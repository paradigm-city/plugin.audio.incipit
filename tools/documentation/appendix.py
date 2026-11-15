"""Appendices: method catalogue, glossary, references, index."""
import re

from doclib import GREY
from part3 import MAIN_AREAS, SERVICE_AREAS

VERBS = {
    "get": "Returns", "is": "Whether", "has": "Whether", "build": "Builds", "show": "Shows", "format": "Formats",
    "parse": "Parses", "load": "Loads", "save": "Saves", "add": "Adds", "run": "Runs", "ensure": "Ensures",
    "apply": "Applies", "set": "Sets", "normalize": "Normalises", "find": "Finds", "record": "Records",
    "remove": "Removes", "make": "Makes", "draw": "Draws", "render": "Renders", "start": "Starts", "stop": "Stops",
    "update": "Updates", "refresh": "Refreshes", "create": "Creates", "write": "Writes",
    "read": "Reads", "list": "Lists", "collect": "Collects", "check": "Checks", "choose": "Lets the listener choose",
    "select": "Lets the listener select", "edit": "Edits", "play": "Plays", "prune": "Prunes", "mark": "Marks",
    "clear": "Clears", "reset": "Resets", "split": "Splits", "query": "Queries", "extract": "Extracts",
    "score": "Scores", "search": "Searches", "evaluate": "Evaluates", "compute": "Computes", "insert": "Inserts",
    "delete": "Deletes", "cleanup": "Cleans up", "enqueue": "Queues", "pop": "Takes the next", "queue": "Queues",
    "open": "Opens", "end": "Ends", "begin": "Begins", "tune": "Tunes", "turn": "Turns", "change": "Changes",
    "rename": "Renames", "ask": "Asks", "confirm": "Confirms", "notify": "Notifies", "log": "Logs",
    "remember": "Remembers", "migrate": "Migrates", "take": "Takes", "announce": "Announces", "handle": "Handles",
    "advance": "Advances", "append": "Appends", "correct": "Corrects", "goto": "Goes to", "follow": "Follows",
    "keep": "Keeps", "describe": "Describes", "match": "Matches", "infer": "Infers", "expand": "Expands",
    "offer": "Offers", "patch": "Patches", "wait": "Waits for", "process": "Processes", "report": "Reports",
    "undo": "Undoes", "reload": "Reloads", "forget": "Forgets", "pick": "Picks", "plain": "Plain text of",
    "calculate": "Calculates", "discovery": "Discovery:", "radio": "Radio:", "station": "Station:", "mix": "Mix:",
    "repair": "Repair:", "track": "Track:", "soundprint": "Sound engine:", "song": "Song:", "favourite": "Favourite:",
}
SMALL = {"mix", "mixes", "radio", "track", "tracks", "song", "songs"}


def from_name(name):
    """A short description derived from a function's name (for functions without a docstring)."""
    base = name.strip("_")
    if base.startswith("on") and base[2:3].isupper():
        return "Kodi callback: " + re.sub(r"(?<!^)(?=[A-Z])", " ", base[2:]).lower() + "."
    if base == "__init__":
        return "Sets up the object."
    words = base.split("_")
    verb = VERBS.get(words[0])
    names = {"ts": "timestamp", "musicip": "MusicIP", "jsonrpc": "JSON-RPC", "ui": "UI", "ai": "AI", "url": "URL",
             "id": "ID", "rpc": "RPC", "db": "database", "dir": "folder"}
    rest = " ".join(names.get(w, w) for w in (words[1:] if verb else words))
    if verb:
        text = f"{verb} {rest}".strip()
    else:
        text = f"The {rest}" if rest else base
    return text[0].upper() + text[1:] + "."


def short(doc, limit=230):
    doc = doc.replace("\n", " ")
    if len(doc) <= limit:
        return doc
    cut = doc[:limit]
    stop = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:stop + 1] if stop > 80 else cut.rsplit(" ", 1)[0] + " …")


