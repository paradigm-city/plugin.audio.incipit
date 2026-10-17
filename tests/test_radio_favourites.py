"""Favourite radio stations: saving a station, the list, playing one (always fresh), renaming and removing."""

import os
import unittest

from fake_kodi import kodi
from support import main
from test_radio_mode import SONGS, RadioTestCase as RadioBase

SONGS_FIRST = SONGS[0]


class FavouriteStationsTest(RadioBase):
    def favourites(self):
        return main.load_radio_favourites()

    def save_playing_station(self):
        seed = self.start()
        self.run_plugin(action="radio_save_favourite")
        return seed

    def test_saving_the_playing_station(self):
        seed = self.save_playing_station()
        (favourite,) = self.favourites()
        self.assertEqual(favourite["seed"], seed)
        self.assertEqual(favourite["name"], self.radio()["events"][0]["seed"])  # no AI name: the picked song
        self.assertNotified(f"Saved as favourite station: {favourite['name']}")
        self.assertEqual(self.radio()["favourite_id"], favourite["id"])
        self.assertEqual(self.menu(), ["Scan again", "Station information", "Favourite stations (1)", "Stop radio"])

    def test_a_station_is_saved_once(self):
        self.save_playing_station()
        state = self.radio()
        state["favourite_id"] = ""  # e.g. after it was removed and added again elsewhere
        main.save_radio_state(state)
        self.run_plugin(action="radio_save_favourite")
        self.assertEqual(len(self.favourites()), 1)
        self.assertNotified("Already a favourite")

    def test_the_station_name_becomes_the_favourites_name(self):
        self.start()
        main.save_radio_state(dict(self.radio(), name="Bombastic Heroic Metal"))
        self.run_plugin(action="radio_save_favourite")
        self.assertEqual(self.favourites()[0]["name"], "Bombastic Heroic Metal")

    def test_a_favourite_starts_fresh_from_its_picked_song(self):
        seed = self.save_playing_station()
        favourite = self.favourites()[0]
        kodi.go_to(3)
        self.run_plugin(action="radio_stop")
        requests = len(self.musicip.mix_requests())
        self.run_plugin(action="radio_play_favourite", id=favourite["id"])
        radio = self.radio()
        self.assertEqual((radio["phase"], radio["seed"], radio["favourite_id"], radio["name"]),
                         ("playing", seed, favourite["id"], favourite["name"]))
        self.assertEqual(self.musicip.mix_requests()[requests]["song"], seed)
        self.assertEqual(kodi.player.file, seed)
        self.assertIn(("setPluginCategory", f"Radio: {favourite['name']}"), self.menu_calls())

    def test_opening_a_favourite_shows_progress_at_once(self):
        self.save_playlist_and_stop()
        favourite = self.favourites()[0]
        kodi.dialog_calls.clear()
        self.run_plugin(action="radio_play_favourite", id=favourite["id"])
        calls = [call for call in kodi.dialog_calls if call[0].startswith("progress")]
        self.assertEqual(calls[0], ("progress.create", (f"Opening {favourite['name']}...", ""), {}))
        texts = [call[1][2] for call in calls if call[0] == "progress.update"]
        self.assertEqual([text for text in texts if text in ("MusicIP is mixing", "Starting playback")],
                         ["MusicIP is mixing", "Starting playback"])
        self.assertEqual(calls[-1][0], "progress.close")
        self.assertNotified(f"Playing {favourite['name']}.")

    def save_playlist_and_stop(self):
        self.save_playing_station()
        self.run_plugin(action="radio_stop")

    def menu_calls(self):
        self.menu()
        return kodi.directory_calls

    def test_the_list_and_its_context_menu(self):
        self.save_playing_station()
        self.run_plugin(action="radio_stop")
        self.assertEqual(self.menu(), ["Scan stations", "Favourite stations (1)"])
        kodi.directory_items.clear()
        self.run_plugin(action="radio_favourites")
        (url, item, is_folder), = kodi.directory_items
        self.assertEqual(item.getLabel(), self.favourites()[0]["name"])
        self.assertFalse(is_folder)
        self.assertEqual([label for label, _action in item.context_menu],
                         ["Openness: Balanced", "Drift: Drift slowly", "Rename", "Remove from favourites"])
        self.assertTrue(item.getLabel2().endswith("| Balanced | Drift slowly"))

    def test_a_favourite_keeps_the_settings_it_was_saved_with(self):
        kodi.settings.update({"mix_assist_station_strictness": "3", "mix_assist_radio_drift": "2"})
        self.save_playing_station()
        favourite = self.favourites()[0]
        self.assertEqual((favourite["openness"], favourite["drift"]), (3, 2))
        self.assertEqual(self.radio()["settings"], {"openness": 3, "drift": 2})

    def test_changing_a_favourites_settings(self):
        self.save_playing_station()
        favourite_id = self.favourites()[0]["id"]
        kodi.respond("select", 0)  # Focused
        self.run_plugin(action="radio_favourite_setting", id=favourite_id, setting="openness")
        self.assertEqual(self.favourites()[0]["openness"], 0)
        self.assertEqual(self.radio()["settings"]["openness"], 0)  # the playing favourite follows
        kodi.respond("select", 2)  # Wander freely
        self.run_plugin(action="radio_favourite_setting", id=favourite_id, setting="drift")
        self.assertEqual(self.favourites()[0]["drift"], 2)
        self.assertEqual(kodi.dialogs("select")[-1][1][0], f"Drift of {self.favourites()[0]['name']}")

    def test_older_favourites_follow_the_global_settings(self):
        main.save_radio_favourites([{"id": "old", "name": "Old", "seed": SONGS_FIRST}])
        kodi.settings["mix_assist_station_strictness"] = "4"
        self.assertEqual(main.favourite_setting_labels(self.favourites()[0]), ("Adventurous", "Drift slowly"))
        self.assertEqual(main.favourite_settings(self.favourites()[0]), {})

    def test_rename_and_remove(self):
        self.save_playing_station()
        favourite_id = self.favourites()[0]["id"]
        kodi.respond("keyboard", "  Night   Drive ")
        self.run_plugin(action="radio_rename_favourite", id=favourite_id)
        self.assertEqual(self.favourites()[0]["name"], "Night Drive")
        self.assertEqual(self.radio()["name"], "Night Drive")
        kodi.respond("yesno", False)
        self.run_plugin(action="radio_remove_favourite", id=favourite_id)
        self.assertEqual(len(self.favourites()), 1)
        kodi.respond("yesno", True)
        self.run_plugin(action="radio_remove_favourite", id=favourite_id)
        self.assertEqual(self.favourites(), [])
        self.assertEqual(self.radio()["favourite_id"], "")

    def test_picking_a_favourites_song_while_scanning_is_that_favourite(self):
        seed = self.save_playing_station()
        favourite = self.favourites()[0]
        self.run_plugin(action="radio_stop")
        self.run_plugin(action="radio_start_seed", seed=seed)
        self.assertEqual((self.radio()["favourite_id"], self.radio()["name"]), (favourite["id"], favourite["name"]))

    def test_a_missing_favourite(self):
        self.run_plugin(action="radio_play_favourite", id="gone")
        self.assertNotified("This favourite station no longer exists.")
        self.assertFalse(os.path.exists(main.radio_favourites_path()))


if __name__ == "__main__":
    unittest.main()
