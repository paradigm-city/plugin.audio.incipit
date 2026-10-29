"""Logging by area (Settings > Logging): what each switch lets through, the area tag, the old switches' migration,
and what the areas write when they are on."""

import json
import os
import unittest
from unittest import mock

import fake_kodi
from fake_kodi import kodi
from support import KodiTestCase, SourceTestCase, logs, main, service

from mixassist import claude, trace

SONGS = [f"D:\\music\\Artist {n}\\Album\\{n:02d} Song {n}.mp3" for n in range(1, 21)]


class AreaSwitchTest(KodiTestCase):
    LEVELS = {"debug": 0, "info": 1, "warning": 2, "error": 3, "fatal": 4}

    def log_every_level(self, area="radio"):
        for name, level in self.LEVELS.items():
            logs.write(area, f"{name} message", level)

    def test_every_area_has_a_switch_and_a_logger(self):
        self.assertEqual(list(logs.AREAS), ["general", "mixing", "ai", "radio", "discovery", "checks"])
        for area in logs.AREAS:
            with self.subTest(area=area):
                getattr(logs, f"log_{area}")("hello")
                self.assertEqual(kodi.logs, [])
                kodi.settings[logs.AREAS[area]] = "true"
                getattr(logs, f"log_{area}")("hello")
                self.assertEqual(kodi.logs, [(f"[plugin.audio.musicip] [{area}] hello", 1)])
                kodi.logs.clear()

    def test_warnings_and_errors_without_the_switch(self):
        self.log_every_level()
        self.assertEqual(kodi.logs, [("[plugin.audio.musicip] [radio] warning message", 2),
                                     ("[plugin.audio.musicip] [radio] error message", 3),
                                     ("[plugin.audio.musicip] [radio] fatal message", 4)])

    def test_everything_with_the_switch_and_debug_as_info(self):
        kodi.settings["log_radio"] = "true"
        self.log_every_level()
        self.assertEqual([level for _message, level in kodi.logs], [1, 1, 2, 3, 4])  # Kodi drops LOGDEBUG

    def test_one_switch_lets_only_its_area_through(self):
        kodi.settings["log_ai"] = "true"
        for area in logs.AREAS:
            logs.write(area, "info")
        self.assertEqual(kodi.log_text(), "[plugin.audio.musicip] [ai] info")

    def test_always(self):
        logs.log_general("started", always=True)
        self.assertEqual(kodi.log_text(), "[plugin.audio.musicip] [general] started")

    def test_switches_described(self):
        kodi.settings.update({"log_mixing": "true", "log_checks": "true"})
        self.assertEqual(logs.describe_switches(),
                         "general off, mixing on, ai off, radio off, discovery off, checks on")

    def test_switches_are_off_by_default(self):
        for switch in logs.AREAS.values():
            self.assertEqual(kodi.setting_defaults[switch], "false")


class MigrationTest(KodiTestCase):
    def write_stored_settings(self, **values):
        os.makedirs(kodi.profile_dir(), exist_ok=True)
        lines = "".join(f'    <setting id="{key}">{value}</setting>\n' for key, value in values.items())
        with open(self.profile_path("settings.xml"), "w", encoding="utf-8") as handle:
            handle.write(f'<settings version="2">\n{lines}</settings>\n')

    def switches(self):
        return {kodi.settings[switch] for switch in logs.AREAS.values()}

    def test_an_old_switch_that_was_on_turns_every_area_on_once(self):
        for old in logs.OLD_SWITCHES:
            with self.subTest(old=old):
                kodi.reset()
                self.write_stored_settings(**{old: "true", "playlist_size": "40"})
                self.assertTrue(logs.migrate_old_switches())
                self.assertEqual(self.switches(), {"true"})
                kodi.settings["log_ai"] = "false"  # the listener's choice afterwards stays
                self.assertFalse(logs.migrate_old_switches())
                self.assertEqual(kodi.settings["log_ai"], "false")

    def test_old_switches_off(self):
        self.write_stored_settings(plugin_extended_logging="false", service_extended_logging="false")
        self.assertFalse(logs.migrate_old_switches())
        self.assertEqual(self.switches(), {"false"})
        self.assertTrue(os.path.exists(self.profile_path(logs.MIGRATED_MARKER)))

    def test_new_installation(self):
        self.assertFalse(logs.migrate_old_switches())
        self.assertTrue(os.path.exists(self.profile_path(logs.MIGRATED_MARKER)))

    def test_unreadable_settings_file(self):
        os.makedirs(kodi.profile_dir(), exist_ok=True)
        with open(self.profile_path("settings.xml"), "w", encoding="utf-8") as handle:
            handle.write("<settings")
        self.assertFalse(logs.migrate_old_switches())

    def test_the_service_migrates_at_its_start(self):
        self.write_stored_settings(service_extended_logging="true")
        service.main()
        (line,) = [message for message, _level in kodi.logs if "MusicIP service started." in message]
        self.assertIn("checks on (turned on from the old extended logging switches).", line)


