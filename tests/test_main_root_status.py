"""The first screen's second texts: what the current mix, the radio and Discovery are doing."""

import time
import unittest

from fake_kodi import kodi
from support import KodiTestCase, main


class RootStatusTest(KodiTestCase):
    def labels2(self):
        kodi.directory_items.clear()
        self.run_plugin()
        return {item.getLabel(): item.getLabel2() for _url, item, _folder in kodi.directory_items}

    def test_kodi_keeps_the_second_lines(self):
        main.save_discovery_state({"enabled": True, "current_label": "Moby – Porcelain"})
        kodi.directory_items.clear()
        self.run_plugin()
        item = {item.getLabel(): item for _url, item, _folder in kodi.directory_items}["Discovery mode"]
        self.assertEqual(item.getMusicInfoTag().getArtist(), "Moby - Porcelain")  # where skins show it (plain here)
        self.assertIn(("addSortMethod", main.xbmcplugin.SORT_METHOD_UNSORTED, {"labelMask": "%L", "label2Mask": "%A"}),
                      kodi.directory_calls)

    def test_nothing_runs(self):
        status = self.labels2()
        self.assertEqual((status["Radio mode"], status["Discovery mode"]), ("", ""))

    def test_the_current_mix_its_name_and_length(self):
        tracks = ["D:\\a.mp3", "D:\\b.mp3"]
        cache_path = self.save_mix(tracks, seed=tracks[0], saved=False)
        meta = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        meta["track_metadata_by_path"] = {main.canonical_audio_path(t): {"title": "x", "duration": 1900} for t in tracks}
        self.write_json(main.mix_meta_path_from_cache_path(cache_path), meta)
        name = main.saved_mix_name(main.get_saved_mix_metadata(cache_path))
        self.assertEqual(self.labels2()["Current mix"], f"{name} | 1 h 03 min | not saved")
        self.assertEqual(main.format_mix_length(59 * 60), "59 min")

    def test_a_playing_station_shows_its_song(self):
        main.save_radio_state({"phase": "playing", "current_label": "Air – La femme d'argent",
                               "playing_started_ts": int(time.time())})
        self.assertEqual(self.labels2()["Radio mode"], "Air - La femme d'argent")  # what plays, not since when
        main.save_radio_state(dict(main.get_radio_state(), name="Night Drive", favourite_id="f1"))
        self.assertEqual(self.labels2()["Radio mode"], "Night Drive: Air - La femme d'argent")  # with its name

    def test_scanning_shows_the_snippet_on_the_radio_not_on_discovery(self):
        main.save_radio_state({"phase": "seeking"})
        main.save_discovery_state({"enabled": True, "owner": "radio", "current_label": "Moby – Porcelain"})
        status = self.labels2()
        self.assertEqual((status["Radio mode"], status["Discovery mode"]), ("Scanning: Moby - Porcelain", ""))

    def test_discovery_shows_its_snippet(self):
        main.save_discovery_state({"enabled": True, "current_label": "Moby – Porcelain"})
        self.assertEqual(self.labels2()["Discovery mode"], "Moby - Porcelain")


if __name__ == "__main__":
    unittest.main()
