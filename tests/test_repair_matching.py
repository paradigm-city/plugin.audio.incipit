"""Saved-mix repair: filename hints, candidate scoring, library lookups and the repair flows."""

import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, main

MISSING_PATH = (
    "D:\\music\\#metal\\Motorhead\\King Biscuit Flower Hour Presents_ Motorhead (1997)"
    "\\03 Marching Off to War.mp3"
)

ANOTHER_PERFECT_DAY = {
    "file": "D:\\music\\#metal\\Motorhead\\Another Perfect Day (1983)\\07 Marching Off to War.mp3",
    "title": "Marching Off to War",
    "artist": ["Motörhead"],
    "albumartist": ["Motörhead"],
    "album": "Another Perfect Day",
    "year": 1983,
    "track": 7,
}
KING_BISCUIT_RETAGGED = {
    "file": "D:\\music\\#metal\\Motorhead\\King Biscuit (1997)\\03 - Marching Off to War.mp3",
    "title": "Marching Off to War",
    "artist": ["Motörhead"],
    "album": "King Biscuit Flower Hour Presents: Motörhead",
    "year": 1997,
    "track": 3,
}
KING_BISCUIT_OTHER_SONG = {
    "file": "D:\\music\\#metal\\Motorhead\\King Biscuit (1997)\\05 Marching Off to War (Live).mp3",
    "title": "Marching Off to War (Live)",
    "artist": ["Motörhead"],
    "album": "King Biscuit Flower Hour Presents: Motörhead",
    "year": 1997,
    "track": 5,
}
OTHER_MOTORHEAD_SONG = {
    "file": "D:\\music\\#compilations\\Rock Heaven (1997)\\12 Motorhead - Ace of Spades.mp3",
    "title": "Ace of Spades",
    "artist": ["Motörhead"],
    "album": "Rock Heaven",
    "year": 1997,
    "track": 12,
}
# Year-only matches that filled the selection dialog in the original incident.
YEAR_ONLY_JUNK = [
    {
        "file": "D:\\music\\#rock\\Sister Machine Gun\\Metropolis (1997)\\Sister Machine Gun - Metropolis - 32 - This Metal Sky.mp3",
        "title": "This Metal Sky",
        "artist": ["Sister Machine Gun"],
        "album": "Metropolis",
        "year": 1997,
        "track": 32,
    },
    {
        "file": "D:\\music\\#punk_wave_industrial\\Various Artists\\Narcosis (1997)\\1-03 Download - Base Metal.mp3",
        "title": "Base Metal",
        "artist": ["Download"],
        "album": "Narcosis: A Dark Ambient Compilation",
        "year": 1997,
        "track": 3,
    },
    {
        "file": "D:\\music\\#compilations\\#hairmetal\\Absolute Hair Metal Vol. 69\\05 Hollywood Underground - Honey.mp3",
        "title": "Honey",
        "artist": ["Hollywood Underground"],
        "album": "Absolute Hair Metal Vol. 69",
        "year": 1997,
        "track": 5,
    },
]


def add_to_library(*songs):
    for song in songs:
        fields = dict(song)
        kodi.library.add_song(fields.pop("file"), **fields)


def queried_filters():
    """(field, value) of every AudioLibrary.GetSongs "contains" filter sent to Kodi."""
    result = []
    for call in kodi.jsonrpc_calls:
        rule = call["params"].get("filter") or {}
        if call["method"] == "AudioLibrary.GetSongs" and rule.get("operator") == "contains":
            result.append((rule["field"], rule["value"]))
    return result


class SplitLeadingTrackNumberTest(unittest.TestCase):
    def test_cases(self):
        cases = [
            ("03 Marching Off to War", (3, 0, "Marching Off to War", "")),
            ("03 - Title", (3, 0, "Title", "")),
            ("3. Title", (3, 0, "Title", "")),
            ("1-03 Download - Base Metal", (3, 0, "Download - Base Metal", "")),
            ("12 Title Song", (0, 12, "Title Song", "12 Title Song")),
            ("99 Luftballons", (0, 99, "Luftballons", "99 Luftballons")),
            ("Artist - Title", (0, 0, "Artist - Title", "")),
            ("0493 - Metallica - Fuel", (0, 0, "0493 - Metallica - Fuel", "")),
        ]
        for stem, expected in cases:
            with self.subTest(stem=stem):
                self.assertEqual(main.split_leading_track_number(stem), expected)


