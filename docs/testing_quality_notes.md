# Testing and Quality Notes

## Automated tests

The tests in `tests/` cover the plugin (`main.py`), the service (`service.py`), the context menu entries, the checks (`mixassist/`) and the sound engine (`soundprint/`). They use only the Python standard library (the sound engine's own tests also numpy, and av and onnxruntime where installed; they are skipped without them) and run without Kodi:

```
python -m unittest discover -s tests -v
```

GitHub Actions runs them on every push and pull request (`.github/workflows/tests.yml`) on Windows with Python 3.8, the interpreter bundled with Kodi, and the latest Python 3.

### Test environment

- `tests/fake_kodi.py` replaces Kodi's `xbmc`, `xbmcaddon`, `xbmcgui`, `xbmcplugin` and `xbmcvfs` modules. It provides add-on settings (defaults read from `resources/settings.xml`), a temporary `special://profile` folder, a music library that answers `AudioLibrary.GetSongs` filters like Kodi, the player and music playlist, dialogs with scripted answers, and plugin directory listings. A music file only "exists" if the test adds it, so the real disk is never consulted.
- `tests/fake_source.py` stands in for the sound engine (`soundprint.client.neighbours`) with mixes set per test.
- `tests/support.py` loads the add-on modules and provides `KodiTestCase` (fresh Kodi state per test, `run_plugin(...)` to call the router, a controllable clock) and `SourceTestCase` (mixes from the stand-in for the sound engine).

### Test files

| File | Covers |
| --- | --- |
| `test_packaging.py` | addon.xml, settings.xml vs. setting IDs used in code, keymap, Python 3.8 syntax |
| `test_main_mix_parameters.py` | settings, mix parameters, the generate-mix dialog |
| `test_main_fetch_mix.py` | mixes from the source: the seed first, errors, the set-up hint, MusicIP's recorded parameters, the dormant MusicIP file |
| `test_settings_layout.py` | the settings' sections, Radio's own values and their one-time copy |
| `test_main_mix_assist.py`, `test_radio_mix_assist.py`, `test_radio_favourites.py` | the checks for mixes, More like this, Radio and favourite stations |
| `test_mixassist_core.py`, `test_mixassist_tidy_up.py`, `test_mixassist_tiers.py`, `test_mixassist_chart.py`, `test_mixassist_usage.py` | the checks' package: ratings, prompts, Character and Intent each on or off, the fixed scale, charts, statistics |
| `test_soundprint.py`, `test_soundprint_client.py` | the sound engine: snippets, decoding, the store, nearest songs, variety, the artist rule; Kodi's side of it |
| `test_main_saved_mixes.py` | saved mix files and sidecars, ordering, date groups, cleanup, remove/more/less like this, consistency, repair readiness, keymap install |
| `test_main_metadata.py` | library lookups, SQLite metadata cache, sidecar snapshots, refresh queue, track labels |
| `test_main_plugin_routes.py` | every `router()` action: listings, context menus, playback, error handling, script entry point |
| `test_main_discovery.py` | Discovery mode from the plugin: start, stop, next, mix from the current song |
| `test_repair_matching.py` | repair hints, candidate scoring, candidate selection, foreground and automatic repair |
| `test_repair_sources.py` | music sources and repair: unavailable sources, virtual library roots, disk search for moved files, notifications, and scanning never-scanned sources before repair |
| `test_radio_mode.py` | Radio mode: menu, tuning, starting the station without a dialog, top-ups from the last queued song, backlog, stopping on Stop or other playback, service integration |
| `test_service_discovery.py` | Discovery mode in the service: commands, playlist buffer, auto-skip, player events, main loop |
| `test_service_metadata.py` | background consistency check and automatic repair, background metadata refresh, delayed view refresh, service repair readiness |
| `test_logs.py` | logging by area: each switch, warnings and errors always, the area tag, the old switches' migration, what Mixing, Radio and the checks write |
| `test_shared_helpers.py` | helpers duplicated in `main.py` and `service.py` behave the same |
| `test_context_mix.py` | the "Create Incipit mix" library context menu entry |
| `test_context_radio.py` | the "Start Incipit radio" library context menu entry |
| `test_findings.py` | `docs/findings.md` lists exactly the known-issue tests that still fail |

### Known issues

Known issues are tracked in [findings.md](findings.md). Tests marked `@unittest.expectedFailure` reproduce open findings; `test_findings.py` keeps the two in step.

## Discovery mode tests

Recommended tests:

1. Start Discovery mode
2. Confirm playback starts from a non-zero offset
3. Confirm the playlist is initially filled
4. Confirm no second playlist rebuild happens shortly after start
5. Confirm automatic next happens after the excerpt length
6. Confirm manual next does not double-skip
7. Confirm Stop disables Discovery mode
8. Confirm Discovery screen remains visible after start/stop/next
9. Confirm Generate mix opens parameter dialog
10. Confirm cancelling dialog resumes or skips according to dialog duration
11. Confirm confirming dialog stops Discovery and plays the generated mix
12. Confirm starting playback outside the add-on stops Discovery mode but keeps external playback running

## Repair tests

Recommended tests:

1. Missing file with no candidate: no automatic repair
2. Moved/renamed track with unique candidate: automatic repair
3. Multiple candidates: no false automatic repair
4. Library too old: show update-library-before-repair
5. Library fresh enough: show repair option
6. Repaired mix keeps its date-group order
