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

- 2026-10-17, opening a stored mix (`browse_mix`, "Loaded stored mix from cache"), about 0.1 s into adding its tracks: again in `xbmcplugin.addDirectoryItem()` → `CPluginDirectory::AddItem` → `CFileItemList::Add`, this time while inserting into the list's lookup map. No mix was being generated, so the listing itself was fast.

- 2026-10-25, during Radio playback: `kodi.old.log` ends at 09:58:18, right after a song change ("now playing 'Extrawelt - Zu Fuss'", no check running, no listing being built). Kodi left no crash dump this time, so the cause is unknown and may not be this pattern.

All three stacks were resolved with Kodi 21.3's debug symbols (`kodi-21.3-Omega-x64.pdb` from mirrors.kodi.tv matches the installed build). In all cases Kodi's object for the pending folder request was no longer valid when the add-on called into it. This happens when Kodi gives up a folder request while the add-on is still working on it, for example when the screen changes (`Container.Update`, `Container.Refresh`, Back) during a slow listing. Generating a mix inside a listing takes several seconds (MusicIP reload, the confirmation dialog, the mix itself), which leaves a wide window. F8 is the same pattern from the other side: actions run as folder requests that switch screens instead of returning a listing.

The add-on can't check whether Kodi still waits for a listing. The 2026-10-17 crash shows that a slow listing is not required: the add-on adds tracks one call at a time (40 calls for a 40-track mix), and the crash hits during that loop. Adding all items in one call (`xbmcplugin.addDirectoryItems`) would shrink that window to a single call. A likely fix is to stop doing slow work and dialogs inside folder requests: generate mixes in a `RunPlugin` action, then show the stored mix with `Container.Update`, whose listing is fast.

### F17 · A Radio test failed once

`test_radio_mode.StartFromAnySongTest.test_new_station_is_not_mistaken_for_other_playback` failed once on 2026-10-15 during a full test run (`stop_reason` was `''` instead of `external_playback`) and passed in the next 10 runs, alone and in the full suite. It failed once more later the same day (1 of about 20 full runs). On 2026-10-17 another Radio test, `test_radio_mode.TuningTest.test_no_redraw_while_kodi_is_loading_a_list`, failed once in a full run (no redraw where one was expected) and passed alone, in its module and in the next two full runs; likely the same cause. On 2026-10-19 the first test failed once more (1 of 2 full runs after a merge), again with `stop_reason` `''`. On 2026-10-21 two more Radio tests failed once each in full runs, `test_radio_mode.TuningTest.test_no_redraw_while_kodi_is_loading_a_list` (on `main`) and `test_radio_mode.TuningTest.test_the_radio_screen_follows_the_snippets`; both passed alone and in the next runs. On 2026-10-22 `test_no_redraw_while_kodi_is_loading_a_list` failed once more (no redraw, 0 builtins instead of 1) and passed in the next full run. On 2026-10-24 one test failed in a full run after a prompt-only change (`mixassist/checks.py`); the output wasn't kept, so which test is unknown, and the next three full runs passed. Later on 2026-10-24, `test_no_redraw_while_kodi_is_loading_a_list` failed once more in a full run after the listening-perspective change and passed in the next full run. On 2026-10-28 one test failed in a full run after the sound engine's decoding fix (`soundprint/audio.py`, which no Radio test touches); the output wasn't kept, and the next two full runs passed. The flaky failures are getting more frequent and all sit in the Radio tests. The test uses the fake clock, so the cause is probably state left behind by another test (a background thread or the fake MusicIP server) rather than real time. Not reproduced yet.

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

### F34 · A station whose first MusicIP list mostly doesn't fit runs dry

Seen by the user on 2026-10-24 with the favourite "Cold Precision Electro" (seed: Kraftwerk, "Vitamin"; drift "Stay close to the picked song"). The refill checks chose 0 of 6 songs three times in a row. MusicIP's list for "Vitamin" is mostly lounge, nu-jazz and downtempo (Thievery Corporation, dZihan & Kamien, Beanfield), which every perspective rejects. The AI accepted 2 of 144 candidates with Mixed (Close), 19 of 216 with Cultural (Close) and 9 of 216 with Emotional (5 of 72 at Close, 4 of 144 at Balanced). The checks were counted with the AI log; the perspective is not the cause.

