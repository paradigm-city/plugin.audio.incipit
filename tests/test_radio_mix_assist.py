"""Radio with AI Mix Assist: the station's first songs are checked, refills are checked before they are queued."""

import threading
import unittest
from unittest import mock

from fake_kodi import kodi
from support import main, service
from test_radio_mode import RadioTestCase as RadioBase

REFERENCE = {"energy": 5, "sounding_year": 1983}
CHECK_RADIO_REFILL = main.check_radio_refill  # the real one; the tests below replace it


class RadioMixAssistTest(RadioBase):
    def setUp(self):
        super().setUp()
        service.RADIO_CHECK.update(thread=None, station=0, kind="", result=None, fallback=[], seed="")
        self.addCleanup(service.RADIO_CHECK.update, thread=None, result=None)
        patcher = mock.patch.object(main, "mix_assist_available", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.start_check = mock.Mock(return_value={"remove": [], "intent": "dark metal", "reference": REFERENCE})
        self.refill_check = mock.Mock(side_effect=self.choose_every_other)
        for name, fake in (("check_radio_start", self.start_check), ("check_radio_refill", self.refill_check)):
            patcher = mock.patch.object(main, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def choose_every_other(reference_song, candidates, count, reference, neighbours, check=None):
        return {"chosen": candidates[::2][:count], "reference": {"energy": 6, "sounding_year": 1984},
                "not_fitting": [{"path": path, "label": path, "reason": "no"} for path in candidates[1::2]]}

    def finish_check(self):
        thread = service.RADIO_CHECK.get("thread")
        if thread is not None:
            thread.join(5)

    def started_station(self):
        """A station (5 songs) whose start check is done, nothing removed, playing its third song: 2 songs are
        left, so the first refill check starts."""
        self.start()
        self.tick()  # starts the check of the first songs
        self.finish_check()
        self.tick()  # applies it
        kodi.go_to(2)
        return self.tick()

    def files(self):
        return [entry["file"] for entry in self.radio()["queue"]]

    def test_a_station_starts_small(self):
        self.start()
        self.assertEqual(self.musicip.mix_requests()[0]["size"], str(main.RADIO_ASSISTED_START_SIZE))

    def test_the_first_songs_lose_the_ones_that_dont_fit(self):
        self.start()
        queue = self.files()
        self.start_check.return_value = {"remove": [queue[1], queue[3]], "intent": "dark metal", "reference": REFERENCE}
        self.tick()
        self.finish_check()
        radio = self.tick()
        tracks = self.start_check.call_args[0][0]
        self.assertEqual(tracks[0], radio["seed"])  # the picked song first
        self.assertEqual(self.files(), [queue[0], queue[1], queue[2], queue[4]])  # the next song stays
        self.assertEqual(kodi.playlist_files(), self.files())
        self.assertEqual((radio["intent"], radio["reference"]), ("dark metal", REFERENCE))
        self.finish_check()
        self.tick()
        self.assertEqual(self.start_check.call_count, 1)

    def test_refills_are_checked_before_they_are_queued(self):
        self.start()
        before = self.files()
        self.tick()
        self.finish_check()
        self.tick()
        kodi.go_to(1)
        self.tick()
        self.assertEqual(len(self.musicip.mix_requests()), 1)  # 3 songs left: no refill yet
        kodi.go_to(2)
        self.tick()
        self.assertEqual(self.musicip.mix_requests()[-1]["size"], str(service.RADIO_CHECK_SIZE))
        self.assertEqual(self.files(), before)  # nothing queued while the check runs
        self.finish_check()
        radio = self.tick()
        reference_song, candidates, count, reference, neighbours = self.refill_check.call_args[0]
        self.assertEqual(reference_song, before[-1])  # "Drift slowly": judged against the refill's seed
        self.assertEqual((count, reference, neighbours), (service.RADIO_CHECKED_BATCH, REFERENCE, before))
        self.assertEqual(self.files(), before + candidates[::2])
        self.assertEqual(kodi.playlist_files(), self.files())
        self.assertEqual(radio["reference"], {"energy": 6, "sounding_year": 1984})

    def test_staying_close_judges_against_the_picked_song(self):
        kodi.settings["mix_assist_radio_drift"] = "0"
        radio = self.started_station()
        self.finish_check()
        self.assertEqual(self.refill_check.call_args[0][0], radio["seed"])

    def test_when_nothing_fits_an_earlier_song_seeds_the_next_try(self):
        self.refill_check.side_effect = None
        self.refill_check.return_value = {"chosen": [], "reference": REFERENCE,
                                          "not_fitting": [{"path": "x", "label": "x", "reason": "no"}]}
        self.started_station()
        before = self.files()
        self.finish_check()
        radio = self.tick()
        self.assertEqual(self.files(), before)
        self.assertEqual(radio["refill_seed_offset"], 1)
        self.tick(service.RADIO_REFILL_RETRY_SECONDS)
        self.assertEqual(self.musicip.mix_requests()[-1]["song"], before[-2])

    def test_a_failed_check_keeps_the_station_going_unchecked(self):
        self.refill_check.side_effect = main.mix_assist_claude.ClaudeError(main.mix_assist_claude.USAGE_LIMIT, "limit")
        self.started_station()
        before = self.files()
        self.finish_check()
        self.tick()
        self.assertGreater(len(self.files()), len(before))
        self.assertNotified("Claude's usage limit is reached")

    def test_a_slow_check_never_lets_the_station_run_dry(self):
        release = threading.Event()

        def slow(*args, **kwargs):
            release.wait(5)
            return self.choose_every_other(*args, **kwargs)

        self.refill_check.side_effect = slow
        self.started_station()  # the refill check now runs (and waits)
        before = self.files()
        kodi.go_to(len(before) - 2)
        self.tick()
        self.assertEqual(self.files(), before)  # one song still to come: keep waiting
        kodi.go_to(len(before) - 1)  # the last song plays
        self.tick()
        fallback = self.files()[len(before):]
        self.assertEqual(fallback, self.refill_check.call_args[0][1][:service.RADIO_CHECKED_BATCH])
        release.set()
        self.finish_check()
        radio = self.tick()
        self.assertEqual(self.files(), before + fallback)  # the check's songs are not added on top
        self.assertEqual(radio["reference"], {"energy": 6, "sounding_year": 1984})

    def test_results_for_an_earlier_station_are_dropped(self):
        self.start()
        queue = self.files()
        self.start_check.return_value = {"remove": [queue[3]], "intent": "x", "reference": REFERENCE}
        self.tick()
        self.finish_check()
        main.save_radio_state(dict(self.radio(), playing_started_ts=self.radio()["playing_started_ts"] + 1))
        self.tick()
        self.assertEqual(self.files(), queue)

    def test_station_strictness_and_drift_reach_the_check(self):
        kodi.settings.update({"mix_assist_station_strictness": "4", "mix_assist_radio_drift": "2"})
        chosen = {"chosen": ["b"], "entries": {"b": {"energy": 9, "sounding_year": 1983}}, "seed_entry": None,
                  "not_fitting": []}
        with mock.patch.object(main.mix_assist, "choose_additions", return_value=chosen) as choose, \
                mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}):
            result = CHECK_RADIO_REFILL("a", ["b"], 8, REFERENCE, ["x", "y"])
        kwargs = choose.call_args[1]
        self.assertEqual((kwargs["strictness"], kwargs["accept_borderline"], kwargs["reference"]), (1.5, True, REFERENCE))
        step = 1 - 0.5 ** (1 / 20)  # "Wander freely": half the way after 20 songs
        self.assertAlmostEqual(result["reference"]["energy"], 5 + step * 4)

    def test_station_strictness_is_its_own_setting(self):
        kodi.settings.update({"mix_assist_station_strictness": "1", "mix_assist_mix_strictness": "4"})
        self.assertEqual(main.get_station_strictness(), (1.1, False))

    def test_station_information_shows_what_happened_and_the_drift(self):
        self.started_station()
        self.finish_check()
        radio = self.tick()
        kinds = [event["kind"] for event in radio["events"]]
        self.assertEqual(kinds, ["started", "start_check", "refill"])
        refill = radio["events"][-1]
        self.assertEqual((refill["checked"], refill["skipped_count"], len(refill["added"])), (True, len(refill["skipped"]), 2))
        self.assertEqual(refill["seed"], radio["queue"][4]["label"])
        pages = dict(main.radio_info_pages(radio))
        self.assertEqual(list(pages)[:3], ["Overview", "What it is about", "Drift"])
        self.assertIn("AI Mix Assist: on · Station openness: Balanced · Station drift: Drift slowly", pages["Overview"])
        self.assertIn("Refills: 1 (1 checked, 0 unchecked)", pages["Overview"])
        self.assertIn("The picked song:\ndark metal", pages["What it is about"])
        self.assertIn("Energy: 5.0 steady → 6.0 steady (+1.0) · course: 5.0, 6.0", pages["Drift"])
        self.assertIn("Sounding year: 1983 → 1984 (+1.0 years)", pages["Drift"])
        self.assertIn("Moved most: Energy (+1.0)", pages["Drift"])
        history = pages[f"History ({len(kinds)})"]
        self.assertTrue(history.split("\n")[0].endswith("2 song(s), checked"))
        self.assertIn("AI Mix Assist checked the first songs: all fit", history)

    def test_station_information_from_the_radio_screen(self):
        self.started_station()
        kodi.respond("select", 2, -1)  # Drift, then close
        self.run_plugin(action="radio_info")
        self.assertEqual(kodi.dialogs("select")[0][1], ("Radio station", ["Overview", "What it is about", "Drift",
                                                                          "History (2)"]))
        self.assertEqual(kodi.dialogs("textviewer")[0][1][0], "Radio station: Drift")

    def test_without_the_claude_cli_radio_works_as_before(self):
        with mock.patch.object(main, "mix_assist_available", return_value=False):
            self.start()
            self.assertEqual(self.musicip.mix_requests()[0]["size"], str(main.get_playlist_size()))
            kodi.go_to(3)
            self.tick()
        self.start_check.assert_not_called()
        self.refill_check.assert_not_called()
        self.assertEqual(len(self.files()), 9)


if __name__ == "__main__":
    unittest.main()
