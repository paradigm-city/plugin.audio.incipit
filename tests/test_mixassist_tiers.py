"""The checks after the source, each of which can be off: Character (the profile, on the seed's fixed scale when its
nearest songs by sound are known, F40) and Intent (the AI's judgement); and their settings in Kodi."""

import os
import unittest
from unittest import mock
from xml.etree import ElementTree

from fake_kodi import ADDON_DIR, kodi
from support import KodiTestCase, main, service
import test_mixassist_tidy_up as tidy  # its AssistTest's fixture, not its tests

from mixassist import assist


class TierTest(unittest.TestCase):
    """The seed, fitting tracks and clear outliers of AssistTest."""

    setUp, add, resolve = tidy.AssistTest.setUp, tidy.AssistTest.add, tidy.AssistTest.resolve
    ask, fetch_mix = tidy.AssistTest.ask, tidy.AssistTest.fetch_mix

    def counting_ask(self):
        calls = []

        def ask(system, schema, message):
            calls.append(message)
            return self.ask(system, schema, message)
        return ask, calls

    def test_with_intent_off_the_profile_alone_decides_without_asking_the_ai(self):
        ask, calls = self.counting_ask()
        plan = assist.tidy_up(self.paths, self.store, ask, self.resolve, self.fetch_mix, artist_window=0,
                              perspective=None)
        self.assertEqual(calls, [])
        statuses = {row["unit"]["label"]: row["status"] for row in plan["rows"]}
        self.assertEqual((statuses["bad1"], statuses["bad2"]), ("outlier", "outlier"))
        self.assertEqual((plan["intent"], plan["perspective"], plan["name"]), ("", "", ""))
        self.assertTrue(set(change["new"] for change in plan["changes"]) <= {"cand1", "cand2", "cand3", "cand4"})

    def test_with_character_off_the_ai_alone_decides(self):
        self.add("bad1", exploration=9, form=1)  # the profile would let it in; the AI still turns it down
        plan = assist.tidy_up(self.paths, self.store, self.ask, self.resolve, self.fetch_mix, artist_window=0,
                              strictness=None)
        statuses = {row["unit"]["label"]: row["status"] for row in plan["rows"]}
        self.assertEqual((statuses["bad1"], statuses["bad2"]), ("outlier", "outlier"))
        self.assertNotIn("relative", plan["rows"][5])

    def test_more_like_this_with_intent_off_takes_what_the_profile_lets_in(self):
        ask, calls = self.counting_ask()
        result = assist.choose_additions("seed", ["candbad", "cand3", "cand1", "cand2", "cand4"], 2, self.store, ask,
                                         self.resolve, artist_window=0, perspective=None)
        self.assertEqual(calls, [])
        self.assertEqual(result["chosen"], ["cand3", "cand1"])
        self.assertIn("Intent is off", result["not_fitting"][0]["reason"])

    def test_more_like_this_with_character_off_takes_what_the_ai_lets_in(self):
        self.add("cand9", exploration=1, form=10)  # far off in profile, but the AI says it fits
        result = assist.choose_additions("seed", ["candbad", "cand9", "cand1"], 2, self.store, self.ask, self.resolve,
                                         artist_window=0, strictness=None)
        self.assertEqual(result["chosen"], ["cand9", "cand1"])

    def test_passes_with_either_check_off(self):
        far = {"relative": 3.0, "single": "", "verdict": "fits"}
        self.assertFalse(assist.passes(far, 1.2))
        self.assertTrue(assist.passes(far, None))
        unjudged = {"relative": 0.5, "single": "", "verdict": ""}
        self.assertFalse(assist.passes(unjudged, 1.2))
        self.assertTrue(assist.passes(unjudged, 1.2, judged=False))
        self.assertTrue(assist.passes({"verdict": "borderline"}, None, accept_borderline=True))

    def test_a_loose_list_is_measured_on_the_seeds_fixed_scale(self):
        loose = ["seed"] + [f"loose{index}" for index in range(8)]
        for index in range(8):  # every song a little further off than the seed's neighbours are
            self.add(f"loose{index}", exploration=6 + index % 2, form=4 - index % 2)
        own = assist.analyze(self.resolve(loose), [self.store.get(f"key:{p}") for p in loose], {},
                             self.store.library(), 1.2, None)
        near = [self.store.get(f"key:fit{index}") for index in range(1, 9)]
        fixed = assist.analyze(self.resolve(loose), [self.store.get(f"key:{p}") for p in loose], {},
                               self.store.library(), 1.2, None, scale_entries=near)
        self.assertEqual((own["scale"], fixed["scale"]), ("list", "fixed"))
        passing = lambda analysis: sum(row["status"] == "fits" for row in analysis["rows"][1:])
        self.assertGreater(passing(own), passing(fixed))  # the list's own scale makes it look closer than it is

    def test_too_few_rated_neighbours_fall_back_to_the_lists_own_scale(self):
        entries = [self.store.get(f"key:{p}") for p in self.paths]
        self.assertIsNone(assist.character_scale(entries[0], entries[1:4], self.store.library(), ("energy",)))
        analysis = assist.analyze(self.resolve(self.paths), entries, {}, self.store.library(), 1.2, None,
                                  scale_entries=entries[1:4])
        self.assertEqual(analysis["scale"], "list")


class CharacterReferenceTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        main.CHARACTER_SCALES.clear()
        self.addCleanup(main.CHARACTER_SCALES.clear)

    def test_the_seeds_nearest_rated_songs_once_per_seed(self):
        answer = {"songs": [{"path": f"n{index}.mp3"} for index in range(4)]}
        units = [{"key": "seed"}, {"key": "a"}, {"key": "seed"}, {"key": "b"}, {"key": "c"}]
        store = mock.Mock()
        store.get.side_effect = lambda key: {"a": {"energy": 1}, "c": {"energy": 3}}.get(key)
        with mock.patch.object(main.soundprint, "neighbours", return_value=answer) as neighbours, \
                mock.patch.object(main.mix_assist_library, "resolve", return_value=units):
            entries = main.character_reference("seed.mp3", store)
            self.assertEqual(main.character_reference("seed.mp3", store), entries)
        self.assertEqual(entries, [{"energy": 1}, {"energy": 3}])  # the seed's own album and unrated ones left out
        self.assertEqual(neighbours.call_count, 1)
        self.assertEqual(neighbours.call_args[0][2:], ("seed.mp3", main.CHARACTER_SCALE_SONGS, 0, 0))

    def test_without_the_sound_engine_there_is_none(self):
        self.log_everything()
        error = main.soundprint.SoundprintError(main.soundprint.NOT_SET_UP, "not set up")
        with mock.patch.object(main.soundprint, "neighbours", side_effect=error):
            self.assertEqual(main.character_reference("seed.mp3", mock.Mock()), [])
        self.assertIn("the tracks' own scale is used", kodi.log_text())


class TierSettingsTest(KodiTestCase):
    def options(self, setting):
        root = ElementTree.parse(os.path.join(ADDON_DIR, "resources", "settings.xml")).getroot()
        node = next(node for node in root.iter("setting") if node.get("id") == setting)
        return [option.text for option in node.iter("option")]

    def test_character_and_intent_can_be_off_for_mixes_and_radio(self):
        for setting in ("mix_assist_mix_strictness", "mix_assist_station_strictness"):
            self.assertEqual(self.options(setting), ["-1", "0", "1", "2", "3", "4"])
        for setting in ("mix_assist_mix_perspective", "mix_assist_station_perspective"):
            self.assertEqual(self.options(setting), ["-1", "0", "1", "2", "3", "4", "5"])
        kodi.settings.update(mix_assist_mix_strictness="-1", mix_assist_mix_perspective="-1")
        self.assertEqual(main.get_mix_assist_strictness(), (None, False))
        self.assertIsNone(main.perspective_key(main.default_mix_perspective()))
        self.assertEqual(main.perspective_label(main.CHECK_OFF), "Off")

    def test_a_station_with_both_checks_off_is_not_checked(self):
        with mock.patch.object(main, "mix_assist_available", return_value=True):
            self.assertTrue(main.mix_assist_for_radio())
            kodi.settings.update(mix_assist_station_strictness="-1")
            self.assertTrue(main.mix_assist_for_radio())  # Intent still on
            kodi.settings.update(mix_assist_station_perspective="-1")
            self.assertFalse(main.mix_assist_for_radio())
        self.assertFalse(main.station_checks_on({"openness": -1, "perspective": -1}))
        self.assertEqual(main.radio_check_batches({"openness": -1}), main.RADIO_CHECK_BATCHES[2])


class BorderlineMigrationTest(KodiTestCase):
    def stored(self, **values):
        root = ElementTree.Element("settings", version="2")
        for setting, value in values.items():
            ElementTree.SubElement(root, "setting", id=setting).text = value
        os.makedirs(kodi.profile_dir(), exist_ok=True)
        ElementTree.ElementTree(root).write(os.path.join(kodi.profile_dir(), "settings.xml"), encoding="utf-8")

    def test_adventurous_keeps_taking_borderline_songs(self):
        self.stored(mix_assist_mix_strictness="4", mix_assist_station_strictness="2")
        self.assertEqual(service.migrate_intent_borderline(), {"mix_intent_borderline": "true"})
        self.assertTrue(main.mix_accepts_borderline())
        self.assertFalse(main.station_accepts_borderline())
        self.assertEqual(service.migrate_intent_borderline(), {})  # only once


if __name__ == "__main__":
    unittest.main()
