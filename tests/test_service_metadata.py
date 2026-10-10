"""Service background work: metadata refresh queue, sidecar updates, view refresh and repair readiness."""

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
        self.assertEqual(self.listed_labels()[0], "1. Motörhead - Ace of Spades")

    def test_unresolved_tracks_are_retried_then_dropped(self):
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


class ServiceRepairReadinessTest(KodiTestCase):
    def test_matches_plugin_readiness(self):
        consistency = {"status": "inconsistent", "first_inconsistent_ts": 100, "missing": [{"first_missing_ts": 150}]}
        for properties in ({}, {"songsmodified": "1970-01-01 00:02:00"}, {"songsmodified": "2026-01-01 00:00:00"}):
            with self.subTest(properties=properties):
                kodi.library_properties = properties
                from_service = service.get_repair_readiness_for_consistency(consistency)
                from_plugin = main.get_mix_repair_readiness({"consistency": consistency})
                for key in ("status", "reason", "required_library_ts", "library_freshest_ts"):
                    self.assertEqual(from_service[key], from_plugin[key])
        self.assertEqual(service.get_repair_readiness_for_consistency({"status": "ok"})["status"], "not_needed")

    def test_service_settings(self):
        self.assertTrue(service.is_consistency_service_enabled())
        self.assertFalse(service.is_service_auto_repair_enabled())
        self.assertEqual(service.get_check_interval_seconds(), 3600)
        kodi.settings["consistency_interval_minutes"] = "0"
        self.assertEqual(service.get_check_interval_seconds(), 60)

    def test_service_extended_logging(self):
        service.log_info("hidden")
        kodi.settings["service_extended_logging"] = "true"
        service.log_info("shown")
        self.assertNotIn("hidden", kodi.log_text())
        self.assertIn("shown", kodi.log_text())

    def test_unreadable_json_file(self):
        path = self.profile_path("broken.json")
        service.get_profile_dir()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{")
        self.assertEqual(service.load_json_file(path), {})
        self.assertIn("Could not load JSON file", kodi.log_text())


if __name__ == "__main__":
    unittest.main()
