"""AI Mix Assist in the add-on: tidying up saved mixes from the context menu, undo, editing the intent."""

import os
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, SourceTestCase, main, service

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

    def history(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path)).get("history", [])


class TidyUpTest(MixAssistTestCase):
    def test_replacements_are_applied_recorded_and_announced(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])
        section = self.section()
        self.assertEqual(section["intent"], "dark, abstract, instrumental")
        self.assertEqual(section["intent_source"], "ai")
        self.assertEqual(section["previous_tracks"], TRACKS)
        self.assertEqual(section["replaced"][0]["new_label"], "Medeski Martin & Wood – Think")  # stored as given
        self.assertEqual(section["removed"], ["Track 5"])
        self.assertNotified("Checks: 1 track didn't fit and was replaced, 1 without a fitting replacement was removed.")
        self.assertBuiltin("Container.Refresh")
        event = self.history()[-1]
        self.assertEqual((event["kind"], event["automatic"], event["intent"]),
                         ("ai_tidy_up", False, "dark, abstract, instrumental"))
        self.assertEqual(event["replaced"], [{"old": "wilfried \u2013 fire walk", "new": "Medeski Martin & Wood \u2013 Think",
                                              "reason": "Danceable disco, bright"}])
        self.assertEqual(event["removed"], [{"track": "Track 5", "reason": ""}])

    def test_a_replacement_says_it_came_from_ai_mix_assist(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        origin = main.track_origin(main.get_saved_mix_metadata(self.cache_path), REPLACEMENT)
        self.assertEqual(origin["origin"], "ai")
        self.assertEqual(origin["note"], "Replaced by the checks: wilfried \u2013 fire walk (Danceable disco, bright)")
        for track in self.read_mix(self.cache_path):
            kodi.add_media(track)
        kodi.directory_items.clear()
        self.run_plugin(action="browse_saved_mix", cache_path=self.cache_path)
        item = [item for _url, item, _folder in kodi.directory_items][2]
        self.assertTrue(item.getLabel2().startswith("Checks"))
        self.assertEqual(item.getMusicInfoTag().getComment(),
                         "Replaced by the checks: wilfried - fire walk (Danceable disco, bright)")  # plain

    def test_older_tidy_ups_count_too(self):
        meta_path = main.mix_meta_path_from_cache_path(self.cache_path)
        meta = self.read_json(meta_path)
        meta["mix_assist"] = {"replaced": [dict(REPLACE_DISCO)]}  # before origins were kept
        self.write_json(meta_path, meta)
        self.assertEqual(main.track_origin(main.get_saved_mix_metadata(self.cache_path), REPLACEMENT)["origin"], "ai")
        self.assertEqual(main.track_origin(main.get_saved_mix_metadata(self.cache_path), TRACKS[1]), {})

    def test_a_fitting_mix_is_left_unchanged(self):
        self.tidy_up(plan())
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("Checks: every track fits.")

    def test_settings_and_the_listeners_intent_are_passed_on(self):
        kodi.settings.update({"mix_assist_mix_strictness": "0", "mix_reject_size": "3"})
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
        self.assertNotified("The checks need the Claude Code CLI")


class UndoTest(MixAssistTestCase):
    def test_undo_restores_the_previous_tracks(self):
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotIn("previous_tracks", self.section())
        self.assertNotIn("replaced", self.section())
        self.assertEqual(self.section()["intent"], "dark, abstract, instrumental")
        self.assertNotified("Checks: the changes were undone.")
        self.assertEqual(self.history()[-1]["kind"], "ai_undone")

    def test_nothing_to_undo(self):
        self.run_plugin(action="mix_assist_undo", cache_path=self.cache_path)
        self.assertNotified("There are no changes of the checks to undo.")


class EditIntentTest(MixAssistTestCase):
    def test_the_listener_can_write_and_clear_the_intent(self):
        self.tidy_up(plan())
        kodi.respond("keyboard", "complex, abstract, not danceable")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertEqual(kodi.dialogs("keyboard")[-1][1], ("What is this mix about?", "dark, abstract, instrumental"))
        self.assertEqual(self.section()["listener_intent"], "complex, abstract, not danceable")
        self.assertNotified("Saved. Tidy up the mix to apply it.")
        self.assertEqual(self.history()[-1], dict(self.history()[-1], kind="intent_edited",
                                                  text="complex, abstract, not danceable"))

        kodi.respond("keyboard", "  ")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())
        self.assertEqual(self.history()[-1]["text"], "")

    def test_cancelling_keeps_the_intent_and_says_nothing(self):
        self.tidy_up(plan())
        kodi.notifications.clear()
        kodi.respond("keyboard", "complex, abstract, not danceable")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        kodi.notifications.clear()
        kodi.respond("keyboard", None)  # Esc
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertEqual(self.section()["listener_intent"], "complex, abstract, not danceable")
        self.assertEqual(kodi.notification_messages(), [])

    def test_unchanged_or_empty_text_changes_nothing(self):
        self.tidy_up(plan())
        kodi.notifications.clear()
        kodi.respond("keyboard", "dark, abstract, instrumental ", "")
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.run_plugin(action="mix_assist_edit_intent", cache_path=self.cache_path)
        self.assertNotIn("listener_intent", self.section())
        self.assertEqual(kodi.notification_messages(), [])


