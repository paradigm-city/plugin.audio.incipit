# Findings

Problems found in the add-on code during reviews and testing, with their current status.

How this file is kept up to date:

- Each finding has a permanent number (F1, F2, …). New findings get the next free number.
- A fixed finding moves to **Resolved**, keeping its number, with the commit that fixed it.
- A finding reproduced by a test lists that test under **Test**. Such tests are marked `@unittest.expectedFailure`. `tests/test_findings.py` checks that every one of these tests is listed under **Open**, and that every test listed under **Open** still fails. When a fix makes such a test pass, CI fails until the decorator is removed and the finding is moved to **Resolved**.

Last reviewed: 2026-10-15

## Open

### F14 · Kodi crashes while a mix listing is being built

Kodi crashed (access violation) twice while the add-on was building a folder listing:

- 2026-10-15, right after a new mix was generated inside the mix listing (`browse_mix`): in `xbmcplugin.addDirectoryItem()` → `CPluginDirectory::AddItem` → `CFileItemList::Add`, while copying a song's music tag.
- 2026-10-11: in `xbmcplugin.setPluginCategory()` → `CPluginDirectory::SetProperty`, the first call of a listing.

- 2026-10-17, opening a stored mix (`browse_mix`, "Loaded stored mix from cache"), about 0.1 s into adding its tracks: again in `xbmcplugin.addDirectoryItem()` → `CPluginDirectory::AddItem` → `CFileItemList::Add`, this time while inserting into the list's lookup map. No mix was being generated, so the listing itself was fast.

All three stacks were resolved with Kodi 21.3's debug symbols (`kodi-21.3-Omega-x64.pdb` from mirrors.kodi.tv matches the installed build). In all cases Kodi's object for the pending folder request was no longer valid when the add-on called into it. This happens when Kodi gives up a folder request while the add-on is still working on it, for example when the screen changes (`Container.Update`, `Container.Refresh`, Back) during a slow listing. Generating a mix inside a listing takes several seconds (MusicIP reload, the confirmation dialog, the mix itself), which leaves a wide window. F8 is the same pattern from the other side: actions run as folder requests that switch screens instead of returning a listing.

The add-on can't check whether Kodi still waits for a listing. The 2026-10-17 crash shows that a slow listing is not required: the add-on adds tracks one call at a time (40 calls for a 40-track mix), and the crash hits during that loop. Adding all items in one call (`xbmcplugin.addDirectoryItems`) would shrink that window to a single call. A likely fix is to stop doing slow work and dialogs inside folder requests: generate mixes in a `RunPlugin` action, then show the stored mix with `Container.Update`, whose listing is fast.

### F17 · A Radio test failed once

`test_radio_mode.StartFromAnySongTest.test_new_station_is_not_mistaken_for_other_playback` failed once on 2026-10-15 during a full test run (`stop_reason` was `''` instead of `external_playback`) and passed in the next 10 runs, alone and in the full suite. It failed once more later the same day (1 of about 20 full runs). On 2026-10-17 another Radio test, `test_radio_mode.TuningTest.test_no_redraw_while_kodi_is_loading_a_list`, failed once in a full run (no redraw where one was expected) and passed alone, in its module and in the next two full runs; likely the same cause. The test uses the fake clock, so the cause is probably state left behind by another test (a background thread or the fake MusicIP server) rather than real time. Not reproduced yet.

