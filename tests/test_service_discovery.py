"""Discovery mode, service side: the playlist buffer, auto-skip, player events and startup reset.

The plugin starts, stops and skips Discovery mode; the service runs it through the shared state file."""

import unittest
from unittest import mock

import fake_kodi
from fake_kodi import kodi
from support import KodiTestCase, service

SONGS = [(f"D:\\music\\Artist {n}\\Album\\{n:02d} Song.mp3", f"Song {n}", f"Artist {n}", 240) for n in range(1, 31)]
OFFSET = service.calculate_discovery_offset(240, 20, 33)  # 79 seconds into each song


def add_library_songs(count=len(SONGS)):
    for file, title, artist, duration in SONGS[:count]:
        kodi.library.add_song(file, title=title, artist=artist, duration=duration)


class DiscoveryServiceTestCase(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        self.song_cache = []
        add_library_songs()

    def start(self):
        """Start Discovery mode the way the add-on does: from the plugin."""
        self.run_plugin(action="discovery_start")
        self.song_cache = []
        return service.load_discovery_state()

    def tick(self, seconds=1):
        self.clock.advance(seconds)
        self.song_cache = service.run_discovery_tick(self.song_cache)
        return service.load_discovery_state()


class LeftoverCommandFileTest(DiscoveryServiceTestCase):
    def test_command_file_from_an_older_version_is_ignored(self):
        # Older versions controlled the service through discovery_mode_command.json (finding F6).
        command_file = self.profile_path("discovery_mode_command.json")
        service.get_profile_dir()
        self.write_json(command_file, {"command": "start", "ts": int(self.clock.now)})
        state = self.tick()
        self.assertFalse(state.get("enabled"))
        self.assertEqual(kodi.playlist, [])


class PluginStartedSessionTest(DiscoveryServiceTestCase):
    """The plugin starts Discovery directly; from then on the service runs it via the shared state file."""

    def setUp(self):
        super().setUp()
        self.start()

    def test_service_takes_over_a_plugin_started_session(self):
        state = self.tick(10)
        self.assertTrue(state["enabled"])
        self.assertEqual(kodi.player.position, 0)

        state = self.tick(11)  # excerpt of 20 s elapsed
        self.assertEqual((kodi.player.position, state["current_playlist_position"]), (1, 1))
        self.assertEqual(state["last_next_reason"], "excerpt_elapsed")
        self.assertEqual(kodi.player.time, float(state["queue"][1]["offset"]))

    def test_service_refills_and_prunes_a_plugin_started_playlist(self):
        for _song in range(14):
            self.tick(21)
        state = service.load_discovery_state()
        # Pruning runs before the auto-skip within a tick, so the backlog can be one longer until the next tick.
        self.assertLessEqual(kodi.player.position, service.DISCOVERY_BACKLOG_SIZE + 1)
        self.assertGreater(state["playlist_pruned_count"], 0)
        self.assertEqual(kodi.playlist_files(), [entry["file"] for entry in state["queue"]])
        self.assertGreaterEqual(len(state["queue"]) - kodi.player.position - 1, service.DISCOVERY_REFILL_THRESHOLD)

    def test_plugin_skip_restarts_the_service_timer(self):
        self.clock.advance(15)
        self.run_plugin(action="discovery_next")
        state = self.tick(10)  # 25 s since start, but only 10 s since the skip
        self.assertEqual((kodi.player.position, state["current_playlist_position"]), (1, 1))

    def test_plugin_stop_ends_service_control(self):
        self.run_plugin(action="discovery_stop")
        state = self.tick(60)
        self.assertFalse(state["enabled"])
        self.assertEqual(kodi.playlist, [])

    def test_outside_playback_ends_service_control(self):
        kodi.play_file("D:\\music\\Elsewhere\\song.mp3")
        state = self.tick()
        self.assertEqual((state["enabled"], state["stop_reason"]), (False, "external_playback"))


class AutoSkipTest(DiscoveryServiceTestCase):
    def test_skips_after_excerpt_length(self):
        self.start()
        state = self.tick(10)
        self.assertEqual(state["current_playlist_position"], 0)

        state = self.tick(11)
        self.assertEqual(kodi.player.position, 1)
        self.assertEqual(state["current_playlist_position"], 1)
        self.assertEqual(state["last_next_reason"], "excerpt_elapsed")
        self.assertEqual(state["current_started_ts"], int(self.clock.now))

    def test_no_skip_while_mix_dialog_is_open(self):
        state = self.start()
        state["mix_dialog_active"] = True
        service.save_discovery_state(state)
        state = self.tick(60)
        self.assertEqual(kodi.player.position, 0)

    def test_next_request_from_state(self):
        state = self.start()
        state["next_requested"] = True
        service.save_discovery_state(state)
        state = self.tick()
        self.assertEqual(kodi.player.position, 1)
        self.assertFalse(state["next_requested"])

    def test_buffer_is_refilled_near_its_end(self):
        self.start()
        kodi.go_to(6)  # 3 songs left, below the refill threshold of 5
        state = self.tick()
        self.assertEqual(len(state["queue"]), 6 + 1 + service.DISCOVERY_BUFFER_SIZE)
        self.assertEqual(len(kodi.playlist), len(state["queue"]))

    def test_played_songs_are_pruned(self):
        self.start()
        kodi.go_to(6)
        self.tick()
        kodi.go_to(13)
        state = self.tick()
        removed = 13 - service.DISCOVERY_BACKLOG_SIZE
        self.assertEqual(state["playlist_pruned_count"], removed)
        self.assertEqual(kodi.player.position, service.DISCOVERY_BACKLOG_SIZE)
        self.assertEqual(state["current_playlist_position"], service.DISCOVERY_BACKLOG_SIZE)
        self.assertEqual(kodi.playlist_files(), [entry["file"] for entry in state["queue"]])

    def test_restart_near_song_beginning_is_moved_back_to_offset(self):
        self.start()
        kodi.player.time = 0.0  # e.g. Previous restarted the song
        self.tick(1)  # the song has just started: give Kodi time to apply its start offset
        self.assertEqual(kodi.player.time, 0.0)
        self.tick(1)
        self.assertEqual(kodi.player.time, float(OFFSET))
        self.assertEqual(service.load_discovery_state()["last_seek_correction_to"], OFFSET)


class PlaybackTakeoverTest(DiscoveryServiceTestCase):
    def test_external_playback_stops_discovery(self):
        self.start()
        kodi.play_file("D:\\music\\Elsewhere\\song.mp3")
        state = self.tick()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "external_playback")
        self.assertTrue(state["ui_refresh_requested"])
        self.assertTrue(kodi.player.playing)

    def test_user_stopping_playback_stops_discovery(self):
        self.start()
        self.clock.advance(5)
        fake_kodi.Player().stop()
        state = self.tick()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "player_stop")

    def test_playing_the_expected_discovery_song_is_not_a_takeover(self):
        state = self.start()
        self.assertTrue(service.current_playback_belongs_to_discovery(state))
        state["queue"] = []
        self.assertTrue(service.current_playback_belongs_to_discovery(state))
        state["queue"] = [{"file": "D:\\other.mp3"}]
        self.assertTrue(service.current_playback_belongs_to_discovery(state))  # still the current_song
        state["current_song"] = "D:\\other.mp3"
        self.assertFalse(service.current_playback_belongs_to_discovery(state))

    def test_stop_right_after_start_is_tolerated(self):
        self.start()
        kodi.player.playing = False
        state = self.tick(1)
        self.assertTrue(state["enabled"])


