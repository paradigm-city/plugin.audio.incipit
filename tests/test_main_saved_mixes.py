"""Saved mixes on disk: storage and sidecar metadata, ordering, date groups, cleanup, editing and consistency."""

import os
import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, MusicIPServerTestCase, main

A, B, C, D = (f"D:\\music\\Artist\\Album\\0{n} Song {n}.mp3" for n in range(1, 5))
DAY = 24 * 3600


def local_ts(text):
    return int(time.mktime(time.strptime(text, "%Y-%m-%d %H:%M")))


class StorageTest(KodiTestCase):
    def test_save_and_load_round_trip(self):
        main.save_mix(A, 20, [A, B, C])
        self.assertEqual(main.load_mix(A, 20), [A, B, C])
        cache_path = main.mix_cache_path(A, 20)
        self.assertTrue(os.path.basename(cache_path).startswith("mix_"))
        self.assertEqual(os.path.dirname(cache_path), kodi.profile_dir().rstrip(os.sep))

    def test_cache_key_depends_on_seed_and_size(self):
        self.assertEqual(main.mix_cache_key(A, 20), main.mix_cache_key(A, 20))
        self.assertNotEqual(main.mix_cache_key(A, 20), main.mix_cache_key(A, 21))
        self.assertNotEqual(main.mix_cache_key(A, 20), main.mix_cache_key(B, 20))

    def test_sidecar_metadata(self):
        main.remember_mix_generation_parameters(A, 20, {"size": 20, "style_ui": 3})
        main.save_mix(A, 20, [A, B], track_metadata_list=[
            {"title": "Song 1", "artist": "Artist", "library_freshest_ts": 100},
            {"title": "Song 2", "library_freshest_ts": 200},
        ])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(main.mix_cache_path(A, 20)))
        self.assertEqual((sidecar["seed"], sidecar["size"], sidecar["track_count"]), (A, 20, 2))
        self.assertEqual(sidecar["label"], "01 Song 1")
        self.assertEqual(sidecar["mix_generation_parameters"]["style_ui"], 3)
        self.assertEqual(sidecar["track_metadata_library_freshest_ts"], 200)
        self.assertEqual(sorted(sidecar["track_metadata_by_path"]), sorted(main.canonical_audio_path(p) for p in (A, B)))

    def test_missing_mix(self):
        with self.assertRaisesRegex(main.MusicIPError, "No stored mix"):
            main.load_mix(A, 20)

    def test_metadata_is_inferred_without_sidecar(self):
        cache_path = os.path.join(main.get_profile_dir(), "mix_manual.m3u")
        with open(cache_path, "w", encoding="utf-8") as handle:
            handle.write(f"{A}\n\n{B}\n")
        meta = main.get_saved_mix_metadata(cache_path)
        self.assertEqual((meta["seed"], meta["track_count"], meta["label"]), (A, 2, "01 Song 1"))
        self.assertEqual(meta["cache_path"], cache_path)

    def test_corrupt_sidecar_is_ignored(self):
        cache_path = self.save_mix([A, B])
        with open(main.mix_meta_path_from_cache_path(cache_path), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(main.get_saved_mix_metadata(cache_path)["seed"], A)

    def test_saved_mix_label(self):
        self.assertEqual(main.format_saved_mix_label({"label": "Song", "track_count": 3}), "Song (3 tracks)")
        self.assertEqual(main.format_saved_mix_label({"seed": A}), "01 Song 1")
        self.assertEqual(main.format_saved_mix_label({}), "Stored mix")


class OrderingAndCleanupTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.old = self.save_mix([A, B], updated_ts=local_ts("2026-10-01 10:00"))
        self.middle = self.save_mix([B, C], updated_ts=local_ts("2026-10-05 09:00"))
        self.newest = self.save_mix([C, D], updated_ts=local_ts("2026-10-05 18:00"))

    def test_recent_mixes_are_ordered_by_saved_timestamp_not_file_time(self):
        os.utime(self.old, (time.time() + 1000, time.time() + 1000))  # e.g. after a repair
        self.assertEqual(main.list_saved_mix_cache_paths(), [self.newest, self.middle, self.old])

    def test_group_by_date(self):
        groups = main.group_saved_mixes_by_date(main.list_saved_mix_cache_paths())
        self.assertEqual(groups, [("2026-10-05", [self.newest, self.middle]), ("2026-10-01", [self.old])])

    @unittest.expectedFailure
    def test_unknown_date_group_sorts_last(self):
        # Known issue: sort_key gives "Unknown date" (1, ...) to sort it last, but the list is
        # sorted with reverse=True, so it comes first. Remove expectedFailure once fixed.
        broken = os.path.join(kodi.profile_dir(), "mix_broken.m3u")
        groups = main.group_saved_mixes_by_date([broken, self.old])
        self.assertEqual([key for key, _paths in groups], ["2026-10-01", "Unknown date"])

    def test_cleanup_single_date(self):
        self.assertEqual(main.cleanup_saved_mixes_for_date("2026-10-05"), 2)
        self.assertEqual(main.list_saved_mix_cache_paths(), [self.old])
        self.assertFalse(os.path.exists(main.mix_meta_path_from_cache_path(self.newest)))

    def test_cleanup_date_and_older(self):
        self.assertEqual(main.cleanup_saved_mixes_for_date("2026-10-04", include_older=True), 1)
        self.assertEqual(main.list_saved_mix_cache_paths(), [self.newest, self.middle])


class RemoveTrackTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix([A, B, C, B])

    def test_remove_by_index(self):
        self.assertEqual(main.remove_track_from_mix(A, 4, 1, B, cache_path=self.cache_path), B)
        self.assertEqual(self.read_mix(self.cache_path), [A, C, B])
        self.assertEqual(self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))["track_count"], 3)

    def test_index_out_of_date_falls_back_to_path(self):
        self.assertEqual(main.remove_track_from_mix(A, 4, 0, C, cache_path=self.cache_path), C)
        self.assertEqual(self.read_mix(self.cache_path), [A, B, B])

    def test_unknown_track(self):
        with self.assertRaisesRegex(main.MusicIPError, "Could not remove"):
            main.remove_track_from_mix(A, 4, 9, D, cache_path=self.cache_path)

    def test_find_track_position(self):
        tracks = [A, B, C]
        self.assertEqual(main.find_track_position(tracks, 1, B), 1)
        self.assertEqual(main.find_track_position(tracks, 0, C.replace("\\", "/")), 2)
        self.assertEqual(main.find_track_position(tracks, 1, D), 1)
        self.assertEqual(main.find_track_position(tracks, 9, D), 2)


class MoreAndLessLikeThisTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.settings["playlist_size"] = "10"  # More like this inserts 20 % = 2 tracks
        self.cache_path = self.save_mix([A, B, C])

    def test_more_like_this_inserts_new_tracks_after_selection(self):
        kodi.settings["mix_assist_auto_more_like_this"] = "false"  # AI Mix Assist off: MusicIP's tracks as they come
        new1, new2, new3 = (f"E:\\new\\{n}.mp3" for n in range(3))
        self.musicip.set_mix(B, [A, new1, C, new2, new3])
        self.assertEqual(main.insert_more_like_this_into_mix(A, 3, 1, B, cache_path=self.cache_path), 2)
        self.assertEqual(self.read_mix(self.cache_path), [A, B, new1, new2, C])
        self.assertEqual(self.musicip.mix_requests()[0]["size"], "10")

    def test_more_like_this_without_new_tracks(self):
        self.musicip.set_mix(B, [A, C])
        with self.assertRaisesRegex(main.MusicIPError, "No new tracks"):
            main.insert_more_like_this_into_mix(A, 3, 1, B, cache_path=self.cache_path)

    def test_less_like_this_removes_selection_and_similar_tracks(self):
        self.musicip.set_mix(B, [C])
        self.assertEqual(main.remove_less_like_this_from_mix(A, 3, 1, B, cache_path=self.cache_path), 2)
        self.assertEqual(self.read_mix(self.cache_path), [A])
        self.assertEqual(self.musicip.mix_requests()[0]["size"], "20")

    def test_seed_track_is_required(self):
        with self.assertRaisesRegex(main.MusicIPError, "No seed track"):
            main.insert_more_like_this_into_mix(A, 3, 1, "", cache_path=self.cache_path)
        with self.assertRaisesRegex(main.MusicIPError, "No seed track"):
            main.remove_less_like_this_from_mix(A, 3, 1, "", cache_path=self.cache_path)

    def test_target_size(self):
        for size, expected in (("10", 2), ("1", 1), ("100", 20)):
            kodi.settings["playlist_size"] = size
            self.assertEqual(main.get_more_like_this_target_size(), expected)


class ConsistencyTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        kodi.add_media(A)
        kodi.add_media(C)
        self.cache_path = self.save_mix([A, B, C, D])

    def test_missing_files_are_recorded(self):
        consistency = main.analyze_mix_consistency(self.cache_path)
        self.assertEqual(consistency["status"], "inconsistent")
        self.assertEqual(consistency["missing_files"], 2)
        self.assertEqual([(m["index"], m["path"]) for m in consistency["missing"]], [(1, B), (3, D)])
        meta = main.get_saved_mix_metadata(self.cache_path)
        self.assertTrue(main.is_mix_inconsistent(meta))
        self.assertEqual(main.get_consistency_label(meta), "Inconsistent: 2 missing")

    def test_first_seen_times_survive_rechecks(self):
        with mock.patch("time.time", return_value=1000):
            first = main.analyze_mix_consistency(self.cache_path)
        with mock.patch("time.time", return_value=2000):
            second = main.analyze_mix_consistency(self.cache_path)
        self.assertEqual(second["first_inconsistent_ts"], 1000)
        self.assertEqual(second["last_inconsistency_change_ts"], 1000)
        self.assertEqual(second["missing_signature"], first["missing_signature"])

        kodi.add_media(D)
        with mock.patch("time.time", return_value=3000):
            third = main.analyze_mix_consistency(self.cache_path)
        self.assertEqual(third["missing_files"], 1)
        self.assertEqual(third["first_inconsistent_ts"], 1000)
        self.assertEqual(third["last_inconsistency_change_ts"], 3000)
        self.assertEqual(third["missing"][0]["first_missing_ts"], 1000)

    def test_consistent_mix(self):
        kodi.add_media(B)
        kodi.add_media(D)
        consistency = main.analyze_mix_consistency(self.cache_path)
        self.assertEqual((consistency["status"], consistency["missing_files"]), ("ok", 0))
        self.assertEqual(main.get_consistency_label(main.get_saved_mix_metadata(self.cache_path)), "OK")

    def test_consistency_labels(self):
        self.assertEqual(main.get_consistency_label({}), "")
        self.assertEqual(main.get_consistency_label({"consistency": {"status": "inconsistent", "missing_files": 1}}), "Inconsistent: 1 missing")
        self.assertEqual(main.get_consistency_label({"consistency": {"status": "inconsistent"}}), "Inconsistent")
        self.assertEqual(main.get_consistency_label({"consistency": "garbage"}), "")


class RepairReadinessDeadlockTest(KodiTestCase):
    """The timeline from kodi.log on 2026-10-10 that left 18 mixes blocked under the old timestamp rule (F9)."""

    def test_library_that_already_reflects_the_change_does_not_block_repair(self):
        # The library changed before the check noticed the missing files, and later scans found nothing new,
        # so Kodi's timestamps never moved. The library no longer lists the missing files, so repair is possible.
        clock = self.use_clock(main.parse_kodi_datetime("2026-10-10 17:42:23"))  # 19:42 local
        kodi.add_media(A)
        kodi.add_media(C)
        cache_path = self.save_mix([A, B, C])
        main.analyze_mix_consistency(cache_path)  # B found missing

        kodi.remove_media(C)  # C deleted; the scan at 20:43 local records the change
        kodi.library_properties = {"librarylastupdated": "2026-10-10 18:43:52", "songsmodified": "2026-10-10 18:43:42"}

        clock.now = main.parse_kodi_datetime("2026-10-10 19:25:43")  # 21:25 local: Kodi restart
        main.analyze_mix_consistency(cache_path)  # C found missing -> last change 21:25

        clock.advance(600)  # scans at 21:27-21:34 find nothing; timestamps stay at 18:43 UTC
        readiness = main.get_mix_repair_readiness(main.get_saved_mix_metadata(cache_path))
        self.assertEqual(readiness["status"], "ready")


