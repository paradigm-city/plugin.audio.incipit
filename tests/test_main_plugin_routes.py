"""The plugin as Kodi runs it: router() actions, directory listings, context menus and playback."""

import os
import runpy
import sys
import time
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR, kodi
from support import HANDLE, PLUGIN_URL, KodiTestCase, MusicIPServerTestCase, main, plugin_query

SEED = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
T1 = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
T2 = "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"


def item_by_label(label):
    for url, item, is_folder in kodi.directory_items:
        if item.getLabel() == label:
            return url, item, is_folder
    raise AssertionError(f"{label!r} not listed; have {[i.getLabel() for _u, i, _f in kodi.directory_items]}")


class RootIconTest(KodiTestCase):
    def icons(self):
        kodi.directory_items.clear()
        self.run_plugin()
        return {item.getLabel(): os.path.basename(item.getArt("icon")) for _url, item, _folder in kodi.directory_items}

    def test_each_entry_has_its_icon(self):
        self.assertEqual(self.icons(), {
            "Generate mix from playing audio": "icon-generate.png", "Discovery mode": "icon-discovery.png",
            "Radio mode": "icon-radio.png", "Saved mixes": "DefaultFolder.png", "Settings": "icon-settings.png"})
        for _url, item, _folder in kodi.directory_items:
            self.assertEqual(item.getArt("thumb"), item.getArt("icon"))

    def test_the_icons_are_shipped(self):
        media = os.path.join(ADDON_DIR, "resources", "media")
        for name in ("generate", "discovery", "searching", "radio", "playing", "settings", "skip", "stop"):
            self.assertTrue(os.path.isfile(os.path.join(media, f"icon-{name}.png")), name)
        self.assertTrue(os.path.isfile(os.path.join(media, "LICENSE.txt")))  # Font Awesome: CC BY 4.0
        self.assertEqual(main.media_icon("radio"), os.path.join(main.ADDON.getAddonInfo("path"), "resources", "media",
                                                                "icon-radio.png"))

    def test_discovery_searching(self):
        main.save_discovery_state({"enabled": True})
        self.assertEqual(self.icons()["Discovery mode"], "icon-searching.png")

    def test_radio_scanning_and_playing(self):
        main.save_discovery_state({"enabled": True, "owner": "radio"})  # the radio's scan, not Discovery mode
        main.save_radio_state({"phase": "seeking"})
        icons = self.icons()
        self.assertEqual((icons["Discovery mode"], icons["Radio mode"]), ("icon-discovery.png", "icon-searching.png"))
        main.save_discovery_state({})
        main.save_radio_state({"phase": "playing"})
        self.assertEqual(self.icons()["Radio mode"], "icon-playing.png")


class RootAndSettingsTest(KodiTestCase):
    def test_root_menu(self):
        self.run_plugin()
        self.assertEqual(self.listed_labels(), ["Generate mix from playing audio", "Discovery mode", "Radio mode", "Saved mixes", "Settings"])
        self.assertEqual(plugin_query(item_by_label("Saved mixes")[0])["action"], "saved_mixes")
        self.assertEqual(kodi.ended, [{"succeeded": True, "updateListing": False, "cacheToDisc": False}])

    def test_every_run_installs_the_keymap(self):
        self.run_plugin()
        self.assertTrue(os.path.exists(main.get_musicip_user_keymap_path()))

    def test_open_settings(self):
        self.run_plugin(action="open_settings")
        self.assertEqual(kodi.settings_opened, 1)
        self.assertEqual(kodi.builtins[-1], "Container.Refresh")
        self.assertEqual(kodi.ended, [])

    def test_settings_entries_are_actions_not_folders(self):
        # A folder entry makes Kodi expect a listing, which open_settings never returns.
        self.run_plugin()
        for label in ("Settings",):
            with self.subTest(label=label):
                url, item, is_folder = item_by_label(label)
                self.assertFalse(is_folder)
                self.assertEqual(item.getProperty("IsPlayable"), "false")
                self.assertEqual(plugin_query(url)["action"], "open_settings")

    def test_unknown_action(self):
        self.run_plugin(action="frobnicate")
        self.assertNotified("Unknown action: frobnicate")
        self.assertFalse(kodi.ended[-1]["succeeded"])

    def test_script_entry_point_reports_unhandled_errors(self):
        # Generating a mix with nothing playing raises; the __main__ guard turns it into a notification.
        with mock.patch.object(sys, "argv", [PLUGIN_URL, str(HANDLE), "?action=generate_current_mix"]):
            runpy.run_path(os.path.join(ADDON_DIR, "main.py"), run_name="__main__")
        self.assertNotified("No audio is currently playing.")
        self.assertFalse(kodi.ended[-1]["succeeded"])


class SavedMixListingTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        kodi.add_media(SEED)
        kodi.add_media(T1)
        ts = int(time.mktime(time.strptime("2026-10-05 18:30", "%Y-%m-%d %H:%M")))
        self.ok_mix = self.save_mix([SEED, T1], updated_ts=ts)
        self.broken_mix = self.save_mix([T1, T2], updated_ts=ts - 60)
        main.analyze_mix_consistency(self.broken_mix)

    def test_no_saved_mixes(self):
        main.delete_saved_mix_files(self.ok_mix)
        main.delete_saved_mix_files(self.broken_mix)
        self.run_plugin(action="saved_mixes")
        self.assertEqual(self.listed_labels(), ["No saved mixes yet."])

    def test_date_groups_show_warning_count(self):
        self.run_plugin(action="saved_mixes")
        url, item, is_folder = kodi.directory_items[0]
        self.assertEqual(item.getLabel(), "[B][COLOR red]![/COLOR][/B] 2026-10-05 (2 mixes) | 1 warning")
        self.assertTrue(is_folder)
        self.assertEqual(plugin_query(url), {"action": "saved_mixes_by_date", "date": "2026-10-05", "nonce": plugin_query(url)["nonce"]})
        older = plugin_query(item.context_action("Delete mixes from this date and older"))
        self.assertEqual((older["action"], older["older"]), ("cleanup_saved_mixes", "1"))

    def library_still_lists_missing_file(self):
        kodi.library.add_song(T2, title="Motorcycle Man", artist="Saxon", present=False)

    def test_mixes_of_a_date(self):
        self.library_still_lists_missing_file()
        self.run_plugin(action="saved_mixes_by_date", date="2026-10-05")
        ok_url, ok_item, _ = item_by_label("01 Ace of Spades (2 tracks)")
        self.assertEqual(plugin_query(ok_url)["cache_path"], self.ok_mix)
        self.assertEqual(ok_item.getLabel2(), "01 Ace of Spades | 18:30")  # the seed song, the time
        self.assertEqual(ok_item.getProperty("MusicIP.CachePath"), self.ok_mix)
        self.assertIn("Seed: " + SEED, ok_item.getProperty("Plot"))

        _url, broken, _ = item_by_label("[B][COLOR red]![/COLOR][/B] 01 Overkill (2 tracks)")
        self.assertEqual(broken.getProperty("MusicIP.Inconsistent"), "true")
        self.assertEqual(broken.getLabel2(), "01 Overkill | 18:29 | Inconsistent: 1 missing | Update library before repair")
        labels = [label for label, _action in broken.context_menu]
        self.assertEqual(labels, ["Information", "Check consistency", "Update library before repair",
                                  "AI Mix Assist...", "Delete this mix"])

    def test_repair_offered_once_library_no_longer_lists_missing_file(self):
        self.run_plugin(action="saved_mixes_by_date", date="2026-10-05")
        _url, broken, _ = item_by_label("[B][COLOR red]![/COLOR][/B] 01 Overkill (2 tracks)")
        repair = plugin_query(broken.context_action("Auto-repair this mix"))
        self.assertEqual((repair["action"], repair["cache_path"]), ("repair_mix", self.broken_mix))

    def test_missing_or_unknown_date(self):
        self.run_plugin(action="saved_mixes_by_date")
        self.assertNotified("No date was supplied.")
        self.run_plugin(action="saved_mixes_by_date", date="1999-01-01")
        self.assertEqual(self.listed_labels(), ["No saved mixes for this date."])

    def test_cleanup_actions(self):
        self.run_plugin(action="cleanup_saved_mix", cache_path=self.ok_mix)
        self.assertFalse(os.path.exists(self.ok_mix))
        self.assertNotified("Removed mix.")
        self.assertBuiltin(f"Container.Update({PLUGIN_URL}?action=saved_mixes")

        self.run_plugin(action="cleanup_saved_mixes", date="2026-10-05", older="0")
        self.assertFalse(os.path.exists(self.broken_mix))
        self.assertNotified("Removed 1 stored mix(es) from 2026-10-05.")

        self.run_plugin(action="cleanup_saved_mixes")
        self.assertNotified("No date was supplied.")

    def test_check_consistency_action(self):
        self.run_plugin(action="check_mix_consistency", cache_path=self.broken_mix)
        self.assertNotified("Mix inconsistent: 1 missing.")
        self.run_plugin(action="check_mix_consistency", cache_path=self.ok_mix)
        self.assertNotified("Mix consistency OK.")
        self.assertEqual(kodi.builtins.count("Container.Refresh"), 2)

    def test_repair_action_requires_updated_library(self):
        self.library_still_lists_missing_file()
        self.run_plugin(action="repair_mix", cache_path=self.broken_mix)
        self.assertNotified("Update library before repair.")

    def test_repair_action(self):
        kodi.library.add_song("E:\\moved\\01 Motorcycle Man.mp3", title="Motorcycle Man", artist="Saxon")
        self.run_plugin(action="repair_mix", cache_path=self.broken_mix)
        self.assertNotified("Repaired 1 track(s).")
        self.assertEqual(self.read_mix(self.broken_mix), [T1, "E:\\moved\\01 Motorcycle Man.mp3"])

    def test_update_library_action(self):
        self.library_still_lists_missing_file()
        kodi.respond("select", 1)
        self.run_plugin(action="update_library_before_repair", cache_path=self.broken_mix)
        self.assertIn("AudioLibrary.Scan", kodi.jsonrpc_methods())
        self.assertEqual(kodi.builtins[-1], "Container.Refresh")

    def test_actions_without_cache_path(self):
        for action in ("cleanup_saved_mix", "check_mix_consistency", "update_library_before_repair", "repair_mix"):
            with self.subTest(action=action):
                kodi.notifications.clear()
                self.run_plugin(action=action)
                self.assertEqual(len(kodi.notifications), 1)
                self.assertEqual(kodi.notifications[0][2], "error")