Mitigated in 6f6ba14 (2026-10-17), not fixed (the fault is in Kodi): listings are handed to Kodi in one call (`addDirectoryItems`), and screen redraws from the background (the service, AI Mix Assist's tidy-up) wait while Kodi is loading a list (`Container.IsUpdating`, busy dialog). If it happens again, the next step is the one above: generate mixes outside a listing.

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

## Resolved

### F24 · Redrawing the Radio and Discovery screens moved the focus to the first entry

Found by the user on 2026-10-18: while scanning, the Radio screen is redrawn with every snippet (F20), and the focus jumped back to the first entry each time, for example from "Skip station" to "Pick this station". Two causes: every entry's URL carried a new nonce on each redraw, so Kodi couldn't find the focused entry again, and the service redrew with `Container.Update(...,replace)`, which starts the screen afresh.

Fixed in 126d927 (2026-10-18): the entries of both screens have the same URL on every redraw, and the service redraws with `Container.Refresh`, which keeps the focused entry. `test_radio_mode.RadioMenuTest` and `test_main_discovery.DiscoveryMenuFocusTest` check the stable URLs; that Kodi then keeps the focus is Kodi's behaviour and needs a look in Kodi.

### F23 · The information window left two errors in Kodi's log

Found in the log on 2026-10-18: each time the information window opened, Kodi logged "Control 201 in window 13000 has been asked to focus, but it can't" (the first tab was hidden until the window's properties were set, so the window opened without focus), and some 10 to 40 seconds after it closed, "EXCEPTION: Window id does not exist" (a focus change reported while the window closed reached a window that was gone).

Fixed in e1321be (2026-10-18): the first tab is always shown, and focus changes on a closing window are ignored. `test_main_plugin_routes.MixInfoTest` covers both.

### F22 · Radio asked a failing MusicIP every minute, silently

Found on 2026-10-18 from the log: MusicIP answered every mix with HTTP 500 ("MusicIP API error - invalid request or internal error"), for every song, while it still knew the songs (`/api/getSong` worked). A restart of the MusicIP server is the remedy; the add-on can't repair it. But the station asked again every minute, each time with a server reload, and nothing told the listener; the station would simply have run dry.

Fixed in e1321be (2026-10-18): a refill whose song fails tries the song before it, without another reload (a single song may be the problem). When that fails too, the station waits 1, 2, 4, 8, then 10 minutes between tries, shows one notification ("MusicIP can't make mixes right now ... restart the MusicIP server") and records the outage, and MusicIP's return, in "Station information". `test_radio_mode.StationTest` covers it.

### F21 · Estuary's Noto Sans draws broken glyphs in Pillow

Found on 2026-10-17 while building the information window: text drawn into the charts with Estuary's `NotoSans-Regular.ttf` came out with parts of the glyphs missing ("Polished" looked like "Folished", 9 like a reversed c), in Pillow 12 (FreeType 2.14) as well, with both layout engines. Kodi itself draws the font correctly. Kodi's own `media/Fonts/arial.ttf` (DejaVu Sans), which every Kodi installation has, draws correctly.

Avoided in e566303 (2026-10-17), before it reached a user: the charts use `special://xbmc/media/Fonts/arial.ttf`.

### F20 · The Radio screen kept the first snippet's title while scanning

Found by the user on 2026-10-17: while scanning, the Radio screen's title ("Radio: scanning - <song>") showed the first snippet correctly but was not updated when the next snippet started. The screen was only rebuilt after an action on it.

Fixed in a03ba20 (2026-10-17): the service requests a redraw whenever the snippet changes, if the Radio screen is open. `test_radio_mode.TuningTest.test_the_radio_screen_follows_the_snippets` covers it.

### F19 · AI Mix Assist judged replacement candidates several times

Found by the user on 2026-10-17: tidying up a new 40-track mix showed "asking the AI about 300 tracks". The mix had 7 gaps; gaps that share a submix seed share one larger submix (F16), but the shared list was added to the round's candidates once per gap. Rating was not affected (each album is rated once), but the AI's judging call got the same tracks two or three times: slower and costlier, with the same result.

Fixed in 982a7a6 (2026-10-17): the candidates are deduplicated. `test_mixassist_tidy_up.AssistTest.test_gaps_sharing_a_submix_seed_share_one_larger_submix` counts the tracks the AI judges.

### F18 · Radio songs were labelled "(Unknown Artist)"

Found by the user on 2026-10-15: a new station's playlist showed many songs as "(Unknown Artist) - <file name>". Starting a station and topping it up built the labels from the metadata cache only (`allow_live_lookup=False`), and a station's songs are mostly new to that cache. A Radio test even expected the unknown artist.

Fixed in b71f766 (2026-10-15): both look the songs up in the Kodi library. `test_radio_mode.StationTest.test_songs_are_labelled_with_their_artists` and `StartRadioTest.test_labels_have_no_numbers_and_no_snippet_title` cover it.

### F16 · AI Mix Assist left new mixes shorter than requested

Found by the user on 2026-10-15: two new 40-track mixes ended with 36 tracks after AI Mix Assist (4 replaced, 4 removed). The log showed why: gaps that shared a submix seed fetched the same 15 tracks again and competed for them, and the fallback asked the master seed for 45 tracks, most of which were already in the mix.

Fixed in 26ae462 (2026-10-15): gaps sharing a submix seed share one submix, every request asks MusicIP for 75 tracks and keeps the closest new ones, a gap may use any candidate of its round, and gaps still open get a second round of submixes from other clearly fitting tracks. `test_mixassist_tidy_up.AssistTest.test_gaps_sharing_a_submix_seed_share_one_larger_submix` and `test_open_gaps_get_submixes_from_other_fitting_tracks` cover it.

### F15 · Esc in "Edit what this mix is about" changed the intent

Found by the user on 2026-10-15: closing the editor with Esc showed "Saved. Tidy up the mix to apply it." `Dialog().input()` returns "" when cancelled, which the editor took as "go back to the AI's statement".

Fixed in 26ae462 (2026-10-15) with the keyboard dialog, as for F2. `test_main_mix_assist.EditIntentTest` covers it.

### F13 · Saved mixes had two context menu entries for the same information

The context menu of a saved mix listed both **Information** and **Show mix information**, which ran the same action. Found by the user on 2026-10-15.

Fixed in 10fd43d (2026-10-15): only **Information** is left. `test_main_plugin_routes` checks the menu.

### F2 · Cancelling the filter input clears the mix filter

In the generate-mix dialog, `edit_mix_generation_parameter()` in `main.py` only ignored `None` from `Dialog().input()`. Kodi returns `""` when that dialog is cancelled, so cancelling replaced the filter with an empty one.

Fixed in 10fd43d (2026-10-15): text input uses Kodi's keyboard dialog (`xbmc.Keyboard`), whose `isConfirmed()` tells "cancelled" apart from "cleared on purpose", so no extra "Clear filter" choice is needed. `test_main_mix_parameters.ConfirmMixGenerationDialogTest.test_cancelling_the_filter_input_keeps_the_filter` and `test_the_filter_can_be_cleared` cover it.

### F12 · Seeds with characters outside ISO-8859-1 couldn't be mixed

`build_musicip_parameter_query()` in `main.py` percent-encoded the seed path as ISO-8859-1 with `errors="replace"`. The MusicIP server on Windows expects the Windows code page (cp1252), which also contains characters that ISO-8859-1 lacks, such as œ, Š, ’, “ ”, –, … and €. For a seed whose path contained one of them, the add-on sent `?` instead, and MusicIP answered HTTP 500, so no mix could be created from that track. Found on 2026-10-13 during the style pilot's replacement dry run, with `Jazz Liberatorz – Clin d'œil` (ISO-8859-1 and UTF-8: HTTP 500; cp1252: a mix).

The seed is now encoded as cp1252. MusicIP's responses were never affected.

Fixed in 351c23a (2026-10-13). `test_main_mix_parameters.ParameterQueryTest.test_seed_outside_latin_1_is_encoded_as_cp1252` covers it; the fake MusicIP server decodes the seed as cp1252, like the real one.

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