class SavedMixMenuTest(MixAssistTestCase):
    def context_labels(self):
        kodi.directory_items.clear()
        main.add_saved_mix_item(self.cache_path)
        self.finish_listing()
        return [label for label, _action in kodi.directory_items[-1][1].context_menu]

    def menu(self):
        kodi.dialog_calls.clear()
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        return kodi.dialogs("select")[0][1][1]

    def test_one_context_menu_entry(self):
        labels = self.context_labels()
        self.assertIn("Checks...", labels)
        for old in ("Tidy up with AI Mix Assist", "Edit what this mix is about", "Undo AI Mix Assist changes"):
            self.assertNotIn(old, labels)

    def test_the_menu_offers_undo_only_after_a_change(self):
        self.assertEqual(self.menu(), ["What this mix is about: <not worked out yet>", "Character: Balanced",
                                       "Intent: Mixed", "Name: <given at the first check>", "Check the mix now"])
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        self.assertEqual(self.menu(), ["What this mix is about: dark, abstract, instrumental", "Character: Balanced",
                                       "Intent: Mixed", "Name: <given at the first check>", "Check the mix now", "Undo the changes of the checks"])

    def test_tidy_up_now_from_the_menu(self):
        kodi.respond("select", 4)
        with mock.patch.object(main.mix_assist, "tidy_up", return_value=plan(changes=[REPLACE_DISCO])):
            self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path)[2], REPLACEMENT)

    def test_the_openness_of_a_mix_can_be_changed(self):
        kodi.respond("select", 1, 4)  # Character, then: Off, Focused, Close, Balanced, Open, ...
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        _method, (heading, options), _kwargs = kodi.dialogs("select")[-1]
        self.assertEqual(heading, "Character of this mix")
        self.assertEqual(options[0], "Off: the profile isn't compared")
        self.assertEqual(options[3], "Balanced (default)")
        self.assertEqual(self.section()["character"], 3)
        self.assertEqual(self.history()[-1]["openness"], "Open")
        self.assertNotified("Saved. The checks use it for this mix from now on.")
        self.assertIn("Checks: Character Open (chosen for this mix), Intent Mixed",
                      main.build_mix_info_page(self.cache_path))

    def test_the_perspective_of_a_mix_can_be_changed(self):
        self.assertEqual(self.tidy_up(plan()).call_args[1]["perspective"], "mixed")  # the setting's default
        kodi.respond("select", 2, 2)  # Intent, then: Off, Mixed, Technical, ...
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        _method, (heading, options), _kwargs = kodi.dialogs("select")[-1]
        self.assertEqual(heading, "Intent of this mix")
        self.assertEqual(options[:3], ["Off: no AI judgement", "Mixed: intention and qualities (default)",
                                       "Technical: how it is made"])
        self.assertEqual(self.section()["perspective"], 1)
        self.assertEqual(self.history()[-1]["perspective"], "Technical")
        self.assertIn("You set the checks to Intent Technical", main.build_mix_history_text(
            self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))))
        self.assertNotified("Saved. Tidy up the mix to see it from the new perspective.")
        self.assertIn("Checks: Character Balanced, Intent Technical (chosen for this mix)",
                      main.build_mix_info_page(self.cache_path))
        self.assertEqual(self.tidy_up(dict(plan(), perspective="technical")).call_args[1]["perspective"], "technical")
        self.assertEqual(self.section()["intent_perspective"], "technical")
        self.assertIn("(as the AI put it, from the technical perspective)", main.build_mix_info_page(self.cache_path))

    def test_the_perspective_setting_applies_to_mixes_without_their_own(self):
        kodi.settings["mix_assist_mix_perspective"] = "2"
        self.assertEqual(self.tidy_up(plan()).call_args[1]["perspective"], "emotional")
        self.assertEqual(self.menu()[2], "Intent: Emotional")

    def test_cancelling_the_menu_does_nothing(self):
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertNotIn("Container.Refresh", kodi.builtins)
        self.assertEqual(kodi.notifications, [])

    def test_mix_information_shows_what_it_is_about_and_the_changes(self):
        self.assertNotIn("[B]What it is about[/B]", main.build_mix_info_page(self.cache_path))
        self.tidy_up(plan(changes=[REPLACE_DISCO]))
        page = main.build_mix_info_page(self.cache_path)
        self.assertIn("[B]What it is about[/B]\ndark, abstract, instrumental\n(as the AI put it)\n"
                      "Checks: Character Balanced, Intent Mixed, last checked", page)
        self.assertIn("[B]Last tidy-up[/B]\nwilfried - fire walk » Medeski Martin & Wood - Think (Danceable disco, bright)",
                      page)
        self.assertIn("can undo it", page)
        history = page.split("[B]History[/B]")[1]
        self.assertIn("The mix was tidied up: 1 replaced, 0 removed\n"
                      "    wilfried - fire walk » Medeski Martin & Wood - Think (Danceable disco, bright)", history)

    def test_a_check_stores_how_the_mix_sounds(self):
        result = plan(changes=[REPLACE_DISCO])
        for row, energy in zip(result["rows"], (2, 4, 9, 6, 8)):  # position 3 is replaced: its rating doesn't count
            row["entry"] = {"energy": energy, "exploration": 5, "sounding_year": 1980 + energy}
        self.tidy_up(result)
        profile = self.section()["profile"]
        self.assertEqual((profile["rated"], profile["values"]["energy"]), (4, [5.0, 2.0, 8.0]))
        page = main.build_mix_info_page(self.cache_path)
        self.assertIn("[B]How it sounds[/B]\nEnergy: 5.0 steady (range 2-8)", page)
        self.assertIn("Sounding year: 1985 (range 1982-1988)", page)
        self.assertIn("(ratings of 4 tracks, at the check on", page)
        self.assertNotIn("changed since", page)

    def test_a_check_stores_each_tracks_ratings_for_the_course(self):
        result = plan(changes=[dict(REPLACE_DISCO, entry={"energy": 7, "sounding_year": 1990})], removed=[5])
        for row, energy in zip(result["rows"], (2, 4, 9, 6, 8)):
            row["entry"] = {"energy": energy, "sounding_year": 1980 + energy}
        result["paths"] = [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]]
        self.tidy_up(result)
        profile = self.section()["profile"]
        energy, year = (main.mix_assist_dimensions.ALL_KEYS.index(key) for key in ("energy", "sounding_year"))
        self.assertEqual([(row[energy], row[year]) for row in profile["course"]],
                         [(2, 1982), (4, 1984), (7, 1990), (6, 1986)])  # the replacement's own, the removed one gone
        self.assertEqual(profile["tracks_key"], main.mix_tracks_key(result["paths"]))
        main.save_mix_by_cache_path(self.cache_path, result["paths"][:3])
        self.assertIn("; the mix has changed since)", main.build_mix_info_page(self.cache_path))

    def test_the_window_shows_the_sound_and_the_course_as_charts(self):
        result = plan(changes=[REPLACE_DISCO])
        for row, energy in zip(result["rows"], (2, 4, 9, 6, 8)):
            row["entry"] = {"energy": energy, "exploration": 5, "sounding_year": 1980 + energy}
        self.tidy_up(result)
        self.run_plugin(action="mix_info", cache_path=self.cache_path)
        window = kodi.windows[-1]
        titles = [window.properties.get(f"tab{number}") for number in range(1, 6)]
        self.assertEqual(titles, ["Overview", "Sound", "Course", "Changes", "History"])
        self.assertIn("[B]What it is about[/B]\ndark, abstract, instrumental", window.properties["text"])
        window.onFocus(202)
        sound = window.properties["image"]
        self.assertTrue(sound.endswith(".png") and os.path.isfile(sound))
        self.assertIn("Energy: 5.0 steady (range 2-8)", window.properties["text"])  # no font here: as text
        window.onFocus(203)
        self.assertTrue(os.path.isfile(window.properties["image"]))
        self.assertIn("in the mix's order", window.properties["text"])
        self.assertIn("the sounding year in white, on its own scale (right)", window.properties["text"])
        window.onFocus(204)
        self.assertEqual(window.properties["image"], "")
        self.assertIn("[B]Last tidy-up[/B]\nwilfried - fire walk » Medeski Martin & Wood - Think", window.properties["text"])
        self.run_plugin(action="mix_info", cache_path=self.cache_path)  # a new chart; the older one is gone
        charts = os.listdir(os.path.dirname(sound))
        self.assertEqual(sorted(name.split("_")[0] for name in charts), ["course", "sound"])
        self.assertNotIn(os.path.basename(sound), charts)

    def test_the_course_chart_has_all_dimensions_on_one_scale_and_the_year_on_its_own(self):
        keys = main.mix_assist_dimensions.ALL_KEYS
        course = [[2.0] * (len(keys) - 1) + [1980.0], [None] * len(keys), [6.0] * (len(keys) - 1) + [1990.0]]
        data = main.course_chart_series(course)
        self.assertEqual(data["tracks"], [1, 2, 3])
        self.assertEqual(data["years"], (1975, 1995))
        energy, year = data["series"][0], data["series"][-1]
        self.assertEqual((energy["name"], energy["axis"], energy["values"]), ("Energy", "left", [2.0, None, 6.0]))
        self.assertEqual(energy["legend"], f"{main.dimension_value_text('energy', 4.0)} (2-6)")
        self.assertEqual((year["axis"], year["legend"]), ("right", "1985 (1980-1990)"))
        texts = [text.text for text in main.line_chart_texts(data, "Track 1", "Track 3",
                                                             [item["legend"] for item in data["series"]])]
        self.assertIn("Sounding year (right scale)", texts)
        self.assertTrue({"Track 1", "Track 3", "1975", "1995", "0", "10"} <= set(texts))

    def test_with_a_font_the_charts_carry_their_text(self):
        result = plan()
        for row in result["rows"]:
            row["entry"] = {"energy": 5, "sounding_year": 1980}
        self.tidy_up(result)
        with mock.patch.object(main.mix_assist_chart, "can_draw_text", return_value=True):
            self.run_plugin(action="mix_info", cache_path=self.cache_path)
        window = kodi.windows[-1]
        window.onFocus(202)
        self.assertNotIn("Energy: 5.0", window.properties["text"])
        self.assertIn("the bar is the mix's range, the dot its average", window.properties["text"])

    def test_without_a_check_the_page_has_no_ratings(self):
        self.assertNotIn("range", main.build_mix_info_page(self.cache_path))


