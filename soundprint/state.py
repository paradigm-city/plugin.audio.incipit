"""What the add-on and the tool share on disk, in plain Python (no numpy: Kodi's Python reads it too).

The data folder holds sound.db (the store), status.json (the running or last analysis), a file named "stop" (asks a
running analysis to end), analysis.log, the tool's own Python environment ("python") and the model ("model").
"""

from __future__ import annotations

import json
import os
import sys
import time

from soundprint import MODEL_FILES

STATUS_FILE, STOP_FILE, LOG_FILE = "status.json", "stop", "analysis.log"
# A running analysis writes its status every few seconds; one that hasn't for this long has ended without saying
# so (the computer was switched off) even if its process number is in use again.
ADDON_ID = "plugin.audio.incipit"  # as logs.ADDON_ID (the sound engine runs outside Kodi)
STALE_SECONDS = 3600


def environment_python(data: str) -> str:
    folder = os.path.join(data, "python")
    return os.path.join(folder, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(folder, "bin", "python")


def model_folder(data: str) -> str:
    return os.path.join(data, "model")


def model_present(folder: str) -> bool:
    """Whether the model files are there (their checksums are checked when they are downloaded)."""
    return all(os.path.isfile(os.path.join(folder, name)) for name in MODEL_FILES)


def write_status(folder: str, status: dict) -> None:
    status["updated"] = time.time()
    target = os.path.join(folder, STATUS_FILE)
    with open(target + ".part", "w", encoding="utf-8") as handle:
        json.dump(status, handle, indent=1)
    os.replace(target + ".part", target)


def read_status(folder: str) -> dict:
    try:
        with open(os.path.join(folder, STATUS_FILE), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def request_stop(folder: str) -> None:
    open(os.path.join(folder, STOP_FILE), "w").close()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def running(folder: str, now: float = 0.0, alive=process_alive) -> dict:
    """The status of the analysis that is running now; {} if none is."""
    status = read_status(folder)
    if status.get("state") != "running":
        return {}
    if (now or time.time()) - float(status.get("updated") or 0) > STALE_SECONDS:
        return {}
    return status if alive(int(status.get("pid") or 0)) else {}