def esc(text):
    # keep the markup parser from reading code as markup
    return text.replace("**", "∗∗").replace("`", "'").replace("[[", "[ [")


def catalogue(D, cat):
    D.h(1, "Appendix A · Method catalogue", page_break=True)
    D.p("Every function and method of the add-on, module by module, in the order of the file. *Line* is where it "
        "begins, *Len.* its length in lines. The purpose is the first paragraph of the docstring; where there is none, "
        "a description derived from the name, marked ◦. `main.py` and `service.py` are grouped by area (chapter 15).")
    order = ["main.py", "service.py", "context_mix.py", "context_radio.py", "logs.py", "musicip_dormant.py"] + \
            [m for m in cat if m.startswith("mixassist/")] + [m for m in cat if m.startswith("soundprint/")] + \
            [m for m in cat if m.startswith("tools/")]
    for mod in order:
        e = cat[mod]
        items = [(f["line"], f["name"], f["sig"], f["len"], f["doc"]) for f in e["functions"]]
        for c in e["classes"]:
            items.append((c["line"], f"class {c['name']}", ", ".join(c["bases"]), 0, c["doc"]))
            for m in c["methods"]:
                items.append((m["line"], f"{c['name']}.{m['name']}", m["sig"], m["len"], m["doc"]))
        items.sort()
        if not items:
            continue
        D.h(2, f"A · {mod}", index=f"{mod}")
        if e["doc"]:
            D.p(esc(short(e["doc"], 400)), size=9, color=GREY)
        areas = MAIN_AREAS if mod == "main.py" else SERVICE_AREAS if mod == "service.py" else [(0, 10 ** 6, "")]
        for a, b, label in areas:
            chunk = [it for it in items if a <= it[0] <= b]
            if not chunk:
                continue
            if label:
                D.h(4, f"Lines {a:,}–{b:,}: {label}")
            rows = []
            for line, name, sig, length, doc in chunk:
                shown = f"{name}({sig})" if not name.startswith("class ") else f"{name}({sig})"
                purpose = esc(short(doc)) if doc else "◦ " + from_name(name.split(".")[-1].replace("class ", ""))
                rows.append([shown, str(line), str(length) if length else "", purpose])
            D.table(["Function", "Line", "Len.", "Purpose"], rows, [6.0, 1.1, 0.9, 8.6], size=7.5, mono_cols=(0,))