class PerMixLevelTest(MixAssistTestCase):
    def set_openness(self, index):
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"openness": index}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)

    def test_a_tidy_up_uses_the_mixs_openness(self):
        self.set_openness(4)
        tidy_up = self.tidy_up(plan())
        self.assertEqual((tidy_up.call_args[1]["strictness"], tidy_up.call_args[1]["accept_borderline"]), (1.5, False))
        kodi.settings["mix_intent_borderline"] = "true"  # Intent's own switch now, not part of the level
        self.assertTrue(self.tidy_up(plan()).call_args[1]["accept_borderline"])

    def test_without_a_choice_the_setting_counts(self):
        kodi.settings["mix_assist_mix_strictness"] = "0"
        tidy_up = self.tidy_up(plan())
        self.assertEqual(tidy_up.call_args[1]["strictness"], 1.0)

    def test_an_older_mix_switched_off_has_every_check_off(self):
        self.set_openness(main.MIX_OPENNESS_OFF)  # an older mix's Off switched every check off
        meta = main.get_saved_mix_metadata(self.cache_path, self.read_mix(self.cache_path))
        self.assertTrue(main.mix_checks_off(meta))
        with self.assertRaisesRegex(main.MusicIPError, "both off for this mix"):
            main.run_mix_assist_on_saved_mix(self.cache_path)
        self.assertIn("Checks: off for this mix", main.build_mix_info_page(self.cache_path))

    def test_character_off_leaves_intent_on(self):
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"character": main.CHECK_OFF}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        tidy_up = self.tidy_up(plan())
        self.assertEqual((tidy_up.call_args[1]["strictness"], tidy_up.call_args[1]["perspective"]), (None, "mixed"))
        self.assertEqual(tidy_up.call_args[1]["scale_entries"], ())  # no fixed scale without Character

    def test_intent_off_leaves_character_on(self):
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"perspective": main.CHECK_OFF}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        tidy_up = self.tidy_up(plan())
        self.assertEqual((tidy_up.call_args[1]["strictness"], tidy_up.call_args[1]["perspective"]), (1.2, None))


