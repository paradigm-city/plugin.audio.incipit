"""Title, about, Part I (overview, goals and concepts) and Part II (theory)."""
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from doclib import GREY, NAVY


def F(name):
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "figs", name)


def title_page(D, info):
    d = D.d
    sec = d.sections[0]
    sec.different_first_page_header_footer = True
    for _ in range(5):
        d.add_paragraph()
    p = d.add_paragraph(style="Title")
    p.add_run("Incipit")
    D.p("A Kodi add-on for mixes and endless radio, chosen by sound and kept true to what the first song is about",
        size=15, color=NAVY, after=24)
    D.p("Integrated documentation", size=20, color=NAVY, after=2)
    D.p("Goals and concepts · signal processing and pattern detection · architecture · design down to each method · "
        "databases · software review · open issues and outlook", size=11, color=GREY, after=60)
    D.table(["", ""], [
        ["Add-on", f"Incipit, ID `plugin.audio.incipit`, version {info['version']} (formerly MusicIP)"],
        ["Code base", f"branch `main`, commit `{info['commit']}`; {info['files']} Python files, {info['lines']:,} lines, "
                      f"{info['funcs']} functions and methods; {info['tests']:,} automated tests"],
        ["Platform", "Kodi 21 (Omega), Kodi's Python 3.8; sound engine in its own Python 3.9+ environment"],
        ["Document date", info["date"]],
        ["Written for", "presentation, learning and software review"],
    ], [3.5, 13.1], size=9.5, header_fill="FFFFFF", zebra=False, bold_first=True, header=False)
    D.page_break()


def about(D):
    D.h(1, "About this document")
    D.p("This document describes Incipit as a whole: why it exists, the ideas behind it, the theory its sound engine "
        "rests on, how its parts are built and work together, and how to review it. It is written in plain language. "
        "Technical terms are explained where they first appear and collected in the glossary (Appendix B).")
    D.h(3, "Three ways to read it")
    D.table(["Goal", "Read", "Time"], [
        ["**Presentation**: show what Incipit is and does", "Chapter 1 and 2, the figures of chapters 3 to 8 "
         "(each figure stands on its own), chapter 24 (outlook)", "30 minutes"],
        ["**Learning**: understand how it works", "Part II (theory: signal processing, search, statistics, AI) "
         "and Part III (architecture) in order; the boxes marked *Key idea* sum up each step", "half a day"],
        ["**Software review**: examine the code", "Chapter 22 (review strategy) first, then Part III and IV; "
         "the method catalogue (Appendix A) is the map for each session", "per session 1–2 hours"],
    ], [4.3, 9.8, 2.5], size=9.5)
    D.h(3, "Conventions")
    D.bullets([
        "File and function names are written like `main.fetch_mix` or `soundprint/neighbours.py`. A function is named "
        "with its module: `main.fetch_mix` is the function `fetch_mix` in `main.py`.",
        "**F12** is a finding (a problem in the code, `docs/findings.md`); **I34** is a roadmap idea (`docs/roadmap.md`). "
        "Both numbers are permanent.",
        "Numbers measured on the developer's library (about 153,000 to 156,000 songs on an Intel i3-10100 without a "
        "graphics card) are marked as measured; they describe this library, not every library.",
        "References to outside sources are in square brackets, e.g. [5], and listed in Appendix C.",
        "Index terms are listed in Appendix D.",
    ])
    D.h(3, "How this document was made")
    D.p("The descriptions come from the code, its docstrings and the concept documents in `docs/`. The method catalogue "
        "(Appendix A), the metrics in chapter 22 and the dependency data were extracted from the source code by a "
        "script that reads the Python syntax tree. The charts of chapters 3 and 4 were computed with the sound engine's own "
        "code on the developer's library. Where the code has no docstring, the catalogue gives a short description derived "
        "from the function's name; such entries are marked with ◦.")
    D.page_break()
    D.p("**Contents**", size=20, color=NAVY, after=10)
    D.toc()
    D.p("**Figures**", size=14.5, color=NAVY, before=16, after=6)
    D.toc("Figure")
    D.p("**Tables**", size=14.5, color=NAVY, before=16, after=6)
    D.toc("Table")