class TextNormalizationTest(unittest.TestCase):
    def test_match_key_ignores_diacritics(self):
        self.assertEqual(main.repair_match_key("Motörhead"), main.repair_match_key("Motorhead"))

    def test_query_text_keeps_diacritics(self):
        self.assertEqual(main.normalize_repair_text("Motörhead"), "motörhead")

    def test_normalize_strips_extension_year_and_separated_track(self):
        self.assertEqual(main.normalize_repair_text("03 - Marching Off to War (1997).mp3"), "marching off to war")

    def test_normalize_handles_url_encoding_and_lists(self):
        self.assertEqual(main.normalize_repair_text("Marching%20Off%20to%20War.flac"), "marching off to war")
        self.assertEqual(main.normalize_repair_text(["Lemmy", "Motörhead"]), "lemmy motörhead")

    def test_strong_text_match(self):
        self.assertTrue(main.is_strong_text_match("marching off to war", "Marching Off to War"))
        self.assertTrue(main.is_strong_text_match("King Biscuit Flower Hour Presents_ Motorhead", "King Biscuit Flower Hour Presents: Motörhead"))
        self.assertFalse(main.is_strong_text_match("marching off to war", "Ace of Spades"))
        self.assertFalse(main.is_strong_text_match("war", "war pigs"))
        self.assertFalse(main.is_strong_text_match("", "war pigs"))


class HintHelpersTest(unittest.TestCase):
    def test_year_hint(self):
        self.assertEqual(main.extract_year_hint("Another Perfect Day (1983)"), 1983)
        self.assertEqual(main.extract_year_hint("Track 12"), 0)

    def test_artist_title_pairs_are_tried_both_ways(self):
        self.assertEqual(
            main.split_artist_title_hints("Motorhead - Ace of Spades"),
            [("motorhead", "ace of spades"), ("ace of spades", "motorhead")],
        )
        self.assertEqual(main.split_artist_title_hints("Ace of Spades"), [])

    def test_structured_filename_variants(self):
        self.assertEqual(
            main.parse_structured_filename_hints("Motorhead - Ace of Spades - 01 Ace of Spades"),
            {"artist": "motorhead", "album": "ace of spades", "title": "ace of spades", "track_number": 1},
        )
        self.assertEqual(main.parse_structured_filename_hints("Ace of Spades")["title"], "")

    def test_skips_genre_folders_broad_terms_and_years(self):
        directory = "D:\\music\\#metal\\Motorhead\\King Biscuit Flower Hour Presents_ Motorhead (1997)"
        self.assertEqual(
            main.directory_hint_values(directory),
            ["motorhead", "king biscuit flower hour presents motorhead"],
        )


class BuildRepairHintsTest(unittest.TestCase):
    def test_leading_track_number_without_separator(self):
        hints = main.build_repair_hints(MISSING_PATH)
        self.assertEqual(hints["possible_titles"], ["marching off to war"])
        self.assertEqual(hints["track_number"], 3)
        self.assertEqual(hints["possible_track_number"], 0)
        self.assertEqual(hints["year"], 1997)
        self.assertEqual(
            hints["search_terms"],
            ["marching off to war", "motorhead", "king biscuit flower hour presents motorhead"],
        )

    def test_unpadded_number_keeps_both_title_variants(self):
        hints = main.build_repair_hints("D:\\music\\Nena\\Nena (1983)\\99 Luftballons.mp3")
        self.assertEqual(hints["possible_titles"], ["luftballons", "99 luftballons"])
        self.assertEqual(hints["track_number"], 0)
        self.assertEqual(hints["possible_track_number"], 99)

    def test_structured_artist_album_track_title(self):
        hints = main.build_repair_hints("D:\\music\\Sister Machine Gun - Metropolis - 32 - This Metal Sky.mp3")
        self.assertEqual(hints["possible_artists"], ["sister machine gun"])
        self.assertEqual(hints["possible_albums"], ["metropolis"])
        self.assertEqual(hints["possible_titles"], ["this metal sky"])
        self.assertEqual(hints["track_number"], 32)


