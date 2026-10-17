"""Music sources and repair: unavailable sources, virtual library roots and the disk search for moved files."""

import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, main, service

METAL = "D:\\music\\#metal\\"
ROCK = "D:\\music\\#rock\\"
PRESENT = "D:\\music\\#metal\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
MISSING = "D:\\music\\#metal\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"
# After a reorganization the album lives in a folder that is not a music source.
MOVED = "D:\\music\\#soul_disco\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"


class SourcesTestCase(KodiTestCase):
    def setUp(self):
        super().setUp()
        kodi.music_sources = []
        kodi.library.add_song(PRESENT, title="Overkill")  # #metal is scanned into the library
        self.cache_path = self.save_mix([PRESENT, MISSING])
        main.analyze_mix_consistency(self.cache_path)

    def meta(self):
        return main.get_saved_mix_metadata(self.cache_path)

    def readiness(self):
        return main.get_mix_repair_readiness(self.meta())


class UnavailableSourceTest(SourcesTestCase):
    def test_ready_when_the_covering_source_exists(self):
        kodi.add_music_source(METAL)
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual((readiness["unavailable_sources"], readiness["outside_sources"]), ([], []))

    def test_source_folder_gone_after_reorganization_blocks_repair(self):
        kodi.add_music_source(METAL, present=False)
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "update_sources_before_repair")
        self.assertEqual(readiness["unavailable_sources"], [METAL])
        self.assertEqual(
            readiness["reason"],
            f"Kodi music source(s) no longer available: {METAL}. Update the music sources to the new "
            "folder structure (or reconnect the drive), then update the library.",
        )
        self.assertEqual(main.repair_readiness_action_label(readiness), "Check music sources before repair")
        with self.assertRaisesRegex(main.MusicIPError, "Check music sources before repair"):
            main.ensure_repair_ready(self.cache_path)

    def test_most_specific_source_decides(self):
        kodi.add_music_source("D:\\")
        kodi.add_music_source(METAL, present=False)
        self.assertEqual(self.readiness()["unavailable_sources"], [METAL])

    def test_missing_files_outside_all_sources_are_only_reported(self):
        # Normal after an obsolete source was removed during a reorganization.
        kodi.add_music_source("E:\\new_structure\\")
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["outside_sources"], [MISSING])
        self.assertEqual(
            readiness["reason"],
            "Kodi music library no longer lists the missing files. 1 of them were outside all Kodi music sources.",
        )

    def test_no_music_sources(self):
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "update_sources_before_repair")
        self.assertEqual(readiness["reason"], "Kodi has no music sources, so the library cannot add the missing files. Add a music source.")

    def test_multipath_source(self):
        kodi.music_sources = [{"file": "multipath://D%3a%5cmusic%5c%23metal%5c/E%3a%5cother%5c/", "label": "Metal"}]
        self.assertEqual(main.get_music_source_paths(), [METAL, "E:\\other\\"])
        self.assertEqual(self.readiness()["unavailable_sources"], [METAL])

    def test_covering_source(self):
        self.assertEqual(main.find_covering_music_source("smb://nas/music/a/b.mp3", ["smb://NAS/music/", "D:\\"]), "smb://NAS/music/")
        self.assertEqual(main.find_covering_music_source("D:\\musicbox\\a.mp3", ["D:\\music\\"]), "")

    def test_unreadable_sources_fall_back_to_the_library_check(self):
        kodi.settings["plugin_extended_logging"] = "true"
        kodi.fail_jsonrpc("Files.GetSources")
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertFalse(readiness["sources_checked"])
        self.assertIn("music_sources=unreadable", kodi.log_text())

    def test_sources_dialog_and_message(self):
        kodi.add_music_source(METAL, present=False)
        main.show_update_library_before_repair(self.cache_path)
        self.assertEqual(kodi.dialogs("select"), [])  # scanning cannot help yet
        heading, text = kodi.dialogs("ok")[0][1]
        self.assertEqual(heading, "Check music sources before repair")
        self.assertIn("Kodi music sources that no longer exist:\n- " + METAL, text)
        self.assertIn("Update the Kodi music sources to match the folder structure on disk", text)

    def test_saved_mix_entry_names_the_sources(self):
        kodi.add_music_source(METAL, present=False)
        main.add_saved_mix_item(self.cache_path)
        self.finish_listing()
        _url, item, _folder = kodi.directory_items[-1]
        self.assertIn("Check music sources before repair", [label for label, _action in item.context_menu])
        self.assertTrue(item.getLabel2().endswith("| Check music sources before repair"))