# ======================================================================================================================
def part1(D, info):
    D.h(1, "Part I · Overview", page_break=True)
    D.p("What Incipit is, what it is for, and the ideas that shape it.", italic=True, color=GREY)

    D.h(1, "1  Incipit at a glance")
    D.h(2, "1.1  What it does")
    D.p("[[Incipit]] is a music add-on for [[Kodi]], the open-source media centre [1]. It makes **mixes** and "
        "endless **radio stations** from any song of the listener's music library. The name is the Latin word for "
        "*it begins*: the first words of a text or the first bars of a piece. In Incipit, the first song of a mix — "
        "the [[seed|seed song]] — decides what the mix is about.")
    D.p("A mix is made in three steps. First the [[sound engine]] finds the songs that *sound* most like the seed: "
        "it has listened to every song of the library once and keeps a small acoustic fingerprint of each, a "
        "[[sound print]]. Then two optional checks keep the mix true to its seed: [[Character]] compares a profile of "
        "eight musical values, and [[Intent]] asks an AI (Claude [12]) what the seed is about and whether each song "
        "fits that. The listener hears the mix at once; the checks work in the background.")
    D.p("Around this core, Incipit offers saved mixes that repair themselves when files move, a Radio mode that "
        "works like the scan button of an old radio, a Discovery mode that plays short snippets of random songs, "
        "favourite stations, an information window with charts, and detailed logging.")
    D.h(2, "1.2  Key figures")
    D.table(["What", "Value", "Note"], [
        ["Songs with a sound print", "156,415", "the developer's library, 2026-11-15"],
        ["Sound print", "512 numbers, stored in 1 KB", "from 6 snippets of 10 s per song"],
        ["First analysis of the library", "about 22 hours (0.4 s per song)", "4-core PC, no graphics card, low priority"],
        ["Search for the nearest songs", "about 1 s", "all 156,000 vectors compared at once"],
        ["Profile values (Character)", "8", "energy, exploration, mood, making, danceability, production, form, sounding year"],
        ["Listening perspectives (Intent)", "7", "Mixed, Technical, Emotional, Cultural, Functional, Lyrical, Epoch"],
        ["Code", f"{info['files']} Python files, {info['lines']:,} lines, {info['funcs']} functions", "plus XML resources"],
        ["Plugin actions", "54", "every menu entry and context-menu entry is one"],
        ["Settings", "44", "in four categories plus Logging"],
        ["Automated tests", f"{info['tests']:,}", "run without Kodi, on every push (GitHub Actions)"],
        ["Findings (code problems) recorded", "57 so far, 4 open", "docs/findings.md"],
        ["Roadmap ideas", "44 numbered", "docs/roadmap.md"],
    ], [5.3, 5.5, 5.8], size=9, caption="Incipit in numbers")
    D.h(2, "1.3  A short tour")
    D.p("In Kodi, Incipit appears under **Music → Music add-ons → Incipit**. Its first screen shows:")
    D.bullets([
        ("Generate mix from playing audio:", "a mix seeded with the song that plays now. A dialog asks for size, "
         "variety and the checks; the mix plays at once."),
        ("Current mix / Current station:", "what plays now, with the red playing icon, when a mix or a station plays."),
        ("Mix mode:", "the current mix, Discovery mode (random snippets; *Create mix from current discovery song*) "
         "and **Saved mixes**."),
        ("Radio mode:", "**Scan stations** (random snippets, *Pick this station*) and **Favourite stations**."),
        ("Settings:", "Mixing, Radio, Advanced (sound engine, Claude Code), Logging."),
    ])
    D.p("In Kodi's music library, the context menu of every song has **Create Incipit mix** and **Start Incipit "
        "radio**. In a mix, each track has **More like this**, **Less like this**, **Remove from mix**, **Save mix**, "
        "**Checks…** and **Information**; the keys `m`, `l`, `DEL` and `i` do the same. The information window shows a "
        "mix's or station's profile, its course through the eight values, its history and what the AI said.")

    D.h(1, "2  Goals, concepts and ideas", page_break=True)
    D.h(2, "2.1  The problem")
    D.p("Until October 2026 the mixes came from [[MusicIP]] (MusicMagic Mixer) [21], a program from the early "
        "2000s that analysed the audio of a library and made mixes of songs that sound alike. Its mixes were good at "
        "sound and blind to context: depending on the seed, a mix could hold songs that *sound* similar but "
        "*belong* somewhere else — Austrian disco in an avant-jazz mix, hard rock in a synth-pop mix. MusicIP was also "
        "old, Windows-only, ran as a separate server, and had to rescan the library after files moved.")
    D.p("Tags do not solve this. The genre tags of the developer's library hold 2,079 different values; mood tags "
        "exist for less than 1 % of the songs. A mix that should stay true to its seed needs something that "
        "understands the music itself.")
    D.h(2, "2.2  Goals")
    D.table(["Goal", "How Incipit meets it"], [
        ["**A mix grows from its first song**", "the seed carries the intent; every check measures against the seed"],
        ["**By sound, not by tags**", "sound prints from the audio itself; little-known music is found as easily as famous music"],
        ["**True to what the seed is about**", "Character (profile) and Intent (AI judgement), each optional"],
        ["**Playback starts at once**", "no mix or station waits for an AI; checks run in the background and patch the "
         "part not yet played"],
        ["**As little interaction as possible**", "automatic by default; notifications and Undo instead of questions"],
        ["**Local and light**", "the analysis runs on the listener's PC at low priority; no graphics card; a search takes a "
         "second; the target is an always-on quiet box"],
        ["**Works without AI**", "with both checks off, nothing is asked of an AI and no subscription is needed"],
        ["**Saved mixes stay playable**", "consistency checks, repair readiness, automatic repair of moved files"],
        ["**General**", "nothing depends on how one library is organised (no genre folders, no tag structure)"],
        ["**Transparent**", "every step is logged by area; the information window shows what happened and why"],
    ], [5.0, 11.6], size=9, caption="Goals and how they are met")
    D.h(2, "2.3  The central idea: the incipit")
    D.p("**The seed carries the intent of the mix.** Whatever the listener starts from — the song that plays, a "
        "library song, a Discovery snippet, a Radio pick — that song defines what the mix is about. Everything after "
        "it is measured against it.")
    D.figure(F("three_steps.png"), "A mix in three steps: Source, Character, Intent", index="Source, Character, Intent")
    D.table(["Step", "What it does", "The listener's control", "Can be off"], [
        ["**Source**", "the sound engine: the songs nearest to the seed by sound", "Variety 0–9; no artist repeat within N songs", "no"],
        ["**Character**", "each song's 8-value profile against the seed's", "Tolerance: Focused, Close, Balanced, Open, Adventurous", "yes"],
        ["**Intent**", "the AI states what the seed is about, then judges each song", "Perspective (7); Accept borderline", "yes"],
    ], [2.4, 6.2, 5.8, 2.2], size=9, caption="The three steps")
    D.callout("Key idea.", "A new song must pass **every** check that is on. A track leaves an existing mix only when "
              "**every** check that is on turns it down. So adding is strict and removing is careful.")
    D.h(2, "2.4  Design principles")
    D.p("These principles come from the concept documents and guide every decision in the code:")
    D.bullets([
        ("0  As little interaction as possible.", "The add-on works on its own; the listener sees notifications and can undo."),
        ("1  Playback starts immediately.", "No new mix and no station waits for an AI call. (\"More like this\" may "
         "wait: its new songs are checked before they are inserted.)"),
        ("2  Saved mixes change only on demand.", "Changes made while a mix is created are announced and can be undone."),
        ("3  Act on the available facts.", "When the checks agree, a track is replaced, even when the AI knows the "
         "music only from hints. A wrong removal costs little: a replacement is fetched."),
        ("4  General.", "Nothing depends on one library's organisation."),
        ("5  Rated on demand, cached forever.", "Only albums that appear in mixes are rated by the AI, each only once "
         "per prompt version."),
        ("Listen like a DJ.", "Judge music from the artist's intent, not from the average listener's reaction or the "
         "mainstream consensus of \"similar artists\"."),
        ("Light at run time.", "Heavy work (the analysis) runs once, in the background, at low priority; what runs "
         "while the listener waits is small."),
        ("Respect licences and privacy.", "The DCLAP model (AGPL-3.0) is downloaded at the listener's request, never "
         "bundled; the add-on is MIT. The listener's subscription is used, never an API key; no e-mail address goes "
         "into a log."),
    ])
    D.h(2, "2.5  Ideas behind the features")
    D.table(["Feature", "Idea"], [
        ["[[Current mix]] and [[saved mixes|Saved mix]]", "A new mix is not saved on its own. It becomes the *current mix*; the listener "
         "decides whether to keep it (*Save mix*). An unsaved current mix is replaced by the next new mix."],
        ["[[Radio mode]]", "Like a vintage radio set: scan through random snippets, and when something sounds good, "
         "*pick this station*. From then on an endless mix plays, refilled from the last songs, so the station "
         "drifts slowly like a radio programme."],
        ["[[Drift]]", "A station's profile can stay with the picked song, drift slowly or wander freely (a half-life "
         "of 0, 60 or 20 songs)."],
        ["[[Discovery mode]]", "Sample the library: short excerpts of random songs; any snippet can seed a mix."],
        ["[[Favourite stations]]", "A station's picked song, name, settings and the AI's description are kept; a "
         "favourite always starts fresh."],
        ["[[Repair]]", "Saved mixes point to files. When files move, the add-on finds them again in Kodi's library "
         "and repairs the mix — automatically only when the match is unique and certain."],
        ["[[Listening perspective|Perspective]]", "The same song can be about different things: how it is made (Technical), what "
         "the artist expresses (Emotional), where it comes from (Cultural), what it is for (Functional), what the "
         "words say (Lyrical), when it came out (Epoch)."],
        ["[[Epoch]]", "A station of what came out when the seed came out, across genres and countries; the sound "
         "engine searches only songs of that time window."],
    ], [4.0, 12.6], size=9, caption="Features and the ideas behind them")
    D.h(2, "2.6  History in brief")
    D.table(["When", "What"], [
        ["2026-04-20", "First commit: mixes from a local MusicIP server, shown as a folder in Kodi"],
        ["to 2026-10", "Saved mixes, consistency checks and repair, Discovery mode, metadata cache, keyboard shortcuts"],
        ["2026-10-14 to 10-24", "AI Mix Assist: profile ratings, the seed-intent check, Radio mode with checks, perspectives"],
        ["2026-10-25 to 10-29", "The sound engine (DCLAP sound prints) replaces MusicIP; the checks become Character and Intent"],
        ["2026-10-29", "Renamed Incipit; new ID `plugin.audio.incipit`; data of the old ID taken over"],
        ["2026-10-30 to 11-01", "Mix mode and Radio mode screens; songs per refill; a station's search leaves out its songs (I34)"],
        ["2026-11-10", "Epoch perspective with a time window in the search; years for compilation songs"],
        ["2026-11-12 to 11-13", "AI requests: verdict cache, lean CLI start, model and effort per purpose"],
    ], [3.4, 13.2], size=9, caption="Milestones (from the git history and the concept documents)")


