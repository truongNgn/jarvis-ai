"""Scoped Win32 window operations. Never bypass foreground or secure-desktop policy."""
import base64
import ctypes
import hmac
import os
import time
from ctypes import wintypes
from pathlib import Path

from jarvis.runtime.protocol import Rejected, canonical, loads, sign
from jarvis.security.paths import executable


def apis():
    if os.name != "nt":
        raise Rejected("windows_required")
    u = ctypes.WinDLL("user32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = [
        (u, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
        (u, "GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
        (u, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        (u, "GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        (u, "GetForegroundWindow", [], wintypes.HWND),
        (u, "SetForegroundWindow", [wintypes.HWND], wintypes.BOOL),
        (u, "OpenInputDesktop", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (u, "SwitchDesktop", [wintypes.HANDLE], wintypes.BOOL),
        (u, "CloseDesktop", [wintypes.HANDLE], wintypes.BOOL),
        (k, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (k, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        (k, "QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                         ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        (k, "GetProcessTimes", [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)], wintypes.BOOL),
    ]
    for lib, name, args, result in signatures:
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, result
    return u, k


def interactive():
    u, _ = apis()
    desktop = u.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        raise Rejected("interactive_desktop_unavailable")
    try:
        if not u.SwitchDesktop(desktop):
            raise Rejected("desktop_locked_or_secure")
    finally:
        u.CloseDesktop(desktop)


def acquire_runtime_lock():
    _, k = apis()
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    ctypes.set_last_error(0)
    handle = k.CreateMutexW(None, False, "Local\\JarvisAI-DesktopRuntime")
    if not handle:
        raise Rejected("runtime_lock_unavailable")
    if ctypes.get_last_error() == 183:
        k.CloseHandle(handle)
        raise Rejected("runtime_already_running")
    return handle


def release_runtime_lock(handle):
    _, k = apis()
    k.CloseHandle(handle)


def identity(hwnd, config):
    u, k = apis()
    pid = wintypes.DWORD()
    if not u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        raise Rejected("stale_window")
    process = k.OpenProcess(0x1000, False, pid.value)
    if not process:
        raise Rejected("window_process_inaccessible")
    try:
        text = ctypes.create_unicode_buffer(4096)
        length = wintypes.DWORD(len(text))
        if not k.QueryFullProcessImageNameW(process, 0, text, ctypes.byref(length)):
            raise Rejected("window_process_inaccessible")
        if os.path.normcase(str(Path(text.value).resolve())) != os.path.normcase(executable(config, "editor_executable")):
            raise Rejected("window_not_allowlisted")
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(process, *(ctypes.byref(item) for item in times)):
            raise Rejected("window_process_inaccessible")
        creation = str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        return pid.value, creation
    finally:
        k.CloseHandle(process)


def list_windows(config, key):
    u, _ = apis()
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(hwnd, _):
        if len(windows) >= 32:
            return False
        if not u.IsWindowVisible(hwnd):
            return True
        try:
            pid, created = identity(hwnd, config)
        except (Rejected, OSError):
            return True
        title = ctypes.create_unicode_buffer(257)
        u.GetWindowTextW(hwnd, title, len(title))
        payload = {"hwnd": int(hwnd), "pid": pid, "created": created, "expiry": time.time() + 30}
        encoded = base64.urlsafe_b64encode(canonical(payload).encode()).decode()
        windows.append({"window_ref": encoded + "." + sign(payload, key), "title": title.value, "pid": pid})
        return True

    u.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    u.EnumWindows.restype = wintypes.BOOL
    u.EnumWindows(collect, 0)
    return {"windows": windows}


def decode_reference(reference, key, now=None):
    try:
        encoded, signature = reference.split(".", 1)
        payload = loads(base64.urlsafe_b64decode(encoded))
        if set(payload) != {"hwnd", "pid", "created", "expiry"} or not hmac.compare_digest(sign(payload, key), signature):
            raise Rejected("invalid_window_reference")
        if not (time.time() if now is None else now) < payload["expiry"]:
            raise Rejected("stale_window_reference")
        return payload
    except (ValueError, TypeError, KeyError) as exc:
        raise Rejected("invalid_or_stale_window_reference") from exc


def activate(config, key, reference):
    interactive()
    data = decode_reference(reference, key)
    pid, created = identity(data["hwnd"], config)
    if (pid, created) != (data["pid"], data["created"]):
        raise Rejected("stale_window_identity")
    u, _ = apis()
    if not u.SetForegroundWindow(data["hwnd"]) or u.GetForegroundWindow() != data["hwnd"]:
        raise Rejected("foreground_denied")
    return {"foreground": True}
