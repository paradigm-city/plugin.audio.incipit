"""Track metadata: library lookups, the SQLite cache, sidecar snapshots, refresh queue and display labels."""

import os
import time
import unittest
from unittest import mock

from fake_kodi import ListItem, kodi
from support import KodiTestCase, main

TRACK = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
OTHER = "D:\\music\\Motorhead\\Overkill (1979)\\01 Overkill.mp3"


def add_ace_of_spades(file=TRACK):
    return kodi.library.add_song(
        file, title="Ace of Spades", artist="Motörhead", album="Ace of Spades", genre=["Metal"],
        year=1980, duration=169, track=1, thumbnail="thumb.jpg", fanart="fanart.jpg",
    )


class PathHelpersTest(unittest.TestCase):
    def test_canonical_audio_path(self):
        self.assertEqual(main.canonical_audio_path("D:\\Music\\\\A%20B.mp3"), "d:/music/a b.mp3")
        self.assertEqual(main.canonical_audio_path("SMB://Server//Share/a.mp3/"), "smb://server/share/a.mp3")
        self.assertEqual(main.canonical_audio_path(""), "")

    def test_split_path_and_label(self):
        self.assertEqual(main.split_full_path("D:\\a\\b.mp3"), ("b.mp3", "D:\\a"))
        self.assertEqual(main.split_full_path("smb://x/b.mp3/"), ("b.mp3", "smb://x"))
        self.assertEqual(main.split_full_path("b.mp3"), ("b.mp3", ""))
        self.assertEqual(main.path_to_label("/music/a/01 Song.flac"), "01 Song")

    def test_path_candidates(self):
        candidates = main.build_path_candidates("D:\\music\\a")
        self.assertEqual(candidates[:2], ["D:\\music\\a", "D:/music/a"])
        self.assertIn("D:\\music\\a\\", candidates)
        self.assertIn("D:/music/a/", candidates)
        self.assertEqual(main.build_path_candidates("smb://x/a/"), ["smb://x/a", "smb://x/a/"])
        self.assertEqual(main.build_path_candidates(""), [])

    def test_find_song_by_file_relaxed(self):
        songs = [{"file": "E:\\other\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"}, {"file": "E:\\x\\02.mp3"}]
        self.assertIs(main.find_song_by_file_relaxed(songs, TRACK.upper()), songs[0])
        self.assertIsNone(main.find_song_by_file_relaxed(songs + [dict(songs[0])], TRACK))
        self.assertIsNone(main.find_song_by_file_relaxed(songs, "D:\\nothing.mp3"))

    def test_value_parsers(self):
        self.assertEqual(main.parse_year("1980"), 1980)
        self.assertEqual(main.parse_year("abc"), 0)
        self.assertEqual(main.parse_track_number("07/12"), 7)
        self.assertEqual(main.parse_track_number([3]), 3)
        self.assertEqual(main.parse_duration_seconds(-5), 0)
        self.assertEqual(main.normalize_genres([" Rock ", "", "Metal"]), ["Rock", "Metal"])
        self.assertEqual(main.normalize_genres("Rock"), ["Rock"])
        self.assertEqual(main.format_decade(1987), "1980s")
        self.assertEqual(main.format_duration(169), "2:49")
        self.assertEqual(main.format_duration(3725), "1:02:05")
        self.assertEqual(main.format_duration(0), "")
        self.assertEqual(main.first_non_empty_text(["A", " ", "B"]), "A / B")


