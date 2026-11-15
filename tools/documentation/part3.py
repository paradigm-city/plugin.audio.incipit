"""Part IV (design, high detail) and Part V (review, open issues, outlook)."""
from doclib import GREY
from part1 import F

MODULES = {
    "main.py": "The plugin: every screen and action of the add-on, the mix store (files and sidecars), the current mix, "
               "saved mixes, consistency and repair, the metadata cache, track labels and artwork, the information "
               "window, Radio and Discovery from the plugin's side, favourites, and the plumbing that connects the "
               "checks (`mixassist`) and the sound engine (`soundprint.client`) to Kodi. Entry point: `router()`.",
    "service.py": "The background service: one loop with a tick per second for Discovery (excerpt timer, playlist "
                  "buffer), Radio (follow the playlist, refill, stop), screen redraws, the checks worker, cover "
                  "collages, the sound engine's analysis start, metadata refresh and the saved-mix consistency check. "
                  "At start it takes over the old ID's data and migrates settings. Imports `main.py` for shared logic.",
    "context_mix.py": "The library context entry *Create Incipit mix*: builds a plugin URL from the selected song and "
                      "runs it.",
    "context_radio.py": "The library context entry *Start Incipit radio*: the same for `radio_start_seed`.",
    "logs.py": "Logging by area (general, mixing, ai, radio, discovery, checks), each with its switch; errors and "
               "warnings always. Also the add-on ID and the migration of the old logging switches.",
    "musicip_dormant.py": "MusicIP's code (mix request, parameters, library reload), unused since 2026-10-29 and kept for "
                          "reference.",
    "mixassist/assist.py": "The checks' core: `analyze` (status per track), `character_scale` (the fixed scale), "
                           "`passes`, `tidy_up` (the plan for a mix: intent, statuses, replacements from submixes), "
                           "`choose_additions` (More like this and Radio), `drift_reference`.",
    "mixassist/checks.py": "The Intent prompts: the seed-intent prompt, the intent prompt, seven perspectives, the JSON "
                           "schema, track lines, parsing of verdicts and names, Epoch's years (`epoch_span`).",
    "mixassist/claude.py": "Calls to the Claude Code CLI: finding the CLI, the environment without API keys, the command "
                           "line, structured output, failure classes, usage reporting.",
    "mixassist/rating.py": "Rating units the cache doesn't have: batches of 20 albums or 25 tracks, run in parallel; "
                           "answers validated, clamped and stored.",
    "mixassist/cache.py": "`ratings.db`: the rating cache (`RatingCache`) and the verdict cache (`VerdictCache`); keys "
                          "for units (`album_key`, `track_key`), `artist_key`, `is_compilation`, `normalize`.",
    "mixassist/dimensions.py": "The eight profile values (version 2) with slider labels, anchor artists and notes; "
                               "the rating prompt and its JSON schema.",
    "mixassist/fit.py": "Misfit maths: seed weights, robust spreads, shrunk inverse correlation, misfit, the reason "
                        "in words.",
    "mixassist/stats.py": "Small statistics in plain Python: mean, standard deviation, Pearson, correlation matrix, "
                          "median, robust spread, matrix inverse.",
    "mixassist/library.py": "From paths to rating units via Kodi's JSON-RPC: albums, compilation tracks with their own "
                            "years, unknown files from their names.",
    "mixassist/chart.py": "PNG charts for the information window (line, bar), with Pillow when Kodi has it, else a "
                          "plain PNG writer.",
    "mixassist/usage.py": "Usage events (`usage.db`) and their summaries for the statistics.",
    "mixassist/trace.py": "The AI area's log: every request and answer in full, prompts once per session.",
    "soundprint/__init__.py": "Model name, snippet count, pre-roll, the model files' SHA-256, the analysis version.",
    "soundprint/__main__.py": "The command line: setup, check, fetch-model, analyse, stop, status, neighbours, failures.",
    "soundprint/analyse.py": "The analysis: plan (what's new, changed, taken over), worker pool, status, stop file, "
                             "following Kodi's process, `analysis.log`.",
    "soundprint/audio.py": "Decoding to mono 48 kHz, ID3 workaround, damaged frames, snippet positions and cutting, "
                           "silence.",
    "soundprint/model.py": "Mel filterbank, log-mel spectrogram, the ONNX model, the song's vector; downloading and "
                           "checking the model.",
    "soundprint/neighbours.py": "The search: seed vector (analysed on the spot if needed), cosine, reach and weighted "
                                "draw, artist rule, same-song rule, leave-out, time window.",
    "soundprint/store.py": "`sound.db` and the search matrix (`vectors.npy`), with incremental update.",
    "soundprint/songs.py": "Which songs to analyse: Kodi's music database (read-only) or a list; artist and title "
                           "lookups.",
    "soundprint/years.py": "A year for every song: album dates, compilations dated song by song, trusted compilations, "
                           "same recordings by sound, era hints; the time window for Epoch.",
    "soundprint/state.py": "What the add-on and the tool share on disk (status, stop file, paths), process checks and "
                           "lower priority — plain Python, readable by Kodi's Python too.",
    "soundprint/client.py": "The add-on's side of the sound engine (Kodi's Python): neighbours, start/stop analysis, "
                            "set-up, counts, the status window's lines.",
    "tools/make_icon.py": "Draws the add-on's icon.",
    "tools/make_icons.py": "Draws the menu icons from Font Awesome glyphs.",
    "tools/make_settings.py": "Generates repeated parts of `resources/settings.xml`.",
}