class VirtualLibraryRootTest(unittest.TestCase):
    def roots(self, *sources):
        return main.get_virtual_library_roots(list(sources))

    def test_common_folder_of_a_disk(self):
        self.assertEqual(self.roots(METAL, ROCK), ["D:\\music\\"])

    def test_sources_spread_over_a_disk(self):
        self.assertEqual(self.roots(METAL, "D:\\Slsk\\", "d:\\bin\\ytdlp\\"), ["D:\\"])

    def test_single_source_looks_one_level_up(self):
        self.assertEqual(self.roots("E:\\music\\"), ["E:\\"])
        self.assertEqual(self.roots("E:\\"), ["E:\\"])

    def test_one_root_per_disk_and_share(self):
        self.assertEqual(
            self.roots(METAL, ROCK, "smb://nas/music/a/", "smb://nas/music/b/", "smb://nas/video/x/"),
            ["D:\\music\\", "smb://nas/music/", "smb://nas/video/"],
        )

    def test_root_folders_on_unix(self):
        self.assertEqual(self.roots("/mnt/music/rock/", "/mnt/music/jazz/"), ["/mnt/music/"])
        self.assertEqual(self.roots("/srv/music/"), ["/srv/"])

    def test_unsearchable_sources_are_ignored(self):
        self.assertEqual(self.roots("upnp://server/1/", "special://home/music/", "smb://nas/"), [])


class MissingFileSearchTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        kodi.music_sources = []
        kodi.add_music_source(METAL)
        kodi.add_music_source(ROCK)
        # Both sources are scanned into the library.
        kodi.library.add_song(PRESENT, title="Overkill")
        kodi.library.add_song("D:\\music\\#rock\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3", title="Motorcycle Man")

    def search(self, *missing):
        return main.search_missing_files_outside_sources(list(missing), main.get_music_source_paths())

    def test_finds_moved_album_outside_the_sources(self):
        kodi.add_media(MOVED)
        result = self.search(MISSING)
        self.assertEqual(result["roots"], ["D:\\music\\"])
        self.assertEqual(result["found_outside_sources"], {MISSING: MOVED})
        self.assertTrue(result["complete"])
        self.assertNotIn("suggested_sources", result)

    def test_music_sources_are_not_searched(self):
        result = self.search(MISSING)
        self.assertEqual(result["found_outside_sources"], {})
        self.assertNotIn(ROCK, kodi.listed)

    def test_same_file_name_in_another_album_does_not_match(self):
        kodi.add_media("D:\\music\\#soul_disco\\Other Band\\Other Album\\01 Motorcycle Man.mp3")
        self.assertEqual(self.search(MISSING)["found_outside_sources"], {})

    def test_system_folders_are_skipped(self):
        kodi.add_media("D:\\music\\$RECYCLE.BIN\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3")
        self.assertEqual(self.search(MISSING)["found_outside_sources"], {})

    def test_search_stops_at_its_limit(self):
        kodi.add_media(MOVED)
        with mock.patch.object(main, "MISSING_FILE_SEARCH_MAX_FOLDERS", 1):
            result = self.search(MISSING)
        self.assertFalse(result["complete"])
        self.assertEqual(result["folders_searched"], 1)

    def test_network_share(self):
        kodi.music_sources = []
        kodi.add_music_source("smb://nas/music/metal/")
        moved = "smb://nas/music/soul/Saxon/Wheels of Steel (1980)/01 Motorcycle Man.mp3"
        kodi.add_media(moved)
        missing = "smb://nas/music/metal/Saxon/Wheels of Steel (1980)/01 Motorcycle Man.mp3"
        self.assertEqual(self.search(missing)["found_outside_sources"], {missing: moved})


