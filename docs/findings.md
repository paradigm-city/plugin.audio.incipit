# Findings

Problems found in the add-on code during reviews and testing, with their current status.

How this file is kept up to date:

- Each finding has a permanent number (F1, F2, …). New findings get the next free number.
- A fixed finding moves to **Resolved**, keeping its number, with the commit that fixed it.
- A finding reproduced by a test lists that test under **Test**. Such tests are marked `@unittest.expectedFailure`. `tests/test_findings.py` checks that every one of these tests is listed under **Open**, and that every test listed under **Open** still fails. When a fix makes such a test pass, CI fails until the decorator is removed and the finding is moved to **Resolved**.

Last reviewed: 2026-10-10

## Open

### F2 · Cancelling the filter input clears the mix filter

In the generate-mix dialog, `edit_mix_generation_parameter()` in `main.py` only ignores `None` from `Dialog().input()`. Kodi returns `""` when the dialog is cancelled, so cancelling replaces the filter with an empty one.

Kodi can't tell "cancelled" apart from "cleared on purpose", so a fix needs a UX decision. One option is a separate "Clear filter" choice.

**Test:** `test_main_mix_parameters.ConfirmMixGenerationDialogTest.test_cancelling_the_filter_input_keeps_the_filter`

### F3 · "Unknown date" is listed first among recent mix dates

`group_saved_mixes_by_date()` in `main.py` gives "Unknown date" a sort key meant to put it last, but then sorts with `reverse=True`, so it comes first. This only affects mixes whose save time can't be read.

**Test:** `test_main_saved_mixes.OrderingAndCleanupTest.test_unknown_date_group_sorts_last`

### F6 · The service's Discovery commands are never sent

The service runs Discovery mode: once the plugin has started playback and written the shared state file (`discovery_mode_state.json`), the service tracks the playlist, refills and prunes it, skips after each excerpt, corrects the start offset and reacts to player events. `tests/test_service_discovery.py` (`PluginStartedSessionTest`) covers this hand-over.

The service also still reads `start`, `stop` and `next` commands from `discovery_mode_command.json` in `run_discovery_tick()`, but the plugin no longer writes that file: it starts, stops and skips directly (its `write_discovery_command` was removed with F5). So this command handling never runs.

In the `start` handler, the branch that adopts an already-started playlist could not run anyway, because `state["queue"]` is emptied just before `existing_queue` is read from it.

### F8 · Menu actions are folders but return no listing

In the main menu and the Discovery menu, these entries are added as folders, but their actions never call `endOfDirectory()`. They switch screens with `Container.Update(…,replace)` instead:

- **Generate mix from playing audio** (`generate_current_mix`, on success)
- **Start discovery mode**, **Skip to next discovery song**, **Stop discovery mode**, **Create mix from current discovery song** (`discovery_start`, `discovery_next`, `discovery_stop`, `discovery_mix_current`)

For **Settings** the same pattern produced `XFILE::CDirectory::GetDirectory - Error getting plugin://plugin.audio.musicip/?action=open_settings` in `kodi.log` (fixed in dd92060). For these entries no such error has been seen in `kodi.log` so far, likely because the screen switch cancels Kodi's pending folder request.

**Test:** `test_main_plugin_routes.FolderEntriesTest.test_folder_entries_end_their_directory`

### F9 · Repair readiness can stay blocked although the library is up to date

`get_mix_repair_readiness()` in `main.py` (and its copy in `service.py`) allows repair only when Kodi's newest library timestamp (`librarylastupdated`, `librarylastcleaned`, `songslastadded`, `songsmodified`) is later than the **latest** time a missing track was detected in the mix.

The rule measures when the add-on *noticed* a file was missing, not when the file went missing. Kodi only moves those timestamps when a scan or clean actually changes something.

As a result:

- **It can block repair indefinitely.** If the library is scanned after files are moved but before the check notices (the check runs every 1–2 hours), every later scan finds nothing new, and repair stays blocked until something unrelated changes in the library. Seen on 2026-10-10: the library last changed at 20:43, the check found more missing tracks at 21:25, and three scans at 21:27–21:34 changed no timestamp. 18 mixes stayed blocked.
- **A newly missing track resets the whole mix.** One track going missing later moves the required time forward for all of the mix's missing tracks.
- **The message is misleading.** "Kodi audio library has not been updated since the latest detected inconsistency" appears right after the user updated the library.
- **Any library change counts.** For example, a tag edit on an unrelated album makes every mix "ready", even if the moved files were never scanned. This is harmless, because automatic repair still needs a confident candidate.
- **The docs disagree with the code.** `docs/concept_repair_strategy.md` and `repair_readiness_flow.mmd` compare against the *first* inconsistency with `>=`; the code uses the *latest* detection with `>`.

What is correct: Kodi stores these timestamps in UTC, and the add-on parses them as UTC. This was confirmed against the music database file's modification time.

A more direct rule is to ask the library about each missing track. If Kodi no longer lists the missing path, the library already reflects the change.

**Test:** `test_main_saved_mixes.RepairReadinessDeadlockTest.test_library_that_already_reflects_the_change_does_not_block_repair`

## Resolved

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