MAIN_AREAS = [
    (1, 600, "Basics: keymap, URLs, notifications, settings, mix parameters, dialogs"),
    (601, 821, "Profile folder; Discovery playback started by the plugin"),
    (822, 1365, "Metadata cache (SQLite), sidecar snapshots, refresh queue; mix file paths"),
    (1366, 2475, "The current mix, saved mixes, consistency, music sources, repair readiness, cleanup"),
    (2476, 2599, "The source of mixes: seed, fetch_mix (sound engine)"),
    (2600, 2962, "Browse URLs and focus; mix edits: remove, More like this, Less like this"),
    (2963, 3973, "Player metadata, JSON-RPC, library lookups, repair hints, candidate scoring, repair"),
    (3974, 4394, "Metadata parsing, Kodi's track-name template, ListItem decoration"),
    (4395, 4657, "Info key, track origins, list items for tracks and saved mixes"),
    (4658, 5042, "Icons, second lines, the first screen, Mix mode, Discovery actions"),
    (5043, 5657, "Radio mode (plugin side), Discovery control (skip, dialog hold, mix from snippet)"),
    (5658, 5884, "Saved-mix listings, generate and browse mixes"),
    (5885, 6147, "Mix history"),
    (6148, 6412, "Information window; Claude statistics"),
    (6413, 6494, "The sound engine's set-up and analysis (Settings > Advanced)"),
    (6495, 6919, "Skin colours; the mix information pages and charts"),
    (6920, 7270, "A saved mix as a compilation album; cover collages"),
    (7271, 7492, "What plays: backgrounds, playing-mix detection, playback"),
    (7493, 7854, "Settings dialog; the checks' settings, store and reporting"),
    (7855, 8139, "Checks for new mixes and More like this; per-mix choices (openness, perspective)"),
    (8140, 8303, "Names; the checks' request queue and its processing"),
    (8304, 8518, "Checks for Radio: parameters, years, batches, start and refill checks"),
    (8519, 9225, "Station information and favourite stations"),
    (9226, 9672, "router(): the 54 actions"),
]
SERVICE_AREAS = [
    (1, 1168, "Discovery mode: state, rolling playlist buffer, excerpt timer, player events, external playback"),
    (1169, 2012, "Radio mode: tick, playlist edits, checks in a thread, refills, backlog, artwork, screen redraws"),
    (2013, 2238, "Saved-mix consistency check, missing-file search, notifications; start-up resets"),
    (2239, 2947, "Background metadata refresh and the delayed view refresh"),
    (2948, 3062, "Checks worker, cover collages, the sound engine's analysis start"),
    (3063, 3392, "Settings reload, take-over of the old ID's data, migrations, readiness note, main()"),
]