class PlayerEventTest(DiscoveryServiceTestCase):
    def setUp(self):
        super().setUp()
        self.start()
        service.DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL = 0.0
        self.monitor = service.DiscoveryPlaybackMonitor()

    def test_stop_event_is_classified_later(self):
        self.monitor.onPlayBackStopped()
        self.assertTrue(service.load_discovery_state()["pending_player_stop"])

        fake_kodi.Player().stop()
        state = self.tick(2)
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "player_stop")

    def test_stop_event_during_playlist_transition_is_ignored(self):
        self.monitor.onPlayBackStopped()
        state = self.tick(2)
        self.assertTrue(state["enabled"])
        self.assertFalse(state["pending_player_stop"])

    def test_stop_event_with_restarted_song_moves_back_to_offset(self):
        self.monitor.onPlayBackStopped()
        kodi.player.time = 0.0
        state = self.tick(2)
        self.assertTrue(state["enabled"])
        self.assertEqual(kodi.player.time, float(OFFSET))
        self.assertEqual(state["last_seek_correction_from"], 0)

    def test_events_during_internal_player_change_are_ignored(self):
        service.mark_discovery_internal_player_change(4.0)
        self.monitor.onPlayBackStopped()
        self.monitor.onPlayBackEnded()
        self.monitor.onPlayBackError()
        state = service.load_discovery_state()
        self.assertTrue(state["enabled"])
        self.assertFalse(state.get("pending_player_stop"))
        self.assertFalse(state.get("playlist_change_pending"))

    def test_playback_end_marks_playlist_change(self):
        self.monitor.onPlayBackEnded()
        self.assertTrue(service.load_discovery_state()["playlist_change_pending"])

    def test_playback_error_stops_discovery(self):
        self.monitor.onPlayBackError()
        state = service.load_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertEqual(state["stop_reason"], "player_error")


