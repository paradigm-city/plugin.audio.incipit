"""MusicIP's library, reloaded by the service now and then and after Kodi's music library scan (not before mixes)."""

import unittest

from fake_kodi import kodi
from support import MusicIPServerTestCase, main, service


class MusicIPReloadTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        service.MUSICIP_RELOAD.update(thread=None, scan_finished=False, first_tick_ts=0.0)

    def tick(self, seconds=0):
        self.clock.advance(seconds)
        thread = service.run_musicip_reload_tick()
        if thread is not None:
            thread.join(10)
        return thread is not None

    def record(self):
        return service.load_json_file(service.musicip_reload_state_path())

    def test_not_while_kodi_starts_then_once(self):
        self.assertFalse(self.tick())
        self.assertFalse(self.tick(service.MUSICIP_RELOAD_STARTUP_DELAY_SECONDS - 1))
        self.assertTrue(self.tick(1))
        self.assertEqual(self.musicip.reload_count(), 1)
        self.assertEqual(self.record(), {"last_ts": int(self.clock.now)})
        self.assertIn("MusicIP library reloaded (scheduled)", kodi.log_text())  # without extended logging

    def test_about_three_times_a_day(self):
        self.tick()
        self.tick(service.MUSICIP_RELOAD_STARTUP_DELAY_SECONDS)
        self.assertFalse(self.tick(service.MUSICIP_RELOAD_INTERVAL_SECONDS - 1))
        self.assertTrue(self.tick(1))
        self.assertEqual(self.musicip.reload_count(), 2)

    def test_a_kodi_restart_keeps_the_time_of_the_last_reload(self):
        service.save_json_file(service.musicip_reload_state_path(), {"last_ts": int(self.clock.now) - 3600})
        self.tick()
        self.assertFalse(self.tick(service.MUSICIP_RELOAD_STARTUP_DELAY_SECONDS))
        self.assertEqual(self.musicip.reload_count(), 0)

    def test_after_kodis_music_library_scan_at_once(self):
        service.save_json_file(service.musicip_reload_state_path(), {"last_ts": int(self.clock.now)})
        monitor = service.ServiceMonitor()
        monitor.onScanFinished("video")
        self.assertFalse(self.tick())
        monitor.onScanFinished("music")
        self.assertTrue(self.tick())
        self.assertIn("MusicIP library reloaded (after Kodi's library scan)", kodi.log_text())
        self.assertFalse(self.tick(1))  # once

    def test_a_failed_reload_is_tried_again_later(self):
        self.musicip.reload_status = 503
        self.tick()
        self.assertTrue(self.tick(service.MUSICIP_RELOAD_STARTUP_DELAY_SECONDS))
        self.assertIn("MusicIP library reload (scheduled) failed", kodi.log_text())
        self.assertFalse(self.tick(service.MUSICIP_RELOAD_RETRY_SECONDS - 1))
        self.musicip.reload_status = 200
        self.assertTrue(self.tick(1))
        self.assertEqual(self.musicip.reload_count(), 2)
        self.assertEqual(self.record(), {"last_ts": int(self.clock.now)})

    def test_mixes_do_not_reload(self):
        self.musicip.set_mix("D:\\music\\a.mp3", ["D:\\music\\b.mp3"])
        main.fetch_mix("D:\\music\\a.mp3", 10)
        self.assertEqual(self.musicip.reload_count(), 0)


if __name__ == "__main__":
    unittest.main()
