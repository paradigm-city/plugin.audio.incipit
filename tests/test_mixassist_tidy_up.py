"""AI Mix Assist: library resolution, rating, the AI checks and tidying up a mix (with stand-ins for Kodi,
MusicIP and Claude)."""

import os
import sys
import tempfile
import unittest

from fake_kodi import ADDON_DIR

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

from mixassist import assist, cache, checks, claude, dimensions, library, rating  # noqa: E402


def vector(**values):
    base = {key: 5 for key in dimensions.SCALE_KEYS}
    base.update({dimensions.ERA_KEY: 1990, "familiarity": 1, "character": "x"})
    base.update(values)
    return base


class FakeJsonRpc:
    """Kodi's AudioLibrary with a few songs and albums."""

    def __init__(self, songs, albums):
        self.songs, self.albums = songs, albums

    def __call__(self, method, params):
        if method == "AudioLibrary.GetSongs":
            wanted = params["filter"]
            if "albumid" in wanted:
                return {"songs": [s for s in self.songs if s["albumid"] == wanted["albumid"]]}
            name = wanted["value"].lower()
            return {"songs": [s for s in self.songs if s["file"].replace("\\", "/").split("/")[-1].lower() == name]}
        if method == "AudioLibrary.GetAlbumDetails":
            return {"albumdetails": self.albums[params["albumid"]]}
        raise AssertionError(method)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        songs = [
            {"file": "D:\\m\\Blue\\09 A Case of You.mp3", "title": "A Case of You", "displayartist": "Joni Mitchell",
             "albumid": 1, "year": 1971, "genre": ["Folk"], "musicbrainztrackid": "rec-1", "track": 9},
            {"file": "D:\\m\\Blue\\01 All I Want.mp3", "title": "All I Want", "displayartist": "Joni Mitchell",
             "albumid": 1, "year": 1971, "genre": ["Folk"], "musicbrainztrackid": "", "track": 1},
            {"file": "D:\\m\\VA\\Hits\\05 Fire Walk.mp3", "title": "fire walk", "displayartist": "wilfried",
             "albumid": 2, "year": 1979, "genre": [], "musicbrainztrackid": "", "track": 5},
        ]
        albums = {
            1: {"albumid": 1, "title": "Blue", "displayartist": "Joni Mitchell", "year": 1971, "genre": ["Folk"],
                "musicbrainzreleasegroupid": "rg-blue", "compilation": False},
            2: {"albumid": 2, "title": "Austrian Funk Nuggets", "displayartist": "Various Artists", "year": 0,
                "genre": [], "musicbrainzreleasegroupid": "", "compilation": True},
        }
        self.jsonrpc = FakeJsonRpc(songs, albums)

    def test_normal_albums_are_rated_as_a_whole(self):
        unit = library.resolve(["d:/M/Blue/09 A Case of You.mp3"], self.jsonrpc)[0]
        self.assertEqual((unit["kind"], unit["key"]), ("album", "rg:rg-blue"))
        self.assertEqual(unit["item"]["tracks"], ["All I Want", "A Case of You"])
        self.assertEqual(unit["item"]["genres"], "Folk")
        self.assertEqual(unit["path"], "d:/M/Blue/09 A Case of You.mp3")

    def test_compilation_tracks_are_their_own_units(self):
        unit = library.resolve(["D:\\m\\VA\\Hits\\05 Fire Walk.mp3"], self.jsonrpc)[0]
        self.assertEqual((unit["kind"], unit["key"]), ("track", cache.track_key("wilfried", "fire walk")))
        self.assertEqual(unit["item"]["album"], "Austrian Funk Nuggets")
        self.assertEqual(unit["item"]["year"], 1979)

    def test_unknown_tracks_fall_back_to_recorded_metadata_or_the_file_name(self):
        recorded = {"d:/m/x/reducers - airways.mp3": {"artist": ["Reducers"], "title": "Airways", "year": 1980}}
        units = library.resolve(["D:\\m\\x\\REDUCERS - Airways.mp3", "D:\\m\\x\\Who - Else.mp3"], self.jsonrpc, recorded)
        self.assertEqual(units[0]["key"], cache.track_key("Reducers", "Airways"))
        self.assertEqual(units[0]["item"]["year"], 1980)
        self.assertEqual(units[1]["key"], cache.track_key("Who", "Else"))


