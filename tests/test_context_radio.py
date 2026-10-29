"""The "Start MusicIP radio" entry in Kodi's library context menu (context_radio.py)."""

import os
import runpy
import sys
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR, ListItem, kodi
from support import KodiTestCase, context_radio, plugin_query

SONG = "D:\\music\\Motörhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"


def selected_song(url):
    item = ListItem("Ace of Spades")
    item.getMusicInfoTag().setURL(url)
    return item


class ContextRadioTest(KodiTestCase):
    def run_context_item(self, list_item):
        with mock.patch.object(sys, "listitem", list_item, create=True):
            context_radio.main()

    def test_starts_the_radio_as_an_action(self):
        self.run_context_item(selected_song(SONG))
        self.assertEqual(len(kodi.builtins), 1)
        command = kodi.builtins[0]
        # RunPlugin, not ActivateWindow: the radio starts and the current view stays.
        self.assertTrue(command.startswith("RunPlugin(plugin://plugin.audio.incipit/?"))
        self.assertEqual(plugin_query(command), {"action": "radio_start_seed", "seed": SONG})

    def test_song_without_url(self):
        self.run_context_item(selected_song(""))
        self.assertNotified("does not provide a usable song URL")
        self.assertEqual(kodi.builtins, [])

    def test_no_selected_item(self):
        self.run_context_item(None)
        self.assertNotified("Kodi did not provide the selected list item.")
        self.assertEqual(kodi.notifications[0][0], "Incipit")

    def test_script_entry_point(self):
        with mock.patch.object(sys, "listitem", selected_song(SONG), create=True):
            runpy.run_path(os.path.join(ADDON_DIR, "context_radio.py"), run_name="__main__")
        self.assertEqual(plugin_query(kodi.builtins[0])["seed"], SONG)


if __name__ == "__main__":
    unittest.main()
