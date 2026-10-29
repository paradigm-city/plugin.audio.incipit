"""The add-on's ID changed from plugin.audio.musicip to plugin.audio.incipit: the old ID's data is taken over once."""

import json
import os
import unittest

from fake_kodi import kodi
from support import KodiTestCase, main, service

OLD = "plugin.audio.musicip"


class TakeOverTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.old = kodi.translate_path(f"special://profile/addon_data/{OLD}/")
        self.new = kodi.profile_dir()
        os.makedirs(os.path.join(self.old, "soundprint"), exist_ok=True)
        os.makedirs(os.path.join(self.old, "covers"), exist_ok=True)
        self.write(os.path.join(self.old, "settings.xml"),
                   '<settings version="2">\n'
                   '    <setting id="mix_variety">9</setting>\n'
                   '    <setting id="mix_reject_size">6</setting>\n'
                   '    <setting id="playlist_size" default="true">20</setting>\n'
                   '    <setting id="host">musicip.local</setting>\n'
                   '</settings>\n')
        cover = f"C:\\Kodi\\userdata\\addon_data\\{OLD}\\covers\\favourite_1.jpg"
        self.write(os.path.join(self.old, "radio_favourites.json"),
                   json.dumps({"stations": [{"id": "f1", "cover": cover, "url": f"plugin://{OLD}/?action=x"}]}))
        self.write(os.path.join(self.old, "mix_a.m3u.json"),
                   json.dumps({"collage": f"/home/kodi/.kodi/userdata/addon_data/{OLD}/covers/mix_a.jpg"}))
        self.write(os.path.join(self.old, "covers", "favourite_1.jpg"), "jpeg")
        self.write(os.path.join(self.old, "soundprint", "sound.db"), "sound prints")
        self.old_keymap = os.path.join(service.get_kodi_user_keymap_dir(), service.OLD_KEYMAP_FILENAME)
        self.write(self.old_keymap, "<keymap/>")

    @staticmethod
    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, *parts):
        with open(os.path.join(self.new, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_the_old_data_is_copied_once_with_its_paths_and_settings(self):
        done = service.take_over_old_data()
        self.assertEqual(done["copied"], 4)  # every file but settings.xml
        self.assertEqual(self.read("soundprint", "sound.db"), "sound prints")
        self.assertEqual(self.read("covers", "favourite_1.jpg"), "jpeg")
        station = json.loads(self.read("radio_favourites.json"))["stations"][0]
        self.assertEqual(station["cover"], "C:\\Kodi\\userdata\\addon_data\\plugin.audio.incipit\\covers\\favourite_1.jpg")
        self.assertEqual(station["url"], f"plugin://{OLD}/?action=x")  # not a path into the data folder
        self.assertEqual(json.loads(self.read("mix_a.m3u.json"))["collage"],
                         "/home/kodi/.kodi/userdata/addon_data/plugin.audio.incipit/covers/mix_a.jpg")
        self.assertEqual(sorted(done["rewritten"]), ["mix_a.m3u.json", "radio_favourites.json"])
        self.assertEqual(done["settings"], {"mix_variety": "9", "mix_reject_size": "6"})  # not Kodi's defaults,
        self.assertEqual((main.get_mix_variety(), main.get_mix_reject_size()), (9, 6))  # not ones no longer declared
        self.assertNotIn("host", kodi.settings)
        self.assertTrue(done["keymap_removed"])
        self.assertFalse(os.path.exists(self.old_keymap))
        self.assertTrue(os.path.exists(os.path.join(self.old, "soundprint", "sound.db")))  # the old one stays
        self.assertIn("Your MusicIP data is taken over", kodi.notification_messages()[0])
        self.assertIn(f"Took over the data of {OLD}", kodi.log_text())
        self.assertEqual(service.take_over_old_data(), {})  # only once

    def test_the_take_over_comes_before_the_other_migrations(self):
        service.main()
        self.assertTrue(os.path.exists(os.path.join(self.new, service.TAKEN_OVER_MARKER)))
        self.assertEqual(main.get_mix_variety(), 9)

    def test_nothing_to_take_over(self):
        import shutil
        shutil.rmtree(self.old)
        self.assertEqual(service.take_over_old_data(), {})
        self.assertTrue(os.path.exists(self.old_keymap))  # left alone


class OneIdTest(unittest.TestCase):
    def test_every_part_uses_the_same_id(self):
        self.assertEqual(main.ADDON_ID, "plugin.audio.incipit")
        self.assertIs(service.ADDON_ID, main.ADDON_ID)
        from soundprint import state
        self.assertEqual(state.ADDON_ID, main.ADDON_ID)
        self.assertIn(f"plugin://{main.ADDON_ID}/?action=keyboard_more_like_this", main.MUSICIP_KEYMAP_CONTENT)
        self.assertNotIn(OLD, main.MUSICIP_KEYMAP_CONTENT)


if __name__ == "__main__":
    unittest.main()
