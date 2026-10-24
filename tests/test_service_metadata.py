"""Service background work: metadata refresh queue, sidecar updates, view refresh and repair readiness."""

import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, main, service

TRACK = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
OTHER = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
MIX_FOLDER = "plugin://plugin.audio.musicip/?action=browse_saved_mix&cache_path=x"


class MetadataRefreshTickTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        kodi.library.add_song(TRACK, title="Ace of Spades", artist="Motörhead", year=1980, genre=["Metal"])
        kodi.library_properties = {"songsmodified": "2026-10-01 00:00:00"}
        self.cache_path = self.save_mix([TRACK, OTHER])

    def test_refresh_writes_cache_and_mix_sidecar(self):
        main.enqueue_metadata_refresh_for_tracks([TRACK], cache_path=self.cache_path)
        self.assertEqual(service.run_metadata_refresh_tick(), 1)

        cached = main.read_track_metadata_cache(TRACK)
        self.assertEqual((cached["artist"], cached["decade"]), ("Motörhead", "1980s"))
        self.assertEqual(cached["cached_ts"], int(self.clock.now))
        self.assertEqual(cached["library_freshest_ts"], main.parse_kodi_datetime("2026-10-01 00:00:00"))

        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        self.assertEqual(sidecar["track_metadata_by_path"][main.canonical_audio_path(TRACK)]["title"], "Ace of Spades")
        self.assertEqual(sidecar["track_metadata_library_freshest_ts"], cached["library_freshest_ts"])
        self.assertEqual(main.load_metadata_refresh_queue()["entries"], [])

    def test_refreshed_metadata_shows_up_in_the_plugin(self):
        main.enqueue_metadata_refresh_for_tracks([TRACK], cache_path=self.cache_path)
        service.run_metadata_refresh_tick()
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        self.assertEqual(self.listed_labels()[0], "1. Motörhead - Ace of Spades  [COLOR FF8C929C]Seed[/COLOR]")

    def test_unresolved_tracks_are_retried_then_dropped(self):
        self.log_everything()
        main.enqueue_metadata_refresh_for_tracks([OTHER])
        for attempt in range(1, service.METADATA_REFRESH_MAX_ATTEMPTS):
            self.assertEqual(service.run_metadata_refresh_tick(), 0)
            self.assertEqual(main.load_metadata_refresh_queue()["entries"][0]["attempts"], attempt)
        service.run_metadata_refresh_tick()
        self.assertEqual(main.load_metadata_refresh_queue()["entries"], [])
        self.assertIn("dropped unresolved track after 3 attempts", kodi.log_text())

    def test_batch_size_limits_work_per_tick(self):
        paths = [f"D:\\music\\x\\{n}.mp3" for n in range(service.METADATA_REFRESH_BATCH_SIZE + 2)]
        main.enqueue_metadata_refresh_for_tracks(paths)
        service.run_metadata_refresh_tick()
        entries = main.load_metadata_refresh_queue()["entries"]
        self.assertEqual(len(entries), len(paths))
        self.assertEqual([entry.get("attempts", 0) for entry in entries], [1] * 5 + [0, 0])

    def test_empty_queue(self):
        self.assertEqual(service.run_metadata_refresh_tick(), 0)
        self.assertEqual(kodi.jsonrpc_calls, [])

    def test_service_and_plugin_share_the_cache_format(self):
        service.write_track_metadata_cache(TRACK, {"title": "Ace", "genre": "Metal", "year": 1980})
        self.assertEqual(main.read_track_metadata_cache(TRACK)["genre"], ["Metal"])


class ViewRefreshTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        kodi.info_labels.update({"Container.FolderPath": MIX_FOLDER, "Container.CurrentItem": "1"})

    def test_refresh_waits_for_selection_change(self):
        service.refresh_visible_mix_view_if_needed(2)
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertEqual(kodi.builtins, [])

        kodi.info_labels["Container.CurrentItem"] = "2"
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertEqual(kodi.builtins, [f"Container.Update({MIX_FOLDER},replace)"])

        kodi.info_labels["Container.CurrentItem"] = "3"
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertEqual(len(kodi.builtins), 1)

    def test_refreshes_are_spaced_out(self):
        service.refresh_visible_mix_view_if_needed(1)
        kodi.info_labels["Container.CurrentItem"] = "2"
        service.apply_pending_metadata_refresh_on_selection_change()

        service.refresh_visible_mix_view_if_needed(1)
        kodi.info_labels["Container.CurrentItem"] = "3"
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertEqual(len(kodi.builtins), 1)

        self.clock.advance(service.METADATA_REFRESH_MIN_REFRESH_GAP_SECONDS)
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertEqual(len(kodi.builtins), 2)

    def test_no_refresh_outside_mix_views(self):
        kodi.info_labels["Container.FolderPath"] = "musicdb://artists/"
        service.refresh_visible_mix_view_if_needed(1)
        self.assertFalse(service.METADATA_REFRESH_PENDING_VIEW_REFRESH)

    def test_pending_refresh_is_dropped_when_user_leaves_the_mix(self):
        service.refresh_visible_mix_view_if_needed(1)
        kodi.info_labels["Container.FolderPath"] = "musicdb://artists/"
        service.apply_pending_metadata_refresh_on_selection_change()
        self.assertFalse(service.METADATA_REFRESH_PENDING_VIEW_REFRESH)
        self.assertEqual(kodi.builtins, [])

    def test_visible_context(self):
        kodi.window_id = 10502
        kodi.info_labels["Container.FolderPath"] = "plugin://plugin.audio.musicip/?action=saved_mixes"
        context = service.get_visible_musicip_mix_context()
        self.assertEqual((context["is_musicip_view"], context["is_mix_view"], context["is_visible_mix"]), (True, False, True))