class ScoreRepairCandidateTest(unittest.TestCase):
    def setUp(self):
        self.hints = main.build_repair_hints(MISSING_PATH)

    def score(self, song):
        score, _reasons, safe_auto = main.score_repair_candidate(song, self.hints)
        return score, safe_auto

    def test_same_song_on_another_release_is_not_penalized_for_track_number(self):
        # +90 title, +20 artist from the "Motorhead" folder; track 7 vs 3 is expected on another album.
        self.assertEqual(self.score(ANOTHER_PERFECT_DAY), (110, True))

    def test_retagged_original_release(self):
        # +90 title, +20 artist, +15 album from folder, +20 year, +40 track.
        self.assertEqual(self.score(KING_BISCUIT_RETAGGED), (185, True))

    def test_track_mismatch_on_same_album_is_penalized(self):
        self.assertEqual(self.score(KING_BISCUIT_OTHER_SONG), (65, False))

    def test_artist_only_match_is_kept_low(self):
        self.assertEqual(self.score(OTHER_MOTORHEAD_SONG), (40, False))

    def test_year_only_match_is_discarded(self):
        for song in YEAR_ONLY_JUNK:
            with self.subTest(file=song["file"]):
                self.assertEqual(self.score(song), (0, False))

    def test_possible_track_number_rewards_but_never_penalizes(self):
        hints = main.build_repair_hints("D:\\music\\Nena\\Nena (1983)\\99 Luftballons.mp3")
        song = {"file": "x.mp3", "title": "99 Luftballons", "artist": ["Nena"], "album": "Nena", "year": 1983}
        self.assertEqual(main.score_repair_candidate(dict(song, track=4), hints)[0], 90 + 20 + 15 + 20)
        self.assertEqual(main.score_repair_candidate(dict(song, track=99), hints)[0], 90 + 20 + 15 + 20 + 40)

    def test_artist_album_and_filename_evidence(self):
        hints = main.build_repair_hints("E:\\x\\Sister Machine Gun - Metropolis - 32 - This Metal Sky.mp3")
        song = {
            "file": "F:\\SMG\\32 - This Metal Sky.mp3", "title": "This Metal Sky",
            "artist": ["Sister Machine Gun"], "album": "Metropolis", "track": 32,
        }
        # title 90, artist 35, album 25, track 40
        self.assertEqual(main.score_repair_candidate(song, hints)[0], 190)
        # "Machine Gun" only partly matches the artist: 20 instead of 35
        self.assertEqual(main.score_repair_candidate(dict(song, artist=["Machine Gun"]), hints)[0], 175)
        # Untagged file: the title is found in the filename (70) and still counts as safe evidence.
        score, _reasons, safe_auto = main.score_repair_candidate({"file": song["file"], "track": 32}, hints)
        self.assertEqual((score, safe_auto), (110, True))

    def test_candidate_label_shows_score_reasons_and_file(self):
        scored = main.score_fallback_repair_candidates([dict(ANOTHER_PERFECT_DAY)], self.hints)
        label = main.format_repair_candidate_label(scored[0])
        self.assertTrue(label.startswith("110 - Motörhead - Marching Off to War - [Another Perfect Day]"))
        self.assertTrue(label.endswith(ANOTHER_PERFECT_DAY["file"]))
        self.assertEqual(main.format_repair_candidate_label({}), "Unknown candidate")


