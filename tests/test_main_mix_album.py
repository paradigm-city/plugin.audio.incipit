"""A saved mix shown as a compilation album: album fields, the seed song, and a collage of its covers."""

import os
import unittest

from fake_kodi import kodi
from support import KodiTestCase, main, service

TRACKS = [f"D:\\music\\Artist {index % 5}\\Album {index}\\{index:02d} Song.mp3" for index in range(20)]


def snapshot(index, **extra):
    values = {"title": f"Song {index}", "artist": f"Artist {index % 5}", "album": f"Album {index}",
              "genre": ["Rock"] if index % 2 else ["Rock", "Blues"], "year": 1970 + index, "duration": 200,
              "thumbnail": f"image://cover{index}.jpg/", "fanart": f"image://fanart{index}.jpg/"}
    values.update(extra)
    return values


class MixAlbumTestCase(KodiTestCase):
    def setUp(self):
        super().setUp()
        self.cache_path = self.save_mix(TRACKS, seed=TRACKS[3])
        meta = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        meta["track_metadata_by_path"] = {main.canonical_audio_path(track): snapshot(index)
                                          for index, track in enumerate(TRACKS)}
        meta["updated_ts"] = 1791300000
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), meta)

    def mix_item(self):
        kodi.directory_items.clear()
        date = main.format_calendar_date(1791300000)
        self.run_plugin(action="saved_mixes_by_date", date=date)
        (item,) = [item for _url, item, _folder in kodi.directory_items]
        return item

    def add_covers(self, count, size=(300, 200)):
        from PIL import Image
        folder = kodi.translate_path("special://thumbnails/c")
        os.makedirs(folder, exist_ok=True)
        for index in range(count):
            Image.new("RGB", size, (index * 10, 80, 160)).save(os.path.join(folder, f"{index}.jpg"))
            kodi.textures[f"image://cover{index}.jpg/"] = f"c/{index}.jpg"


class MixAlbumTest(MixAlbumTestCase):
    def test_the_mix_is_a_compilation_album_with_its_seed_song(self):
        item = self.mix_item()
        tag = item.getMusicInfoTag()
        self.assertIn(("setContent", "albums"), kodi.directory_calls)
        self.assertEqual((tag.getMediaType(), tag.getAlbumArtist()), ("album", "MusicIP"))
        self.assertEqual(tag.getAlbum(), main.saved_mix_name(main.get_saved_mix_metadata(self.cache_path)))
        self.assertTrue(tag.getArtist().startswith("Artist 3 - Song 3 | "))  # the seed song: the second line
        self.assertEqual(tag.getArtist(), item.getLabel2())
        self.assertIn(("addSortMethod", main.xbmcplugin.SORT_METHOD_UNSORTED, {"labelMask": "%L", "label2Mask": "%A"}),
                      kodi.directory_calls)  # Kodi keeps it as the second label
        self.assertEqual(tag.getGenres(), ["Rock", "Blues"])
        self.assertEqual((tag.getYear(), tag.getDuration()), (1980, 20 * 200))  # the middle release year
        self.assertTrue(item.getLabel2().startswith("Artist 3 - Song 3 | "))  # plain punctuation on this branch
        self.assertEqual(item.getProperty("Album_Description"),
                         "From: Artist 3 - Song 3\nArtists: Artist 3, Artist 0, Artist 1, Artist 2, Artist 4")
        self.assertEqual((item.getProperty("Album_Type"), item.getProperty("Album_Label")), ("Mix", "MusicIP"))
        self.assertEqual((item.getArt("thumb"), item.getArt("fanart")), ("image://cover3.jpg/", "image://fanart3.jpg/"))

    def test_ai_mix_assist_adds_what_it_is_about_and_the_sound_in_words(self):
        meta = self.read_json(main.mix_meta_path_from_cache_path(self.cache_path))
        meta["mix_assist"] = {"intent": "dark, abstract, instrumental", "profile": {"values": {
            "energy": [5.0, 2, 8], "mood": [2.6, 1, 4], "danceability": [3.7, 2, 7], "exploration": [2.5, 1, 6],
            "making": [0.6, 0, 4], "production": [6.7, 4, 8], "form": [8.1, 7, 9], "sounding_year": [1991, 1972, 2020]}}}
        self.write_json(main.mix_meta_path_from_cache_path(self.cache_path), meta)
        item = self.mix_item()
        self.assertEqual(item.getProperty("Album_Description"), "dark, abstract, instrumental\nFrom: Artist 3 - Song 3\n"
                         "Artists: Artist 3, Artist 0, Artist 1, Artist 2, Artist 4")
        self.assertEqual(item.getProperty("Album_Mood"), "steady, brooding, swaying")
        self.assertEqual(item.getProperty("Album_Style"), "familiar, hand-played, clean, song")

    def test_a_short_artist_list_is_shown_whole(self):
        self.assertEqual(main.mix_artist_text(["A", "B"]), "A, B")

    def test_covers_are_spread_over_the_mix_the_seeds_first(self):
        self.assertEqual(main.pick_spread(list("abcdefghij"), 4), ["a", "b", "f", "j"])
        self.assertEqual(main.pick_spread(list("abc"), 4), ["a", "b", "c"])


