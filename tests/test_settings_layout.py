"""The settings' layout (Mixing, Radio, Advanced, Logging), Radio's own values and their one-time copy from Mixing's."""

import os
import re
import unittest
from xml.etree import ElementTree

from fake_kodi import ADDON_DIR, kodi
from support import KodiTestCase, main, service
from test_radio_mode import RadioTestCase

SETTINGS = os.path.join(ADDON_DIR, "resources", "settings.xml")
STRINGS = os.path.join(ADDON_DIR, "resources", "language", "resource.language.en_gb", "strings.po")


def categories():
    root = ElementTree.parse(SETTINGS).getroot()
    return {category.get("id"): [setting.get("id") for setting in category.iter("setting")]
            for category in root.iter("category")}


class LayoutTest(unittest.TestCase):
    def test_four_sections(self):
        self.assertEqual(list(categories()), ["mix", "radio", "advanced", "logging"])

    def test_radio_and_mixing_have_their_own_values(self):
        found = categories()
        for setting in ("playlist_size", "mix_variety", "mix_reject_size", "mix_assist_name_mixes",
                        "mix_assist_mix_strictness", "mix_assist_mix_perspective", "discovery_excerpt_seconds"):
            self.assertIn(setting, found["mix"])
        for setting in ("radio_variety", "radio_reject_size", "radio_name_stations", "mix_assist_station_strictness",
                        "mix_assist_station_perspective", "mix_assist_radio_drift", "radio_batch_size", "radio_excerpt_seconds",
                        "radio_offset_percent"):
            self.assertIn(setting, found["radio"])

    def test_the_sound_engine_and_claude_code_are_advanced(self):
        self.assertEqual(categories()["advanced"],
                         ["soundprint_auto_analyse", "soundprint_status", "soundprint_analyse", "soundprint_stop",
                          "soundprint_setup", "soundprint_base_python", "mix_assist_cli_path", "mix_assist_statistics",
                          "mix_assist_statistics_reset"])

    def test_every_label_has_a_text_and_every_text_is_used(self):
        with open(STRINGS, encoding="utf-8") as handle:
            texts = set(re.findall(r'msgctxt "#(\d+)"', handle.read()))
        with open(SETTINGS, encoding="utf-8") as handle:
            used = {a or b for a, b in re.findall(r'(?:label|help)="(\d+)"|<heading>(\d+)</heading>', handle.read())}
        self.assertEqual(used - texts, set())
        self.assertEqual(texts - used, set())

    def test_texts_name_the_section_where_the_sound_engine_is_set_up(self):
        self.assertIn("Settings > Advanced", main.SOUND_ENGINE_SETUP_HINT)


class RadioValuesTest(KodiTestCase):
    def test_a_stations_mixes_use_radios_variety_and_artist_rule(self):
        kodi.settings.update(mix_variety="7", mix_reject_size="2", radio_variety="4", radio_reject_size="6",
                             mix_assist_radio_drift="1")
        self.assertEqual(main.radio_mix_parameters(75), {"size": 75, "variety": 4, "rejectsize": 6})
        self.assertEqual(main.get_effective_mix_parameters()["variety"], 7)  # Mixing keeps its own

    def test_a_station_that_stays_close_still_varies(self):
        kodi.settings.update(radio_variety="0", mix_assist_radio_drift="0")
        self.assertEqual(main.radio_mix_parameters(75)["variety"], main.RADIO_STAY_CLOSE_MIN_VARIETY)

    def test_station_names_have_their_own_switch(self):
        kodi.settings.update(mix_assist_name_mixes="false", radio_name_stations="true")
        self.assertEqual(main.station_name({"name": "Cold Machines"}), "Cold Machines")
        kodi.settings.update(mix_assist_name_mixes="true", radio_name_stations="false")
        self.assertEqual(main.station_name({"name": "Cold Machines"}), "")
        self.assertTrue(main.mix_naming_enabled())


class TuningSnippetsTest(RadioTestCase):
    def test_scan_stations_plays_radios_snippets_discovery_its_own(self):
        kodi.settings.update(discovery_excerpt_seconds="40", discovery_offset_percent="10", radio_excerpt_seconds="8",
                             radio_offset_percent="50")
        self.turn_on()
        discovery = main.get_discovery_state()
        self.assertEqual((discovery["owner"], discovery["excerpt_seconds"], discovery["offset_percent"]),
                         ("radio", 8, 50))
        self.assertEqual((main.get_discovery_excerpt_seconds(), main.get_discovery_offset_percent()), (40, 10))


class MigrationTest(KodiTestCase):
    def stored(self, **values):
        """The add-on's stored settings.xml as Kodi writes it: (value, Kodi's default) per setting."""
        root = ElementTree.Element("settings", version="2")
        for setting, (value, default) in values.items():
            node = ElementTree.SubElement(root, "setting", id=setting)
            node.text = value
            if default:
                node.set("default", "true")
        os.makedirs(kodi.profile_dir(), exist_ok=True)
        ElementTree.ElementTree(root).write(os.path.join(kodi.profile_dir(), "settings.xml"), encoding="utf-8")

    def test_radio_takes_over_the_values_it_shared_once(self):
        self.stored(mix_variety=("9", False), mix_reject_size=("6", False), mix_assist_name_mixes=("true", True),
                    discovery_excerpt_seconds=("15", False), discovery_offset_percent=("25", False),
                    radio_variety=("0", True))
        copied = service.migrate_radio_settings()
        self.assertEqual(copied, {"radio_variety": "9", "radio_reject_size": "6", "radio_excerpt_seconds": "15",
                                  "radio_offset_percent": "25"})
        self.assertEqual((main.get_radio_variety(), main.get_radio_reject_size(), main.get_radio_excerpt_seconds(),
                          main.get_radio_offset_percent()), (9, 6, 15, 25))
        self.assertIn("Radio's own settings: radio_variety = '9' (from mix_variety)", kodi.log_text())
        kodi.settings["radio_variety"] = "2"
        self.assertEqual(service.migrate_radio_settings(), {})  # only once
        self.assertEqual(main.get_radio_variety(), 2)

    def test_a_radio_value_set_already_is_kept(self):
        self.stored(mix_variety=("9", False), radio_variety=("3", False))
        self.assertEqual(service.migrate_radio_settings(), {})

    def test_nothing_stored_nothing_copied(self):
        self.assertEqual(service.migrate_radio_settings(), {})
        self.assertTrue(os.path.exists(os.path.join(kodi.profile_dir(), service.RADIO_SETTINGS_MIGRATED_MARKER)))


if __name__ == "__main__":
    unittest.main()