class GenerateDialogTest(SourceTestCase):
    def setUp(self):
        super().setUp()
        self.source.set_mix(TRACKS[0], TRACKS[1:])

    @property
    def cache_path(self):
        return main.get_current_mix_cache_path()

    def sidecar(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))

    def queued(self):
        return self.read_json(main.mix_assist_queue_path()).get("entries", [])

    def test_the_dialog_shows_the_ai_mix_assist_lines(self):
        params = main.confirm_mix_generation({}) or {}
        choices = kodi.dialogs("select")[0][1][1]
        self.assertEqual(choices[4:], ["Character: Balanced", "Intent: Mixed",
                                       "What this mix is about: <worked out by the AI>"])
        self.assertEqual(params, {})  # cancelled

    def test_a_perspective_chosen_when_generating_is_kept_with_the_mix(self):
        kodi.respond("select", 5, 6, 0)  # Intent -> Lyrical (after Off), Generate
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        self.assertEqual(self.sidecar()["mix_assist"]["perspective"], 5)
        self.assertIn("When you created the mix, you set the checks to Intent Lyrical",
                      main.build_mix_history_text(self.sidecar()))
        self.assertNotIn("assist_perspective", self.sidecar()["mix_generation_parameters"])

    def test_choices_made_when_generating_are_kept_with_the_mix(self):
        kodi.respond("select", 4, 5, 6, 0)  # AI Mix Assist -> Adventurous, What it is about -> ..., Generate
        kodi.respond("keyboard", "  dark cosmic electronics  ")
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        section = self.sidecar()["mix_assist"]
        self.assertEqual((section["character"], section["listener_intent"]), (4, "dark cosmic electronics"))
        event = [e for e in self.sidecar()["history"] if e["kind"] == "assist_settings"][0]
        self.assertEqual((event["at_creation"], event["openness"]), (True, "Adventurous"))
        self.assertIn('When you created the mix, you set the checks to Character Adventurous; about "dark cosmic electronics"',
                      main.build_mix_history_text(self.sidecar()))
        self.assertEqual([entry["cache_path"] for entry in self.queued()], [self.cache_path])
        self.assertNotIn("assist_openness", self.sidecar()["mix_generation_parameters"])  # MusicIP's stay clean

    def test_a_mix_created_with_both_checks_off_is_not_tidied_up(self):
        kodi.respond("select", 4, 0, 5, 0, 0)  # Character -> Off, Intent -> Off, Generate
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        section = self.sidecar()["mix_assist"]
        self.assertEqual((section["character"], section["perspective"]), (main.CHECK_OFF, main.CHECK_OFF))
        self.assertEqual(self.queued(), [])

    def test_a_mix_created_with_character_off_is_still_checked(self):
        kodi.respond("select", 4, 0, 0)  # Character -> Off, Generate
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        self.assertEqual(self.sidecar()["mix_assist"]["character"], main.CHECK_OFF)
        self.assertEqual([entry["cache_path"] for entry in self.queued()], [self.cache_path])

    def test_default_choices_store_nothing_extra(self):
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        self.assertNotIn("mix_assist", self.sidecar())
        self.assertEqual(len(self.queued()), 1)


