"""Radio with AI Mix Assist: the station's first songs are checked ("More like this" for the picked song), refills
are checked before they are queued and seeded from songs that passed a check."""

import os
import threading
import unittest
from unittest import mock

from fake_kodi import kodi
from support import main, service
from test_radio_mode import SONGS, RadioTestCase as RadioBase

REFERENCE = {"energy": 5, "sounding_year": 1983}
CHECK_RADIO_REFILL = main.check_radio_refill  # the real ones; the tests below replace them
CHECK_RADIO_START = main.check_radio_start


class RadioMixAssistTest(RadioBase):
    def setUp(self):
        super().setUp()
        service.RADIO_CHECK.update(thread=None, station=0, kind="", result=None, fallback=[], seed="")
        self.addCleanup(service.RADIO_CHECK.update, thread=None, result=None)
        patcher = mock.patch.object(main, "mix_assist_available", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.start_check = mock.Mock(side_effect=self.all_first_songs_fit)
        self.refill_check = mock.Mock(side_effect=self.choose_every_other)
        for name, fake in (("check_radio_start", self.start_check), ("check_radio_refill", self.refill_check)):
            patcher = mock.patch.object(main, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def all_first_songs_fit(tracks, count, check=None, settings=None, intent=""):
        return {"chosen": tracks[1:][:count], "not_fitting": [], "intent": "dark metal", "reference": REFERENCE,
                "name": "", "checked": True}

    def start_result(self, chosen, not_fitting=(), **extra):
        self.start_check.side_effect = None
        self.start_check.return_value = dict({"chosen": list(chosen), "intent": "dark metal", "reference": REFERENCE,
                                              "checked": True, "name": "",
                                              "not_fitting": [{"path": path, "label": os.path.basename(path), "reason": "no"}
                                                              for path in not_fitting]}, **extra)

    @staticmethod
    def choose_every_other(reference_song, candidates, count, reference, neighbours, check=None, settings=None,
                           **_more):
        return {"chosen": candidates[::2][:count], "reference": {"energy": 6, "sounding_year": 1984},
                "not_fitting": [{"path": path, "label": path, "reason": "no"} for path in candidates[1::2]]}

    def finish_check(self):
        thread = service.RADIO_CHECK.get("thread")
        if thread is not None:
            thread.join(5)

    def started_station(self, started=False):
        """A station (5 songs) whose start check is done, nothing removed, playing its third song: 2 songs are
        left, so the first refill check starts."""
        if not started:
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
        self.assertEqual(self.source.mix_requests()[0]["size"], str(main.RADIO_BATCH_SIZE_DEFAULT))

    def test_songs_per_refill_is_a_setting_kept_by_the_station(self):
        kodi.settings["radio_batch_size"] = "3"
        self.start()
        self.assertEqual(self.source.mix_requests()[0]["size"], "3")  # it starts with one refill's worth
        self.assertEqual(self.radio()["batch"], 3)
        self.tick()
        self.finish_check()
        self.assertEqual(self.start_check.call_args[0][1], 3)
        kodi.settings["radio_batch_size"] = "9"  # for the next station
        self.tick()  # applies the start check
        kodi.go_to(len(self.files()) - 1)
        self.tick()  # the refill check starts
        self.finish_check()
        self.assertEqual(self.refill_check.call_args[0][2], 3)
        self.assertIn("Songs per refill: 3", main.build_radio_overview(self.radio(), self.radio()["events"]))

    def test_songs_per_refill_stays_within_2_and_10(self):
        for value, expected in (("1", 2), ("2", 2), ("10", 10), ("25", 10), ("", 6)):
            with self.subTest(value=value):
                kodi.settings["radio_batch_size"] = value
                self.assertEqual(main.get_radio_batch_size(), expected)
        self.assertEqual(main.station_batch_size({"batch": 4}), 4)
        self.assertEqual(main.station_batch_size({}), 6)  # a station from before: the setting

    def new_songs(self, count):
        """Library songs the station hasn't queued."""
        queued = set(self.files())
        return [song for song in SONGS if song not in queued][:count]

    def test_the_first_songs_are_held_to_more_like_this_for_the_picked_song(self):
        self.start()
        queue = self.files()
        new = self.new_songs(3)
        self.start_result([queue[2], queue[4]] + new, not_fitting=[queue[1], queue[3]])
        self.tick()
        self.finish_check()
        radio = self.tick()
        tracks, count = self.start_check.call_args[0][:2]
        self.assertEqual(tracks, queue)  # the picked song first, then the first songs
        self.assertEqual(count, main.RADIO_BATCH_SIZE_DEFAULT)
        self.assertEqual(self.files(), [queue[0], queue[2], queue[4]] + new)  # the next song left too
        self.assertEqual(kodi.playlist_files(), self.files())
        self.assertEqual([entry.get("checked", False) for entry in radio["queue"]], [False, True, True, True, True, True])
        self.assertEqual((radio["intent"], radio["reference"]), ("dark metal", REFERENCE))
        event = radio["events"][-1]
        self.assertEqual(([entry["reason"] for entry in event["removed"]], event["kept"], len(event["added"])),
                         (["no", "no"], 2, 3))
        history = dict(main.radio_info_pages(radio))[f"History ({len(radio['events'])})"]
        self.assertIn("The first songs were checked: 2 taken out, 3 added", history)
        self.finish_check()
        self.tick()
        self.assertEqual(self.start_check.call_count, 1)

    def test_the_next_song_stays_when_the_playing_song_is_about_to_end(self):
        self.start()
        queue = self.files()
        self.start_result([queue[2]], not_fitting=[queue[1], queue[3], queue[4]])
        self.tick()
        self.finish_check()
        kodi.player.time = kodi.player.total_time - service.RADIO_START_KEEP_NEXT_SECONDS + 1
        self.tick()
        self.assertEqual(self.files(), [queue[0], queue[1], queue[2]])
        self.assertNotIn("checked", self.radio()["queue"][1])  # it stays, unchecked

    def test_without_a_measurement_the_first_songs_stay(self):
        self.start()
        queue = self.files()
        self.start_result(queue[1:3], checked=False)
        self.tick()
        self.finish_check()
        radio = self.tick()
        self.assertEqual(self.files(), queue)
        self.assertFalse(any(entry.get("checked") for entry in radio["queue"]))
        self.assertTrue(radio["events"][-1]["unchecked"])

    def test_refills_seed_from_the_last_song_that_passed_a_check(self):
        self.start()
        queue = self.files()
        self.start_result([queue[1], queue[2]], not_fitting=[queue[3], queue[4]])  # the last two leave
        self.tick()
        self.finish_check()
        self.tick()  # applies it; 2 songs left: the first refill
        self.assertEqual(self.source.mix_requests()[-1]["song"], queue[2])
        self.finish_check()
        self.tick()
        unchecked = self.new_songs(1)
        service.append_radio_tracks(self.radio(), main, queue[2], unchecked)  # e.g. queued unchecked to keep playing
        state = self.radio()
        state = dict(state, queue=state["queue"] + [{"file": unchecked[0], "label": "x"}])
        self.assertNotEqual(service.refill_seed_entries(state, True)[0]["file"], unchecked[0])
        self.assertEqual(service.refill_seed_entries(state, True)[-1]["file"], state["seed"])  # at last the picked song
        self.assertEqual(service.refill_seed_entries(state, False)[0]["file"], unchecked[0])  # AI Mix Assist off

    def test_songs_turned_down_are_not_checked_again_while_the_station_plays(self):
        self.started_station()  # the first refill check: every other candidate is turned down
        self.finish_check()
        radio = self.tick()
        turned_down = self.refill_check.call_args[0][1][1::2]
        self.assertTrue(turned_down)
        self.assertEqual(set(radio["rejected"]), {main.normalize_track_identity(path) for path in turned_down})
        seed = service.refill_seed_entries(radio, True)[0]["file"]
        fresh = [song for song in self.new_songs(len(SONGS)) if song not in turned_down][:2]
        self.source.set_mix(seed, turned_down + fresh)
        service.refill_radio_queue(radio, checked=True)
        self.finish_check()
        args, kwargs = self.refill_check.call_args
        self.assertEqual(args[1], fresh)
        self.assertTrue({main.normalize_track_identity(path) for path in turned_down} <= set(kwargs["seen"]))
        self.assertEqual(service.RADIO_CHECK["fallback"], turned_down + fresh)  # they may still keep it playing

    def test_the_station_forgets_them_when_it_stops_or_its_settings_change(self):
        first, second = (main.normalize_track_identity(song) for song in SONGS[1:3])
        state = {"settings": {}}
        service.remember_rejected(state, main, {"not_fitting": [{"path": SONGS[1]}, {"path": SONGS[1]}]})
        self.assertEqual((state["rejected"], service.rejected_songs(state, main)), ([first], {first}))
        kodi.settings["mix_assist_station_perspective"] = "2"  # judged differently from now on
        self.assertEqual(service.rejected_songs(state, main), set())
        service.remember_rejected(state, main, {"not_fitting": [{"path": SONGS[2]}]})
        self.assertEqual(service.rejected_songs(state, main), {second})
        state["settings"] = {"openness": 4}  # a favourite's own, changed while it plays
        self.assertEqual(service.rejected_songs(state, main), set())
        service.end_radio(state, "player_stop")
        self.assertNotIn("rejected", state)

    def test_without_checked_songs_refills_seed_from_the_picked_song(self):
        self.start()
        queue = self.files()
        self.start_result(queue[1:3], checked=False)
        self.tick()
        self.finish_check()
        self.tick()
        kodi.go_to(2)
        self.tick()
        self.assertEqual(self.source.mix_requests()[-1]["song"], queue[0])

    def test_a_stricter_station_examines_more(self):
        self.assertEqual([main.radio_check_batches({"openness": level}) for level in range(5)], [6, 4, 2, 2, 2])
        with mock.patch.object(main.mix_assist, "choose_additions", return_value={"chosen": [], "entries": {}}) as choose, \
                mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}):
            CHECK_RADIO_REFILL("a", ["b"], 6, REFERENCE, ["x"], settings={"openness": 0})
        self.assertEqual(choose.call_args[1]["max_batches"], 6)
        self.assertTrue(callable(choose.call_args[1]["more"]))

    def test_a_check_judges_from_the_stations_perspective(self):
        kodi.settings["mix_assist_station_perspective"] = "1"
        with mock.patch.object(main.mix_assist, "choose_additions", return_value={"chosen": [], "entries": {}}) as choose, \
                mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}):
            CHECK_RADIO_REFILL("a", ["b"], 6, REFERENCE, ["x"], settings={})
            self.assertEqual(choose.call_args[1]["perspective"], "technical")
            CHECK_RADIO_REFILL("a", ["b"], 6, REFERENCE, ["x"], settings={"perspective": 2})  # a favourite's own
            self.assertEqual(choose.call_args[1]["perspective"], "emotional")

    def test_more_candidates_come_from_the_songs_that_fit_then_earlier_seeds(self):
        mixes = {"chosen2": ["chosen2", "known", "n1"], "chosen1": ["n2"], "older": ["n3"]}
        requested = []

        def fetch(seed, size, params=None):
            requested.append(seed)
            return mixes[seed]

        with mock.patch.object(main, "fetch_mix", side_effect=fetch):
            more = main.radio_more_candidates(["older"], [main.normalize_track_identity("known")])
            self.assertEqual(more(["chosen1", "chosen2"]), ["chosen2", "n1"])  # the newest song that fits first
            self.assertEqual(more(["chosen1", "chosen2"]), ["n2"])
            self.assertEqual(more(["chosen1", "chosen2"]), [])  # RADIO_CHECK_LISTS: the first list and 2 more
        self.assertEqual(requested, ["chosen2", "chosen1"])

    def test_staying_close_looks_again_at_the_picked_song_first(self):
        requested = []

        def fetch(seed, size, params=None):
            requested.append((seed, params["variety"]))
            return [seed, f"new from {seed}"]

        with mock.patch.object(main, "fetch_mix", side_effect=fetch):
            more = main.radio_more_candidates(["older", "picked"], [], {"drift": 0}, picked="picked")
            self.assertEqual(more(["chosen"]), ["picked", "new from picked"])
            self.assertEqual(more(["chosen"]), ["chosen", "new from chosen"])
            self.assertEqual(more(["chosen"]), [])  # the first list and 2 more; "picked" not asked twice
            requested.clear()
            more = main.radio_more_candidates(["older"], [], {"drift": 1}, picked="picked")
            more(["chosen"])
        self.assertEqual(requested, [("chosen", 0)])  # drifting: the songs that fit first, the variety as set

    def test_staying_close_keeps_musicips_mixes_from_repeating(self):
        kodi.settings["radio_variety"] = "0"
        self.assertEqual(main.radio_mix_parameters(75, {"drift": 0})["variety"], main.RADIO_STAY_CLOSE_MIN_VARIETY)
        self.assertEqual(main.radio_mix_parameters(75, {"drift": 1})["variety"], 0)
        kodi.settings["radio_variety"] = "5"
        self.assertEqual(main.radio_mix_parameters(75, {"drift": 0})["variety"], 5)

    def test_a_station_that_stays_close_asks_musicip_with_variety(self):
        kodi.settings.update({"radio_variety": "0", "mix_assist_radio_drift": "0"})
        self.started_station()
        self.assertEqual({query["variety"] for query in self.source.mix_requests()}, {"2"})  # start and refill
        self.assertIn("variety 2", self.radio()["events"][0]["parameters"])

    def test_a_refill_may_look_further_from_earlier_checked_songs_and_the_picked_song(self):
        radio = self.started_station()
        kwargs = self.refill_check.call_args[1]
        files = [entry["file"] for entry in radio["queue"]]
        self.assertEqual(kwargs["more_seeds"], list(reversed(files[1:-1])) + [files[0]])  # after the refill's seed
        self.assertTrue(set(main.normalize_track_identity(path) for path in files) <= set(kwargs["seen"]))

    def test_the_real_start_check_takes_the_first_songs_then_musicips_mix(self):
        seed, first, mix = SONGS[0], SONGS[1:4], [SONGS[2], SONGS[0], SONGS[7], SONGS[8]]
        with mock.patch.object(main, "fetch_mix", return_value=mix) as fetch, \
                mock.patch.object(main, "check_radio_refill", return_value={"chosen": []}) as refill:
            CHECK_RADIO_START([seed] + first, 6, settings={"openness": 0})
        self.assertEqual(fetch.call_args[0][:2], (seed, main.mix_assist.MUSICIP_MAX_MIX))
        args, kwargs = refill.call_args
        self.assertEqual(args, (seed, first + [SONGS[7], SONGS[8]], 6, None, [seed]))  # each once, the seed not
        self.assertEqual((kwargs["name"], kwargs["settings"]), (True, {"openness": 0}))
        self.assertEqual(kwargs["seen"], [main.normalize_track_identity(track) for track in [seed] + first])

    def test_refills_are_checked_before_they_are_queued(self):
        self.start()
        before = self.files()
        self.tick()
        self.finish_check()
        self.tick()
        kodi.go_to(1)
        self.tick()
        self.assertEqual(len(self.source.mix_requests()), 1)  # 3 songs left: no refill yet
        kodi.go_to(2)
        self.tick()
        self.assertEqual(self.source.mix_requests()[-1]["size"], str(service.RADIO_CHECK_SIZE))
        self.assertEqual(self.files(), before)  # nothing queued while the check runs
        self.finish_check()
        radio = self.tick()
        reference_song, candidates, count, reference, neighbours = self.refill_check.call_args[0]
        self.assertEqual(reference_song, before[-1])  # "Drift slowly": judged against the refill's seed
        self.assertEqual((count, reference, neighbours), (main.RADIO_BATCH_SIZE_DEFAULT, REFERENCE, before))
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
        self.assertEqual(self.source.mix_requests()[-1]["song"], before[-2])

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
        self.assertEqual(fallback, self.refill_check.call_args[0][1][:main.RADIO_BATCH_SIZE_DEFAULT])
        release.set()
        self.finish_check()
        radio = self.tick()
        self.assertEqual(self.files(), before + fallback)  # the check's songs are not added on top
        self.assertEqual(radio["reference"], {"energy": 6, "sounding_year": 1984})

    def test_results_for_an_earlier_station_are_dropped(self):
        self.start()
        queue = self.files()
        self.start_result(queue[1:3] + queue[4:], not_fitting=[queue[3]])
        self.tick()
        self.finish_check()
        main.save_radio_state(dict(self.radio(), playing_started_ts=self.radio()["playing_started_ts"] + 1))
        self.tick()
        self.assertEqual(self.files(), queue)

    def test_station_strictness_and_drift_reach_the_check(self):
        kodi.settings.update({"mix_assist_station_strictness": "4", "mix_assist_radio_drift": "2",
                              "radio_intent_borderline": "true"})
        chosen = {"chosen": ["b"], "entries": {"b": {"energy": 9, "sounding_year": 1983}}, "seed_entry": None,
                  "not_fitting": []}
        with mock.patch.object(main.mix_assist, "choose_additions", return_value=chosen) as choose, \
                mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}):
            result = CHECK_RADIO_REFILL("a", ["b"], 8, REFERENCE, ["x", "y"])
        kwargs = choose.call_args[1]
        self.assertEqual((kwargs["strictness"], kwargs["accept_borderline"], kwargs["reference"]), (1.5, True, REFERENCE))
        step = 1 - 0.5 ** (1 / 20)  # "Wander freely": half the way after 20 songs
        self.assertAlmostEqual(result["reference"]["energy"], 5 + step * 4)

    def test_a_favourites_own_artist_rule_spaces_its_refills(self):
        kodi.settings["radio_reject_size"] = "2"
        chosen = {"chosen": [], "entries": {}, "seed_entry": None, "not_fitting": []}
        with mock.patch.object(main.mix_assist, "choose_additions", return_value=chosen) as choose, \
                mock.patch.object(main, "mix_assist_ask", return_value=lambda *args: {}):
            CHECK_RADIO_REFILL("a", ["b"], 8, REFERENCE, ["w", "x", "y", "z"], settings={"rejectsize": 3})
        self.assertEqual((choose.call_args[1]["artist_window"], choose.call_args[1]["before"]), (3, ["x", "y", "z"]))

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
        self.assertIn("Checks: on | Character: Balanced | Drift: Drift slowly", pages["Overview"])
        self.assertIn("Refills: 1 (1 checked, 0 unchecked)", pages["Overview"])
        self.assertIn("The picked song:\ndark metal", pages["What it is about"])
        self.assertIn("Energy: 5.0 steady » 6.0 steady (+1.0) | course: 5.0, 6.0", pages["Drift"])
        self.assertIn("Sounding year: 1983 » 1984 (+1.0 years)", pages["Drift"])
        self.assertIn("Moved most: Energy (+1.0)", pages["Drift"])
        history = pages[f"History ({len(kinds)})"]
        self.assertTrue(history.split("\n")[0].endswith("2 song(s), checked"))
        self.assertIn("The first songs were checked: all fit", history)

    def test_station_information_from_the_radio_screen(self):
        self.started_station()
        self.run_plugin(action="radio_info")
        window = kodi.windows[0]
        properties = window.properties
        self.assertEqual(properties["heading"], "Radio station")
        self.assertTrue(properties["facts"].startswith("Picked song: "))
        self.assertIn("| playing for 0 min", properties["facts"])
        self.assertEqual([properties.get(f"tab{number}") for number in range(1, 6)],
                         ["Overview", "What it is about", "Drift", "History (2)", None])
        self.assertIn("Checks: on", properties["text"])
        window.onFocus(203)
        self.assertTrue(os.path.isfile(properties["image"]))  # the start check measured the picked song
        self.assertIn("Measured 1 time(s)", properties["text"])

    def test_without_the_window_the_station_information_is_a_list_of_pages(self):
        self.started_station()
        kodi.window_error = "broken skin file"
        kodi.respond("select", 2, -1)  # Drift, then close
        self.run_plugin(action="radio_info")
        self.assertEqual(kodi.dialogs("select")[0][1], ("Radio station", ["Overview", "What it is about", "Drift",
                                                                          "History (2)"]))
        self.assertEqual(kodi.dialogs("textviewer")[0][1][0], "Radio station: Drift")

    def test_the_drift_chart(self):
        self.started_station()
        self.finish_check()
        radio = self.tick()
        texts = [text.text for text in main.drift_chart_texts(main.drift_chart_series(radio["events"]))]
        for text in ("Energy", "5.0 » 6.0 steady", "Sounding year (right scale)", "1983 » 1984", "0", "10"):
            self.assertIn(text, texts)
        self.assertTrue(any(text.endswith("| 2 measurements") for text in texts))
        self.run_plugin(action="radio_info")
        self.run_plugin(action="radio_info")  # a new image; the older one is gone
        kodi.windows[-1].onFocus(203)
        image = kodi.windows[-1].properties["image"]
        self.assertTrue(os.path.isfile(image))
        self.assertEqual(os.listdir(os.path.dirname(image)), [os.path.basename(image)])

    def test_the_drift_chart_needs_measurements(self):
        self.start()
        drift = main.radio_info_tabs(self.radio())[2]
        self.assertEqual((drift["title"], drift.get("image")), ("Drift", None))
        self.assertIn("Drift is measured when", drift["text"])

    def test_the_first_check_names_the_station(self):
        self.start()
        self.start_result(self.files()[1:], name="Bombastic Heroic Metal")
        radio = self.started_station(started=True)
        self.assertEqual(radio["name"], "Bombastic Heroic Metal")
        self.assertTrue(radio["ui_refresh_requested"])  # the visible Radio screen is redrawn with the name
        self.assertIn(("setPluginCategory", "Radio: Bombastic Heroic Metal"), self.menu_calls())
        self.assertTrue(dict(main.radio_info_pages(radio))["Overview"].startswith("Station: Bombastic Heroic Metal"))

    def test_a_favourite_keeps_its_name(self):
        self.start()
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": self.radio()["seed"]}])
        main.save_radio_state(dict(self.radio(), favourite_id="f1", name="Night Drive"))
        self.start_result(self.files()[1:], name="Other")
        self.tick()
        self.finish_check()
        self.assertEqual(self.tick()["name"], "Night Drive")

    def menu_calls(self):
        self.menu()
        return kodi.directory_calls

    def test_a_favourite_station_uses_its_own_settings(self):
        self.start()
        seed = self.radio()["seed"]
        main.save_radio_favourites([{"id": "f1", "name": "Night Drive", "seed": seed, "openness": 4, "drift": 0}])
        self.run_plugin(action="radio_stop")
        kodi.settings.update({"mix_assist_station_strictness": "0", "mix_assist_radio_drift": "2"})  # global: other values
        self.run_plugin(action="radio_play_favourite", id="f1")
        self.assertEqual(self.radio()["settings"], {"openness": 4, "drift": 0})
        self.assertEqual((self.radio()["events"][0]["openness"], self.radio()["events"][0]["drift"]),
                         ("Adventurous", "Stay close to the picked song"))
        self.tick()  # the start check gets the favourite's settings
        self.finish_check()
        self.assertEqual(self.start_check.call_args[1]["settings"], {"openness": 4, "drift": 0})
        self.tick()
        kodi.go_to(2)
        self.tick()  # a refill: judged against the picked song ("stay close"), with the favourite's settings
        self.finish_check()
        self.assertEqual(self.refill_check.call_args[0][0], seed)
        self.assertEqual(self.refill_check.call_args[1]["settings"], {"openness": 4, "drift": 0})

    def test_a_favourite_plays_with_the_description_it_was_saved_with(self):
        self.start()
        seed = self.radio()["seed"]
        main.save_radio_favourites([{"id": "f1", "number": 1, "name": "Night Drive", "seed": seed,
                                     "intent": "cold synths for a night drive"}])
        self.run_plugin(action="radio_stop")
        self.run_plugin(action="radio_play_favourite", id="f1")
        radio = self.radio()
        self.assertEqual((radio["intent"], radio["saved_intent"]), ("cold synths for a night drive",) * 2)
        about = main.radio_info_tabs(radio, charts=False)[1]["text"]  # before the start check
        self.assertEqual(about, "The picked song, as saved with the favourite:\ncold synths for a night drive")
        self.start_result([], intent="cold synths for a night drive")  # the check returns the intent it was given
        self.tick()  # the start check judges against it
        self.finish_check()
        self.assertEqual(self.start_check.call_args[1]["intent"], "cold synths for a night drive")
        radio = self.tick()
        self.assertEqual(radio["name"], "Night Drive")
        about = main.radio_info_tabs(radio, charts=False)[1]["text"]
        self.assertIn("  The picked song, as saved with the favourite:\ncold synths for a night drive", about)
        self.assertEqual(about.count("cold synths"), 1)

    def test_a_new_station_and_an_old_favourite_are_described_by_the_ai(self):
        self.start()
        self.tick()
        self.finish_check()
        self.assertEqual(self.start_check.call_args[1]["intent"], "")
        seed = self.radio()["seed"]
        main.save_radio_favourites([{"id": "f1", "number": 1, "name": "Night Drive", "seed": seed}])  # saved without
        self.run_plugin(action="radio_stop")
        self.run_plugin(action="radio_play_favourite", id="f1")
        self.assertEqual(self.radio()["saved_intent"], "")
        self.assertIn("Not worked out yet", main.radio_info_tabs(self.radio(), charts=False)[1]["text"])

    def test_a_new_perspective_drops_the_saved_description(self):
        main.save_radio_favourites([{"id": "f1", "number": 1, "name": "Night Drive", "seed": "D:\\x.mp3",
                                     "perspective": 0, "intent": "cold synths"}])
        with mock.patch.object(main, "select_perspective", return_value=2):
            self.run_plugin(action="radio_favourite_setting", id="f1", setting="perspective")
        self.assertEqual(main.load_radio_favourites()[0]["intent"], "")
        main.save_radio_favourites([dict(main.load_radio_favourites()[0], intent="cold synths")])
        with mock.patch.object(main, "dialog_slider_int", return_value=5):
            self.run_plugin(action="radio_favourite_setting", id="f1", setting="variety")
        self.assertEqual(main.load_radio_favourites()[0]["intent"], "cold synths")  # other settings keep it

    def test_the_settings_reach_the_checks(self):
        self.assertEqual(main.get_station_strictness({"openness": 4}), (1.5, False))
        self.assertEqual(main.get_station_strictness({"openness": 4, "borderline": True}), (1.5, True))
        self.assertEqual(main.get_station_strictness({"openness": main.CHECK_OFF}), (None, False))
        self.assertEqual(main.get_radio_drift_half_life({"drift": 0}), 0)
        self.assertEqual(main.get_station_strictness({}), main.get_station_strictness())  # none of its own: global

    def test_without_the_claude_cli_radio_works_as_before(self):
        with mock.patch.object(main, "mix_assist_available", return_value=False):
            self.start()
            self.assertEqual(self.source.mix_requests()[0]["size"], str(main.get_playlist_size()))
            kodi.go_to(3)
            self.tick()
        self.start_check.assert_not_called()
        self.refill_check.assert_not_called()
        self.assertEqual(len(self.files()), 9)


if __name__ == "__main__":
    unittest.main()
