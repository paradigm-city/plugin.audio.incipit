"""The sound engine's years (an Epoch station's time): each song's year from Kodi's music database, the search
within a span of years, and how the add-on asks for it."""

import os
import random
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock

from fake_kodi import ADDON_DIR

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

import numpy as np  # noqa: E402

from soundprint import neighbours, store, years  # noqa: E402

SCHEMA = (
    "CREATE TABLE path (idPath INTEGER, strPath TEXT);"
    "CREATE TABLE album (idAlbum INTEGER, strAlbum TEXT, strArtistDisp TEXT, bCompilation INTEGER, "
    "strOrigReleaseDate TEXT, strReleaseDate TEXT);"
    "CREATE TABLE song (idSong INTEGER, idPath INTEGER, idAlbum INTEGER, strFileName TEXT, strArtistDisp TEXT, "
    "strTitle TEXT, strOrigReleaseDate TEXT, strReleaseDate TEXT);"
)
ALBUMS = [  # id, title, artist, compilation, original date, release date
    (1, "Aja", "Steely Dan", 0, "1977", "1999-03-01"),  # a reissue: the original date counts
    (2, "Disco Box", "Various Artists", 1, "", "2003"),
    (3, "Bad Girls", "Donna Summer", 0, "", "1979"),
    (4, "Punk 77", "Various Artists", 1, "", "1978"),  # a compilation of the time
    (5, "Hits Forever", "Various Artists", 1, "", "1995"),
    (6, "Rock Heaven Vol. 32", "Various Artists", 1, "1978", "1978"),  # a series of today, dated 1978 by its tags
    (7, "Out of the Shadows", "Volbeat", 0, "", "2005"),
    (8, "Images and Words", "Dream Theater", 0, "", "1992"),
    (9, "Rock Heaven Vol. 103", "Various Artists", 1, "1975", "1975"),  # dated song by song: Kodi takes the first
]
SONGS = [  # id, album, file, artist, title, the song's own date
    (1, 1, "aja.mp3", "Steely Dan", "Aja"),
    (2, 2, "love.mp3", "Donna Summer", "Hot Stuff"),  # also on her own album of 1979
    (3, 2, "feel.mp3", "Donna Summer", "I Feel Love"),  # only on compilations: 2003 and 1995
    (4, 3, "hot.mp3", "Donna Summer", "Hot Stuff"),
    (5, 4, "anarchy.mp3", "Sex Pistols", "Anarchy in the U.K."),
    (6, 5, "feel2.mp3", "Donna Summer", "I Feel Love"),
    (7, 6, "heaven1.mp3", "Volbeat", "Another Day"),
    (8, 6, "heaven2.mp3", "Dream Theater", "Pull Me Under"),
    (9, 6, "heaven3.mp3", "Rich Kids", "Ghosts of Princes"),
    (10, 7, "volbeat.mp3", "Volbeat", "Fallen"),
    (11, 8, "under.mp3", "Dream Theater", "Pull Me Under"),
    (12, 9, "sabbath.mp3", "Black Sabbath", "Don't Start (Too Late)", "1975"),
    (13, 9, "flock.mp3", "A Flock of Seagulls", "I Ran", "1982-04-01"),
    (14, 9, "nodate.mp3", "The Unknowns", "Untitled", ""),
    (15, 5, "iran2.mp3", "A Flock of Seagulls", "I Ran"),  # on a compilation dated by its release
]


