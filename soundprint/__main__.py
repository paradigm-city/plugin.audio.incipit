"""python -m soundprint <command>: the sound print tool (run from the add-on's folder, or with it on PYTHONPATH).

  setup         make the tool's own Python environment (<data>/python) with numpy, onnxruntime and av, and
                download the model; needs only a Python 3.9 or later to start with
  check         are numpy, onnxruntime and av there, is the model there, what's stored
  fetch-model   download the DCLAP model (release v1, ~22 MB, AGPL-3.0) into the model folder
  analyse       analyse the library's new and changed songs (resumes where it stopped)
  stop          ask a running analysis to stop
  status        the running or last analysis, as JSON
  neighbours    the songs nearest to a seed by sound, as JSON
  failures      the files that could not be read

The data folder defaults to Kodi's addon_data/plugin.audio.musicip/soundprint; the model lives in its "model"
subfolder unless --model says otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

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
    parser.add_argument("--data", help="data folder (default: <userdata>/addon_data/plugin.audio.musicip/soundprint)")
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
    commands.add_parser("stop")
    commands.add_parser("status")
    near = commands.add_parser("neighbours")
    near.add_argument("seed", help="the seed song's path, as Kodi stores it")
    near.add_argument("--count", type=int, default=100)
    commands.add_parser("failures")
    args = parser.parse_args(argv)
    args.data = args.data or os.path.join(args.userdata, "addon_data", "plugin.audio.musicip", "soundprint")
    args.model = args.model or os.path.join(args.data, "model")
    return args


def environment_python(data: str) -> str:
    folder = os.path.join(data, "python")
    return os.path.join(folder, "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(folder, "bin", "python")


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
                        low=not args.normal_priority, prune=args.prune, limit=args.limit)
    return 0 if status["state"] in ("finished", "stopped") else 1


def neighbours(args) -> int:
    from soundprint.neighbours import nearest
    from soundprint.store import Store

    store = Store(args.data)
    try:
        found, source = nearest(store, args.seed, args.count, args.model if os.path.isdir(args.model) else "")
    finally:
        store.close()
    print(json.dumps({"seed": args.seed, "seed_vector": source,
                      "songs": [{"path": path, "similarity": round(similarity, 4)} for path, similarity in found]},
                     ensure_ascii=False))
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
    from soundprint import analyse as runner

    if args.command == "stop":
        os.makedirs(args.data, exist_ok=True)
        runner.request_stop(args.data)
        return 0
    if args.command == "status":
        print(json.dumps(runner.read_status(args.data), indent=1))
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
