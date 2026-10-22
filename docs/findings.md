# Findings

Problems found in the add-on code during reviews and testing, with their current status.

How this file is kept up to date:

- Each finding has a permanent number (F1, F2, …). New findings get the next free number.
- A fixed finding moves to **Resolved**, keeping its number, with the commit that fixed it.
- A finding reproduced by a test lists that test under **Test**. Such tests are marked `@unittest.expectedFailure`. `tests/test_findings.py` checks that every one of these tests is listed under **Open**, and that every test listed under **Open** still fails. When a fix makes such a test pass, CI fails until the decorator is removed and the finding is moved to **Resolved**.

Last reviewed: 2026-10-22

## Open

### F14 · Kodi crashes while a mix listing is being built

Kodi crashed (access violation) twice while the add-on was building a folder listing:

- 2026-10-15, right after a new mix was generated inside the mix listing (`browse_mix`): in `xbmcplugin.addDirectoryItem()` → `CPluginDirectory::AddItem` → `CFileItemList::Add`, while copying a song's music tag.
- 2026-10-11: in `xbmcplugin.setPluginCategory()` → `CPluginDirectory::SetProperty`, the first call of a listing.

Both stacks were resolved with Kodi 21.3's debug symbols (`kodi-21.3-Omega-x64.pdb` from mirrors.kodi.tv matches the installed build). In both cases Kodi's object for the pending folder request was no longer valid when the add-on called into it. This happens when Kodi gives up a folder request while the add-on is still working on it, for example when the screen changes (`Container.Update`, `Container.Refresh`, Back) during a slow listing. Generating a mix inside a listing takes several seconds (MusicIP reload, the confirmation dialog, the mix itself), which leaves a wide window. F8 is the same pattern from the other side: actions run as folder requests that switch screens instead of returning a listing.

The add-on can't check whether Kodi still waits for a listing. A likely fix is to stop doing slow work and dialogs inside folder requests: generate mixes in a `RunPlugin` action, then show the stored mix with `Container.Update`, whose listing is fast.

Mitigated in 6f6ba14 (2026-10-17), not fixed (the fault is in Kodi): listings are handed to Kodi in one call (`addDirectoryItems`), and screen redraws from the background (the service, AI Mix Assist's tidy-up) wait while Kodi is loading a list (`Container.IsUpdating`, busy dialog). If it happens again, the next step is the one above: generate mixes outside a listing.

### F3 · "Unknown date" is listed first among saved mix dates

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

### F29 · "Settings" on the first screen has "Play" in its context menu

Found by the user on 2026-10-21: the context menu of "Settings" shows Play, Play using..., Play next, Queue item, Information and Add to favourites, like a song; the other entries of the first screen (folders) show only "Add to favourites". Kodi gives every entry that is not a folder its play entries, and an add-on can't remove Kodi's entries (only add its own).

"Settings" is an action, not a folder, since dd92060 (2026-10-10): as a folder Kodi expected a listing from it, logged an error, and the Back key could open the settings again. Options looked at on 2026-10-21: a folder again (brings those problems back), or taking "Settings" off the first screen (the add-on's settings stay reachable through Kodi's add-on menu). Kept as it is for now.

### F31 · MusicIP doesn't notice changed tags

Reported by the user on 2026-10-22: MusicIP's library reload (`/server/reload`, run by the service every 8 hours and after Kodi's music library scan) takes in new files, but it doesn't notice changed tags in files it already knows, even when the file's date has changed. MusicIP then keeps a song's old artist, album, title and genre while Kodi's library has the new ones.

Why it matters: good tags make good mixes. MusicIP uses its own copy of the tags, for example for "no artist repeat within N tracks" and for its filters, while the add-on and AI Mix Assist read Kodi's tags (labels, genre hints for the AI's ratings). Songs whose tags were corrected stay wrong on MusicIP's side, and the two libraries drift apart.

Not solved. Still to find out: whether MusicIP can be made to read a file's tags again (an API call, a setting, or removing the song from its library and taking it in again), and how the add-on could find the songs whose tags changed (for example Kodi's library dates against the time of the last reload). Taking in a song takes MusicIP minutes, one song at a time, so any fix has to touch only the changed songs and wait while Radio or Discovery plays.

## Resolved

### F28 · Saved mixes had "Information" twice in the context menu

Found by the user on 2026-10-20: since saved mixes are listed as albums (2026-10-19), their context menu showed "Information" twice: the add-on's own (the mix information) and Kodi's. Kodi adds its "Information" to every entry whose music tag is a song, an album, an artist or "music" (`CMusicInfoBase`), and it takes an entry with an artist for a song (`ListItem.DBType` "song"), whatever the add-on sets. With the song type came the song context items too, this add-on's "Create MusicIP mix" and "Start MusicIP radio" among them, on every menu entry and saved mix. Checked in the running Kodi with test entries: only entries without artist and without media type have an empty type, and get none.