class LibraryMetadataTest(KodiTestCase):
    def test_strict_lookup_by_filename_and_folder(self):
        add_ace_of_spades()
        add_ace_of_spades(file="E:\\copy\\01 Ace of Spades.mp3")
        metadata = main.get_library_track_metadata(TRACK)
        self.assertEqual(metadata, {
            "songid": 1, "title": "Ace of Spades", "artist": "Motörhead", "album": "Ace of Spades",
            "genre": ["Metal"], "year": 1980, "decade": "1980s", "duration": 169,
            "thumbnail": "thumb.jpg", "fanart": "fanart.jpg",
        })
        strict_filter = kodi.jsonrpc_calls[0]["params"]["filter"]["and"]
        self.assertEqual(strict_filter[0], {"field": "filename", "operator": "is", "value": "01 Ace of Spades.mp3"})

    def test_filename_only_fallback_when_folder_moved(self):
        add_ace_of_spades(file="E:\\moved\\01 Ace of Spades.mp3")
        self.assertEqual(main.get_library_track_metadata(TRACK)["title"], "Ace of Spades")

    def test_ambiguous_or_unknown(self):
        add_ace_of_spades(file="E:\\a\\01 Ace of Spades.mp3")
        add_ace_of_spades(file="F:\\b\\01 Ace of Spades.mp3")
        self.assertEqual(main.get_library_track_metadata(TRACK), {})
        self.assertEqual(main.get_library_track_metadata(""), {})

    def test_artist_falls_back_to_display_and_album_artist(self):
        song = {"displayartist": "", "albumartist": ["Various"], "title": "x"}
        self.assertEqual(main.extract_song_metadata(song)["artist"], "Various")


class TrackMetadataCacheTest(KodiTestCase):
    def test_write_and_read_back(self):
        main.write_track_metadata_cache(TRACK, {"title": "Ace of Spades", "genre": ["Metal"], "year": 1980, "cached_ts": 5})
        cached = main.read_track_metadata_cache(TRACK.lower().replace("\\", "/"))
        self.assertEqual((cached["title"], cached["genre"], cached["decade"], cached["cached_ts"]), ("Ace of Spades", ["Metal"], "1980s", 5))

    def test_upsert_replaces_previous_row(self):
        main.write_track_metadata_cache(TRACK, {"title": "Old"})
        main.write_track_metadata_cache(TRACK, {"title": "New"})
        self.assertEqual(main.read_track_metadata_cache(TRACK)["title"], "New")

    def test_empty_metadata_is_not_cached(self):
        main.write_track_metadata_cache(TRACK, {"title": "01 Ace of Spades"})
        self.assertEqual(main.read_track_metadata_cache(TRACK), {})

    def test_snapshot_has_payload(self):
        self.assertFalse(main.track_metadata_snapshot_has_payload(TRACK, None))
        self.assertFalse(main.track_metadata_snapshot_has_payload(TRACK, main.build_empty_track_metadata(TRACK)))
        self.assertTrue(main.track_metadata_snapshot_has_payload(TRACK, {"duration": 3}))
        self.assertTrue(main.track_metadata_snapshot_has_payload(TRACK, {"songid": 4}))


class GetTrackMetadataTest(KodiTestCase):
    def test_sidecar_snapshot_wins(self):
        add_ace_of_spades()
        metadata = main.get_track_metadata(TRACK, sidecar_snapshot={"title": "From sidecar"})
        self.assertEqual(metadata["title"], "From sidecar")
        self.assertEqual(kodi.jsonrpc_calls, [])

    def test_cache_before_library(self):
        add_ace_of_spades()
        main.write_track_metadata_cache(TRACK, {"title": "From cache"})
        self.assertEqual(main.get_track_metadata(TRACK)["title"], "From cache")

    def test_live_library_lookup_fills_cache(self):
        add_ace_of_spades()
        kodi.library_properties = {"songsmodified": "2026-10-01 00:00:00"}
        metadata = main.get_track_metadata(TRACK)
        self.assertEqual(metadata["artist"], "Motörhead")
        cached = main.read_track_metadata_cache(TRACK)
        self.assertEqual(cached["library_freshest_ts"], main.parse_kodi_datetime("2026-10-01 00:00:00"))

    def test_no_live_lookup_returns_filename_title(self):
        add_ace_of_spades()
        metadata = main.get_track_metadata(TRACK, allow_live_lookup=False)
        self.assertEqual((metadata["title"], metadata["artist"]), ("01 Ace of Spades", ""))

    def test_playing_track_overrides_with_player_tags(self):
        kodi.play_file(TRACK, title="Live title", artist="Lemmy", genres=["Rock"], year=1981, duration=170)
        metadata = main.get_track_metadata(TRACK, sidecar_snapshot={"title": "From sidecar", "album": "Ace"})
        self.assertEqual((metadata["title"], metadata["artist"], metadata["album"]), ("Live title", "Lemmy", "Ace"))
        self.assertEqual((metadata["genre"], metadata["year"], metadata["decade"]), (["Rock"], 1981, "1980s"))

    def test_other_playing_track_is_ignored(self):
        kodi.play_file(OTHER, title="Overkill")
        self.assertEqual(main.get_current_player_metadata(TRACK), {})
        self.assertEqual(main.get_current_player_metadata()["title"], "Overkill")

    def test_freshness_is_cached_briefly(self):
        kodi.library_properties = {"songsmodified": "2026-10-01 00:00:00"}
        first = main.get_cached_audio_library_freshest_ts()
        kodi.library_properties = {"songsmodified": "2026-10-02 00:00:00"}
        self.assertEqual(main.get_cached_audio_library_freshest_ts(), first)
        self.assertEqual(kodi.jsonrpc_methods().count("AudioLibrary.GetProperties"), 1)