def part4(D, cat, facts):
    D.h(1, "Part IV · Design in detail", page_break=True)
    D.p("Modules, algorithms, sequences, databases, dependencies and interfaces, down to the level of each function. "
        "The complete list of functions is Appendix A.", italic=True, color=GREY)

    # ---------------------------------------------------------------- 15 modules
    D.h(1, "15  Module reference")
    rows = []
    for mod, e in cat.items():
        funcs = len(e["functions"]) + sum(len(c["methods"]) for c in e["classes"])
        rows.append([f"`{mod}`", f"{e['lines']:,}", str(funcs), MODULES.get(mod, e["doc"])])
    D.table(["Module", "Lines", "Func.", "Purpose"], rows, [3.9, 1.3, 1.2, 10.2], size=8,
            caption="All modules (lines and functions from the source, 2026-11-15)")
    D.h(2, "15.1  main.py by area")
    D.p("`main.py` is organised by area in this order; the section comments in the file mark most of them.")
    rows = []
    funcs = cat["main.py"]["functions"]
    for a, b, text in MAIN_AREAS:
        n = sum(1 for f in funcs if a <= f["line"] <= b)
        rows.append([f"{a:,}–{b:,}", str(n), text])
    D.table(["Lines", "Func.", "Area"], rows, [2.6, 1.4, 12.6], size=8.5, caption="Areas of main.py")
    D.h(2, "15.2  service.py by area")
    rows = []
    funcs = cat["service.py"]["functions"]
    for a, b, text in SERVICE_AREAS:
        n = sum(1 for f in funcs if a <= f["line"] <= b)
        rows.append([f"{a:,}–{b:,}", str(n), text])
    D.table(["Lines", "Func.", "Area"], rows, [2.6, 1.4, 12.6], size=8.5, caption="Areas of service.py")
    D.p("Classes in the service: `DiscoveryPlaybackMonitor(xbmc.Player)` turns the player's stop, end and error into a "
        "Discovery stop; `ServiceMonitor(xbmc.Monitor)` notes Kodi's finished library scan (for the analysis) and "
        "reloads settings when they change (F39).")

    # ---------------------------------------------------------------- 16 algorithms
    D.h(1, "16  Key algorithms in the code", page_break=True)
    D.p("Step-by-step descriptions of the functions that carry the add-on's logic. Read them next to the code.")

    D.h(2, "16.1  soundprint.neighbours.nearest — the search")
    D.bullets([
        "Get the seed's vector from the store; if missing and the file is local, analyse it on the spot and store it.",
        "Load the matrix (`Store.matrix`) and compute `similarity = matrix @ seed` (all songs at once).",
        "Build the leave-out set: the caller's paths (a station's songs) and, with a time window, the songs outside it "
        "(`years.within`; uncertain years allowed up to 25 % of the mix).",
        "Order by similarity (`argsort`, or `argpartition` when no rules apply); remove the seed and the leave-out "
        "songs, keeping the original ranks.",
        "Unless `in_order`: draw the first `reach` positions with keys `rank^p · ln(1−u)` and sort by key (weighted "
        "sampling without replacement); the rest follow in order.",
        "Walk the positions: skip the same song (artist + title, file key, path twins), skip an artist among the last "
        "*window* songs, limit uncertain years; stop at *count* songs.",
        "Return `(path, similarity, rank)` triples, where the seed vector came from, and counts of what each rule left out.",
    ], numbered=True)
    D.h(2, "16.2  soundprint.analyse.plan and run — the analysis")
    D.bullets([
        "Refuse to start if another analysis of the same data folder runs (`state.running`).",
        "Lower the priority; write `status.json` (*planning*); remove a stale stop file.",
        "Plan: for every path of Kodi's library, `os.stat`. Unchanged (same size, mtime within 1 ms, same version) → "
        "skip. Failed before and unchanged → skip (unless `--retry-failed`). Same file under another spelling of its "
        "path → take the stored row over. Missing on disk → count. Else → to do.",
        "Load the model once in the main process (a worker whose start fails would be restarted without end).",
        "Start a *spawn* pool of workers (CPU threads / 2, 2 ONNX threads each; numpy's own threads set to 1).",
        "For each result: store the vector or the error; commit every 25 songs; every 5 s write the status with "
        "seconds per song and an ETA; stop after the songs in hand when the stop file exists or Kodi has closed.",
        "Finally terminate the pool, commit, write the final status (*finished*, *stopped*, *failed*).",
    ], numbered=True)
    D.h(2, "16.3  mixassist.assist.tidy_up — keeping a mix on track")
    D.bullets([
        "Resolve paths to units; rate the units the cache lacks.",
        "Intent on: state the intent from the perspective and judge all tracks in one call (or judge against the "
        "listener's own intent, or one stated before for the same seed and perspective, reusing cached verdicts).",
        "`analyze`: per track the Character misfit on the fixed scale, the single-value rule and the verdict → status "
        "*seed*, *fits*, *borderline*, *flagged*, *outlier* or *unrated*.",
        "For each outlier (outside the protected zone), find a replacement — round 1: a submix seeded from the nearest "
        "earlier track that clearly fits (gaps with the same submix seed share one larger submix); round 2: submixes "
        "from other clearly fitting tracks, nearest first; fallback: the seed's own submix.",
        "Candidates are scored with both signals against the master seed (one AI call for all), must pass every check "
        "that is on and keep the artist window; the one closest in profile wins.",
        "Return the plan (intent, rows, replacements, removals, *rebuild suggested* if over a third fails). The caller "
        "applies it to the playlist and the sidecar and records history and Undo.",
    ], numbered=True)
    D.h(2, "16.4  mixassist.assist.choose_additions — More like this and Radio")
    D.p("The selected song and the source's candidates for it form a small mix with the selected song as its seed. "
        "Candidates are examined in batches (18 for Radio) until enough pass every check that is on, in the order the "
        "source gave them, keeping the artist rule against the songs around the insertion point (or the station's "
        "queue). With checks off, the first candidates are taken as they are.")
    D.h(2, "16.5  service.run_radio_tick — a station's heartbeat")
    D.bullets([
        "*seeking*: after a 3 s grace period, if Discovery's snippets stopped, end the radio; if a new snippet plays, "
        "ask for a redraw of the Radio screen.",
        "*playing*: if audio stopped for more than 3 s, or video plays, end the station with the reason.",
        "Follow edits of Kodi's playlist (`follow_playlist_edits`): removed songs leave the queue and stay *seen*; "
        "foreign songs end the station.",
        "If a check thread finished, apply its result (songs to append, rejected songs, the drifted profile, events).",
        "If fewer than 3 songs are left after the playing one: start a checked refill in a thread, or (checks off) "
        "refill at once from the last queued songs (up to 3 tried as seeds); after a failure wait 60 s, doubling up to "
        "10 minutes while the source keeps failing.",
        "Prune the backlog to 10 played songs; refresh the station's artwork when enough covers are known.",
    ], numbered=True)
    D.h(2, "16.6  Discovery's rolling playlist buffer (service)")
    D.p("Discovery keeps about 10 played songs behind the current one and 10 ahead (`DISCOVERY_BACKLOG_SIZE`, "
        "`DISCOVERY_BUFFER_SIZE`); when fewer than 5 are ahead, random library songs are appended. Each song starts at "
        "its offset (default 33 % of its length) and plays for the excerpt length (Fibonacci steps 2–55 s, default 21); "
        "then the service calls `Player.GoTo` on the next position. A manual skip updates the state at once so the old "
        "timer does not skip twice. While the mix dialog is open the timer holds; on cancel it skips if the dialog was "
        "open longer than one excerpt. Playback that is not Discovery's (another file) stops Discovery without "
        "touching the new playback.")
    D.h(2, "16.7  main.score_repair_candidate and choose_repair_candidate — repair")
    D.p("For a missing file, candidates come from Kodi's library (same file name, relaxed name, text search). Each is "
        "scored against hints taken from the old path (title, artist, album, year, track number from the file and "
        "folder names):")
    D.table(["Evidence", "Points"], [
        ["strong title match", "+90"], ["strong title match from the file name", "+70"],
        ["track number match / possible match", "+40"], ["artist match", "+35"], ["album match", "+25"],
        ["artist partial match; folder/artist hint; year match", "+20 each"], ["folder/album hint", "+15"],
        ["contradicting evidence", "minus points, with the reason logged"],
    ], [10.0, 6.6], size=8.5, caption="Repair scoring")
    D.p("Automatic repair requires exactly one high-confidence candidate with at least 120 points and a lead of at "
        "least 35 over the next one, and that Kodi's library no longer lists the missing file. Otherwise the listener "
        "chooses in the foreground; the add-on never guesses.")

    # ---------------------------------------------------------------- 17 sequences
    D.h(1, "17  Sequences and states", page_break=True)
    D.p("The four diagrams on the following landscape pages show how the parts work together over time. Read them "
        "top to bottom; solid arrows are calls or messages, dashed arrows are answers.")
    D.bullets([
        ("Generate mix from playing audio.", "The listener's action runs a plugin URL. The plugin asks the sound engine, "
         "writes the mix and starts it, queues the checks and ends. Seconds later the service's worker rates, states "
         "the intent, judges, replaces outliers and patches the playlist beyond the protected zone."),
        ("A station's refill.", "The radio tick notices the station running low and starts a check thread. The thread "
         "asks the sound engine for 75 candidates the station hasn't had, judges them in batches until enough fit, and "
         "hands the result back to the next tick, which appends the songs."),
        ("The analysis.", "The service decides an analysis is due and starts it detached. The analysis plans, runs a "
         "pool of workers and writes `sound.db` and its status until it is done, stopped, or Kodi closes."),
        ("Radio's phases.", "off → seeking (scanning snippets) → playing (an endless mix); *Scan again* goes back to "
         "seeking; many events end a station."),
    ])
    D.figure(F("seq_generate.png"), "Sequence: Generate mix from playing audio", index="sequence:generate mix", landscape=True)
    D.figure(F("seq_radio.png"), "Sequence: a station's refill with the checks on", index="sequence:radio refill", landscape=True)
    D.figure(F("seq_analysis.png"), "Sequence: the sound engine's analysis", index="sequence:analysis", landscape=True)
    D.figure(F("radio_states.png"), "Radio mode: the phases of a station", index="Radio mode:states", landscape=True)

    # ---------------------------------------------------------------- 18 databases
    D.h(1, "18  Database design", page_break=True)
    D.figure(F("er.png"), "Databases and their tables", index="database design", landscape=True)
    D.h(2, "18.1  sound.db (soundprint/store.py)")
    D.table(["Column", "Type", "Meaning"], [
        ["path", "TEXT, primary key", "the file path as Kodi stores it"],
        ["size, mtime", "INTEGER, REAL", "the file's size and change time when analysed; a change means a new analysis"],
        ["version", "TEXT", "analysis version, e.g. `dclap-v1/snippets-6/preroll-1`"],
        ["length", "REAL", "the song's length in seconds"],
        ["vector", "BLOB", "512 × float16 (1,024 bytes); NULL if the file could not be read"],
        ["error", "TEXT", "why the file could not be read"],
        ["analysed", "REAL", "when; also the stamp for the matrix cache"],
    ], [3.0, 3.6, 10.0], size=8.5, caption="sound.db, table songs")
    D.p("Design choices: one row per **file**, not per Kodi song ID, so the store survives a rebuilt Kodi library; "
        "failures are rows too, so a broken file is not retried until it changes. Two spellings of one path (Windows "
        "ignores case) can both exist; the search takes the one Kodi knows (F45, F50). Rows of songs that left the "
        "library are not yet removed automatically (F36, I9).")
    D.h(2, "18.2  ratings.db (mixassist/cache.py)")
    D.table(["Table.column", "Type", "Meaning"], [
        ["units.key", "TEXT, primary key", "`rg:<release group MBID>`, `rec:<recording MBID>`, `album:<artist>|<title>` or "
         "`track:<artist>|<title>` (normalised)"],
        ["units.prompt_version", "TEXT", "12-character SHA-1 of the rating prompt; other versions are ignored"],
        ["units.kind", "TEXT", "album or track"],
        ["units.vector", "TEXT (JSON)", "the 8 values"],
        ["units.familiarity", "INTEGER", "0 unknown, 1 artist known, 2 this album known"],
        ["units.description, model, source, rated_ts", "TEXT/INTEGER", "15-word description; model; how it was rated; when"],
        ["verdicts.key", "TEXT, primary key", "fingerprint of model+effort, prompt, intent, seed line, track line"],
        ["verdicts.verdict, reason, stored_ts", "TEXT/INTEGER", "fits / borderline / outlier, the reason, when (kept 365 days)"],
    ], [4.6, 2.8, 9.2], size=8.5, caption="ratings.db")
    D.h(2, "18.3  usage.db and track_metadata_cache.db")
    D.p("`usage.db` has one table `events(ts, kind, data)` with an index on `ts`; `data` is JSON (for an AI call: purpose, "
        "model, effort, ok, tokens in/out, cache reads and writes, cost, seconds, turns). `track_metadata_cache.db` has "
        "one table keyed by path with title, artist, album, genres (JSON), year, decade, duration, thumbnail, fanart, "
        "when it was cached and how fresh Kodi's library was then; an index on `songid`.")
    D.h(2, "18.4  JSON documents")
    D.table(["Document", "Main keys"], [
        ["mix sidecar `mix_*.m3u.json`", "seed, size, track_count, label, name, updated_ts, unsaved, saved_ts, modified_ts, "
         "cache_path, mix_generation_parameters (size, variety, rejectsize, …), track_metadata_by_path, consistency "
         "(status, missing, missing_signature, first_inconsistent_ts, …), repair_readiness (status, reason, "
         "still_listed, unavailable_sources, …), missing_file_search, mix_assist (intent, intent_source, profile, "
         "replaced, removed, previous_tracks, rebuild_suggested, ai_name), track_origins, history"],
        ["`radio_mode_state.json`", "phase (off/seeking/playing), started_ts, tuning_started_ts, seed, queue (file, label), "
         "seen (≤ 5,000), rejected (≤ 5,000) and rejected_with, seeds, settings (a favourite's), batch, intent, "
         "saved_intent, profile, events, current_*, stop_reason"],
        ["`discovery_mode_state.json`", "enabled, owner (radio while scanning), queue, current position and song, "
         "excerpt timing, mix_dialog_active, stop_reason"],
        ["`radio_favourites.json`", "per favourite: number, name, picked song, artwork, settings (variety, artist rule, "
         "openness, perspective, borderline, drift), saved_intent"],
        ["`status.json` (analysis)", "state, phase, pid, started, updated, version, songs, todo, done, failed, unchanged, "
         "missing, taken_over, workers, threads, seconds_per_song, eta, stopped_by, error"],
    ], [4.4, 12.2], size=8, caption="JSON documents and their main keys")

    # ---------------------------------------------------------------- 19 dependencies
    D.h(1, "19  Dependencies", page_break=True)
    D.h(2, "19.1  Internal dependencies")
    D.figure(F("modules.png"), "Internal module dependencies", index="dependencies:internal", landscape=True)
    rows = []
    for mod, e in cat.items():
        if e["imports"]:
            rows.append([f"`{mod}`", ", ".join(f"`{i}`" for i in e["imports"])])
    rows.append(["`service.py` (at run time)", "`main` via `importlib.import_module` (`load_plugin_module`)"])
    D.table(["Module", "Imports (internal)"], rows, [4.6, 12.0], size=8, caption="Internal imports (from the syntax tree)")
    D.p(f"The service uses {len(facts['service_uses_plugin'])} functions of `main.py`:")
    D.p(", ".join(f"`{n}`" for n in facts["service_uses_plugin"]) + ".", size=8.5)
    D.p(f"These {len(facts['duplicates'])} functions exist with the same name in both `main.py` and `service.py`:")
    D.p(", ".join(f"`{n}`" for n in facts["duplicates"]) + ".", size=8.5)
    D.h(3, "Most-used functions (fan-in)")
    D.p("How many functions of the same module call a function — the helpers a change would touch most:")
    fm, fs = facts["fanin_main.py"][:10], facts["fanin_service.py"][:10]
    rows = [[f"`{a[0]}`", str(a[1]), f"`{b[0]}`", str(b[1])] for a, b in zip(fm, fs)]
    D.table(["main.py", "callers", "service.py", "callers"], rows, [5.6, 2.2, 6.6, 2.2], size=8.5,
            caption="Fan-in inside main.py and service.py")
    D.h(2, "19.2  External dependencies")
    D.table(["Dependency", "Where", "Why", "Licence"], [
        ["Kodi 21 Python API (`xbmc`, `xbmcgui`, `xbmcplugin`, `xbmcaddon`, `xbmcvfs`)", "plugin, service", "everything Kodi", "GPL-2.0 (Kodi)"],
        ["Python standard library (sqlite3, json, subprocess, threading, multiprocessing, …)", "everywhere", "storage, processes", "PSF"],
        ["numpy ≥ 1.24 [26]", "sound engine", "spectrogram, search", "BSD"],
        ["onnxruntime ≥ 1.17 [15]", "sound engine", "runs DCLAP", "MIT"],
        ["PyAV ≥ 12 [16] (FFmpeg [17])", "sound engine", "decoding", "BSD (PyAV), LGPL/GPL (FFmpeg)"],
        ["DCLAP model v1 [13]", "sound engine (downloaded)", "sound prints", "AGPL-3.0"],
        ["Pillow (optional, from Kodi)", "mixassist/chart.py, collages", "charts, collages", "HPND"],
        ["Claude Code CLI [12]", "checks (optional)", "ratings, Intent, names", "Anthropic terms"],
        ["GitHub Actions", "CI", "tests on push (Windows, Python 3.8 and latest)", "—"],
    ], [5.8, 3.6, 3.8, 3.4], size=8.5, caption="External dependencies")

    # ---------------------------------------------------------------- 20 interfaces
    D.h(1, "20  Interfaces: actions, settings, command line", page_break=True)
    D.h(2, "20.1  Plugin actions")
    D.p("Every URL `plugin://plugin.audio.incipit/?action=<name>&…` is dispatched by `main.router()`. Without an "
        "action it shows the first screen (`show_root`).")
    skip = {"notify", "end_directory", "log_general", "get_playlist_size", "ensure_remove_allowed_from_addon_container",
            "BackgroundProgress", "mix_assist_result_message"}
    fixes = {"repair_mix": ["ensure_repair_ready", "repair_saved_mix_foreground"],
             "more_like_this": ["insert_more_like_this_into_mix"], "less_like_this": ["remove_less_like_this_from_mix"],
             "browse_mix": ["browse_mix"]}
    rows = []
    for action, calls in facts["actions"]:
        handlers = fixes.get(action) or [c for c in calls if c not in skip]
        rows.append([f"`{action}`", ", ".join(f"`{h}`" for h in handlers)])
    D.table(["Action", "Handled by"], rows, [5.6, 11.0], size=8, caption="Router actions (main.router)")
    D.h(2, "20.2  Settings")
    rows = [[s["category"], s["group"], f"`{s['id']}`", s["type"], s["label"].replace('\\"', '"'),
             "" if s["default"] in (None, "None") else s["default"]] for s in facts["settings"]]
    D.table(["Category", "Group", "ID", "Type", "Label", "Default"], rows, [1.8, 2.4, 4.6, 1.5, 4.8, 1.5], size=7.5,
            caption="All settings (resources/settings.xml)")
    D.p("Integer settings with choices store an index: Tolerance 0–4 (Focused … Adventurous) or Off; Perspective 0–6 or "
        "Off; drift 0–2 (stay close, drift slowly, wander freely); model 0–2 (Opus, Sonnet, Haiku); effort 0–2 (low, "
        "medium, high). Radio's own values were copied once from the old shared ones (`migrate_radio_settings`).")
    D.h(2, "20.3  The sound engine's command line")
    D.table(["Command", "Does"], [
        ["`setup`", "makes `<data>/python` (venv) with numpy, onnxruntime, av, and downloads the model"],
        ["`check`", "are the packages and the model there, what is stored"],
        ["`fetch-model`", "downloads DCLAP release v1 and checks SHA-256"],
        ["`analyse [--list --folder --workers --threads --snippets --limit --prune --kodi-pid --retry-failed]`",
         "analyses new and changed songs; resumes where it stopped"],
        ["`stop`, `status`, `failures`", "asks a running analysis to stop; prints its status; lists unreadable files"],
        ["`neighbours <seed> [--count --artist-window --variety --in-order --leave-out --years]`",
         "the nearest songs as JSON, with artist and title from Kodi's library"],
    ], [7.4, 9.2], size=8.5, caption="python -m soundprint")

    # ---------------------------------------------------------------- 21 testing
    D.h(1, "21  Testing and quality", page_break=True)
    total = sum(t[1] for t in facts["tests"])
    D.p(f"The add-on has {total:,} automated tests in {len(facts['tests'])} files (`tests/`). They use only the "
        "standard library (the sound engine's tests also numpy, and PyAV and onnxruntime where installed) and run "
        "without Kodi: `python -m unittest discover -s tests -v`. GitHub Actions runs them on every push and pull "
        "request on Windows with Python 3.8 (Kodi's) and the latest Python 3.")
    D.h(2, "21.1  The test environment")
    D.bullets([
        ("`tests/fake_kodi.py`", "replaces Kodi's modules: settings with defaults from settings.xml, a temporary "
         "profile folder, a music library that answers `AudioLibrary.GetSongs` filters like Kodi, the player and "
         "playlist, scripted dialog answers, directory listings. A music file exists only if the test adds it."),
        ("`tests/fake_source.py`", "stands in for the sound engine with mixes set per test."),
        ("`tests/support.py`", "`KodiTestCase` (fresh Kodi state, `run_plugin`, a controllable clock) and "
         "`SourceTestCase`."),
    ])
    D.h(2, "21.2  Findings and tests in step")
    D.p("A known problem gets a test that reproduces it, marked `@unittest.expectedFailure`, and an entry in "
        "`docs/findings.md`. `tests/test_findings.py` checks both ways: every such test is listed as open, and every "
        "listed test still fails. When a fix makes the test pass, CI fails until the decorator is removed and the "
        "finding is moved to *Resolved*. This keeps the list of known problems honest.")
    rows = [[f"`{n}`", str(c)] for n, c, _x in sorted(facts["tests"], key=lambda t: -t[1])]
    half = (len(rows) + 1) // 2
    merged = [a + (b if i < len(rows) - half else ["", ""]) for i, (a, b) in enumerate(zip(rows[:half], rows[half:] + [["", ""]]))]
    D.table(["Test file", "Tests", "Test file", "Tests"], merged, [5.6, 1.4, 5.6, 1.4], size=8,
            caption="Tests per file")


