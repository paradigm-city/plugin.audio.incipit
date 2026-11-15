"""Redrawn figures (replacing the first versions in diagrams.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import diagrams as D  # noqa: E402
from draw import BOLD, INK, KINDS, MUTED, REG, SEMI, Canvas  # noqa: E402

P = D.P


def fig_dataflow_mix():
    c = Canvas(1600, 945)
    c.title("Data flow: a new mix", "From the playing song to a checked mix in Kodi's playlist")
    seed = c.box(30, 110, 230, 90, "Playing song", "seed path from the player", "kodi", size=14)
    dlg = c.box(30, 250, 230, 100, "Mix dialog", "size, variety, artist rule, Character, Intent", "user", size=14)
    fm = c.box(330, 170, 260, 110, "fetch_mix", "main.py: parameters, log, seed first", "core", size=14)
    nb = c.box(700, 110, 280, 110, "neighbours", "soundprint process: cosine, draw, rules", "sound", size=14)
    vec = c.box(1060, 90, 260, 90, "vectors.npy / sound.db", None, "store", "store")
    kdb = c.box(1060, 200, 260, 90, "MyMusic*.db", "artist and title per path", "store", "store", size=13)
    cm = c.box(330, 360, 260, 110, "create_current_mix", "file name, sidecar, current_mix.json", "core", size=14)
    m3u = c.box(700, 330, 280, 90, "mix_….m3u + .m3u.json", "track list + sidecar", "store", "store", size=14)
    cur = c.box(700, 440, 280, 70, "current_mix.json", None, "store", "store")
    play = c.box(330, 560, 260, 100, "play_tracks_as_music_playlist", "Kodi playlist, seed first", "core", size=13)
    kp = c.box(30, 560, 230, 100, "Kodi playlist", "plays at once", "kodi", size=14)
    q = c.box(700, 560, 280, 80, "mixassist/queue.json", "tidy-up request", "store", "store", size=13)
    mq = c.box(700, 670, 280, 80, "metadata_refresh_queue.json", None, "store", "store", size=13)
    md = c.box(700, 790, 280, 105, "track_metadata_cache.db", "title, artist, art", "store", "store", size=13)
    svc = c.box(1060, 540, 260, 120, "Service: process_mix_assist_request", "worker thread", "ai", size=14)
    rat = c.box(1370, 450, 200, 90, "ratings.db", "profiles, verdicts", "store", "store", size=14)
    cl = c.box(1370, 600, 200, 90, "Claude CLI", "intent, verdicts, name", "ai", size=14)
    c.connect(seed, "e", fm, "w", fb=0.3)
    c.connect(dlg, "e", fm, "w", fb=0.7)
    c.connect(fm, "e", nb, "w", "seed, size,\nvariety", fa=0.3, fb=0.6)
    c.connect(nb, "e", vec, "w", fa=0.3)
    c.connect(nb, "e", kdb, "w", fa=0.7)
    c.arrow([(840, 220), (840, 258), (590, 258)], "JSON: paths, similarity, rank", dashed=True, lpos=(715, 258))
    c.connect(fm, "s", cm, "n", "track list")
    c.connect(cm, "e", m3u, "w", fa=0.3)
    c.connect(cm, "e", cur, "w", fa=0.7)
    c.connect(cm, "s", play, "n")
    c.connect(play, "w", kp, "e")
    c.connect(play, "e", q, "w", fa=0.3)
    c.connect(play, "e", mq, "w", fa=0.75)
    c.connect(mq, "s", md, "n", "the service, in batches")
    c.connect(q, "e", svc, "w", "next tick", fb=0.5)
    c.connect(svc, "e", rat, "w", fa=0.25, both=True)
    c.connect(svc, "e", cl, "w", fa=0.75, both=True)
    c.arrow([(1190, 540), (1190, 375), (980, 375)], "patched mix,\nhistory, Undo", lpos=(1190, 460))
    c.arrow([(1190, 660), (1190, 920), (145, 920), (145, 660)], "replacements beyond the protected zone", dashed=True, lpos=(500, 920))
    c.save(P("dataflow_mix.png"))


def fig_messaging():
    c = Canvas(1600, 870)
    c.title("Messaging: how the parts talk", "No sockets, no shared memory: URLs, files, Kodi's APIs and child processes")
    kodi = c.box(620, 100, 360, 110, "Kodi", "GUI, player, playlist, JSON-RPC, music DB", "kodi")
    plug = c.box(120, 360, 340, 120, "Plugin  (main.py)", "a new interpreter per URL", "core")
    svc = c.box(1140, 360, 340, 120, "Service  (service.py)", "long-lived loop", "core")
    files = c.box(620, 375, 360, 110, "Profile files", "state, queues, sidecars", "store", "store")
    snd = c.box(120, 690, 340, 110, "Sound engine processes", "neighbours · analyse · setup", "sound")
    cl = c.box(620, 690, 360, 110, "Claude Code CLI", "one process per request", "ai")
    st = c.box(1140, 690, 340, 110, "status.json · stop file", "the running analysis", "store", "store")
    lis = c.box(1365, 100, 50, 90, "Listener", None, "user", "actor")
    c.arrow([(620, 135), (290, 135), (290, 360)], "1  plugin:// URL, RunPlugin (router actions)", lpos=(455, 135))
    c.arrow([(392, 360), (392, 185), (620, 185)], "2  JSON-RPC, xbmc / xbmcgui,\nContainer.Update / Refresh", lpos=(470, 260))
    c.arrow([(900, 210), (900, 290), (1310, 290), (1310, 360)], "3  Player / Monitor callbacks:\nstop, end, scan finished, settings", lpos=(1105, 290))
    c.connect(plug, "e", files, "w", "4  write state,\nqueues", fa=0.6, fb=0.55)
    c.connect(files, "e", svc, "w", "5  read in the next tick,\nwrite back", fa=0.45, fb=0.55, both=True)
    c.connect(plug, "s", snd, "n", "6  command line in,\nJSON out (stdout)", fa=0.3, fb=0.3)
    c.arrow([(392, 480), (392, 630), (760, 630), (760, 690)])
    c.arrow([(1208, 480), (1208, 630), (850, 630), (850, 690)], "7  stdin message + JSON schema → JSON on stdout", lpos=(800, 630))
    c.connect(svc, "s", st, "n", "8  Popen detached;\nread status, write stop", fa=0.75, fb=0.75)
    c.arrow([(1208, 640), (1208, 690)], None) if False else None
    c.connect(kodi, "e", lis, "w", "9  notifications, dialogs", fa=0.4)
    c.text(40, 830, "Not a message: the service imports main.py as a module (importlib) and calls its functions directly.", 14, REG, MUTED)
    c.save(P("messaging.png"))


def fig_modules():
    c = Canvas(1600, 860)
    c.title("Internal module dependencies", "Arrows point from the importing module to the imported one")
    pos = {}

    def node(name, x, y, kind, w=160):
        pos[name] = c.box(x, y, w, 46, name, None, kind, tsize=15)

    # entry points
    node("context_radio", 40, 100, "core")
    node("context_mix", 240, 100, "core")
    node("logs", 440, 100, "core", 120)
    node("service", 780, 100, "core")
    node("main", 780, 210, "core")
    # mixassist, layered
    c.group(20, 300, 820, 470, "mixassist", "ai")
    node("assist", 300, 345, "ai")
    for i, n in enumerate(["fit", "checks", "library", "chart"]):
        node(n, 40 + i * 200, 445, "ai")
    for i, n in enumerate(["rating", "cache"]):
        node(n, 240 + i * 200, 545, "ai")
    for i, n in enumerate(["stats", "claude", "dimensions"]):
        node(n, 40 + i * 200, 645, "ai")
    c.text(560, 705, "trace, usage: logging and", 13, REG, MUTED)
    c.text(560, 727, "statistics, used by most", 13, REG, MUTED)
    # soundprint, layered
    c.group(870, 300, 710, 470, "soundprint", "sound")
    node("__main__", 1000, 345, "sound")
    node("client", 1390, 345, "sound")
    for i, n in enumerate(["analyse", "neighbours", "songs"]):
        node(n, 900 + i * 220, 445, "sound")
    for i, n in enumerate(["model", "store", "years", "state"]):
        node(n, 900 + i * 170, 545, "sound", 150)
    node("audio", 900, 645, "sound", 150)
    c.text(1080, 650, "all: the package's constants (soundprint/__init__)", 13, REG, MUTED)

    def edge(a, b, sa="s", sb="n", fa=0.5, fb=0.5, **kw):
        c.connect(pos[a], sa, pos[b], sb, fa=fa, fb=fb, color=(120, 128, 140), width=1.6, **kw)

    edge("context_radio", "context_mix", "e", "w")
    edge("context_mix", "logs", "e", "w")
    edge("service", "logs", "w", "e", fb=0.3)
    edge("main", "logs", "w", "s", fb=0.7)
    edge("service", "main", dashed=True)
    c.label(905, 190, "importlib at run time", 12)
    # main into the packages
    c.arrow([(830, 256), (830, 285), (380, 285), (380, 345)], color=(120, 128, 140), width=1.6)
    c.label(560, 285, "main imports 9 mixassist modules", 12)
    c.arrow([(900, 256), (900, 285), (1450, 285), (1450, 345)], color=(120, 128, 140), width=1.6)
    c.label(1180, 285, "client, years", 12)
    edge("assist", "fit", fb=0.6)
    edge("assist", "checks")
    edge("assist", "rating", fa=0.35)
    edge("assist", "cache", fa=0.65, fb=0.3)
    edge("checks", "rating", fb=0.7)
    edge("library", "cache", fa=0.4, fb=0.7)
    edge("fit", "stats")
    edge("fit", "dimensions", fa=0.8, via=[(168, 520), (590, 520), (590, 645)])
    edge("rating", "claude")
    edge("rating", "dimensions", fa=0.8, fb=0.2)
    edge("cache", "dimensions", fb=0.6)
    edge("__main__", "analyse", fa=0.3)
    edge("__main__", "neighbours")
    edge("__main__", "songs", fa=0.7)
    edge("analyse", "model", fa=0.3)
    edge("analyse", "store", fa=0.6, fb=0.3)
    edge("analyse", "state", fa=0.9, fb=0.2, via=[(1050, 518), (1440, 518), (1440, 545)])
    edge("neighbours", "store", fa=0.3, fb=0.7)
    edge("neighbours", "years", fa=0.7)
    edge("model", "audio")
    edge("client", "state", fb=0.8)
    # the one cross-package edge
    c.arrow([(1258, 591), (1258, 610), (860, 610), (860, 568), (600, 568)], color=KINDS["warn"][1], width=2)
    c.label(1000, 610, "artist_key, is_compilation", 12, KINDS["warn"][1])
    c.legend_row(40, 800, [("core", "entry points"), ("ai", "mixassist (Kodi's Python)"),
                           ("sound", "soundprint (own Python; client and years also in Kodi's)")])
    c.line([(1000, 808), (1040, 808)], KINDS["warn"][1], 2)
    c.text(1050, 798, "the only edge between the packages", 14)
    c.save(P("modules.png"))


D.fig_dataflow_mix, D.fig_messaging, D.fig_modules = fig_dataflow_mix, fig_messaging, fig_modules

if __name__ == "__main__":
    names = sys.argv[1:]
    for name in names:
        getattr(D, name)()
        print("ok", name)
