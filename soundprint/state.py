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


IDLE_PRIORITY_CLASS = 0x00000040
PROCESS_IO_PRIORITY = 33  # NtSetInformationProcess's ProcessIoPriority (as psutil's ionice uses it)
IO_PRIORITY_VERY_LOW = 0  # the I/O priority of background work (Windows' own background mode uses it)


def lower_priority() -> str:
    """Idle CPU priority and very low I/O priority for this process (Windows; elsewhere nice 19, which also gives
    the lowest I/O priority of its class). Started by the add-on, an analysis has the idle class from the start
    (soundprint.client.IDLE_PRIORITY_CLASS) and passes it on; this covers one started by hand, and the I/O priority,
    which every process sets for itself. Returns what was set, for the log."""
    done = []
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            # The current process. GetCurrentProcess() gives the same, but ctypes returned it as a 32-bit int,
            # which named no process, so SetPriorityClass failed without a word (F47).
            process = wintypes.HANDLE(-1)
            if ctypes.windll.kernel32.SetPriorityClass(process, IDLE_PRIORITY_CLASS):
                done.append("idle CPU priority")
            else:
                done.append(f"CPU priority not lowered (error {ctypes.windll.kernel32.GetLastError()})")
            hint = ctypes.c_ulong(IO_PRIORITY_VERY_LOW)
            status = ctypes.windll.ntdll.NtSetInformationProcess(process, PROCESS_IO_PRIORITY, ctypes.byref(hint),
                                                                 ctypes.sizeof(hint))
            done.append("very low I/O priority" if status == 0 else
                        f"I/O priority not lowered (status {status & 0xFFFFFFFF:#010x})")
        else:
            os.nice(19)
            done.append("nice 19 (CPU and I/O)")
    except Exception as exc:
        done.append(f"priority not lowered: {type(exc).__name__}: {exc}")
    return ", ".join(done)


class Watched:
    """A process the analysis follows (Kodi, which started it): ended() once it has exited. On Windows a handle is
    held from the start, so the process number can't pass to another process while the analysis runs."""

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0

    def __init__(self, pid: int):
        self.pid, self.handle = pid, None
        if pid > 0 and sys.platform == "win32":
            import ctypes

            self.handle = ctypes.windll.kernel32.OpenProcess(self.SYNCHRONIZE, False, pid)

    def ended(self) -> bool:
        if self.pid <= 0:  # nothing to follow
            return False
        if sys.platform != "win32":
            return not process_alive(self.pid)
        if not self.handle:  # gone before the analysis began
            return True
        import ctypes

        return ctypes.windll.kernel32.WaitForSingleObject(self.handle, 0) == self.WAIT_OBJECT_0

    def close(self) -> None:
        if self.handle:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


def running(folder: str, now: float = 0.0, alive=process_alive) -> dict:
    """The status of the analysis that is running now; {} if none is."""
    status = read_status(folder)
    if status.get("state") != "running":
        return {}
    if (now or time.time()) - float(status.get("updated") or 0) > STALE_SECONDS:
        return {}
    return status if alive(int(status.get("pid") or 0)) else {}
