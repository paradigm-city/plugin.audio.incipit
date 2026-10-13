# Findings

Problems found in the add-on code during reviews and testing, with their current status.

How this file is kept up to date:

- Each finding has a permanent number (F1, F2, …). New findings get the next free number.
- A fixed finding moves to **Resolved**, keeping its number, with the commit that fixed it.
- A finding reproduced by a test lists that test under **Test**. Such tests are marked `@unittest.expectedFailure`. `tests/test_findings.py` checks that every one of these tests is listed under **Open**, and that every test listed under **Open** still fails. When a fix makes such a test pass, CI fails until the decorator is removed and the finding is moved to **Resolved**.

Last reviewed: 2026-10-13

## Open

### F2 · Cancelling the filter input clears the mix filter

In the generate-mix dialog, `edit_mix_generation_parameter()` in `main.py` only ignores `None` from `Dialog().input()`. Kodi returns `""` when the dialog is cancelled, so cancelling replaces the filter with an empty one.

Kodi can't tell "cancelled" apart from "cleared on purpose", so a fix needs a UX decision. One option is a separate "Clear filter" choice.

**Test:** `test_main_mix_parameters.ConfirmMixGenerationDialogTest.test_cancelling_the_filter_input_keeps_the_filter`

### F3 · "Unknown date" is listed first among recent mix dates

`group_saved_mixes_by_date()` in `main.py` gives "Unknown date" a sort key meant to put it last, but then sorts with `reverse=True`, so it comes first. This only affects mixes whose save time can't be read.

**Test:** `test_main_saved_mixes.OrderingAndCleanupTest.test_unknown_date_group_sorts_last`

### F8 · Menu actions are folders but return no listing

In the main menu and the Discovery menu, these entries are added as folders, but their actions never call `endOfDirectory()`. They switch screens with `Container.Update(…,replace)` instead:

- **Generate mix from playing audio** (`generate_current_mix`, on success)
- **Start discovery mode**, **Skip to next discovery song**, **Stop discovery mode**, **Create mix from current discovery song** (`discovery_start`, `discovery_next`, `discovery_stop`, `discovery_mix_current`)

For **Settings** the same pattern produced `XFILE::CDirectory::GetDirectory - Error getting plugin://plugin.audio.musicip/?action=open_settings` in `kodi.log` (fixed in dd92060). For these entries no such error has been seen in `kodi.log` so far, likely because the screen switch cancels Kodi's pending folder request.

**Test:** `test_main_plugin_routes.FolderEntriesTest.test_folder_entries_end_their_directory`

### F11 · More unused code in main.py

These plugin functions are never called:

- `get_mix_style_api_value()`; the style value for MusicIP is computed in `get_effective_mix_parameters()` and `normalize_mix_parameters()` instead
- `build_mix_parameter_summary()`; the generate-mix dialog builds its own lines
- `add_discovery_run_action_item()`; the Discovery menu uses `add_discovery_action_item()`

Found on 2026-10-11 while removing the Discovery command channel (F6). They are unrelated to that change.

### F12 · Seeds with characters outside ISO-8859-1 can't be mixed

`build_musicip_parameter_query()` in `main.py` percent-encodes the seed path as ISO-8859-1 with `errors="replace"`. The MusicIP server on Windows expects the Windows code page (cp1252), which also contains characters that ISO-8859-1 lacks, such as œ, Š, ’, “ ”, –, … and €. For a seed whose path contains one of them, the add-on sends `?` instead, and MusicIP answers HTTP 500, so no mix can be created from that track.

Checked against the local MusicIP server (1.9) with `D:\music\#jazzhop\Jazz Liberatorz\Clin d'œil (2007)\01 Jazz Liberatorz - Clin d'œil.mp3`: ISO-8859-1 and UTF-8 give HTTP 500, cp1252 returns a mix. MusicIP's responses are not affected (the returned paths decode correctly). Found on 2026-10-13 during the style pilot's replacement dry run.

A fix would encode the seed as cp1252, falling back to ISO-8859-1 only for characters cp1252 can't represent.

**Test:** `test_main_mix_parameters.ParameterQueryTest.test_seed_outside_latin_1_is_encoded_as_cp1252`

## Resolved

### F6 · The service's Discovery commands were never sent

