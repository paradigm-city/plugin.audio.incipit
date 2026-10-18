"""The mix history (what happened to a saved mix), the mix information pages, and progress bars."""

import time
import unittest
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, MusicIPServerTestCase, main
from test_repair_matching import KING_BISCUIT_RETAGGED, MISSING_PATH, add_to_library

A, B, C, D = (f"D:\\music\\Artist\\Album\\0{n} Song {n}.mp3" for n in range(1, 5))
NEW1, NEW2 = "E:\\new\\1.mp3", "E:\\new\\2.mp3"


class HistoryTestCase(KodiTestCase):
    def history(self, cache_path):
        return self.read_json(main.mix_meta_path_from_cache_path(cache_path)).get("history", [])

    def progress_calls(self):
        return [call for call in kodi.dialog_calls if call[0].startswith("progress")]


class MixHistoryTest(HistoryTestCase):
    def test_creating_and_saving(self):
        main.remember_mix_generation_parameters(A, 3, {"size": 3, "variety": 4, "style_ui": 0, "rejectsize": 6})
        cache_path = self.save_mix([A, B, C], size=3)
        created, saved = self.history(cache_path)
        self.assertEqual((created["kind"], created["tracks"]), ("created", 3))
        self.assertEqual(created["seed"], main.path_to_label(A))
        self.assertEqual(created["parameters"], "variety 4, style 0/10, no artist repeat within 6 tracks, no filter")
        self.assertEqual((saved["kind"], saved["name"]), ("saved", main.path_to_label(A)))
        text = main.build_mix_history_text(self.read_json(main.mix_meta_path_from_cache_path(cache_path)))
        self.assertIn(f'Saved as "{main.path_to_label(A)}"', text)

    def test_mixes_from_older_versions_were_created_again(self):
        self.assertIn("Created again from", main.build_mix_history_text(
            {"history": [{"kind": "created", "again": True, "seed": "Song", "tracks": 2, "ts": 0}]}))

    def test_removing_a_track(self):
        cache_path = self.save_mix([A, B, C], size=3)
        main.remove_track_from_mix(A, 3, 1, B, cache_path=cache_path)
        self.assertEqual(self.history(cache_path)[-1]["kind"], "removed")
        self.assertEqual(self.history(cache_path)[-1]["track"], main.path_to_label(B))

    def test_labels_come_from_the_recorded_metadata(self):
        cache_path = self.save_mix([A, B], size=2)
        sidecar = self.read_json(main.mix_meta_path_from_cache_path(cache_path))
        sidecar["track_metadata_by_path"] = {main.canonical_audio_path(B): {"artist": "Motörhead", "title": "Overkill"}}
        self.write_json(main.mix_meta_path_from_cache_path(cache_path), sidecar)
        self.assertEqual(main.mix_track_labels(cache_path, [B, C]), ["Motörhead – Overkill", main.path_to_label(C)])

    def test_the_history_is_capped(self):
        cache_path = self.save_mix([A, B], size=2)
        for _ in range(main.MIX_HISTORY_LIMIT + 5):
            main.record_mix_history(cache_path, "removed", track="x")
        history = self.history(cache_path)
        self.assertEqual(len(history), main.MIX_HISTORY_LIMIT)
        self.assertEqual(history[0]["kind"], "removed")

    def test_history_text_is_newest_first(self):
        cache_path = self.save_mix([A, B, C], size=3, saved=False)
        main.record_mix_history(cache_path, "more_like_this", song="Song 2", added=["New 1", "New 2"])
        text = main.build_mix_history_text(self.read_json(main.mix_meta_path_from_cache_path(cache_path)))
        first, second = text.split("\n\n")
        self.assertIn('"More like this" for Song 2 added 2 track(s):', first)
        self.assertIn("    + New 1\n    + New 2", first)
        self.assertIn(f"Created from {main.path_to_label(A)}: 3 tracks", second)

    def test_unknown_events_are_shown_by_name(self):
        text = main.build_mix_history_text({"history": [{"kind": "something_new", "ts": 0}]})
        self.assertIn("something_new", text)
        self.assertIn("Nothing recorded yet", main.build_mix_history_text({}))


class MixInformationPagesTest(HistoryTestCase):
    def test_pages_work_like_tabs(self):
        cache_path = self.save_mix([A, B], size=2, saved=False)
        kodi.respond("select", 1, 0, -1)  # History, then Overview, then close
        self.run_plugin(action="mix_info", cache_path=cache_path)
        _method, (heading, choices), _kwargs = kodi.dialogs("select")[0]
        self.assertEqual((heading, choices), ("MusicIP mix information", ["Overview", "History (1)"]))
        pages = [call[1] for call in kodi.dialogs("textviewer")]
        self.assertEqual([heading for heading, _text in pages],
                         ["MusicIP mix information: History (1)", "MusicIP mix information: Overview"])
        self.assertIn("Created from", pages[0][1])
        self.assertIn("Seed:", pages[1][1])