def kodi_datetime(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


class BackgroundConsistencyCheckTest(KodiTestCase):
    PRESENT = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
    MISSING = "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"
    MOVED = "E:\\moved\\01 Motorcycle Man.mp3"

    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        kodi.add_media(self.PRESENT)
        kodi.library.add_song(self.MOVED, title="Motorcycle Man", artist="Saxon")
        # Kodi has scanned the new location but not been cleaned: it still lists the missing file.
        kodi.library.add_song(self.MISSING, title="Motorcycle Man", artist="Saxon", present=False)
        self.cache_path = self.save_mix([self.PRESENT, self.MISSING])

    def sidecar(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))

    def library_updated(self):
        # A library clean removes the entry for the missing file.
        self.clock.advance(600)
        kodi.library.songs = [song for song in kodi.library.songs if song["file"] != self.MISSING]

    def test_records_missing_tracks_and_readiness(self):
        self.assertEqual(service.run_consistency_check(), 1)
        sidecar = self.sidecar()
        self.assertEqual(sidecar["consistency"]["status"], "inconsistent")
        self.assertEqual(sidecar["consistency"]["missing"][0]["path"], self.MISSING)
        self.assertEqual(sidecar["repair_readiness"]["status"], "update_library_before_repair")
        self.assertEqual(self.read_mix(self.cache_path), [self.PRESENT, self.MISSING])

    def test_consistent_mix(self):
        kodi.add_media(self.MISSING)
        self.assertEqual(service.run_consistency_check(), 0)
        self.assertEqual(self.sidecar()["consistency"]["status"], "ok")

    def test_repairs_automatically_once_library_is_cleaned(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        service.run_consistency_check()
        self.assertEqual(self.read_mix(self.cache_path)[1], self.MISSING)  # library still lists the missing file

        self.library_updated()
        self.assertEqual(service.run_consistency_check(), 1)
        self.assertEqual(self.read_mix(self.cache_path), [self.PRESENT, self.MOVED])
        sidecar = self.sidecar()
        self.assertEqual(sidecar["consistency"]["status"], "ok")
        self.assertEqual(sidecar["repair_readiness"]["status"], "not_needed")

        self.assertEqual(service.run_consistency_check(), 0)

    def test_no_repair_when_automatic_repair_is_off(self):
        service.run_consistency_check()
        self.library_updated()
        service.run_consistency_check()
        self.assertEqual(self.read_mix(self.cache_path), [self.PRESENT, self.MISSING])
        self.assertEqual(self.sidecar()["repair_readiness"]["status"], "ready")

    def test_ambiguous_candidates_are_never_guessed(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        kodi.library.add_song("F:\\other\\01 Motorcycle Man.mp3", title="Motorcycle Man", artist="Saxon")
        service.run_consistency_check()
        self.library_updated()
        service.run_consistency_check()
        self.assertEqual(self.read_mix(self.cache_path), [self.PRESENT, self.MISSING])
        self.assertEqual(kodi.dialog_calls, [])

    def test_notifies_when_automatic_repair_waits_for_library_update(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [(
            "MusicIP",
            "Mix '01 Overkill' has missing tracks. Update the Kodi music library to allow automatic repair.",
            "warning",
        )])

    def test_notification_counts_several_waiting_mixes(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        self.save_mix([self.MISSING, self.PRESENT])
        service.run_consistency_check()
        self.assertEqual(kodi.notification_messages(), [
            "2 mixes have missing tracks. Update the Kodi music library to allow automatic repair.",
        ])

    def test_no_notification_without_automatic_repair(self):
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [])

    def test_no_notification_when_repair_is_possible(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        service.run_consistency_check()
        kodi.notifications.clear()
        self.library_updated()
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [])

    def test_no_notification_for_consistent_mixes(self):
        kodi.settings["service_auto_repair_enabled"] = "true"
        kodi.add_media(self.MISSING)
        service.run_consistency_check()
        self.assertEqual(kodi.notifications, [])

    def test_one_broken_mix_does_not_stop_the_check(self):
        self.log_everything()
        other = self.save_mix([self.MISSING, self.PRESENT])
        original = main.analyze_mix_consistency

        def fail_for_first(cache_path):
            if cache_path == self.cache_path:
                raise RuntimeError("unreadable")
            return original(cache_path)

        with mock.patch.object(main, "analyze_mix_consistency", fail_for_first):
            self.assertEqual(service.run_consistency_check(), 1)
        self.assertEqual(self.read_json(main.mix_meta_path_from_cache_path(other))["consistency"]["status"], "inconsistent")
        self.assertIn("Consistency check failed for", kodi.log_text())

    def test_summary_is_logged_with_saved_mix_check_logging(self):
        kodi.settings["log_checks"] = "true"
        service.run_consistency_check()
        log_text = kodi.log_text()
        self.assertIn("Consistency check: '01 Overkill' has 1 missing track(s).", log_text)
        self.assertIn("Repair readiness: repair not available for '01 Overkill'; status=update_library_before_repair", log_text)
        self.assertIn("Consistency check: checked 1 mix(es), 1 inconsistent, automatic repair disabled, repaired 0 track(s).", log_text)
        self.assertNotIn("skipped in this build branch", log_text)

    def test_service_loop_runs_the_check(self):
        service.main()
        self.assertEqual(self.sidecar()["consistency"]["status"], "inconsistent")

    def test_service_loop_respects_the_setting(self):
        kodi.settings["consistency_enabled"] = "false"
        service.main()
        self.assertNotIn("consistency", self.sidecar())

    def test_service_loop_waits_for_the_interval(self):
        kodi.abort_after_waits = 3
        with mock.patch.object(service, "run_consistency_check", wraps=service.run_consistency_check) as check:
            with mock.patch.object(service.xbmc.Monitor, "waitForAbort", side_effect=self.wait_one_minute, autospec=True):
                service.main()
        self.assertEqual(check.call_count, 1)  # three one-minute waits, 60-minute interval

    def wait_one_minute(self, monitor, timeout=0):
        self.clock.advance(60)
        kodi.waits += 1
        return kodi.waits >= kodi.abort_after_waits


class ServiceLoggingTest(KodiTestCase):
    def test_service_run_logs_nothing_but_errors(self):
        kodi.add_media("D:\music\a.mp3")
        self.save_mix(["D:\music\a.mp3", "D:\music\gone.mp3"])
        main.enqueue_metadata_refresh_for_tracks(["D:\music\gone.mp3"])
        kodi.settings["service_auto_repair_enabled"] = "true"
        kodi.logs.clear()
        service.main()
        below_error = [message for message, level in kodi.logs if level < 3]
        self.assertEqual(len(below_error), 1)
        self.assertTrue(below_error[0].startswith("[plugin.audio.musicip] [general] MusicIP service started. version="))

    def test_service_errors_are_still_logged(self):
        with mock.patch.object(service, "run_discovery_tick", side_effect=RuntimeError("boom")):
            service.main()
        self.assertIn(("[plugin.audio.musicip] [discovery] Discovery mode tick failed: boom", 3), kodi.logs)


class ServiceStartupLogTest(KodiTestCase):
    def start_lines(self):
        return [(message, level) for message, level in kodi.logs if "MusicIP service started." in message]

    def test_start_line_is_logged_as_info_without_logging(self):
        service.main()
        lines = self.start_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][1], 1)  # LOGINFO

    def test_start_line_with_all_logging(self):
        self.log_everything()
        service.main()
        self.assertEqual(len(self.start_lines()), 1)
        self.assertIn("logging: general on, mixing on, ai on, radio on, discovery on, checks on.", self.start_lines()[0][0])

    def test_service_start_message_has_a_single_addon_prefix(self):
        service.main()
        message = self.start_lines()[0][0]
        self.assertTrue(message.startswith("[plugin.audio.musicip] [general] MusicIP service started. version="))
        self.assertNotIn("[plugin.audio.musicip] [plugin.audio.musicip]", message)


