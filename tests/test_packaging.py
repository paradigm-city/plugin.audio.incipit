"""Add-on packaging: addon.xml, settings.xml, entry points, keymap and Python 3.8 compatibility."""

import ast
import os
import re
import unittest
import xml.etree.ElementTree as ET

from fake_kodi import ADDON_DIR, ADDON_ID
from support import logs, main, service

SOURCES = ("main.py", "service.py", "context_mix.py", "context_radio.py")  # the entry points
MODULES = SOURCES + ("logs.py",)


def read(name):
    with open(os.path.join(ADDON_DIR, name), encoding="utf-8") as handle:
        return handle.read()


class AddonXmlTest(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(os.path.join(ADDON_DIR, "addon.xml")).getroot()

    def test_identity(self):
        self.assertEqual(self.root.get("id"), ADDON_ID)
        self.assertRegex(self.root.get("version"), r"^\d+\.\d+\.\d+$")

    def test_entry_point_libraries_exist(self):
        libraries = [node.get("library") for node in self.root.iter() if node.get("library")]
        self.assertEqual(sorted(libraries), sorted(SOURCES))
        for library in libraries:
            self.assertTrue(os.path.isfile(os.path.join(ADDON_DIR, library)), library)

    def test_icon_exists(self):
        icon = self.root.find(".//assets/icon").text
        self.assertTrue(os.path.isfile(os.path.join(ADDON_DIR, icon)))

    def test_version_has_changelog_entry(self):
        self.assertIn(f"## Version {self.root.get('version')}", read("CHANGELOG.md"))


def read_strings():
    """msgctxt number -> msgid of the English strings.po."""
    text = read(os.path.join("resources", "language", "resource.language.en_gb", "strings.po"))
    entries = re.findall(r'msgctxt "#(\d+)"\nmsgid "((?:[^"\\]|\\.)*)"', text)
    return {int(number): re.sub(r"\\(.)", r"\1", message) for number, message in entries}


class SettingsXmlTest(unittest.TestCase):
    def setUp(self):
        self.tree = ET.parse(os.path.join(ADDON_DIR, "resources", "settings.xml"))
        self.settings = {node.get("id"): node for node in self.tree.iter("setting")}

    def test_new_settings_format(self):
        root = self.tree.getroot()
        self.assertEqual((root.tag, root.get("version")), ("settings", "1"))
        self.assertEqual(root.find("section").get("id"), ADDON_ID)

    def test_every_setting_has_a_label_and_a_help_text(self):
        strings = read_strings()
        for setting_id, node in self.settings.items():
            with self.subTest(setting=setting_id):
                self.assertTrue(strings.get(int(node.get("label"))))
                self.assertGreater(len(strings.get(int(node.get("help")), "")), 20)
        for node in self.tree.iter():
            for attribute in ("label", "help"):
                if node.get(attribute):
                    self.assertIn(int(node.get(attribute)), strings, f"{node.tag} {attribute}={node.get(attribute)}")

    def used_setting_ids(self):
        pattern = re.compile(r"""(?:get_setting(?:_bool|_int)?|getSetting)\(\s*["']([a-z_]+)["']""")
        used = {name for source in MODULES for name in pattern.findall(read(source))}
        return used | set(logs.AREAS.values())  # the switches in Settings > Logging

    def test_every_setting_used_in_code_is_declared(self):
        used = self.used_setting_ids()
        self.assertTrue(used)
        self.assertEqual(used - set(self.settings), set())

    def test_every_declared_setting_is_used(self):
        values = {setting_id for setting_id, node in self.settings.items() if node.get("type") != "action"}
        self.assertEqual(values - self.used_setting_ids(), set())

    def test_buttons_run_an_action_of_the_add_on(self):
        buttons = {setting_id: node for setting_id, node in self.settings.items() if node.get("type") == "action"}
        for setting_id, node in buttons.items():
            with self.subTest(setting=setting_id):
                data = node.find("data").text
                self.assertTrue(data.startswith(f"RunPlugin(plugin://{ADDON_ID}/?action="), data)
                action = data.split("action=")[1].rstrip(")")
                self.assertIn(f'action == "{action}"', read("main.py"))

    def test_slider_defaults_are_inside_their_range(self):
        for setting_id, node in self.settings.items():
            if node.find("control").get("type") != "slider":
                continue
            with self.subTest(setting=setting_id):
                low, high = int(node.findtext("constraints/minimum")), int(node.findtext("constraints/maximum"))
                self.assertLessEqual(low, int(node.findtext("default")))
                self.assertLessEqual(int(node.findtext("default")), high)

    def test_code_fallbacks_match_declared_defaults(self):
        pattern = re.compile(r"""get_setting(?:_bool|_int)?\(\s*["']([a-z_]+)["']\s*,\s*([^)]+)\)""")
        for source in MODULES:
            for setting_id, fallback in pattern.findall(read(source)):
                with self.subTest(source=source, setting=setting_id):
                    declared = self.settings[setting_id].findtext("default") or ""
                    fallback = fallback.strip().strip("\"'")
                    self.assertEqual(fallback.lower(), declared.lower())


class KeymapTest(unittest.TestCase):
    def test_plugin_and_service_install_the_same_keymap(self):
        self.assertEqual(main.MUSICIP_KEYMAP_CONTENT, service.MUSICIP_KEYMAP_CONTENT)

    def test_keymap_is_valid_xml_and_targets_known_actions(self):
        root = ET.fromstring(main.MUSICIP_KEYMAP_CONTENT)
        commands = {node.text for node in root.iter() if node.text and node.text.startswith("RunPlugin(")}
        actions = {re.search(r"action=([a-z_]+)", command).group(1) for command in commands}
        self.assertEqual(actions, {"keyboard_remove_from_mix", "keyboard_more_like_this", "keyboard_less_like_this",
                                   "keyboard_info"})
        router_source = read("main.py")
        for action in actions:
            self.assertIn(f'action == "{action}"', router_source)

    def test_shipped_keymap_matches_installed_keymap(self):
        shipped = read(os.path.join("resources", "keymaps", "musicip_mix_editing.xml"))
        self.assertEqual(
            ET.tostring(ET.fromstring(shipped.encode("utf-8"))),
            ET.tostring(ET.fromstring(main.MUSICIP_KEYMAP_CONTENT.encode("utf-8"))),
        )


class PythonCompatibilityTest(unittest.TestCase):
    """Kodi on Windows bundles Python 3.8; the sources must parse there."""

    def test_sources_parse_with_python_3_8_grammar(self):
        for source in MODULES:
            with self.subTest(source=source):
                ast.parse(read(source), filename=source, feature_version=(3, 8))

    def test_annotations_are_postponed(self):
        # list[str] / int | None annotations are only valid on 3.8 with postponed evaluation.
        for source in MODULES:
            with self.subTest(source=source):
                self.assertIn("from __future__ import annotations", read(source))


if __name__ == "__main__":
    unittest.main()