class MixNameTest(MixAssistTestCase):
    def named_plan(self, name="Cosmic Analog Journeys"):
        result = plan()
        result["name"] = name
        return result

    def label(self):
        return main.format_saved_mix_label(main.get_saved_mix_metadata(self.cache_path, TRACKS))

    def test_the_first_check_names_the_mix(self):
        self.tidy_up(self.named_plan())
        self.assertEqual(self.section()["ai_name"], "Cosmic Analog Journeys")
        self.assertEqual(self.label(), "Cosmic Analog Journeys (5 tracks)")
        self.assertEqual(self.history()[-2], dict(self.history()[-2], kind="named", name="Cosmic Analog Journeys"))
        self.assertTrue(main.build_mix_info_page(self.cache_path).startswith("[B]Cosmic Analog Journeys[/B]\nCreated 20"))

    def test_your_name_wins_and_can_be_removed(self):
        self.tidy_up(self.named_plan())
        kodi.respond("select", 3)  # Name
        kodi.respond("keyboard", " My  Mix ")
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertEqual(self.label(), "My Mix (5 tracks)")
        self.assertEqual(self.history()[-1]["kind"], "renamed")
        self.tidy_up(self.named_plan("Something Else"))  # a later check renames only the AI's name
        self.assertEqual(self.label(), "My Mix (5 tracks)")
        kodi.respond("select", 3)
        kodi.respond("keyboard", "")
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertEqual(self.label(), "Something Else (5 tracks)")

    def test_naming_can_be_switched_off(self):
        self.tidy_up(self.named_plan())
        kodi.settings["mix_assist_name_mixes"] = "false"
        self.assertEqual(self.label(), "Seed (5 tracks)")
        kodi.respond("select", -1)
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertFalse(any(label.startswith("Name") for label in kodi.dialogs("select")[-1][1][1]))

    def test_without_a_name_the_seed_names_the_mix(self):
        self.tidy_up(plan())
        self.assertEqual(self.label(), "Seed (5 tracks)")


class CurrentMixNameTest(MixAssistTestCase):
    """The AI's name of a mix that isn't saved yet stays hidden; saving lists the mix under it."""

    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix(TRACKS, saved=False)
        result = plan()
        result["name"] = "Cosmic Analog Journeys"
        self.tidy_up(result)

    def meta(self):
        return main.get_saved_mix_metadata(self.cache_path, TRACKS)

    def test_the_name_is_hidden_until_the_mix_is_saved(self):
        self.assertEqual(self.section()["ai_name"], "Cosmic Analog Journeys")
        self.assertEqual(main.mix_name(self.meta()), "")
        page = main.build_mix_info_page(self.cache_path)
        self.assertNotIn("Cosmic Analog Journeys", page)
        self.assertIn(" | not saved yet", page)
        kodi.respond("select", -1)
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertFalse(any(label.startswith("Name") for label in kodi.dialogs("select")[-1][1][1]))

    def save(self, name):
        kodi.respond("keyboard", name)
        self.run_plugin(action="save_mix", cache_path=self.cache_path)

    def test_saving_lists_the_mix_under_the_ai_name(self):
        self.save("Cosmic Analog Journeys")
        self.assertEqual(kodi.dialogs("keyboard")[0][1], ("Save mix as", "Cosmic Analog Journeys"))
        self.assertNotified('Saved as "Cosmic Analog Journeys".')
        self.assertNotIn("name", self.read_json(main.mix_meta_path_from_cache_path(self.cache_path)))
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Cosmic Analog Journeys (5 tracks)")
        self.assertIn('named the mix "Cosmic Analog Journeys"', main.build_mix_history_text(self.meta()))
        self.assertNotIn("not saved yet", main.build_mix_info_page(self.cache_path))

    def test_a_name_of_your_own_when_saving_wins_over_later_checks(self):
        self.save("Night Drive")
        self.assertNotified('Saved as "Night Drive".')
        result = plan()
        result["name"] = "Something Else"
        self.tidy_up(result)
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Night Drive (5 tracks)")
        kodi.settings["mix_assist_name_mixes"] = "false"  # the setting is about the AI's names
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Night Drive (5 tracks)")

    def test_without_naming_the_seed_song_is_suggested(self):
        kodi.settings["mix_assist_name_mixes"] = "false"
        self.save("Seed")
        self.assertEqual(kodi.dialogs("keyboard")[0][1], ("Save mix as", "Seed"))
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Seed (5 tracks)")

    def test_renaming_keeps_the_name_where_saving_does(self):
        self.save("Night Drive")
        kodi.respond("select", 3)  # Name
        kodi.respond("keyboard", "Late Night Drive")
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        self.assertEqual(sidecar["name"], "Late Night Drive")
        self.assertNotIn("listener_name", sidecar.get("mix_assist", {}))

    def test_a_name_given_by_an_older_version_is_still_used(self):
        self.save("Cosmic Analog Journeys")
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"]["listener_name"] = "Old Name"
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Old Name (5 tracks)")
        kodi.respond("select", 3)
        kodi.respond("keyboard", "")  # back to the AI's name
        self.run_plugin(action="mix_assist_menu", cache_path=self.cache_path)
        self.assertEqual(main.format_saved_mix_label(self.meta()), "Cosmic Analog Journeys (5 tracks)")

    def test_the_first_screen_says_current_mix(self):
        self.run_plugin()
        labels = [item.getLabel() for _url, item, _folder in kodi.directory_items]
        self.assertIn("Current mix", labels)
        self.assertFalse(any("Cosmic" in label for label in labels))
        item = [item for _url, item, _folder in kodi.directory_items if item.getLabel() == "Current mix"][0]
        self.assertNotIn("Cosmic", item.getLabel2())
        self.assertIn("Checks...", [label for label, _action in item.context_menu])


