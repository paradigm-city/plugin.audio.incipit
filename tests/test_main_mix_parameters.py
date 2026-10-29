"""Plugin settings and mix parameters: defaults, clamping, the confirmation dialog."""

import unittest

import os

from fake_kodi import ADDON_DIR, kodi
from support import KodiTestCase, main


class SettingsTest(KodiTestCase):
    def test_defaults_come_from_settings_xml(self):
        self.assertEqual(main.get_playlist_size(), 20)
        self.assertEqual(main.get_mix_variety(), 0)
        self.assertEqual(main.get_mix_reject_size(), 0)
        self.assertEqual(main.get_discovery_excerpt_seconds(), 20)
        self.assertEqual(main.get_discovery_offset_percent(), 33)

    def test_empty_or_invalid_values_fall_back(self):
        kodi.settings.update({"playlist_size": "", "mix_variety": "abc"})
        self.assertEqual(main.get_playlist_size(), 20)
        self.assertEqual(main.get_mix_variety(), 0)

    def test_values_are_clamped(self):
        cases = [
            ("playlist_size", "0", main.get_playlist_size, 1),
            ("mix_variety", "12", main.get_mix_variety, 9),
            ("mix_reject_size", "50", main.get_mix_reject_size, 20),
            ("discovery_excerpt_seconds", "1", main.get_discovery_excerpt_seconds, 5),
            ("discovery_excerpt_seconds", "600", main.get_discovery_excerpt_seconds, 60),
            ("discovery_offset_percent", "95", main.get_discovery_offset_percent, 90),
        ]
        for setting, value, getter, expected in cases:
            with self.subTest(setting=setting, value=value):
                kodi.settings[setting] = value
                self.assertEqual(getter(), expected)

    def test_bool_settings_accept_common_spellings(self):
        for value, expected in (("true", True), ("1", True), ("YES", True), ("on", True), ("false", False), ("0", False)):
            with self.subTest(value=value):
                kodi.settings["consistency_enabled"] = value
                self.assertIs(main.get_setting_bool("consistency_enabled", False), expected)

    def test_musicips_settings_are_gone(self):
        with open(os.path.join(ADDON_DIR, "resources", "settings.xml"), encoding="utf-8") as handle:
            settings = handle.read()
        for setting in ("host", "port", "timeout", "mix_style_preference", "mix_filter", "suggestion_engine"):
            self.assertNotIn(f'id="{setting}"', settings)


class MixParametersTest(KodiTestCase):
    def test_effective_parameters_from_settings(self):
        kodi.settings.update({"playlist_size": "30", "mix_variety": "3", "mix_reject_size": "4"})
        self.assertEqual(main.get_effective_mix_parameters(), {"size": 30, "variety": 3, "rejectsize": 4})
        self.assertEqual(main.get_effective_mix_parameters(size_override=7)["size"], 7)

    def test_normalize_clamps_and_fills(self):
        normalized = main.normalize_mix_parameters({"size": 500, "variety": -3, "rejectsize": 99, "mixgenre": True})
        self.assertEqual(normalized, {"size": 100, "variety": 0, "rejectsize": 20})
        self.assertEqual(main.normalize_mix_parameters({})["size"], 20)

    def test_compact_parameters_keep_only_known_keys(self):
        compact = main.compact_mix_generation_parameters({"size": 5, "style_ui": 1, "extra": "x"})
        self.assertEqual(compact, {"size": 5, "variety": 0, "rejectsize": 0})

    def test_parameters_are_remembered_once_per_seed_and_size(self):
        main.remember_mix_generation_parameters("seed.mp3", 20, {"size": 20, "variety": 3})
        self.assertEqual(main.pop_mix_generation_parameters("seed.mp3", 20)["variety"], 3)
        self.assertEqual(main.pop_mix_generation_parameters("seed.mp3", 20), {})


class ConfirmMixGenerationDialogTest(KodiTestCase):
    def test_generate_immediately(self):
        kodi.respond("select", 0)
        params = main.confirm_mix_generation(main.get_effective_mix_parameters())
        self.assertEqual(params["size"], 20)
        _method, (heading, choices), _kwargs = kodi.dialogs("select")[0]
        self.assertEqual(heading, "Generate mix")
        self.assertEqual(choices[0], "Generate mix")
        self.assertEqual(choices[1], "Size: 20 tracks")

    def test_cancel(self):
        self.assertIsNone(main.confirm_mix_generation({}))

    def test_edit_each_parameter_then_generate(self):
        # Kodi has no Dialog.slider(), so numeric input is used for numbers.
        kodi.respond("select", 1, 2, 3, 0)
        kodi.respond("numeric", "35", "4", "12")
        params = main.confirm_mix_generation(main.get_effective_mix_parameters())
        self.assertEqual((params["size"], params["variety"], params["rejectsize"]), (35, 4, 12))
        self.assertNotIn("style_ui", params)
        self.assertNotIn("filter", params)
        choices = kodi.dialogs("select")[-1][1][1]
        self.assertEqual(choices[3], "Artist repeat: do not repeat artist within 12 tracks")
        self.assertFalse(any("Style" in choice or "Filter" in choice for choice in choices))

    def test_numeric_input_is_clamped_or_ignored(self):
        kodi.respond("numeric", "500")
        self.assertEqual(main.edit_mix_generation_parameter({"size": 20}, 1)["size"], 100)
        kodi.respond("numeric", "abc")
        self.assertEqual(main.edit_mix_generation_parameter({"size": 20}, 1)["size"], 20)
        kodi.respond("numeric", "")
        self.assertEqual(main.edit_mix_generation_parameter({"size": 20}, 1)["size"], 20)

    def test_slider_is_used_when_available(self):
        main.xbmcgui.Dialog.slider = lambda self, *args, **kwargs: 9
        self.addCleanup(delattr, main.xbmcgui.Dialog, "slider")
        self.assertEqual(main.dialog_slider_int(2, "Variety", 0, 9), 9)
        main.xbmcgui.Dialog.slider = lambda self, *args, **kwargs: 12
        self.assertIsNone(main.dialog_slider_int(2, "Variety", 0, 9))


if __name__ == "__main__":
    unittest.main()