class RatingTest(unittest.TestCase):
    def setUp(self):
        self.store = cache.RatingCache(os.path.join(tempfile.mkdtemp(), "ratings.db"))

    def unit(self, key, kind="album"):
        return {"key": key, "kind": kind, "label": key, "item": {"artist": "a", "album": key, "year": 1990,
                                                                   "genres": "", "tracks": []}}

    def test_batches_drop_duplicates_and_respect_sizes(self):
        units = [self.unit(f"rg:{i}") for i in range(45)] + [self.unit("rg:0")] + [self.unit("rec:1", "track")]
        groups = rating.batches(units)
        self.assertEqual([(kind, len(group)) for kind, group in groups], [("album", 20), ("album", 20), ("album", 5),
                                                                          ("track", 1)])

    def test_parse_ratings_clamps_and_drops_incomplete_entries(self):
        payload = {"ratings": [dict(vector(energy=14, sounding_year=1850, familiarity=7), id="u0"),
                               {"id": "u1", "energy": 3}, dict(vector(), id="zzz")]}
        ratings = rating.parse_ratings(payload, ["u0", "u1"])
        self.assertEqual(list(ratings), ["u0"])
        self.assertEqual((ratings["u0"]["energy"], ratings["u0"]["sounding_year"], ratings["u0"]["familiarity"]),
                         (10, 1900, 2))
        self.assertEqual(ratings["u0"]["description"], "x")

    def test_only_uncached_units_are_rated(self):
        self.store.put("rg:cached", vector(), model="m", source="test")
        asked = []

        def ask(system, schema, message):
            asked.append(message)
            return {"ratings": [dict(vector(energy=7), id="u0")]}

        stored = rating.rate_missing([self.unit("rg:cached"), self.unit("rg:new")], self.store, ask)
        self.assertEqual(stored, 1)
        self.assertEqual(len(asked), 1)
        self.assertIn('"album": "rg:new"', asked[0])
        self.assertNotIn("rg:cached", asked[0])
        self.assertEqual(self.store.get("rg:new")["energy"], 7)

    def test_usage_limit_keeps_what_was_rated_and_reports_afterwards(self):
        def ask(system, schema, message):
            if '"album": "rg:20"' in message:  # the second batch hits the limit
                raise claude.ClaudeError(claude.USAGE_LIMIT, "limit reached")
            return {"ratings": [dict(vector(), id=f"u{i}") for i in range(20)]}

        units = [self.unit(f"rg:{i}") for i in range(25)]  # two batches: 20 and 5
        with self.assertRaises(claude.ClaudeError) as caught:
            rating.rate_missing(units, self.store, ask, parallel=1)
        self.assertEqual(caught.exception.kind, claude.USAGE_LIMIT)
        self.assertIsNotNone(self.store.get("rg:0"))
        self.assertIsNone(self.store.get("rg:20"))


class ChecksTest(unittest.TestCase):
    def unit(self, artist, title):
        return {"key": title, "kind": "track", "label": f"{artist} – {title}",
                "item": {"artist": artist, "title": title, "album": "A", "year": 1990}}

    def test_state_intent_numbers_tracks_from_the_seed(self):
        seen = {}

        def ask(system, schema, message):
            seen.update(system=system, message=message)
            return {"character": "dark and abstract", "tracks": [
                {"position": 1, "verdict": "fits", "reason": ""}, {"position": 2, "verdict": "outlier", "reason": "bright"},
                {"position": 9, "verdict": "fits", "reason": ""}, {"position": 3, "verdict": "maybe", "reason": ""}]}

        units = [self.unit("Seed", "s"), self.unit("Other", "o"), self.unit("Third", "t")]
        intent, verdicts = checks.state_intent(units, [{"description": "dark"}, None, None], ask)
        self.assertEqual(intent, "dark and abstract")
        self.assertEqual(verdicts, {1: {"verdict": "fits", "reason": ""}, 2: {"verdict": "outlier", "reason": "bright"}})
        self.assertIs(seen["system"], checks.SEED_INTENT_PROMPT)
        self.assertTrue(seen["message"].startswith("1. Seed – s (A, 1990) — dark"))

    def test_judge_uses_the_given_intent(self):
        seen = {}

        def ask(system, schema, message):
            seen["message"] = message
            return {"character": "x", "tracks": [{"position": 1, "verdict": "fits", "reason": ""}]}

        verdicts = checks.judge("my own words", self.unit("Seed", "s"), None, [self.unit("Cand", "c")], [None], ask)
        self.assertEqual(verdicts, {1: {"verdict": "fits", "reason": ""}})
        self.assertTrue(seen["message"].startswith("Intent: my own words"))
        self.assertIn("Seed: Seed – s", seen["message"])
        self.assertIn("1. Cand – c", seen["message"])