Fixed in 3939672 (2026-10-20): menu entries and saved mixes have no artist and no media type; their second lines come from the album field (label2 mask `%B`, see F27). Two earlier attempts did not work: d8c68e0 dropped the media type "album" (Kodi then saw a song), 3cbf077 set the media type "music" (which has its own "Information").

### F27 · The add-on's second texts (Label2) were never shown

Found by the user on 2026-10-19: the first screen's Discovery and Radio entries showed "Folder" under their names instead of what they were doing. Kodi rewrites the Label2 of every add-on entry from the listing's label masks; without a sort method of the add-on's own, folders get none and files their duration. So every `setLabel2()` of the add-on was lost: the first screen's status texts, the saved mixes' seed song, a missing track's "Missing file", the tracks' origins. Arctic Fuse then shows a fallback ("Folder"). Checked in the running Kodi with a test listing: the Label2 stayed empty with the default masks and with `%h`.

Fixed in 43212c9 (2026-10-19): listings with second lines (the first screen, the saved mixes of a date) put them in the entries' artist field as well and ask for `%A` as the second label (`keep_second_lines()`), so skins that show the artist (Arctic Fuse) and skins that show Label2 both show them. A track's origin is shown after its name (a file's second label stays its duration). Still to be seen in Kodi.

### F26 · Drawing a mix's collage could delete another mix's collage

Found on 2026-10-19 while adding the fanart collage: `make_mix_collage()` removed the mix's older collages by the beginning of their file name. Mix files can be named `mix_<id>.m3u` and `mix_<id>_<time>.m3u`, so the first mix's name begins the second's, and drawing its collage deleted the other's. The service then drew that one again, and so on.

Fixed in c6d690b (2026-10-19), before it reached a user: older collages are matched by their exact name (`<mix>_<12 hex digits>[_fanart].jpg`). `test_main_mix_album.MixCollageTest.test_another_mixs_collages_are_left_alone` covers it.

### F25 · A redraw after "Refresh mix" asked for a new mix again

Found on 2026-10-18 while changing new mixes to the current mix. "Refresh mix" opens the mix with a URL that has `refresh=1`, and that URL stays the folder's URL. Kodi runs it again whenever the folder is redrawn: `Container.Refresh` after "Check consistency", or the service's redraw once background metadata has been looked up (`Container.Update(<folder>,replace)`), which often follows right after a new mix. Each redraw showed the generate dialog again and, when confirmed, made yet another mix. With the current mix the redraw could also fail: refreshing a current mix that wasn't saved deletes it, and the redraw then opened the deleted mix ("No stored mix found").

Fixed in 789eced (2026-10-18): the current mix remembers the nonce of the "Refresh mix" URL that made it, and a redraw with that nonce shows that mix. **Test:** `test_main_current_mix.RefreshRedrawTest`

### F24 · Redrawing the Radio and Discovery screens moved the focus to the first entry

Found by the user on 2026-10-18: while scanning, the Radio screen is redrawn with every snippet (F20), and the focus jumped back to the first entry each time, for example from "Skip station" to "Pick this station". Two causes: every entry's URL carried a new nonce on each redraw, so Kodi couldn't find the focused entry again, and the service redrew with `Container.Update(...,replace)`, which starts the screen afresh.

Fixed in af61f96 (2026-10-18): the entries of both screens have the same URL on every redraw, and the service redraws with `Container.Refresh`, which keeps the focused entry. `test_radio_mode.RadioMenuTest` and `test_main_discovery.DiscoveryMenuFocusTest` check the stable URLs; that Kodi then keeps the focus is Kodi's behaviour and needs a look in Kodi.

Not enough, found by the user on 2026-10-21: the Radio screen's own actions (Skip station, Pick this station, ...) still redrew it with `Container.Update` and a new URL, so after every skip the focus was back on the first entry. Fixed in b353f8e (2026-10-21): on the Radio screen itself they refresh it (`replace_with_radio_mode_menu()`). The Discovery screen's actions are folders (F8) and still jump to the first entry.

### F20 · The Radio screen kept the first snippet's title while scanning

Found by the user on 2026-10-17: while scanning, the Radio screen's title ("Radio: scanning - <song>") showed the first snippet correctly but was not updated when the next snippet started. The screen was only rebuilt after an action on it.

Fixed in a03ba20 (2026-10-17): the service requests a redraw whenever the snippet changes, if the Radio screen is open. `test_radio_mode.TuningTest.test_the_radio_screen_follows_the_snippets` covers it.

### F18 · Radio songs were labelled "(Unknown Artist)"

Found by the user on 2026-10-15: a new station's playlist showed many songs as "(Unknown Artist) - <file name>". Starting a station and topping it up built the labels from the metadata cache only (`allow_live_lookup=False`), and a station's songs are mostly new to that cache. A Radio test even expected the unknown artist.

Fixed in b71f766 (2026-10-15): both look the songs up in the Kodi library. `test_radio_mode.StationTest.test_songs_are_labelled_with_their_artists` and `StartRadioTest.test_labels_have_no_numbers_and_no_snippet_title` cover it.

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