class EditingHistoryAndProgressTest(MusicIPServerTestCase, HistoryTestCase):
    def setUp(self):
        super().setUp()
        kodi.settings["playlist_size"] = "10"  # More/Less like this change 20 % = 2 tracks
        kodi.info_labels["Container.PluginName"] = "plugin.audio.musicip"
        self.cache_path = self.save_mix([A, B, C, D], size=4)

    def test_more_like_this(self):
        self.musicip.set_mix(B, [A, NEW1, NEW2])
        self.run_plugin(action="more_like_this", seed=A, size="4", index="1", path=B, cache_path=self.cache_path)
        event = self.history(self.cache_path)[-1]
        self.assertEqual((event["kind"], event["song"]), ("more_like_this", main.path_to_label(B)))
        self.assertEqual(event["added"], [main.path_to_label(NEW1), main.path_to_label(NEW2)])
        calls = self.progress_calls()
        self.assertEqual(calls[0], ("progress.create", ("More like this", ""), {}))
        self.assertIn(("progress.update", (55, "More like this", "MusicIP is mixing"), {}), calls)
        self.assertEqual(calls[-1][0], "progress.close")

    def test_less_like_this(self):
        self.musicip.set_mix(B, [C])
        self.run_plugin(action="less_like_this", seed=A, size="4", index="1", path=B, cache_path=self.cache_path)
        event = self.history(self.cache_path)[-1]
        self.assertEqual((event["kind"], event["removed"]), ("less_like_this", [main.path_to_label(B), main.path_to_label(C)]))
        self.assertEqual(self.progress_calls()[0][1][0], "Less like this")
        self.assertEqual(self.progress_calls()[-1][0], "progress.close")

    def test_the_progress_bar_closes_when_musicip_fails(self):
        self.musicip.mix_status = 500
        self.run_plugin(action="less_like_this", seed=A, size="4", index="1", path=B, cache_path=self.cache_path)
        self.assertEqual(self.progress_calls()[-1][0], "progress.close")
        self.assertEqual(self.history(self.cache_path)[-1]["kind"], "saved")  # nothing recorded since

    def test_creating_a_mix_shows_progress(self):
        self.musicip.set_mix(C, [C, A, B])
        kodi.respond("select", 0)
        self.run_plugin(action="browse_mix", seed=C, size="3")
        calls = self.progress_calls()
        self.assertEqual(calls[0], ("progress.create", ("Creating a MusicIP mix", ""), {}))
        self.assertIn(("progress.update", (15, "Creating a MusicIP mix", "Updating MusicIP's library"), {}), calls)
        self.assertEqual(calls[-1][0], "progress.close")


class ProgressClockTest(HistoryTestCase):
    def test_a_long_step_shows_a_running_clock(self):
        with mock.patch.object(main.BackgroundProgress, "SHOW_CLOCK_AFTER", 0):
            with main.BackgroundProgress("Busy", tick=0.01) as progress:
                progress(40, "Waiting for MusicIP")
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and                         ("progress.update", (40, "Busy", "Waiting for MusicIP (0:00)"), {}) not in self.progress_calls():
                    time.sleep(0.01)
            calls = self.progress_calls()
        self.assertIn(("progress.update", (40, "Busy", "Waiting for MusicIP (0:00)"), {}), calls)
        self.assertEqual(calls[-1][0], "progress.close")
        self.assertFalse(progress.thread.is_alive())

    def test_short_steps_show_no_clock(self):
        with main.BackgroundProgress("Busy", tick=0.01) as progress:
            progress(10, "Quick")
        self.assertIn(("progress.update", (10, "Busy", "Quick"), {}), self.progress_calls())
        self.assertFalse(any("(0:" in str(call) for call in self.progress_calls()))


class RepairHistoryTest(HistoryTestCase):
    def setUp(self):
        super().setUp()
        self.present = "D:\\music\\Motorhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
        kodi.add_media(self.present)
        self.cache_path = self.save_mix([self.present, MISSING_PATH], seed=self.present, size=20)
        add_to_library(KING_BISCUIT_RETAGGED)

    def test_foreground_repair_is_recorded_with_progress(self):
        with main.BackgroundProgress("Repairing the mix") as progress:
            main.repair_saved_mix_foreground(self.cache_path, progress=progress)
        event = self.history(self.cache_path)[-1]
        self.assertEqual((event["kind"], event["automatic"]), ("repaired", False))
        self.assertEqual(event["replaced"], [{"old": main.path_to_label(MISSING_PATH),
                                              "new": main.path_to_label(KING_BISCUIT_RETAGGED["file"])}])
        self.assertIn("Checking track 2 of 2", [call[1][2] for call in self.progress_calls() if call[0] == "progress.update"])

    def test_automatic_repair_is_recorded(self):
        main.repair_saved_mix_automatic_only(self.cache_path)
        self.assertEqual(self.history(self.cache_path)[-1]["automatic"], True)


if __name__ == "__main__":
    unittest.main()