def part5(D, cat, facts):
    D.h(1, "Part V · Review and outlook", page_break=True)
    D.p("A strategy for reviewing the code in a structured way, the open issues, and where the add-on could go.",
        italic=True, color=GREY)

    # ---------------------------------------------------------------- 22 review
    D.h(1, "22  Strategy for a structured software review")
    D.h(2, "22.1  Goals of a review")
    D.bullets([
        "Find defects before listeners do: wrong results, crashes, lost data, hangs.",
        "Check that the code does what the concepts promise (Part I–III) — and that the documents still describe the "
        "code.",
        "Keep the code maintainable: understandable, testable, not more complex than needed.",
        "Spread knowledge: after a review, more than one person understands each area.",
    ])
    D.h(2, "22.2  Review types and when to use them")
    D.table(["Type", "Form", "Use for"], [
        ["**Inspection** [27][28]", "formal: roles (moderator, author, reader, reviewers), checklist, preparation, "
         "meeting, recorded findings, follow-up", "risky areas: Radio's threads and state, repair, the sound engine's "
         "analysis, everything that writes files"],
        ["**Walkthrough**", "the author leads through the code along a data flow", "learning an area; the sequences "
         "in chapter 17 are the script"],
        ["**Change review** [29]", "every branch before its merge; small diffs", "day-to-day; `feature/…` and `fix/…` "
         "branches, code and tests in separate commits"],
        ["**Tool-assisted**", "linters, type checks, tests, metrics", "before every human review; cheap"],
    ], [3.2, 6.6, 6.8], size=8.5, caption="Review types")
    D.h(2, "22.3  The process")
    D.figure(F("review.png"), "The review process", index="review:process", landscape=True)
    D.table(["Step", "Who", "What comes out"], [
        ["1 Plan", "moderator", "scope (modules, line ranges from Appendix A), goal, checklist, 2–4 reviewers, date"],
        ["2 Prepare", "everyone", "this document's chapters for the area; the module's catalogue; its tests; the "
         "related findings and roadmap ideas"],
        ["3 Examine", "each reviewer", "notes: defects, questions, risks — with file and line"],
        ["4 Meet (≤ 2 h)", "all", "walk through by data flow; each note: defect, question, idea or no issue"],
        ["5 Record", "moderator", "defects as F-numbers in `docs/findings.md`; ideas as I-numbers in `docs/roadmap.md`"],
        ["6 Reproduce", "author", "a failing test per defect where possible (`expectedFailure`)"],
        ["7 Fix and verify", "author, one reviewer", "fix on a `fix/…` branch; test passes; finding moved to Resolved "
         "with the commit"],
    ], [2.8, 3.0, 10.8], size=8.5, caption="Review steps and their results")
    D.h(2, "22.4  Where to look first: metrics and hotspots")
    D.p("A review cannot read 18,000 lines at once. Size, missing documentation and the number of callers point to "
        "the places where defects are most likely and most costly.")
    rows = []
    for m in sorted(facts["metrics"], key=lambda x: -x["lines"]):
        if m["functions"] == 0:
            continue
        rows.append([f"`{m['module']}`", f"{m['lines']:,}", str(m["functions"]),
                     f"{100 * m['documented'] // m['functions']} %", str(m["avg_len"]), m["longest"]])
    D.table(["Module", "Lines", "Func.", "Docstrings", "Avg. lines", "Longest function (lines)"], rows,
            [4.2, 1.5, 1.3, 1.9, 1.7, 6.0], size=8, caption="Code metrics per module")
    rows = [[f"`{mod}`", f"`{name}`", str(line), str(n)] for n, mod, name, line in facts["longest"][:15]]
    D.table(["Module", "Function", "Line", "Lines"], rows, [4.2, 7.6, 2.0, 2.8], size=8.5,
            caption="The longest functions")
    total = facts["total_funcs"]
    documented = sum(m["documented"] for m in facts["metrics"])
    D.p(f"Of {total} functions (the tools included), {documented} ({100 * documented // total} %) have a docstring; {facts['over_50']} are "
        f"longer than 50 lines and {facts['over_100']} longer than 100. In the packages `mixassist` and `soundprint` "
        "about half of the functions have a docstring, and almost all of the important ones (the undocumented ones are "
        "mostly short helpers); in `main.py` about a third, in `service.py` a quarter.")
    D.h(2, "22.5  A first review plan")
    D.table(["#", "Session", "Scope", "Focus"], [
        ["1", "The search", "`soundprint/neighbours.py`, `store.py`, `client.py`", "correctness of ranks after leave-out, "
         "rules order, matrix cache consistency, timeouts, error kinds"],
        ["2", "The analysis", "`soundprint/analyse.py`, `audio.py`, `model.py`, `state.py`", "resume and stop, "
         "process handling on Windows, priority, decoding edge cases, model checksum"],
        ["3", "Character", "`mixassist/fit.py`, `stats.py`, `assist.analyze`, `character_scale`", "the maths against "
         "chapter 5; small samples; singular matrices; NaN"],
        ["4", "Intent and Claude", "`mixassist/checks.py`, `claude.py`, `rating.py`, `cache.py`", "prompt and schema "
         "agreement, failure handling, no API key leak, cache keys complete"],
        ["5", "Tidy-up", "`assist.tidy_up`, `choose_additions`, `main.process_mix_assist_request`, `patch_playlist_for_mix`",
         "protected zone, artist window, Undo, concurrent edits by the listener"],
        ["6", "Radio", "`service.py` 1,169–2,012; `main.py` 5,043–5,657 and 8,304–9,225", "state machine, threads and "
         "the tick, stop reasons, refills, favourites"],
        ["7", "Saved mixes and repair", "`main.py` 1,366–2,475 and 2,963–3,973; `service.run_consistency_check`",
         "never lose a mix; never repair wrongly; source checks"],
        ["8", "Discovery and screens", "`service.py` 1–1,168; `main.py` 4,658–5,042", "timer, buffer, external "
         "playback, redraws and focus"],
        ["9", "Data and migrations", "sidecars, state files, `take_over_old_data`, migrations", "atomic writes, old "
         "formats, missing keys"],
    ], [0.6, 3.0, 6.2, 6.8], size=8, caption="Suggested review sessions, in order of risk")
    D.h(2, "22.6  Checklists")
    checks = [
        ("Correctness", ["Does the function do what its docstring and the concept say? Edge cases: empty lists, one "
                         "song, the seed missing, a song without artist or title, a library of 0 songs.",
                         "Are paths compared the same way everywhere (`normalize_track_identity`, `file_key`, case on "
                         "Windows)?",
                         "Are artists compared only through `artist_key`?"]),
        ("State and files", ["Is every state file written atomically and read with a default for missing keys?",
                             "Can the plugin and the service write the same file at the same time? What wins?",
                             "Is an old file format (older versions, the old ID) still read?"]),
        ("Concurrency", ["Which thread owns which state (`RADIO_CHECK`, `MIX_ASSIST_WORKER`)? Is a result applied "
                         "only in the tick?",
                         "Can a check's result arrive for a station that has ended or changed (`superseded`)?",
                         "Do child processes always end (timeouts, Kodi closing)?"]),
        ("Kodi", ["Does every listing end with `endOfDirectory`, every action avoid a folder without listing (F8)?",
                  "Are built-ins (`Container.Update`) used only when the right container is visible?",
                  "Does the code survive Kodi's restart in the middle of an action?"]),
        ("AI", ["Do the prompt, the JSON schema and the parser agree?", "Is every failure kind handled with a message "
                "and a safe fallback?", "Does any credential or personal data reach a log or a prompt?",
                "Does a cache key include everything the answer depends on?"]),
        ("Performance", ["Is anything done per song that could be done per mix? Any JSON-RPC call in a loop over a "
                         "mix's tracks?", "Does the service tick stay well under a second?",
                         "Is the low-power target (an always-on quiet box) respected?"]),
        ("Tests and docs", ["Is there a test for the change, and does it fail without it?",
                            "Are findings, roadmap and concept documents updated?",
                            "Are logs detailed enough to explain a listener's report afterwards?"]),
        ("Licences and privacy", ["Is anything AGPL bundled?", "Is the listener's subscription the only route to Claude?"]),
    ]
    for title, items in checks:
        D.h(4, title)
        D.bullets(items)
    D.h(2, "22.7  Exit criteria")
    D.bullets([
        "Every note is classified; every defect has an F-number, every idea an I-number.",
        "Defects of the reviewed scope are fixed or consciously deferred (with a reason in findings.md).",
        "The full test suite passes; tests for fixed findings no longer carry `expectedFailure`.",
        "This document and the concept documents describe the reviewed code correctly.",
    ])

    # ---------------------------------------------------------------- 23 open issues
    D.h(1, "23  Open issues", page_break=True)
    D.h(2, "23.1  Open findings")
    D.table(["#", "Finding", "Impact", "Status"], [
        ["F3", "\"Unknown date\" is listed first among saved mix dates (sorted with reverse=True)", "cosmetic; only mixes "
         "whose save time can't be read", "reproduced by a test"],
        ["F11", "Unused code: `add_discovery_run_action_item()` in main.py", "maintenance", "open"],
        ["F17", "Radio tests fail now and then in full runs (probably state left by another test)", "CI noise; may hide "
         "a real failure", "not reproduced; getting more frequent"],
        ["F36", "The sound engine can suggest songs no longer in the library (no prune of removed songs)", "a mix can "
         "hold a file Kodi can't play; 251 such songs on 2026-11-05", "fix planned: library sync (I9)"],
    ], [1.0, 7.2, 5.4, 3.0], size=8.5, caption="Open findings (docs/findings.md)")
    D.h(2, "23.2  Observations from writing this document")
    D.p("These are not defects but points a review should weigh. They were found while extracting the method "
        "catalogue and comparing code and documents:")
    D.bullets([
        ("Size of main.py.", "9,672 lines and 544 functions in one module make navigation and review hard. The areas "
         "of chapter 15 are natural seams for a split into modules (roadmap I45)."),
        ("Duplicated helpers.", f"{len(facts['duplicates'])} functions exist in both main.py and service.py; a test keeps "
         "them alike, but a shared module would remove the duplication (roadmap I46)."),
        ("Docstrings.", "About 37 % of main.py's and 25 % of service.py's functions have a docstring; in the packages "
         "about half, with the important functions documented. Appendix A marks the undocumented ones (roadmap I47)."),
        ("Legacy names.", "Internal names still say MusicIP or mix assist: `MusicIPError`, `MusicIP.*` list-item "
         "properties, `ensure_musicip_keymap_installed`, the skin file `script-musicip-info.xml`, setting IDs "
         "`mix_assist_*`. Harmless, but confusing for newcomers (the glossary maps them)."),
        ("Roadmap behind the code.", "I40 to I43 (statistics per request, verdict cache, lean CLI start, model and effort "
         "per purpose) and the reuse of a stated intent (part of I7) are in the code since 2026-11-13 but still listed "
         "as open in `docs/roadmap.md`."),
        ("Long functions.", f"{facts['over_100']} functions are longer than 100 lines, `router()` alone 434. A "
         "dispatch table would make the router shorter and its actions easier to list and test."),
    ])

    # ---------------------------------------------------------------- 24 outlook
    D.h(1, "24  Future outlook", page_break=True)
    D.figure(F("outlook.png"), "The open roadmap by theme", index="roadmap", landscape=True)
    D.h(2, "24.1  Near term")
    D.bullets([
        ("Library sync (I9, fixes F36):", "follow Kodi's library events (`AudioLibrary.OnUpdate`, `OnRemove`), analyse "
         "new songs from a list, prune removed ones, and leave unknown files out of searches."),
        ("Mix edits reach Kodi's queue (I2):", "More like this, Less like this and Remove change the playing queue too."),
        ("Mix recipes (I33):", "named sets of Source, Character, Intent and Radio settings, applied to mixes and stations."),
        ("Sharper intents (I37, I38):", "Cultural as *the scene*, not the whole tradition; three stages from broad to sharp."),
    ])
    D.h(2, "24.2  Architecture")
    D.bullets([
        ("A faster search (I11):", "keep the matrix as float16, or a resident helper process that keeps it loaded "
         "instead of one process per search."),
        ("A slower box (I12):", "three snippets instead of six halve the analysis time at slightly lower quality — for an "
         "always-on, quiet, low-power player, the stated target hardware."),
        ("Splitting main.py (I45) and a shared helper module (I46):", "smaller modules along the areas of chapter 15."),
        ("Other models (I14):", "self-supervised music models (MuQ, MERT) as a comparison; the CC0 CLAP teacher if "
         "DCLAP's licence ever matters."),
    ])
    D.h(2, "24.3  Further out")
    D.bullets([
        ("Mix from a prompt (I4):", "from a description to a seed to a mix."),
        ("Ordering a mix by sound (I1):", "shortest path, round trip, contrast, arcs of one profile value."),
        ("A screen during playback (I36):", "what plays, the station's story, and suggestions of music to discover that "
         "is not in the library."),
    ])