Two things in the search make it worse:

- **Balanced examines fewer songs than Close.** `RADIO_CHECK_BATCHES` gives Focused 6 batches of 18, Close 4 and Balanced 2, because a stricter station needs more to choose from. When the list is mostly misfits, a station set to Balanced examines 36 songs and finds nothing, where the same station at Close examines 72.
- **The check stays on the first list.** `radio_more_candidates` brings MusicIP's lists for the songs that fit only when the first list runs out. That list has more than 70 candidates, so the batch limit always ends the check first ("2 batch(es) and 1 list(s)"). The songs that did fit, for example Fred und Luna's "Monotonikum", would seed better lists. With "Stay close", every refill asks MusicIP about "Vitamin" again and gets much the same list.

The same misfits were also judged again and again: that evening, 797 rejections were of only 534 different songs (Jazz Liberatorz' "Always Something" 7 times). Since 2026-10-24 a playing station remembers the songs its checks turned down and leaves them out of later checks, so a check reaches new songs sooner (see `concept_radio_mode.md`).

Still open: move on to the next list when a batch brings almost nothing (for example 0 or 1 of 18), and give a check that keeps choosing too little more batches. Not decided yet.

On 2026-10-25, with Emotional from the artist's side, the same station got 7 songs from 4 checks (2, 1, 1 and 3 of about 70 examined each, always from 1 list). The user reproduced the thin suggestions in MusicIP itself, and added compilations and fringe music to the library in the hope of better lists. A second limit showed in that log: see F35. MusicIP was then scanning the new folders, so later lists for this seed may differ; the counts above are from before.

### F31 · MusicIP doesn't notice changed tags

Reported by the user on 2026-10-22: MusicIP's library reload (`/server/reload`, run by the service every 8 hours and after Kodi's music library scan) takes in new files, but it doesn't notice changed tags in files it already knows, even when the file's date has changed. MusicIP then keeps a song's old artist, album, title and genre while Kodi's library has the new ones.

Why it matters: good tags make good mixes. MusicIP uses its own copy of the tags, for example for "no artist repeat within N tracks" and for its filters, while the add-on and AI Mix Assist read Kodi's tags (labels, genre hints for the AI's ratings). Songs whose tags were corrected stay wrong on MusicIP's side, and the two libraries drift apart.

Not solved. Still to find out: whether MusicIP can be made to read a file's tags again (an API call, a setting, or removing the song from its library and taking it in again), and how the add-on could find the songs whose tags changed (for example Kodi's library dates against the time of the last reload). Taking in a song takes MusicIP minutes, one song at a time, so any fix has to touch only the changed songs and wait while Radio or Discovery plays.

### F36 · The sound engine can suggest songs that are no longer in the library

Found on 2026-10-28 while planning how to keep the sound prints in step with Kodi's library. The analysis started by the add-on (`soundprint.client.start_analysis`) only adds new and changed songs; it never removes stored songs that Kodi's library no longer lists (`python -m soundprint analyse --prune` would, but nothing passes it). `soundprint.neighbours.nearest` searches every stored song and `main.fetch_sound_mix` doesn't check that the files still exist, so a deleted song, or the old path of a moved or renamed one, can end up in a mix. Kodi then can't play it. Such a song also escapes the "same song only once" rule, because the Kodi lookup finds no artist or title for it.

Not fixed. The planned fix is the library sync: remove a song's sound print when Kodi removes the song, prune at startup, and leave out stored songs that Kodi doesn't list when searching.

### F40 · AI Mix Assist's profile check is measured against the candidate list itself