class RepairCandidateLookupTest(KodiTestCase):
    def test_primary_lookup_by_exact_filename(self):
        add_to_library(dict(ANOTHER_PERFECT_DAY, file="E:\\moved\\03 Marching Off to War.mp3"), ANOTHER_PERFECT_DAY)
        candidates = main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertEqual([song["file"] for song in candidates], ["E:\\moved\\03 Marching Off to War.mp3"])
        self.assertEqual(queried_filters(), [])

    def test_genre_folders_and_broad_terms_are_not_queried(self):
        add_to_library(ANOTHER_PERFECT_DAY, *YEAR_ONLY_JUNK)
        main.get_repair_candidates_for_path(MISSING_PATH)
        queried_values = {value for _field, value in queried_filters()}
        self.assertIn(("title", "marching off to war"), queried_filters())
        self.assertNotIn("metal", queried_values)
        self.assertNotIn("music", queried_values)
        self.assertNotIn("03 marching off to war", queried_values)

    def test_other_release_is_offered_first_and_junk_is_dropped(self):
        add_to_library(OTHER_MOTORHEAD_SONG, ANOTHER_PERFECT_DAY, *YEAR_ONLY_JUNK)
        candidates = main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertEqual(
            [song["file"] for song in candidates],
            [ANOTHER_PERFECT_DAY["file"], OTHER_MOTORHEAD_SONG["file"]],
        )

    def test_other_release_is_selectable_but_not_automatic(self):
        add_to_library(OTHER_MOTORHEAD_SONG, ANOTHER_PERFECT_DAY, *YEAR_ONLY_JUNK)
        candidates = main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), "")

        kodi.respond("select", 1)  # index 0 is "Skip this track"
        self.assertEqual(main.choose_repair_candidate(MISSING_PATH, candidates), ANOTHER_PERFECT_DAY["file"])
        _method, (heading, labels), _kwargs = kodi.dialogs("select")[0]
        self.assertEqual(heading, "Repair missing track: 03 Marching Off to War")
        self.assertEqual(labels[0], "Skip this track")

    def test_original_release_is_repaired_automatically(self):
        add_to_library(KING_BISCUIT_RETAGGED, KING_BISCUIT_OTHER_SONG, ANOTHER_PERFECT_DAY, OTHER_MOTORHEAD_SONG, *YEAR_ONLY_JUNK)
        candidates = main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertEqual(candidates[0]["file"], KING_BISCUIT_RETAGGED["file"])
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), KING_BISCUIT_RETAGGED["file"])
        self.assertEqual(kodi.dialogs("select"), [])

    def test_no_candidates(self):
        add_to_library(*YEAR_ONLY_JUNK)
        candidates = main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertEqual(candidates, [])
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), "")
        self.assertEqual(main.choose_repair_candidate(MISSING_PATH, candidates), "")

    def test_metadata_lookup_retries_with_safe_properties(self):
        add_to_library(ANOTHER_PERFECT_DAY)
        kodi.fail_jsonrpc("AudioLibrary.GetSongs", times=1)
        songs = main.query_library_songs_by_filename("07 Marching Off to War.mp3")
        self.assertEqual(len(songs), 1)
        self.assertEqual(kodi.jsonrpc_calls[1]["params"]["properties"], main.SONG_METADATA_SAFE_PROPERTIES)

    def test_metadata_lookup_gives_up_after_both_attempts_fail(self):
        kodi.fail_jsonrpc("AudioLibrary.GetSongs", times=2)
        self.assertEqual(main.query_library_songs_by_filename("x.mp3"), [])


class ChooseUnscoredCandidateTest(KodiTestCase):
    """Primary (exact filename) candidates carry no score."""

    def test_single_candidate_is_selected_automatically(self):
        candidates = [{"file": "E:\\moved\\03 Marching Off to War.mp3"}]
        self.assertEqual(main.choose_repair_candidate(MISSING_PATH, candidates), candidates[0]["file"])
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), candidates[0]["file"])

    def test_unique_tail_match_wins_among_several(self):
        candidates = [
            {"file": "E:\\a\\03 Marching Off to War.mp3"},
            {"file": "E:\\Motorhead\\King Biscuit Flower Hour Presents_ Motorhead (1997)\\03 Marching Off to War.mp3"},
        ]
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), candidates[1]["file"])

    def test_ambiguous_candidates_need_a_person(self):
        candidates = [{"file": "E:\\a\\03 Marching Off to War.mp3"}, {"file": "E:\\b\\03 Marching Off to War.mp3"}]
        self.assertEqual(main.choose_repair_candidate_automatic_only(MISSING_PATH, candidates), "")

        kodi.respond("select", 2)
        self.assertEqual(main.choose_repair_candidate(MISSING_PATH, candidates), candidates[1]["file"])

    def test_skip_and_cancel(self):
        candidates = [{"file": "E:\\a\\x.mp3"}, {"file": "E:\\b\\x.mp3"}]
        kodi.respond("select", 0)
        self.assertEqual(main.choose_repair_candidate(MISSING_PATH, candidates), "")

        kodi.respond("select", -1)
        with self.assertRaisesRegex(main.MusicIPError, "cancelled"):
            main.choose_repair_candidate(MISSING_PATH, candidates)


class RepairSavedMixTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.present = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
        kodi.add_media(self.present)
        self.cache_path = self.save_mix([self.present, MISSING_PATH], seed=self.present, size=20)

    def test_foreground_repair_replaces_missing_track_and_rechecks(self):
        add_to_library(KING_BISCUIT_RETAGGED)
        self.assertEqual(main.repair_saved_mix_foreground(self.cache_path), 1)
        self.assertEqual(self.read_mix(self.cache_path), [self.present, KING_BISCUIT_RETAGGED["file"]])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        self.assertEqual(sidecar["consistency"]["status"], "ok")

    def test_foreground_repair_with_manual_choice(self):
        add_to_library(ANOTHER_PERFECT_DAY, OTHER_MOTORHEAD_SONG)
        kodi.respond("select", 1)
        self.assertEqual(main.repair_saved_mix_foreground(self.cache_path), 1)
        self.assertEqual(self.read_mix(self.cache_path)[1], ANOTHER_PERFECT_DAY["file"])

    def test_foreground_repair_without_result_raises_and_records_inconsistency(self):
        with self.assertRaisesRegex(main.MusicIPError, "No tracks were repaired"):
            main.repair_saved_mix_foreground(self.cache_path)
        self.assertEqual(self.read_mix(self.cache_path), [self.present, MISSING_PATH])
        consistency = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))["consistency"]
        self.assertEqual(consistency["status"], "inconsistent")
        self.assertEqual(consistency["missing"][0]["path"], MISSING_PATH)

    def test_automatic_repair_only_takes_safe_matches(self):
        add_to_library(ANOTHER_PERFECT_DAY)
        self.assertEqual(main.repair_saved_mix_automatic_only(self.cache_path), 0)
        self.assertEqual(self.read_mix(self.cache_path), [self.present, MISSING_PATH])
        self.assertEqual(kodi.dialogs("select"), [])

        add_to_library(KING_BISCUIT_RETAGGED)
        self.assertEqual(main.repair_saved_mix_automatic_only(self.cache_path), 1)
        self.assertEqual(self.read_mix(self.cache_path)[1], KING_BISCUIT_RETAGGED["file"])

    def test_repair_keeps_the_saved_timestamp_used_for_ordering(self):
        sidecar_path = main.mix_meta_path_from_cache_path(self.cache_path)
        sidecar = self.read_json(sidecar_path)
        sidecar["updated_ts"] = 1_600_000_000
        self.write_json(sidecar_path, sidecar)
        add_to_library(KING_BISCUIT_RETAGGED)

        main.repair_saved_mix_foreground(self.cache_path)
        sidecar = self.read_json(sidecar_path)
        self.assertEqual(sidecar["updated_ts"], 1_600_000_000)
        self.assertGreaterEqual(sidecar["modified_ts"], int(time.time()) - 5)

    def test_empty_mix(self):
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            handle.write("")
        with self.assertRaisesRegex(main.MusicIPError, "empty"):
            main.repair_saved_mix_foreground(self.cache_path)
        self.assertEqual(main.repair_saved_mix_automatic_only(self.cache_path), 0)


class RepairLoggingTest(KodiTestCase):
    def test_saved_mix_check_logging_controls_repair_logs(self):
        main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertNotIn("Auto-repair", kodi.log_text())

        kodi.settings["log_checks"] = "true"
        main.get_repair_candidates_for_path(MISSING_PATH)
        self.assertIn("Auto-repair: primary lookup by exact filename", kodi.log_text())


if __name__ == "__main__":
    unittest.main()
