"""Analysing many songs: worker processes, each with its own model; only the main process writes the store.

Decoding and the model both use one CPU core per song, so songs are spread over processes rather than threads
(Python threads would share one core for the spectrogram). The processes run at idle priority by default, so
playback and Kodi keep the CPU whenever they need it.

While it runs, status.json in the data folder says how far it is; a file named "stop" there ends it after the
songs in hand (the next run picks up where it stopped). Started by Kodi, it follows Kodi's process and ends the same
way once Kodi has closed; the add-on's service starts it again after Kodi's next start. Every song gets a line in
analysis.log.
"""

from __future__ import annotations

import logging
import logging.handlers
import multiprocessing
import os
import time
from typing import Dict, List, Sequence, Tuple

from soundprint import analysis_version
from soundprint.state import (LOG_FILE, STOP_FILE, Watched, lower_priority, read_status, running,
                              write_status)
from soundprint.store import Store

STATUS_EVERY = 5.0  # s
COMMIT_EVERY = 25  # songs

MODEL = None
SNIPPETS = 0


def start_worker(model_folder: str, threads: int, snippets: int, low: bool) -> None:
    global MODEL, SNIPPETS
    if low:
        lower_priority()
    from soundprint.model import Model

    MODEL, SNIPPETS = Model(model_folder, threads), snippets


def analyse_song(item: Tuple[str, int, float]) -> dict:
    from soundprint import audio

    path, size, mtime = item
    started = time.perf_counter()
    try:
        windows, length, how = audio.snippets(path, SNIPPETS)
        decoded = time.perf_counter()
        vector = MODEL.embed(windows)
        return {"path": path, "size": size, "mtime": mtime, "length": length, "vector": vector, "error": "",
                "windows": len(windows), "how": how, "decode_s": decoded - started,
                "model_s": time.perf_counter() - decoded}
    except Exception as exc:  # a file FFmpeg can't open, or a broken one
        return {"path": path, "size": size, "mtime": mtime, "length": 0.0, "vector": None,
                "error": f"{type(exc).__name__}: {exc}", "decode_s": time.perf_counter() - started, "model_s": 0.0}


def same_file(path: str, info: os.stat_result, known: Dict[str, Tuple[int, float, str, bool]],
              spellings: Dict[str, List[str]], version: str, retry_failed: bool = False) -> str:
    """A stored path that names the same file as path, spelled differently ("D:\\Music" and "d:\\music" on Windows,
    where os.path.normcase makes them equal), with the same size and change time and the current version; "" if
    there is none. Kodi keeps such a spelling as a song of its own (F45)."""
    for stored in spellings.get(os.path.normcase(path), ()):
        size, mtime, stored_version, failed = known[stored]
        if (stored != path and size == info.st_size and abs(mtime - info.st_mtime) < 1e-3
                and stored_version == version and not (failed and retry_failed)):
            return stored
    return ""


def plan(paths: Sequence[str], store: Store, version: str, retry_failed: bool = False
         ) -> Tuple[List[Tuple[str, int, float]], Dict[str, int], List[Tuple[str, str]]]:
    """The songs to analyse (path, size, change time), counts of the rest: unchanged, failed before (and
    unchanged; analysed again with retry_failed, after a fix of the decoding), missing (the file isn't there),
    taken over; and the new paths whose row is taken over from another spelling of the same file (new, stored)."""
    known = store.known()
    spellings: Dict[str, List[str]] = {}
    for stored in known:
        spellings.setdefault(os.path.normcase(stored), []).append(stored)
    todo, taken_over = [], []
    counts = {"unchanged": 0, "failed_before": 0, "missing": 0, "taken_over": 0}
    for path in paths:
        try:
            info = os.stat(path)
        except OSError:
            counts["missing"] += 1
            continue
        before = known.get(path)
        if before and before[0] == info.st_size and abs(before[1] - info.st_mtime) < 1e-3:
            if before[3]:
                if not retry_failed:
                    counts["failed_before"] += 1
                    continue
            elif before[2] == version:
                counts["unchanged"] += 1
                continue
        twin = "" if before else same_file(path, info, known, spellings, version, retry_failed)
        if twin:
            taken_over.append((path, twin))
            counts["taken_over"] += 1
            continue
        todo.append((path, info.st_size, info.st_mtime))
    return todo, counts, taken_over