class SkinHighlightTest(KodiTestCase):
    def colour_file(self, name, colours):
        folder = os.path.join(kodi.root, "skin", "colors")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{name}.xml"), "w", encoding="utf-8") as handle:
            handle.write("<colors>" + "".join(f'<color name="{key}">{value}</color>' for key, value in colours.items())
                         + "</colors>")

    def test_without_a_skin_colour_a_blue_with_white_text(self):
        self.assertEqual(main.skin_highlight(), (main.DEFAULT_HIGHLIGHT, "FFFFFFFF"))

    def test_a_skin_string_and_its_text_setting(self):
        kodi.info_labels["Skin.String(focuscolor.name)"] = "#0094a6"
        self.assertEqual(main.skin_highlight(), ("FF0094A6", "FF272727"))
        kodi.conditions["Skin.HasSetting(RevertSelectedText)"] = True
        self.assertEqual(main.skin_highlight(), ("FF0094A6", "FFFFFFFF"))
        self.colour_file("defaults", {"accent": "FFAA0000"})
        kodi.info_labels["Skin.String(focuscolor.name)"] = "accent"  # a colour's name
        self.assertEqual(main.skin_highlight()[0], "FFAA0000")

    def test_the_colour_theme_over_the_skins_defaults(self):
        self.colour_file("defaults", {"button_focus": "FF12A0C7", "selected": "FFFFB70F"})
        self.assertEqual(main.skin_highlight(), ("FF12A0C7", "FFFFFFFF"))  # Estuary
        self.colour_file("gold", {"button_focus": "FFF0E68C"})
        kodi.info_labels["Skin.CurrentColourTheme"] = "gold"
        self.assertEqual(main.skin_highlight(), ("FFF0E68C", "FF272727"))  # a light highlight gets dark text
        kodi.info_labels["Skin.CurrentColourTheme"] = "SKINDEFAULT"
        self.assertEqual(main.skin_highlight()[0], "FF12A0C7")

    def test_a_broken_colour_file_is_ignored(self):
        self.colour_file("defaults", {"button_focus": "FF12A0C7"})
        self.colour_file("teal", {})
        with open(os.path.join(kodi.root, "skin", "colors", "teal.xml"), "w", encoding="utf-8") as handle:
            handle.write("<colors><color")
        kodi.info_labels["Skin.CurrentColourTheme"] = "teal"
        self.assertEqual(main.skin_highlight()[0], "FF12A0C7")

    def test_colour_values(self):
        self.assertEqual([main.color_value(text) for text in ("12a0c7", "#8012A0C7", "red", "", None, "12A0C")],
                         ["FF12A0C7", "8012A0C7", "", "", "", ""])


class MixInfoTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        main.remember_mix_generation_parameters(SEED, 2, {"size": 2, "style_ui": 5, "rejectsize": 2})
        self.cache_path = self.save_mix([SEED, T1], size=2)

    def test_info_window(self):
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        self.assertEqual(kodi.dialogs("textviewer"), [])
        window = kodi.windows[0]
        self.assertEqual(window.xml, ("script-musicip-info.xml", main.ADDON.getAddonInfo("path"), "Default", "1080i"))
        properties = window.properties
        self.assertTrue(properties["facts"].startswith("Created 20"))
        self.assertIn("| 2 tracks |", properties["facts"])
        tabs = [properties.get(f"tab{number}") for number in range(1, 7)]
        self.assertEqual(tabs, ["Overview", "Sound", "Changes", "History", None, None])  # no course without ratings
        self.assertEqual((window.focus, properties["tab"], properties["image"]), (201, "1", ""))
        self.assertIn("[B]How it was made[/B]\nMusicIP: 2 tracks, variety 0, style 5/10, no artist repeat within 2 "
                      "tracks, no filter", properties["text"])
        self.assertIn("[B]Files[/B]\nNot checked yet", properties["text"])
        window.onFocus(202)
        self.assertEqual((properties["tab"], properties["image"]), ("2", ""))
        self.assertIn("Not rated yet", properties["text"])
        window.onFocus(203)
        self.assertEqual(properties["text"], "AI Mix Assist hasn't checked this mix yet.")
        window.onFocus(204)
        self.assertEqual(properties["text"], main.mix_info_parts(self.cache_path)["history"])
        window.onFocus(205)  # no such tab: stays
        self.assertEqual(properties["tab"], "4")
        window.onClick(204)  # on to the text, to scroll it
        self.assertEqual(window.focus, main.INFO_TEXT_GROUP)

    def test_the_window_takes_the_skins_highlight(self):
        kodi.info_labels["Skin.String(focuscolor.name)"] = "AB0094A6"  # Arctic Fuse: the listener's colour
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        self.assertEqual(kodi.window_properties[main.HOME_WINDOW], {
            "MusicIP.Highlight": "AB0094A6", "MusicIP.Highlight.Dim": "440094A6", "MusicIP.Highlight.Text": "FF272727"})

    def test_a_focus_change_while_the_window_closes_is_ignored(self):
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        window = kodi.windows[0]

        def gone(*args):
            raise RuntimeError("Window id does not exist")

        window.setProperty = window.setFocusId = gone
        window.onFocus(202)
        window.onClick(201)

    def test_without_the_window_the_text_viewer_shows_it_all(self):
        kodi.window_error = "broken skin file"
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        heading, text = kodi.dialogs("textviewer")[0][1]
        self.assertEqual(heading, "MusicIP mix information")
        self.assertIn("[B]How it was made[/B]", text)
        self.assertIn("MusicIP: 2 tracks, variety 0, style 5/10, no artist repeat within 2 tracks, no filter", text)
        self.assertIn("[B]Files[/B]\nNot checked yet", text)

    def test_the_window_file_is_shipped(self):
        import xml.etree.ElementTree as ET
        skin = os.path.join(ADDON_DIR, "resources", "skins", "Default")
        tree = ET.parse(os.path.join(skin, "1080i", main.INFO_WINDOW_XML))
        ids = {int(control.get("id")) for control in tree.iter("control") if control.get("id")}
        self.assertTrue(set(main.INFO_TAB_IDS) | {main.INFO_TEXT_GROUP} <= ids)
        textures = {element.text for element in tree.iter() if element.text and element.text.endswith(".png")}
        self.assertEqual(textures, {"musicip-white.png"})
        self.assertTrue(os.path.isfile(os.path.join(skin, "media", "musicip-white.png")))
        self.assertEqual(list(tree.iter("include")), [])  # a script window can't use the skin's includes
        first_tab = next(control for control in tree.iter("control") if control.get("id") == "201")
        self.assertIsNone(first_tab.find("visible"))  # focusable as the window opens

    def test_the_info_key_opens_the_mix_information(self):
        item = main.xbmcgui.ListItem("mix")
        main.apply_saved_mix_info_metadata(item, self.cache_path)  # what a mix entry carries
        kodi.info_labels["ListItem.Property(MusicIP.InfoAction)"] = item.getProperty("MusicIP.InfoAction")
        self.run_plugin(action="keyboard_info")
        self.assertEqual(len(kodi.windows), 1)  # the add-on's information window
        self.assertNotIn("Action(Info)", kodi.builtins)

    def test_the_info_key_on_anything_else_is_kodis(self):
        self.run_plugin(action="keyboard_info")  # a song, an album: no information of the add-on's own
        self.assertEqual([command for command in kodi.builtins if command != "ReloadKeymaps"], ["Action(Info)"])
        self.assertEqual(kodi.dialogs("textviewer"), [])

    def test_the_info_key_is_in_the_keymap(self):
        for section in ("MyMusicNav", "window10502", "MusicPlaylist", "MusicFiles"):
            block = main.MUSICIP_KEYMAP_CONTENT.split(f"<{section}>")[1].split(f"</{section}>")[0]
            self.assertIn("<i>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_info)</i>", block)
            self.assertIn("<info>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_info)</info>", block)

    def test_info_for_selected_item(self):
        kodi.info_labels["ListItem.Property(MusicIP.CachePath)"] = self.cache_path
        self.run_plugin(action="mix_info_selected")
        self.assertEqual(len(kodi.windows), 1)

    def test_nothing_selected(self):
        self.run_plugin(action="mix_info")
        self.assertNotified("No saved mix is selected.")

    def test_unreadable_mix(self):
        self.run_plugin(action="mix_info", cache_path=self.cache_path + ".gone")
        self.assertIn("Could not read mix information.", kodi.dialogs("ok")[0][1][1])


class BrowseMixTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.add_media(SEED)
        kodi.add_media(T1)
        self.musicip.set_mix(SEED, [T1, T2])

    def test_stored_mix_is_listed_without_contacting_musicip(self):
        cache_path = self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(self.musicip.requests, [])
        self.assertEqual(self.listed_labels(), [
            "1. (Unknown Artist) - 01 Ace of Spades  [COLOR FF8C929C]Seed[/COLOR]",  # the seed says so
            "2. (Unknown Artist) - 01 Overkill",
            "[B][COLOR red]![/COLOR][/B] 3. (Unknown Artist) - 01 Motorcycle Man",
        ])
        url, item, is_folder = kodi.directory_items[0]
        self.assertEqual(plugin_query(url), {"action": "play_track", "path": SEED})
        self.assertFalse(is_folder)
        self.assertEqual(item.getProperty("IsPlayable"), "true")
        self.assertEqual([label for label, _a in item.context_menu], ["Refresh mix", "More like this", "Remove from mix"])
        second = kodi.directory_items[1][1]
        self.assertIn("Less like this", [label for label, _a in second.context_menu])
        missing = kodi.directory_items[2][1]
        self.assertEqual(missing.getProperty("MusicIP.Missing"), "true")
        self.assertEqual(missing.getLabel2(), "[B][COLOR red]![/COLOR][/B] Missing file")
        self.assertEqual(plugin_query(item.getProperty("MusicIP.MixAction.Remove"))["cache_path"], cache_path)
        self.assertIn(("setContent", "songs"), kodi.directory_calls)

    def test_a_listing_is_handed_to_kodi_in_one_call(self):
        self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(kodi.directory_batches, [3])
        self.assertEqual(len(kodi.directory_items), 3)

    def test_missing_mix_is_generated_after_confirmation(self):
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(len(self.listed_labels()), 3)
        self.assertEqual(self.current_mix_tracks(), [SEED, T1, T2])

    def test_refresh_regenerates_and_replaces_listing(self):
        self.save_mix([SEED, T1], size=20)
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", refresh="1")
        self.assertEqual(self.current_mix_tracks(), [SEED, T1, T2])
        self.assertTrue(kodi.ended[-1]["updateListing"])

    def test_a_new_mix_plays_when_nothing_else_does(self):
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(kodi.playlist_files(), [SEED, T1, T2])
        self.assertEqual(kodi.player.file, SEED)
        self.assertNotified("Playing the new mix.")
        self.assertTrue(kodi.ended)  # the listing came first

    def test_a_new_mix_never_interrupts_other_media(self):
        kodi.play_file(T2)  # something else plays (or is paused)
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(kodi.player.file, T2)
        self.assertEqual(kodi.playlist_files(), [])
        self.assertEqual(self.current_mix_tracks(), [SEED, T1, T2])  # created and listed all the same

    def test_opening_a_stored_mix_does_not_play_it(self):
        self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertFalse(kodi.player.playing)

    def test_a_refreshed_mix_plays_when_idle(self):
        self.save_mix([SEED, T1], size=20)
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", refresh="1")
        self.assertEqual(kodi.playlist_files(), [SEED, T1, T2])

    def test_cancelled_generation_shows_error_item(self):
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(self.listed_labels(), ["MusicIP mix failed: Mix generation cancelled."])
        self.assertEqual(kodi.notifications[-1][2], "warning")

    def test_no_seed(self):
        self.run_plugin(action="browse_mix")
        self.assertNotified("No seed song was supplied.")

    def test_listing_queues_metadata_refresh_and_stores_snapshots(self):
        cache_path = self.save_mix([SEED, T1], size=20)
        main.write_track_metadata_cache(T1, {"title": "Overkill", "artist": "Motörhead"})
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertIn("2. Motörhead - Overkill", self.listed_labels())
        queued = [entry["path"] for entry in main.load_metadata_refresh_queue()["entries"]]
        # T1 has cached metadata; with no known library update time it is not refreshed again.
        self.assertEqual(queued, [SEED])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        self.assertIn(main.canonical_audio_path(T1), sidecar["track_metadata_by_path"])

    def test_focus_is_applied_once(self):
        self.save_mix([SEED, T1, T2], size=20)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", focus_index="2", focus_token="tok")
        self.assertEqual(kodi.builtins.count("Action(Down)"), 2)
        self.run_plugin(action="browse_mix", seed=SEED, size="20", focus_index="2", focus_token="tok")
        self.assertEqual(kodi.builtins.count("Action(Down)"), 2)


class BrowseSavedMixTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix([SEED, T1], size=20)

    def test_listing(self):
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        self.assertEqual(len(self.listed_labels()), 2)
        self.assertIn(("setPluginCategory", "Saved MusicIP mix: 01 Ace of Spades"), kodi.directory_calls)

    def test_refresh_makes_a_new_current_mix(self):
        self.musicip.set_mix(SEED, [T2])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path, refresh="1")
        self.assertEqual(self.current_mix_tracks(), [SEED, T2])
        self.assertNotEqual(main.get_current_mix_cache_path(), self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1])  # the saved mix stays
        self.assertIn(("setPluginCategory", "Current MusicIP mix: 01 Ace of Spades"), kodi.directory_calls)

    def test_empty_mix(self):
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            handle.write("")
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        self.assertEqual(self.listed_labels(), ["Mix is empty. Use Refresh mix to generate a new one."])

    def test_refresh_failure_keeps_stored_mix(self):
        self.musicip.mix_status = 500
        kodi.respond("select", 0)
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path, refresh="1")
        self.assertNotified("HTTP 500")
        self.assertFalse(kodi.ended[-1]["succeeded"])
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1])

    def test_unknown_or_missing_path(self):
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path + ".gone")
        self.assertNotified("No stored mix found")
        self.assertFalse(kodi.ended[-1]["succeeded"])
        self.run_plugin(action="browse_saved_mix")
        self.assertNotified("No stored mix path was supplied.")