class NameTest(unittest.TestCase):
    def unit(self, title):
        return {"key": title, "kind": "track", "label": title, "item": {"artist": "A", "title": title, "album": "B"}}

    def test_describe_asks_for_a_name_in_the_same_call(self):
        calls = []

        def ask(system, schema, message):
            calls.append((system, schema))
            return {"character": "cosmic", "name": '  "Cosmic   Analog Journeys" ', "tracks": []}

        intent, verdicts, name = checks.describe([self.unit("s")], [None], ask)
        self.assertEqual((intent, name, len(calls)), ("cosmic", "Cosmic Analog Journeys", 1))
        self.assertIn(checks.NAME_NOTE, calls[0][0])
        self.assertIn("name", calls[0][1]["required"])

    def test_judge_named_uses_the_given_intent(self):
        def ask(system, schema, message):
            return {"character": "x", "name": "Night Drive", "tracks": [{"position": 1, "verdict": "fits", "reason": ""}]}

        verdicts, name = checks.judge_named("my words", self.unit("s"), None, [self.unit("c")], [None], ask)
        self.assertEqual((verdicts[1]["verdict"], name), ("fits", "Night Drive"))

    def test_unusable_names_are_dropped(self):
        self.assertEqual(checks.parse_name({"name": ""}), "")
        self.assertEqual(checks.parse_name({}), "")
        self.assertEqual(checks.parse_name({"name": "x" * 80}), "")
        self.assertEqual(checks.schema()["required"], ["character", "tracks"])  # judging candidates needs no name


