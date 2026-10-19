"""The current mix: a new mix is shown as "Current mix" and listed under Saved mixes only once it is saved."""

import os
import unittest

from fake_kodi import kodi
from support import KodiTestCase, MusicIPServerTestCase, main, plugin_query, service

SEED = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
T1 = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"
T2 = "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3"


def item_by_label(label):
    for url, item, is_folder in kodi.directory_items:
        if item.getLabel() == label:
            return url, item, is_folder
    raise AssertionError(f"{label!r} not listed; have {[i.getLabel() for _u, i, _f in kodi.directory_items]}")


class CurrentMixTest(KodiTestCase):
    def root(self):
        kodi.directory_items.clear()
        self.run_plugin()
        return [item.getLabel() for _url, item, _folder in kodi.directory_items]

    def test_without_a_mix_there_is_no_current_mix(self):
        self.assertEqual(main.get_current_mix_cache_path(), "")
        self.assertNotIn("Current mix", self.root())

    def test_a_new_mix_is_the_current_mix_and_not_saved(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        self.assertEqual(main.get_current_mix_cache_path(), cache_path)
        self.assertFalse(main.is_mix_saved(main.get_saved_mix_metadata(cache_path)))
        self.assertEqual(main.list_saved_mix_cache_paths(), [])
        self.assertEqual(self.root(), ["Generate mix from playing audio", "Current mix", "Discovery mode", "Radio mode",
                                       "Saved mixes", "Settings"])
        url, item, is_folder = item_by_label("Current mix")
        self.assertTrue(is_folder)
        self.assertEqual(plugin_query(url), {"action": "browse_saved_mix", "cache_path": cache_path,
                                             "nonce": plugin_query(url)["nonce"]})
        self.assertEqual(item.getLabel2(), "01 Ace of Spades | 2 tracks | not saved")
        self.assertEqual(os.path.basename(item.getArt("icon")), "DefaultMusicPlaylists.png")
        self.assertEqual([label for label, _a in item.context_menu],
                         ["Save mix", "Information", "Check consistency", "AI Mix Assist..."])
        self.assertIn("Saved: not yet", item.getProperty("Plot"))

    def test_saving_lists_the_mix_and_keeps_it_current(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        self.root()
        _url, item, _folder = item_by_label("Current mix")
        kodi.respond("keyboard", "01 Ace of Spades")  # the suggested name, confirmed
        self.run_plugin(**plugin_query(item.context_action("Save mix")))
        self.assertEqual(kodi.dialogs("keyboard")[0][1], ("Save mix as", "01 Ace of Spades"))
        self.assertNotified('Saved as "01 Ace of Spades".')
        self.assertEqual(kodi.builtins[-1], "Container.Refresh")
        self.assertEqual(main.list_saved_mix_cache_paths(), [cache_path])
        self.assertEqual(main.get_current_mix_cache_path(), cache_path)
        self.root()
        _url, item, _folder = item_by_label("Current mix")
        self.assertEqual(item.getLabel2(), "01 Ace of Spades | 2 tracks | saved")
        self.assertNotIn("Save mix", [label for label, _a in item.context_menu])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        self.assertNotIn("unsaved", sidecar)
        self.assertNotIn("name", sidecar)  # no name of the listener's own
        self.assertGreater(sidecar["saved_ts"], 0)

    def test_the_name_can_be_edited_when_saving(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        kodi.respond("keyboard", "  Loud   and Fast ")
        self.run_plugin(action="save_mix", cache_path=cache_path)
        self.assertNotified('Saved as "Loud and Fast".')
        meta = main.get_saved_mix_metadata(cache_path)
        self.assertEqual(main.format_saved_mix_label(meta), "Loud and Fast (2 tracks)")
        self.assertIn('Saved as "Loud and Fast"', main.build_mix_history_text(meta))
        self.assertIn("Name: Loud and Fast", main.build_mix_info_message(cache_path))

    def test_an_empty_name_saves_under_the_suggested_one(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        kodi.respond("keyboard", "")
        self.run_plugin(action="save_mix", cache_path=cache_path)
        self.assertNotified('Saved as "01 Ace of Spades".')
        self.assertEqual(main.list_saved_mix_cache_paths(), [cache_path])

    def test_cancelling_the_name_leaves_the_mix_unsaved(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        self.run_plugin(action="save_mix", cache_path=cache_path)  # no keyboard response: cancelled
        self.assertEqual(main.list_saved_mix_cache_paths(), [])
        self.assertEqual(kodi.notifications, [])
        self.assertNotIn("Container.Refresh", kodi.builtins)

    def test_a_saved_mix_is_not_asked_again(self):
        cache_path = self.save_mix([SEED, T1])
        self.run_plugin(action="save_mix", cache_path=cache_path)
        self.assertEqual(kodi.dialogs("keyboard"), [])
        self.assertNotified('Saved as "01 Ace of Spades".')

    def test_saving_twice_records_it_once(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        main.save_current_mix(cache_path)
        main.save_current_mix(cache_path)
        history = self.read_json(main.mix_meta_path_from_cache_path(cache_path))["history"]
        self.assertEqual([event["kind"] for event in history], ["created", "saved"])

    def test_saving_a_mix_that_is_gone(self):
        self.run_plugin(action="save_mix", cache_path=os.path.join(main.get_profile_dir(), "mix_gone.m3u"))
        self.assertNotified("No stored mix found")

    def test_a_new_mix_replaces_an_unsaved_current_mix(self):
        first = main.create_current_mix(SEED, 20, [SEED, T1])
        second = main.create_current_mix(SEED, 20, [SEED, T2])
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(first))
        self.assertFalse(os.path.exists(main.mix_meta_path_from_cache_path(first)))
        self.assertEqual(main.get_current_mix_cache_path(), second)

    def test_a_new_mix_never_replaces_a_saved_mix(self):
        saved = main.create_current_mix(SEED, 20, [SEED, T1])
        main.save_current_mix(saved)
        current = main.create_current_mix(SEED, 20, [SEED, T2])  # the same song and size
        self.assertEqual(self.read_mix(saved), [SEED, T1])
        self.assertEqual(main.list_saved_mix_cache_paths(), [saved])
        self.assertEqual(main.get_current_mix_cache_path(), current)

    def test_a_deleted_current_mix_is_not_shown(self):
        cache_path = self.save_mix([SEED, T1])
        self.run_plugin(action="cleanup_saved_mix", cache_path=cache_path)
        self.assertEqual(main.get_current_mix_cache_path(), "")
        self.assertNotIn("Current mix", self.root())

    def test_mixes_from_older_versions_are_saved_mixes(self):
        cache_path = main.mix_cache_path(SEED, 20)  # no "unsaved" in the sidecar
        with open(cache_path, "w", encoding="utf-8") as handle:
            handle.write(f"{SEED}\n{T1}\n")
        self.write_json(main.mix_meta_path_from_cache_path(cache_path), {"seed": SEED, "size": 20})
        self.assertEqual(main.list_saved_mix_cache_paths(), [cache_path])
        self.assertNotIn("Current mix", self.root())


class SaveFromTheMixTest(KodiTestCase):
    def tracks_context(self, cache_path):
        kodi.directory_items.clear()
        self.run_plugin(action="browse_saved_mix", cache_path=cache_path)
        return [[label for label, _a in item.context_menu] for _url, item, _folder in kodi.directory_items]

    def test_each_track_of_an_unsaved_mix_offers_saving(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        menus = self.tracks_context(cache_path)
        self.assertEqual(menus[0], ["Refresh mix", "More like this", "Remove from mix", "Save mix"])
        self.assertEqual(menus[1][-1], "Save mix")
        self.assertIn(("setPluginCategory", "Current MusicIP mix: 01 Ace of Spades"), kodi.directory_calls)
        save = plugin_query(kodi.directory_items[1][1].context_action("Save mix"))
        self.assertEqual((save["action"], save["cache_path"]), ("save_mix", cache_path))

    def test_a_saved_mix_offers_no_saving(self):
        cache_path = self.save_mix([SEED, T1])
        for menu in self.tracks_context(cache_path):
            self.assertNotIn("Save mix", menu)

    def test_edits_before_saving_are_kept(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1, T2])
        main.remove_track_from_mix(SEED, 20, 1, T1, cache_path=cache_path)
        main.save_current_mix(cache_path)
        self.assertEqual(self.read_mix(cache_path), [SEED, T2])
        info = main.build_mix_info_message(cache_path)
        self.assertIn("Created: ", info)
        self.assertNotIn("Saved: not yet", info)


class BrowseMixUsesTheCurrentMixTest(MusicIPServerTestCase):
    def test_the_current_mix_of_the_same_song_is_shown(self):
        cache_path = main.create_current_mix(SEED, 20, [SEED, T1])
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertEqual(self.musicip.requests, [])
        self.assertEqual(main.get_current_mix_cache_path(), cache_path)
        self.assertEqual(len(kodi.directory_items), 2)

    def test_another_song_makes_a_new_current_mix(self):
        saved = self.save_mix([T2, T1], size=20)
        self.musicip.set_mix(SEED, [T1])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=SEED, size="20")
        self.assertNotEqual(main.get_current_mix_cache_path(), saved)
        self.assertEqual(self.current_mix_tracks(), [SEED, T1])
        self.assertEqual(main.list_saved_mix_cache_paths(), [saved])  # listed once it is saved


class RefreshRedrawTest(MusicIPServerTestCase):
    """Findings F25: Kodi runs the "Refresh mix" URL again whenever it redraws the folder."""

    def refresh_query(self, cache_path):
        kodi.directory_items.clear()
        self.run_plugin(action="browse_saved_mix", cache_path=cache_path)
        return plugin_query(kodi.directory_items[0][1].context_action("Refresh mix"))

    def test_a_redraw_after_refreshing_does_not_mix_again(self):
        unsaved = main.create_current_mix(SEED, 20, [SEED, T1])
        query = self.refresh_query(unsaved)
        self.musicip.set_mix(SEED, [T2])
        kodi.respond("select", 0)
        self.run_plugin(**query)
        refreshed = main.get_current_mix_cache_path()
        self.assertFalse(os.path.exists(unsaved))  # replaced: it wasn't saved
        kodi.directory_items.clear()
        self.run_plugin(**query)  # Container.Refresh
        self.assertEqual(len(kodi.dialogs("select")), 1)
        self.assertEqual(main.get_current_mix_cache_path(), refreshed)
        self.assertEqual(len(kodi.directory_items), 2)
        self.assertTrue(kodi.ended[-1]["succeeded"])

    def test_refreshing_again_mixes_again(self):
        saved = self.save_mix([SEED, T1], size=20)
        self.musicip.set_mix(SEED, [T2])
        kodi.respond("select", 0, 0)
        self.run_plugin(**self.refresh_query(saved))
        first = main.get_current_mix_cache_path()
        self.run_plugin(**self.refresh_query(saved))
        self.assertEqual(len(kodi.dialogs("select")), 2)
        self.assertNotEqual(main.get_current_mix_cache_path(), first)

    def test_a_redraw_of_a_library_song_mix_after_refreshing(self):
        self.musicip.set_mix(SEED, [T1])
        kodi.respond("select", 0)
        query = {"action": "browse_mix", "seed": SEED, "size": "20", "refresh": "1", "nonce": "123"}
        self.run_plugin(**query)
        self.run_plugin(**query)
        self.assertEqual(len(kodi.dialogs("select")), 1)


if __name__ == "__main__":
    unittest.main()


class StartupTest(KodiTestCase):
    def test_kodi_starts_without_a_current_mix(self):
        saved = self.save_mix(["D:\\a.mp3", "D:\\b.mp3"], seed="D:\\a.mp3")  # saved, and current
        self.assertEqual(main.get_current_mix_cache_path(), saved)
        self.assertEqual(main.clear_current_mix_on_startup(), 0)
        self.assertEqual(main.get_current_mix_cache_path(), "")
        self.assertIn(saved, main.list_saved_mix_cache_paths())  # a saved mix stays

    def test_unsaved_mixes_are_deleted_with_their_collages(self):
        left_over = main.create_current_mix("D:\\x.mp3", 2, ["D:\\x.mp3", "D:\\y.mp3"])
        main.save_json_file(main.current_mix_state_path(), {})  # e.g. Kodi stopped while another was current
        current = main.create_current_mix("D:\\a.mp3", 2, ["D:\\a.mp3", "D:\\b.mp3"])
        collage = main.mix_collage_path(current, ["D:\\a.mp3", "D:\\b.mp3"])
        os.makedirs(os.path.dirname(collage), exist_ok=True)
        open(collage, "wb").close()
        kodi.textures[collage] = "x/cached.jpg"  # Kodi showed it, so it has a copy
        self.assertEqual(main.clear_current_mix_on_startup(), 2)
        for path in (left_over, current, collage):
            self.assertFalse(os.path.exists(path), path)
        self.assertNotIn(collage, kodi.textures)

    def test_the_service_clears_it_when_it_starts(self):
        self.save_mix(["D:\\a.mp3", "D:\\b.mp3"], seed="D:\\a.mp3", saved=False)
        service.clear_current_mix_on_startup()
        self.assertEqual(main.get_current_mix_cache_path(), "")

