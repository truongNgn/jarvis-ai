"""User-scoped DPAPI credentials; no plaintext credentials in the repository."""
import ctypes
import json
import os
import secrets
import subprocess
from pathlib import Path
from ctypes import wintypes


def private_root():
    if os.name != "nt":
        raise RuntimeError("Windows credential storage requires Windows")
    return Path(os.environ["LOCALAPPDATA"]) / "JarvisAI"


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, protect):
    if os.name != "nt":
        raise RuntimeError("DPAPI requires Windows")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = api.CryptProtectData if protect else api.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(dest.data)


def load_credentials():
    path = private_root() / "bridge.dpapi"
    return json.loads(crypt(path.read_bytes(), False))


def initialize():
    root = private_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "bridge.dpapi"
    if not path.exists():
        data = {key: secrets.token_hex(32) for key in ("admin_token", "runtime_token", "signing_key")}
        with path.open("xb") as file:
            file.write(crypt(json.dumps(data).encode(), True))
    data = load_credentials()
    # Protect the private runtime directory and its journal as well as credentials.
    sid = subprocess.check_output(["powershell", "-NoProfile", "-Command",
        "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value"], text=True).strip()
    subprocess.run(["icacls", str(root), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"], check=True, capture_output=True)
    subprocess.run(["wsl", "-d", "Ubuntu", "-u", "root", "--", "docker", "-H",
        "unix:///run/persona-docker.sock", "volume", "create", "jarvis-ai_bridge_secrets"], check=True, capture_output=True)
    subprocess.run(["wsl", "-d", "Ubuntu", "-u", "root", "--", "docker", "-H",
        "unix:///run/persona-docker.sock", "volume", "create", "jarvis-ai_bridge_state"], check=True, capture_output=True)
    installer = ("import sys,pathlib,os,json; p=pathlib.Path('/secrets/bridge.json'); "
                 "d=json.load(sys.stdin); p.write_text(json.dumps(d)); os.chown(p,10001,10001); os.chmod(p,0o600); "
                 "os.chown('/state',10001,10001); os.chmod('/state',0o700)")
    subprocess.run(["wsl", "-d", "Ubuntu", "-u", "root", "--", "docker", "-H",
        "unix:///run/persona-docker.sock", "run", "--rm", "--network", "none", "-i", "-v",
        "jarvis-ai_bridge_secrets:/secrets", "-v", "jarvis-ai_bridge_state:/state",
        "python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258",
        "python", "-c", installer],
        input=json.dumps(data), text=True, check=True, capture_output=True)
    print("DPAPI credentials and JARVIS-only broker secret volume provisioned; no tokens printed.")


if __name__ == "__main__":
    initialize()
