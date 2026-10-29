"""The "Create MusicIP mix" entry in Kodi's library context menu (context_mix.py)."""

import os
import runpy
import sys
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR, ListItem, kodi
from support import KodiTestCase, context_mix, plugin_query

SONG = "D:\\music\\Motörhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"


def selected_song(url):
    item = ListItem("Ace of Spades")
    item.getMusicInfoTag().setURL(url)
    return item


class ContextMixTest(KodiTestCase):
    def run_context_item(self, list_item):
        with mock.patch.object(sys, "listitem", list_item, create=True):
            context_mix.main()

    def test_opens_mix_for_selected_song(self):
        kodi.settings["playlist_size"] = "25"
        self.run_context_item(selected_song(SONG))
        self.assertEqual(len(kodi.builtins), 1)
        command = kodi.builtins[0]
        self.assertTrue(command.startswith("ActivateWindow(Music,plugin://plugin.audio.incipit/?"))
        self.assertTrue(command.endswith(",return)"))
        self.assertEqual(plugin_query(command), {"action": "browse_mix", "seed": SONG, "size": "25"})

    def test_song_without_url(self):
        self.run_context_item(selected_song(""))
        self.assertNotified("does not provide a usable song URL")
        self.assertEqual(kodi.builtins, [])

    def test_no_selected_item(self):
        self.run_context_item(None)
        self.assertNotified("Kodi did not provide the selected list item.")
        self.assertEqual(kodi.notifications[0][0], "Incipit")

    def test_broken_list_item(self):
        self.run_context_item(object())
        self.assertNotified("did not provide a valid song URL")

    def test_playlist_size_setting(self):
        kodi.settings["playlist_size"] = "abc"
        self.assertEqual(context_mix.get_playlist_size(), 20)
        kodi.settings["playlist_size"] = "-3"
        self.assertEqual(context_mix.get_playlist_size(), 1)

    def test_script_entry_point(self):
        with mock.patch.object(sys, "listitem", selected_song(SONG), create=True):
            runpy.run_path(os.path.join(ADDON_DIR, "context_mix.py"), run_name="__main__")
        self.assertEqual(plugin_query(kodi.builtins[0])["seed"], SONG)


if __name__ == "__main__":
    unittest.main()