GLOSSARY = [
    ("AUC", "Area under the ROC curve: how well a score ranks the right items first; 1.0 perfect, 0.5 chance."),
    ("Accept borderline", "Intent also takes songs it calls borderline."),
    ("Analysis version", "What a sound print was made with (`dclap-v1/snippets-6/preroll-1`); another version is made again."),
    ("Artist window", "No artist repeat within N songs; MusicIP's *reject size*."),
    ("Borderline", "The AI's verdict for a track that shares part of what the seed is about."),
    ("Character", "The profile check: each song's 8 values against the seed's (formerly the vector or profile check)."),
    ("Checks", "Character and Intent together (formerly AI Mix Assist)."),
    ("CLAP / DCLAP", "Contrastive Language–Audio Pretraining; DCLAP is its distilled, faster audio encoder."),
    ("Compilation", "An album with the compilation flag, *Various Artists*, or more than 8 track artists."),
    ("Cosine similarity", "The cosine of the angle between two vectors; 1 = same direction."),
    ("Current mix", "The newest mix; replaced by the next one unless saved."),
    ("Drift", "How a station's reference profile moves with its songs (half-life 0, 60 or 20 songs)."),
    ("Embedding", "A vector that places an item in a space where distance means difference."),
    ("Epoch", "The perspective of time; limits the search to a window of years."),
    ("Familiarity", "How well the AI knows a unit: 0 unknown, 1 artist known, 2 this album known."),
    ("Fixed scale", "Character's spreads and typical misfit from the seed's nearest rated songs by sound (F40)."),
    ("Flagged", "One check reports an outlier; the track stays but never seeds a submix."),
    ("Incipit", "The first words or bars of a work; the add-on's name; the seed song."),
    ("Intent", "The AI's statement of what the seed is about, and its judgement of each track."),
    ("Log-mel spectrogram", "Band energies on the mel scale in decibels over time: the model's input."),
    ("MAD", "Median absolute deviation; a spread that ignores outliers."),
    ("Mahalanobis distance", "A distance that accounts for correlated dimensions."),
    ("Misfit", "A track's weighted distance from the seed's profile; relative misfit divides by the typical one."),
    ("Outlier", "A track that every check that is on turns down."),
    ("Perspective", "The listening view the intent is stated from (Mixed, Technical, Emotional, Cultural, Functional, Lyrical, Epoch)."),
    ("Protected zone", "The playing track and the next; never patched."),
    ("Reach", "How deep into the order by sound a mix draws (variety)."),
    ("Refill", "The songs Radio adds when fewer than 3 are left."),
    ("Sidecar", "The JSON file next to a mix's .m3u with everything about the mix."),
    ("Seed", "The song a mix or station starts from; it carries the intent."),
    ("Sound engine", "The package `soundprint`: sound prints of every song and the search."),
    ("Sound print", "A song's 512-number vector from six 10-second snippets."),
    ("Source", "Where a mix's songs come from: the sound engine (formerly MusicIP)."),
    ("STFT", "Short-time Fourier transform: frequencies of short overlapping frames."),
    ("Submix", "A small mix from a fitting track, used to find replacements."),
    ("Tidy-up", "Checking an existing mix and replacing outliers."),
    ("Tolerance", "Character's limit: Focused 1.0 · Close 1.1 · Balanced 1.2 · Open 1.35 · Adventurous 1.5, or Off."),
    ("Unit", "What is rated: an album, or a track from a compilation."),
    ("Variety", "0–9: how far a mix reaches into the order by sound, and how random it is."),
]