class SidecarSnapshotTest(KodiTestCase):
    def test_sidecar_map_is_keyed_by_canonical_path(self):
        meta = {"track_metadata_by_path": {TRACK: {"title": "Ace"}, OTHER: {"title": "01 Overkill"}, "": {"title": "x"}}}
        self.assertEqual(list(main.build_sidecar_track_metadata_map(meta)), [main.canonical_audio_path(TRACK)])
        self.assertEqual(main.build_sidecar_track_metadata_map({"track_metadata_by_path": "garbage"}), {})

    def test_collect_uses_sidecar_per_track(self):
        sidecar = {main.canonical_audio_path(TRACK): {"title": "Ace"}}
        titles = [m["title"] for m in main.collect_mix_track_metadata([TRACK, OTHER], sidecar, allow_live_lookup=False)]
        self.assertEqual(titles, ["Ace", "01 Overkill"])

    def test_set_snapshot_writes_sidecar(self):
        cache_path = self.save_mix([TRACK, OTHER])
        main.set_mix_track_metadata_snapshot(cache_path, [TRACK, OTHER], [{"title": "Ace", "library_freshest_ts": 9}, {}])
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        self.assertEqual(list(sidecar["track_metadata_by_path"]), [main.canonical_audio_path(TRACK)])
        self.assertEqual(sidecar["track_metadata_library_freshest_ts"], 9)


class MetadataRefreshQueueTest(KodiTestCase):
    def test_reasons(self):
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {}, 100), (True, "missing"))
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {"title": "Ace"}, 0), (False, ""))
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {"title": "Ace", "library_freshest_ts": 50}, 100), (True, "stale"))
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {"title": "Ace", "cached_ts": 50}, 100), (True, "stale"))
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {"title": "Ace"}, 100), (True, "missing_timestamp"))
        self.assertEqual(main.track_metadata_needs_background_refresh(TRACK, {"title": "Ace", "library_freshest_ts": 100}, 100), (False, ""))

    def test_enqueue_merges_entries_and_mix_paths(self):
        self.assertEqual(main.enqueue_metadata_refresh_for_tracks([TRACK, OTHER], cache_path="mix1.m3u", reason_context="browse"), 2)
        self.assertEqual(main.enqueue_metadata_refresh_for_tracks([TRACK], cache_path="mix2.m3u", reason_context="again"), 0)

        entries = main.load_metadata_refresh_queue()["entries"]
        self.assertEqual([entry["path"] for entry in entries], [TRACK, OTHER])
        self.assertEqual(entries[0]["cache_paths"], ["mix1.m3u", "mix2.m3u"])
        self.assertEqual(entries[0]["context"], "again")
        self.assertEqual(entries[0]["reason"], "missing")

    def test_fresh_metadata_is_not_queued(self):
        self.assertEqual(main.enqueue_metadata_refresh_for_tracks([TRACK], metadata_list=[{"title": "Ace", "cached_ts": 1}]), 0)
        self.assertFalse(os.path.exists(main.get_metadata_refresh_queue_path()))

    def test_corrupt_queue_file(self):
        self.write_json(main.get_metadata_refresh_queue_path(), {"entries": "garbage", "updated_ts": 3})
        self.assertEqual(main.load_metadata_refresh_queue(), {"version": 1, "updated_ts": 3, "entries": []})