class GenerateFromPlayingAudioTest(MusicIPServerTestCase):
    def test_generates_saves_and_plays_mix(self):
        kodi.play_file(SEED, title="Ace of Spades")
        self.musicip.set_mix(SEED, [T1, T2])
        kodi.respond("select", 0)

        self.run_plugin(action="generate_current_mix")

        self.assertEqual(self.current_mix_tracks(), [SEED, T1, T2])
        self.assertEqual(kodi.playlist_files(), [SEED, T1, T2])
        self.assertEqual(kodi.playlist[1][1].getLabel(), "2. (Unknown Artist) - 01 Overkill")
        self.assertEqual((kodi.player.position, kodi.player.file), (0, SEED))
        self.assertNotified("Playing generated mix.")
        update = kodi.builtins[-1]
        self.assertTrue(update.startswith("Container.Update(") and update.endswith(",replace)"))
        self.assertEqual(plugin_query(update)["cache_path"], main.get_current_mix_cache_path())
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(main.get_current_mix_cache_path()))
        self.assertEqual(sidecar["mix_generation_parameters"]["size"], 20)

    def test_server_error_is_listed(self):
        kodi.play_file(SEED)
        self.musicip.mix_status = 500
        kodi.respond("select", 0)
        self.run_plugin(action="generate_current_mix")
        self.assertEqual(self.listed_labels(), ["MusicIP mix failed: MusicIP server returned HTTP 500."])
        self.assertEqual(kodi.playlist, [])

    def test_playback_failure_is_listed(self):
        kodi.play_file(SEED)
        self.musicip.set_mix(SEED, [T1])
        kodi.respond("select", 0)
        with mock.patch("fake_kodi.Player.play", side_effect=RuntimeError("player busy")):
            self.run_plugin(action="generate_current_mix")
        self.assertEqual(self.listed_labels(), ["MusicIP mix playback failed: player busy"])
        self.assertEqual(self.current_mix_tracks(), [SEED, T1])

    def test_nothing_playing(self):
        with self.assertRaisesRegex(main.MusicIPError, "No audio is currently playing."):
            self.run_plugin(action="generate_current_mix")


class PlayTrackTest(KodiTestCase):
    def test_resolves_track_with_metadata(self):
        kodi.library.add_song(SEED, title="Ace of Spades", artist="Motörhead", album="Ace of Spades", year=1980, duration=169, genre=["Metal"])
        self.run_plugin(action="play_track", path=SEED)
        succeeded, item = kodi.resolved[0]
        self.assertTrue(succeeded)
        self.assertEqual((item.getLabel(), item.getPath()), ("Ace of Spades", SEED))
        self.assertEqual(item.getLabel2(), "1980s | Metal | 2:49")

    def test_no_path(self):
        self.run_plugin(action="play_track")
        self.assertFalse(kodi.resolved[0][0])