class RepairReadinessTest(KodiTestCase):
    """Repair is ready once the Kodi library no longer lists any of the mix's missing files."""

    def setUp(self):
        super().setUp()
        kodi.add_media(A)
        self.cache_path = self.save_mix([A, B])
        main.analyze_mix_consistency(self.cache_path)  # B is missing

    def readiness(self):
        meta = main.get_saved_mix_metadata(self.cache_path)
        return main.get_mix_repair_readiness(meta)

    def library_still_lists_missing_file(self):
        kodi.library.add_song(B, title="Song 2", present=False)

    def test_library_still_lists_missing_file(self):
        self.library_still_lists_missing_file()
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "update_library_before_repair")
        self.assertEqual(readiness["still_listed"], [B])
        self.assertEqual(readiness["reason"], "Kodi music library still lists 1 of 1 missing file(s). Update and clean the library.")
        self.assertFalse(main.is_repair_ready(readiness))
        with self.assertRaisesRegex(main.MusicIPError, "Update library before repair"):
            main.ensure_repair_ready(self.cache_path)

    def test_library_no_longer_lists_missing_file(self):
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["reason"], "Kodi music library no longer lists the missing files.")
        main.ensure_repair_ready(self.cache_path)
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        self.assertEqual(sidecar["repair_readiness"]["status"], "ready")

    def test_moved_file_listed_under_its_new_path_is_ready(self):
        kodi.library.add_song("E:\\moved\\02 Song 2.mp3", title="Song 2")
        self.assertEqual(self.readiness()["status"], "ready")

    def test_path_comparison_ignores_folder_separators(self):
        kodi.library.add_song(B.replace("\\", "/"), title="Song 2", present=False)
        self.assertEqual(self.readiness()["still_listed"], [B])

    def test_timestamps_are_not_used(self):
        self.library_still_lists_missing_file()
        kodi.library_properties = {"songsmodified": "2099-01-01 00:00:00"}
        self.assertEqual(self.readiness()["status"], "update_library_before_repair")
        self.assertNotIn("AudioLibrary.GetProperties", kodi.jsonrpc_methods())

    def test_library_query_failure_blocks_repair(self):
        kodi.fail_jsonrpc("AudioLibrary.GetSongs")
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "update_library_before_repair")
        self.assertTrue(readiness["reason"].startswith("Kodi music library could not be queried:"))

    def test_no_missing_files_recorded(self):
        readiness = main.evaluate_repair_readiness({"status": "inconsistent", "missing": []})
        self.assertEqual(readiness["status"], "update_library_before_repair")
        self.assertEqual(readiness["reason"], "No missing files are recorded yet. Run the consistency check again.")

    def test_consistent_mix_needs_no_repair(self):
        self.assertEqual(main.get_mix_repair_readiness({})["status"], "not_needed")
        self.assertEqual(main.evaluate_repair_readiness({"status": "ok"})["status"], "not_needed")

    def test_readiness_result_is_logged_with_extended_logging(self):
        kodi.settings["plugin_extended_logging"] = "true"
        self.library_still_lists_missing_file()
        self.readiness()
        kodi.library.songs.clear()
        self.readiness()
        main.get_mix_repair_readiness({"label": "Fine mix"})

        lines = [message for message, _level in kodi.logs if "Repair readiness:" in message]
        self.assertEqual(lines, [
            "[plugin.audio.musicip] Repair readiness: repair not available for '01 Song 1'; "
            "status=update_library_before_repair, reason='Kodi music library still lists 1 of 1 missing file(s). "
            "Update and clean the library.', missing_files=1, still_listed_by_kodi=1, "
            "unavailable_sources=0, outside_sources=0",
            "[plugin.audio.musicip] Repair readiness: repair available for '01 Song 1'; status=ready, "
            "reason='Kodi music library no longer lists the missing files.', missing_files=1, still_listed_by_kodi=0, "
            "unavailable_sources=0, outside_sources=0",
            "[plugin.audio.musicip] Repair readiness: repair not available for 'Fine mix'; status=not_needed, "
            "reason='Mix is not inconsistent.'",
        ])

    def test_readiness_is_not_logged_without_extended_logging(self):
        self.readiness()
        self.assertNotIn("Repair readiness:", kodi.log_text())

    def test_library_freshness_follows_extended_service_logging(self):
        kodi.library_properties = {"librarylastupdated": "2026-10-04 08:00:00"}
        kodi.settings["plugin_extended_logging"] = "true"
        main.get_audio_library_freshness()
        self.assertNotIn("Library freshness:", kodi.log_text())

        kodi.settings["service_extended_logging"] = "true"
        main.get_audio_library_freshness()
        self.assertIn("Library freshness: Kodi library property librarylastupdated='2026-10-04 08:00:00'", kodi.log_text())
        self.assertIn("Library freshness: parsed Kodi datetime '2026-10-04 08:00:00'", kodi.log_text())
        self.assertNotIn("Repair readiness:", kodi.log_text())

    def test_readiness_message(self):
        self.library_still_lists_missing_file()
        message = main.build_repair_readiness_message(self.readiness())
        self.assertIn("Kodi music library still lists 1 of 1 missing file(s). Update and clean the library.", message)
        self.assertIn("Missing files: 1", message)
        self.assertIn("Still listed by the Kodi music library:\n- " + B, message)
        self.assertIn("Update and clean the Kodi music library so it no longer lists these files, then try repair again.", message)
        self.assertNotIn("consistency service", message)

    def test_readiness_message_shortens_long_lists(self):
        paths = [f"D:\\music\\{n}.mp3" for n in range(12)]
        message = main.build_repair_readiness_message({"reason": "x", "missing_files": 12, "still_listed": paths})
        self.assertIn("- ... and 2 more", message)
        self.assertNotIn(paths[10], message)

    def test_update_library_dialog_runs_scan_and_clean(self):
        self.library_still_lists_missing_file()
        kodi.respond("select", 3)
        main.show_update_library_before_repair(self.cache_path)
        self.assertEqual(kodi.jsonrpc_methods()[-2:], ["AudioLibrary.Scan", "AudioLibrary.Clean"])
        self.assertNotified("scan and cleanup started")
        heading, text = kodi.dialogs("ok")[0][1]
        self.assertEqual(heading, "Update library before repair")
        self.assertIn(B, text)

    def test_update_library_dialog_when_already_ready(self):
        main.show_update_library_before_repair(self.cache_path)
        heading, text = kodi.dialogs("ok")[0][1]
        self.assertEqual(heading, "Repair is now available")
        self.assertIn("no longer lists the missing files", text)
        self.assertEqual(kodi.dialogs("select"), [])

    def test_library_maintenance_modes(self):
        for mode, methods in (("scan", ["AudioLibrary.Scan"]), ("clean", ["AudioLibrary.Clean"])):
            kodi.jsonrpc_calls.clear()
            main.run_audio_library_maintenance(mode)
            self.assertEqual(kodi.jsonrpc_methods(), methods)
        main.run_audio_library_maintenance("other")
        self.assertNotified("No library action selected.")


