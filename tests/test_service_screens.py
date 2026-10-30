"""The service redraws the first screen (or Mix mode) when a mix starts or stops playing: they show what plays."""

import unittest

from fake_kodi import kodi
from support import KodiTestCase, service

ROOT = "plugin://plugin.audio.incipit/"


class PlaybackRedrawTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        service.PLAYBACK_SEEN["key"] = None
        kodi.info_labels["Container.FolderPath"] = ROOT
        service.refresh_screens_when_playback_changes()  # the first look only remembers

    def play(self, length):
        kodi.player.playing = True
        kodi.info_labels["Playlist.Length(music)"] = str(length)

    def test_a_mix_starting_and_stopping_redraws_the_visible_first_screen(self):
        self.assertEqual(kodi.builtins, [])
        self.play(40)
        service.refresh_screens_when_playback_changes()
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, ["Container.Refresh"])  # once; a refresh keeps the focused item
        kodi.player.playing = False
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, ["Container.Refresh"] * 2)

    def test_mix_mode_is_redrawn_too(self):
        kodi.info_labels["Container.FolderPath"] = f"{ROOT}?action=mix_mode"
        self.play(40)
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, ["Container.Refresh"])

    def test_other_screens_are_left_alone(self):
        kodi.info_labels["Container.FolderPath"] = f"{ROOT}?action=radio_mode"
        self.play(40)
        service.refresh_screens_when_playback_changes()
        kodi.info_labels["Container.FolderPath"] = ROOT  # back on the first screen: Kodi lists it anew anyway
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, [])

    def test_no_redraw_while_kodi_is_loading_a_list(self):
        self.play(40)
        kodi.conditions["Container.IsUpdating"] = True
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, [])  # postponed, not dropped
        kodi.conditions.clear()
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, ["Container.Refresh"])

    def test_the_radio_and_discovery_redraw_themselves(self):
        service.save_radio_state({"phase": "playing"})
        self.play(6)
        service.refresh_screens_when_playback_changes()  # the station starts: its own redraw follows it
        kodi.builtins.clear()
        self.play(12)  # a refill
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, [])
        service.save_radio_state({"phase": "off"})
        service.save_discovery_state({"enabled": True})
        self.play(21)
        service.refresh_screens_when_playback_changes()
        self.assertEqual(kodi.builtins, [])


if __name__ == "__main__":
    unittest.main()