The service still read and handled `start`, `stop` and `next` commands from `discovery_mode_command.json`, but nothing wrote that file any more: the plugin starts, stops and skips Discovery mode directly, and the service runs it through the shared state file. Inside that dead code, the branch that would adopt an already-started playlist could never run.

The command channel is removed: the command handling in `run_discovery_tick()`, `read_discovery_command()`, `command_is_stale_for_state()`, `start_discovery_playlist()`, `discovery_command_path()` in both modules, and the startup step that deleted a stale command file. A leftover command file from an older version is ignored.

Fixed in bf07e7c (2026-10-11). Service tests now start Discovery mode through the plugin; `test_service_discovery.LeftoverCommandFileTest` covers the leftover file.

### F10 · A music source that was never scanned counted as part of the library

Kodi lists every configured music source, including sources that were never scanned into the library, and "Update library" does not cover those. The disk search skipped all configured sources, so a file moved into a never-scanned source was not reported, and repair readiness said "ready" although the file could never reach the library. Seen on 2026-10-10 with `#jazz_fusion_progressive`, `#jazz_general` and `#jazz_nordic_ambient`; the fixed search finds 31 of the 34 missing files there.

A source now counts as part of the library only if the library holds songs below it. The search walks the other sources like any folder. A missing file found in a never-scanned source triggers a notification naming the source, and readiness becomes **Scan music source before repair**, which asks whether to scan the source and starts the scan. Readiness checks the source live, so it clears once the source has library songs.

Fixed in e4d1501 (2026-10-10). Covered by `test_repair_sources.UnscannedSourceTest`.

### F9 · Repair readiness could stay blocked although the library was up to date

Readiness used to compare Kodi's library timestamps with the latest time the add-on detected a missing track. When the library was updated before the check noticed, later scans changed nothing, the timestamps never moved, and repair stayed blocked. On 2026-10-10 this blocked 18 mixes after three library scans.

Readiness now asks the Kodi library about each missing file (`evaluate_repair_readiness()` in `main.py`, also used by the service). Repair is ready once the library no longer lists any of them. If it still lists some, **Update library before repair** names them, and repair is not offered if the library cannot be queried. Timestamps are no longer used. The concept doc and the readiness flow diagram describe the new rule.

Fixed in 7de4f3b (2026-10-10). Covered by `test_main_saved_mixes.RepairReadinessDeadlockTest` and `RepairReadinessTest`.

### F7 · The service start message showed the add-on prefix twice

`main()` in `service.py` passed a message that already started with `[plugin.audio.musicip]` to `log()`, which added the prefix again. The start line now has a single prefix, and it is always logged at info level, also without extended service logging.

Fixed in e37c424 (2026-10-10).

### F1 · The background consistency check and automatic repair never ran

`run_consistency_check()` in `service.py` only logged "Consistency service check skipped in this build branch.", so saved mixes were never checked in the background and the consistency settings had no effect.

It now runs on the configured interval: it checks every saved mix for missing files, records consistency and repair readiness in the mix's sidecar, and, with **Enable automatic mix repair** on and the library newer than the inconsistency, repairs tracks that have a unique high-confidence candidate. Covered by `test_service_metadata.BackgroundConsistencyCheckTest`.

Fixed in c3b09df (2026-10-10).

### F5 · Unused code

Functions nothing called were removed:

- `main.py`: `write_discovery_command`, `discovery_mode_is_active`, `discovery_current_song`, `discovery_mode_url`, `refresh_discovery_mode_menu`, `discovery_status_label`.
- `service.py`: `start_discovery_song`, `play_discovery_file_at_offset`, `correct_discovery_seek_position`, `seek_discovery_player_to_offset`, `jsonrpc_time_from_seconds`, `request_discovery_menu_refresh`, and the second, identical definition of `get_song_duration_seconds()`.

The unused auto-repair functions were kept for F1.

Fixed in 45746d8 (2026-10-10).

### F4 · A track without artist was labelled "1. - Title"

With Kodi's default track format `[%N. ]%A - %T`, `format_mix_track_label()` left the separator in place when the artist was missing. Missing artists and titles now show as `(Unknown Artist)` and `(Unknown Title)`. The file name is still used as the title when there is one.

Fixed in 5d1e1b6 (2026-10-10).