class MixEditingRoutesTest(MusicIPServerTestCase):
    def setUp(self):
        super().setUp()
        kodi.settings["playlist_size"] = "10"
        self.cache_path = self.save_mix([SEED, T1, T2], size=10)
        kodi.info_labels["Container.PluginName"] = "plugin.audio.musicip"

    def test_remove_track(self):
        self.run_plugin(action="remove_track", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T2])
        self.assertNotified("Removed: 01 Overkill")
        self.assertEqual(plugin_query(kodi.builtins[-1])["action"], "browse_saved_mix")

    def test_remove_is_only_allowed_inside_the_addon(self):
        kodi.info_labels.clear()
        self.run_plugin(action="remove_track", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertNotified("only available inside the MusicIP add-on")
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1, T2])

        kodi.info_labels["Container.FolderPath"] = "plugin://plugin.audio.musicip/?action=browse_mix"
        self.assertTrue(main.is_addon_mix_container_active())

    def test_more_like_this(self):
        self.musicip.set_mix(T1, ["E:\\new\\1.mp3"])
        self.run_plugin(action="more_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED, T1, "E:\\new\\1.mp3", T2])
        self.assertNotified("Inserted 1 track(s).")
        self.assertEqual(plugin_query(kodi.builtins[-1])["focus_index"], "1")

    def test_less_like_this(self):
        self.musicip.set_mix(T1, [T2])
        self.run_plugin(action="less_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [SEED])
        self.assertNotified("Removed 2 track(s).")
        self.assertEqual(plugin_query(kodi.builtins[-1])["focus_index"], "0")

    def test_edit_errors_are_notified(self):
        self.run_plugin(action="more_like_this", seed=SEED, size="10", index="1", path=T1, cache_path=self.cache_path)
        self.assertNotified("MusicIP returned an empty mix.")
        self.assertEqual(kodi.notifications[-1][2], "error")


class FolderEntriesTest(MusicIPServerTestCase):
    """Kodi expects every folder entry to answer with a directory listing (endOfDirectory)."""

    def folder_actions(self):
        self.run_plugin()
        self.run_plugin(action="discovery_mode")
        main.save_discovery_state({"enabled": True})
        self.run_plugin(action="discovery_mode")
        actions = []
        for url, _item, is_folder in kodi.directory_items:
            action = plugin_query(url).get("action")
            if is_folder and action not in actions:
                actions.append(action)
        return actions

    def prepare_for(self, action):
        kodi.reset()
        kodi.settings.update({"host": "127.0.0.1", "port": str(self.musicip.port)})
        for n in range(1, 4):
            kodi.library.add_song(f"D:\\music\\{n}.mp3", title=f"Song {n}", duration=240)
        if action in ("discovery_next", "discovery_stop", "discovery_mix_current"):
            self.run_plugin(action="discovery_start")
        kodi.play_file(SEED)
        self.musicip.set_mix(SEED, [T1])
        self.musicip.set_mix("D:\\music\\1.mp3", [T1])
        kodi.respond("select", 0)
        kodi.ended.clear()

    def test_menus_offer_these_folders(self):
        self.assertEqual(sorted(self.folder_actions()), sorted([
            "generate_current_mix", "discovery_mode", "radio_mode", "saved_mixes",
            "discovery_start", "discovery_mix_current", "discovery_next", "discovery_stop",
        ]))

    @unittest.expectedFailure
    def test_folder_entries_end_their_directory(self):
        # Known issue F8: these actions replace the screen with Container.Update instead of returning a listing.
        without_listing = []
        for action in self.folder_actions():
            self.prepare_for(action)
            self.run_plugin(action=action)
            if not kodi.ended:
                without_listing.append(action)
        self.assertEqual(without_listing, [])


class KeyboardShortcutTest(KodiTestCase):
    def test_runs_the_selected_items_action(self):
        kodi.info_labels["ListItem.Property(MusicIP.MixAction.Remove)"] = "RunPlugin(plugin://plugin.audio.musicip/?action=remove_track)"
        self.run_plugin(action="keyboard_remove_from_mix")
        self.assertEqual(kodi.builtins[-1], "RunPlugin(plugin://plugin.audio.musicip/?action=remove_track)")

    def test_no_action_for_selection(self):
        for action, label in (("keyboard_more_like_this", "More like this"), ("keyboard_less_like_this", "Less like this")):
            with self.subTest(action=action):
                self.run_plugin(action=action)
                self.assertNotified(f"No '{label}' action is available for the selected item.")


if __name__ == "__main__":
    unittest.main()
