"""Small strict schema subset shared across Python 3.10 Windows and 3.12 Docker.

Only the explicit primitive schemas below are supported. Unsupported schema
constructs fail rather than accepting an unchecked value.
"""
import hashlib
import hmac
import json
import math
import time


class Rejected(ValueError):
    pass


def unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise Rejected("duplicate_json_key")
        data[key] = value
    return data


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(Rejected("nonfinite_number")))


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(canonical(data).encode()).hexdigest()


def sign(data, key):
    return hmac.new(key.encode(), canonical(data).encode(), hashlib.sha256).hexdigest()


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required,
            "additionalProperties": False}


STRING = {"type": "string", "minLength": 1, "maxLength": 128}
PROJECT = obj({"project_id": {"type": "string", "enum": ["jarvis-ai"]}})
TOOLS = {
    "system.metrics": {"args": obj({}), "timeout": 5, "mutation": False},
    "git.branch": {"args": PROJECT, "timeout": 5, "mutation": False},
    "project.open": {"args": PROJECT, "timeout": 10, "mutation": True},
    "window.list": {"args": obj({"app_id": {"type": "string", "enum": ["vscode"]}}), "timeout": 5, "mutation": False},
    "window.activate": {"args": obj({"window_ref": {"type": "string", "minLength": 1, "maxLength": 1024}}),
                        "timeout": 5, "mutation": True},
}


def validate(value, schema):
    kind = schema["type"]
    if kind == "object":
        if type(value) is not dict or set(value) - schema["properties"].keys():
            raise Rejected("unknown_or_invalid_fields")
        if set(schema["required"]) - value.keys():
            raise Rejected("missing_fields")
        for name, item in value.items():
            validate(item, schema["properties"][name])
    elif kind == "string":
        if type(value) is not str or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 4096):
            raise Rejected("invalid_string")
    elif kind == "integer":
        if type(value) is not int:
            raise Rejected("invalid_integer")
    elif kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise Rejected("invalid_number")
    elif kind == "boolean":
        if type(value) is not bool:
            raise Rejected("invalid_boolean")
    elif kind == "array":
        if type(value) is not list or len(value) > schema.get("maxItems", 64):
            raise Rejected("invalid_array")
        for item in value:
            validate(item, schema["items"])
    else:
        raise Rejected("unsupported_schema")
    if "enum" in schema and value not in schema["enum"]:
        raise Rejected("invalid_enum")
    if kind in {"number", "integer"} and not schema.get("minimum", -1e100) <= value <= schema.get("maximum", 1e100):
        raise Rejected("out_of_range")


def manifest(enabled=None):
    return {"version": 1, "runtime_id": "desktop-main", "tools": {
        name: {"version": 1, "schema_hash": digest(spec["args"]), **spec}
        for name, spec in TOOLS.items() if enabled is None or name in enabled}}


CALL_SCHEMA = obj({
    "version": {"type": "integer", "enum": [1]}, "policy_version": {"type": "integer", "enum": [1]},
    "call_id": STRING, "task_id": STRING, "tool": {"type": "string", "enum": list(TOOLS)},
    "args": obj({}, []), "deadline": {"type": "number"}, "schema_hash": STRING,
    "grant": obj({"principal": {"type": "string", "enum": ["local-user"]},
        "tools": {"type": "array", "items": {"type": "string", "enum": list(TOOLS)}, "maxItems": 5},
        "projects": {"type": "array", "items": {"type": "string", "enum": ["jarvis-ai"]}, "maxItems": 1}}),
    "signature": STRING,
})


def validate_call(call, key, enabled, now=None, check_deadline=True):
    if type(call) is not dict or call.get("tool") not in TOOLS:
        raise Rejected("unknown_tool")
    schema = {**CALL_SCHEMA, "properties": {**CALL_SCHEMA["properties"], "args": TOOLS[call["tool"]]["args"]}}
    validate(call, schema)
    unsigned = {k: v for k, v in call.items() if k != "signature"}
    if not hmac.compare_digest(sign(unsigned, key), call["signature"]):
        raise Rejected("invalid_signature")
    name = call["tool"]
    if name not in enabled or name not in call["grant"]["tools"]:
        raise Rejected("tool_not_granted")
    if call["args"].get("project_id") not in (None, *call["grant"]["projects"]):
        raise Rejected("project_not_granted")
    if call["schema_hash"] != digest(TOOLS[name]["args"]):
        raise Rejected("schema_mismatch")
    now = time.time() if now is None else now
    if check_deadline and not now < call["deadline"] <= now + 31:
        raise Rejected("expired_or_excessive_deadline")
    return call