class ReadinessIgnoresSearchTest(SourcesTestCase):
    def test_readiness_dialog_and_mix_info_do_not_use_the_search(self):
        kodi.add_music_source(METAL)
        meta = self.meta()
        meta["missing_file_search"] = {
            "checked_ts": 1,
            "signature": meta["consistency"]["missing_signature"],
            "found_outside_sources": {MISSING: MOVED},
            "complete": True,
        }
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), meta)

        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["reason"], "Kodi music library no longer lists the missing files.")
        self.assertNotIn(MOVED, main.build_repair_readiness_message(readiness))
        self.assertNotIn(MOVED, main.build_mix_info_message(self.cache_path))


class ServiceSearchTest(SourcesTestCase):
    NOTIFICATION = f"Missing file found outside of the music sources: {MOVED}"

    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        kodi.add_music_source(METAL)
        kodi.add_media(MOVED)

    def test_background_check_searches_stores_and_notifies(self):
        service.run_consistency_check()
        search = self.meta()["missing_file_search"]
        self.assertEqual(search["found_outside_sources"], {MISSING: MOVED})
        self.assertEqual(search["signature"], self.meta()["consistency"]["missing_signature"])
        self.assertNotIn("suggested_sources", self.meta()["repair_readiness"])
        self.assertEqual(kodi.notifications, [("MusicIP", self.NOTIFICATION, "info")])

    def test_several_files_in_one_notification(self):
        other_missing = "D:\\music\\#metal\\Saxon\\Wheels of Steel (1980)\\02 Wheels of Steel.mp3"
        other_moved = "D:\\music\\#soul_disco\\Saxon\\Wheels of Steel (1980)\\02 Wheels of Steel.mp3"
        kodi.add_media(other_moved)
        self.save_mix([PRESENT, other_missing], size=3)  # another mix (seed and size name the mix file)
        service.run_consistency_check()
        self.assertEqual(len(kodi.notifications), 1)
        self.assertTrue(kodi.notification_messages()[0].startswith("2 missing files found outside of the music sources, e.g. D:\\music\\#soul_disco\\"))

    def test_search_is_not_repeated_while_current(self):
        service.run_consistency_check()
        kodi.notifications.clear()
        kodi.listed.clear()
        self.clock.advance(3600)
        service.run_consistency_check()
        self.assertEqual(kodi.listed, [])
        self.assertEqual(kodi.notifications, [])

    def test_search_is_repeated_after_a_day_without_repeating_the_notification(self):
        service.run_consistency_check()
        kodi.listed.clear()
        self.clock.advance(main.MISSING_FILE_SEARCH_MAX_AGE_SECONDS + 1)
        service.run_consistency_check()
        self.assertNotEqual(kodi.listed, [])
        self.assertEqual(kodi.notification_messages(), [self.NOTIFICATION])

    def test_nothing_found_means_no_notification(self):
        kodi.remove_media(MOVED)
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [])
        self.assertEqual(self.meta()["missing_file_search"]["found_outside_sources"], {})

    def test_search_waits_while_discovery_mode_is_active(self):
        service.save_discovery_state({"enabled": True})
        service.run_consistency_check()
        self.assertNotIn("missing_file_search", self.meta())
        self.assertEqual(kodi.listed, [])

    def test_search_is_logged_with_extended_service_logging(self):
        kodi.settings["service_extended_logging"] = "true"
        service.run_consistency_check()
        self.assertIn(
            f"for 1 missing file(s); found 1 outside the music sources: [{MOVED!r}]; "
            "found 0 in music sources not scanned into the library [].",
            kodi.log_text(),
        )


