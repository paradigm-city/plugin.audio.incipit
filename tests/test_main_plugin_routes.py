"""The plugin as Kodi runs it: router() actions, directory listings, context menus and playback."""

import os
import runpy
import sys
import time
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR, kodi
from support import HANDLE, PLUGIN_URL, KodiTestCase, MusicIPServerTestCase, main, plugin_query

# A Kodi track format whose artist separator is optional, so tracks without metadata read "1. Title".
TRACK_FORMAT = "[%N. ][%A - ]%T"
SEED = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
T1 = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
T2 = "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"


def item_by_label(label):
    for url, item, is_folder in kodi.directory_items:
        if item.getLabel() == label:
            return url, item, is_folder
    raise AssertionError(f"{label!r} not listed; have {[i.getLabel() for _u, i, _f in kodi.directory_items]}")


class RootAndSettingsTest(KodiTestCase):
    def test_root_menu(self):
        self.run_plugin()
        self.assertEqual(self.listed_labels(), ["Generate mix from playing audio", "Discovery mode", "Recent mixes", "Settings"])
        self.assertEqual(plugin_query(item_by_label("Recent mixes")[0])["action"], "saved_mixes")
        self.assertEqual(kodi.ended, [{"succeeded": True, "updateListing": False, "cacheToDisc": False}])

    def test_every_run_installs_the_keymap(self):
        self.run_plugin()
        self.assertTrue(os.path.exists(main.get_musicip_user_keymap_path()))

    def test_open_settings(self):
        self.run_plugin(action="open_settings")
        self.assertEqual(kodi.settings_opened, 1)
        self.assertBuiltin(f"Container.Update({PLUGIN_URL}?nonce=")

    def test_unknown_action(self):
        self.run_plugin(action="frobnicate")
        self.assertNotified("Unknown action: frobnicate")
        self.assertFalse(kodi.ended[-1]["succeeded"])

    def test_script_entry_point_reports_unhandled_errors(self):
        # Generating a mix with nothing playing raises; the __main__ guard turns it into a notification.
        with mock.patch.object(sys, "argv", [PLUGIN_URL, str(HANDLE), "?action=generate_current_mix"]):
            runpy.run_path(os.path.join(ADDON_DIR, "main.py"), run_name="__main__")
        self.assertNotified("No audio is currently playing.")
        self.assertFalse(kodi.ended[-1]["succeeded"])


class SavedMixListingTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        kodi.add_media(SEED)
        kodi.add_media(T1)
        ts = int(time.mktime(time.strptime("2026-10-05 18:30", "%Y-%m-%d %H:%M")))
        self.ok_mix = self.save_mix([SEED, T1], updated_ts=ts)
        self.broken_mix = self.save_mix([T1, T2], updated_ts=ts - 60)
        main.analyze_mix_consistency(self.broken_mix)

    def test_no_saved_mixes(self):
        main.delete_saved_mix_files(self.ok_mix)
        main.delete_saved_mix_files(self.broken_mix)
        self.run_plugin(action="saved_mixes")
        self.assertEqual(self.listed_labels(), ["No recent mixes found yet."])

    def test_date_groups_show_warning_count(self):
        self.run_plugin(action="saved_mixes")
        url, item, is_folder = kodi.directory_items[0]
        self.assertEqual(item.getLabel(), "[B][COLOR red]![/COLOR][/B] 2026-10-05 (2 mixes) · 1 warning")
        self.assertTrue(is_folder)
        self.assertEqual(plugin_query(url), {"action": "saved_mixes_by_date", "date": "2026-10-05", "nonce": plugin_query(url)["nonce"]})
        older = plugin_query(item.context_action("Cleanup mixes from this date and older"))
        self.assertEqual((older["action"], older["older"]), ("cleanup_saved_mixes", "1"))

    def test_mixes_of_a_date(self):
        kodi.library_properties = {"songsmodified": "2000-01-01 00:00:00"}
        self.run_plugin(action="saved_mixes_by_date", date="2026-10-05")
        ok_url, ok_item, _ = item_by_label("01 Ace of Spades (2 tracks)")
        self.assertEqual(plugin_query(ok_url)["cache_path"], self.ok_mix)
        self.assertEqual(ok_item.getLabel2(), "2026-10-05 18:30")
        self.assertEqual(ok_item.getProperty("MusicIP.CachePath"), self.ok_mix)
        self.assertIn("Seed: " + SEED, ok_item.getProperty("Plot"))

        _url, broken, _ = item_by_label("[B][COLOR red]![/COLOR][/B] 01 Overkill (2 tracks)")
        self.assertEqual(broken.getProperty("MusicIP.Inconsistent"), "true")
        self.assertEqual(broken.getLabel2(), "2026-10-05 18:29 · Inconsistent: 1 missing · Update library before repair")
        labels = [label for label, _action in broken.context_menu]
        self.assertEqual(labels, ["Information", "Show mix information", "Check consistency", "Update library before repair", "Cleanup this mix"])

    def test_repair_offered_once_library_is_newer(self):
        kodi.library_properties = {"songsmodified": "2099-01-01 00:00:00"}
        self.run_plugin(action="saved_mixes_by_date", date="2026-10-05")
        _url, broken, _ = item_by_label("[B][COLOR red]![/COLOR][/B] 01 Overkill (2 tracks)")
        repair = plugin_query(broken.context_action("Auto-repair this mix"))
        self.assertEqual((repair["action"], repair["cache_path"]), ("repair_mix", self.broken_mix))

    def test_missing_or_unknown_date(self):
        self.run_plugin(action="saved_mixes_by_date")
        self.assertNotified("No date was supplied.")
        self.run_plugin(action="saved_mixes_by_date", date="1999-01-01")
        self.assertEqual(self.listed_labels(), ["No recent mixes found for this date."])

    def test_cleanup_actions(self):
        self.run_plugin(action="cleanup_saved_mix", cache_path=self.ok_mix)
        self.assertFalse(os.path.exists(self.ok_mix))
        self.assertNotified("Removed mix.")
        self.assertBuiltin(f"Container.Update({PLUGIN_URL}?action=saved_mixes")

        self.run_plugin(action="cleanup_saved_mixes", date="2026-10-05", older="0")
        self.assertFalse(os.path.exists(self.broken_mix))
        self.assertNotified("Removed 1 stored mix(es) from 2026-10-05.")

        self.run_plugin(action="cleanup_saved_mixes")
        self.assertNotified("No date was supplied.")

    def test_check_consistency_action(self):
        self.run_plugin(action="check_mix_consistency", cache_path=self.broken_mix)
        self.assertNotified("Mix inconsistent: 1 missing.")
        self.run_plugin(action="check_mix_consistency", cache_path=self.ok_mix)
        self.assertNotified("Mix consistency OK.")
        self.assertEqual(kodi.builtins.count("Container.Refresh"), 2)

    def test_repair_action_requires_fresh_library(self):
        self.run_plugin(action="repair_mix", cache_path=self.broken_mix)
        self.assertNotified("Update library before repair.")

    def test_repair_action(self):
        kodi.library_properties = {"songsmodified": "2099-01-01 00:00:00"}
        kodi.library.add_song("E:\\moved\\01 Motorcycle Man.mp3", title="Motorcycle Man", artist="Saxon")
        self.run_plugin(action="repair_mix", cache_path=self.broken_mix)
        self.assertNotified("Repaired 1 track(s).")
        self.assertEqual(self.read_mix(self.broken_mix), [T1, "E:\\moved\\01 Motorcycle Man.mp3"])

    def test_update_library_action(self):
        kodi.respond("select", 1)
        self.run_plugin(action="update_library_before_repair", cache_path=self.broken_mix)
        self.assertIn("AudioLibrary.Scan", kodi.jsonrpc_methods())
        self.assertEqual(kodi.builtins[-1], "Container.Refresh")

    def test_actions_without_cache_path(self):
        for action in ("cleanup_saved_mix", "check_mix_consistency", "update_library_before_repair", "repair_mix"):
            with self.subTest(action=action):
                kodi.notifications.clear()
                self.run_plugin(action=action)
                self.assertEqual(len(kodi.notifications), 1)
                self.assertEqual(kodi.notifications[0][2], "error")


class MixInfoTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        main.remember_mix_generation_parameters(SEED, 2, {"size": 2, "style_ui": 5, "rejectsize": 2})
        self.cache_path = self.save_mix([SEED, T1], size=2)

    def test_info_dialog(self):
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        heading, text = kodi.dialogs("textviewer")[0][1]
        self.assertEqual(heading, "MusicIP mix information")
        self.assertIn("Style: 5/10 - medium preference (API 100)", text)
        self.assertIn("Artist repeat: do not repeat artist within 2 tracks", text)
        self.assertIn("Status: unknown", text)

    def test_info_for_selected_item(self):
        kodi.info_labels["ListItem.Property(MusicIP.CachePath)"] = self.cache_path
        self.run_plugin(action="mix_info_selected")
        self.assertEqual(len(kodi.dialogs("textviewer")), 1)

    def test_nothing_selected(self):
        self.run_plugin(action="mix_info")
        self.assertNotified("No saved mix is selected.")

    def test_unreadable_mix(self):
        self.run_plugin(action="mix_info", cache_path=self.cache_path + ".gone")
        self.assertIn("Could not read mix information.", kodi.dialogs("ok")[0][1][1])


class BrowseMixTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.kodi_settings["musicfiles.trackformat"] = TRACK_FORMAT
        kodi.add_media(SEED)
        kodi.add_media(T1)
        self.musicip.set_mix(SEED, [T1, T2])

    def test_stored_mix_is_listed_without_contacting_musicip(self):
        cache_path = self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(self.musicip.requests, [])
        self.assertEqual(self.listed_labels(), [
            "1. 01 Ace of Spades", "2. 01 Overkill", "[B][COLOR red]![/COLOR][/B] 3. 01 Motorcycle Man",
        ])
        url, item, is_folder = kodi.directory_items[0]
        self.assertEqual(plugin_query(url), {"action": "play_track", "path": SEED})
        self.assertFalse(is_folder)
        self.assertEqual(item.getProperty("IsPlayable"), "true")
        self.assertEqual([label for label, _a in item.context_menu], ["Refresh mix", "More like this", "Remove from mix"])
        second = kodi.directory_items[1][1]
        self.assertIn("Less like this", [label for label, _a in second.context_menu])
        missing = kodi.directory_items[2][1]
        self.assertEqual(missing.getProperty("MusicIP.Missing"), "true")
        self.assertEqual(missing.getLabel2(), "[B][COLOR red]![/COLOR][/B] Missing file")
        self.assertEqual(plugin_query(item.getProperty("MusicIP.MixAction.Remove"))["cache_path"], cache_path)
        self.assertIn(("setContent", "songs"), kodi.directory_calls)

    def test_missing_mix_is_generated_after_confirmation(self):
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(len(self.listed_labels()), 3)
        self.assertEqual(main.load_mix(SEED, 20), [SEED, T1, T2])

    def test_refresh_regenerates_and_replaces_listing(self):
        self.save_mix([SEED, T1], size=20)
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", refresh="1")
        self.assertEqual(main.load_mix(SEED, 20), [SEED, T1, T2])
        self.assertTrue(kodi.ended[-1]["updateListing"])

    def test_cancelled_generation_shows_error_item(self):
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(self.listed_labels(), ["MusicIP mix failed: Mix generation cancelled."])
        self.assertEqual(kodi.notifications[-1][2], "warning")

    def test_no_seed(self):
        self.run_plugin(action="browse_mix")
        self.assertNotified("No seed song was supplied.")

    def test_listing_queues_metadata_refresh_and_stores_snapshots(self):
        cache_path = self.save_mix([SEED, T1], size=20)
        main.write_track_metadata_cache(T1, {"title": "Overkill", "artist": "Motörhead"})
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertIn("2. Motörhead - Overkill", self.listed_labels())
        queued = [entry["path"] for entry in main.load_metadata_refresh_queue()["entries"]]
        # T1 has cached metadata; with no known library update time it is not refreshed again.
        self.assertEqual(queued, [SEED])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        self.assertIn(main.canonical_audio_path(T1), sidecar["track_metadata_by_path"])

    def test_focus_is_applied_once(self):
        self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", focus_index="2", focus_token="tok")
        self.assertEqual(kodi.builtins.count("Action(Down)"), 2)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", focus_index="2", focus_token="tok")
        self.assertEqual(kodi.builtins.count("Action(Down)"), 2)


class BrowseSavedMixTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix([SEED, T1], size=20)

    def test_listing(self):
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        self.assertEqual(len(self.listed_labels()), 2)
        self.assertIn(("setPluginCategory", "Saved MusicIP mix: 01 Ace of Spades"), kodi.directory_calls)

    def test_refresh(self):
        self.musicip.set_mix(SEED, [T2])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path, refresh="1")
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T2])

    def test_empty_mix(self):
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            handle.write("")
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        self.assertEqual(self.listed_labels(), ["Mix is empty. Use Refresh mix to generate a new one."])

    def test_refresh_failure_keeps_stored_mix(self):
        self.musicip.mix_status = 500
        kodi.respond("select", 0)
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path, refresh="1")
        self.assertNotified("HTTP 500")
        self.assertFalse(kodi.ended[-1]["succeeded"])
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1])

    def test_unknown_or_missing_path(self):
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path + ".gone")
        self.assertNotified("No stored mix found")
        self.assertFalse(kodi.ended[-1]["succeeded"])
        self.run_plugin(action="browse_saved_mix")
        self.assertNotified("No stored mix path was supplied.")


class GenerateFromPlayingAudioTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.kodi_settings["musicfiles.trackformat"] = TRACK_FORMAT

    def test_generates_saves_and_plays_mix(self):
        kodi.play_file(SEED, title="Ace of Spades")
        self.musicip.set_mix(SEED, [T1, T2])
        kodi.respond("select", 0)

        self.run_plugin(action="generate_current_mix")

        self.assertEqual(main.load_mix(SEED, 20), [SEED, T1, T2])
        self.assertEqual(kodi.playlist_files(), [SEED, T1, T2])
        self.assertEqual(kodi.playlist[1][1].getLabel(), "2. 01 Overkill")
        self.assertEqual((kodi.player.position, kodi.player.file), (0, SEED))
        self.assertNotified("Playing generated mix.")
        update = kodi.builtins[-1]
        self.assertTrue(update.startswith("Container.Update(") and update.endswith(",replace)"))
        self.assertEqual(plugin_query(update)["seed"], SEED)
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(main.mix_cache_path(SEED, 20)))
        self.assertEqual(sidecar["mix_generation_parameters"]["size"], 20)

    def test_server_error_is_listed(self):
        kodi.play_file(SEED)
        self.musicip.mix_status = 500
        kodi.respond("select", 0)
        self.run_plugin(action="generate_current_mix")
        self.assertEqual(self.listed_labels(), ["MusicIP mix failed: MusicIP server returned HTTP 500."])
        self.assertEqual(kodi.playlist, [])

    def test_playback_failure_is_listed(self):
        kodi.play_file(SEED)
        self.musicip.set_mix(SEED, [T1])
        kodi.respond("select", 0)
        with mock.patch("fake_kodi.Player.play", side_effect=RuntimeError("player busy")):
            self.run_plugin(action="generate_current_mix")
        self.assertEqual(self.listed_labels(), ["MusicIP mix playback failed: player busy"])
        self.assertEqual(main.load_mix(SEED, 20), [SEED, T1])

    def test_nothing_playing(self):
        with self.assertRaisesRegex(main.MusicIPError, "No audio is currently playing."):
            self.run_plugin(action="generate_current_mix")


class PlayTrackTest(KodiTestCase):
    def test_resolves_track_with_metadata(self):
        kodi.library.add_song(SEED, title="Ace of Spades", artist="Motörhead", album="Ace of Spades", year=1980, duration=169, genre=["Metal"])
        self.run_plugin(action="play_track", path=SEED)
        succeeded, item = kodi.resolved[0]
        self.assertTrue(succeeded)
        self.assertEqual((item.getLabel(), item.getPath()), ("Ace of Spades", SEED))
        self.assertEqual(item.getLabel2(), "1980s · Metal · 2:49")

    def test_no_path(self):
        self.run_plugin(action="play_track")
        self.assertFalse(kodi.resolved[0][0])


class MixEditingRoutesTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.settings["playlist_size"] = "10"
        self.cache_path = self.save_mix([SEED, T1, T2], size=10)
        kodi.info_labels["Container.PluginName"] = "plugin.audio.musicip"

    def test_remove_track(self):
        self.run_plugin(action="remove_track", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T2])
        self.assertNotified("Removed: 01 Overkill")
        self.assertEqual(plugin_query(kodi.builtins[-1])["action"], "browse_saved_mix")

    def test_remove_is_only_allowed_inside_the_addon(self):
        kodi.info_labels.clear()
        self.run_plugin(action="remove_track", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertNotified("only available inside the MusicIP add-on")
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1, T2])

        kodi.info_labels["Container.FolderPath"] = "plugin://plugin.audio.musicip/?action=browse_mix"
        self.assertTrue(main.is_addon_mix_container_active())

    def test_more_like_this(self):
        self.musicip.set_mix(T1, ["E:\\new\\1.mp3"])
        self.run_plugin(action="more_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1, "E:\\new\\1.mp3", T2])
        self.assertNotified("Inserted 1 track(s).")
        self.assertEqual(plugin_query(kodi.builtins[-1])["focus_index"], "1")

    def test_less_like_this(self):
        self.musicip.set_mix(T1, [T2])
        self.run_plugin(action="less_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED])
        self.assertNotified("Removed 2 track(s).")
        self.assertEqual(plugin_query(kodi.builtins[-1])["focus_index"], "0")

    def test_edit_errors_are_notified(self):
        self.run_plugin(action="more_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertNotified("MusicIP returned an empty mix.")
        self.assertEqual(kodi.notifications[-1][2], "error")


class KeyboardShortcutTest(KodiTestCase):
    def test_runs_the_selected_items_action(self):
        kodi.info_labels["ListItem.Property(MusicIP.MixAction.Remove)"] = "RunPlugin(plugin://plugin.audio.musicip/?action=remove_track)"
        self.run_plugin(action="keyboard_remove_from_mix")
        self.assertEqual(kodi.builtins[-1], "RunPlugin(plugin://plugin.audio.musicip/?action=remove_track)")

    def test_no_action_for_selection(self):
        for action, label in (("keyboard_more_like_this", "More like this"), ("keyboard_less_like_this", "Less like this")):
            with self.subTest(action=action):
                self.run_plugin(action=action)
                self.assertNotified(f"No '{label}' action is available for the selected item.")


if __name__ == "__main__":
    unittest.main()