# ======================================================================================================================
def part2(D):
    D.h(1, "Part II · Theory", page_break=True)
    D.p("The ideas from signal processing, machine learning and statistics that the sound engine and the checks use. "
        "Each section explains the idea first and then shows how Incipit applies it.", italic=True, color=GREY)

    D.h(1, "3  Signal processing in the sound engine")
    D.p("The [[sound engine]] (package `soundprint/`) turns every music file into a [[sound print]]: one list of 512 "
        "numbers that describes how the song sounds. The figure at the end of this chapter shows the whole path; "
        "the sections below take it step by step.")
    D.figure(F("pipeline.png"), "From a music file to a sound print", index="sound print:pipeline", landscape=True)
    D.h(2, "3.1  Digital audio in brief")
    D.p("A music file stores sound as **samples**: the air pressure measured many thousand times a second. The "
        "[[sample rate]] says how often (CD audio: 44,100 per second). By the [[Nyquist theorem|Nyquist–Shannon theorem]] [4], a sample rate "
        "of *f* can only hold frequencies below *f*/2 — 22 kHz for CD audio, above the limit of human hearing. "
        "Each sample has a resolution (16 bits on a CD: 65,536 steps). Stereo files hold two channels.")
    D.p("Files are usually compressed (MP3, AAC, FLAC …). A **decoder** turns them back into samples. Incipit uses "
        "[[FFmpeg]] [17] through [[PyAV]] [16], which read almost every audio format.")
    D.h(2, "3.2  Decoding as the model expects it")
    D.p("A neural network gives good results only on input that looks like its training data. The DCLAP model was "
        "trained on audio as the library librosa [7] loads it, so `soundprint/audio.py` reproduces exactly that:")
    D.bullets([
        ("Resampled to 48 kHz", "(`RATE = 48000`), whatever the file's own rate."),
        ("Mono:", "the mean of all channels (also for 5.1 or 7.1 files)."),
        ("Clipped and rounded to 16 bits", "(`prepare`): values limited to −1…1, rounded to 1/32,767."),
    ])
    D.p("Two robustness measures were added after the first full analysis of the library (2026-10-28):")
    D.bullets([
        ("ID3 tags in front of non-MP3 data", "(an MP3 inside a WAV file, Musepack) or tags over 1 MB (large cover "
         "images) hide the audio from FFmpeg. `tag_end` reads the tag's size from its 10-byte header and `FileFrom` "
         "hands FFmpeg a view of the file that begins after the tag."),
        ("Damaged MP3 frames:", "a false frame start in damaged data decodes as a frame with another sample rate or "
         "channel layout, which the resampler refuses. Such frames are skipped, as librosa's decoder does."),
    ])
    D.h(2, "3.3  Snippets instead of the whole song")
    D.p("Analysing every second of 156,000 songs would take weeks on a small PC (another project, AudioMuse-AI, "
        "takes about three weeks for a library this size). Incipit analyses **six snippets of 10 seconds** per song, "
        "evenly spread: snippet *i* (0…5) is centred at (*i* + ½)/6 of the song's length (`snippet_starts`).")
    D.figure(F("snippets.png"), "Six snippets spread over a song; each is decoded from one second earlier", index="snippet")
    D.bullets([
        ("Pre-roll:", "the first frames after a seek are garbled (an MP3's bit reservoir, the resampler starting up), "
         "and the model weighs a window's first 50 ms heavily: such a glitch alone gave a cosine of 0.73 against the "
         "clean window (measured). So each snippet is decoded from 1 s earlier and that second is dropped "
         "(`PREROLL_SECONDS = 1.0`)."),
        ("Silence:", "a window quieter than about −80 dBFS (RMS below 10⁻⁴) says nothing about the song and is left "
         "out, unless all windows are that quiet."),
        ("Short or broken files:", "a song of 10 s or less becomes one padded window; when the file's stated length "
         "is wrong, the song is decoded once and cut (`how` = *short*, *whole* or *seek* in the log)."),
        ("Quality:", "6 snippets reach a cosine of 0.995 to the whole-song vector; 3 snippets would reach 0.983 at "
         "half the time (roadmap I12, for a slower box)."),
    ])
    D.h(2, "3.4  The short-time Fourier transform")
    D.p("Sound is a mix of frequencies. The [[Fourier transform]] splits a signal into them; the "
        "[[short-time Fourier transform|STFT]] (STFT) does this for short, overlapping frames, so we see how the "
        "frequencies change over time [3]. For frame *m* and frequency bin *k*:")
    D.formula("X(m, k) = Σₙ x(n + m·H) · w(n) · e^(−2πi·k·n / N)", "n = 0 … N−1")
    D.table(["Parameter", "Value in Incipit", "Meaning"], [
        ["N (`N_FFT`)", "2,048 samples = 42.7 ms", "frame length; frequency resolution 48,000 / 2,048 = 23.4 Hz"],
        ["H (`HOP`)", "480 samples = 10 ms", "step between frames: 100 frames per second, 1,001 per 10-s window"],
        ["w(n)", "periodic [[Hann window]]", "w(n) = ½ − ½·cos(2πn/N): fades each frame in and out to avoid "
         "spectral leakage [5]"],
        ["Edges", "mirrored padding of N/2", "frames centred on their time (librosa's `center=True`)"],
        ["Power", "|X(m, k)|²", "energy per frequency bin and frame"],
    ], [3.0, 4.5, 9.1], size=9, caption="STFT parameters (`soundprint/model.py`)")
    D.p("In the code this is three lines of numpy: a sliding window view of the padded signal, multiplied by the Hann "
        "window, and `np.fft.rfft` (`model.mel_db`).")
    D.h(2, "3.5  The mel scale")
    D.p("Human hearing does not perceive pitch linearly: the step from 100 to 200 Hz sounds much larger than from "
        "10,100 to 10,200 Hz. The [[mel scale]] [6] spaces frequencies as we hear them: about linearly below 1 kHz, "
        "logarithmically above. Incipit uses Slaney's version [8] (as librosa does by default):")
    D.formula("mel(f) = f / (200/3)                         for f < 1,000 Hz")
    D.formula("mel(f) = 15 + ln(f / 1,000) / (ln 6.4 / 27)    for f ≥ 1,000 Hz")
    D.p("A [[mel filterbank]] of 128 triangular filters, evenly spaced on the mel scale from 0 to 14 kHz, sums the "
        "2,048-point spectrum into 128 bands. Each triangle is normalised to the same area (Slaney norm), so wide "
        "high bands are lower.")
    D.figure(F("filterbank.png"), "The 128 mel filters (computed with `soundprint.model.mel_filters`)", index="mel filterbank")
    D.h(2, "3.6  Loudness in decibels")
    D.p("The energy in a band spans many orders of magnitude, and we hear loudness roughly logarithmically. So the "
        "band energies are converted to [[decibels]]:")
    D.formula("S(b, m) = 10 · log₁₀( max(mel(b, m), 10⁻¹⁰) )")
    D.p("The result is a **log-mel spectrogram**: an image of 128 bands × 1,001 frames per snippet. The figure below "
        "shows one, computed from a real song with the add-on's own code. The horizontal stripes are tones held over "
        "time, the vertical lines are drum hits; this image is all the model sees.")
    D.figure(F("spectrogram.png"), "Waveform and log-mel spectrogram of one 10-second snippet", index="spectrogram")
    D.p("The numpy implementation reproduces AudioMuse-AI's librosa-based vectors exactly (cosine 1.000, measured "
        "2026-10-27), so the model sees precisely the input it was trained on.")
    D.h(2, "3.7  From spectrogram to meaning: a neural audio embedding")
    D.p("A spectrogram still describes sound at the level of frequencies. To compare songs by what they *are* — "
        "instruments, rhythm, timbre, production, style — Incipit uses a neural network that maps each spectrogram to "
        "a point in a 512-dimensional space, an [[embedding]]. Songs that sound alike land close together.")
    D.h(3, "Contrastive learning: CLAP")
    D.p("[[CLAP]] (Contrastive Language–Audio Pretraining) [9] learns from pairs of audio and text descriptions, as "
        "CLIP [11] does for images. It has two encoders, one for audio and one for text. Training pulls the vectors of "
        "matching pairs together and pushes non-matching ones apart (a contrastive loss [10]). Afterwards, the audio "
        "encoder alone places sounds in a space where distance reflects meaning that people describe in words "
        "(\"a fast techno track with a heavy bass\"). LAION's music CLAP uses the HTS-AT audio transformer [9b].")
    D.h(3, "Knowledge distillation: DCLAP")
    D.p("The full CLAP audio encoder is too slow for 156,000 songs on a CPU. [[DCLAP]] [13] (AudioMuse-AI Distilled "
        "CLAP) is a smaller *student* network trained to reproduce the *teacher's* vectors [14]: it gives nearly the same "
        "embedding at a fraction of the cost. Incipit runs release v1 (`model_epoch_36.onnx`, about 22 MB) with "
        "[[ONNX Runtime]] [15] on the CPU, one process per CPU core pair, with spinning threads switched off so that "
        "the analysis processes don't steal CPU from each other.")
    D.callout("Licence.", "The DCLAP weights are AGPL-3.0; Incipit is MIT. So the model is **not** shipped with the "
              "add-on: the set-up downloads it from the DCLAP release, checks both files' SHA-256 and writes a licence "
              "note next to them. The teacher (LAION CLAP, CC0) would be the fallback, 5 to 6 times slower (I14).",
              fill="FFF7E6", edge="C77C02")
    D.h(3, "What the embedding captures — and what not")
    D.p("The embedding reflects what can be heard: instrumentation, timbre, rhythm and tempo feel, density, "
        "production, voice, and through them genre and era. It knows nothing about the artist, the scene, the lyrics' "
        "meaning or the history around a song. That is why Incipit adds Character and Intent: the sound engine finds "
        "songs that *sound* right; the checks keep those that *belong*.")
    D.h(2, "3.8  One vector per song")
    D.p("Each snippet gives one 512-number vector. The song's [[sound print]] is their **mean**, scaled to length 1 "
        "(L2 normalisation, `Model.embed`):")
    D.formula("v = m / ‖m‖,    m = (1/S) Σₛ e(snippetₛ)")
    D.p("It is stored as 512 half-precision floats (float16: about three significant digits, 1 KB per song) in "
        "`sound.db`. For the search all vectors are kept as one float32 matrix in `vectors.npy` (about 306 MB for "
        "156,000 songs). A stored vector carries its **analysis version** (`dclap-v1/snippets-6/preroll-1`); a "
        "vector of another version is made again at the next analysis.")

    # ---------------------------------------------------------------- chapter 4
    D.h(1, "4  Pattern detection and search", page_break=True)
    D.p("With a sound print for every song, \"songs that sound alike\" becomes a geometric question: which points "
        "lie near the seed's point? This chapter explains the measure, the search, how variety is made, and three "
        "further patterns the sound engine detects in the prints.")
    D.h(2, "4.1  Similarity as an angle")
    D.figure(F("cosine.png"), "Cosine similarity: the angle between two sound prints", index="cosine similarity")
    D.p("Incipit measures similarity with the [[cosine similarity]] [19]: the cosine of the angle between two vectors. "
        "Because every sound print has length 1, it is simply their dot product. It ignores the vectors' lengths and "
        "compares only their direction — what the song sounds like, not how loud the model's response was.")
    D.h(2, "4.2  Finding the nearest songs")
    D.p("The search is **exact** and brute-force: one matrix–vector product computes the similarity of the seed to "
        "every song at once (156,415 × 512 multiplications and additions, about 80 million). numpy does this in "
        "well under a second. Only the songs actually needed are sorted: `np.argpartition` finds the top *k* in linear "
        "time, then only those are sorted.")
    D.p("Reading the 306 MB matrix is the slow part. `Store.matrix` therefore keeps `vectors.npy` with a stamp (the "
        "newest analysis time and the row count). If the store changed by fewer than 2,000 rows, the saved matrix is "
        "memory-mapped and only the new rows are appended; otherwise it is written anew. While the analysis runs, "
        "searches stay fast (1.3 s per search at 10,000 songs before this, measured).")
    D.callout("For reviewers.", "An approximate index (HNSW, IVF) would be faster for very large libraries but adds a "
              "dependency and a rebuild step. At this size an exact search is simple and fast enough; roadmap I11 "
              "lists the next steps (float16 matrix, a resident helper process).")
    D.h(2, "4.3  Variety: reach and a weighted random draw")
    D.p("Taking simply the nearest 25 songs gives a very cohesive mix that is the same every time. Incipit's "
        "[[variety]] (0 to 9) controls two things: how deep into the order by sound a mix reaches, and how random it "
        "is (`soundprint/neighbours.py`).")
    D.h(3, "Reach")
    D.p("For a mix of *c* songs in a library of *L* songs, the reach grows geometrically with the variety *v*:")
    D.formula("reach(v) = min( L,  max( round(1.5·c),  round( c · (L/c)^(v/9) ) ) )")
    D.p("At variety 0 a mix draws from the nearest 1.5 × *c* songs (38 for a mix of 25); each step goes the same "
        "factor deeper; at 9 the whole library is in reach. The next figure shows these depths on the real similarity curve "
        "of a seed: similarity falls slowly over the first thousands of songs and steeply at the end.")
    D.figure(F("similarity.png"), "Similarity of all songs to one seed, and the reach of each variety", index="variety:reach")
    D.h(3, "The draw")
    D.p("Within the reach, each song of the mix is drawn at random, the nearer the likelier. A song at rank *r* gets "
        "the weight")
    D.formula("w(r) = 1 / r^p,     p = 1 − 0.3 · v/9     (p = 1 at variety 0, 0.7 at variety 9)")
    D.p("With *p* = 1 the draws spread evenly over the orders of magnitude (about as many from ranks 2–4 as from "
        "1,000–2,000); with *p* < 1 far songs get more. Near and far songs therefore alternate, and a loose mix keeps "
        "finding its way back to the seed. The weighted sampling without replacement uses the method of "
        "[[Efraimidis–Spirakis|Efraimidis and Spirakis]] [18]: each candidate gets the key *u*^(1/*w*) for a uniform random *u*, and the "
        "largest keys win — in one vectorised step. (In the code: `(rank)^p · ln(1 − u)`, sorted, which orders the same "
        "way.)")
    D.figure(F("variety.png"), "Where the songs of a mix come from at different varieties", index="variety:draw")
    D.p("Measured on the whole library (2026-10-29): for Kraftwerk's \"Vitamin\", rock and metal sit at ranks 34,000 to "
        "100,000. At variety 9 about a fifth of a mix comes from there, and about 29 % of the songs fit the seed's "
        "profile (54 % at the old setting). Such a loose mix is then shaped by Character and Intent.")
    D.h(2, "4.4  Rules after the draw")
    D.p("The draws come first; then `nearest` walks through them in order and applies three rules:")
    D.bullets([
        ("No artist repeat within N:", "a song whose artist is among the last N songs of the mix (the seed first) is "
         "passed over. Artist names are compared loosely by `mixassist.cache.artist_key` (\"Medeski Martin & Wood\" = "
         "\"Medeski, Martin and Wood\"), the one rule for \"the same artist\" in the whole add-on."),
        ("The same song only once:", "the same artist and title on another album, a copy, or the same file under "
         "another spelling of its path (`file_key`, case-blind on Windows; F45, F50)."),
        ("Leave out:", "songs the caller lists — a station's played, queued and turned-down songs (I34) — and, for "
         "an Epoch station, songs outside its time window. These are removed *before* the draw, so ranks stay those "
         "of the whole library."),
    ])
    D.p("When the rules pass over all drawn songs, the mix continues with the songs further out, nearest first.")
    D.h(2, "4.5  Pattern: the same recording")
    D.p("Two sound prints of the same artist that are almost identical are the same recording under another title "
        "or edition. Measured on 400 undated songs: true duplicates reach cosines of 0.9939 to 0.9997 "
        "(\"One of a Kind\" / \"One of the Kind\"), while two different songs of one band reached at most 0.9912. "
        "`years.same_recordings` therefore treats ≥ 0.993 as *the same recording* and gives an undated song the "
        "year of its dated twin.")
    D.h(2, "4.6  Pattern: a song's era from its neighbours")
    D.p("Production sound tells its time, roughly. For an undated song, `years.era_hints` takes its 20 nearest dated "
        "songs by **other** artists (an album's songs are each other's nearest) and keeps their years. A "
        "[[k-nearest-neighbour|k-nearest neighbours]] vote [20] then decides whether the song may belong to a time window: at least 20 % of the "
        "neighbours within the window ± 2 years.")
    D.p("Measured on 3,000 dated songs: the neighbours' median year misses the true year by 5 years (within 5 years "
        "for 52 %), pulled towards the library's middle. As a *filter* it is useful: for 1975–1979 it keeps 77 % of "
        "the songs of those years while passing 27 % of all — three times better than chance.")
    D.h(2, "4.7  Pattern: compilations whose dates can be trusted")
    D.p("Half of the library sits on compilations, which carry the compilation's date, not the song's. "
        "`years.trusted_compilations` detects compilations whose date cannot bound their songs (a series of today "
        "tagged 1978): a song is *late* when its artist's own album with it, or the artist's first album, came more "
        "than two years after the compilation's date. With more than a third of the known songs late, the "
        "compilation is not trusted. Compilations dated song by song (several different song dates) give each song "
        "its own year.")

    # ---------------------------------------------------------------- chapter 5
    D.h(1, "5  Profile statistics: Character", page_break=True)
    D.p("[[Character]] compares each song's profile with the seed's. The profile has eight values, rated once per "
        "album by the AI and cached. This chapter explains the statistics that turn two profiles into a yes or no "
        "(`mixassist/fit.py`, `mixassist/assist.py`).")
    D.h(2, "5.1  The eight values")
    D.table(["Value", "0", "2.5", "5", "7.5", "10"], [
        ["energy", "still", "gentle", "steady", "driving", "ferocious"],
        ["exploration", "conventional", "familiar", "inventive", "adventurous", "radical"],
        ["mood", "bleak", "brooding", "bittersweet", "sunny", "exuberant"],
        ["making", "hand-played", "mostly played", "mixed", "mostly programmed", "machine-made"],
        ["danceability", "for listening", "swaying", "groovy", "danceable", "dancefloor"],
        ["production", "raw", "rough", "natural", "clean", "glossy"],
        ["form", "open", "instrumental", "loose", "song", "vocal-led"],
        ["sounding year", "≤ 1964", "1965–79", "eighties", "1990–2009", "2010 +"],
    ], [2.8, 2.6, 2.6, 2.6, 3.0, 3.0], size=8.5, caption="The profile dimensions (version 2) and their slider words")
    D.p("They were chosen by a **dependency study**: 22 candidate properties were rated for the pilot's albums, and "
        "correlations and factor analysis showed which measure the same thing. Version 2 takes one value per "
        "independent axis plus danceability; it behaves like 5.7 independent dimensions of 8 (the first guess: 4.4).")
    D.figure(F("character.png"), "How Character decides", index="Character:decision", landscape=True)
    D.h(2, "5.2  Seed weights: what makes the seed unusual")
    D.p("The values on which the seed is unusual carry its intent. For each value *k*, with the library's mean μₖ "
        "and standard deviation σₖ over all rated albums:")
    D.formula("rawₖ = max(0.1, |seedₖ − μₖ| / σₖ),        weightₖ = rawₖ / mean(raw)")
    D.p("For an avant-jazz seed: form 2.1, exploration 2.0, sounding year 1.3, but energy 0.3 because its energy is "
        "ordinary. Without weights the agreement with the listener's verdicts fell from 1.00 to 0.78 (AUC).")
    D.h(2, "5.3  A robust spread")
    D.p("Deviations are measured in units of a spread. A plain standard deviation is pulled by the very outliers we "
        "want to find, so Incipit uses the [[median absolute deviation]] (MAD) [22], scaled to match a standard "
        "deviation for normal data, with a floor of 1 point (5 years for the sounding year) — about the rating noise:")
    D.formula("spreadₖ = max( floorₖ, 1.4826 · median |xₖ − median(xₖ)| ) / weightₖ")
    D.h(2, "5.4  Misfit: a distance that knows the values overlap")
    D.p("The eight values are not independent (energetic music is often more danceable). Adding up squared "
        "deviations would count shared information twice. The misfit is therefore a [[Mahalanobis distance]] [23]: "
        "the deviation vector *z* weighted by the inverse of the library's correlation matrix *R*:")
    D.formula("zₖ = (songₖ − seedₖ) / spreadₖ,        misfit = √( zᵀ R⁻¹ z / 8 )")
    D.p("To avoid over-amplifying rare value combinations, *R* is **shrunk** 30 % towards the identity "
        "(R' = 0.7·R + 0.3·I), an idea known from covariance shrinkage [24]. The 8 × 8 inverse is computed in plain "
        "Python by Gauss–Jordan elimination (`stats.invert`): Kodi's Python has no numpy. Tested alternatives (cubic, "
        "maximum, signed deviations) ranked no better and flagged more fitting songs.")
    D.h(2, "5.5  Relative misfit and the fixed scale")
    D.p("A fixed threshold on the misfit does not transfer between mixes. What does: the misfit relative to the "
        "**typical** misfit of songs near the seed. The [[Tolerance]] sets the limit:")
    D.formula("relative = misfit / typical,     pass if relative ≤ limit")
    D.table(["Tolerance", "Focused", "Close", "Balanced (default)", "Open", "Adventurous", "Off"], [
        ["limit", "1.0", "1.1", "1.2", "1.35", "1.5", "no Character check"],
    ], [2.6, 2.0, 2.0, 2.8, 2.0, 2.6, 2.6], size=8.5)
    D.p("Until F40, *typical* was the median of the list being checked, so a loose candidate list looked closer than it "
        "was. Now it comes from a **fixed scale per seed**: the seed's nearest 120 songs by sound that have a rating "
        "(up to 35 units) define the spreads and the typical misfit (`assist.character_scale`). Every list checked "
        "against that seed is then measured alike. With fewer than 5 rated neighbours the list's own spread is used.")
    D.h(2, "5.6  The single-value rule")
    D.p("A song can be close overall and still clearly wrong on one value. A second rule flags a song when one value "
        "differs from the seed's by **5 points or more** (25 years for the sounding year). On the pilot's mixes this "
        "caught 45 of the AI's 47 outliers instead of 36, flagging 2 of 70 fitting songs instead of 1.")
    D.h(2, "5.7  Drift for Radio")
    D.p("A station's reference profile can move with the songs it plays. After each added song the profile moves "
        "towards it so that it has gone half the way after *h* songs (the half-life), whatever the refill size:")
    D.formula("profile ← (1 − α) · profile + α · song,     α = 1 − 2^(−1/h)")
    D.p("*h* = 0 keeps the picked song's profile (*stay close*), 60 drifts slowly (about 4 hours), 20 wanders freely "
        "(about 80 minutes) — `assist.drift_reference`.")
    D.h(2, "5.8  How the numbers were calibrated")
    D.p("The constants are not guesses; they were measured in a pilot on the developer's library (486 albums and 200 "
        "compilation tracks rated, dry runs on real mixes, the listener's own verdicts). Agreement is measured as "
        "[[AUC]] (area under the ROC curve: 1.0 perfect ranking, 0.5 chance) [25].")
    D.table(["Test", "Result", "Consequence"], [
        ["Stability of ratings", "repeats agree at r = 0.90–0.99, also for unknown music", "one cache for all times"],
        ["Profile vs. AI judgement", "AUC 0.95–1.00 on five mixes; against the listener 0.97", "the values reproduce the holistic view"],
        ["Threshold", "1.2 × typical caught 33 of 47 outliers, flagged 1 of 70 fitting songs", "Balanced = 1.2"],
        ["Seed weighting", "unweighted 0.78, weighted 1.00 (listener's verdicts)", "weights are essential"],
        ["Single-value rule", "≥ 5 points / 25 years: 45 of 47 outliers, 2 false", "built 2026-10-17"],
        ["Mainstream reference", "150 famous albums as the basis for \"unusual\": no better", "keep the library as basis"],
    ], [3.8, 7.6, 5.2], size=8.5, caption="Calibration results from the pilot (concept_ai_mix_assist.md)")