class NewMixQueueTest(KodiTestCase):
    def queued(self):
        return self.read_json(main.mix_assist_queue_path()).get("entries", [])

    def test_new_mixes_are_queued_once(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS[:3])
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS[:4])  # regenerated: replaces the older request
        self.assertEqual([(e["cache_path"], len(e["tracks"])) for e in self.queued()], [("b.m3u", 3), ("a.m3u", 4)])

    def test_nothing_is_queued_when_switched_off_or_too_short(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS[:1])
        kodi.settings["mix_assist_auto_new_mixes"] = "false"
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS)
        self.assertEqual(self.queued(), [])

    def test_requests_are_taken_oldest_first(self):
        self.assertEqual(main.pop_mix_assist_request(), {})
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        main.queue_mix_assist_for_new_mix("b.m3u", TRACKS)
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "a.m3u")
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "b.m3u")
        self.assertEqual(main.pop_mix_assist_request(), {})


class NewMixGenerationQueueTest(SourceTestCase):
    def test_a_generated_mix_is_queued(self):
        self.source.set_mix(TRACKS[0], TRACKS[1:])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=TRACKS[0], size="20")
        entries = self.read_json(main.mix_assist_queue_path()).get("entries", [])
        self.assertEqual([(e["cache_path"], e["tracks"]) for e in entries],
                         [(main.get_current_mix_cache_path(), TRACKS)])