class SongDurationTest(KodiTestCase):
    def test_duration_from_song_or_song_details(self):
        kodi.library.add_song("D:\\a.mp3", title="A", duration=123)
        self.assertEqual(service.get_song_duration_seconds({"duration": 99}), 99)
        self.assertEqual(service.get_song_duration_seconds({"songid": 1}), 123)
        self.assertEqual(service.get_song_duration_seconds({"songid": 42}), 0)
        self.assertEqual(service.get_song_duration_seconds({}), 0)


class MenuRefreshAndResetTest(KodiTestCase):
    def test_visible_discovery_menu_is_refreshed_once(self):
        service.save_discovery_state({"ui_refresh_requested": True})
        folder = "plugin://plugin.audio.musicip/?action=discovery_mode&nonce=1"
        kodi.info_labels["Container.FolderPath"] = folder
        service.refresh_discovery_menu_if_visible()
        service.refresh_discovery_menu_if_visible()
        self.assertEqual(kodi.builtins, ["Container.Refresh"])  # keeps the focused item

    def test_the_visible_root_follows_discovery(self):
        service.save_discovery_state({"ui_refresh_requested": True})
        kodi.info_labels["Container.FolderPath"] = "plugin://plugin.audio.musicip/"
        service.refresh_discovery_menu_if_visible()
        self.assertEqual(kodi.builtins, ["Container.Refresh"])

    def test_hidden_menu_is_not_refreshed(self):
        service.save_discovery_state({"ui_refresh_requested": True})
        service.refresh_discovery_menu_if_visible()
        self.assertEqual(kodi.builtins, [])
        self.assertTrue(service.load_discovery_state()["ui_refresh_requested"])

    def test_startup_reset(self):
        service.save_discovery_state({"enabled": True, "queue": [{"file": "x"}], "current_song": "x"})
        kodi.playlist.append(("x", None))
        service.reset_discovery_mode_on_startup()
        state = service.load_discovery_state()
        self.assertEqual((state["enabled"], state["stop_reason"], state["queue"]), (False, "startup_reset", []))
        self.assertEqual(kodi.playlist, [])

    def test_playback_path_normalization(self):
        self.assertEqual(service.normalize_discovery_playback_path("D:\\Music\\A%20B.mp3"), "d:/music/a b.mp3")
        self.assertEqual(service.normalize_discovery_playback_path("smb://server//a.mp3"), "smb://server//a.mp3")
        self.assertEqual(service.normalize_discovery_playback_path(""), "")


class ServiceMainLoopTest(KodiTestCase):
    def test_one_loop_iteration_then_abort(self):
        kodi.settings["service_extended_logging"] = "true"
        add_library_songs(3)
        service.save_discovery_state({"enabled": True})  # left over from before a Kodi restart
        service.main()

        self.assertTrue(service.xbmcvfs.exists(service.get_musicip_user_keymap_path()))
        state = service.load_discovery_state()
        self.assertEqual(state["stop_reason"], "startup_reset")
        self.assertFalse(state["enabled"])
        self.assertIn("MusicIP service started. version=", kodi.log_text())
        self.assertEqual(kodi.waits, 1)

    def test_discovery_is_stopped_on_shutdown(self):
        add_library_songs(3)
        kodi.abort_after_waits = 2

        original_tick = service.run_discovery_tick

        def tick_and_start(song_cache):
            if not service.load_discovery_state().get("enabled"):
                self.run_plugin(action="discovery_start")
            return original_tick(song_cache)

        with mock.patch.object(service, "run_discovery_tick", tick_and_start):
            service.main()
        state = service.load_discovery_state()
        self.assertFalse(state["enabled"])
        self.assertFalse(kodi.player.playing)

    def test_tick_errors_do_not_stop_the_service(self):
        with mock.patch.object(service, "run_discovery_tick", side_effect=RuntimeError("boom")):
            service.main()
        self.assertIn("Discovery mode tick failed: boom", kodi.log_text())


if __name__ == "__main__":
    unittest.main()
