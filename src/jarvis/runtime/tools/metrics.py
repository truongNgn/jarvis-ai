"""Native Win32 monitoring and optional NVML, with no host Python packages."""
import ctypes
import os
import shutil
import time
from ctypes import wintypes
from pathlib import Path

from jarvis.runtime.protocol import Rejected
from jarvis.security.paths import project_path


def gpu_metrics():
    candidates = [Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvml.dll",
                  Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "NVIDIA Corporation/NVSMI/nvml.dll"]
    dll = next((p for p in candidates if p.is_file()), None)
    if dll is None:
        return {"available": False, "reason": "nvml_unavailable"}
    try:
        lib = ctypes.WinDLL(str(dll))
        lib.nvmlInit_v2.restype = ctypes.c_int
        if lib.nvmlInit_v2() != 0:
            return {"available": False, "reason": "nvml_initialization_failed"}
        try:
            device = ctypes.c_void_p()
            lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
            lib.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
            if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(device)) != 0:
                return {"available": False, "reason": "gpu_unavailable"}
            class Memory(ctypes.Structure):
                _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]
            memory = Memory()
            lib.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory)]
            lib.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
            if lib.nvmlDeviceGetMemoryInfo(device, ctypes.byref(memory)) != 0:
                return {"available": False, "reason": "gpu_counter_unavailable"}
            return {"available": True, "total_bytes": memory.total, "used_bytes": memory.used}
        finally:
            lib.nvmlShutdown()
    except (OSError, AttributeError):
        return {"available": False, "reason": "nvml_unavailable"}


def collect(config):
    if os.name != "nt":
        raise Rejected("windows_required")
    lib = ctypes.WinDLL("kernel32", use_last_error=True)
    lib.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
    lib.GetSystemTimes.restype = wintypes.BOOL

    def times():
        values = [wintypes.FILETIME() for _ in range(3)]
        if not lib.GetSystemTimes(*(ctypes.byref(x) for x in values)):
            raise Rejected("cpu_metrics_unavailable")
        return [(x.dwHighDateTime << 32) | x.dwLowDateTime for x in values]

    before = times()
    started = time.monotonic()
    time.sleep(0.1)
    after = times()
    idle, kernel, user = [a-b for a, b in zip(after, before)]
    total = kernel + user
    cpu = max(0.0, min(100.0, 100.0 * (total-idle)/total)) if total else 0.0
    class Memory(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total", "free", "page_total", "page_free", "virtual_total", "virtual_free", "extended")]]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    lib.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
    lib.GlobalMemoryStatusEx.restype = wintypes.BOOL
    if not lib.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise Rejected("memory_metrics_unavailable")
    disk = shutil.disk_usage(project_path(config, "jarvis-ai"))
    return {"cpu_percent": round(cpu, 2), "ram_used_bytes": memory.total-memory.free,
            "ram_total_bytes": memory.total, "disk_free_bytes": disk.free, "disk_total_bytes": disk.total,
            "sample_time": time.time(), "sample_seconds": round(time.monotonic()-started, 3), "gpu": gpu_metrics()}
