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

### F7 · The service start message shows the add-on prefix twice

`main()` in `service.py` passes a message that already starts with `[plugin.audio.musicip]` to `log()`, which adds the prefix again: `[plugin.audio.musicip] [plugin.audio.musicip] MusicIP service started. …`

**Test:** `test_service_metadata.ServiceStartupLogTest.test_service_start_message_has_a_single_addon_prefix`

## Resolved

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
