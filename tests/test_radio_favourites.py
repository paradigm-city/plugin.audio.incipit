"""Favourite radio stations: saving a station, the list, playing one (always fresh), renaming and removing."""

import os
import unittest
from unittest import mock

from fake_kodi import kodi
from support import main, plugin_query, service
from test_radio_mode import SONGS, RadioTestCase as RadioBase

SONGS_FIRST = SONGS[0]


class FavouriteIconTest(RadioBase):
    def test_icons(self):
        self.start()
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": "D:\\x.mp3"}])
        self.menu()
        icons = {item.getLabel(): os.path.basename(item.getArt("icon")) for _url, item, _folder in kodi.directory_items}
        self.assertEqual(icons["Station information"], "icon-info.png")
        self.assertEqual(icons["Save as favourite station"], "icon-favourite.png")
        self.assertEqual(icons["Favourite stations (1)"], "DefaultFolder.png")
        with mock.patch.object(main, "station_fanart", return_value="image://artist.jpg/"):
            self.menu()
        fanarts = {item.getLabel(): item.getArt("fanart") for _url, item, _folder in kodi.directory_items}
        self.assertEqual(set(fanarts.values()), {"image://artist.jpg/"})  # every entry, the folder too
        kodi.directory_items.clear()
        self.run_plugin(action="radio_favourites")
        self.assertEqual([os.path.basename(item.getArt("icon")) for _url, item, _folder in kodi.directory_items],
                         ["icon-radio.png"])
        (item,) = [item for _url, item, _folder in kodi.directory_items]
        self.assertEqual(item.getMusicInfoTag().getAlbum(), item.getLabel2())  # the second line Kodi keeps


class FavouriteArtworkTest(RadioBase):
    def collages(self, name):
        folder = os.path.join(kodi.root, "art")
        os.makedirs(folder, exist_ok=True)
        cover, fanart = os.path.join(folder, f"{name}.jpg"), os.path.join(folder, f"{name}_fanart.jpg")
        for path in (cover, fanart):
            with open(path, "wb") as handle:
                handle.write(name.encode())
        return cover, fanart

    def test_saving_a_station_keeps_its_most_recent_collage(self):
        self.start()
        cover, fanart = self.collages("now")
        main.save_radio_state(dict(self.radio(), station_cover=cover, station_fanart=fanart))
        self.run_plugin(action="radio_save_favourite")
        (favourite,) = main.load_radio_favourites()
        self.assertEqual(open(favourite["fanart"], "rb").read(), b"now")  # a copy: the station's collage changes
        self.assertTrue(os.path.basename(favourite["cover"]).startswith(f"favourite_{favourite['id']}_"))
        kodi.directory_items.clear()
        self.run_plugin(action="radio_favourites")
        (item,) = [item for _url, item, _folder in kodi.directory_items]
        self.assertEqual((item.getArt("thumb"), item.getArt("fanart")), (favourite["cover"], favourite["fanart"]))
        self.run_plugin(action="radio_favourite_info", id=favourite["id"])
        self.assertEqual(kodi.windows[-1].properties["image"], favourite["fanart"])

    def test_a_playing_favourite_keeps_its_stations_newest_artwork(self):
        self.start()
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": self.radio()["seed"]}])
        main.save_radio_state(dict(self.radio(), favourite_id="f1"))
        first_cover, first_fanart = self.collages("first")
        self.assertTrue(main.save_favourite_artwork("f1", first_cover, first_fanart))
        old = main.find_radio_favourite(favourite_id="f1")["fanart"]
        state = self.radio()
        self.assertEqual(main.station_fanart(state), old)  # no collage of its own yet: the favourite's
        newer = self.collages("newer")
        with mock.patch.object(main, "make_station_collages", return_value={"cover": newer[0], "fanart": newer[1]}):
            self.assertTrue(service.refresh_station_artwork(state))
        favourite = main.find_radio_favourite(favourite_id="f1")
        self.assertEqual(open(favourite["fanart"], "rb").read(), b"newer")
        self.assertFalse(os.path.exists(old))  # its earlier artwork is gone

    def test_removing_a_favourite_removes_its_artwork(self):
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": "D:\a.mp3"}])
        main.save_favourite_artwork("f1", *self.collages("x"))
        artwork = main.find_radio_favourite(favourite_id="f1")["fanart"]
        kodi.respond("yesno", True)
        self.run_plugin(action="radio_remove_favourite", id="f1")
        self.assertFalse(os.path.exists(artwork))


class FavouriteInfoTest(RadioBase):
    def test_information_shows_the_station_not_a_music_file(self):
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": "D:\\air.mp3", "seed_label": "Air - La femme",
                                     "intent": "dreamy downtempo", "saved_ts": 1792000000, "openness": 3, "drift": 2}])
        self.run_plugin(action="radio_favourites")
        (item,) = [item for _url, item, _folder in kodi.directory_items]
        self.assertEqual(item.context_menu[0][0], "Information")
        self.assertEqual(item.getMusicInfoTag().getTitle(), "")  # no title: Kodi adds no "Information" for a music file
        self.run_plugin(action="radio_favourite_info", id="f1")
        window = kodi.windows[-1]
        self.assertEqual((window.properties["heading"], window.properties["facts"]),
                         ("Night Drive", "Favourite station | Open | Wander freely"))
        self.assertTrue(window.properties["text"].startswith("Picked song: Air - La femme"))
        window.onFocus(202)
        self.assertEqual(window.properties["text"], "dreamy downtempo")

    def test_the_info_key_opens_the_favourites_information(self):
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": "D:\\air.mp3"}])
        self.run_plugin(action="radio_favourites")
        (item,) = [item for _url, item, _folder in kodi.directory_items]
        kodi.info_labels["ListItem.Property(MusicIP.InfoAction)"] = item.getProperty("MusicIP.InfoAction")
        self.run_plugin(action="keyboard_info")
        self.assertEqual(kodi.windows[-1].properties["heading"], "Night Drive")

    def test_the_info_key_on_the_radio_entries_opens_the_playing_stations_information(self):
        self.start()
        kodi.directory_items.clear()
        self.run_plugin()  # the first screen
        radio = {item.getLabel(): item for _url, item, _folder in kodi.directory_items}["Radio mode"]
        self.assertEqual(plugin_query(radio.getProperty("MusicIP.InfoAction"))["action"], "radio_info")
        for _url, item, _folder in self.listed("radio_mode"):
            self.assertEqual(plugin_query(item.getProperty("MusicIP.InfoAction"))["action"], "radio_info")
        kodi.info_labels["ListItem.Property(MusicIP.InfoAction)"] = radio.getProperty("MusicIP.InfoAction")
        self.run_plugin(action="keyboard_info")
        self.assertEqual(kodi.windows[-1].properties["tab1"], "Overview")

    def listed(self, action):
        kodi.directory_items.clear()
        self.run_plugin(action=action)
        return list(kodi.directory_items)

    def test_a_removed_favourite(self):
        self.run_plugin(action="radio_favourite_info", id="gone")
        self.assertNotified("This favourite station no longer exists.")


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
                         ["Information", "Openness: Balanced", "Drift: Drift slowly", "Rename", "Remove from favourites"])
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