class ProcessNewMixTest(MixAssistTestCase):
    def request(self):
        return {"cache_path": self.cache_path, "tracks": list(TRACKS)}

    def process(self, result):
        with mock.patch.object(main.mix_assist, "tidy_up", return_value=result) as tidy_up:
            main.process_mix_assist_request(self.request())
        return tidy_up

    def play_mix(self, position):
        playlist = main.get_music_playlist()
        for track in TRACKS:
            playlist.add(track)
        kodi.go_to(position)

    def test_fix_saves_the_replacements_and_notifies(self):
        tidy_up = self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertTrue(tidy_up.call_args[1]["find_replacements"])
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])
        self.assertEqual(self.section()["previous_tracks"], TRACKS)
        self.assertNotified("1 track didn't fit and was replaced")
        self.assertEqual((self.history()[-1]["kind"], self.history()[-1]["automatic"]), ("ai_tidy_up", True))

    def test_a_progress_bar_shows_the_steps(self):
        def tidy_up(*args, **kwargs):
            kwargs["progress"]("Rating new music")
            return plan()

        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=tidy_up):
            main.process_mix_assist_request(self.request())
        calls = [call for call in kodi.dialog_calls if call[0].startswith("progress")]
        self.assertEqual(calls[0], ("progress.create", ("Checking the new mix", ""), {}))
        self.assertIn(("progress.update", (33, "Checking the new mix", "Rating new music"), {}), calls)
        self.assertEqual(calls[-1][0], "progress.close")
        self.assertEqual(self.history()[-1]["kind"], "ai_tidy_up")  # "every track fits" is recorded too

    def test_a_mix_changed_since_it_was_queued_is_skipped(self):
        main.save_mix_by_cache_path(self.cache_path, TRACKS[:3])
        tidy_up = self.process(plan(changes=[REPLACE_DISCO]))
        tidy_up.assert_not_called()
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:3])

    def test_a_mix_changed_during_the_check_is_left_alone(self):
        def tidy_up(*args, **kwargs):
            main.save_mix_by_cache_path(self.cache_path, TRACKS[:3])
            return plan(changes=[REPLACE_DISCO])

        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=tidy_up):
            main.process_mix_assist_request(self.request())
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:3])

    def test_claude_problems_are_reported_without_changes(self):
        error = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        with mock.patch.object(main.mix_assist, "tidy_up", side_effect=error):
            main.process_mix_assist_request(self.request())
        self.assertNotified("Claude's usage limit is reached")
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)

    def test_the_playing_mix_is_patched_after_the_next_track(self):
        self.play_mix(0)
        self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(kodi.playlist_files(), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])

    def test_the_list_is_not_redrawn_while_kodi_loads_one(self):
        kodi.info_labels["Container.PluginName"] = "plugin.audio.incipit"
        kodi.conditions["Container.IsUpdating"] = True
        with mock.patch.object(main.xbmc.Monitor, "waitForAbort", return_value=False):
            self.process(plan(changes=[REPLACE_DISCO]))
        self.assertNotIn("Container.Refresh", kodi.builtins)
        self.assertNotified("1 track didn't fit and was replaced")  # the change itself is done

    def test_a_patched_track_is_labelled_with_its_artist(self):
        kodi.library.add_song(REPLACEMENT, title="Think", artist="Medeski Martin & Wood")
        self.play_mix(0)
        self.process(plan(changes=[REPLACE_DISCO]))
        self.assertIn("Medeski Martin & Wood", kodi.playlist[2][1].getLabel())

    def test_the_playing_track_and_the_next_one_are_never_touched(self):
        self.play_mix(1)  # track 3 (the disco one) is next
        self.process(plan(changes=[REPLACE_DISCO], removed=[5]))
        self.assertEqual(kodi.playlist_files(), TRACKS[:4])
        self.assertEqual(self.read_mix(self.cache_path), [TRACKS[0], TRACKS[1], REPLACEMENT, TRACKS[3]])

    def test_another_playlist_is_not_patched(self):
        main.get_music_playlist().add(TRACKS[0])
        main.get_music_playlist().add(TRACKS[2])
        kodi.go_to(0)
        self.process(plan(changes=[REPLACE_DISCO]))
        self.assertEqual(kodi.playlist_files(), [TRACKS[0], TRACKS[2]])


class MoreLikeThisTest(SourceTestCase):
    NEW = [f"E:\\new\\{n}.mp3" for n in range(6)]

    def setUp(self):
        super().setUp()
        kodi.settings["playlist_size"] = "10"  # More like this adds 20 % = 2 tracks
        kodi.info_labels["Container.PluginName"] = "plugin.audio.incipit"
        self.cache_path = self.save_mix(TRACKS)
        self.source.set_mix(TRACKS[1], [TRACKS[0]] + self.NEW)
        patcher = mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def more_like_this(self, result=None, error=None):
        with mock.patch.object(main.mix_assist, "choose_additions", return_value=result, side_effect=error) as choose:
            self.run_plugin(action="more_like_this", seed=TRACKS[0], size="5", index="1", path=TRACKS[1],
                            cache_path=self.cache_path)
        return choose

    def section(self):
        return self.read_json(main.mix_meta_path_from_cache_path(self.cache_path)).get("mix_assist", {})

    def test_only_tracks_close_to_the_selected_song_are_inserted(self):
        result = {"intent": "dark, abstract", "chosen": [self.NEW[2], self.NEW[4]],
                  "not_fitting": [{"path": self.NEW[0], "label": "New 0", "reason": "too bright"}], "checked": True}
        kodi.settings["mix_reject_size"] = "5"
        choose = self.more_like_this(result)
        args, kwargs = choose.call_args
        self.assertEqual((args[0], args[1], args[2]), (TRACKS[1], self.NEW, 2))  # this song, all new tracks, 2 wanted
        # the final mix around the insertion point, within the artist window
        self.assertEqual((kwargs["before"], kwargs["after"], kwargs["artist_window"]), (TRACKS[:2], TRACKS[2:], 5))
        kodi.settings["mix_reject_size"] = "0"
        self.assertEqual(main.mix_reject_size_for({"mix_generation_parameters": {"rejectsize": 3}}), 3)  # its own
        self.assertEqual(main.mix_reject_size_for({}), 0)  # else the setting's: 0, artists may repeat
        self.assertEqual(self.source.mix_requests()[0]["size"], "75")
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:2] + [self.NEW[2], self.NEW[4]] + TRACKS[2:])
        self.assertNotified("Inserted 2 track(s). The checks skipped 1 that didn't fit (see the mix history).")
        self.assertNotIn("intent", self.section())  # the song's intent is not the mix's
        event = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))["history"][-1]
        self.assertEqual(event["skipped"], [{"track": "New 0", "reason": "too bright"}])
        text = main.build_mix_history_text({"history": [event]})
        self.assertIn("The checks skipped 1 that didn't fit:\n    x New 0 (too bright)", text)

    def test_a_mix_switched_off_gets_musicips_tracks_unchecked(self):
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        sidecar["mix_assist"] = {"openness": main.MIX_OPENNESS_OFF}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), sidecar)
        choose = self.more_like_this({"chosen": [], "not_fitting": [], "checked": True})
        choose.assert_not_called()
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:2] + self.NEW[:2] + TRACKS[2:])

    def test_nothing_fits(self):
        self.more_like_this({"intent": "x", "chosen": [], "checked": True,
                             "not_fitting": [{"path": p, "label": p, "reason": "no"} for p in self.NEW]})
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)
        self.assertNotified("None of the suggested tracks passes the checks.")

    def test_claude_problems_fall_back_to_musicips_tracks(self):
        error = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        self.more_like_this(error=error)
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:2] + self.NEW[:2] + TRACKS[2:])
        self.assertNotified("Claude's usage limit is reached")
        self.assertNotified("Inserted 2 track(s).")

    def test_without_the_claude_cli_more_like_this_works_as_before_and_quietly(self):
        with mock.patch.object(main, "mix_assist_ask", ORIGINAL_ASK):
            self.run_plugin(action="more_like_this", seed=TRACKS[0], size="5", index="1", path=TRACKS[1],
                            cache_path=self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), TRACKS[:2] + self.NEW[:2] + TRACKS[2:])
        self.assertEqual(kodi.notification_messages(), ["Inserted 2 track(s)."])
        self.assertEqual([call[0] for call in kodi.dialog_calls if call[0].startswith("progress")][-1],
                         "progress.close")