Found on 2026-10-29 while widening the sound engine's variety, so that loose mixes cross genres and AI Mix Assist keeps them consistent. `assist.analyze` scales every dimension by the spread of the list it checks (`fit.mix_spreads`) and calls a track off when its misfit is more than 1.2 × the list's median misfit. So the looser the list, the more of it passes than its distance from the seed warrants. Only the second rule (a single dimension off by 5 points or 25 years) is absolute. On mixes of 25 from the whole library (`tools/style_pilot/data/variety_2026-10-29/variety_scale.txt`; the seeds Kraftwerk, Holdsworth, Machacek), 59 / 75 / 70% pass at variety 0 and 34 / 44 / 29% at variety 9. On a fixed scale taken from the seed's 35 nearest songs, 59 / 56 / 30% fit at variety 0 and 19 / 30 / 24% at variety 9. Within a rank band the gap is larger: of the songs ranked 3,000 to 10,000 for Allan Holdsworth, 24% fit on the fixed scale and 46% on their own (`variety_survey.txt`).

This was calibrated on MusicIP's mixes, which are close to their seed anyway. With loose candidate lists, the profile check gets more lenient just when it should hold the mix together, and more of the consistency rests on the AI's verdict. A possible fix is to measure against a fixed scale per seed (for example its nearest songs by sound, or the spread of the library's rated units around the seed) instead of the list's own.

## Resolved

### F39 · The service ignored settings changed while Kodi runs

Found on 2026-10-29: the user chose the sound engine in the settings after Kodi had started, with MusicIP shut down. Radio's first songs came from the sound engine (the plugin reads the settings anew on every call), but the service's start check and every refill still asked MusicIP, failed ("Could not reach MusicIP server"), and the station ran dry after one song; the service also tried MusicIP's library reload. Kodi gives every `xbmcaddon.Addon` its own copy of the settings, read when it is made, and the service made its copies once at start: its own `ADDON`, the plugin module's (loaded by the service) and the logging switches' (`logs.ADDON`). So any setting changed while Kodi runs (logging switches, intervals, AI Mix Assist settings, the engine) reached the service only after a restart.

Fixed on 2026-10-29 (c4a98e7, tests 07c49c5): `ServiceMonitor.onSettingsChanged` calls `service.reload_settings()`, which makes all three anew and logs "Settings changed: the service reads them again. Mixes come from … (before: …)" and the logging switches.

**Test:** `test_soundprint_client.SettingsChangeTest.test_the_service_reads_changed_settings_again`

### F38 · The AI judge turned down little-known music for an intent it read from a guessed description

Found by the user on 2026-10-29 in the sound engine pilot (Kraftwerk "Vitamin", Emotional). The rating guesses a description for music it doesn't know (familiarity 0), from the names, the album and the genre, and the judge took such guesses as fact. It turned down three little-known 80s synth tracks for their intent: Satellite & Atom Cristal "Boulevard Circulaire" (outlier, "eighties synthpop going for pop appeal"), Tara Cross "City Limit" (borderline, "leans toward pop mood over concept") and Paul Nagle "Journey" (borderline, "more style exercise than statement"). The user hears all three as fitting. An intent can't be told from names; only the fourth, Im Namen des Volkes "Haushaltsmaschine" (borderline, retro Kraftwerk/DAF homage), was turned down for a reason the user shares (X or b), though for its style rather than its emotion.

Fixed on 2026-10-29 (c4a98e7, tests 07c49c5): `checks.track_line` marks lines of music the rating didn't know with "(little known)", and the note every check prompt ends with says such a description is a guess; the judge is not to turn such a track down only because the guess suggests another intent (pop appeal, nostalgia, pastiche, a use), only when what is known clearly clashes. On the pilot's 5 lists (175 verdicts) the little-known units went from 16 fits / 19 borderline / 14 outliers to 32 / 9 / 8, the others from 44 / 38 / 44 to 48 / 45 / 33 (the judge's run-to-run variance is of that size). All four tracks above now fit, Haushaltsmaschine included, which the user would turn down. Little-known tracks that clearly clash stay out, for example J. P. & Company's boogie soul and a smooth-jazz cover of "Aja" on the Machacek lists. Still to check by ear: whether the rule now lets in too much (`tools/style_pilot/data/soundprint_pilot_2026-10-29/compare_little_known.txt`).

**Test:** `test_mixassist_tidy_up.ChecksTest.test_music_the_rating_did_not_know_is_marked_as_little_known`

### F37 · The sound engine's analysis couldn't read 68 songs

The first full analysis (2026-10-28, 152,975 songs) failed on 68 files that Kodi plays:

- 44 MP3s inside a WAV file with an ID3 tag in front, and 5 Musepack files (`.mpc`) with an ID3 tag in front: FFmpeg doesn't look for the RIFF or Musepack header behind the tag (`InvalidDataError`);
- 6 MP3s with an ID3 tag over 1 MB (a large cover): FFmpeg found no audio in them (`InvalidDataError`, once `IndexError`);
- 12 damaged MP3s (from 1 to 1,663 damaged packets): a false frame start in the damage decodes as a frame of another sample rate or channel layout, and the resampler refuses it (`ValueError: Frame does not match AudioResampler setup`).

Fixed in dfd4698 (2026-10-28) in `soundprint/audio.py`: a file FFmpeg finds no audio in is opened again from where its ID3 tag ends (`opened`, `tag_end`, `FileFrom`), and frames of another sample rate or layout than the song's are left out. Songs that failed stay failed until their file changes, so `python -m soundprint analyse --retry-failed` analyses them again; that run read all 68 (62 by seeking, 6 whole). The damaged-frame rule was checked on the 12 files, not by a test.

**Test:** `test_soundprint.TagTest`, `test_soundprint.DecodingTest.test_a_wave_file_behind_an_id3_tag_is_read_after_the_tag`, `test_soundprint.PlanTest.test_songs_that_failed_before_are_analysed_again_when_asked`

### F35 · Radio gives the AI's "fits" reason for songs the profile check turned down

Seen on 2026-10-25 in the log of "Cold Precision Electro" (Emotional). A song is added only when both signals say it fits (`assist.passes`). When the AI says "fits" but the profile check doesn't, `choose_additions` records the AI's reason in `not_fitting`, so the Radio log shows `doesn't fit: 'Jeff Mills - DNA': Stripped hypnotic techno, machine precision and repetition`, which reads like a fit. The `[ai]` trace has the real cause ("clearly off in production"), the Radio lines don't. The station's memory of turned-down songs also keeps these songs, so they are not checked again while it plays, even if the station drifts towards them.

In that session the profile check overruled 5 of the AI's 14 fits, all for one dimension clearly off in production (the single-dimension rule): Cinephile "One", Human League "All I Ever Wanted (Minimal Demo)", Symboter "Silent Storm", Jeff Mills "DNA" and "Solid Sleep". Emotional's prompt says production doesn't matter unless it carries the statement; the profile check weighed it the same for every perspective.

Fixed in 476c940 (2026-10-25): `assist.turned_down_reason` gives the profile's reason when the AI would have taken the song ("the AI says it fits, but its profile is clearly off in production (production: natural vs. glossy; …)"), in the Radio log, the trace and the station's skipped songs. Emotional leaves production out of the profile check (`assist.PROFILE_LEAVES_OUT`); replayed on that session, 3 of the 5 songs pass (see `concept_ai_mix_assist.md`, *Emotional leaves production out of the profile check*).

**Test:** `test_mixassist_tidy_up.AssistTest.test_a_song_the_ai_would_take_is_turned_down_with_the_profiles_reason`, `test_mixassist_tidy_up.AssistTest.test_emotional_leaves_production_out_of_the_profile`

### F32 · A favourite station's artwork could stay without its number

Found by the user on 2026-10-24: station 10's artwork had no number. While it played on 2026-10-23, the background service was still running the add-on code from before favourites had numbers (the service loads `main.py` once, at Kodi's start) and saved the station's newest collage without the number. The check for artwork to (re)draw only compared the stored look of the number (`artwork_mark`), which that save had left in place, so the unnumbered picture was taken as done.

Fixed on 2026-10-24: a favourite's picture counts as numbered only when its original (without the number) is the one saved with it (`plain_favourite_artwork_path`); any other picture gets the number on the next load. Station 10 was redrawn that way.

**Test:** `test_radio_favourites.FavouriteNumberTest.test_artwork_saved_without_the_number_by_older_code_gets_it`

### F30 · Tests wrote a usage.db into the working directory

Found on 2026-10-22: after a full test run from `tests/`, an untracked `tests/profile/addon_data/plugin.audio.musicip/mixassist/usage.db` appeared (from the repository root it lands in `profile/`, which `.gitignore` had been hiding). The mixassist tests report usage events (`mixassist.usage.emit`) while no test Kodi is set up; importing `main.py` had registered its sink, and the fake Kodi then translated `special://profile` with an empty root, into a relative path.

Fixed in the test fakes: `fake_kodi` refuses `special://` paths outside a test's Kodi, so such events are dropped (`emit` never fails the work it reports).

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

Fixed in af61f96 on `main`, 126d927 on `ai-mix-assist` (2026-10-18): the entries of both screens have the same URL on every redraw, and the service redraws with `Container.Refresh`, which keeps the focused entry. `test_radio_mode.RadioMenuTest` and `test_main_discovery.DiscoveryMenuFocusTest` check the stable URLs; that Kodi then keeps the focus is Kodi's behaviour and needs a look in Kodi.

### F23 · The information window left two errors in Kodi's log

Found in the log on 2026-10-18: each time the information window opened, Kodi logged "Control 201 in window 13000 has been asked to focus, but it can't" (the first tab was hidden until the window's properties were set, so the window opened without focus), and some 10 to 40 seconds after it closed, "EXCEPTION: Window id does not exist" (a focus change reported while the window closed reached a window that was gone).

Fixed in e1321be (2026-10-18): the first tab is always shown, and focus changes on a closing window are ignored. `test_main_plugin_routes.MixInfoTest` covers both.

### F22 · Radio asked a failing MusicIP every minute, silently

Found on 2026-10-18 from the log: MusicIP answered every mix with HTTP 500 ("MusicIP API error - invalid request or internal error"), for every song, while it still knew the songs (`/api/getSong` worked). A restart of the MusicIP server is the remedy; the add-on can't repair it. But the station asked again every minute, each time with a server reload, and nothing told the listener; the station would simply have run dry.

Fixed in e1321be (2026-10-18): a refill whose song fails tries the song before it, without another reload (a single song may be the problem). When that fails too, the station waits 1, 2, 4, 8, then 10 minutes between tries, shows one notification ("MusicIP can't make mixes right now ... restart the MusicIP server") and records the outage, and MusicIP's return, in "Station information". `test_radio_mode.StationTest` covers it.

### F21 · Estuary's Noto Sans draws broken glyphs in Pillow

Found on 2026-10-17 while building the information window: text drawn into the charts with Estuary's `NotoSans-Regular.ttf` came out with parts of the glyphs missing ("Polished" looked like "Folished", 9 like a reversed c), in Pillow 12 (FreeType 2.14) as well, with both layout engines. Kodi itself draws the font correctly. Kodi's own `media/Fonts/arial.ttf` (DejaVu Sans), which every Kodi installation has, draws correctly.

Avoided in e566303 (2026-10-17), before it reached a user: the charts use `special://xbmc/media/Fonts/arial.ttf`.

Not enough, found by the user on 2026-10-21: the Radio screen's own actions (Skip station, Pick this station, ...) still redrew it with `Container.Update` and a new URL, so after every skip the focus was back on the first entry. Fixed in b353f8e (2026-10-21): on the Radio screen itself they refresh it (`replace_with_radio_mode_menu()`). The Discovery screen's actions are folders (F8) and still jump to the first entry.

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
