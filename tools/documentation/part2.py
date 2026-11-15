"""Part III: architecture at a low level of detail."""
from part1 import F
from doclib import GREY


def part3(D, facts):
    D.h(1, "Part III · Architecture", page_break=True)
    D.p("The add-on seen from above: what it does, which parts it has, how they run, where data flows and is kept, "
        "how the parts talk, how Kodi is used, and how the AI is used.", italic=True, color=GREY)

    # ---------------------------------------------------------------- 6 functional
    D.h(1, "6  Functional view")
    D.p("Incipit's functions fall into eight areas. Each is reached through plugin actions (chapter 20) and, where it "
        "runs on its own, through the service.")
    D.table(["Area", "Functions", "Where"], [
        ["**Mixes**", "generate from the playing song, a library song or a Discovery snippet; refresh; play; More like "
         "this; Less like this; remove; save and name; delete; group saved mixes by date", "main.py: fetch_mix, "
         "create_current_mix, insert_more_like_this_into_mix, …"],
        ["**Checks**", "Character and Intent for new mixes (background), More like this, Radio; tidy-up on request; "
         "Undo; edit the intent; per-mix settings; names", "mixassist/, main.py (process_mix_assist_request, "
         "check_radio_*), service.py worker"],
        ["**Radio**", "scan stations, pick one, start from a library song, refill, follow playlist edits, stop; "
         "favourites with their own settings; station information", "main.py (plugin side), service.py (run_radio_tick)"],
        ["**Discovery**", "random snippets in a rolling playlist buffer; skip; mix from the current snippet; dialog hold",
         "main.py, service.py (run_discovery_tick)"],
        ["**Sound engine**", "set-up, analysis (automatic and on request), status, stop; nearest songs; years",
         "soundprint/, main.py (Settings > Advanced actions), service.py (run_library_update_tick)"],
        ["**Saved-mix care**", "consistency checks, repair readiness, search for moved files, foreground and automatic "
         "repair", "main.py, service.py (run_consistency_check)"],
        ["**Presentation**", "first screen, Mix mode, Radio mode, track labels, artwork and collages, information "
         "window with charts, statistics, metadata cache", "main.py, mixassist/chart.py, service.py (collage and "
         "metadata ticks)"],
        ["**Housekeeping**", "logging by area, settings migrations, take-over of the old ID's data, keymap install",
         "logs.py, service.py"],
    ], [3.0, 8.4, 5.2], size=8.5, caption="Functional areas")

    # ---------------------------------------------------------------- 7 context
    D.h(1, "7  System context", page_break=True)
    D.figure(F("context.png"), "System context: Incipit between Kodi, the sound engine, Claude and the files",
             index="system context", landscape=True)
    D.p("Incipit lives inside Kodi and talks to three kinds of outside things:")
    D.bullets([
        ("Kodi itself:", "its GUI, player and playlist, JSON-RPC interface and music library. Kodi starts the add-on's "
         "code; the add-on never runs on its own."),
        ("Two helper programs on the same PC:", "the sound engine (`python -m soundprint`, in its own Python "
         "environment) and the Claude Code CLI (`claude`). Both are started as child processes."),
        ("Files:", "the music files (read by Kodi to play, by the sound engine to analyse) and the add-on's data folder."),
    ])
    D.p("The internet is needed only for the sound engine's set-up (Python packages from PyPI, the model from GitHub) "
        "and, if the checks are on, for Claude.")

    # ---------------------------------------------------------------- 8 components
    D.h(1, "8  Components and layers", page_break=True)
    D.figure(F("components.png"), "Components and layers", index="architecture:components", landscape=True)
    D.p("The code has three layers and one separate program:")
    D.table(["Layer", "Parts", "Rules"], [
        ["**Entry points**", "`main.py` (plugin), `service.py` (service), `context_mix.py`, `context_radio.py`, "
         "`logs.py`", "run in Kodi's Python; may use every Kodi module"],
        ["**Domain packages**", "`mixassist/` (Character, Intent, ratings, Claude calls, charts, statistics); "
         "`soundprint/client.py` and `soundprint/years.py` (the sound engine's Kodi side)", "`mixassist` imports no "
         "Kodi module: paths, settings and a JSON-RPC function are passed in. This keeps it testable and reusable."],
        ["**Sound engine**", "`soundprint/` run as `python -m soundprint` in its own environment with numpy, "
         "onnxruntime, PyAV", "never imported by Kodi's Python except `client.py`, `state.py` and `years.py` "
         "(plain Python, no numpy)"],
        ["**Resources**", "`addon.xml`, `resources/settings.xml`, strings, keymap, skin XML for the information "
         "window, icons", "declarative; `tools/make_settings.py` generates parts of settings.xml"],
    ], [3.2, 7.4, 6.0], size=8.5, caption="Layers and their rules")
    D.callout("Key idea.", "Kodi's own Python cannot load numpy, onnxruntime or PyAV. So everything heavy runs in a "
              "separate Python process, and the add-on talks to it through a command line and JSON — the same way it "
              "talks to the Claude CLI. This also keeps the heavy work out of Kodi's process.")
    D.p("Two structural facts matter for anyone working on the code:")
    D.bullets([
        ("`main.py` is large:", f"9,672 lines and 544 functions — menus, mixes, Radio, Discovery, repair, metadata, "
         "artwork, information pages and the checks' plumbing in one module (see chapter 22 for what this means for "
         "a review)."),
        ("The service imports the plugin:", "`service.load_plugin_module()` imports `main.py` at run time and calls "
         f"{len(facts['service_uses_plugin'])} of its functions (mix storage, consistency, repair, the checks, Radio "
         f"parameters). In addition, {len(facts['duplicates'])} helper functions exist in both files with the same name "
         "(settings, JSON files, JSON-RPC, metadata); `tests/test_shared_helpers.py` checks that the copies behave alike."),
    ])

    # ---------------------------------------------------------------- 9 runtime
    D.h(1, "9  Processes and run time", page_break=True)
    D.figure(F("runtime.png"), "Processes and threads at run time", index="processes", landscape=True)
    D.h(2, "9.1  The plugin: short lives")
    D.p("Kodi runs `main.py` once per plugin URL, in a fresh Python interpreter: it parses the URL, `router()` "
        "picks the action, the action builds a listing or does its work, and the interpreter ends. Nothing stays in "
        "memory between two calls. Everything that must last is written to files in the profile folder.")
    D.h(2, "9.2  The service: one long life")
    D.p("Kodi starts `service.py` once and keeps it until Kodi closes. Its `main()` runs a loop with one tick per "
        "second. Each area has its own step, wrapped in its own error handler, so a failure in one area is logged "
        "and the others go on.")
    D.figure(F("service_loop.png"), "One tick of the service loop", index="service loop", landscape=True)
    D.p("Two kinds of work are too slow for a tick and run in background threads of the service: the checks for a "
        "new mix (`run_mix_assist_tick` starts one worker at a time) and a Radio station's check "
        "(`start_radio_check`; the radio tick applies its result when it is done). The tick itself only starts them "
        "and looks at their results.")
    D.h(2, "9.3  Child processes")
    D.table(["Process", "Started by", "How", "Lives", "Priority"], [
        ["`soundprint neighbours`", "plugin (a mix), service (Radio)", "`subprocess.run`, JSON on stdout", "~1 s (up to 4 s)", "normal"],
        ["`soundprint analyse`", "service (automatic), plugin (on request)", "`Popen`, detached, new process group", "minutes to a day", "below normal, very low I/O"],
        ["  worker processes", "the analysis", "`multiprocessing` pool (spawn)", "as the analysis", "below normal"],
        ["`soundprint setup`", "plugin (Settings)", "`subprocess.run`, 30 min timeout", "minutes", "below normal"],
        ["`claude -p`", "service worker, plugin (on request)", "`subprocess.run`, stdin message", "10–17 s per request", "normal"],
    ], [3.3, 3.6, 4.0, 2.7, 3.0], size=8.5, caption="Child processes")
    D.p("All child processes start without a console window (`CREATE_NO_WINDOW`). The analysis follows Kodi's "
        "process: it holds a handle to it (`state.Watched`) and stops after the songs in hand once Kodi has closed; "
        "the service starts it again two minutes after Kodi's next start. Only one analysis runs per data folder "
        "(`state.running` reads `status.json` and checks the process number).")

    # ---------------------------------------------------------------- 10 data flow
    D.h(1, "10  Data flow", page_break=True)
    D.figure(F("dataflow_mix.png"), "Data flow of a new mix", index="data flow:new mix", landscape=True)
    D.h(2, "10.1  A new mix")
    D.bullets([
        "The seed path comes from the player (or the library item, or the Discovery state). The mix dialog adds size, "
        "variety, artist rule and the per-mix checks.",
        "`fetch_mix` asks the sound engine for the nearest songs. The answer (paths, similarity, rank, artist, title) is "
        "logged in full; the seed is put first.",
        "`create_current_mix` writes the track list (`mix_<hash>_<time>.m3u`), its sidecar (`….m3u.json`) and names it "
        "in `current_mix.json`. An unsaved previous mix is deleted.",
        "The playlist plays at once. A tidy-up request goes to `mixassist/queue.json`; missing metadata to "
        "`metadata_refresh_queue.json`.",
        "In the next tick the service's worker runs `process_mix_assist_request`: units are resolved and rated, the "
        "intent is stated and the tracks are judged; outliers are replaced from submixes; the sidecar gets the result, "
        "the history and the previous tracks for Undo; the playlist is patched beyond the protected zone (the playing "
        "song and the next).",
    ], numbered=True)
    D.h(2, "10.2  Other flows")
    D.table(["Flow", "Path of the data"], [
        ["**More like this**", "selected song → sound engine (candidates) → Character and Intent against the selected "
         "song (the plugin waits, with a progress bar) → inserted after it in the stored mix"],
        ["**Radio refill**", "radio tick (< 3 songs left) → check thread: sound engine with the station's played/queued/"
         "turned-down songs left out → batches of 18 judged → songs per refill appended to Kodi's playlist → "
         "`radio_mode_state.json` (queue, seen, rejected, profile, events)"],
        ["**Analysis**", "Kodi's MyMusic*.db (song paths) → plan (new, changed, moved spelling) → worker processes "
         "(decode, embed) → `sound.db` → `vectors.npy` at the next search"],
        ["**Metadata refresh**", "queue file → service tick (5 songs every 5 s) → JSON-RPC `AudioLibrary.GetSongs` → "
         "`track_metadata_cache.db` and the mix sidecar → the visible view is refreshed on the next selection change"],
        ["**Consistency and repair**", "service interval → sidecars' tracks checked on disk → missing files → repair "
         "readiness (does Kodi still list them?) → disk search in virtual library roots → candidates scored → "
         "automatic repair only for a unique, high-confidence match (score ≥ 120, gap ≥ 35)"],
        ["**Statistics**", "every AI call, mix and refill → `usage.db` events → Settings > Advanced > Show statistics"],
    ], [3.6, 13.0], size=8.5, caption="Data flows")

    # ---------------------------------------------------------------- 11 stores
    D.h(1, "11  Data stores", page_break=True)
    D.p("All of the add-on's data lives in Kodi's profile folder `userdata/addon_data/plugin.audio.incipit/`. Kodi's "
        "music database is only read. Chapter 18 shows the database tables in detail.")
    D.table(["Store", "Format", "Written by", "Read by", "Holds"], [
        ["`mix_*.m3u`", "text", "plugin, service (repair, checks)", "both, Kodi", "a mix's track paths"],
        ["`mix_*.m3u.json`", "JSON (sidecar)", "plugin, service", "both", "seed, parameters, metadata, consistency, "
         "repair, checks, history, origins"],
        ["`current_mix.json`", "JSON", "plugin", "both", "which mix file is the current mix"],
        ["`radio_mode_state.json`", "JSON", "plugin, service", "both", "phase, queue, seen, rejected, seeds, profile, "
         "events, stop reason"],
        ["`discovery_mode_state.json`", "JSON", "plugin, service", "both", "enabled, queue, position, dialog hold, owner"],
        ["`radio_favourites.json`", "JSON", "plugin", "plugin, service", "favourite stations, their settings and "
         "saved intent"],
        ["`mixassist/queue.json`", "JSON", "plugin", "service", "tidy-up requests"],
        ["`metadata_refresh_queue.json`", "JSON", "plugin", "service", "paths whose metadata is missing or stale"],
        ["`focus_state.json`", "JSON", "plugin", "plugin", "one-time focus tokens for refreshed listings"],
        ["`soundprint_analysis.json`", "JSON", "service", "service", "last automatic analysis start and why"],
        ["`track_metadata_cache.db`", "SQLite", "plugin, service", "both", "title, artist, album, art per path"],
        ["`mixassist/ratings.db`", "SQLite", "checks", "checks", "profiles (units) and the verdict cache"],
        ["`mixassist/usage.db`", "SQLite", "checks, plugin", "plugin", "events for the statistics"],
        ["`soundprint/sound.db`", "SQLite", "analysis", "search, years", "one sound print per file"],
        ["`soundprint/vectors.npy` + `.json`", "numpy + JSON", "search", "search", "all vectors as one matrix"],
        ["`soundprint/years.pickle`", "pickle", "search / plugin", "both", "a year per song, era hints"],
        ["`soundprint/status.json`, `stop`", "JSON, empty file", "analysis; plugin/service", "plugin, service", "progress; a stop request"],
        ["`charts/`, `covers/`", "PNG", "plugin, service", "Kodi", "charts for the information window, mix collages"],
        ["Kodi `MyMusic*.db`", "SQLite (Kodi's)", "Kodi", "sound engine, years (read-only)", "the music library"],
    ], [4.2, 2.4, 3.2, 2.6, 4.2], size=8, caption="Where the add-on keeps its data")
    D.callout("Key idea.", "A song is identified by its **file path** everywhere — in the mix files, the sidecars, "
              "the metadata cache, the Radio state and the sound engine. That keeps the stores independent of Kodi's "
              "internal song IDs, which change when the library is rebuilt, but makes moved files the main source of "
              "inconsistency (hence the repair functions).")

    # ---------------------------------------------------------------- 12 messaging
    D.h(1, "12  Messaging and communication", page_break=True)
    D.figure(F("messaging.png"), "The channels between the parts", index="messaging", landscape=True)
    D.p("Incipit uses no sockets, queues or shared memory of its own. Its parts talk through nine channels:")
    D.table(["#", "Channel", "From → to", "Form", "Example"], [
        ["1", "plugin URL", "Kodi → plugin", "`plugin://plugin.audio.incipit/?action=…&…`", "a menu entry, a context "
         "entry, a key from the keymap (`RunPlugin`)"],
        ["2", "Kodi API calls", "plugin, service → Kodi", "Python modules `xbmc*`; JSON-RPC; built-ins", "`Container.Update`, "
         "`AudioLibrary.GetSongs`, `Player.GoTo`"],
        ["3", "callbacks", "Kodi → service", "`xbmc.Player`, `xbmc.Monitor` methods", "`onPlayBackStopped`, "
         "`onScanFinished`, `onSettingsChanged`"],
        ["4", "state files", "plugin → service", "JSON files, written atomically (`.part` + replace)", "Radio phase "
         "*playing*; a Discovery skip"],
        ["5", "state files", "service ↔ plugin", "the same files read in the next tick", "a station's queue and events"],
        ["6", "command line + JSON", "plugin/service → sound engine", "arguments in, JSON on stdout; a file for long lists",
         "`neighbours <seed> --count 75 --leave-out <file>`"],
        ["7", "command line + stdin", "→ Claude CLI", "system prompt and JSON schema as arguments, message on stdin, "
         "JSON out", "rate 20 albums; state an intent"],
        ["8", "status and stop files", "service/plugin ↔ analysis", "`status.json` every 5 s; an empty `stop` file", "the "
         "status window; Stop the analysis"],
        ["9", "notifications, dialogs, log", "add-on → listener", "`xbmcgui.Dialog`, `kodi.log` lines tagged by area",
         "\"2 tracks didn't fit and were replaced\""],
    ], [0.6, 2.8, 3.2, 5.0, 5.0], size=8, caption="Communication channels")
    D.p("Because the plugin is short-lived, every request it makes of the service is a **file**: the plugin writes, "
        "the service picks it up within a second. Writes go to a temporary file first and are then renamed, so a "
        "reader never sees half a file. The only direct call between the two is the service importing `main.py` as a "
        "module — shared code, not a message.")

    # ---------------------------------------------------------------- 13 kodi
    D.h(1, "13  Kodi integration", page_break=True)
    D.figure(F("kodi.png"), "Kodi integration: extension points and APIs", index="Kodi:integration", landscape=True)
    D.h(2, "13.1  Extension points")
    D.p("`addon.xml` declares what Kodi should do with the add-on [1]:")
    D.bullets([
        ("`xbmc.python.pluginsource` (provides audio):", "the add-on appears under Music add-ons; Kodi runs `main.py` "
         "for each `plugin://` URL with the handle and the query string as arguments."),
        ("`xbmc.service`:", "Kodi runs `service.py` at start-up and asks it to end when it closes "
         "(`Monitor.abortRequested`, `waitForAbort`)."),
        ("`kodi.context.item`:", "two entries in the context menu of library songs (`String.IsEqual(ListItem.DBTYPE,song)`), "
         "each a small script that builds a plugin URL from the selected item and runs it."),
        ("`xbmc.addon.metadata`:", "name, summary, description, licence (MIT), icon."),
    ])
    D.h(2, "13.2  The plugin as a virtual folder")
    D.p("Every screen of Incipit is a directory listing: `xbmcplugin.addDirectoryItem` for each entry and "
        "`endOfDirectory` at the end. Entries are `xbmcgui.ListItem`s with a label, a second label, artwork, a "
        "`MusicInfoTag` (title, artist, album, track number, duration) and properties. Actions that should not leave "
        "a listing (start the radio, save a mix) are plain actions; after them the plugin refreshes or replaces the "
        "visible container with `Container.Refresh` or `Container.Update(…, replace)` (F8, F24, F25 record what went "
        "wrong before). Track labels follow Kodi's own track-name template (`[%N. ]%A - %T`), with %N the position in "
        "the mix.")
    D.h(2, "13.3  Kodi APIs used")
    D.table(["API", "Used for"], [
        ["`xbmc`", "player and monitor classes, `executebuiltin` (Container.Refresh/Update, ReloadKeymaps, Action), "
         "`executeJSONRPC`, `getInfoLabel` (Container.FolderPath, Player.Filenameandpath, Playlist.Length), log"],
        ["`xbmcgui`", "ListItem, Dialog (select, input, yes/no, notification, progress), `WindowXMLDialog` (the "
         "information window), window properties"],
        ["`xbmcplugin`", "directory items, end of directory, resolved URLs"],
        ["`xbmcaddon`", "settings (get/set), add-on info, opening the settings dialog"],
        ["`xbmcvfs`", "`translatePath` for `special://profile`, `special://userdata`, `special://skin`, thumbnails"],
        ["JSON-RPC", "`AudioLibrary.GetSongs` (13 places), `GetSongDetails`, `GetAlbumDetails`, `GetProperties`, `Scan`, "
         "`Clean`; `Player.GetProperties`, `Player.GoTo`; `Playlist.GetItems`, `Playlist.Remove`; `Files.GetSources`; "
         "`Settings.GetSettingValue`"],
    ], [2.6, 14.0], size=8.5, caption="Kodi APIs [1][2]")
    D.h(2, "13.4  Other integration points")
    D.bullets([
        ("Keymap:", "`incipit_mix_editing.xml` is written to `special://profile/keymaps` at start (and reloaded with "
         "`ReloadKeymaps` when it changed): `DEL`, `m`, `l`, `i` in the music windows run plugin actions on the "
         "selected mix row."),
        ("Information window:", "a skin XML file (`resources/skins/Default/1080i/script-musicip-info.xml`) for a "
         "`WindowXMLDialog` with tabs and charts; the skin's highlight colour is read from its colour theme so the "
         "window blends in."),
        ("Settings:", "`resources/settings.xml` (Kodi's settings format version 1) with four categories plus Logging; "
         "action settings run plugin URLs (set-up, analyse now, status, statistics). The service follows changes with "
         "`onSettingsChanged`."),
        ("Window properties:", "list items carry properties such as `MusicIP.CachePath` and `MusicIP.MixAction.*` "
         "(names kept from MusicIP) that the keymap actions and the service read back."),
        ("Library events:", "`onScanFinished` starts the sound engine's analysis of new songs; the music database "
         "itself is read directly (read-only SQLite) by the sound engine, since JSON-RPC would be far too slow for "
         "150,000 songs."),
        ("Logging:", "every line is tagged `[plugin.audio.incipit] [area]`; errors and warnings always, details per "
         "area switch (`logs.py`)."),
    ])

    # ---------------------------------------------------------------- 14 AI
    D.h(1, "14  AI concepts", page_break=True)
    D.p("Two very different kinds of AI work in Incipit. The **sound engine** uses a neural network (DCLAP) that runs "
        "locally, once per song, and knows only sound (chapter 3). The **checks** use a large language model, Claude, "
        "that knows about music from text — artists, albums, scenes, history — but never hears it. This chapter is "
        "about the second kind.")
    D.figure(F("ai_flow.png"), "How the add-on asks Claude: ratings and Intent", index="Claude", landscape=True)
    D.h(2, "14.1  What Claude is asked")
    D.table(["Purpose", "Asked", "Answer", "Kept"], [
        ["**Rating**", "per album (or compilation track): artist, title, year, up to 15 track titles, genre tag as a "
         "hint; 20 albums or 25 tracks per request", "8 values, familiarity 0–2, a 15-word description", "forever, "
         "per prompt version (`ratings.db`)"],
        ["**Describing**", "the seed and the tracks, from a perspective", "the seed's intent; a verdict per track; a "
         "name of 2–4 words", "with the mix or station"],
        ["**Judging**", "tracks against an intent already stated (or edited by the listener)", "verdict and reason "
         "per track; optionally a name", "verdict cache"],
    ], [2.4, 6.4, 4.6, 3.2], size=8.5, caption="The three kinds of request")
    D.h(2, "14.2  Calling Claude through the Claude Code CLI")
    D.p("Incipit uses the listener's Claude subscription through the [[Claude Code CLI]] [12] in print mode "
        "(`mixassist/claude.py`). One request is one process:")
    D.code(["claude -p --output-format json --model claude-opus-5-5 --effort medium",
            "       --system-prompt <prompt> --json-schema <schema>",
            "       --tools \"\" --no-session-persistence",
            "       --strict-mcp-config --setting-sources \"\" --disable-slash-commands",
            "stdin:  the message (the tracks, numbered, one per line)",
            "stdout: JSON with the structured output, usage and timings"])
    D.bullets([
        ("Structured output:", "a JSON schema forces the answer's shape; `parse_structured` validates it and values are "
         "clamped to their ranges."),
        ("No tools, no session, lean start:", "the model only answers; the listener's own Claude Code set-up (MCP "
         "servers, settings, skills) is not loaded (saves ~0.3 s of ~1.5 s start-up, I42)."),
        ("Subscription only:", "`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are removed from the CLI's environment "
         "for every call, and `--bare` is never used — either would bill an API account."),
        ("Model and effort:", "chosen per purpose in Settings > Advanced (Opus, Sonnet or Haiku; low, medium, high); "
         "the tested default is Opus 5.5 at medium effort."),
        ("Failures:", "classified as *not found*, *not logged in*, *usage limit*, *timeout* or *failed*; each gives "
         "the listener a clear message, and a check that cannot run leaves the mix as it is."),
        ("Privacy:", "the login check keeps only yes/no — its output contains the account's e-mail address, which "
         "must not reach a log."),
    ])
    D.h(2, "14.3  The prompts")
    D.p("The **seed-intent prompt** (`checks.SEED_INTENT_PROMPT`) asks the model first to *state* the seed's intent and "
        "then to *judge* every other track against it:")
    D.bullets([
        "one sentence on the seed's **intention**: what the music sets out to do, and how its makers stand towards the "
        "listener and the world;",
        "5 to 8 **qualities** a fitting track should share — qualities, not surface features (instrumentation, scene, "
        "production details);",
        "**\"Not:\"** 2 or 3 kinds of music that share the qualities but not the intention;",
        "then a verdict per track — *fits*, *borderline* or *outlier* — with a reason. A track fits only if it shares the "
        "intention as well as the qualities; the rest of the mix is context only.",
    ])
    D.p("This form was chosen by comparing four prompt variants on 27 songs (2026-10-24): only the form with "
        "\"intention first, Not:, and fits only if it shares the intention\" separated first-wave punk from 80s hard "
        "rock for a Van Halen station, where all eight profile values were nearly equal.")
    D.h(3, "Listening perspectives")
    D.table(["Perspective", "The view", "What a fitting track shares"], [
        ["Mixed (default)", "the music's intention and qualities together", "intention and qualities"],
        ["Technical", "an educated musician: what the musicians do, and how", "the craft: harmony, rhythm, form, musicianship"],
        ["Emotional", "the artist's view: the emotion it sets out to express", "the core (stance, depth, sincerity); "
         "colour may differ; production is left out of Character"],
        ["Cultural", "where the music comes from and what it stands for", "the scene, tradition and lineage"],
        ["Functional", "what the music is for", "the use: dancing, focus, sleep, a party …"],
        ["Lyrical", "what the words say", "themes and voice of the lyrics"],
        ["Epoch", "a chronicler: the moment the music came out", "the time (\"Years: 1976–1979\"); the search is "
         "limited to that window"],
    ], [2.8, 6.4, 7.4], size=8.5, caption="Perspectives (`mixassist/checks.py`, PERSPECTIVE_TEXTS)")
    D.h(3, "Two safeguards")
    D.bullets([
        ("Little-known music:", "a track the rating did not know is marked *(little known)*; its description was "
         "guessed from names. The judge must not turn it down for an intent read from that guess (F38)."),
        ("Unknown years:", "a compilation song whose own year is unknown is shown as \"compilation of 1994\" (it came "
         "out then or earlier) or \"year unknown\" — not as the compilation's year (F51, F52)."),
    ])
    D.h(2, "14.4  Combining Character and Intent")
    D.table(["Character", "Intent", "Status of an existing track", "A new track"], [
        ["passes", "fits", "fits", "added"],
        ["passes", "borderline", "borderline", "added only with *Accept borderline*"],
        ["fails", "fits (or off)", "flagged: stays, but never seeds a submix", "not added"],
        ["passes (or off)", "outlier", "flagged", "not added"],
        ["fails", "outlier", "**outlier**: replaced (guessed units too)", "not added"],
    ], [2.6, 2.6, 6.4, 5.0], size=8.5, caption="Decisions when both checks are on (`assist.analyze`, `assist.passes`)")
    D.p("With one check off, that check counts as agreeing. With both off, nothing is asked of the AI. A mix in which "
        "more than a third fails is marked *rebuild suggested* (acting on it is roadmap I3). Replacements come from "
        "**submixes**: a small mix seeded from the nearest earlier track that clearly fits (at worst the seed), whose "
        "candidates are held to the same rules and to the artist window.")
    D.h(2, "14.5  Caches, cost and statistics")
    D.bullets([
        ("Rating cache:", "units are keyed by MusicBrainz release-group or recording ID where the files have one, else "
         "by normalised artist and title. Each entry records the prompt version (a SHA-1 fingerprint of the prompt); "
         "a changed prompt re-rates when next needed. Hit rate measured: 64 % (7,981 of 12,519 units)."),
        ("Verdict cache:", "a verdict is kept under a fingerprint of everything it depends on — model and effort, "
         "prompt with perspective, intent text, seed line, track line (I41). Kept 365 days."),
        ("Statistics:", "`usage.db` records every request (tokens, time, API-equivalent cost, cache reads). Measured "
         "2026-10-20 to 11-10: 1,649 requests — rating 1,015 at 10.2 s, describing 350 at 16.7 s, judging 277 at "
         "16.8 s; 5.8 hours of waiting and $68 API-equivalent cost on the subscription. Most of the time is the "
         "answer being written; Claude's prompt cache already serves the system prompts."),
    ])
    D.h(2, "14.6  Where AI is deliberately not used")
    D.bullets([
        "Choosing the candidates: that is the sound engine's job (local, cheap, unbiased by fame).",
        "Starting playback: no mix or station waits for Claude.",
        "Repair of moved files: plain matching rules with scores, never a guess.",
        "Any decision without a fallback: without Claude, mixes and stations work unchecked.",
    ])