def kodi_database(folder):
    path = os.path.join(folder, "MyMusic83.db")
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO path VALUES (1, 'D:\\music\\')")
    connection.executemany("INSERT INTO album VALUES (?, ?, ?, ?, ?, ?)", ALBUMS)
    connection.executemany("INSERT INTO song VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                           [entry[:5] + (entry[5:] or ("",)) * 2 for entry in SONGS])
    connection.commit()
    connection.close()
    return path


def unit(*values):
    vector = np.zeros(store.DIMENSIONS, np.float32)
    vector[:len(values)] = values
    return vector / np.linalg.norm(vector)


class SongYearsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.database = kodi_database(self.folder)

    def test_each_song_has_its_first_release_or_the_latest_its_compilation_allows(self):
        found = years.song_years(self.database)
        self.assertEqual(found["D:\\music\\aja.mp3"], (1977, 0))  # the album's original date, not the reissue's
        self.assertEqual(found["D:\\music\\love.mp3"], (1979, 0))  # from her own album
        self.assertEqual(found["D:\\music\\feel.mp3"], (0, 1995))  # only compilations: the earliest of them
        self.assertEqual(found["D:\\music\\feel2.mp3"], (0, 1995))
        self.assertEqual(found["D:\\music\\anarchy.mp3"], (0, 1978))

    def test_a_compilation_dated_song_by_song_gives_each_song_its_date(self):
        found = years.song_years(self.database)
        self.assertEqual(found["D:\\music\\sabbath.mp3"], (1975, 0))
        self.assertEqual(found["D:\\music\\flock.mp3"], (1982, 0))  # not Kodi's 1975 for the album
        self.assertEqual(found["D:\\music\\iran2.mp3"], (1982, 0))  # the same song elsewhere takes it too
        self.assertEqual(found["D:\\music\\nodate.mp3"], (0, 0))  # its compilation's date bounds nothing

    def test_a_compilation_dated_before_its_songs_bounds_nothing(self):
        found = years.song_years(self.database)
        self.assertEqual(found["D:\\music\\heaven1.mp3"], (0, 0))  # Volbeat's first album: 2005
        self.assertEqual(found["D:\\music\\heaven2.mp3"], (1992, 0))  # on Dream Theater's own album
        self.assertEqual(found["D:\\music\\heaven3.mp3"], (0, 0))  # the only song of its time: its date isn't trusted
        certain, _uncertain, _ = years.within(found, 1975, 1979, minimum=1)
        self.assertFalse({"D:\\music\\heaven1.mp3", "D:\\music\\heaven3.mp3"} & certain)

    def test_certain_and_uncertain_within_a_span_widened_while_too_few(self):
        found = years.song_years(self.database)
        certain, uncertain, used = years.within(found, 1976, 1979, minimum=1)
        self.assertEqual(sorted(certain), ["D:\\music\\aja.mp3", "D:\\music\\hot.mp3", "D:\\music\\love.mp3"])
        self.assertEqual(sorted(uncertain), ["D:\\music\\anarchy.mp3",  # a compilation of 1978: then or before
                                             "D:\\music\\feel.mp3", "D:\\music\\feel2.mp3",  # of 1995: maybe
                                             "D:\\music\\heaven1.mp3", "D:\\music\\heaven3.mp3",  # no date to go by
                                             "D:\\music\\nodate.mp3"])
        self.assertEqual(used, (1976, 1979))
        certain, uncertain, used = years.within(found, 1990, 1990, minimum=2)
        self.assertEqual((sorted(certain), used), (["D:\\music\\heaven2.mp3", "D:\\music\\under.mp3"], (1988, 1992)))
        self.assertNotIn("D:\\music\\anarchy.mp3", uncertain)  # a compilation of 1978 holds no song of 1988
        certain, _, used = years.within(found, 1990, 1990, minimum=4)
        self.assertEqual((len(certain), used), (4, (1982, 1998)))  # the two "I Ran" of 1982 bring it to 4
        certain, _, used = years.within(found, 1990, 1990, minimum=5)
        self.assertEqual((len(certain), used), (4, (1980, 2000)))  # widened at most 10 years, with what it has

    def test_a_song_sounding_as_a_dated_one_by_the_same_artist_is_that_recording(self):
        vectors = (["a", "b", "c", "d"], np.stack([unit(1, 0), unit(1, 0.02), unit(1, 0), unit(1, 0.15)]))
        found = {"a": (1981, 0), "b": (0, 0), "c": (0, 2003), "d": (0, 0)}
        dated = years.same_recordings(found, [("a", "kas product"), ("b", "kas product"), ("c", "another band"),
                                              ("d", "kas product")], vectors, lambda path: path)
        self.assertEqual(dated, 1)
        self.assertEqual(found["b"], (1981, 0))  # "One of the Kind", the same recording as "One of a Kind"
        self.assertEqual(found["c"], (0, 2003))  # the same sound by another artist: not the same recording
        self.assertEqual(found["d"], (0, 0))  # another song of theirs: near, but not the same

    def test_an_undated_songs_sound_hints_at_its_time(self):
        vectors = (["d1", "d2", "d3", "u1", "u2"],
                   np.stack([unit(1, 0), unit(1, 0.1), unit(0, 1), unit(1, 0.05), unit(0.1, 1)]))
        found = {"d1": (1977, 0), "d2": (1978, 0), "d3": (2015, 0), "u1": (0, 0), "u2": (0, 2020)}
        artists = {"d1": "a", "d2": "b", "d3": "c", "u1": "a", "u2": "d"}
        with unittest.mock.patch.object(years, "ERA_NEIGHBOURS", 2):
            hints = years.era_hints(found, artists, vectors, lambda path: path)
        self.assertEqual(list(hints["u1"]), [1978, 2015])  # its own artist's song left out
        self.assertEqual(list(hints["u2"]), [2015, 1978])
        self.assertEqual(years.era_share(hints["u1"], 1976, 1979), 0.5)
        with unittest.mock.patch.object(years, "ERA_NEIGHBOURS", 1):
            hints = years.era_hints(found, artists, vectors, lambda path: path)
        _certain, maybe, _ = years.within(found, 1976, 1979, minimum=1, hints=hints)
        self.assertEqual(maybe, {"u1"})  # u2 sounds like 2015 more than like 1977
        self.assertEqual(years.era_hints(found, artists, vectors, lambda path: path, known={"u1": "kept"})["u1"],
                         "kept")  # made before: kept

    def test_kept_until_the_database_or_the_sound_prints_change(self):
        first = years.cached_years(self.database, self.folder)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, years.CACHE_FILE)))
        self.assertEqual(years.load(self.folder), first)
        connection = sqlite3.connect(self.database)
        connection.execute("UPDATE album SET strOrigReleaseDate = '1976' WHERE idAlbum = 1")
        connection.commit()
        connection.close()
        os.utime(self.database, ns=(1, 1))  # a different time stamp: the database changed
        second = years.cached_years(self.database, self.folder)
        self.assertEqual((first["D:\\music\\aja.mp3"], second["D:\\music\\aja.mp3"]), ((1977, 0), (1976, 0)))
        heaven = "D:\\music\\heaven3.mp3"
        vectors = ([heaven, "D:\\music\\other.mp3"], np.stack([unit(1, 0), unit(0, 1)]))
        self.assertEqual(years.cached_years(self.database, self.folder, vectors=vectors)[heaven], (0, 0))
        self.assertIsNone(years.load(tempfile.mkdtemp()))

    def test_spans_from_the_command_line(self):
        self.assertEqual(years.parse_window("1975-1979"), (1975, 1979))
        self.assertEqual(years.parse_window("1977"), (1977, 1977))
        with self.assertRaises(ValueError):
            years.parse_window("")

    def test_paths_compared_as_the_sound_engine_does(self):
        with unittest.mock.patch.object(years.os, "name", "nt"):
            self.assertEqual(years.path_key(" D:\\Music\\A.mp3"), "d:/music/a.mp3")
        self.assertEqual(neighbours.file_key("D:\\Music\\A.mp3"),
                         years.path_key("D:\\Music\\A.mp3") if os.name == "nt" else "D:/Music/A.mp3")


