"""Radio mode: tuning through snippets, starting the endless station, topping it up and stopping it."""

import glob
import os
import sys
import unittest
from unittest import mock

import fake_kodi
from fake_kodi import kodi
from support import MusicIPServerTestCase, context_radio, main, plugin_query, service

SONGS = [f"D:\\music\\Artist {n}\\Album\\{n:02d} Song {n}.mp3" for n in range(1, 41)]


class RadioTestCase(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        for n, file in enumerate(SONGS, start=1):
            kodi.library.add_song(file, title=f"Song {n}", artist=f"Artist {n}", duration=240)
        # Each seed's mix: the next four library songs, wrapping around, so the station never runs dry.
        for index, seed in enumerate(SONGS):
            self.musicip.set_mix(seed, [SONGS[(index + k) % len(SONGS)] for k in range(1, 5)])

    def radio(self):
        return main.get_radio_state()

    def turn_on(self):
        self.run_plugin(action="radio_on")
        return main.get_discovery_state()["current_song"]

    def start(self):
        seed = self.turn_on()
        self.run_plugin(action="radio_play")
        return seed

    def tick(self, seconds=1):
        self.clock.advance(seconds)
        service.run_radio_tick()
        return self.radio()

    def menu(self):
        kodi.directory_items.clear()
        kodi.directory_calls.clear()
        self.run_plugin(action="radio_mode")
        return self.listed_labels()


class RadioMenuTest(RadioTestCase):
    def test_main_menu_has_radio_mode(self):
        self.run_plugin()
        self.assertIn("Radio mode", self.listed_labels())

    def test_off(self):
        self.assertEqual(self.menu(), ["Scan stations"])
        self.assertIn(("setPluginCategory", "MusicIP radio"), kodi.directory_calls)

    def test_entries_are_actions_not_folders(self):
        self.menu()
        for url, item, is_folder in kodi.directory_items:
            self.assertFalse(is_folder)
            self.assertEqual(item.getProperty("IsPlayable"), "false")
            self.assertEqual(plugin_query(url)["action"], "radio_on")

    def test_tuning_and_playing(self):
        self.turn_on()
        self.assertEqual(self.menu(), ["Pick this station", "Skip station", "Stop radio"])
        snippet = main.get_discovery_state()["current_label"]
        self.assertIn(("setPluginCategory", f"Radio: scanning - {snippet}"), kodi.directory_calls)

        self.run_plugin(action="radio_play")
        self.assertEqual(self.menu(), ["Scan again", "Stop radio"])
        self.assertIn(("setPluginCategory", f"Radio: {self.radio()['current_label']}"), kodi.directory_calls)


class TuningTest(RadioTestCase):
    def test_turn_on_plays_snippets(self):
        self.turn_on()
        self.assertEqual(self.radio()["phase"], "seeking")
        discovery = main.get_discovery_state()
        self.assertTrue(discovery["enabled"])
        self.assertEqual(discovery["owner"], "radio")
        self.assertEqual(kodi.player.time, float(discovery["queue"][0]["offset"]))
        self.assertNotified("Scanning stations.")
        self.assertEqual(plugin_query(kodi.builtins[-1])["action"], "radio_mode")

    def test_turn_on_without_songs(self):
        kodi.library.songs.clear()
        self.turn_on()
        self.assertEqual((self.radio()["phase"], self.radio()["stop_reason"]), ("off", "tuning_failed"))

    def test_next_station(self):
        self.turn_on()
        self.run_plugin(action="radio_tune")
        self.assertEqual(kodi.player.position, 1)
        self.assertEqual(main.get_discovery_state()["current_playlist_position"], 1)
        self.assertEqual(self.radio()["phase"], "seeking")

    def test_tuning_ends_when_its_snippets_stop(self):
        self.turn_on()
        state = main.get_discovery_state()
        state.update({"enabled": False, "stop_reason": "player_stop"})
        main.save_discovery_state(state)
        radio = self.tick(service.RADIO_STOP_GRACE_SECONDS)
        self.assertEqual((radio["phase"], radio["stop_reason"]), ("off", "player_stop"))
        self.assertTrue(radio["ui_refresh_requested"])

    def test_tuning_is_given_time_to_start(self):
        # The plugin marks the radio as tuning just before it starts the snippets.
        main.save_radio_state({"phase": "seeking", "tuning_started_ts": int(self.clock.now)})
        self.assertEqual(self.tick()["phase"], "seeking")
        self.assertEqual(self.tick(service.RADIO_STOP_GRACE_SECONDS)["phase"], "off")


class StartRadioTest(RadioTestCase):
    def test_start_plays_the_station_without_a_dialog(self):
        kodi.settings.update({"playlist_size": "10", "mix_style_preference": "5", "mix_variety": "3"})
        seed = self.start()

        self.assertEqual(kodi.dialog_calls, [])
        query = self.musicip.mix_requests()[0]
        self.assertEqual((query["song"], query["size"], query["style"], query["variety"]), (seed, "10", "100", "3"))

        radio = self.radio()
        self.assertEqual(radio["phase"], "playing")
        index = SONGS.index(seed)
        expected = [seed] + [SONGS[(index + k) % len(SONGS)] for k in range(1, 5)]
        self.assertEqual(kodi.playlist_files(), expected)
        self.assertEqual([entry["file"] for entry in radio["queue"]], expected)
        self.assertEqual((kodi.player.position, kodi.player.file), (0, seed))
        self.assertEqual(radio["seeds"], [seed])
        self.assertNotified("Station picked.")

        discovery = main.get_discovery_state()
        self.assertEqual((discovery["enabled"], discovery["stop_reason"]), (False, "radio_started"))

    def test_labels_have_no_numbers_and_no_snippet_title(self):
        seed = self.start()
        index = SONGS.index(seed)
        first = self.radio()["queue"][0]["label"]
        self.assertFalse(first[:1].isdigit())
        self.assertNotIn(" - Artist ", first)  # not the snippet's "Artist - Title" player title
        self.assertEqual(kodi.playlist[0][1].getLabel(), first)
        self.assertEqual(first, f"Artist {index + 1} - Song {index + 1}")  # from the library

    def test_station_is_not_saved_as_a_recent_mix(self):
        self.start()
        self.assertEqual(glob.glob(os.path.join(main.get_profile_dir(), "mix_*.m3u")), [])

    def test_server_error_keeps_tuning(self):
        self.turn_on()
        self.musicip.mix_status = 500
        self.run_plugin(action="radio_play")
        self.assertEqual(self.radio()["phase"], "seeking")
        discovery = main.get_discovery_state()
        self.assertTrue(discovery["enabled"])
        self.assertFalse(discovery["mix_dialog_active"])
        self.assertNotified("Radio could not start: MusicIP server returned HTTP 500.")

    def test_start_only_while_tuning(self):
        self.run_plugin(action="radio_play")
        self.assertEqual(self.musicip.mix_requests(), [])
        self.assertEqual(self.radio().get("phase", "off"), "off")


class StartFromAnySongTest(RadioTestCase):
    """"Start MusicIP radio" from the library context menu: plugin action radio_start_seed."""

    def start_from(self, seed):
        self.run_plugin(action="radio_start_seed", seed=seed)
        return self.radio()

    def test_starts_a_station_without_tuning(self):
        kodi.settings["playlist_size"] = "10"
        radio = self.start_from(SONGS[5])
        self.assertEqual(radio["phase"], "playing")
        self.assertEqual(radio["seeds"], [SONGS[5]])
        self.assertEqual(kodi.playlist_files()[0], SONGS[5])
        self.assertEqual((kodi.player.position, kodi.player.file), (0, SONGS[5]))
        self.assertEqual(self.musicip.mix_requests()[0]["size"], "10")
        self.assertEqual(kodi.dialog_calls, [])
        self.assertNotified("Station picked.")
        self.assertFalse(main.get_discovery_state().get("enabled"))

    def test_the_current_view_stays(self):
        self.start_from(SONGS[5])
        self.assertFalse([command for command in kodi.builtins if command.startswith("Container.Update(")])
        self.assertTrue(self.radio()["ui_refresh_requested"])  # an open Radio screen is refreshed

    def test_replaces_a_discovery_session(self):
        self.run_plugin(action="discovery_start")
        radio = self.start_from(SONGS[5])
        discovery = main.get_discovery_state()
        self.assertEqual((discovery["enabled"], discovery["stop_reason"]), (False, "radio_started"))
        self.assertEqual(kodi.playlist_files()[0], SONGS[5])
        self.assertEqual(radio["phase"], "playing")

    def test_replaces_the_radio_while_tuning(self):
        self.turn_on()
        self.start_from(SONGS[5])
        self.assertEqual(self.radio()["phase"], "playing")
        self.assertEqual(main.get_discovery_state()["stop_reason"], "radio_started")

    def test_replaces_a_playing_station(self):
        first_seed = self.start()
        started_ts = self.radio()["started_ts"]
        self.clock.advance(60)
        new_seed = SONGS[(SONGS.index(first_seed) + 20) % len(SONGS)]
        radio = self.start_from(new_seed)
        self.assertEqual(radio["seeds"], [new_seed])
        self.assertEqual(radio["started_ts"], started_ts)
        self.assertEqual(kodi.playlist_files()[0], new_seed)
        self.assertEqual(self.tick()["phase"], "playing")

    def test_new_station_is_not_mistaken_for_other_playback(self):
        self.start()
        # The service may look before Kodi has switched to the new station's first song.
        main.save_radio_state(dict(self.radio(), queue=[{"file": SONGS[30], "label": "x"}], playing_started_ts=int(self.clock.now)))
        self.assertEqual(self.tick()["phase"], "playing")
        self.assertEqual(self.tick(service.RADIO_STOP_GRACE_SECONDS)["stop_reason"], "external_playback")

    def test_from_the_context_menu_entry(self):
        with mock.patch.object(sys, "listitem", self.selected(SONGS[7]), create=True):
            context_radio.main()
        self.run_plugin(**plugin_query(kodi.builtins[-1]))
        self.assertEqual(self.radio()["seeds"], [SONGS[7]])
        self.assertEqual(kodi.player.file, SONGS[7])

    def selected(self, url):
        item = fake_kodi.ListItem("song")
        item.getMusicInfoTag().setURL(url)
        return item

    def test_server_error_changes_nothing(self):
        self.musicip.mix_status = 500
        self.start_from(SONGS[5])
        self.assertEqual(self.radio().get("phase", "off"), "off")
        self.assertEqual(kodi.playlist, [])
        self.assertNotified("Radio could not start: MusicIP server returned HTTP 500.")

    def test_no_seed(self):
        self.run_plugin(action="radio_start_seed")
        self.assertNotified("No song was supplied to start the radio from.")
        self.assertEqual(self.musicip.mix_requests(), [])


class ChangeStationTest(RadioTestCase):
    def test_change_station_goes_back_to_tuning(self):
        seed = self.start()
        started_ts = self.radio()["started_ts"]
        self.tick(30)
        self.run_plugin(action="radio_retune")

        radio = self.radio()
        self.assertEqual(radio["phase"], "seeking")
        self.assertEqual(radio["started_ts"], started_ts)
        self.assertEqual(radio["tuning_started_ts"], int(self.clock.now))
        discovery = main.get_discovery_state()
        self.assertEqual((discovery["enabled"], discovery["owner"]), (True, "radio"))
        self.assertEqual(kodi.playlist_files(), [entry["file"] for entry in discovery["queue"]])
        self.assertEqual(kodi.player.time, float(discovery["queue"][0]["offset"]))
        self.assertNotified("Scanning stations.")
        self.assertEqual(self.menu(), ["Pick this station", "Skip station", "Stop radio"])

    def test_new_station_after_changing(self):
        self.start()
        self.run_plugin(action="radio_retune")
        self.run_plugin(action="radio_tune")
        new_seed = main.get_discovery_state()["current_song"]
        self.run_plugin(action="radio_play")
        radio = self.radio()
        self.assertEqual(radio["phase"], "playing")
        self.assertEqual(radio["seeds"], [new_seed])
        self.assertEqual(kodi.playlist_files()[0], new_seed)

    def test_service_keeps_the_radio_while_tuning_again(self):
        self.start()
        self.run_plugin(action="radio_retune")
        for _ in range(5):
            radio = self.tick()
        self.assertEqual(radio["phase"], "seeking")

    def test_change_station_only_while_playing(self):
        self.run_plugin(action="radio_retune")
        self.assertEqual(self.radio().get("phase", "off"), "off")
        self.assertFalse(kodi.player.playing)


class StopRadioTest(RadioTestCase):
    def test_stop_while_tuning(self):
        self.turn_on()
        self.run_plugin(action="radio_stop")
        self.assertEqual((self.radio()["phase"], self.radio()["stop_reason"]), ("off", "manual_stop"))
        self.assertFalse(main.get_discovery_state()["enabled"])
        self.assertFalse(kodi.player.playing)
        self.assertNotified("Radio stopped.")

    def test_stop_while_playing(self):
        self.start()
        self.run_plugin(action="radio_stop")
        self.assertEqual(self.radio()["phase"], "off")
        self.assertFalse(kodi.player.playing)
        self.assertEqual(kodi.playlist, [])

    def test_player_stop_stops_the_radio(self):
        self.start()
        self.tick(5)
        fake_kodi.Player().stop()
        self.assertEqual(self.tick()["phase"], "playing")  # not yet: could be the gap between songs
        radio = self.tick(3)
        self.assertEqual((radio["phase"], radio["stop_reason"]), ("off", "player_stop"))
        self.assertTrue(radio["ui_refresh_requested"])

    def test_short_gap_between_songs_does_not_stop(self):
        self.start()
        self.tick(5)
        kodi.player.playing = False
        self.tick()
        kodi.player.playing = True
        self.tick(5)
        self.assertEqual(self.radio()["phase"], "playing")
        self.assertEqual(self.radio()["not_playing_since"], 0)

    def test_pause_does_not_stop(self):
        # Kodi reports a paused player as playing audio.
        self.start()
        for _ in range(10):
            self.tick(5)
        self.assertEqual(self.radio()["phase"], "playing")

    def test_other_playback_stops_the_radio_but_keeps_playing(self):
        self.start()
        self.tick(service.RADIO_STOP_GRACE_SECONDS)
        kodi.play_file("D:\\music\\Elsewhere\\song.mp3")
        radio = self.tick()
        self.assertEqual((radio["phase"], radio["stop_reason"]), ("off", "external_playback"))
        self.assertTrue(kodi.player.playing)

    def test_kodi_restart_switches_the_radio_off(self):
        main.save_radio_state({"phase": "playing", "queue": []})
        service.reset_radio_mode_on_startup()
        self.assertEqual((self.radio()["phase"], self.radio()["stop_reason"]), ("off", "startup_reset"))


class StationTest(RadioTestCase):
    def test_no_top_up_while_enough_songs_remain(self):
        self.start()
        self.tick()
        self.assertEqual(len(self.musicip.mix_requests()), 1)

    def test_tops_up_from_the_last_queued_song(self):
        self.start()
        kodi.go_to(3)  # one song left after this one
        radio = self.tick()
        last_before = radio["seeds"][-1]
        self.assertEqual(self.musicip.mix_requests()[-1]["song"], last_before)
        self.assertEqual(len(radio["queue"]), 9)
        self.assertEqual(kodi.playlist_files(), [entry["file"] for entry in radio["queue"]])
        self.assertEqual(len(set(kodi.playlist_files())), 9)  # nothing repeats
        self.assertFalse(kodi.playlist[-1][1].getLabel()[:1].isdigit())

    def test_songs_are_labelled_with_their_artists(self):
        self.start()
        kodi.go_to(3)
        radio = self.tick()  # adds songs the metadata cache has never seen
        labels = [entry["label"] for entry in radio["queue"]]
        self.assertTrue(all(label.startswith("Artist ") for label in labels), labels)
        self.assertEqual([item.getLabel() for _url, item in kodi.playlist], labels)

    def test_current_song_is_tracked(self):
        self.start()
        kodi.go_to(2)
        radio = self.tick()
        self.assertEqual(radio["current_position"], 2)
        self.assertEqual(radio["current_song"], kodi.player.file)
        self.assertEqual(radio["current_label"], kodi.playlist[2][1].getLabel())

    def test_empty_mix_tries_an_earlier_song(self):
        self.start()
        last, before = self.radio()["queue"][-1]["file"], self.radio()["queue"][-2]["file"]
        self.musicip.set_mix(last, [])
        kodi.go_to(3)
        radio = self.tick()
        self.assertEqual([query["song"] for query in self.musicip.mix_requests()[1:]], [last, before])
        self.assertEqual(radio["seeds"][-1], before)
        self.assertGreater(len(radio["queue"]), 5)

    def test_nothing_new_waits_before_retrying(self):
        seed = self.start()
        for file in [entry["file"] for entry in self.radio()["queue"]]:
            self.musicip.set_mix(file, [seed])  # only songs already heard
        kodi.go_to(3)
        radio = self.tick()
        self.assertEqual(len(self.musicip.mix_requests()), 1 + service.RADIO_REFILL_SEEDS)
        self.assertGreater(radio["next_refill_ts"], int(self.clock.now))

        self.tick(10)
        self.assertEqual(len(self.musicip.mix_requests()), 1 + service.RADIO_REFILL_SEEDS)
        self.tick(service.RADIO_REFILL_RETRY_SECONDS)
        self.assertGreater(len(self.musicip.mix_requests()), 1 + service.RADIO_REFILL_SEEDS)

    def test_server_error_waits_before_retrying(self):
        self.start()
        self.musicip.mix_status = 500
        kodi.go_to(3)
        radio = self.tick()
        self.assertEqual(len(self.musicip.mix_requests()), 2)  # no further seeds tried
        self.assertGreater(radio["next_refill_ts"], int(self.clock.now))
        self.assertEqual(radio["phase"], "playing")

    def test_old_songs_are_removed_from_the_playlist(self):
        self.start()
        for _ in range(14):
            kodi.go_to(len(kodi.playlist) - 1)
            self.tick()
        radio = self.radio()
        self.assertLessEqual(kodi.player.position, service.RADIO_BACKLOG_SIZE)
        self.assertEqual(kodi.playlist_files(), [entry["file"] for entry in radio["queue"]])
        self.assertEqual(radio["current_position"], kodi.player.position)


class RadioServiceIntegrationTest(RadioTestCase):
    def test_visible_radio_screen_is_refreshed_once(self):
        main.save_radio_state({"phase": "off", "ui_refresh_requested": True})
        folder = "plugin://plugin.audio.musicip/?action=radio_mode&nonce=1"
        kodi.info_labels["Container.FolderPath"] = folder
        service.refresh_radio_menu_if_visible()
        service.refresh_radio_menu_if_visible()
        self.assertEqual(kodi.builtins, [f"Container.Update({folder},replace)"])

    def test_hidden_radio_screen_is_not_refreshed(self):
        main.save_radio_state({"phase": "off", "ui_refresh_requested": True})
        service.refresh_radio_menu_if_visible()
        self.assertEqual(kodi.builtins, [])

    def test_service_loop_runs_the_radio(self):
        self.start()
        fake_kodi.Player().stop()
        kodi.abort_after_waits = 6

        def wait_one_second(monitor, timeout=0):
            self.clock.advance(1)
            kodi.waits += 1
            return kodi.waits >= kodi.abort_after_waits

        with mock.patch.object(service.xbmc.Monitor, "waitForAbort", side_effect=wait_one_second, autospec=True):
            with mock.patch.object(service, "reset_radio_mode_on_startup"):
                service.main()
        self.assertEqual((self.radio()["phase"], self.radio()["stop_reason"]), ("off", "player_stop"))

    def test_missing_file_search_waits_while_the_radio_is_on(self):
        self.turn_on()
        self.assertTrue(service.radio_is_active())
        kodi.add_media(SONGS[0])
        cache_path = self.save_mix([SONGS[0], "D:\\music\\gone\\gone.mp3"])
        state = main.get_discovery_state()
        state["enabled"] = False  # only the radio is on
        main.save_discovery_state(state)
        service.run_consistency_check()
        self.assertNotIn("missing_file_search", self.read_json(main.mix_meta_path_from_cache_path(cache_path)))


if __name__ == "__main__":
    unittest.main()