class LabelFormattingTest(KodiTestCase):
    def test_kodi_track_template_is_used(self):
        metadata = {"title": "Ace of Spades", "artist": "Motörhead", "album": "Ace of Spades"}
        self.assertEqual(main.format_mix_track_label(TRACK, metadata, 3), "3. Motörhead - Ace of Spades")

    def test_optional_blocks_and_leftovers(self):
        kodi.kodi_settings["musicfiles.trackformat"] = "[%N. ]%A - %T [(%B)] %Z"
        main.KODI_MUSIC_TRACK_TEMPLATE_CACHE = None
        self.assertEqual(main.format_mix_track_label(TRACK, {"title": "Ace"}, 0), "(Unknown Artist) - Ace")
        self.assertEqual(main.format_mix_track_label(TRACK, {"title": "Ace", "artist": "M", "album": "B"}, 2), "2. M - Ace (B)")

    def test_fallback_template_when_kodi_setting_unavailable(self):
        kodi.kodi_settings.clear()
        main.KODI_MUSIC_TRACK_TEMPLATE_CACHE = None
        self.assertEqual(main.get_kodi_music_track_template(), main.KODI_MUSIC_TRACK_TEMPLATE_FALLBACK)
        self.assertEqual(main.format_mix_track_label(TRACK, {"artist": "M"}, 1), "1. M - 01 Ace of Spades")

    def test_missing_artist_and_title_get_placeholders(self):
        # The filename stands in for a missing title; the placeholder is only used when there is none.
        self.assertEqual(main.format_mix_track_label(TRACK, {}, 1), "1. (Unknown Artist) - 01 Ace of Spades")
        self.assertEqual(main.format_mix_track_label("", {"artist": "M"}, 2), "2. M - (Unknown Title)")
        self.assertEqual(main.format_mix_track_label("", {}, 3), "3. (Unknown Artist) - (Unknown Title)")

    def test_placeholders_stay_out_of_the_music_tag(self):
        kodi.library.add_song(TRACK, title="Ace of Spades")
        self.run_plugin(action="play_track", path=TRACK)
        self.assertEqual(kodi.resolved[0][1].getMusicInfoTag().getArtist(), "")

    def test_template_is_read_once(self):
        main.get_kodi_music_track_template()
        main.get_kodi_music_track_template()
        self.assertEqual(kodi.jsonrpc_methods().count("Settings.GetSettingValue"), 1)

    def test_cleanup_music_label(self):
        self.assertEqual(main.cleanup_music_label(" -  Ace  of Spades | ", "x"), "Ace of Spades")
        self.assertEqual(main.cleanup_music_label(" - ", "fallback"), "fallback")

    def test_track_details(self):
        self.assertEqual(main.format_track_details(year=1980, genres=["Metal"], duration=169), "1980s · Metal · 2:49")
        self.assertEqual(main.format_track_details(), "")

    def test_list_item_decoration(self):
        item = ListItem("x")
        main.apply_music_metadata(item, "Ace", artist="M", album="B", year=1980, duration=169, genres="Metal", track_number=2)
        main.apply_music_extra_properties(item, decade="1980s", genres=["Metal", "Rock"])
        main.apply_music_path(item, TRACK)
        main.apply_music_artwork(item, thumbnail="t.jpg", fanart="f.jpg")
        tag = item.getMusicInfoTag()
        self.assertEqual((tag.getTitle(), tag.getArtist(), tag.getTrack(), tag.getGenres(), tag.getYear()), ("Ace", "M", 2, ["Metal"], 1980))
        self.assertEqual(tag.getURL(), TRACK)
        self.assertEqual(item.getProperty("MusicIP.Genre"), "Metal / Rock")
        self.assertEqual(item.art, {"thumb": "t.jpg", "icon": "t.jpg", "fanart": "f.jpg"})


if __name__ == "__main__":
    unittest.main()
