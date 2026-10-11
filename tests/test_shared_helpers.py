"""main.py and service.py each carry a copy of several helpers. These tests keep the copies in step."""

import unittest

from fake_kodi import kodi
from support import KodiTestCase, main, service

PATHS = [
    "",
    "D:\\Music\\Motörhead\\01 Ace%20of Spades.mp3",
    "D:/music//a/b.flac/",
    "smb://Server//share/x.mp3",
    "nfs://host/a/b/",
    "01 Song.mp3",
]
SONGS = [
    {"file": "E:\\other\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"},
    {"file": "E:\\x\\02.mp3"},
    {"file": "smb://Server/share/x.mp3"},
]
METADATA = [
    None,
    {},
    {"title": "Ace", "artist": "M", "genre": "Metal", "year": "1980", "duration": "169", "songid": "4"},
    {"title": "", "genre": ["A", " "], "year": "abc", "duration": -1, "cached_ts": "x"},
]
SONG_RECORDS = [
    {"title": " T ", "displayartist": "D", "albumartist": ["X"], "year": 1999, "genre": ["Rock"], "songid": 3},
    {},
]


class SharedHelpersTest(unittest.TestCase):
    def assertSame(self, name, *args):
        with self.subTest(helper=name, args=args):
            self.assertEqual(getattr(main, name)(*args), getattr(service, name)(*args))

    def test_path_helpers(self):
        for path in PATHS:
            for name in ("canonical_audio_path", "path_to_label", "split_full_path", "basename_key", "tail_key"):
                self.assertSame(name, path)
            self.assertSame("build_path_candidates", main.split_full_path(path)[1])

    def test_song_matching(self):
        for path in PATHS + ["D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"]:
            self.assertSame("find_song_by_file", SONGS, path)
            self.assertSame("find_song_by_file_relaxed", SONGS, path)

    def test_value_parsers(self):
        for value in (None, "", "1980", 1980, "abc", -5, ["A", "B"], " x "):
            for name in ("first_non_empty_text", "normalize_genres", "parse_year", "parse_duration_seconds", "format_decade"):
                if name in ("parse_year", "parse_duration_seconds", "format_decade") and isinstance(value, list):
                    continue
                self.assertSame(name, value)

    def test_metadata_snapshots(self):
        for metadata in METADATA:
            self.assertSame("normalize_track_metadata_snapshot", PATHS[1], metadata)
            self.assertSame("normalize_track_metadata_snapshot", PATHS[1], metadata, 5, 6)
            self.assertSame("track_metadata_snapshot_has_payload", PATHS[1], metadata)
        for song in SONG_RECORDS:
            self.assertSame("extract_song_metadata", song)

    def test_discovery_helpers(self):
        for args in ((300, 20, 33), (100, 20, 90), (10, 20, 33), (0, 20, 33), ("x", 1, 1)):
            self.assertSame("calculate_discovery_offset", *args)
        song = {"title": "T", "artist": ["A", "B"]}
        self.assertEqual(main.discovery_song_label_from_song(song), service.discovery_song_label(song))

    def test_kodi_datetime(self):
        for value in ("2026-10-08 12:16:17", "2026-10-08T12:16:17Z", "2026-10-08", "", "garbage", "2026-13-45"):
            self.assertSame("parse_kodi_datetime", value)



class SharedLibraryLookupTest(KodiTestCase):
    """Plugin and service resolve track metadata from the Kodi library the same way."""

    TRACK = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"

    def assertSameLookup(self):
        for path in (self.TRACK, "", "D:\\music\\unknown.mp3"):
            with self.subTest(path=path):
                self.assertEqual(main.get_library_track_metadata(path), service.get_library_track_metadata(path))

    def test_exact_file(self):
        kodi.library.add_song(self.TRACK, title="Ace of Spades", artist="Motörhead", year=1980)
        self.assertSameLookup()
        self.assertEqual(service.get_library_track_metadata(self.TRACK)["artist"], "Motörhead")

    def test_moved_file(self):
        kodi.library.add_song("E:\\moved\\01 Ace of Spades.mp3", title="Ace of Spades")
        self.assertSameLookup()

    def test_ambiguous_file(self):
        kodi.library.add_song("E:\\a\\01 Ace of Spades.mp3", title="A")
        kodi.library.add_song("F:\\b\\01 Ace of Spades.mp3", title="B")
        self.assertSameLookup()
        self.assertEqual(service.get_library_track_metadata(self.TRACK), {})

    def test_safe_property_retry(self):
        kodi.library.add_song(self.TRACK, title="Ace of Spades")
        kodi.fail_jsonrpc("AudioLibrary.GetSongs", times=1)
        self.assertEqual(service.get_library_track_metadata(self.TRACK)["title"], "Ace of Spades")
        kodi.fail_jsonrpc("AudioLibrary.GetSongs", times=4)
        self.assertEqual(service.get_library_track_metadata(self.TRACK), {})


class SharedStorageTest(KodiTestCase):
    def test_both_modules_use_the_same_profile_files(self):
        for name in ("discovery_state_path", "get_profile_dir"):
            self.assertEqual(getattr(main, name)(), getattr(service, name)())
        self.assertEqual(main.get_metadata_refresh_queue_path(), service.metadata_refresh_queue_path())
        self.assertEqual(main.get_track_metadata_cache_db_path(), service.track_metadata_cache_db_path())

    def test_refresh_queue_written_by_plugin_is_read_by_service(self):
        main.enqueue_metadata_refresh_for_tracks([PATHS[1]], cache_path="m.m3u")
        entries = service.load_metadata_refresh_queue()["entries"]
        self.assertEqual([(entry["path"], entry["cache_paths"]) for entry in entries], [(PATHS[1], ["m.m3u"])])

    def test_discovery_state_round_trip(self):
        main.save_discovery_state({"enabled": True, "current_song": PATHS[1]})
        self.assertEqual(service.load_discovery_state()["current_song"], PATHS[1])
        service.save_discovery_state({"enabled": False})
        self.assertFalse(main.get_discovery_state()["enabled"])


if __name__ == "__main__":
    unittest.main()
