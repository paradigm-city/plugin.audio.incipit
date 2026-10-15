"""Radio with AI Mix Assist: the station's first songs are checked, refills are checked before they are queued."""

import unittest
from unittest import mock

from fake_kodi import kodi
from support import main, service
from test_radio_mode import RadioTestCase as RadioBase

REFERENCE = {"energy": 5, "sounding_year": 1983}


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
        """A station whose start check is done (nothing removed). With 5 songs it is short, so the first refill
        check starts right away."""
        self.start()
        self.tick()  # starts the check of the first songs
        self.finish_check()
        return self.tick()  # applies it and starts the first refill check

    def files(self):
        return [entry["file"] for entry in self.radio()["queue"]]

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
        self.assertEqual(self.musicip.mix_requests()[-1]["size"], str(service.RADIO_CHECK_SIZE))
        self.assertEqual(self.files(), before)  # nothing queued while the check runs
        self.finish_check()
        radio = self.tick()
        reference_song, candidates, count, reference, neighbours = self.refill_check.call_args[0]
        self.assertEqual(reference_song, before[-1])  # "Drift slowly": judged against the refill's seed
        self.assertEqual((count, reference, neighbours), (main.get_playlist_size(), REFERENCE, before))
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

    def test_results_for_an_earlier_station_are_dropped(self):
        self.start()
        queue = self.files()
        self.start_check.return_value = {"remove": [queue[3]], "intent": "x", "reference": REFERENCE}
        self.tick()
        self.finish_check()
        main.save_radio_state(dict(self.radio(), playing_started_ts=self.radio()["playing_started_ts"] + 1))
        self.tick()
        self.assertEqual(self.files(), queue)

    def test_without_the_claude_cli_radio_works_as_before(self):
        with mock.patch.object(main, "mix_assist_available", return_value=False):
            self.start()
            kodi.go_to(3)
            self.tick()
        self.start_check.assert_not_called()
        self.refill_check.assert_not_called()
        self.assertEqual(len(self.files()), 9)


if __name__ == "__main__":
    unittest.main()
