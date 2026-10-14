"""AI Mix Assist in the add-on: tidying up saved mixes from the context menu, undo, editing the intent."""

import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, main

TRACKS = [
    "D:\\music\\#jazz\\Seed.mp3",
    "D:\\music\\#jazz\\Fits.mp3",
    "D:\\music\\#disco\\Fire Walk.mp3",
    "D:\\music\\#jazz\\Fits Too.mp3",
    "D:\\music\\#pop\\Who Do You Love.mp3",
]
REPLACEMENT = "D:\\music\\#jazz\\Replacement.mp3"
ORIGINAL_ASK = main.mix_assist_ask


def row(position, label, status="fits"):
    return {"position": position, "unit": {"label": label}, "status": status}


def plan(changes=(), removed=(), intent="dark, abstract, instrumental", source="ai"):
    paths = list(TRACKS)
    for change in changes:
        paths[change["position"] - 1] = change["new"]
    paths = [path for index, path in enumerate(paths, start=1) if index not in removed]
    return {"intent": intent, "intent_source": source, "changes": list(changes), "removed": list(removed),
            "paths": paths, "rebuild_suggested": False,
            "rows": [row(i, f"Track {i}", "outlier" if i in (3, 5) else "fits") for i in range(1, 6)]}


REPLACE_DISCO = {"position": 3, "old": TRACKS[2], "old_label": "wilfried – fire walk", "new": REPLACEMENT,
                 "new_label": "Medeski Martin & Wood – Think", "reason": "Danceable disco, bright", "source": "submix"}


class MixAssistTestCase(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix(TRACKS)
        patcher = mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tidy_up(self, result, **kwargs):
        with mock.patch.object(main.mix_assist, "tidy_up", return_value=result) as tidy_up:
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path, **kwargs)
        return tidy_up

    def section(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path)).get("mix_assist", {})


class TidyUpTest(MixAssistTestCase):
    def test_replacements_are_applied_recorded_and_announced(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])
        section = self.section()
        self.assertEqual(section["intent"], "dark, abstract, instrumental")
        self.assertEqual(section["intent_source"], "ai")
        self.assertEqual(section["previous_tracks"], TRACKS)
        self.assertEqual(section["replaced"][0]["new_label"], "Medeski Martin & Wood – Think")
        self.assertEqual(section["removed"], ["Track 5"])
        self.assertNotified("AI Mix Assist: 1 track didn't fit and was replaced, 1 without a fitting replacement was removed.")
        self.assertBuiltin("Container.Refresh")

    def test_a_fitting_mix_is_left_unchanged(self):
        self.tidy_up(plan())
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("AI Mix Assist: every track fits.")

    def test_settings_and_the_listeners_intent_are_passed_on(self):
        kodi.settings.update({"mix_assist_strictness": "4", "mix_reject_size": "3"})
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"listener_intent": "my own words"}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        tidy_up = self.tidy_up(plan(intent="my own words", source="listener"))
        args, kwargs = tidy_up.call_args
        self.assertEqual(args[0], TRACKS)
        self.assertEqual(kwargs["intent"], "my own words")
        self.assertEqual(kwargs["strictness"], 1.0)
        self.assertEqual(kwargs["artist_window"], 3)
        self.assertEqual(self.section()["listener_intent"], "my own words")

    def test_progress_is_shown_in_the_background_and_closed(self):
        def tidy_up(*args, **kwargs):
            kwargs["progress"]("Rating new music")
            return plan()

        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=tidy_up):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        calls = [call[0] for call in kodi.dialog_calls if call[0].startswith("progress")]
        self.assertEqual(calls[0], "progress.create")
        self.assertIn("progress.update", calls)
        self.assertEqual(calls[-1], "progress.close")

    def test_claude_problems_become_plain_messages(self):
        error = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=error):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        self.assertNotified("Claude's usage limit is reached")
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)

    def test_a_missing_cli_is_reported(self):
        with mock.patch.object(main, "mix_assist_ask", ORIGINAL_ASK), \
                mock.patch.object(main.mix_assist_claude, "find_cli", return_value=""):
            self.run_plugin(action="mix_assist_tidy_up", cache_path=self.cache_path)
        self.assertNotified("AI Mix Assist needs the Claude Code CLI")


class UndoTest(MixAssistTestCase):
    def test_undo_restores_the_previous_tracks(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertNotIn("replaced", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("AI Mix Assist: the changes were undone.")

    def test_nothing_to_undo(self):
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertNotified("There are no AI Mix Assist changes to undo.")


class EditIntentTest(MixAssistTestCase):
    def test_the_listener_can_write_and_clear_the_intent(self):
        self.tidy_up(plan())
        kodi.respond("input", "complex, abstract, not danceable")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertEqual(kodi.dialogs("input")[-1][1], ("What is this mix about?", "dark, abstract, instrumental"))
        self.assertEqual(self.section()["listener_intent"], "complex, abstract, not danceable")
        self.assertNotified("Saved. Tidy up the mix to apply it.")

        kodi.respond("input", "  ")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())

    def test_cancelling_keeps_the_intent(self):
        self.tidy_up(plan())
        kodi.respond("input", "dark, abstract, instrumental")  # unchanged text, as when cancelled with the default
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())


class SavedMixMenuTest(MixAssistTestCase):
    def context_labels(self):
        kodi.directory_items.clear()
        main.add_saved_mix_item(self.cache_path)
        return [label for label, _action in kodi.directory_items[-1][1].context_menu]

    def test_entries_and_undo_only_after_a_change(self):
        labels = self.context_labels()
        self.assertIn("Tidy up with AI Mix Assist", labels)
        self.assertIn("Edit what this mix is about", labels)
        self.assertNotIn("Undo AI Mix Assist changes", labels)
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.assertIn("Undo AI Mix Assist changes", self.context_labels())

    def test_mix_information_shows_the_intent_and_the_changes(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        message = main.build_mix_info_message(self.cache_path)
        self.assertIn("What this mix is about (stated by the AI): dark, abstract, instrumental", message)
        self.assertIn("Replaced: wilfried – fire walk → Medeski Martin & Wood – Think (Danceable disco, bright)", message)


class StrictnessSettingTest(KodiTestCase):
    def test_steps_map_to_thresholds(self):
        self.assertEqual(main.get_mix_assist_strictness(), 1.2)
        for value, expected in (("0", 1.5), ("4", 1.0), ("9", 1.0), ("x", 1.2)):
            kodi.settings["mix_assist_strictness"] = value
            self.assertEqual(main.get_mix_assist_strictness(), expected)


if __name__ == "__main__":
    unittest.main()
