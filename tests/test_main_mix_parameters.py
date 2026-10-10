"""Plugin settings and MusicIP mix parameters: defaults, clamping, the confirmation dialog, query building."""

import unittest
from urllib.parse import parse_qs

from fake_kodi import kodi
from support import KodiTestCase, main


class SettingsTest(KodiTestCase):
    def test_defaults_come_from_settings_xml(self):
        self.assertEqual(main.get_server_host(), "localhost")
        self.assertEqual(main.get_server_port(), 10002)
        self.assertEqual(main.get_playlist_size(), 20)
        self.assertEqual(main.get_timeout(), 10)
        self.assertEqual(main.get_mix_style_preference(), 2)
        self.assertEqual(main.get_mix_variety(), 0)
        self.assertEqual(main.get_mix_reject_size(), 0)
        self.assertEqual(main.get_mix_filter(), "")
        self.assertFalse(main.get_mix_genre_enabled())
        self.assertEqual(main.get_discovery_excerpt_seconds(), 20)
        self.assertEqual(main.get_discovery_offset_percent(), 33)

    def test_empty_or_invalid_values_fall_back(self):
        kodi.settings.update({"host": "  ", "port": "abc", "playlist_size": ""})
        self.assertEqual(main.get_server_host(), "localhost")
        self.assertEqual(main.get_server_port(), 10002)
        self.assertEqual(main.get_playlist_size(), 20)

    def test_values_are_clamped(self):
        cases = [
            ("playlist_size", "0", main.get_playlist_size, 1),
            ("timeout", "-5", main.get_timeout, 1),
            ("mix_style_preference", "15", main.get_mix_style_preference, 10),
            ("mix_style_preference", "-1", main.get_mix_style_preference, 0),
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
                kodi.settings["mix_genre"] = value
                self.assertIs(main.get_mix_genre_enabled(), expected)

    def test_style_labels(self):
        self.assertEqual(main.get_mix_style_label(0), "ignore")
        self.assertEqual(main.get_mix_style_label(10), "strongly prefer")
        self.assertEqual(main.get_mix_style_label(42), "strongly prefer")
        self.assertEqual(main.get_mix_style_label(), "weak preference")
        self.assertEqual(main.get_mix_style_api_value(), 40)


class MixParametersTest(KodiTestCase):
    def test_effective_parameters_from_settings(self):
        kodi.settings.update({
            "playlist_size": "30", "mix_style_preference": "5", "mix_variety": "3",
            "mix_genre": "true", "mix_filter": " jazz ", "mix_reject_size": "4",
        })
        self.assertEqual(main.get_effective_mix_parameters(), {
            "size": 30, "sizetype": "tracks", "style": 100, "style_ui": 5,
            "style_label": "medium preference", "variety": 3, "mixgenre": True,
            "filter": "jazz", "rejectsize": 4, "rejecttype": "tracks", "content": "text",
        })
        self.assertEqual(main.get_effective_mix_parameters(size_override=7)["size"], 7)

    def test_normalize_clamps_and_fills(self):
        normalized = main.normalize_mix_parameters({"size": 500, "style_ui": 12, "variety": -3, "rejectsize": 99, "filter": None})
        self.assertEqual(normalized["size"], 100)
        self.assertEqual((normalized["style_ui"], normalized["style"]), (10, 200))
        self.assertEqual(normalized["variety"], 0)
        self.assertEqual(normalized["rejectsize"], 20)
        self.assertEqual(normalized["filter"], "")
        self.assertEqual(main.normalize_mix_parameters({})["size"], 20)

    def test_compact_parameters_keep_only_known_keys(self):
        compact = main.compact_mix_generation_parameters({"size": 5, "style_ui": 1, "extra": "x"})
        self.assertNotIn("extra", compact)
        self.assertEqual(compact["style_label"], "barely noticeable")

    def test_parameters_are_remembered_once_per_seed_and_size(self):
        main.remember_mix_generation_parameters("seed.mp3", 20, {"size": 20, "style_ui": 3})
        self.assertEqual(main.pop_mix_generation_parameters("seed.mp3", 20)["style_ui"], 3)
        self.assertEqual(main.pop_mix_generation_parameters("seed.mp3", 20), {})

    def test_summary(self):
        summary = main.build_mix_parameter_summary({"size": 25, "style_ui": 4, "rejectsize": 3, "mixgenre": True})
        self.assertIn("Size: 25 tracks", summary)
        self.assertIn("Style: 4/10 - mild preference", summary)
        self.assertIn("MusicIP style value: 80", summary)
        self.assertIn("Restrict to seed genre: yes", summary)
        self.assertIn("Filter: <none>", summary)
        self.assertIn("Artist repeat: do not repeat artist within 3 tracks", summary)


class ParameterQueryTest(KodiTestCase):
    def query(self, seed, **params):
        query = main.build_musicip_parameter_query(seed, params)
        return query, {key: values[0] for key, values in parse_qs(query, encoding="iso-8859-1").items()}

    def test_seed_is_encoded_as_iso_8859_1(self):
        raw, parsed = self.query("D:\\Musik\\Motörhead\\Ace.mp3", size=10)
        self.assertTrue(raw.startswith("song=D%3A%5CMusik%5CMot%F6rhead%5CAce.mp3&"))
        self.assertEqual(parsed["song"], "D:\\Musik\\Motörhead\\Ace.mp3")

    def test_optional_parameters(self):
        _raw, parsed = self.query("a.mp3", size=10, style_ui=2, variety=4)
        self.assertEqual(parsed, {
            "song": "a.mp3", "size": "10", "sizeType": "tracks", "style": "40",
            "variety": "4", "mixgenre": "false", "content": "text",
        })

        _raw, parsed = self.query("a.mp3", size=10, mixgenre=True, filter="Rock", rejectsize=5)
        self.assertEqual(parsed["mixgenre"], "true")
        self.assertEqual(parsed["filter"], "Rock")
        self.assertEqual((parsed["rejectsize"], parsed["rejectType"]), ("5", "tracks"))

    def test_server_urls(self):
        kodi.settings.update({"host": "musicip.local", "port": "1234"})
        self.assertEqual(main.build_musicip_reload_url(), "http://musicip.local:1234/server/reload")
        self.assertTrue(main.build_musicip_url("a.mp3", 5).startswith("http://musicip.local:1234/api/mix?song=a.mp3&size=5&"))


class ConfirmMixGenerationDialogTest(KodiTestCase):
    def test_generate_immediately(self):
        kodi.respond("select", 0)
        params = main.confirm_mix_generation(main.get_effective_mix_parameters())
        self.assertEqual(params["size"], 20)
        _method, (heading, choices), _kwargs = kodi.dialogs("select")[0]
        self.assertEqual(heading, "Generate MusicIP mix")
        self.assertEqual(choices[0], "Generate mix")
        self.assertEqual(choices[1], "Size: 20 tracks")

    def test_cancel(self):
        self.assertIsNone(main.confirm_mix_generation({}))

    def test_edit_each_parameter_then_generate(self):
        # Kodi has no Dialog.slider(), so numeric input is used for numbers.
        kodi.respond("select", 1, 2, 3, 4, 5, 6, 0)
        kodi.respond("numeric", "35", "7", "4", "12")
        kodi.respond("input", "  genre:Rock ")
        params = main.confirm_mix_generation(main.get_effective_mix_parameters())
        self.assertEqual(params["size"], 35)
        self.assertEqual((params["style_ui"], params["style"]), (7, 140))
        self.assertEqual(params["variety"], 4)
        self.assertTrue(params["mixgenre"])
        self.assertEqual(params["filter"], "genre:Rock")
        self.assertEqual(params["rejectsize"], 12)
        self.assertEqual(kodi.dialogs("select")[-1][1][1][6], "Artist repeat: do not repeat artist within 12 tracks")

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

    @unittest.expectedFailure
    def test_cancelling_the_filter_input_keeps_the_filter(self):
        # Known issue: Kodi's Dialog.input() returns "" when cancelled, and edit_mix_generation_parameter()
        # only ignores None, so cancelling clears the filter. Remove expectedFailure once fixed.
        kodi.respond("input", "")
        params = main.edit_mix_generation_parameter({"filter": "genre:Rock"}, 5)
        self.assertEqual(params["filter"], "genre:Rock")


if __name__ == "__main__":
    unittest.main()