class RepairReadinessSourcesTest(KodiTestCase):
    """Repair needs Kodi music sources that can still add or update the missing files."""

    SOURCE = "D:\\music\\#metal\\"
    PRESENT = "D:\\music\\#metal\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
    MISSING = "D:\\music\\#metal\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"

    def setUp(self):
        super().setUp()
        kodi.music_sources = []
        kodi.add_media(self.PRESENT)
        self.cache_path = self.save_mix([self.PRESENT, self.MISSING])
        main.analyze_mix_consistency(self.cache_path)

    def readiness(self):
        return main.get_mix_repair_readiness(main.get_saved_mix_metadata(self.cache_path))

    def test_ready_when_the_covering_source_exists(self):
        kodi.add_music_source(self.SOURCE)
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual((readiness["unavailable_sources"], readiness["outside_sources"]), ([], []))

    def test_source_folder_gone_after_reorganization_blocks_repair(self):
        kodi.add_music_source(self.SOURCE, present=False)
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "update_sources_before_repair")
        self.assertEqual(readiness["unavailable_sources"], [self.SOURCE])
        self.assertEqual(
            readiness["reason"],
            f"Kodi music source(s) no longer available: {self.SOURCE}. Update the music sources to the new "
            "folder structure (or reconnect the drive), then update the library.",
        )
        self.assertEqual(main.repair_readiness_action_label(readiness), "Check music sources before repair")
        with self.assertRaisesRegex(main.MusicIPError, "Check music sources before repair"):
            main.ensure_repair_ready(self.cache_path)

    def test_most_specific_source_decides(self):
        kodi.add_music_source("D:\\")
        kodi.add_music_source(self.SOURCE, present=False)
        self.assertEqual(self.readiness()["unavailable_sources"], [self.SOURCE])

    def test_missing_files_outside_all_sources_are_only_reported(self):
        # Normal after an obsolete source was removed during a reorganization.
        kodi.add_music_source("E:\\new_structure\\")
        readiness = self.readiness()
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["outside_sources"], [self.MISSING])
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
        self.assertEqual(main.get_music_source_paths(), [self.SOURCE, "E:\\other\\"])
        self.assertEqual(self.readiness()["unavailable_sources"], [self.SOURCE])

    def test_network_source(self):
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
        kodi.add_music_source(self.SOURCE, present=False)
        main.show_update_library_before_repair(self.cache_path)
        self.assertEqual(kodi.dialogs("select"), [])  # scanning cannot help yet
        heading, text = kodi.dialogs("ok")[0][1]
        self.assertEqual(heading, "Check music sources before repair")
        self.assertIn("Kodi music sources that no longer exist:\n- " + self.SOURCE, text)
        self.assertIn("Update the Kodi music sources to match the folder structure on disk", text)

    def test_saved_mix_entry_names_the_sources(self):
        kodi.add_music_source(self.SOURCE, present=False)
        main.add_saved_mix_item(self.cache_path)
        _url, item, _folder = kodi.directory_items[-1]
        self.assertIn("Check music sources before repair", [label for label, _action in item.context_menu])
        self.assertTrue(item.getLabel2().endswith("· Check music sources before repair"))