class MixingLogTest(SourceTestCase):
    def test_a_mix_request_and_its_songs(self):
        self.source.set_mix(SONGS[0], SONGS[1:4])
        main.fetch_mix(SONGS[0], 3)
        self.assertNotIn("Sound engine mix request", kodi.log_text())
        kodi.settings["log_mixing"] = "true"
        main.fetch_mix(SONGS[0], 3)
        text = kodi.log_text()
        self.assertIn(f"[mixing] Sound engine mix request: seed {SONGS[0]!r}", text)
        self.assertIn("size 3, artists may repeat, variety 0.", text)
        self.assertIn(f"with 3 song(s) for {SONGS[0]!r} ( - ):\n  1. {SONGS[1]} (similarity 0.900, rank 1,  - )", text)

    def test_mix_history_events(self):
        kodi.settings["log_mixing"] = "true"
        cache_path = self.save_mix(SONGS[:3])
        main.record_mix_history(cache_path, "renamed", name="Night Drive")
        self.assertIn(f"Mix history of {os.path.basename(cache_path)!r}: renamed {{\"name\": \"Night Drive\"}}",
                      kodi.log_text())


class RadioLogTest(SourceTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        for n, file in enumerate(SONGS, start=1):
            kodi.library.add_song(file, title=f"Song {n}", artist=f"Artist {n}", duration=240)
        for index, seed in enumerate(SONGS):
            self.source.set_mix(seed, [SONGS[(index + k) % len(SONGS)] for k in range(1, 5)])
        kodi.settings["log_radio"] = "true"
        self.run_plugin(action="radio_on")
        self.run_plugin(action="radio_play")

    def tick(self, seconds=1):
        self.clock.advance(seconds)
        service.run_radio_tick()

    def radio_lines(self, text):
        return [message for message, _level in kodi.logs if text in message]

    def test_a_tick_is_logged_when_something_changed(self):
        self.tick(5)
        self.tick()
        self.tick()
        (summary,) = self.radio_lines("queued, ")
        self.assertIn("[radio] Radio mode: position 0 of ", summary)
        self.assertIn("AI Mix Assist off; no check running; refill allowed now.", summary)

    def test_refill_seeds_and_songs(self):
        state = main.get_radio_state()
        state["queue"] = state["queue"][:2]
        service.save_radio_state(state)
        self.tick(5)
        self.assertTrue(self.radio_lines("refilling."))
        self.assertTrue(self.radio_lines("Radio mode: refill seeds to try"))
        self.assertTrue(self.radio_lines("of them new to the station."))
        self.assertTrue(self.radio_lines("Radio mode:   2: "))  # each added song with its position

    def test_a_stop_says_where_the_station_was(self):
        self.tick(5)
        fake_kodi.Player().stop()
        self.tick()
        self.tick(3)
        self.assertTrue(self.radio_lines("the player stopped playing audio; the station ends if it doesn't play "
                                         "again within 3 s."))
        (stop,) = self.radio_lines("Radio mode stopped: player_stop.")
        self.assertRegex(stop, r"; last song 'Artist \d+ - Song \d+' at position 0 of \d+ queued\.$")


class AiLogTest(KodiTestCase):
    def answer(self, structured):
        return fake_kodi_completed(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                                               "structured_output": structured, "total_cost_usd": 0.01,
                                               "usage": {"input_tokens": 10, "output_tokens": 5}}))

    def ask(self, prompt="You judge tracks.", message="1. A - B"):
        return claude.ask("claude.exe", prompt, {}, message, runner=lambda *args, **kwargs: self.answer({"tracks": []}))

    def test_requests_and_answers_go_to_the_log_under_ai(self):
        trace._PROMPTS_SHOWN.clear()
        self.ask()
        self.assertEqual(kodi.logs, [])
        kodi.settings["log_ai"] = "true"
        self.ask()
        self.ask()
        text = kodi.log_text()
        self.assertIn("[ai] AI request ", text)
        self.assertEqual(text.count("You judge tracks."), 1)  # the prompt in full once, then by its hash
        self.assertIn("(in full earlier in the log)", text)
        self.assertEqual(text.count("Message:\n1. A - B"), 2)
        self.assertIn('[ai] AI answer ', text)
        self.assertIn('"tracks": []', text)
        self.assertIn("tokens in 10 (cache read 0, written 0), out 5, API-equivalent cost $0.0100.", text)

    def test_a_failure_is_logged_with_its_kind(self):
        kodi.settings["log_ai"] = "true"
        with self.assertRaises(claude.ClaudeError):
            claude.ask("claude.exe", "p", {}, "m", runner=lambda *args, **kwargs: fake_kodi_completed("", "Not logged in"))
        self.assertIn("failed (not_logged_in)", kodi.log_text())
        self.assertIn("stderr: Not logged in", kodi.log_text())


class TraceTest(unittest.TestCase):
    def test_without_a_sink_or_while_off_nothing_happens(self):
        said = []
        saved = (trace._SINK, trace._ACTIVE)
        try:
            trace.set_sink(None)
            trace.say("x")
            self.assertFalse(trace.active())
            trace.set_sink(said.append, lambda: False)
            trace.say("x")
            trace.set_sink(lambda message: 1 / 0)
            trace.say("x")  # a failing sink never fails the work
            trace.set_sink(said.append, lambda: 1 / 0)
            self.assertFalse(trace.active())
            trace.set_sink(said.append)
            trace.say("y")
        finally:
            trace.set_sink(*saved)
        self.assertEqual(said, ["y"])


def fake_kodi_completed(stdout, stderr=""):
    return mock.Mock(stdout=stdout, stderr=stderr, returncode=0)


if __name__ == "__main__":
    unittest.main()
