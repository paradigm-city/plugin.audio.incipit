"""python -m soundprint <command>: the sound print tool (run from the add-on's folder, or with it on PYTHONPATH).

  setup         make the tool's own Python environment (<data>/python) with numpy, onnxruntime and av, and
                download the model; needs only a Python 3.9 or later to start with
  check         are numpy, onnxruntime and av there, is the model there, what's stored
  fetch-model   download the DCLAP model (release v1, ~22 MB, AGPL-3.0) into the model folder
  analyse       analyse the library's new and changed songs (resumes where it stopped)
  stop          ask a running analysis to stop
  status        the running or last analysis, as JSON
  neighbours    the songs nearest to a seed by sound, as JSON (with artist and title from Kodi's library)
  failures      the files that could not be read

The data folder defaults to Kodi's addon_data/plugin.audio.incipit/soundprint; the model lives in its "model"
subfolder unless --model says otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from soundprint.state import ADDON_ID, environment_python, read_status, request_stop, running

ADDON_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = ("numpy>=1.24", "onnxruntime>=1.17", "av>=12")


def kodi_userdata() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Kodi", "userdata")
    return os.path.join(os.path.expanduser("~"), ".kodi", "userdata")


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m soundprint", description=__doc__.split("\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--userdata", default=kodi_userdata(), help="Kodi's userdata folder")
    parser.add_argument("--data", help=f"data folder (default: <userdata>/addon_data/{ADDON_ID}/soundprint)")
    parser.add_argument("--model", help="model folder (default: <data>/model)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup")
    commands.add_parser("check")
    commands.add_parser("fetch-model")
    analyse = commands.add_parser("analyse")
    analyse.add_argument("--list", help="a file with one path per line, instead of Kodi's library")
    analyse.add_argument("--folder", action="append", default=[], help="only songs inside this folder (repeatable)")
    analyse.add_argument("--workers", type=int, default=0, help="processes (default: CPU threads / 2)")
    analyse.add_argument("--threads", type=int, default=2, help="model threads per process (default 2)")
    analyse.add_argument("--snippets", type=int, default=0, help="10 s snippets per song (default 6)")
    analyse.add_argument("--limit", type=int, default=0, help="analyse at most this many songs")
    analyse.add_argument("--normal-priority", action="store_true", help="don't lower the priority")
    analyse.add_argument("--prune", action="store_true", help="remove stored songs that are no longer listed")
    analyse.add_argument("--kodi-pid", type=int, default=0,
                         help="stop once this process (Kodi) has ended; the add-on starts it again with Kodi")
    analyse.add_argument("--retry-failed", action="store_true",
                         help="analyse songs that failed before again, although their files haven't changed")
    commands.add_parser("stop")
    commands.add_parser("status")
    near = commands.add_parser("neighbours")
    near.add_argument("seed", help="the seed song's path, as Kodi stores it")
    near.add_argument("--count", type=int, default=100)
    near.add_argument("--artist-window", type=int, default=0,
                      help="no artist repeat within this many songs, the seed counted (0: repeats allowed)")
    near.add_argument("--variety", type=int, default=0, help="0: the nearest songs; up to 9: a random choice "
                                                             "reaching further out, spread from near to far")
    commands.add_parser("failures")
    args = parser.parse_args(argv)
    args.data = args.data or os.path.join(args.userdata, "addon_data", ADDON_ID, "soundprint")
    args.model = args.model or os.path.join(args.data, "model")
    return args


def setup(args) -> int:
    """The tool's own environment, so nothing is installed into the listener's Python."""
    import venv

    python = environment_python(args.data)
    if not os.path.isfile(python):
        print(f"making a Python environment in {os.path.dirname(os.path.dirname(python))}", flush=True)
        venv.create(os.path.dirname(os.path.dirname(python)), with_pip=True)
    subprocess.check_call([python, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade",
                           *REQUIREMENTS])
    subprocess.check_call([python, "-m", "soundprint", "--userdata", args.userdata, "--data", args.data,
                           "--model", args.model, "fetch-model"], cwd=ADDON_FOLDER)
    print(f"ready: {python} -m soundprint (run from {ADDON_FOLDER})")
    return 0


def check(args) -> int:
    report, ready = {"python": sys.version.split()[0], "data": args.data, "model_folder": args.model}, True
    for module in ("numpy", "onnxruntime", "av"):
        try:
            report[module] = __import__(module).__version__
        except Exception as exc:
            report[module], ready = f"missing ({exc})", False
    if ready:
        from soundprint import model

        absent = model.missing(args.model)
        report["model"] = "ready" if not absent else f"missing or changed: {', '.join(absent)}"
        ready = not absent
        from soundprint.store import Store

        store = Store(args.data)
        report.update(store.counts())
        store.close()
    report["cpu_threads"] = os.cpu_count()
    report["ready"] = ready
    print(json.dumps(report, indent=1))
    return 0 if ready else 1


def analyse(args) -> int:
    from soundprint import DEFAULT_SNIPPETS, analyse as runner, model, songs

    absent = model.missing(args.model)
    if absent:
        print(f"the model is missing ({', '.join(absent)}): run fetch-model first", file=sys.stderr)
        return 2
    if args.list:
        paths, source = songs.from_list(args.list), args.list
    else:
        source = songs.kodi_database(args.userdata)
        paths = songs.from_kodi(source)
    paths, remote, outside = songs.local(paths, args.folder)
    print(f"{len(paths)} song(s) from {source}; left out: {remote} not local, {outside} outside the folders")
    workers = args.workers or max(1, (os.cpu_count() or 2) // 2)
    status = runner.run(paths, args.data, args.model, args.snippets or DEFAULT_SNIPPETS, workers, args.threads,
                        low=not args.normal_priority, prune=args.prune, limit=args.limit,
                        retry_failed=args.retry_failed, kodi_pid=args.kodi_pid)
    return {"finished": 0, "stopped": 0, "busy": 3}.get(status["state"], 1)


def neighbours(args) -> int:
    import time

    from soundprint import songs
    from soundprint.neighbours import nearest, reach
    from soundprint.store import Store

    started = time.perf_counter()
    try:
        database = songs.kodi_database(args.userdata)
    except FileNotFoundError:
        database = ""
    details = songs.Details(database)
    store = Store(args.data)
    try:
        found, source, left_out = nearest(store, args.seed, args.count, args.model if os.path.isdir(args.model) else "",
                                          details=details, window=args.artist_window, variety=args.variety)
        analysed = store.counts()["analysed"]
        print(json.dumps({"seed": args.seed, "seed_vector": source, "seed_details": list(details(args.seed)),
                          "library": database, "analysed": analysed, "left_out": left_out,
                          "reach": reach(args.count, args.variety, analysed),
                          "seconds": round(time.perf_counter() - started, 2),
                          "songs": [{"path": path, "similarity": round(similarity, 4), "rank": rank,
                                     "artist": details(path)[0], "title": details(path)[1]}
                                    for path, similarity, rank in found]}, ensure_ascii=False))
    finally:
        store.close()
        details.close()
    return 0 if found else 1


def main(argv=None) -> int:
    args = arguments(argv)
    if args.command == "setup":
        return setup(args)
    if args.command == "check":
        return check(args)
    if args.command == "fetch-model":
        from soundprint import model

        model.fetch(args.model)
        return 0
    if args.command == "analyse":
        return analyse(args)
    if args.command == "stop":
        os.makedirs(args.data, exist_ok=True)
        request_stop(args.data)
        return 0
    if args.command == "status":
        status = read_status(args.data)
        if status.get("state") == "running":
            status["alive"] = bool(running(args.data))
        print(json.dumps(status, indent=1))
        return 0
    if args.command == "neighbours":
        return neighbours(args)
    if args.command == "failures":
        from soundprint.store import Store

        store = Store(args.data)
        for path, error in store.failures():
            print(f"{path}\t{error}")
        store.close()
        return 0
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
