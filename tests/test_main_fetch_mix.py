"""Mixes from the source (the sound engine): the seed first, errors, the parameters asked for; MusicIP's dormant code."""

import os
import py_compile
import tempfile
import unittest
from unittest import mock

from fake_kodi import ADDON_DIR, kodi
from support import KodiTestCase, SourceTestCase, main

SEED = "D:\\music\\Motörhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
TRACKS = [
    "D:\\music\\Motörhead\\Overkill (1979)\\01 Overkill.mp3",
    "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3",
]


class FetchMixTest(SourceTestCase):
    def test_fetches_mix_with_seed_first(self):
        kodi.settings.update(mix_variety="3", mix_reject_size="4")
        self.source.set_mix(SEED, TRACKS)
        self.assertEqual(main.fetch_mix(SEED, 20), [SEED] + TRACKS)
        self.assertEqual(self.source.mix_requests(), [{"song": SEED, "size": "20", "rejectsize": "4", "variety": "3"}])

    def test_seed_returned_by_the_source_is_not_duplicated(self):
        self.source.set_mix(SEED, [SEED.replace("\\", "/"), TRACKS[0], TRACKS[0]])
        self.assertEqual(main.fetch_mix(SEED, 20), [SEED, TRACKS[0]])

    def test_empty_mix_is_an_error(self):
        with self.assertRaisesRegex(main.MusicIPError, "empty mix"):
            main.fetch_mix(SEED, 20)

    def test_a_failure_is_an_error(self):
        self.source.mix_status = 500
        with self.assertRaisesRegex(main.MusicIPError, "The sound engine failed"):
            main.fetch_mix(SEED, 20)

    def test_fetch_with_defaults_remembers_parameters(self):
        self.source.set_mix(SEED, TRACKS)
        main.fetch_mix_with_defaults(SEED, 15)
        self.assertEqual(self.source.mix_requests()[0]["size"], "15")
        self.assertEqual(main.pop_mix_generation_parameters(SEED, 15), {"size": 15, "variety": 0, "rejectsize": 0})

    def test_confirmed_fetch_uses_edited_parameters(self):
        self.source.set_mix(SEED, TRACKS)
        kodi.respond("select", 1, 0)
        kodi.respond("numeric", "5")
        main.fetch_mix_confirmed(SEED, 20)
        self.assertEqual(self.source.mix_requests()[0]["size"], "5")
        self.assertEqual(main.pop_mix_generation_parameters(SEED, 20)["size"], 5)

    def test_the_dialog_offers_size_variety_and_artist_repeat_only(self):
        kodi.respond("select", -1)
        with self.assertRaisesRegex(main.MusicIPError, "cancelled"):
            main.fetch_mix_confirmed(SEED, 20)
        heading, choices = kodi.dialogs("select")[0][1][:2]
        self.assertEqual(heading, "Generate mix")
        self.assertEqual(choices[:main.MIX_ASSIST_DIALOG_FIRST],
                         ["Generate mix", "Size: 20 tracks", "Variety: 0", "Artist repeat: disabled"])
        self.assertEqual(self.source.requests, [])


class SetUpTest(KodiTestCase):
    def test_a_sound_engine_that_is_not_set_up_says_where_to_set_it_up(self):
        error = main.soundprint.SoundprintError(main.soundprint.NOT_SET_UP, "The sound engine isn't set up yet.")
        with mock.patch.object(main.soundprint, "neighbours", side_effect=error):
            with self.assertRaises(main.MusicIPError) as caught:
                main.fetch_mix(SEED, 20)
        self.assertEqual(str(caught.exception), f"The sound engine isn't set up yet. {main.SOUND_ENGINE_SETUP_HINT}")


class ParametersTest(unittest.TestCase):
    def test_prepend_seed_track(self):
        self.assertEqual(main.prepend_seed_track(" a.mp3 ", ["b.mp3", "", "a.mp3", "b.mp3"]), ["a.mp3", "b.mp3"])
        self.assertEqual(main.prepend_seed_track("", ["b.mp3"]), ["b.mp3"])

    def test_a_mix_made_by_musicip_is_described_with_its_style_and_filter(self):
        old = {"size": 20, "style_ui": 5, "style": 100, "variety": 2, "filter": "", "rejectsize": 3}
        self.assertTrue(main.made_by_musicip(old))
        self.assertEqual(main.describe_mix_parameters(old),
                         "variety 2, style 5/10, no artist repeat within 3 tracks, no filter")
        new = {"size": 20, "variety": 2, "rejectsize": 0}
        self.assertFalse(main.made_by_musicip(new))
        self.assertEqual(main.describe_mix_parameters(new), "variety 2, artists may repeat")
        self.assertEqual(main.normalize_mix_parameters(old)["style_ui"], 5)  # kept as recorded


class DormantMusicIPTest(unittest.TestCase):
    def test_musicips_code_is_kept_in_one_file_nothing_imports(self):
        path = os.path.join(ADDON_DIR, "musicip_dormant.py")
        py_compile.compile(path, cfile=os.path.join(tempfile.mkdtemp(), "dormant.pyc"), doraise=True)
        for name in ("main.py", "service.py"):
            with open(os.path.join(ADDON_DIR, name), encoding="utf-8") as handle:
                self.assertNotIn("import musicip_dormant", handle.read())


if __name__ == "__main__":
    unittest.main()