class ServiceRepairReadinessTest(KodiTestCase):
    MISSING = "D:\\music\\gone.mp3"
    CONSISTENCY = {"status": "inconsistent", "first_inconsistent_ts": 100, "missing": [{"path": MISSING}]}

    def test_service_uses_the_plugin_rule(self):
        for still_listed in (False, True):
            with self.subTest(still_listed=still_listed):
                kodi.library.songs.clear()
                if still_listed:
                    kodi.library.add_song(self.MISSING, title="Gone", present=False)
                from_service = service.get_repair_readiness_for_consistency(self.CONSISTENCY)
                from_plugin = main.evaluate_repair_readiness(self.CONSISTENCY)
                for key in ("status", "reason", "missing_files", "still_listed"):
                    self.assertEqual(from_service[key], from_plugin[key])
        self.assertEqual(service.get_repair_readiness_for_consistency({"status": "ok"})["status"], "not_needed")

    def test_readiness_result_is_logged_with_saved_mix_check_logging(self):
        kodi.settings["log_checks"] = "true"
        service.get_repair_readiness_for_consistency(self.CONSISTENCY, "Rock mix")
        kodi.library.add_song(self.MISSING, title="Gone", present=False)
        service.get_repair_readiness_for_consistency(self.CONSISTENCY)
        lines = [message for message, _level in kodi.logs if "Repair readiness:" in message]
        self.assertIn("Repair readiness: repair available for 'Rock mix'; status=ready", lines[0])
        self.assertIn("Repair readiness: repair not available; status=update_library_before_repair, "
                      "reason='Kodi music library still lists 1 of 1 missing file(s). Update and clean the library.'", lines[1])

    def test_readiness_follows_the_saved_mix_check_switch(self):
        self.log_everything()
        kodi.settings["log_checks"] = "false"
        service.get_repair_readiness_for_consistency(self.CONSISTENCY)
        self.assertNotIn("Repair readiness:", kodi.log_text())

    def test_service_settings(self):
        self.assertTrue(service.is_consistency_service_enabled())
        self.assertFalse(service.is_service_auto_repair_enabled())
        self.assertEqual(service.get_check_interval_seconds(), 3600)
        kodi.settings["consistency_interval_minutes"] = "0"
        self.assertEqual(service.get_check_interval_seconds(), 60)

    def test_unreadable_json_file(self):
        self.log_everything()
        path = self.profile_path("broken.json")
        service.get_profile_dir()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{")
        self.assertEqual(service.load_json_file(path), {})
        self.assertIn("Could not load JSON file", kodi.log_text())


if __name__ == "__main__":
    unittest.main()