def result(call, status, data=None, error=None, verification="unverified"):
    return {"version": 1, "call_id": call.get("call_id", "invalid"), "tool": call.get("tool", "invalid"),
            "status": status, "data": data or {}, "error": error, "verification": verification,
            "synthetic": False}


def validate_result(value, call):
    if type(value) is not dict:
        raise Rejected("invalid_result")
    schema = obj({"version": {"type": "integer", "enum": [1]}, "call_id": STRING, "tool": STRING,
        "status": {"type": "string", "enum": ["succeeded", "failed", "denied", "cancelled", "unknown"]},
        "data": obj({}, []), "error": {"type": "string", "maxLength": 128},
        "verification": {"type": "string", "enum": ["verified", "unverified"]},
        "synthetic": {"type": "boolean", "enum": [False]}})
    # Data is validated below by tool-specific executable postconditions.
    copy = dict(value)
    data = copy.get("data")
    if copy.get("error") is None:
        copy["error"] = ""
    copy["data"] = {}
    validate(copy, schema)
    if value["call_id"] != call["call_id"] or value["tool"] != call["tool"] or type(data) is not dict:
        raise Rejected("result_identity_mismatch")
    if len(canonical(value).encode()) > 32768:
        raise Rejected("result_too_large")
    if value["status"] != "succeeded":
        if data:
            raise Rejected("failed_result_has_data")
        return value
    name = call["tool"]
    if name == "system.metrics":
        _validate_metrics(data)
    elif name == "git.branch":
        validate(data, obj({"project_id": {"type": "string", "enum": [call["args"]["project_id"]]},
            "state": {"type": "string", "enum": ["branch", "detached", "unborn", "not_a_repository"]},
            "branch": {"type": "string", "maxLength": 256}, "commit": {"type": "string", "maxLength": 64}}))
    elif name == "project.open":
        validate(data, obj({"project_id": {"type": "string", "enum": [call["args"]["project_id"]]},
            "launch_requested": {"type": "boolean", "enum": [True]},
            "matching_window_count": {"type": "integer", "minimum": 0}}))
        if value["verification"] != "unverified":
            raise Rejected("launch_receipt_is_not_workspace_verification")
    elif name == "window.list":
        validate(data, obj({"windows": {"type": "array", "maxItems": 32, "items": obj({
            "window_ref": {"type": "string", "maxLength": 1024}, "title": {"type": "string", "maxLength": 256},
            "pid": {"type": "integer", "minimum": 1}})}}))
    elif name == "window.activate":
        validate(data, obj({"foreground": {"type": "boolean", "enum": [True]}}))
    return value


def _validate_metrics(data):
    validate({**data, "gpu": {}}, obj({"cpu_percent": {"type": "number", "minimum": 0, "maximum": 100},
        "ram_used_bytes": {"type": "integer", "minimum": 0}, "ram_total_bytes": {"type": "integer", "minimum": 1},
        "disk_free_bytes": {"type": "integer", "minimum": 0}, "disk_total_bytes": {"type": "integer", "minimum": 1},
        "sample_time": {"type": "number"}, "sample_seconds": {"type": "number", "minimum": 0}, "gpu": obj({}, [])}))
    gpu = data.get("gpu")
    if type(gpu) is not dict:
        raise Rejected("invalid_gpu")
    if gpu.get("available") is False:
        validate(gpu, obj({"available": {"type": "boolean", "enum": [False]}, "reason": STRING}))
    else:
        validate(gpu, obj({"available": {"type": "boolean", "enum": [True]},
                          "total_bytes": {"type": "integer", "minimum": 1},
                          "used_bytes": {"type": "integer", "minimum": 0}}))
    if data["ram_used_bytes"] > data["ram_total_bytes"] or data["disk_free_bytes"] > data["disk_total_bytes"]:
        raise Rejected("inconsistent_system_metrics")
