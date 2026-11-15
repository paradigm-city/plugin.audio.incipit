"""All figures of the Incipit documentation, drawn with draw.py into figs/."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from draw import (BOLD, INK, KINDS, LINE, MONO, MUTED, REG, SEMI, WHITE, Canvas, Chart, sequence)  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figs")
os.makedirs(OUT, exist_ok=True)
DATA = np.load(os.path.join(HERE, "figdata.npz"))


def P(name):
    return os.path.join(OUT, name)


# ------------------------------------------------------------------------------------------------------------------
def fig_context():
    c = Canvas(1600, 900)
    c.title("System context", "Who and what Incipit works with")
    lis = c.box(45, 125, 110, 100, "Listener", kind="user", shape="actor")
    c.group(190, 90, 380, 580, "Kodi 21 (Omega)", "kodi")
    gui = c.box(210, 135, 340, 80, "GUI, skin and windows", "menus, dialogs, information window", "kodi")
    c.box(210, 235, 340, 60, "Settings, keymaps", None, "kodi")
    rpc = c.box(210, 315, 340, 80, "JSON-RPC API", "AudioLibrary, Player, Playlist, Files", "kodi")
    ply = c.box(210, 420, 340, 80, "Player and music playlist", "plays files, reports events", "kodi")
    db = c.box(210, 530, 340, 110, "Music library", "MyMusic*.db (SQLite): songs, albums, paths", "store", "store")
    c.group(640, 90, 380, 580, "Incipit add-on (Kodi's Python 3.8)", "core")
    plug = c.box(660, 135, 340, 120, "Plugin  (main.py)", "menus, mixes, Radio and Discovery actions, information", "core")
    svc = c.box(660, 285, 340, 130, "Service  (service.py)", "background loop: radio refills, Discovery, checks, analysis start, repair", "core")
    ctx = c.box(660, 440, 340, 75, "Context menu entries", "context_mix.py, context_radio.py", "core")
    pkg = c.box(660, 535, 340, 115, "Packages", "mixassist (Character and Intent), soundprint.client (the sound engine's Kodi side)", "ai")
    snd = c.box(1100, 135, 460, 130, "Sound engine  (python -m soundprint)", "own Python environment: numpy, onnxruntime, PyAV; DCLAP model; separate processes", "sound")
    gh = c.box(1100, 305, 220, 90, "GitHub", "DCLAP model release (set-up only)", "ext")
    pypi = c.box(1340, 305, 220, 90, "PyPI", "numpy, onnxruntime, PyAV (set-up only)", "ext")
    cli = c.box(1100, 450, 460, 80, "Claude Code CLI", "claude -p, structured output, no tools", "ai")
    cla = c.box(1100, 575, 460, 70, "Claude (Anthropic), the listener's subscription", None, "ext")
    data = c.box(210, 760, 810, 110, "Add-on data folder  (userdata/addon_data/plugin.audio.incipit)",
                 "mixes (.m3u + sidecar JSON), state JSON, ratings.db, usage.db, track metadata cache, soundprint/sound.db, vectors.npy", "store", "store")
    files = c.box(1100, 760, 460, 110, "Music files", "local or mapped drives", "store", "store")
    c.connect(lis, "e", gui, "w", "browse, play", fa=0.45)
    c.connect(gui, "e", plug, "w", "plugin:// URL", fb=0.33)
    c.connect(rpc, "e", svc, "w", "JSON-RPC calls", fa=0.5, fb=0.53, both=True)
    c.connect(ply, "e", svc, "w", "Player and Monitor events", via=[(610, 460), (610, 390)], fb=0.82)
    c.connect(ctx, "n", svc, "s", "runs a plugin URL", dashed=True)
    c.connect(plug, "e", snd, "w", "neighbours (JSON)", fa=0.3, fb=0.27)
    c.connect(svc, "e", snd, "w", "start analysis", fa=0.2, via=[(1050, 311), (1050, 215)], fb=0.62)
    c.arrow([(1100, 245), (1075, 245), (1075, 705), (380, 705), (380, 640)], "reads Kodi's music library (read-only)", dashed=True, lpos=(760, 705))
    c.arrow([(1560, 200), (1585, 200), (1585, 815), (1560, 815)], "decodes\nsnippets", lpos=(1540, 700))
    c.connect(snd, "s", gh, "n", dashed=True, fa=0.24, fb=0.5)
    c.connect(snd, "s", pypi, "n", dashed=True, fa=0.76, fb=0.5)
    c.connect(pkg, "e", cli, "w", "requests", fa=0.3, via=[(1060, 570), (1060, 490)])
    c.connect(cli, "s", cla, "n", both=True)
    c.connect(pkg, "s", data, "n", "reads and writes", fb=0.78)
    c.save(P("context.png"))


def fig_three_steps():
    c = Canvas(1600, 470)
    c.title("A mix in three steps", "The seed song (the incipit) carries what the mix is about")
    seed = c.box(30, 150, 200, 190, "Seed song", "the playing song, a library song, a Discovery snippet or a Radio pick", "user")
    steps = [
        ("1  Source", "The sound engine: songs nearest to the seed by sound. Variety 0–9 sets how far it reaches; no artist repeat within N.", "sound", 140, "always on"),
        ("2  Character", "Each song's 8-value profile against the seed's. Tolerance: Focused … Adventurous.", "ai", 120, "can be off"),
        ("3  Intent", "Claude states what the seed is about from a perspective and judges every song.", "ai", 100, "can be off"),
    ]
    x = 290
    prev = seed
    for title, text, kind, h, note in steps:
        bh = h + 110
        b = c.box(x, 245 - bh / 2, 300, bh, title, text, kind)
        c.text(x + 150, 245 + bh / 2 + 10, note, 14, SEMI, MUTED, "ma")
        c.connect(prev, "e", b, "w")
        prev = b
        x += 360
    mix = c.box(x, 170, 200, 150, "The mix or station", "plays at once; checks run in the background", "core")
    c.connect(prev, "e", mix, "w")
    c.text(800, 430, "A new song must pass every check that is on.  A track leaves a mix only when every check that is on turns it down.", 15, SEMI, INK, "ma")
    c.save(P("three_steps.png"))


def fig_pipeline():
    c = Canvas(1600, 640)
    c.title("From a music file to a sound print", "soundprint/audio.py, model.py, analyse.py, store.py")
    rows = [
        [("Audio file", "MP3, FLAC, …; any format FFmpeg reads", "store", "store"),
         ("Decode", "PyAV / FFmpeg; reopened after an ID3 tag if needed; damaged frames left out", "sound", "round"),
         ("Mono, 48 kHz", "mean of all channels, resampled, clipped and rounded to 16 bits", "sound", "round"),
         ("6 snippets × 10 s", "centred at (i + ½)/6 of the song; 1 s pre-roll decoded and dropped; silent ones left out", "sound", "round")],
        [("STFT", "Hann window 2048, hop 480 (10 ms), mirrored edges", "sound", "round"),
         ("Mel filterbank", "128 Slaney bands, 0–14 kHz", "sound", "round"),
         ("Power in dB", "10·log10(max(mel, 1e-10)) → 128 × 1001 image", "sound", "round"),
         ("DCLAP (ONNX)", "distilled CLAP audio encoder → 512 numbers per snippet", "ai", "round")],
        [("Mean of snippets", "one 512-value vector per song", "sound", "round"),
         ("Normalise", "scaled to length 1 (L2)", "sound", "round"),
         ("sound.db", "one row per file: float16 vector (1 KB), size, mtime, version", "store", "store"),
         ("vectors.npy", "all vectors as one float32 matrix for the search", "store", "store")],
    ]
    boxes = []
    for r, row in enumerate(rows):
        y = 100 + r * 175
        line = []
        for i, (t, s, kind, shape) in enumerate(row):
            b = c.box(40 + i * 395, y, 330, 120, t, s, kind, shape, size=14)
            line.append(b)
        for a, b in zip(line, line[1:]):
            c.connect(a, "e", b, "w")
        boxes.append(line)
    c.arrow([boxes[0][3].s, (boxes[0][3].s[0], 250), (boxes[1][0].n[0], 250), boxes[1][0].n], "480,000 samples per snippet", lpos=(800, 250))
    c.arrow([boxes[1][3].s, (boxes[1][3].s[0], 425), (boxes[2][0].n[0], 425), boxes[2][0].n], "six vectors of 512", lpos=(800, 425))
    c.save(P("pipeline.png"))


def fig_snippets():
    length = float(DATA["length"])
    starts = DATA["starts"]
    c = Canvas(1600, 330)
    c.title("Where the six snippets sit", f"Kraftwerk, \"Vitamin\" ({length:.0f} s): snippet i is centred at (i + ½)/6 of the song")
    x0, x1, y = 60, 1540, 170
    scale = (x1 - x0) / length
    c.rect(x0, y, x1 - x0, 40, (243, 244, 246), (156, 163, 175), 1.5, radius=4)
    for i, s in enumerate(starts):
        pre = max(0.0, s - 1.0)
        c.rect(x0 + pre * scale, y - 12, (s - pre) * scale, 64, (254, 215, 170), None)
        c.rect(x0 + s * scale, y - 12, 10 * scale, 64, KINDS["sound"][0], KINDS["sound"][1], 2, radius=3)
        c.text(x0 + (s + 5) * scale, y - 40, f"#{i + 1}", 15, SEMI, INK, "ma")
        centre = (i + 0.5) / 6 * length
        c.line([(x0 + centre * scale, y + 58), (x0 + centre * scale, y + 70)], MUTED, 1.5)
    for t in range(0, int(length) + 1, 60):
        c.text(x0 + t * scale, y + 74, f"{t // 60}:{t % 60:02d}", 13, REG, MUTED, "ma")
    c.rect(60, 285, 22, 14, (254, 215, 170), None)
    c.text(90, 281, "1 s pre-roll: decoded, then dropped (the first frames after a seek are garbled)", 14)
    c.rect(820, 285, 22, 14, KINDS["sound"][0], KINDS["sound"][1], 1.5)
    c.text(850, 281, "10 s window: the model's input (480,000 samples at 48 kHz)", 14)
    c.save(P("snippets.png"))


def fig_filterbank():
    filt = DATA["filters"]  # 128 x 1025
    c = Canvas(1600, 600)
    c.title("The mel filterbank", "128 triangular bands (Slaney's scale): narrow and dense in the low frequencies, wide in the high ones")
    ch = Chart(c, 110, 110, 1420, 360, (0, 15000), (0, 1.08))
    ch.axes([0, 1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000], [], "frequency (Hz)", "",
            fmt_x=lambda v: f"{v // 1000} k" if v else "0")
    filt = filt / np.maximum(filt.max(axis=1, keepdims=True), 1e-12)  # each band drawn to the same height
    freqs = np.linspace(0, 24000, filt.shape[1])
    keep = freqs <= 15000
    for i in range(0, 128):
        t = i / 127
        color = (int(30 + 200 * t), int(110 - 40 * t), int(200 - 150 * t))
        row = filt[i]
        nz = np.nonzero(row)[0]
        if not len(nz):
            continue
        a, b = max(0, nz[0] - 1), min(len(row) - 1, nz[-1] + 1)
        ch.series(freqs[a:b + 1], row[a:b + 1], color, 1.6)
    c.text(110, 545, "Each band adds up the power of the FFT bins under its triangle (drawn here to equal height; in the "
                     "model each band has the same area, so wide bands are lower).", 14, REG, MUTED)
    c.save(P("filterbank.png"))


def colormap(v):
    # a perceptual dark-to-bright ramp (magma-like), v in 0..1
    stops = [(0.0, (0, 0, 4)), (0.25, (80, 18, 123)), (0.5, (182, 54, 121)), (0.75, (251, 136, 97)), (1.0, (252, 253, 191))]
    v = np.clip(v, 0, 1)
    out = np.zeros(v.shape + (3,))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        m = (v >= a) & (v <= b)
        t = (v[m] - a) / (b - a)
        for k in range(3):
            out[..., k][m] = ca[k] + (cb[k] - ca[k]) * t
    return out.astype(np.uint8)


def fig_spectrogram():
    from PIL import Image
    mel = DATA["mel"]  # 128 x 1001, dB
    wave = DATA["wave"]
    c = Canvas(1600, 760)
    c.title("One snippet as the model sees it", "Kraftwerk, \"Vitamin\", snippet 3: waveform (top) and log-mel spectrogram (bottom), 10 s")
    # waveform
    x, w = 110, 1400
    ch = Chart(c, x, 100, w, 130, (0, len(wave)), (-1, 1))
    ch.axes([], [-1, 0, 1], "", "amplitude", grid=True)
    n = len(wave)
    cols = 1400
    step = n // cols
    env = wave[:step * cols].reshape(cols, step)
    lo, hi = env.min(axis=1), env.max(axis=1)
    for i in range(cols):
        c.line([(x + i * w / cols, ch.py(lo[i])), (x + i * w / cols, ch.py(hi[i]))], (78, 138, 30), 1)
    # spectrogram
    lo_db, hi_db = np.percentile(mel, 1), mel.max()
    norm = (mel - lo_db) / (hi_db - lo_db)
    rgb = colormap(norm[::-1])
    img = Image.fromarray(rgb).resize((int(w * c.k), int(360 * c.k)), Image.BICUBIC)
    top = 280
    c.img.paste(img, (int(x * c.k), int(top * c.k)))
    c.rect(x, top, w, 360, None, LINE, 1.5)
    # y ticks: mel band -> Hz (approximate from filter centres)
    filt = DATA["filters"]
    freqs = np.linspace(0, 24000, filt.shape[1])
    centres = (filt * freqs).sum(axis=1) / np.maximum(filt.sum(axis=1), 1e-12)
    for band in (0, 32, 64, 96, 127):
        yy = top + 360 - band / 127 * 360
        hz = centres[band]
        c.text(x - 8, yy, f"{hz / 1000:.1f} kHz" if hz >= 1000 else f"{hz:.0f} Hz", 13, REG, MUTED, "rm")
    for s in range(0, 11, 2):
        c.text(x + s / 10 * w, top + 368, f"{s} s", 13, REG, MUTED, "ma")
    c.text(x - 100, top - 26, "mel band (centre)", 14, SEMI, INK)
    # colour bar
    bar = np.linspace(0, 1, 300)[None, :].repeat(14, axis=0)
    bimg = Image.fromarray(colormap(bar)).resize((int(400 * c.k), int(14 * c.k)))
    c.img.paste(bimg, (int(x * c.k), int((top + 410) * c.k)))
    c.text(x, top + 430, f"{lo_db:.0f} dB", 13, REG, MUTED)
    c.text(x + 400, top + 430, f"{hi_db:.0f} dB", 13, REG, MUTED, "ra")
    c.text(x + 430, top + 406, "128 × 1001 values: 128 mel bands × 1,001 frames of 10 ms. This image is the input of the "
                             "neural network.", 14, REG, INK)
    c.save(P("spectrogram.png"))


def fig_cosine():
    c = Canvas(1600, 470)
    c.title("Similarity as an angle", "Every song is an arrow of length 1 in a 512-dimensional space; drawn here in 2 dimensions")
    ox, oy, r = 260, 400, 300
    c.line([(ox - 20, oy), (ox + 340, oy)], (209, 213, 219), 1.5)
    c.line([(ox, oy + 20), (ox, oy - 330)], (209, 213, 219), 1.5)
    vecs = [(70, "seed", KINDS["user"][1]), (58, "similar song  cos ≈ 0.98", KINDS["sound"][1]),
            (20, "different song  cos ≈ 0.64", KINDS["ext"][1])]
    for ang, name, col in vecs:
        a = math.radians(ang)
        tip = (ox + r * math.cos(a), oy - r * math.sin(a))
        c.arrow([(ox, oy), tip], color=col, width=3)
        c.text(tip[0] + 10, tip[1] - 10, name, 15, SEMI, col)
    a0, a1 = 58, 70
    k = c.k
    c.d.arc([(ox - 120) * k, (oy - 120) * k, (ox + 120) * k, (oy + 120) * k], -a1, -a0, fill=MUTED, width=int(2 * k))
    c.text(ox + 60, oy - 140, "θ", 18, SEMI, MUTED)
    tx = 760
    c.text(tx, 110, "cosine similarity", 20, BOLD, INK)
    c.text(tx, 150, "cos θ = (a · b) / (|a| |b|)  =  a · b   (both have length 1)", 18, MONO, INK)
    c.textblock(tx, 200, 780,
                "1.0: the same direction (the same recording). 0: unrelated. The search computes one dot product per "
                "song: the whole library at once as a matrix–vector product (156,000 × 512), about a second on a "
                "4-core PC. The nearest songs are those with the largest cosine. Measured on this library: two copies of "
                "one recording reach 0.994 to 0.9997; the nearest other song to Kraftwerk's \"Vitamin\" 0.91.", 16)
    c.save(P("cosine.png"))


def fig_similarity():
    sim = DATA["sim"]
    reaches = DATA["reaches"]
    n = len(sim)
    c = Canvas(1600, 640)
    c.title("How far a mix reaches", "Similarity of every song in the library to Kraftwerk's \"Vitamin\", sorted (log scale), "
                                     "and how deep a mix of 25 draws at each variety")
    ch = Chart(c, 120, 110, 1380, 400, (1, n), (-0.1, 1.0), logx=True)
    ch.axes([1, 10, 100, 1000, 10000, 100000], [0, 0.2, 0.4, 0.6, 0.8, 1.0], "rank of the song in the order by sound",
            "cosine similarity", fmt_x=lambda v: f"{v:,}")
    ranks = np.unique(np.round(np.logspace(0, math.log10(n), 600)).astype(int))
    ch.series(ranks, sim[ranks - 1], KINDS["sound"][1], 3)
    for v in (0, 1, 3, 5, 7, 9):
        rr = int(reaches[v])
        xx = ch.px(rr)
        c.dline([(xx, ch.y), (xx, ch.y + ch.h)], KINDS["ai"][1], 1.5, 5, 5)
        c.label(xx, ch.y + 12 + (v % 2) * 22, f"variety {v}: {rr:,}", 12, KINDS["ai"][1])
    c.text(120, 590, "The mix draws its songs from the nearest \"reach\" songs; the line marks that depth. "
                     "At variety 9 every song of the library can be drawn.", 14, REG, MUTED)
    c.save(P("similarity.png"))


def fig_variety():
    reaches = DATA["reaches"]
    powers = DATA["powers"]
    c = Canvas(1600, 600)
    c.title("Where the songs of a mix come from", "Chance that a draw lands within the nearest r songs, mix of 25 "
                                                  "(weight 1 / rank^p over the reach)")
    n = int(reaches[9])
    ch = Chart(c, 120, 110, 1000, 380, (1, n), (0, 1.0), logx=True)
    ch.axes([1, 10, 100, 1000, 10000, 100000], [0, 0.25, 0.5, 0.75, 1.0], "rank r", "share of draws",
            fmt_x=lambda v: f"{v:,}", fmt_y=lambda v: f"{int(v * 100)} %")
    colours = {0: (19, 138, 114), 3: (59, 111, 216), 6: (199, 124, 2), 9: (190, 24, 93)}
    for v, col in colours.items():
        reach, p = int(reaches[v]), float(powers[v])
        r = np.arange(1, reach + 1, dtype=np.float64)
        w = 1 / r ** p
        cum = np.cumsum(w) / w.sum()
        xs = np.unique(np.round(np.logspace(0, math.log10(reach), 300)).astype(int))
        ch.series(xs, cum[xs - 1], col, 3)
        c.text(ch.px(reach) + 6, ch.py(1.0) - 4 - list(colours).index(v) * 0, "", 12)
    lx = 1160
    c.text(lx, 120, "variety  reach  power p", 15, BOLD, INK)
    for i, v in enumerate(range(10)):
        col = colours.get(v, INK)
        c.text(lx, 150 + i * 30, f"{v}", 15, SEMI if v in colours else REG, col)
        c.text(lx + 150, 150 + i * 30, f"{int(reaches[v]):,}", 15, SEMI if v in colours else REG, col, "ra")
        c.text(lx + 250, 150 + i * 30, f"{float(powers[v]):.2f}", 15, SEMI if v in colours else REG, col, "ra")
    c.text(120, 540, "At variety 0 every song comes from the nearest 38. At 9 half of the draws land beyond rank 20,000: "
                     "near and far songs alternate.", 14, REG, MUTED)
    c.save(P("variety.png"))


def fig_character():
    c = Canvas(1600, 700)
    c.title("Character: is a song's profile close enough to the seed's?", "mixassist/assist.py (analyze, character_scale, passes) and fit.py")
    inp = [("Seed profile", "8 values from ratings.db"),
           ("Library ratings", "all rated albums: averages, spreads, correlations"),
           ("Nearest 120 by sound", "rated ones (up to 35): the fixed scale")]
    bs = []
    for i, (t, s) in enumerate(inp):
        bs.append(c.box(40, 100 + i * 200, 300, 120, t, s, "store", "store", size=14))
    w1 = c.box(420, 100, 330, 120, "Seed weights", "how unusual the seed is per value: |seed − mean| / sd, scaled to average 1", "ai", size=14)
    w2 = c.box(420, 300, 330, 120, "Spreads", "robust spread (1.4826 × MAD) of the scale songs, floor 1 point / 5 years, divided by the weight", "ai", size=14)
    w3 = c.box(420, 500, 330, 120, "Correlation", "library correlations, shrunk 30 % towards independence, inverted", "ai", size=14)
    cand = c.box(830, 95, 330, 100, "Candidate profile", "8 values from ratings.db", "store", "store", size=14)
    m = c.box(830, 260, 330, 160, "Misfit", "deviations z = (song − seed) / weighted spread; misfit = √(zᵀ R⁻¹ z / 8)", "ai", size=14)
    rel = c.box(830, 470, 330, 110, "Relative misfit", "misfit / typical misfit of the scale songs (≥ 1)", "ai", size=14)
    dec = c.box(1215, 200, 370, 300, "Pass?", "relative ≤ tolerance (1.0 to 1.5) and no single value off by ≥ 5 points (25 years)", "warn", "diamond", size=13)
    c.box(1230, 570, 330, 100, "Emotional perspective", "leaves production out of the profile (7 values)", "note", size=14)
    c.connect(bs[0], "e", w1, "w")
    c.connect(bs[1], "e", w1, "w", fa=0.3, fb=0.8)
    c.connect(bs[1], "e", w3, "w", fa=0.7, fb=0.3)
    c.connect(bs[2], "e", w2, "w", fa=0.3, fb=0.6)
    c.connect(w1, "e", m, "w", fb=0.15)
    c.connect(w2, "e", m, "w", fb=0.6)
    c.connect(w3, "e", m, "w", fb=0.9)
    c.connect(cand, "s", m, "n")
    c.connect(m, "s", rel, "n")
    c.connect(rel, "e", dec, "s")
    c.connect(m, "e", dec, "w", "single-value rule", fa=0.3)
    c.save(P("character.png"))


def fig_ai():
    c = Canvas(1600, 760)
    c.title("Intent and the ratings: how the add-on asks Claude", "mixassist/library.py, rating.py, checks.py, claude.py, cache.py")
    paths = c.box(30, 110, 250, 100, "Song paths", "the seed and the candidates", "core")
    units = c.box(340, 110, 270, 100, "Units", "an album, or a track from a compilation (library.resolve)", "ai", size=14)
    cache = c.box(680, 100, 260, 120, "ratings.db", "units: 8 values, familiarity, description, prompt version", "store", "store", size=14)
    rate = c.box(680, 280, 260, 120, "Rate missing", "20 albums or 25 tracks per request; values clamped (rating.py)", "ai", size=14)
    cli = c.box(1030, 280, 250, 120, "Claude Code CLI", "claude -p, JSON schema, no tools, lean start", "ai", size=14)
    claude = c.box(1350, 280, 220, 120, "Claude", "subscription; model and effort from the settings", "ext", size=14)
    seedp = c.box(30, 470, 300, 140, "Describe (seed-intent)", "states the seed's intent from the perspective, judges each track, may name the mix", "ai", size=14)
    judge = c.box(380, 470, 300, 140, "Judge (intent check)", "judges tracks against an intent already stated or edited by the listener", "ai", size=14)
    persp = c.box(30, 650, 650, 80, "Perspective", "Mixed · Technical · Emotional · Cultural · Functional · Lyrical · Epoch", "note", size=14)
    verd = c.box(780, 480, 300, 120, "Verdicts", "fits · borderline · outlier, each with a reason; a name of 2–4 words", "core", size=14)
    vc = c.box(1150, 480, 280, 120, "Verdict cache", "keyed by model, prompt, intent, seed line, track line (ratings.db)", "store", "store", size=14)
    use = c.box(1150, 640, 280, 90, "usage.db", "every request: tokens, time, cost", "store", "store", size=14)
    c.connect(paths, "e", units, "w")
    c.connect(units, "e", cache, "w", "look up")
    c.connect(cache, "s", rate, "n", "missing")
    c.connect(rate, "e", cli, "w")
    c.connect(cli, "e", claude, "w", both=True)
    c.connect(rate, "e", cache, "e", "store", via=[(970, 340), (970, 160)], fa=0.5)
    c.connect(units, "s", seedp, "n", "profiles and descriptions", fb=0.6)
    c.connect(units, "s", judge, "n", fb=0.5)
    c.arrow([(285, 470), (285, 435), (1100, 435), (1100, 400)], "requests", lpos=(860, 435))
    c.line([(635, 470), (635, 435)])
    c.connect(judge, "e", verd, "w")
    c.connect(cli, "s", verd, "n", fa=0.7, fb=0.8, via=[(1205, 455), (1020, 455)])
    c.connect(verd, "e", vc, "w", "kept")
    c.connect(cli, "e", use, "e", dashed=True, fa=0.85, via=[(1300, 382), (1300, 420), (1585, 420), (1585, 685)])
    c.save(P("ai_flow.png"))


def fig_components():
    c = Canvas(1600, 960)
    c.title("Components and layers", "The add-on's code by layer; arrows point from user to used")
    c.group(30, 85, 1540, 120, "Kodi", "kodi")
    for i, (t, s) in enumerate([("Skin and windows", "Container, ListItem, info window"), ("Settings UI", "resources/settings.xml"),
                                ("Player, playlist", "xbmc.Player, Monitor"), ("JSON-RPC", "AudioLibrary, Player, …"),
                                ("Music library", "MyMusic*.db")]):
        c.box(50 + i * 304, 120, 284, 70, t, s, "kodi", size=13, tsize=16)
    c.group(30, 230, 1540, 175, "Entry points (run by Kodi, Kodi's Python)", "core")
    ep = [("main.py  ·  plugin", "router(): 54 actions; menus, mixes, Radio, Discovery, information, repair  (9,672 lines)"),
          ("service.py  ·  service", "main(): 1-second loop; Radio, Discovery, checks worker, analysis start, consistency; imports main.py at run time  (3,392 lines)"),
          ("context_mix.py, context_radio.py", "library context menu: Create Incipit mix, Start Incipit radio"),
          ("logs.py", "logging by area, the add-on ID")]
    eb = []
    widths = [440, 440, 320, 230]
    x = 50
    for (t, s), w in zip(ep, widths):
        eb.append(c.box(x, 265, w, 120, t, s, "core", size=13, tsize=16))
        x += w + 20
    c.group(30, 430, 760, 260, "mixassist  ·  Character and Intent (no Kodi imports)", "ai")
    mods = [("assist", "tidy-up, drift"), ("checks", "prompts, perspectives"), ("claude", "CLI calls"),
            ("rating", "rate missing units"), ("cache", "ratings.db, verdicts"), ("dimensions", "the 8 values"),
            ("fit", "misfit maths"), ("stats", "median, MAD, inverse"), ("library", "paths → units"),
            ("chart", "PNG charts"), ("usage", "usage.db"), ("trace", "AI log")]
    for i, (t, s) in enumerate(mods):
        c.box(50 + (i % 4) * 183, 468 + (i // 4) * 72, 170, 64, t, s, "ai", size=12, tsize=14)
    c.group(810, 430, 760, 260, "soundprint  ·  the sound engine (own Python: numpy, onnxruntime, PyAV)", "sound")
    smods = [("__main__", "CLI commands"), ("analyse", "worker pool"), ("audio", "decode, snippets"), ("model", "mel, DCLAP"),
             ("neighbours", "search, variety"), ("store", "sound.db, matrix"), ("songs", "Kodi's song list"), ("years", "a year per song"),
             ("state", "status, stop, priority"), ("client", "Kodi's side")]
    for i, (t, s) in enumerate(smods):
        c.box(830 + (i % 4) * 183, 468 + (i // 4) * 72, 170, 64, t, s, "sound", size=12, tsize=14)
    c.group(30, 715, 760, 110, "Resources", "ext")
    for i, t in enumerate(["settings.xml", "strings.po", "keymap XML", "info window skin XML", "icons"]):
        c.box(50 + i * 146, 755, 136, 50, t, None, "ext", tsize=13)
    c.group(810, 715, 760, 110, "Dormant and tools", "ext")
    c.box(830, 755, 340, 50, "musicip_dormant.py", "MusicIP's code, unused", "ext", size=12, tsize=14)
    c.box(1190, 755, 360, 50, "tools/", "icons, settings.xml generator", "ext", size=12, tsize=14)
    c.group(30, 845, 1540, 95, "Storage (add-on data folder)", "store")
    for i, t in enumerate(["mix_*.m3u + .json", "state JSON files", "ratings.db", "usage.db", "track_metadata_cache.db", "sound.db + vectors.npy", "years.pickle"]):
        c.box(50 + i * 216, 880, 200, 46, t, None, "store", tsize=13)
    c.arrow([(275, 265), (275, 205)])
    c.arrow([(725, 265), (725, 205)])
    c.arrow([(275, 385), (275, 430)])
    c.arrow([(450, 385), (450, 412), (1000, 412), (1000, 430)], "soundprint.client, soundprint.years", lpos=(820, 412))
    c.save(P("components.png"))


def fig_runtime():
    c = Canvas(1600, 800)
    c.title("Processes and threads at run time", "What runs where, and how long")
    c.group(30, 90, 900, 680, "Kodi process", "kodi")
    for i in range(3):
        c.box(60 + i * 12, 140 + i * 12, 380, 150, None, None, "core")
    c.box(84, 164, 380, 150, "Plugin invocation", "one Python interpreter per call: parse URL → router() → listing or action → ends. Short-lived; Kodi may run several.", "core", size=14)
    c.box(500, 140, 400, 300, None, None, "core")
    c.text(520, 150, "Service (lives as long as Kodi)", 16, SEMI, INK)
    c.box(520, 190, 360, 80, "Main loop", "a tick every second (waitForAbort(1))", "core", size=13)
    c.box(520, 285, 170, 70, "Checks worker", "a thread per tidy-up", "ai", size=12, tsize=14)
    c.box(710, 285, 170, 70, "Radio check", "a thread per check", "ai", size=12, tsize=14)
    c.box(520, 370, 360, 55, "Player / Monitor callbacks", None, "kodi", tsize=14)
    c.box(60, 480, 400, 110, "Context menu script", "context_mix.py / context_radio.py: runs the plugin URL and ends", "core", size=14)
    c.box(500, 480, 400, 110, "Kodi's own threads", "GUI, player, library scan, JSON-RPC server", "kodi", size=14)
    c.box(60, 620, 840, 120, "Shared through files and Kodi", "the plugin and the service never call each other directly: state JSON files, queue files, Kodi's playlist and JSON-RPC, Container.Refresh. The service imports main.py as a module for shared logic.", "note", size=14)
    nb = c.box(990, 120, 570, 120, "soundprint neighbours", "one process per mix or refill, normal priority; ~1 s search (up to 4 s after many new songs); JSON on stdout", "sound", size=14)
    an = c.box(990, 280, 570, 150, "soundprint analyse", "detached, below-normal CPU and very low I/O priority; pool of worker processes (CPU threads / 2), each with its own ONNX model; ~0.4 s per song; follows Kodi's process and stops when Kodi closes", "sound", size=14)
    st = c.box(990, 470, 570, 90, "soundprint setup", "once, from Settings (the plugin): makes the environment with the listener's Python, downloads the model", "sound", size=14)
    cl = c.box(990, 600, 570, 120, "claude -p", "one process per AI request, no console window, API keys removed from its environment; 10–17 s per request", "ai", size=14)
    c.arrow([(274, 164), (274, 120), (960, 120), (960, 160), (990, 160)], "plugin: subprocess.run (a mix)", lpos=(620, 120))
    c.arrow([(900, 200), (990, 200)])
    c.arrow([(900, 330), (990, 330)], "Popen\n(detached)", lpos=(945, 300))
    c.arrow([(900, 410), (945, 410), (945, 660), (990, 660)], "subprocess.run", lpos=(945, 600))
    c.save(P("runtime.png"))


def fig_service_loop():
    c = Canvas(1600, 480)
    c.title("One tick of the service loop", "service.main(): each step in its own try/except, so one failing area doesn't stop the others")
    steps = [("Metadata view refresh", "on selection change"), ("Discovery tick", "excerpt timer, buffer"),
             ("Radio tick", "follow, refill, stop"), ("Screens", "redraw on play change"),
             ("Checks tick", "pop queue → worker"), ("Collage tick", "one mix per 15 s"),
             ("Library tick", "analysis due?"), ("Metadata refresh", "interval"), ("Consistency check", "interval, repair")]
    bs = []
    for i, (t, s) in enumerate(steps):
        r, col = divmod(i, 5)
        x = 40 + col * 300
        y = 110 + r * 180
        bs.append(c.box(x, y, 250, 110, t, s, "core" if i not in (4,) else "ai", size=14))
    for a, b in zip(bs, bs[1:]):
        if a.y == b.y:
            c.connect(a, "e", b, "w")
        else:
            c.arrow([a.s, (a.s[0], 255), (b.n[0], 255), b.n])
    wait = c.box(1240, 290, 300, 110, "waitForAbort(1 s)", "Kodi closing ends the loop; Discovery is stopped", "kodi", size=14)
    c.connect(bs[-1], "e", wait, "w")
    c.arrow([(1540, 345), (1575, 345), (1575, 80), (20, 80), (20, 165), (40, 165)], "next tick", lpos=(800, 80))
    c.text(40, 440, "At start: take over the old ID's data, migrate settings, install the keymap, reset Discovery and Radio, "
                    "clear an unsaved current mix, prune statistics.", 14, REG, MUTED)
    c.save(P("service_loop.png"))


def fig_dataflow_mix():
    c = Canvas(1600, 820)
    c.title("Data flow: a new mix", "From the playing song to a checked mix in Kodi's playlist")
    seed = c.box(30, 110, 230, 90, "Playing song", "seed path from the player", "kodi", size=14)
    dlg = c.box(30, 250, 230, 100, "Mix dialog", "size, variety, artist rule, Character, Intent", "user", size=14)
    fm = c.box(330, 170, 260, 110, "fetch_mix", "main.py: parameters, log, seed first", "core", size=14)
    nb = c.box(660, 110, 290, 110, "neighbours", "soundprint process: cosine, draw, rules", "sound", size=14)
    vec = c.box(1020, 90, 260, 90, "vectors.npy / sound.db", None, "store", "store")
    kdb = c.box(1020, 200, 260, 90, "MyMusic*.db", "artist and title per path", "store", "store", size=13)
    cm = c.box(330, 360, 260, 110, "create_current_mix", "file name, sidecar, current_mix.json", "core", size=14)
    m3u = c.box(660, 330, 290, 90, "mix_….m3u + .m3u.json", "track list + sidecar", "store", "store", size=14)
    cur = c.box(660, 440, 290, 70, "current_mix.json", None, "store", "store")
    play = c.box(330, 540, 260, 100, "play_tracks_as_music_playlist", "Kodi playlist, seed first", "core", size=13)
    kp = c.box(30, 540, 230, 100, "Kodi playlist", "plays at once", "kodi", size=14)
    q = c.box(660, 560, 290, 80, "mixassist/queue.json", "tidy-up request", "store", "store", size=13)
    mq = c.box(660, 680, 290, 80, "metadata_refresh_queue.json", None, "store", "store", size=13)
    svc = c.box(1020, 520, 260, 120, "Service: process_mix_assist_request", "worker thread", "ai", size=14)
    rat = c.box(1340, 400, 230, 90, "ratings.db", "profiles, verdicts", "store", "store", size=14)
    cl = c.box(1340, 520, 230, 90, "Claude CLI", "intent, verdicts, name", "ai", size=14)
    md = c.box(1020, 690, 260, 90, "track_metadata_cache.db", "title, artist, art", "store", "store", size=13)
    c.connect(seed, "e", fm, "w", fb=0.3)
    c.connect(dlg, "e", fm, "w", fb=0.7)
    c.connect(fm, "e", nb, "w", "seed, count,\nvariety, window", fa=0.3, fb=0.5)
    c.connect(nb, "e", vec, "w", fb=0.5, fa=0.3)
    c.connect(nb, "e", kdb, "w", fa=0.7)
    c.connect(nb, "s", fm, "e", "JSON: paths,\nsimilarity, rank", via=[(805, 260), (590, 260)], fb=0.82, dashed=True)
    c.connect(fm, "s", cm, "n", "track list")
    c.connect(cm, "e", m3u, "w", fb=0.5, fa=0.3)
    c.connect(cm, "e", cur, "w", fa=0.7)
    c.connect(cm, "s", play, "n")
    c.connect(play, "w", kp, "e")
    c.connect(play, "e", q, "w", fa=0.4)
    c.connect(play, "e", mq, "w", fa=0.8)
    c.connect(q, "e", svc, "w", "next tick", fb=0.4)
    c.connect(svc, "e", rat, "w", fa=0.2, both=True)
    c.connect(svc, "e", cl, "w", fa=0.6, both=True)
    c.connect(svc, "n", m3u, "e", "patched mix,\nhistory, Undo", via=[(1150, 375)], fb=0.5)
    c.connect(svc, "w", kp, "s", "replacements beyond the protected zone", via=[(990, 620), (990, 800), (145, 800)], fa=0.8, dashed=True)
    c.connect(mq, "e", md, "w", "service, in batches")
    c.save(P("dataflow_mix.png"))


def fig_messaging():
    c = Canvas(1600, 860)
    c.title("Messaging: how the parts talk", "No sockets, no shared memory: URLs, files, Kodi's APIs and child processes")
    kodi = c.box(620, 100, 360, 110, "Kodi", "GUI, player, playlist, JSON-RPC, music DB", "kodi")
    plug = c.box(120, 360, 340, 120, "Plugin  (main.py)", "a new process per URL", "core")
    svc = c.box(1140, 360, 340, 120, "Service  (service.py)", "long-lived loop", "core")
    files = c.box(620, 380, 360, 110, "Profile files", "state JSON, queues, focus token, sidecars", "store", "store")
    snd = c.box(120, 680, 340, 110, "Sound engine processes", "neighbours · analyse · setup", "sound")
    cl = c.box(620, 680, 360, 110, "Claude Code CLI", "one process per request", "ai")
    st = c.box(1140, 680, 340, 110, "status.json · stop file", "the running analysis", "store", "store")
    lis = c.box(1280, 100, 200, 110, "Listener", None, "user", "actor")
    c.connect(kodi, "w", plug, "n", "1  plugin:// URL, RunPlugin\n(router actions)", fa=0.5)
    c.connect(plug, "e", kodi, "s", "2  JSON-RPC, xbmc / xbmcgui calls,\nContainer.Update / Refresh", via=[(560, 400), (560, 260), (740, 260)], fb=0.33)
    c.connect(kodi, "s", svc, "n", "3  Player / Monitor callbacks:\nstop, end, scan finished, settings", via=[(860, 290), (1310, 290)], fa=0.67)
    c.connect(plug, "e", files, "w", "4  write: radio_mode_state,\ndiscovery state, queues", fa=0.6, fb=0.4)
    c.connect(files, "e", svc, "w", "5  read in the next tick,\nwrite back state", fa=0.4, fb=0.6, both=True)
    c.connect(plug, "s", snd, "n", "6  command line in,\nJSON out (stdout)")
    c.connect(svc, "s", cl, "e", "7  stdin message +\nJSON schema → JSON", via=[(1250, 735)], fb=0.5)
    c.connect(plug, "s", cl, "w", None, via=[(400, 600), (580, 600), (580, 735)], fa=0.83)
    c.connect(svc, "s", st, "n", "8  Popen detached;\nread status, write stop", fa=0.75)
    c.connect(kodi, "e", lis, "w", "9  notifications,\ndialogs, kodi.log", fb=0.4)
    c.text(40, 820, "The service imports main.py as a module (importlib) and calls its functions directly: that is shared code, "
                    "not a message.", 14, REG, MUTED)
    c.save(P("messaging.png"))


def fig_kodi():
    c = Canvas(1600, 780)
    c.title("Kodi integration", "addon.xml declares four extension points; Kodi's Python modules do the rest")
    ax = c.box(40, 120, 300, 520, "addon.xml", "id plugin.audio.incipit, version 1.0.102, requires xbmc.python 3.0.0", "kodi", "doc", size=14)
    eps = [("xbmc.python.pluginsource", "provides audio → main.py", "Music add-ons → Incipit; every menu and action is a plugin:// URL"),
           ("xbmc.service", "→ service.py", "starts with Kodi, ends with Kodi"),
           ("kodi.context.item", "→ context_mix.py, context_radio.py", "\"Create Incipit mix\", \"Start Incipit radio\" on library songs (DBTYPE song)"),
           ("xbmc.addon.metadata", "→ icon.png, summary, description", "licence MIT, platform all")]
    for i, (t, a, s) in enumerate(eps):
        b = c.box(440, 120 + i * 135, 420, 110, t, a, "core", size=14)
        c.connect(ax, "e", b, "w", fa=0.15 + i * 0.23)
        c.box(900, 130 + i * 135, 300, 90, None, s, "note", size=13)
    c.group(1240, 110, 330, 530, "Kodi Python API used", "kodi")
    for i, (t, s) in enumerate([("xbmc", "Player, Monitor, executebuiltin, executeJSONRPC, log"),
                                ("xbmcgui", "ListItem, Dialog, WindowXMLDialog, Window properties"),
                                ("xbmcplugin", "addDirectoryItem, endOfDirectory, setResolvedUrl"),
                                ("xbmcaddon", "Addon, settings, info"),
                                ("xbmcvfs", "translatePath, file tests")]):
        c.box(1260, 150 + i * 96, 290, 82, t, s, "kodi", size=12, tsize=15)
    c.group(40, 665, 1530, 100, "resources/", "ext")
    for i, t in enumerate(["settings.xml (4 categories)", "language strings.po", "keymaps: DEL, m, l, i", "skins/…/script-musicip-info.xml", "media: menu icons"]):
        c.box(60 + i * 300, 708, 285, 46, t, None, "ext", tsize=13)
    c.save(P("kodi.png"))


def fig_states():
    c = Canvas(1600, 640)
    c.title("Radio mode: the station's phases", "radio_mode_state.json, field \"phase\"")
    off = c.box(80, 300, 220, 110, "off", "no station", "ext")
    seek = c.box(640, 140, 260, 120, "seeking", "scanning random snippets (Discovery playback, owner radio)", "kodi", size=14)
    play = c.box(640, 430, 260, 120, "playing", "an endless mix; refills when < 3 songs are left", "core", size=14)
    c.arrow([(300, 330), (470, 330), (470, 200), (640, 200)], "Scan stations", lpos=(555, 200))
    c.arrow([(744, 260), (744, 430)], "Pick this\nstation", lpos=(690, 345))
    c.arrow([(822, 430), (822, 260)], "Scan\nagain", lpos=(865, 345))
    c.arrow([(300, 380), (470, 380), (470, 490), (640, 490)], "Start Incipit radio (library song),\nplay a favourite", lpos=(470, 520))
    c.box(1050, 140, 500, 410, "Ends a station (→ off)", "Stop radio · the player's Stop (after 3 s) · a library song played or queued · a mix of the add-on · other media such as a video · another file playing · Kodi's restart.\n\nPause does not end it.\n\nThe end is recorded as stop_reason: manual_stop, player_stop, external_playback, songs_added, mix_started, other_media, startup_reset.", "note", size=14)
    c.arrow([(900, 520), (1000, 520), (1000, 605), (190, 605), (190, 410)], "any end", lpos=(600, 605))
    c.arrow([(900, 170), (980, 170), (980, 105), (190, 105), (190, 300)], "scan stops", lpos=(600, 105))
    c.save(P("radio_states.png"))


def fig_modules():
    c = Canvas(1600, 900)
    c.title("Internal module dependencies", "Arrows point from the importing module to the imported one (static imports; service → main is dynamic)")
    pos = {}

    def node(name, x, y, kind, w=170):
        pos[name] = c.box(x, y, w, 50, name, None, kind, tsize=15)

    node("context_radio", 40, 100, "core")
    node("context_mix", 40, 200, "core")
    node("service", 640, 100, "core")
    node("main", 640, 250, "core")
    node("logs", 330, 160, "core")
    node("assist", 110, 400, "ai")
    node("checks", 330, 520, "ai")
    node("rating", 110, 640, "ai")
    node("claude", 330, 760, "ai")
    node("cache", 560, 640, "ai")
    node("dimensions", 560, 760, "ai")
    node("fit", 20, 520, "ai", 130)
    node("stats", 20, 760, "ai", 130)
    node("library", 560, 520, "ai")
    node("trace", 780, 700, "ai", 130)
    node("usage", 780, 800, "ai", 130)
    node("chart", 780, 400, "ai", 130)
    node("client", 1000, 400, "sound")
    node("years", 1000, 520, "sound")
    node("state", 1230, 400, "sound")
    node("__main__", 1230, 100, "sound")
    node("analyse", 1420, 200, "sound", 150)
    node("neighbours", 1230, 520, "sound")
    node("store", 1420, 640, "sound", 150)
    node("model", 1420, 400, "sound", 150)
    node("audio", 1420, 520, "sound", 150)
    node("songs", 1230, 200, "sound")
    node("soundprint", 1230, 780, "sound")
    edges = [("context_radio", "context_mix"), ("context_mix", "logs"), ("service", "logs"), ("service", "main"),
             ("main", "logs"), ("main", "assist"), ("main", "checks"), ("main", "claude"), ("main", "cache"),
             ("main", "dimensions"), ("main", "library"), ("main", "chart"), ("main", "trace"), ("main", "usage"),
             ("main", "client"), ("main", "years"),
             ("assist", "checks"), ("assist", "fit"), ("assist", "rating"), ("assist", "cache"), ("assist", "stats"),
             ("assist", "dimensions"), ("assist", "trace"),
             ("checks", "rating"), ("checks", "trace"), ("checks", "usage"), ("rating", "claude"), ("rating", "cache"),
             ("rating", "dimensions"), ("rating", "trace"), ("rating", "usage"), ("claude", "trace"), ("claude", "usage"),
             ("cache", "dimensions"), ("fit", "dimensions"), ("fit", "stats"), ("library", "cache"), ("library", "trace"),
             ("client", "state"), ("years", "cache"), ("state", "soundprint"), ("__main__", "state"),
             ("__main__", "analyse"), ("__main__", "songs"), ("__main__", "neighbours"), ("__main__", "years"),
             ("__main__", "store"), ("__main__", "model"),
             ("analyse", "state"), ("analyse", "store"), ("analyse", "model"), ("analyse", "audio"),
             ("neighbours", "store"), ("neighbours", "years"), ("neighbours", "cache"), ("neighbours", "model"),
             ("neighbours", "audio"), ("model", "audio"), ("audio", "soundprint"), ("model", "soundprint"),
             ("neighbours", "soundprint"), ("analyse", "soundprint")]
    for a, b in edges:
        A, B = pos[a], pos[b]
        ax, ay = A.c
        bx, by = B.c
        # clip to box borders
        def clip(box, x0, y0, x1, y1):
            dx, dy = x1 - x0, y1 - y0
            tx = (box.w / 2) / abs(dx) if dx else 1e9
            ty = (box.h / 2) / abs(dy) if dy else 1e9
            t = min(tx, ty)
            return (x0 + dx * t, y0 + dy * t)
        p = clip(A, ax, ay, bx, by)
        q = clip(B, bx, by, ax, ay)
        dashed = (a, b) == ("service", "main")
        cross = (a in ("neighbours", "years") and b == "cache")
        color = KINDS["warn"][1] if cross else (150, 156, 168)
        c.arrow([p, q], dashed=dashed, color=color, width=1.6)
    c.group(1180, 870 - 10, 10, 10, "", "ext") if False else None
    c.legend_row(40, 865, [("core", "entry points"), ("ai", "mixassist"), ("sound", "soundprint")])
    c.line([(760, 873), (800, 873)], KINDS["warn"][1], 2)
    c.text(810, 863, "soundprint uses mixassist.cache.artist_key (one rule for \"the same artist\")", 14)
    c.save(P("modules.png"))


def fig_er():
    c = Canvas(1600, 900)
    c.title("Databases and their tables", "SQLite files of the add-on, and the tables it reads from Kodi's music database")

    def table(x, y, name, cols, kind="store", w=330, sub=None):
        h = 50 + 30 * len(cols)
        fill, stroke = KINDS[kind]
        c.rect(x, y, w, h, WHITE, stroke, 2, radius=6)
        c.rect(x, y, w, 44, fill, None, radius=6)
        c.line([(x, y + 44), (x + w, y + 44)], stroke, 1.5)
        c.text(x + 12, y + 9, name, 16, BOLD, INK)
        if sub:
            c.text(x + w - 10, y + 12, sub, 12, REG, MUTED, "ra")
        for i, (col, typ, key) in enumerate(cols):
            yy = y + 50 + i * 30
            c.text(x + 12, yy, ("🔑 " if False else "") + col, 14, SEMI if key else REG, INK)
            c.text(x + w - 12, yy, typ, 13, MONO, MUTED, "ra")
            if key:
                c.text(x + 12 + c.textlen(col, 14, SEMI) + 6, yy + 1, key, 11, BOLD, KINDS["store"][1])
        from draw import Box
        return Box(x, y, w, h)

    c.text(40, 85, "soundprint/sound.db", 15, BOLD, KINDS["sound"][1])
    songs = table(40, 110, "songs", [("path", "TEXT", "PK"), ("size", "INTEGER", ""), ("mtime", "REAL", ""),
                                     ("version", "TEXT", ""), ("length", "REAL", ""), ("vector", "BLOB 512×f16", ""),
                                     ("error", "TEXT", ""), ("analysed", "REAL", "")], sub="one row per file")
    c.text(420, 85, "mixassist/ratings.db", 15, BOLD, KINDS["ai"][1])
    units = table(420, 110, "units", [("key", "TEXT", "PK"), ("prompt_version", "TEXT", ""), ("kind", "TEXT", ""),
                                      ("vector", "TEXT (JSON)", ""), ("familiarity", "INTEGER", ""),
                                      ("description", "TEXT", ""), ("model", "TEXT", ""), ("source", "TEXT", ""),
                                      ("rated_ts", "INTEGER", "")], sub="album or track")
    verd = table(420, 460, "verdicts", [("key", "TEXT", "PK"), ("verdict", "TEXT", ""), ("reason", "TEXT", ""),
                                        ("stored_ts", "INTEGER", "")], sub="fingerprint key")
    c.text(800, 85, "mixassist/usage.db", 15, BOLD, KINDS["ai"][1])
    ev = table(800, 110, "events", [("ts", "INTEGER", "IX"), ("kind", "TEXT", ""), ("data", "TEXT (JSON)", "")], sub="AI calls, mixes")
    c.text(800, 275, "track_metadata_cache.db", 15, BOLD, KINDS["core"][1])
    tm = table(800, 300, "track_metadata_cache", [("path", "TEXT", "PK"), ("songid", "INTEGER", "IX"), ("title", "TEXT", ""),
                                                  ("artist", "TEXT", ""), ("album", "TEXT", ""), ("genre_json", "TEXT", ""),
                                                  ("year", "INTEGER", ""), ("decade", "TEXT", ""), ("duration", "INTEGER", ""),
                                                  ("thumbnail", "TEXT", ""), ("fanart", "TEXT", ""), ("cached_ts", "INTEGER", ""),
                                                  ("library_freshest_ts", "INTEGER", ""), ("schema_version", "INTEGER", "")])
    c.text(1200, 85, "Kodi: MyMusic*.db (read-only)", 15, BOLD, KINDS["kodi"][1])
    ks = table(1200, 110, "song", [("idSong", "INTEGER", "PK"), ("idPath", "INTEGER", "FK"), ("idAlbum", "INTEGER", "FK"),
                                   ("strFileName", "TEXT", ""), ("strTitle", "TEXT", ""), ("strArtistDisp", "TEXT", ""),
                                   ("strOrigReleaseDate", "TEXT", ""), ("strReleaseDate", "TEXT", "")], "kodi", 330)
    kp = table(1200, 450, "path", [("idPath", "INTEGER", "PK"), ("strPath", "TEXT", "")], "kodi", 330)
    ka = table(1200, 590, "album", [("idAlbum", "INTEGER", "PK"), ("bCompilation", "INTEGER", ""), ("strArtistDisp", "TEXT", ""),
                                    ("strOrigReleaseDate", "TEXT", ""), ("strReleaseDate", "TEXT", "")], "kodi", 330)
    c.arrow([(1530, 180), (1565, 180), (1565, 475), (1530, 475)], "idPath", lpos=(1565, 330))
    c.arrow([(1200, 205), (1175, 205), (1175, 615), (1200, 615)], "idAlbum", lpos=(1175, 400))
    
    c.textblock(40, 425, 340, "Keys by value, not by foreign key: a song is identified by its file path everywhere "
                              "(Kodi: path.strPath + song.strFileName; sound.db, track metadata cache, mix files, Radio state). A unit key in ratings.db is "
                              "rg:<MusicBrainz release group>, rec:<recording>, or album:/track:<artist>|<title>.", 14, REG, MUTED)
    c.textblock(40, 680, 340, "Files next to the databases: vectors.npy + vectors.json (the search matrix and its paths), "
                              "years.pickle (a year per song and era hints), status.json (the analysis).", 14, REG, MUTED)
    c.save(P("er.png"))


def fig_review():
    c = Canvas(1600, 560)
    c.title("A structured review, step by step", "From planning to a finding that stays fixed")
    steps = [("1 Plan", "scope, goal, roles, checklist; pick the risk areas", "core"),
             ("2 Prepare", "read this document's overview, the module's catalogue entry and its tests", "core"),
             ("3 Examine", "each reviewer alone, with the checklist; note questions and defects", "ai"),
             ("4 Meet", "walk through the code by data flow; agree on each finding", "ai"),
             ("5 Record", "docs/findings.md: F-number, status; ideas to docs/roadmap.md", "store"),
             ("6 Reproduce", "a failing test marked expectedFailure; test_findings keeps both in step", "sound"),
             ("7 Fix and verify", "fix on a fix/… branch, test passes, finding → Resolved with commit", "sound")]
    bs = []
    for i, (t, s, k) in enumerate(steps):
        r, col = divmod(i, 4)
        x = 40 + col * 390 + (195 if r else 0)
        y = 110 + r * 210
        bs.append(c.box(x, y, 330, 140, t, s, k, size=14))
    for a, b in zip(bs, bs[1:]):
        if a.y == b.y:
            c.connect(a, "e", b, "w")
        else:
            c.arrow([a.s, (a.s[0], 285), (b.n[0], 285), b.n])
    c.arrow([bs[-1].e, (1575, bs[-1].e[1]), (1575, 80), (205, 80), (205, 110)], "next review round: metrics and hotspots again", lpos=(900, 80), dashed=True)
    c.save(P("review.png"))


def fig_outlook():
    c = Canvas(1600, 600)
    c.title("Outlook: the open roadmap by theme", "Numbers are the roadmap's (I…); none of them says when it will be built")
    themes = [("Mixes", "I1 ordering by sound · I2 edits reach Kodi's queue · I3 rebuild instead of patching · I4 mix from a prompt · I33 mix recipes", "core"),
              ("Radio", "I5 carry on after a stop · I6 a favourite's refill size · I7 describe the seed once · I8 artist rule for unchecked refills · I32 move on from a poor batch · I44 artwork from the start", "core"),
              ("Sound engine", "I9 in step with Kodi's library (fixes F36) · I11 a faster search · I12 fewer snippets for a slow box · I13 intro/outro windows · I14 other models · I16 set-up stops with Kodi", "sound"),
              ("Character and Intent", "I17 acoustic/electric/electronic · I18 intent as summary · I19 longer descriptions · I20 context tags · I21 MusicBrainz genres · I22 folder signal · I23 narrow libraries · I24 API key · I37 Cultural: the scene · I38 sharpness · I39 Epoch (built in part)", "ai"),
              ("AI requests", "I40 turns and timings · I41 verdict cache (built) · I42 lean CLI start (built) · I43 effort and model per purpose", "ai"),
              ("Screen and housekeeping", "I36 a screen during playback with suggestions · I25 GitHub Actions on Node 24 · I26 MusicIP out of the description", "ext")]
    for i, (t, s, k) in enumerate(themes):
        r, col = divmod(i, 3)
        c.box(40 + col * 515, 100 + r * 240, 490, 215, t, s, k, size=14, tsize=19)
    c.save(P("outlook.png"))


def seqs():
    sequence(P("seq_generate.png"), "Sequence: Generate mix from playing audio",
             [("Listener", "user"), ("Kodi", "kodi"), ("Plugin (main.py)", "core"), ("Sound engine", "sound"),
              ("Service", "core"), ("Claude CLI", "ai")],
             [(0, 1, "\"Generate mix from playing audio\""),
              (1, 2, "plugin://…?action=generate_current_mix"),
              (2, 1, "get the playing file (seed)"),
              (2, 0, "mix dialog: size, variety, checks"),
              (0, 2, "OK", "dashed"),
              (2, 3, "python -m soundprint neighbours <seed> --count --variety --artist-window"),
              ("self", 3, "cosine over all vectors, weighted draw, rules"),
              (3, 2, "JSON: songs, similarity, rank", "dashed"),
              ("self", 2, "create_current_mix: .m3u, sidecar, current_mix.json"),
              (2, 1, "play the playlist, seed first; Container.Update(mix view)"),
              ("note", 2, 4, "The plugin writes mixassist/queue.json and metadata_refresh_queue.json, then ends."),
              ("divider", "in the background, seconds later"),
              ("self", 4, "tick: pop the request, start a worker thread"),
              (4, 3, "nearest rated songs (fixed scale), submixes"),
              (4, 5, "rate missing units; state the intent, judge the tracks"),
              (5, 4, "structured JSON: values, intent, verdicts, name", "dashed"),
              ("self", 4, "plan: replace outliers from submixes"),
              (4, 1, "patch the playlist beyond the protected zone"),
              (4, 0, "notification: \"2 tracks didn't fit and were replaced\"")])
    sequence(P("seq_radio.png"), "Sequence: a station's refill with the checks on",
             [("Kodi player", "kodi"), ("Service: radio tick", "core"), ("Radio check thread", "ai"),
              ("Sound engine", "sound"), ("Claude CLI", "ai")],
             [("self", 1, "fewer than 3 songs left after the playing one"),
              (1, 2, "start check: seed = last song that passed"),
              (2, 3, "neighbours: 75 songs, leave out played/queued/turned-down"),
              (3, 2, "candidates", "dashed"),
              (2, 4, "batch of 18: judge against the station's intent"),
              (4, 2, "verdicts", "dashed"),
              ("self", 2, "Character + Intent; more batches or lists until enough fit"),
              (2, 1, "result: songs per refill (default 6), drifted profile", "dashed"),
              (1, 0, "append to the playlist; prune backlog to 10"),
              ("note", 1, 2, "If the playing song is the last before the check is done, the source's songs are queued unchecked so the radio never stops."),
              (0, 1, "onPlayBackStopped (> 3 s) or other playback → end the station")])
    sequence(P("seq_analysis.png"), "Sequence: the sound engine's analysis",
             [("Service", "core"), ("soundprint.client", "sound"), ("analyse (main process)", "sound"),
              ("Worker processes", "sound"), ("sound.db", "store")],
             [("self", 0, "due: after Kodi's library scan, every 8 h, or to resume"),
              (0, 1, "start_analysis(data, userdata, kodi_pid)"),
              (1, 2, "Popen detached, below-normal priority"),
              ("self", 2, "plan: Kodi's song paths vs stored rows (size, mtime, version)"),
              (2, 3, "pool.imap_unordered(analyse_song, todo)"),
              ("self", 3, "decode snippets, mel, DCLAP, mean, normalise"),
              (3, 2, "vector or error per song", "dashed"),
              (2, 4, "put; commit every 25 songs"),
              ("self", 2, "status.json every 5 s; stop file? Kodi closed?"),
              (0, 1, "(the plugin) status_lines() for Settings > Advanced > Status", "dashed")])


if __name__ == "__main__":
    for fn in [fig_context, fig_three_steps, fig_pipeline, fig_snippets, fig_filterbank, fig_spectrogram, fig_cosine,
               fig_similarity, fig_variety, fig_character, fig_ai, fig_components, fig_runtime, fig_service_loop,
               fig_dataflow_mix, fig_messaging, fig_kodi, fig_states, fig_modules, fig_er, fig_review, fig_outlook, seqs]:
        if len(sys.argv) > 1 and fn.__name__ not in sys.argv[1:]:
            continue
        fn()
        print("ok", fn.__name__)
