"""The add-on's side of the sound print tool: run from Kodi's Python, which has no numpy, so the tool runs in its
own Python environment (made by setup) as a separate process, without a console window, as the Claude CLI does.

- neighbours: one short call per mix (python -m soundprint neighbours ..., JSON on stdout);
- an analysis runs detached, so Kodi doesn't wait for it, and says how far it is in status.json; it follows
  Kodi's process and stops after the songs in hand once Kodi has closed (the service starts it again later);
- setup makes the environment with a Python the listener has installed (Kodi's own can't make one).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Callable, Dict, List, Optional

from soundprint.state import environment_python, model_folder, model_present, read_status, request_stop, running

ADDON_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000  # not ended with Kodi, should Kodi end its processes
NEIGHBOURS_TIMEOUT = 120  # s; the first search after many new songs reads all vectors
SETUP_TIMEOUT = 1800  # s; pip downloads about 60 MB
# Kodi's own Python settings would make the tool's Python load Kodi's library instead of its own.
FOREIGN_VARIABLES = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE")

# Why a call failed.
NOT_SET_UP = "not_set_up"
NOT_ANALYSED = "not_analysed"
TIMEOUT = "timeout"
FAILED = "failed"


class SoundprintError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def data_folder(profile: str) -> str:
    return os.path.join(profile, "soundprint")


def environment(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    variables = dict(os.environ if base is None else base)
    for name in FOREIGN_VARIABLES:
        variables.pop(name, None)
    variables["PYTHONIOENCODING"] = "utf-8"
    return variables


def window_flags() -> int:
    return CREATE_NO_WINDOW if sys.platform == "win32" else 0


def command(python: str, data: str, userdata: str, *args: str) -> List[str]:
    return [python, "-X", "utf8", "-m", "soundprint", "--userdata", userdata, "--data", data, *args]


def not_ready(data: str) -> str:
    """Why the tool can't be used yet ("" when it can)."""
    if not os.path.isfile(environment_python(data)):
        return "The sound engine isn't set up yet (its Python environment is missing)."
    if not model_present(model_folder(data)):
        return "The sound engine's model is missing; run its set-up again."
    return ""


def run(cmd: List[str], timeout: int, runner: Callable = subprocess.run):
    try:
        return runner(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment(),
                      cwd=ADDON_FOLDER, timeout=timeout, creationflags=window_flags())
    except subprocess.TimeoutExpired:
        raise SoundprintError(TIMEOUT, f"The sound engine did not answer within {timeout} s.")
    except OSError as exc:
        raise SoundprintError(NOT_SET_UP, f"The sound engine could not be started: {exc}")


def last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def neighbours(data: str, userdata: str, seed: str, count: int, window: int = 0, variety: int = 0,
               runner: Callable = subprocess.run) -> dict:
    """The tool's answer (see soundprint.__main__.neighbours): songs nearest to seed, with similarity, artist and
    title, no artist repeated within window songs; raises SoundprintError when there are none."""
    reason = not_ready(data)
    if reason:
        raise SoundprintError(NOT_SET_UP, reason)
    completed = run(command(environment_python(data), data, userdata, "neighbours", seed, "--count", str(count),
                            "--artist-window", str(window), "--variety", str(variety)), NEIGHBOURS_TIMEOUT, runner)
    try:
        answer = json.loads(completed.stdout)
    except ValueError:
        raise SoundprintError(FAILED, f"The sound engine failed: {last_line(completed.stderr) or 'no answer'}")
    if not answer.get("songs"):
        why = answer.get("seed_vector") or "no songs"
        if why == "not analysed" or why == "not a local file":
            raise SoundprintError(NOT_ANALYSED, f"The sound engine has no sound print of this song ({why}).")
        raise SoundprintError(NOT_ANALYSED, f"The sound engine found no songs ({why}; "
                                            f"{answer.get('analysed', 0)} song(s) analysed).")
    return answer


def start_analysis(data: str, userdata: str, popen: Callable = subprocess.Popen, kodi_pid: int = 0) -> dict:
    """Start an analysis of the library's new and changed songs, detached; {"started": False, ...} when one is
    running already. With kodi_pid (Kodi's process: the add-on runs inside it), the analysis stops once Kodi has
    closed."""
    reason = not_ready(data)
    if reason:
        raise SoundprintError(NOT_SET_UP, reason)
    other = running(data)
    if other:
        return {"started": False, "pid": other.get("pid")}
    cmd = command(environment_python(data), data, userdata, "analyse",
                  *(["--kodi-pid", str(kodi_pid)] if kodi_pid else []))
    with open(os.path.join(data, "run.out"), "w", encoding="utf-8") as out, \
            open(os.path.join(data, "run.err"), "w", encoding="utf-8") as err:
        flags = window_flags() | (CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=ADDON_FOLDER, env=environment(),
                      close_fds=True)
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        try:
            process = popen(cmd, creationflags=flags | (CREATE_BREAKAWAY_FROM_JOB if flags else 0), **kwargs)
        except OSError:  # Kodi's job doesn't allow breaking away
            process = popen(cmd, creationflags=flags, **kwargs)
    return {"started": True, "pid": process.pid, "command": cmd}