class NewMixWithoutCliTest(MixAssistTestCase):
    def test_new_mixes_are_skipped_quietly_without_the_claude_cli(self):
        with mock.patch.object(main, "mix_assist_ask", ORIGINAL_ASK):
            main.process_mix_assist_request({"cache_path": self.cache_path, "tracks": list(TRACKS)})
        self.assertEqual(kodi.notification_messages(), [])
        self.assertEqual(self.read_mix(self.cache_path), TRACKS)


class ServiceTickTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        service.MIX_ASSIST_WORKER = None
        self.addCleanup(setattr, service, "MIX_ASSIST_WORKER", None)
        patcher = mock.patch.object(service, "load_plugin_module", return_value=main)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_queued_mix_is_processed_in_a_background_thread(self):
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        with mock.patch.object(main, "process_mix_assist_request") as process:
            service.run_mix_assist_tick()
            service.MIX_ASSIST_WORKER.join(5)
        self.assertEqual(process.call_args[0][0]["cache_path"], "a.m3u")
        self.assertEqual(main.pop_mix_assist_request(), {})

    def test_one_mix_at_a_time(self):
        busy = mock.Mock(is_alive=mock.Mock(return_value=True))
        service.MIX_ASSIST_WORKER = busy
        main.queue_mix_assist_for_new_mix("a.m3u", TRACKS)
        service.run_mix_assist_tick()
        self.assertIs(service.MIX_ASSIST_WORKER, busy)
        self.assertEqual(main.pop_mix_assist_request()["cache_path"], "a.m3u")

    def test_failures_in_the_worker_are_logged(self):
        with mock.patch.object(main, "process_mix_assist_request", side_effect=RuntimeError("boom")):
            service.run_mix_assist_request(main, {"cache_path": "a.m3u"})  # must not raise


class StepReporterTest(KodiTestCase):
    def test_sub_steps_move_the_bar_within_their_step(self):
        bar = []
        report = main.mix_assist_step_reporter(lambda percent, text: bar.append((percent, text)), main.MIX_ASSIST_STEPS)
        report("Rating new music")
        report("Checking the replacements: rating new music (2 of 4)", 0.35)
        report("Something else")
        self.assertEqual(bar, [(33, "Rating new music"), (89, "Checking the replacements: rating new music (2 of 4)"),
                               (0, "Something else")])


class StrictnessSettingTest(KodiTestCase):
    def test_mixes_and_radio_share_one_scale_but_not_the_setting(self):
        self.assertEqual((main.get_mix_assist_strictness(), main.get_station_strictness()), ((1.2, False), (1.2, False)))
        for value, expected in (("0", (1.0, False)), ("1", (1.1, False)), ("3", (1.35, False)), ("4", (1.5, False)),
                                ("9", (1.5, False)), ("x", (1.2, False)), ("-1", (None, False))):
            kodi.settings["mix_assist_mix_strictness"] = value
            self.assertEqual(main.get_mix_assist_strictness(), expected)
            self.assertEqual(main.get_station_strictness(), (1.2, False))  # independent

    def test_borderline_replacements_are_intents_own_switch(self):
        kodi.settings.update(mix_assist_mix_strictness="4", mix_intent_borderline="true")
        cache_path = self.save_mix(TRACKS)
        meta = main.get_saved_mix_metadata(cache_path, TRACKS)
        with mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}), \
                mock.patch.object(main.mix_assist, "tidy_up", return_value={}) as tidy_up:
            main.compute_mix_assist_plan(TRACKS, meta)
        self.assertEqual((tidy_up.call_args[1]["strictness"], tidy_up.call_args[1]["accept_borderline"]), (1.5, True))

if __name__ == "__main__":
    unittest.main()