def logger_for(folder: str) -> logging.Logger:
    log = logging.getLogger("soundprint")
    if not log.handlers:
        handler = logging.handlers.RotatingFileHandler(os.path.join(folder, LOG_FILE), maxBytes=20 << 20,
                                                       backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


def run(paths: Sequence[str], folder: str, model_folder: str, snippets: int, workers: int, threads: int,
        low: bool = True, prune: bool = False, limit: int = 0, retry_failed: bool = False, say=print,
        kodi_pid: int = 0) -> dict:
    """Analyse what's new or changed among paths; returns the final status ("busy" when another analysis of this
    data folder is running: two would write the same store). With kodi_pid, it stops as if asked to (stop file)
    once that process has ended, and says so in the status ("stopped_by": "kodi_closed")."""
    os.makedirs(folder, exist_ok=True)
    log = logger_for(folder)
    other = running(folder)
    if other and int(other.get("pid") or 0) != os.getpid():
        line = f"an analysis is running already (process {other.get('pid')}); this one doesn't start"
        log.info(line)
        say(line)
        return {"state": "busy", "pid": other.get("pid")}
    kodi = Watched(kodi_pid)
    priority = lower_priority() if low else "normal priority"
    version = analysis_version(snippets)
    # running from now on, while the files are looked at (that takes a while for a large library)
    write_status(folder, {"state": "running", "phase": "planning", "pid": os.getpid(), "started": time.time(),
                          "version": version, "songs": len(paths)})
    store = Store(folder)
    stop = os.path.join(folder, STOP_FILE)
    if os.path.exists(stop):
        os.remove(stop)
    try:
        if prune:
            listed = set(paths)
            gone = store.remove(path for path in store.known() if path not in listed)
            log.info("removed %d stored song(s) that are no longer in the library", gone)
        todo, counts, taken_over = plan(paths, store, version, retry_failed)
        if limit:
            todo = todo[:limit]
        status = {"state": "running", "pid": os.getpid(), "started": time.time(), "version": version,
                  "songs": len(paths), "todo": len(todo), "done": 0, "failed": 0, **counts,
                  "workers": workers, "threads": threads, "snippets": snippets}
        line = (f"analysis {version}: {len(paths)} song(s) listed, {len(todo)} to analyse; {counts['unchanged']} "
                f"unchanged, {counts['failed_before']} failed before, {counts['missing']} missing, "
                f"{counts['taken_over']} taken over from another spelling of their path; {workers} "
                f"worker(s) x {threads} thread(s), {priority}")
        log.info(line)
        say(line)
        for path, stored in taken_over:
            store.take_over(stored, path)
            log.info("%s: taken over from %s (the same file, size and change time; the path differs only in case)",
                     path, stored)
        store.commit()
        write_status(folder, status)
        if not todo:
            status["state"] = "finished"
            write_status(folder, status)
            return status
        # load the model once here first: a worker whose start fails is restarted by the pool without end
        from soundprint.model import Model

        Model(model_folder, 1)
        started, last_status = time.perf_counter(), 0.0
        # one thread per process for numpy's own maths: by default every process would start a thread per CPU
        # for each matrix product, and eight processes then spend most of their time waiting for each other
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[variable] = "1"
        context = multiprocessing.get_context("spawn")
        pool = context.Pool(workers, initializer=start_worker, initargs=(model_folder, threads, snippets, low))
        try:
            for result in pool.imap_unordered(analyse_song, todo, chunksize=2):
                store.put(result["path"], result["size"], result["mtime"], version, result["length"],
                          result["vector"], result["error"])
                status["done"] += 1
                if result["error"]:
                    status["failed"] += 1
                    log.warning("failed: %s: %s", result["path"], result["error"])
                else:
                    log.info("%s: %.0f s, %d window(s) by %s, decode %.2f s, model %.2f s", result["path"],
                             result["length"], result["windows"], result["how"], result["decode_s"], result["model_s"])
                if status["done"] % COMMIT_EVERY == 0:
                    store.commit()
                now = time.perf_counter()
                if now - last_status >= STATUS_EVERY or status["done"] == len(todo):
                    last_status = now
                    rate = (now - started) / status["done"]
                    status.update(seconds_per_song=round(rate, 3),
                                  eta=time.time() + rate * (len(todo) - status["done"]))
                    write_status(folder, status)
                    if kodi.ended():
                        status.update(state="stopped", stopped_by="kodi_closed")
                        log.info("Kodi (process %d) has closed: the analysis stops after the songs in hand and goes "
                                 "on after Kodi's next start", kodi_pid)
                        break
                    if os.path.exists(stop):
                        status["state"] = "stopped"
                        break
            else:
                status["state"] = "finished"
        finally:
            pool.terminate()
            pool.join()
            store.commit()
        line = (f"analysis {status['state']}: {status['done']} of {len(todo)} song(s) in "
                f"{time.perf_counter() - started:.0f} s ({status.get('seconds_per_song', 0):.2f} s per song), "
                f"{status['failed']} failed")
        log.info(line)
        say(line)
        write_status(folder, status)
        return status
    except BaseException as exc:
        status = read_status(folder)
        status.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        write_status(folder, status)
        log.exception("analysis failed")
        raise
    finally:
        if os.path.exists(stop):
            os.remove(stop)
        store.close()
        kodi.close()
