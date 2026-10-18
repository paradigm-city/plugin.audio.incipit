"""Discovery mode, plugin side: menu, start/stop/next, and creating a mix from the current discovery song."""

import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, MusicIPServerTestCase, main, plugin_query

SONGS = [(f"D:\\music\\Artist {n}\\Album\\0{n} Song.mp3", f"Song {n}", f"Artist {n}", 200 + n) for n in range(1, 4)]


def add_library_songs():
    for file, title, artist, duration in SONGS:
        kodi.library.add_song(file, title=title, artist=artist, duration=duration)


class DiscoveryHelpersTest(unittest.TestCase):
    def test_offset(self):
        self.assertEqual(main.calculate_discovery_offset(300, 20, 33), 99)
        self.assertEqual(main.calculate_discovery_offset(100, 20, 90), 78)  # leaves room for the excerpt
        self.assertEqual(main.calculate_discovery_offset(15, 20, 33), 0)
        self.assertEqual(main.calculate_discovery_offset(0, 20, 33), 0)
        self.assertEqual(main.calculate_discovery_offset("x", 20, 33), 0)

    def test_song_label(self):
        self.assertEqual(main.discovery_song_label_from_song({"title": "T", "artist": ["A", "B"]}), "A, B - T")
        self.assertEqual(main.discovery_song_label_from_song({"title": "T"}), "T")
        self.assertEqual(main.discovery_song_label_from_song({"file": "/m/01 Song.mp3"}), "01 Song")


class DiscoveryMenuTest(KodiTestCase):
    def test_inactive_menu(self):
        self.run_plugin(action="discovery_mode")
        self.assertEqual(self.listed_labels(), ["Start discovery mode", "Discovery mode settings"])
        self.assertIn(("setPluginCategory", "MusicIP discovery mode"), kodi.directory_calls)

    def test_active_menu(self):
        main.save_discovery_state({"enabled": True, "current_label": "Artist 1 - Song 1"})
        self.run_plugin(action="discovery_mode")
        self.assertEqual(self.listed_labels(), [
            "Create mix from current discovery song", "Skip to next discovery song",
            "Stop discovery mode", "Discovery mode settings",
        ])
        self.assertIn(("setPluginCategory", "Discovery mode: Artist 1 - Song 1"), kodi.directory_calls)


class DiscoveryMenuFocusTest(KodiTestCase):
    def test_a_redrawn_screen_has_the_same_urls_so_kodi_keeps_the_focus(self):
        main.save_discovery_state({"enabled": True, "current_label": "Artist 1 - Song 1"})
        self.run_plugin(action="discovery_mode")
        first = [url for url, _item, _folder in kodi.directory_items]
        kodi.directory_items.clear()
        main.save_discovery_state({"enabled": True, "current_label": "Artist 2 - Song 2"})
        self.run_plugin(action="discovery_mode")
        self.assertEqual([url for url, _item, _folder in kodi.directory_items], first)


class StartStopTest(KodiTestCase):
    def test_start_fills_playlist_and_plays_from_offset(self):
        add_library_songs()
        self.run_plugin(action="discovery_start")

        state = main.get_discovery_state()
        self.assertTrue(state["enabled"])
        self.assertFalse(state["startup_in_progress"])
        self.assertEqual(len(state["queue"]), main.DISCOVERY_BUFFER_SIZE)
        self.assertEqual(len(kodi.playlist), main.DISCOVERY_BUFFER_SIZE)
        self.assertEqual(state["current_playlist_position"], 0)
        self.assertEqual(state["current_song"], kodi.player.file)

        first = state["queue"][0]
        self.assertEqual(first["offset"], main.calculate_discovery_offset(first["duration"], 20, 33))
        item = kodi.playlist[0][1]
        self.assertEqual(item.getProperty("StartOffset"), str(first["offset"]))
        self.assertEqual(item.getProperty("MusicIP.Discovery"), "true")
        self.assertEqual(kodi.player.time, float(first["offset"]))

        self.assertNotified("Discovery mode started.")
        self.assertEqual(plugin_query(kodi.builtins[-1])["action"], "discovery_mode")

    def test_start_with_empty_library(self):
        self.run_plugin(action="discovery_start")
        state = main.get_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertIn("could not be filled", state["last_error"])
        self.assertEqual(kodi.notifications[0][2], "error")

    def test_start_when_player_refuses(self):
        add_library_songs()
        with mock.patch("fake_kodi.Player.play", side_effect=RuntimeError("no audio device")):
            self.run_plugin(action="discovery_start")
        state = main.get_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["last_error"], "Discovery playlist could not be started: no audio device")

    def test_library_query_falls_back_without_random_sort(self):
        add_library_songs()
        kodi.fail_jsonrpc("AudioLibrary.GetSongs")
        self.assertEqual(len(main.get_discovery_library_songs()), 3)
        self.assertNotIn("sort", kodi.jsonrpc_calls[1]["params"])

    def test_stop(self):
        add_library_songs()
        self.run_plugin(action="discovery_start")
        self.run_plugin(action="discovery_stop")
        state = main.get_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "manual_stop")
        self.assertFalse(kodi.player.playing)
        self.assertEqual(kodi.playlist, [])
        self.assertNotified("Discovery mode stopped.")


class NextTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        add_library_songs()
        self.run_plugin(action="discovery_start")

    def test_next_moves_to_buffered_song(self):
        self.run_plugin(action="discovery_next")
        state = main.get_discovery_state()
        self.assertEqual((kodi.player.position, state["current_playlist_position"]), (1, 1))
        self.assertEqual(state["current_song"], state["queue"][1]["file"])
        self.assertGreater(state["last_ui_next_ts"], 0)
        self.assertNotified("skipping to next song")

    def test_next_at_end_of_buffer(self):
        state = main.get_discovery_state()
        state["current_playlist_position"] = len(state["queue"]) - 1
        main.save_discovery_state(state)
        self.run_plugin(action="discovery_next")
        self.assertNotified("No buffered next discovery song available yet.")

    def test_state_update_ignores_invalid_positions(self):
        state = main.get_discovery_state()
        self.assertIs(main.update_discovery_state_for_playlist_position(state, 99), state)
        self.assertIs(main.update_discovery_state_for_playlist_position({"queue": "x"}, 0)["queue"], "x")


class MixFromDiscoverySongTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        add_library_songs()
        self.run_plugin(action="discovery_start")
        self.seed = main.get_discovery_state()["current_song"]

    def test_mix_replaces_discovery_playback(self):
        mix_track = "D:\\music\\Other\\Album\\01 Mixed.mp3"
        self.musicip.set_mix(self.seed, [mix_track])
        kodi.respond("select", 0)

        self.run_plugin(action="discovery_mix_current")

        state = main.get_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "mix_from_discovery_song")
        self.assertFalse(state["mix_dialog_active"])
        self.assertEqual(kodi.playlist_files(), [self.seed, mix_track])
        self.assertEqual(main.load_mix(self.seed, 20), [self.seed, mix_track])
        self.assertNotified("Discovery mode stopped. Playing generated mix.")
        self.assertEqual(plugin_query(kodi.builtins[-1])["action"], "browse_mix")

    def test_dialog_hold_pauses_auto_skip(self):
        def check_hold(*args):
            state = main.get_discovery_state()
            self.assertTrue(state["mix_dialog_active"])
            self.assertEqual(state["mix_dialog_seed"], self.seed)
            return -1

        kodi.respond("select", check_hold)
        self.run_plugin(action="discovery_mix_current")
        self.assertFalse(main.get_discovery_state()["mix_dialog_active"])

    def test_short_cancel_keeps_current_song(self):
        self.run_plugin(action="discovery_mix_current")
        state = main.get_discovery_state()
        self.assertTrue(state["enabled"])
        self.assertEqual(kodi.player.position, 0)
        self.assertEqual(kodi.notifications[-1][2], "warning")

    def test_cancel_after_excerpt_length_skips_to_next_song(self):
        started = time.time()
        with mock.patch("time.time", side_effect=lambda: started):
            main.set_discovery_mix_dialog_hold(self.seed)
        with mock.patch("time.time", return_value=started + 30):
            main.clear_discovery_mix_dialog_hold(skip_if_elapsed=True)
        self.assertEqual(kodi.player.position, 1)
        self.assertEqual(main.get_discovery_state()["current_playlist_position"], 1)

    def test_server_error_resumes_discovery(self):
        self.musicip.mix_status = 500
        kodi.respond("select", 0)
        self.run_plugin(action="discovery_mix_current")
        self.assertTrue(main.get_discovery_state()["enabled"])
        self.assertNotified("HTTP 500")

    def test_no_current_song(self):
        main.save_discovery_state({"enabled": True})
        kodi.player.playing = False
        self.run_plugin(action="discovery_mix_current")
        self.assertNotified("No discovery song is currently available.")


if __name__ == "__main__":
    unittest.main()