class SearchWithinYearsTest(unittest.TestCase):
    def setUp(self):
        self.store = store.Store(tempfile.mkdtemp())
        for name, vector in (("seed", unit(1, 0)), ("close", unit(1, 0.2)), ("later", unit(1, 0.1)),
                             ("middle", unit(1, 1)), ("far", unit(0, 1))):
            self.store.put(name, 1, 1.0, "v", 1.0, vector)
        self.store.commit()
        self.years = {"seed": (1977, 0), "close": (1978, 0), "later": (1994, 0), "middle": (0, 1976),
                      "far": (0, 2010)}

    def tearDown(self):
        self.store.close()

    def test_songs_of_other_years_are_left_out_before_choosing(self):
        found, _, left_out = neighbours.nearest(self.store, "seed", 5, in_order=True, years=self.years,
                                                span=(1975, 1979), min_songs=1)
        self.assertEqual([(path, rank) for path, _, rank in found], [("close", 2), ("middle", 3)])  # ranks of all
        self.assertEqual((left_out["outside_years"], left_out["years"]), (1, [1975, 1979]))  # "later"
        self.assertEqual((left_out["uncertain"], left_out["uncertain_passed"]), (1, 1))  # a quarter of 5: one
        found, _, _ = neighbours.nearest(self.store, "seed", 5, rng=random.Random(3), years=self.years,
                                         span=(1975, 1979), variety=9, min_songs=1)
        self.assertEqual(len(found), 2)
        self.assertIn("close", [path for path, _, _ in found])

    def test_uncertain_songs_up_to_a_quarter_of_the_mix(self):
        found, _, left_out = neighbours.nearest(self.store, "seed", 8, in_order=True, years=self.years,
                                                span=(1975, 1979), min_songs=1)
        self.assertEqual([path for path, _, _ in found], ["close", "middle", "far"])  # 2 of 8
        self.assertEqual((left_out["uncertain"], left_out["uncertain_passed"]), (2, 0))

    def test_a_window_with_too_few_certain_songs_widens(self):
        self.years["later"] = (1984, 0)
        found, _, left_out = neighbours.nearest(self.store, "seed", 5, in_order=True, years=self.years,
                                                span=(1975, 1979), min_songs=3)
        self.assertEqual([path for path, _, _ in found], ["later", "close", "middle"])
        self.assertEqual(left_out["years"], [1970, 1984])  # 1984 brings the third certain song, the seed counted
        self.years["later"] = (1994, 0)  # further than 10 years: the window stops there, with what it has
        found, _, left_out = neighbours.nearest(self.store, "seed", 5, in_order=True, years=self.years,
                                                span=(1975, 1979), min_songs=3)
        self.assertEqual(([path for path, _, _ in found], left_out["years"]), (["close", "middle"], [1965, 1989]))

    def test_without_a_span_every_year(self):
        found, _, left_out = neighbours.nearest(self.store, "seed", 5, in_order=True, years=self.years)
        self.assertEqual(len(found), 4)
        self.assertNotIn("outside_years", left_out)


if __name__ == "__main__":
    unittest.main()
