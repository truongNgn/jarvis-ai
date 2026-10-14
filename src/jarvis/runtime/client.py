"""Native Windows outbound client and explicit administrative tool CLI."""
import argparse
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from jarvis.runtime.auth import endpoint
from jarvis.runtime.dispatcher import Dispatcher
from jarvis.runtime.journal import Journal
from jarvis.runtime.protocol import Rejected, canonical, digest, loads, manifest, validate_result
from jarvis.security.credentials import load_credentials, private_root


class Client:
    def __init__(self, base, token):
        self.base, self.token = endpoint(base), token
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise Rejected("broker_redirect_forbidden")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, route, payload=None):
        request = urllib.request.Request(self.base + route, data=None if payload is None else canonical(payload).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with self.opener.open(request, timeout=2) as response:
            raw = response.read(32769)
            if len(raw) > 32768:
                raise Rejected("broker_response_too_large")
            return loads(raw)


def configuration(path, allow_desktop=False):
    config = loads(Path(path).read_text(encoding="utf-8-sig"))
    if set(config) != {"projects", "editor_executable", "git_executable", "allowed_tools"}:
        raise Rejected("invalid_local_configuration")
    config["editor_executable"] = os.path.expandvars(config["editor_executable"])
    if allow_desktop:
        config["allowed_tools"] = sorted(set(config["allowed_tools"]) | {"project.open", "window.activate"})
    expected = manifest(config["allowed_tools"])
    if set(expected["tools"]) != set(config["allowed_tools"]):
        raise Rejected("unknown_configured_capability")
    return config


def serve(args, credentials):
    config = configuration(args.config, args.allow_desktop)
    runtime = Client(args.broker, credentials["runtime_token"])
    capabilities = manifest(config["allowed_tools"])
    until = time.monotonic()+20
    while True:
        try:
            registered = runtime.request("/v1/runtime/register", capabilities)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in {502, 503} or time.monotonic() >= until:
                raise
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            if time.monotonic() >= until:
                raise
        time.sleep(0.25)
    if registered.get("manifest_hash") != digest(capabilities):
        raise Rejected("handshake_mismatch")
    root = private_root()
    journal = Journal(root / "runtime.sqlite")
    dispatcher = Dispatcher(config, credentials, journal)
    try:
        while True:
            job = runtime.request("/v1/runtime/calls")["job"]
            if job:
                call = job["call"]
                def cancelled():
                    try:
                        return runtime.request("/v1/runtime/calls/" + call["call_id"] + "/status")["cancelled"]
                    except (urllib.error.URLError, http.client.HTTPException, OSError, Rejected):
                        return True  # disconnect pauses further effects
                output = dispatcher.dispatch(call, cancelled)
                # A lost result POST is retried once. Redelivery consults the durable journal.
                for attempt in range(2):
                    try:
                        runtime.request("/v1/runtime/results", {"lease_id": job["lease_id"], "result": output})
                        break
                    except (urllib.error.URLError, http.client.HTTPException, OSError):
                        if attempt:
                            raise
                        time.sleep(0.2)
                print(canonical({"call_id": call["call_id"], "tool": call["tool"], "status": output["status"]}), flush=True)
            if args.once:
                break
            time.sleep(0.25 if job else 1)
    finally:
        journal.close()


def main():
    parser = argparse.ArgumentParser(description="JARVIS Phase 2 native runtime; explicit tool operations only")
    parser.add_argument("--broker", default="http://127.0.0.1:18765")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("serve")
    run.add_argument("--config", default="config/runtime.example.json")
    run.add_argument("--allow-desktop", action="store_true")
    run.add_argument("--once", action="store_true")
    call = sub.add_parser("call")
    call.add_argument("tool")
    call.add_argument("--args", default="{}")
    call.add_argument("--call-id")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("call_id")
    args = parser.parse_args()
    credentials = load_credentials()
    if args.command == "serve":
        from jarvis.runtime.tools.windows import acquire_runtime_lock, release_runtime_lock
        handle = acquire_runtime_lock()
        try:
            serve(args, credentials)
        finally:
            release_runtime_lock(handle)
        return
    client = Client(args.broker, credentials["admin_token"])
    if args.command == "cancel":
        print(canonical(client.request("/v1/calls/" + args.call_id + "/cancel", {})))
        return
    payload = {"tool": args.tool, "args": loads(args.args)}
    if args.call_id:
        payload["call_id"] = args.call_id
        payload["task_id"] = args.call_id
    ident = client.request("/v1/calls", payload)["call_id"]
    until = time.monotonic()+30
    while time.monotonic() < until:
        state = client.request("/v1/calls/" + ident)
        if state["result"]:
            print(canonical(state["result"]))
            raise SystemExit(0 if state["result"]["status"] == "succeeded" else 2)
        time.sleep(0.2)
    print(canonical({"call_id": ident, "status": "unknown", "error": "wait_expired"}))
    raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (Rejected, urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        print(canonical({"status": "unavailable", "error": str(exc) if isinstance(exc, Rejected) else type(exc).__name__}))
        raise SystemExit(2)