class UnscannedSourceTest(SourcesTestCase):
    """A music source configured in Kodi but never scanned into the library (finding F10)."""

    JAZZ = "D:\\music\\#jazz_fusion_progressive\\"
    JAZZ_MOVED = "D:\\music\\#jazz_fusion_progressive\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"

    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        kodi.add_music_source(METAL)
        kodi.add_music_source(self.JAZZ)  # configured, no songs in the library
        kodi.add_media(self.JAZZ_MOVED)

    def scan_source_into_library(self):
        kodi.library.add_song(self.JAZZ_MOVED, title="Motorcycle Man", artist="Saxon")

    def test_file_moved_into_a_source_that_was_never_scanned_is_reported(self):
        # Seen on 2026-10-10: an album moved into D:\music\#jazz_fusion_progressive, a source with 0 library songs.
        service.run_consistency_check()
        search = self.meta()["missing_file_search"]
        self.assertEqual(search["found_in_unscanned_sources"], {MISSING: self.JAZZ_MOVED})
        self.assertEqual(search["unscanned_sources"], [self.JAZZ])
        self.assertEqual(search["found_outside_sources"], {})

    def test_notification_names_the_source_once(self):
        service.run_consistency_check()
        self.clock.advance(main.MISSING_FILE_SEARCH_MAX_AGE_SECONDS + 1)
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [(
            "MusicIP",
            f"Missing file found in a music source that is not scanned into the library: {self.JAZZ}",
            "info",
        )])

    def test_readiness_asks_for_a_scan(self):
        service.run_consistency_check()
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "scan_source_before_repair")
        self.assertEqual(readiness["unscanned_sources"], [self.JAZZ])
        self.assertEqual(
            readiness["reason"],
            f"1 missing file(s) were found in music source(s) that are not scanned into the library: {self.JAZZ}. "
            "Scan the source into the library.",
        )
        self.assertEqual(self.meta()["repair_readiness"]["status"], "scan_source_before_repair")
        with self.assertRaisesRegex(main.MusicIPError, "Scan music source before repair"):
            main.ensure_repair_ready(self.cache_path)

    def test_mix_entry_offers_the_scan(self):
        service.run_consistency_check()
        main.add_saved_mix_item(self.cache_path)
        self.finish_listing()
        _url, item, _folder = kodi.directory_items[-1]
        self.assertIn("Scan music source before repair", [label for label, _action in item.context_menu])

    def test_accepting_the_question_scans_the_source(self):
        service.run_consistency_check()
        kodi.respond("yesno", True)
        main.show_update_library_before_repair(self.cache_path)
        heading, text = kodi.dialogs("yesno")[0][1]
        self.assertEqual(heading, "Scan music source before repair")
        self.assertIn("- " + self.JAZZ, text)
        self.assertIn("Scan them into the library now?", text)
        scans = [call["params"] for call in kodi.jsonrpc_calls if call["method"] == "AudioLibrary.Scan"]
        self.assertEqual(scans, [{"directory": self.JAZZ}])
        self.assertNotified(f"Kodi music library scan started for {self.JAZZ}.")

    def test_declining_the_question_starts_no_scan(self):
        service.run_consistency_check()
        main.show_update_library_before_repair(self.cache_path)
        self.assertNotIn("AudioLibrary.Scan", kodi.jsonrpc_methods())

    def test_message_lists_the_source_and_the_found_file(self):
        service.run_consistency_check()
        message = main.build_repair_readiness_message(self.readiness())
        self.assertIn("Found in music sources that are not scanned into the library:\n- " + self.JAZZ_MOVED, message)
        self.assertIn("Scan these music sources into the library, then try repair again:\n- " + self.JAZZ, message)

    def test_readiness_clears_once_the_source_has_library_songs(self):
        service.run_consistency_check()
        self.scan_source_into_library()
        self.assertEqual(self.readiness()["status"], "ready")

    def test_automatic_repair_after_the_scan(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        service.run_consistency_check()
        self.assertEqual(self.read_mix(self.cache_path), [PRESENT, MISSING])
        # Only the scan notification: no "update the library" notification for this mix.
        self.assertEqual(len(kodi.notifications), 1)

        self.scan_source_into_library()
        self.clock.advance(3600)
        service.run_consistency_check()
        self.assertEqual(self.read_mix(self.cache_path), [PRESENT, self.JAZZ_MOVED])


if __name__ == "__main__":
    unittest.main()