class MixCollageTest(MixAlbumTestCase):
    def test_a_4_by_4_collage_becomes_the_mixs_picture(self):
        from PIL import Image
        self.add_covers(20)
        path = main.make_mix_collage(self.cache_path)
        self.assertEqual(path, main.mix_collage_path(self.cache_path, TRACKS))
        image = Image.open(path)
        self.assertEqual(image.size, (800, 800))
        cell = (800 - 3 * main.COLLAGE_GAP) // 4
        red, green, _blue = image.getpixel((cell // 2, cell // 2))
        self.assertLess(abs(red - green), abs(30 - 80))  # softened: the colours of the seed's cover move together
        self.assertLess(red, green)  # the seed's cover first (red 30, green 80)
        self.assertEqual(self.mix_item().getArt("thumb"), path)

    def test_a_wide_collage_becomes_the_mixs_fanart(self):
        from PIL import Image
        self.add_covers(20)  # 20 covers: 6 x 3 (8 x 4 needs 32)
        main.make_mix_collage(self.cache_path)
        wide = main.mix_collage_path(self.cache_path, TRACKS, "fanart")
        self.assertEqual(Image.open(wide).size, (1920, 960))
        item = self.mix_item()
        self.assertEqual((item.getArt("fanart"), item.getArt("landscape")), (wide, wide))
        for index in range(20, 40):
            kodi.textures[f"image://cover{index}.jpg/"] = "c/0.jpg"  # same picture: counted once
        self.assertEqual(len(main.mix_cover_files(main.get_saved_mix_metadata(self.cache_path), TRACKS)), 20)

    def test_fewer_covers_make_a_smaller_fanart_or_leave_the_seeds(self):
        self.add_covers(8)
        self.assertTrue(main.make_mix_collage(self.cache_path))
        self.assertTrue(main.existing_mix_collage(self.cache_path, TRACKS, "fanart"))
        kodi.textures.clear()
        self.add_covers(5)
        main.save_mix_by_cache_path(self.cache_path, TRACKS[:19])
        self.assertTrue(main.make_mix_collage(self.cache_path))  # 2 x 2 cover, too few for a fanart
        self.assertEqual(main.existing_mix_collage(self.cache_path, TRACKS[:19], "fanart"), "")
        self.assertEqual(self.mix_item().getArt("fanart"), "image://fanart3.jpg/")  # the seed's

    def test_a_new_drawing_style_draws_the_collages_again(self):
        first = main.mix_collage_path(self.cache_path, TRACKS)
        original = main.COLLAGE_STYLE
        try:
            main.COLLAGE_STYLE = "next"
            self.assertNotEqual(main.mix_collage_path(self.cache_path, TRACKS), first)
        finally:
            main.COLLAGE_STYLE = original

    def test_another_mixs_collages_are_left_alone(self):
        self.add_covers(20)
        other = os.path.join(os.path.dirname(main.mix_collage_path(self.cache_path, TRACKS)),
                             os.path.splitext(os.path.basename(self.cache_path))[0] + "_1792346220176_0123456789ab.jpg")
        os.makedirs(os.path.dirname(other), exist_ok=True)
        open(other, "wb").close()  # a mix whose name begins with this one's
        main.make_mix_collage(self.cache_path)
        self.assertTrue(os.path.isfile(other))

    def test_fewer_covers_make_a_smaller_grid_or_none(self):
        self.add_covers(3)
        self.assertEqual(main.make_mix_collage(self.cache_path), "")  # too few: the seed's cover stays
        self.assertEqual(self.mix_item().getArt("thumb"), "image://cover3.jpg/")
        self.add_covers(10)
        self.assertTrue(main.make_mix_collage(self.cache_path))  # 3 x 3

    def test_a_changed_mix_gets_a_new_collage_and_the_old_one_goes(self):
        self.add_covers(20)
        old = main.make_mix_collage(self.cache_path)
        main.save_mix_by_cache_path(self.cache_path, TRACKS[:18])
        new = main.make_mix_collage(self.cache_path)
        self.assertNotEqual(old, new)
        self.assertEqual(sorted(os.listdir(os.path.dirname(new))),
                         sorted([os.path.basename(new), os.path.basename(new).replace(".jpg", "_fanart.jpg")]))

    def test_the_service_draws_missing_collages_one_at_a_time(self):
        self.add_covers(20)
        service.MIX_COLLAGE_STATE.update(last_ts=0, tried={})
        self.assertEqual(service.run_mix_collage_tick(), main.mix_collage_path(self.cache_path, TRACKS))
        service.MIX_COLLAGE_STATE["last_ts"] = 0
        self.assertEqual(service.run_mix_collage_tick(), "")  # there already
        kodi.textures.clear()
        main.save_mix_by_cache_path(self.cache_path, TRACKS[:18])
        service.MIX_COLLAGE_STATE["last_ts"] = 0
        self.assertEqual(service.run_mix_collage_tick(), "")  # too few covers: tried once, not again
        self.assertIn(self.cache_path, service.MIX_COLLAGE_STATE["tried"])


if __name__ == "__main__":
    unittest.main()
