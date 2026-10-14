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