def stop_analysis(data: str) -> bool:
    """Ask a running analysis to stop after the songs in hand; False if none is running."""
    if not running(data):
        return False
    request_stop(data)
    return True


def base_pythons(configured: str = "", which: Callable[[str], Optional[str]] = shutil.which) -> List[str]:
    """Pythons that can make the tool's environment: the configured one, then those on the PATH."""
    found = [configured] if configured and os.path.isfile(configured) else []
    for name in ("python3", "python", "py"):
        path = which(name)
        if path and path not in found:
            found.append(path)
    return found


def setup(data: str, userdata: str, base_python: str, runner: Callable = subprocess.run) -> str:
    """Make the tool's environment and download the model (minutes); returns what it printed last. The whole
    output goes to setup.log in the data folder."""
    os.makedirs(data, exist_ok=True)
    completed = run(command(base_python, data, userdata, "setup"), SETUP_TIMEOUT, runner)
    with open(os.path.join(data, "setup.log"), "w", encoding="utf-8") as handle:
        handle.write(f"{' '.join(command(base_python, data, userdata, 'setup'))}\n\n{completed.stdout}\n"
                     f"{completed.stderr}")
    if completed.returncode != 0:
        raise SoundprintError(FAILED, f"The set-up failed: {last_line(completed.stderr) or last_line(completed.stdout)}")
    return last_line(completed.stdout)


def counts(data: str) -> Dict[str, int]:
    """Songs stored: analysed, and those that could not be read."""
    database = os.path.join(data, "sound.db")
    if not os.path.isfile(database):
        return {"analysed": 0, "failed": 0}
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=10)
    try:
        analysed, failed = connection.execute("SELECT COUNT(vector), COUNT(*) - COUNT(vector) FROM songs").fetchone()
    finally:
        connection.close()
    return {"analysed": analysed, "failed": failed}


# --- What the status window says ---------------------------------------------------------------------------------
def when(timestamp: float, now: float) -> str:
    moment, today = time.localtime(timestamp), time.localtime(now)
    clock = time.strftime("%H:%M", moment)
    days = (time.mktime(moment[:3] + (0, 0, 0, 0, 0, -1)) - time.mktime(today[:3] + (0, 0, 0, 0, 0, -1))) / 86400
    if round(days) == 0:
        return f"today at {clock}"
    if round(days) == 1:
        return f"tomorrow at {clock}"
    if round(days) == -1:
        return f"yesterday at {clock}"
    return time.strftime("%Y-%m-%d %H:%M", moment)


def duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{max(1, minutes)} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def status_lines(data: str, now: float = 0.0, alive: Callable[[str], dict] = running) -> List[str]:
    now = now or time.time()
    reason = not_ready(data)
    if reason:
        return [reason, "Settings > Advanced > Set up the sound engine."]
    status, stored = read_status(data), counts(data)
    lines = [f"Sound prints stored: {stored['analysed']:,} song(s); {stored['failed']:,} file(s) could not be read."]
    state = status.get("state")
    done, todo, failed = int(status.get("done") or 0), int(status.get("todo") or 0), int(status.get("failed") or 0)
    if state == "running" and alive(data):
        if status.get("phase") == "planning":
            lines.append(f"An analysis started {when(status.get('started', now), now)}; it is looking for new and "
                         f"changed songs among {int(status.get('songs') or 0):,}.")
        else:
            lines.append(f"Analysing now: {done:,} of {todo:,} song(s) ({100 * done // max(1, todo)} %), "
                         f"{failed:,} could not be read.")
            if status.get("eta"):
                lines.append(f"About {status.get('seconds_per_song', 0):.2f} s per song: done in about "
                             f"{duration(status['eta'] - now)} ({when(status['eta'], now)}).")
            lines.append(f"Started {when(status.get('started', now), now)}; {status.get('workers')} process(es) "
                         f"with {status.get('threads')} thread(s) each, at low priority.")
    elif state == "running":
        lines.append(f"The last analysis ended without finishing (the computer was switched off, or its process "
                     f"was ended) after {done:,} of {todo:,} song(s). It goes on where it stopped when it starts again.")
    elif state == "finished":
        taken_over = int(status.get("taken_over") or 0)
        lines.append(f"The last analysis finished {when(status.get('updated', now), now)}: {done:,} song(s) "
                     f"analysed, {failed:,} could not be read"
                     + (f", {taken_over:,} taken over (the same file, its path spelled differently)" if taken_over
                        else "")
                     + f"; {int(status.get('missing') or 0):,} song(s) of Kodi's library are not on disk.")
    elif state == "stopped" and status.get("stopped_by") == "kodi_closed":
        lines.append(f"The last analysis stopped when Kodi closed ({when(status.get('updated', now), now)}) after "
                     f"{done:,} of {todo:,} song(s). It goes on where it stopped two minutes after Kodi starts.")
    elif state == "stopped":
        lines.append(f"The last analysis was stopped {when(status.get('updated', now), now)} after {done:,} of "
                     f"{todo:,} song(s). It goes on where it stopped when it starts again.")
    elif state == "failed":
        lines.append(f"The last analysis failed {when(status.get('updated', now), now)}: {status.get('error', '')}")
    else:
        lines.append("No analysis has run yet.")
    return lines