class AssistTest(unittest.TestCase):
    """A seed with a clear profile, fitting tracks, and two tracks that clearly don't fit."""

    def setUp(self):
        self.store = cache.RatingCache(os.path.join(tempfile.mkdtemp(), "ratings.db"))
        for index in range(60):  # a library reference with spread on every dimension
            self.store.put(f"rg:lib{index}", vector(energy=index % 10, exploration=(index * 3) % 10,
                                                    mood=(index * 7) % 10, form=(index * 9) % 10,
                                                    sounding_year=1960 + index), model="m", source="test")
        self.profiles = {}
        self.add("seed", exploration=9, form=1)
        for index in range(1, 9):
            self.add(f"fit{index}", exploration=9 - index % 2, form=1 + index % 2)
        self.add("bad1", exploration=2, form=9, mood=8)
        self.add("bad2", exploration=1, form=10, mood=9)
        for index in range(1, 5):
            self.add(f"cand{index}", exploration=9, form=1)
        self.add("candbad", exploration=1, form=9)
        self.paths = ["seed"] + [f"fit{i}" for i in range(1, 5)] + ["bad1"] + [f"fit{i}" for i in range(5, 9)] + ["bad2"]

    def add(self, name, **values):
        self.profiles[name] = values
        self.store.put(f"key:{name}", vector(**values), model="m", source="test")

    def resolve(self, paths):
        return [{"key": f"key:{p}", "kind": "album", "label": p, "artist": p.rstrip("0123456789"), "path": p,
                 "item": {"artist": p, "album": p, "year": 1990}} for p in paths]

    def ask(self, system, schema, message):
        lines = [line for line in message.split("\n") if line[:1].isdigit()]
        tracks = []
        for line in lines:
            number, name = line.split(".", 1)[0], line.split("– ")[1].split(" (")[0]
            verdict = "outlier" if "bad" in name else "fits"
            tracks.append({"position": int(number), "verdict": verdict, "reason": "clashes" if verdict != "fits" else ""})
        return {"character": "abstract, instrumental", "tracks": tracks}

    def fetch_mix(self, seed, size):
        return [seed, "cand1", "cand2", "candbad", "fit1", "cand3", "cand4"]

    def test_clear_outliers_are_replaced_from_submixes(self):
        plan = assist.tidy_up(self.paths, self.store, self.ask, self.resolve, self.fetch_mix, artist_window=0)
        statuses = {row["unit"]["label"]: row["status"] for row in plan["rows"]}
        self.assertEqual(statuses["seed"], "seed")
        self.assertEqual((statuses["bad1"], statuses["bad2"]), ("outlier", "outlier"))
        self.assertTrue(all(statuses[f"fit{i}"] == "fits" for i in range(1, 9)))
        self.assertEqual(plan["intent"], "abstract, instrumental")
        self.assertEqual(plan["intent_source"], "ai")
        replaced = {change["old"]: change["new"] for change in plan["changes"]}
        self.assertEqual(set(replaced), {"bad1", "bad2"})
        self.assertTrue(set(replaced.values()) <= {"cand1", "cand2", "cand3", "cand4"})
        self.assertEqual(len(set(replaced.values())), 2)
        self.assertEqual(len(plan["paths"]), len(self.paths))
        self.assertNotIn("candbad", plan["paths"])

    def test_progress_reports_the_parts_of_long_steps(self):
        reports = []
        assist.tidy_up(self.paths, self.store, self.ask, self.resolve, self.fetch_mix, artist_window=0,
                       progress=lambda text, fraction=None: reports.append((text, fraction)))
        self.assertEqual(reports[:3], [("Looking up the tracks", None), ("Rating new music", None),
                                       ("Working out what this mix is about", None)])
        self.assertIn(("Checking the replacements: asking the AI about 5 tracks", 0.75), reports)

    def test_rating_progress_counts_batches(self):
        reports = []
        report = assist.rating_progress(lambda text, fraction: reports.append((text, fraction)),
                                        "Checking the replacements: rating new music", 0.7)
        report(1, 4)
        self.assertEqual(reports, [("Checking the replacements: rating new music (1 of 4)", 0.175)])
        self.assertIsNone(assist.rating_progress(None, "x"))

    def test_the_listeners_intent_is_used_when_given(self):
        messages = []

        def ask(system, schema, message):
            messages.append((system, message))
            return self.ask(system, schema, message)

        plan = assist.tidy_up(self.paths, self.store, ask, self.resolve, self.fetch_mix, intent="my words")
        self.assertEqual((plan["intent"], plan["intent_source"]), ("my words", "listener"))
        self.assertNotIn(checks.SEED_INTENT_PROMPT, [system for system, _ in messages])
        self.assertTrue(all(message.startswith("Intent: my words") for _, message in messages))

    def test_rejected_submix_seeds_fall_back_and_unfillable_gaps_are_removed(self):
        def fetch_mix(seed, size):
            raise RuntimeError("MusicIP: HTTP 500")

        plan = assist.tidy_up(self.paths, self.store, self.ask, self.resolve, fetch_mix)
        self.assertEqual(plan["changes"], [])
        self.assertEqual(sorted(plan["removed"]), [6, 11])
        self.assertEqual(plan["paths"], [p for p in self.paths if not p.startswith("bad")])

    def test_gaps_sharing_a_submix_seed_share_one_larger_submix(self):
        paths = ["seed"] + [f"fit{i}" for i in range(1, 5)] + ["bad1", "bad2"] + [f"fit{i}" for i in range(5, 9)]
        requests = []

        def fetch_mix(seed, size):
            requests.append((seed, size))
            return [seed, "candbad", "cand1", "cand2", "cand3"] if seed == "fit4" else [seed]

        judged = []

        def ask(system, schema, message):
            if system is checks.INTENT_PROMPT:
                judged.append([line for line in message.splitlines() if line[:1].isdigit()])
            return self.ask(system, schema, message)

        plan = assist.tidy_up(paths, self.store, ask, self.resolve, fetch_mix, artist_window=0)
        self.assertEqual(requests, [("fit4", assist.MUSICIP_MAX_MIX), ("seed", assist.MUSICIP_MAX_MIX)])
        self.assertEqual(len(judged), 1)
        self.assertEqual(len(judged[0]), 4)  # candbad, cand1-3: once each, although two gaps share the submix
        self.assertEqual(sorted(change["old"] for change in plan["changes"]), ["bad1", "bad2"])
        self.assertEqual({change["source"] for change in plan["changes"]}, {"submix"})
        self.assertEqual(len(plan["paths"]), len(paths))

    def test_open_gaps_get_submixes_from_other_fitting_tracks(self):
        def fetch_mix(seed, size):
            return [seed, "cand1", "cand2"] if seed == "fit3" else [seed, "candbad"]

        plan = assist.tidy_up(self.paths, self.store, self.ask, self.resolve, fetch_mix, artist_window=0)
        self.assertEqual(sorted(change["old"] for change in plan["changes"]), ["bad1", "bad2"])
        self.assertEqual({change["source"] for change in plan["changes"]}, {"nearby"})
        self.assertEqual(plan["removed"], [])

    def test_more_like_this_measures_against_the_selected_song(self):
        result = assist.choose_additions("seed", ["candbad", "cand3", "cand1", "cand2"], 2, self.store, self.ask,
                                         self.resolve, artist_window=0)
        self.assertEqual(result["chosen"], ["cand3", "cand1"])  # MusicIP's order
        self.assertEqual([entry["path"] for entry in result["not_fitting"]], ["candbad"])
        self.assertEqual((result["intent"], result["checked"]), ("abstract, instrumental", True))

    def test_more_like_this_can_name_what_the_selected_song_is_about(self):
        prompts = []

        def ask(system, schema, message):
            prompts.append(system)
            return dict(self.ask(system, schema, message), name="Abstract Night Music")

        result = assist.choose_additions("seed", ["candbad", "cand3", "cand1", "cand2"], 2, self.store, ask,
                                         self.resolve, artist_window=0, name=True)
        self.assertEqual((result["name"], result["chosen"]), ("Abstract Night Music", ["cand3", "cand1"]))
        self.assertIn(checks.NAME_NOTE, prompts[-1])  # in the same call that states the intent
        self.assertEqual(assist.choose_additions("seed", ["cand1"], 1, self.store, self.ask, self.resolve,
                                                 artist_window=0)["name"], "")

    def test_more_like_this_respects_the_artist_window(self):
        result = assist.choose_additions("seed", ["fit3", "cand1", "cand2", "cand3", "cand4"], 2, self.store,
                                         self.ask, self.resolve, neighbours=["fit1", "fit2"], artist_window=5)
        self.assertEqual(result["chosen"], ["cand1"])  # fit3: an artist next to it; cand2..4: the same artist

    def test_more_like_this_looks_further_with_the_same_intent(self):
        for index in range(1, 5):
            self.add(f"solo{index}", exploration=9, form=1)
        systems = []

        def ask(system, schema, message):
            systems.append(system)
            return self.ask(system, schema, message)

        # The first 10 candidates fit but are all by artists next to the insertion point.
        candidates = [f"cand{i}" for i in range(1, 5)] + [f"fit{i}" for i in range(1, 7)] + [f"solo{i}" for i in range(1, 5)]
        result = assist.choose_additions("seed", candidates, 1, self.store, ask, self.resolve,
                                         neighbours=["cand1", "fit1"], artist_window=5)
        self.assertEqual(result["chosen"], ["solo1"])
        self.assertEqual(systems, [checks.SEED_INTENT_PROMPT, checks.INTENT_PROMPT])

    def test_a_radio_profile_drifts_song_by_song(self):
        reference = vector(energy=2, sounding_year=1980)
        # Half-life 1 song: each song pulls the profile half the way towards it; later songs count more.
        moved = assist.drift_reference(reference, [vector(energy=6, sounding_year=1990), None,
                                                   vector(energy=8, sounding_year=2000)], 1)
        self.assertEqual((moved["energy"], moved["sounding_year"]), (6.0, 1992.5))
        self.assertEqual(moved["character"], "x")
        self.assertEqual(assist.drift_reference(reference, [vector(energy=9)], 0), reference)

    def test_drift_does_not_depend_on_the_refill_size(self):
        reference = vector(energy=0)
        songs = [vector(energy=10)] * 60
        one_batch = assist.drift_reference(reference, songs, 60)
        in_batches = reference
        for start in range(0, 60, 8):
            in_batches = assist.drift_reference(in_batches, songs[start:start + 8], 60)
        self.assertAlmostEqual(one_batch["energy"], 5.0)
        self.assertAlmostEqual(in_batches["energy"], 5.0)

    def test_adventurous_also_takes_borderline_songs(self):
        borderline = {"relative": 1.0, "verdict": "borderline"}
        self.assertFalse(assist.passes(borderline, 1.2))
        self.assertTrue(assist.passes(borderline, 1.2, accept_borderline=True))
        self.assertFalse(assist.passes({"relative": 1.0, "verdict": "outlier"}, 1.2, accept_borderline=True))

    def test_more_like_this_returns_the_ratings_it_used(self):
        result = assist.choose_additions("seed", ["cand1", "cand2", "cand3", "cand4"], 1, self.store, self.ask,
                                         self.resolve, artist_window=0)
        self.assertEqual(result["seed_entry"]["exploration"], 9)
        self.assertEqual(list(result["entries"]), result["chosen"])

    def test_one_dimension_clearly_off(self):
        seed = vector(energy=8, sounding_year=1982)
        self.assertEqual(assist.single_dimension_miss(vector(energy=3, sounding_year=1982), seed), "energy")  # 5 points
        self.assertEqual(assist.single_dimension_miss(vector(energy=4, sounding_year=2006), seed), "")  # 4 points, 24 years
        self.assertEqual(assist.single_dimension_miss(vector(energy=8, sounding_year=2007), seed), "sounding_year")
        # several: the one furthest beyond its limit
        self.assertEqual(assist.single_dimension_miss(vector(energy=2, mood=0, sounding_year=2010), seed), "energy")

    def test_a_track_close_overall_but_off_on_one_dimension_is_flagged(self):
        self.add("odd1", exploration=9, form=1, energy=0)  # like the seed, but 5 points less energy
        paths = ["seed"] + [f"fit{i}" for i in range(1, 9)] + ["odd1"]
        units = self.resolve(paths)
        entries = [self.store.get(unit["key"]) for unit in units]
        verdicts = {position: {"verdict": "fits", "reason": ""} for position in range(1, len(paths) + 1)}
        analysis = assist.analyze(units, entries, verdicts, self.store.library())
        odd = analysis["rows"][-1]
        self.assertLessEqual(odd["relative"], 1.2)  # not far overall
        self.assertEqual((odd["single"], odd["status"]), ("energy", "flagged"))
        self.assertNotIn(len(paths), assist.clearly_fitting(analysis["rows"], 1.2))
        verdicts[len(paths)] = {"verdict": "outlier", "reason": "much calmer"}
        self.assertEqual(assist.analyze(units, entries, verdicts, self.store.library())["rows"][-1]["status"], "outlier")

    def test_new_tracks_must_not_be_clearly_off_on_one_dimension(self):
        self.assertFalse(assist.passes({"relative": 0.5, "verdict": "fits", "single": "energy"}, 1.2))
        self.assertTrue(assist.passes({"relative": 0.5, "verdict": "fits", "single": ""}, 1.2))
        self.add("odd1", exploration=9, form=1, energy=0)
        result = assist.choose_additions("seed", ["odd1", "cand1", "cand2", "cand3", "cand4"], 1, self.store, self.ask,
                                         self.resolve, artist_window=0)
        self.assertEqual(result["chosen"], ["cand1"])
        self.assertEqual([entry["path"] for entry in result["not_fitting"]], ["odd1"])

    def test_a_fitting_mix_is_left_alone(self):
        paths = ["seed"] + [f"fit{i}" for i in range(1, 9)]
        plan = assist.tidy_up(paths, self.store, self.ask, self.resolve, self.fetch_mix)
        self.assertEqual((plan["changes"], plan["removed"], plan["paths"]), ([], [], paths))

    def test_submix_seed_is_the_nearest_clearly_fitting_track(self):
        self.assertEqual(assist.submix_seed_position(10, {1, 5, 9}), 9)
        self.assertEqual(assist.submix_seed_position(10, {1, 5}), 5)
        self.assertEqual(assist.submix_seed_position(2, {1}), 1)

    def test_pick_respects_both_signals_taken_tracks_and_the_artist_window(self):
        candidates = [{"path": "a", "artist": "X", "relative": 0.4, "verdict": "borderline"},
                      {"path": "b", "artist": "Medeski Martin & Wood", "relative": 0.1, "verdict": "fits"},
                      {"path": "c", "artist": "Z", "relative": 0.5, "verdict": "fits"},
                      {"path": "d", "artist": "Y", "relative": 1.5, "verdict": "fits"}]
        self.assertEqual(assist.pick(candidates, 1.2, set(), set())["path"], "b")
        blocked = {assist.artist_key("Medeski, Martin and Wood")}
        self.assertEqual(assist.pick(candidates, 1.2, set(), blocked)["path"], "c")
        self.assertIsNone(assist.pick(candidates, 1.2, {"c"}, blocked))


if __name__ == "__main__":
    unittest.main()