REFERENCES = [
    ("1", "Kodi Wiki: Add-on development; addon.xml; Python API. https://kodi.wiki/view/Add-on_development"),
    ("2", "Kodi JSON-RPC API, version 13 (Kodi 21). https://kodi.wiki/view/JSON-RPC_API/v13"),
    ("3", "J. B. Allen: Short Term Spectral Analysis, Synthesis, and Modification by Discrete Fourier Transform. IEEE "
          "Trans. Acoustics, Speech, and Signal Processing 25(3), 1977, 235–238."),
    ("4", "C. E. Shannon: Communication in the Presence of Noise. Proc. IRE 37(1), 1949, 10–21."),
    ("5", "F. J. Harris: On the Use of Windows for Harmonic Analysis with the Discrete Fourier Transform. Proc. IEEE "
          "66(1), 1978, 51–83."),
    ("6", "S. S. Stevens, J. Volkmann, E. B. Newman: A Scale for the Measurement of the Psychological Magnitude Pitch. "
          "J. Acoustical Society of America 8(3), 1937, 185–190."),
    ("7", "B. McFee et al.: librosa: Audio and Music Signal Analysis in Python. Proc. 14th Python in Science Conference "
          "(SciPy), 2015. https://librosa.org"),
    ("8", "M. Slaney: Auditory Toolbox, Version 2. Interval Research Corporation, Technical Report 1998-010."),
    ("9", "Y. Wu, K. Chen, T. Zhang, Y. Hui, T. Berg-Kirkpatrick, S. Dubnov: Large-scale Contrastive Language-Audio "
          "Pretraining with Feature Fusion and Keyword-to-Caption Augmentation. ICASSP 2023. arXiv:2211.06687; "
          "https://github.com/LAION-AI/CLAP"),
    ("9b", "K. Chen et al.: HTS-AT: A Hierarchical Token-Semantic Audio Transformer for Sound Classification and "
           "Detection. ICASSP 2022. arXiv:2202.00874"),
    ("10", "A. van den Oord, Y. Li, O. Vinyals: Representation Learning with Contrastive Predictive Coding. "
           "arXiv:1807.03748, 2018."),
    ("11", "A. Radford et al.: Learning Transferable Visual Models From Natural Language Supervision (CLIP). ICML 2021. "
           "arXiv:2103.00020"),
    ("12", "Anthropic: Claude Code documentation (CLI reference, print mode, structured output). "
           "https://docs.claude.com/en/docs/claude-code"),
    ("13", "NeptuneHub: AudioMuse-AI-DCLAP, release v1 (AGPL-3.0). https://github.com/NeptuneHub/AudioMuse-AI-DCLAP; "
           "AudioMuse-AI: https://github.com/NeptuneHub/AudioMuse-AI"),
    ("14", "G. Hinton, O. Vinyals, J. Dean: Distilling the Knowledge in a Neural Network. arXiv:1503.02531, 2015."),
    ("15", "ONNX Runtime. https://onnxruntime.ai"),
    ("16", "PyAV: Pythonic bindings for FFmpeg. https://github.com/PyAV-Org/PyAV"),
    ("17", "FFmpeg. https://ffmpeg.org"),
    ("18", "P. S. Efraimidis, P. G. Spirakis: Weighted Random Sampling with a Reservoir. Information Processing Letters "
           "97(5), 2006, 181–185."),
    ("19", "C. D. Manning, P. Raghavan, H. Schütze: Introduction to Information Retrieval, ch. 6 (the vector space "
           "model, cosine similarity). Cambridge University Press, 2008."),
    ("20", "T. Cover, P. Hart: Nearest Neighbor Pattern Classification. IEEE Trans. Information Theory 13(1), 1967, 21–27."),
    ("21", "MusicIP (MusicMagic Mixer). https://en.wikipedia.org/wiki/MusicIP"),
    ("22", "P. J. Rousseeuw, C. Croux: Alternatives to the Median Absolute Deviation. J. American Statistical "
           "Association 88(424), 1993, 1273–1283."),
    ("23", "P. C. Mahalanobis: On the Generalised Distance in Statistics. Proc. National Institute of Sciences of India "
           "2(1), 1936, 49–55."),
    ("24", "O. Ledoit, M. Wolf: A Well-Conditioned Estimator for Large-Dimensional Covariance Matrices. J. Multivariate "
           "Analysis 88(2), 2004, 365–411."),
    ("25", "J. A. Hanley, B. J. McNeil: The Meaning and Use of the Area under a ROC Curve. Radiology 143(1), 1982, 29–36."),
    ("26", "C. R. Harris et al.: Array programming with NumPy. Nature 585, 2020, 357–362. https://numpy.org"),
    ("27", "M. E. Fagan: Design and Code Inspections to Reduce Errors in Program Development. IBM Systems Journal 15(3), "
           "1976, 182–211."),
    ("28", "IEEE Std 1028-2008: IEEE Standard for Software Reviews and Audits."),
    ("29", "Google Engineering Practices: How to do a code review. https://google.github.io/eng-practices/review/"),
    ("30", "Incipit's own documents: docs/concept_incipit.md, concept_ai_mix_assist.md, concept_suggestion_engine.md, "
           "concept_radio_mode.md, concept_discovery_mode.md, concept_repair_strategy.md, concept_epoch.md, "
           "glossary_ai_mix_assist.md, findings.md, roadmap.md, testing_quality_notes.md."),
]


def back_matter(D):
    D.h(1, "Appendix B · Glossary", page_break=True)
    D.table(["Term", "Meaning"], [[f"**{t}**", m] for t, m in GLOSSARY], [4.0, 12.6], size=8.5)
    D.h(1, "Appendix C · References", page_break=True)
    for n, text in REFERENCES:
        D.p(f"[{n}]  {text}", size=9, after=3)
    D.h(1, "Appendix D · Index", page_break=True)
    D.index_field()