class KodiDatetimeTest(unittest.TestCase):
    def test_formats(self):
        expected = 1_791_461_777  # 2026-10-08 12:16:17 UTC
        self.assertEqual(main.parse_kodi_datetime("2026-10-08 12:16:17"), expected)
        self.assertEqual(main.parse_kodi_datetime("2026-10-08T12:16:17Z"), expected)
        self.assertEqual(main.parse_kodi_datetime("2026-10-08"), expected - (12 * 3600 + 16 * 60 + 17))
        self.assertEqual(main.parse_kodi_datetime(""), 0)
        self.assertEqual(main.parse_kodi_datetime("yesterday"), 0)
        self.assertEqual(main.parse_kodi_datetime("2026-13-45"), 0)

    def test_display(self):
        self.assertEqual(main.format_ts_for_display(0), "unknown")
        self.assertEqual(main.format_calendar_date(0), "Unknown date")
        self.assertEqual(main.format_sidecar_ts("garbage"), "unknown")


class KeymapInstallTest(KodiTestCase):
    def test_keymap_is_installed_once(self):
        main.ensure_musicip_keymap_installed()
        path = main.get_musicip_user_keymap_path()
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), main.MUSICIP_KEYMAP_CONTENT)
        self.assertEqual(kodi.builtins, ["ReloadKeymaps"])

        main.ensure_musicip_keymap_installed()
        self.assertEqual(kodi.builtins, ["ReloadKeymaps"])

    def test_outdated_keymap_is_replaced(self):
        path = main.get_musicip_user_keymap_path()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<keymap/>")
        main.ensure_musicip_keymap_installed()
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), main.MUSICIP_KEYMAP_CONTENT)


if __name__ == "__main__":
    unittest.main()
