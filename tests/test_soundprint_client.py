"""The sound engine from Kodi's side: running the tool in its own Python (soundprint/client.py), mixes from it
instead of MusicIP, the settings' buttons, and the service's analysis of new songs."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from fake_kodi import kodi
from support import KodiTestCase, SourceTestCase, main, service

from soundprint import client, state

SEED = "D:\\music\\Kraftwerk\\Radio-Aktivitat (1975)\\04 Radioaktivitat.mp3"
NEAR = ["D:\\music\\Cluster\\Zuckerzeit (1974)\\01 Hollywood.mp3", "D:\\music\\Neu!\\Neu! (1972)\\01 Hallogallo.mp3"]


def ready_data_folder():
    """A data folder with the tool's Python and the model in place (empty files: nothing is run)."""
    data = tempfile.mkdtemp()
    os.makedirs(os.path.dirname(state.environment_python(data)))
    open(state.environment_python(data), "w").close()
    os.makedirs(state.model_folder(data))
    for name in state.MODEL_FILES:
        open(os.path.join(state.model_folder(data), name), "w").close()
    return data


def answer(songs, **fields):
    return dict({"seed": SEED, "seed_vector": "stored", "seed_details": ["Kraftwerk", "Radioaktivitat"],
                 "analysed": 1000, "left_out": {"artist": 3, "same_song": 1}, "seconds": 0.3,
                 "reach": 25, "songs": [{"path": path, "similarity": 0.9 - 0.01 * number, "rank": 1 + 2 * number,
                                    "artist": "A", "title": f"T{number}"}
                           for number, path in enumerate(songs)]}, **fields)


class FakeRun:
    def __init__(self, stdout="", stderr="", returncode=0, error=None):
        self.result = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
        self.error, self.calls = error, []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.error:
            raise self.error
        return self.result


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.data = ready_data_folder()

    def test_the_tool_runs_without_kodis_python_settings(self):
        variables = client.environment({"PYTHONHOME": "kodi", "PYTHONPATH": "kodi", "PATH": "p"})
        self.assertEqual(variables, {"PATH": "p", "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(client.command("py", "D", "U", "status"),
                         ["py", "-X", "utf8", "-m", "soundprint", "--userdata", "U", "--data", "D", "status"])

    def test_not_ready_says_what_is_missing(self):
        empty = tempfile.mkdtemp()
        self.assertIn("isn't set up", client.not_ready(empty))
        os.remove(os.path.join(state.model_folder(self.data), "model_epoch_36.onnx.data"))
        self.assertIn("model is missing", client.not_ready(self.data))
        self.assertEqual(client.not_ready(ready_data_folder()), "")

    def test_neighbours_ask_the_tool_quietly_from_the_addon_folder(self):
        run = FakeRun(json.dumps(answer(NEAR)))
        found = client.neighbours(self.data, "U", SEED, 25, window=6, variety=3, runner=run)
        self.assertEqual([song["path"] for song in found["songs"]], NEAR)
        cmd, kwargs = run.calls[0]
        self.assertEqual(cmd[0], state.environment_python(self.data))
        self.assertEqual(cmd[-8:], ["neighbours", SEED, "--count", "25", "--artist-window", "6", "--variety", "3"])
        self.assertEqual(kwargs["cwd"], client.ADDON_FOLDER)
        self.assertEqual(kwargs["timeout"], client.NEIGHBOURS_TIMEOUT)
        self.assertEqual(kwargs["creationflags"], client.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

    def test_a_seed_without_sound_print_is_an_empty_answer(self):
        run = FakeRun(json.dumps(answer([], seed_vector="not a local file")))
        with self.assertRaises(client.SoundprintError) as caught:
            client.neighbours(self.data, "U", "smb://box/a.mp3", 25, runner=run)
        self.assertEqual(caught.exception.kind, client.NOT_ANALYSED)
        self.assertIn("not a local file", str(caught.exception))

    def test_failures_say_why(self):
        cases = [(FakeRun("Traceback", "ImportError: numpy"), client.FAILED, "ImportError: numpy"),
                 (FakeRun(error=subprocess.TimeoutExpired("x", 1)), client.TIMEOUT, "did not answer"),
                 (FakeRun(error=FileNotFoundError("gone")), client.NOT_SET_UP, "could not be started")]
        for run, kind, text in cases:
            with self.subTest(kind=kind), self.assertRaises(client.SoundprintError) as caught:
                client.neighbours(self.data, "U", SEED, 25, runner=run)
            self.assertEqual(caught.exception.kind, kind)
            self.assertIn(text, str(caught.exception))

    def test_nothing_is_run_before_the_set_up(self):
        run = FakeRun(json.dumps(answer(NEAR)))
        with self.assertRaises(client.SoundprintError) as caught:
            client.neighbours(tempfile.mkdtemp(), "U", SEED, 25, runner=run)
        self.assertEqual((caught.exception.kind, run.calls), (client.NOT_SET_UP, []))

    def test_an_analysis_starts_detached_with_its_output_in_the_data_folder(self):
        started = []

        def popen(cmd, **kwargs):
            started.append((cmd, kwargs))
            return SimpleNamespace(pid=4321)

        result = client.start_analysis(self.data, "U", popen=popen)
        self.assertEqual((result["started"], result["pid"]), (True, 4321))
        cmd, kwargs = started[0]
        self.assertEqual(cmd[-1], "analyse")
        self.assertEqual(kwargs["stdout"].name, os.path.join(self.data, "run.out"))
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        if sys.platform == "win32":
            self.assertEqual(kwargs["creationflags"], client.CREATE_NO_WINDOW | client.CREATE_NEW_PROCESS_GROUP
                             | client.CREATE_BREAKAWAY_FROM_JOB)

    def test_without_leave_to_break_away_from_kodis_job_it_starts_inside_it(self):
        flags = []

        def popen(cmd, **kwargs):
            flags.append(kwargs["creationflags"])
            if kwargs["creationflags"] & client.CREATE_BREAKAWAY_FROM_JOB:
                raise PermissionError("access denied")
            return SimpleNamespace(pid=1)

        if sys.platform != "win32":
            self.skipTest("Windows job objects")
        self.assertTrue(client.start_analysis(self.data, "U", popen=popen)["started"])
        self.assertEqual(len(flags), 2)
        self.assertFalse(flags[1] & client.CREATE_BREAKAWAY_FROM_JOB)

    def test_no_second_analysis_while_one_runs(self):
        state.write_status(self.data, {"state": "running", "pid": os.getpid()})
        popen = mock.Mock()
        self.assertEqual(client.start_analysis(self.data, "U", popen=popen), {"started": False, "pid": os.getpid()})
        popen.assert_not_called()

    def test_stop_asks_only_a_running_analysis(self):
        self.assertFalse(client.stop_analysis(self.data))
        self.assertFalse(os.path.exists(os.path.join(self.data, state.STOP_FILE)))
        state.write_status(self.data, {"state": "running", "pid": os.getpid()})
        self.assertTrue(client.stop_analysis(self.data))
        self.assertTrue(os.path.exists(os.path.join(self.data, state.STOP_FILE)))

    def test_the_set_up_python_is_the_configured_one_then_the_path(self):
        configured = state.environment_python(self.data)
        found = {"python3": None, "python": "C:\\Python\\python.exe", "py": "C:\\Windows\\py.exe"}
        self.assertEqual(client.base_pythons(configured, which=found.get),
                         [configured, "C:\\Python\\python.exe", "C:\\Windows\\py.exe"])
        self.assertEqual(client.base_pythons("C:\\missing.exe", which=lambda name: None), [])

    def test_set_up_keeps_its_output_and_says_why_it_failed(self):
        data = tempfile.mkdtemp()
        self.assertEqual(client.setup(data, "U", "py", runner=FakeRun("installing\nready: x")), "ready: x")
        with open(os.path.join(data, "setup.log"), encoding="utf-8") as handle:
            self.assertIn("installing", handle.read())
        with self.assertRaises(client.SoundprintError) as caught:
            client.setup(data, "U", "py", runner=FakeRun("", "ERROR: no matching distribution", 1))
        self.assertIn("no matching distribution", str(caught.exception))

    def test_counts_come_from_the_store(self):
        self.assertEqual(client.counts(self.data), {"analysed": 0, "failed": 0})
        connection = sqlite3.connect(os.path.join(self.data, "sound.db"))
        connection.executescript("CREATE TABLE songs (path TEXT, vector BLOB);"
                                 "INSERT INTO songs VALUES ('a', x'00'), ('b', x'00'), ('c', NULL);")
        connection.commit()
        connection.close()
        self.assertEqual(client.counts(self.data), {"analysed": 2, "failed": 1})


class StatusTextTest(unittest.TestCase):
    def setUp(self):
        self.data = ready_data_folder()
        self.now = time.mktime((2026, 10, 28, 12, 0, 0, 0, 0, -1))

    def lines(self, status, alive=True):
        with mock.patch.object(state.time, "time", return_value=self.now):
            state.write_status(self.data, status)
        return client.status_lines(self.data, self.now, alive=lambda data: state.read_status(data) if alive else {})

    def test_a_running_analysis_says_how_far_it_is_and_when_it_ends(self):
        lines = self.lines({"state": "running", "pid": 1, "started": self.now - 3600, "todo": 1000, "done": 250,
                            "failed": 2, "seconds_per_song": 0.42, "eta": self.now + 5 * 3600 + 15 * 60,
                            "workers": 4, "threads": 2})
        self.assertIn("Analysing now: 250 of 1,000 song(s) (25 %), 2 could not be read.", lines)
        self.assertIn("About 0.42 s per song: done in about 5 h 15 min (today at 17:15).", lines)
        self.assertIn("Started today at 11:00; 4 process(es) with 2 thread(s) each, at low priority.", lines)

    def test_while_it_looks_for_new_songs(self):
        lines = self.lines({"state": "running", "phase": "planning", "pid": 1, "started": self.now, "songs": 153608})
        self.assertIn("looking for new and changed songs among 153,608", lines[1])

    def test_an_analysis_that_ended_without_saying_so(self):
        lines = self.lines({"state": "running", "pid": 1, "todo": 10, "done": 4}, alive=False)
        self.assertIn("ended without finishing", lines[1])

    def test_finished_stopped_and_failed(self):
        self.assertIn("finished today at 12:00", self.lines({"state": "finished", "done": 5, "missing": 630})[1])
        self.assertIn("630 song(s) of Kodi's library are not on disk",
                      self.lines({"state": "finished", "done": 5, "missing": 630})[1])
        self.assertIn("stopped today at 12:00 after 3 of 9", self.lines({"state": "stopped", "done": 3, "todo": 9})[1])
        self.assertIn("failed today at 12:00: OSError: disk", self.lines({"state": "failed", "error": "OSError: disk"})[1])

    def test_before_the_set_up(self):
        self.assertIn("isn't set up", client.status_lines(tempfile.mkdtemp())[0])

    def test_when_names_the_day(self):
        self.assertEqual(client.when(self.now + 86400, self.now), "tomorrow at 12:00")
        self.assertEqual(client.when(self.now - 86400, self.now), "yesterday at 12:00")
        self.assertEqual(client.when(self.now + 3 * 86400, self.now), "2026-10-31 12:00")
        self.assertEqual(client.duration(59), "1 min")
        self.assertEqual(client.duration(3 * 3600 + 5 * 60), "3 h 05 min")


class SoundEngineMixTest(KodiTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(main.soundprint, "neighbours", return_value=answer(NEAR))
        self.neighbours = patcher.start()
        self.addCleanup(patcher.stop)

    def test_mixes_come_from_the_sound_engine_with_the_seed_first(self):
        kodi.settings.update(mix_variety="4", mix_reject_size="6")
        self.assertEqual(main.fetch_mix(SEED, 20), [SEED] + NEAR)
        data, userdata, seed, size, window, variety = self.neighbours.call_args[0]
        self.assertEqual(data, os.path.join(main.get_profile_dir(), "soundprint"))
        self.assertEqual((seed, size, window, variety), (SEED, 20, 6, 4))

    def test_the_artist_rule_is_musicips_reject_size_also_a_stations_own(self):
        kodi.settings["mix_reject_size"] = "0"
        main.fetch_mix(SEED, 20)
        self.assertEqual(self.neighbours.call_args[0][4], 0)  # artists may repeat
        main.fetch_mix(SEED, 20, {"variety": 3, "rejectsize": 6})  # a Radio station's parameters
        self.assertEqual(self.neighbours.call_args[0][4:], (6, 3))

    def test_every_song_is_logged_with_its_similarity_artist_and_title(self):
        self.log_everything()
        main.fetch_mix(SEED, 20)
        log = kodi.log_text()
        self.assertIn("Sound engine mix request: seed", log)
        self.assertIn("3 for an artist played too recently, 1 the same song again", log)
        self.assertIn(f"1. {NEAR[0]} (similarity 0.900, rank 1, A - T0)", log)
        self.assertIn("variety 0: the nearest songs", log)
        kodi.settings["mix_variety"] = "9"
        main.fetch_mix(SEED, 20)
        self.assertIn("variety 9: drawn from the nearest 25, the nearer the likelier", kodi.log_text())

    def test_a_song_without_sound_print_is_an_empty_mix(self):
        self.neighbours.side_effect = client.SoundprintError(client.NOT_ANALYSED, "no sound print (not analysed)")
        with self.assertRaises(main.MusicIPError) as caught:
            main.fetch_mix(SEED, 20)
        self.assertIn("empty mix", str(caught.exception))  # Radio then tries the song before

    def test_an_engine_that_is_not_set_up_is_an_error(self):
        self.neighbours.side_effect = client.SoundprintError(client.NOT_SET_UP, "The sound engine isn't set up yet.")
        with self.assertRaises(main.MusicIPError) as caught:
            main.fetch_mix(SEED, 20)
        self.assertEqual(str(caught.exception), f"The sound engine isn't set up yet. {main.SOUND_ENGINE_SETUP_HINT}")
        self.assertIn("failed (not_set_up)", kodi.log_text())  # an error is always logged


class SoundEngineSettingsTest(KodiTestCase):
    def test_status_shows_the_status_lines(self):
        with mock.patch.object(main.soundprint, "status_lines", return_value=["one", "two"]):
            self.run_plugin(action="soundprint_status")
        self.assertEqual(kodi.dialogs("textviewer")[0][1], ("Sound engine", "one\n\ntwo"))

    def test_analyse_now_starts_one_in_the_background(self):
        with mock.patch.object(main.soundprint, "start_analysis",
                               return_value={"started": True, "pid": 7, "command": ["py"]}) as start:
            self.run_plugin(action="soundprint_analyse")
        self.assertEqual(start.call_args[0][0], main.soundprint_data())
        self.assertNotified("analyses new songs in the background")
        self.assertIn("Sound engine analysis started (asked for in the settings): process 7", kodi.log_text())

    def test_analyse_now_while_one_runs_or_before_the_set_up(self):
        with mock.patch.object(main.soundprint, "start_analysis", return_value={"started": False, "pid": 7}):
            self.run_plugin(action="soundprint_analyse")
        self.assertNotified("analysing already")
        with mock.patch.object(main.soundprint, "start_analysis",
                               side_effect=client.SoundprintError(client.NOT_SET_UP, "Not set up.")):
            self.run_plugin(action="soundprint_analyse")
        self.assertIn("Not set up.", kodi.dialogs("ok")[0][1][1])

    def test_stop(self):
        with mock.patch.object(main.soundprint, "stop_analysis", return_value=True):
            self.run_plugin(action="soundprint_stop")
        self.assertNotified("stops after the songs in hand")
        self.run_plugin(action="soundprint_stop")
        self.assertNotified("No analysis is running")

    def test_set_up_needs_a_python(self):
        with mock.patch.object(main.soundprint, "base_pythons", return_value=[]):
            self.run_plugin(action="soundprint_setup")
        self.assertIn("No Python was found", kodi.dialogs("ok")[0][1][1])

    def test_set_up_then_analyse(self):
        kodi.respond("yesno", True, True)
        with mock.patch.object(main.soundprint, "base_pythons", return_value=["C:\\Python\\python.exe"]), \
                mock.patch.object(main.soundprint, "setup", return_value="ready") as setup, \
                mock.patch.object(main.soundprint, "start_analysis",
                                  return_value={"started": True, "pid": 7, "command": ["py"]}) as start:
            self.run_plugin(action="soundprint_setup")
        self.assertEqual(setup.call_args[0][2], "C:\\Python\\python.exe")
        self.assertIn("AGPL-3.0", kodi.dialogs("yesno")[0][1][1])
        start.assert_called_once()

    def test_a_failed_set_up_points_to_its_log(self):
        kodi.respond("yesno", True)
        with mock.patch.object(main.soundprint, "base_pythons", return_value=["py"]), \
                mock.patch.object(main.soundprint, "setup",
                                  side_effect=client.SoundprintError(client.FAILED, "The set-up failed: pip")):
            self.run_plugin(action="soundprint_setup")
        self.assertIn("setup.log", kodi.dialogs("ok")[0][1][1])


class SoundEngineAnalysisTickTest(SourceTestCase):
    def setUp(self):
        super().setUp()
        self.clock = self.use_clock()
        patcher = mock.patch.object(main.soundprint, "start_analysis",
                                    return_value={"started": True, "pid": 7, "command": ["py"]})
        self.start = patcher.start()
        self.addCleanup(patcher.stop)

    def tick(self, seconds=0):
        self.clock.advance(seconds)
        return service.run_library_update_tick()

    def test_not_while_kodi_starts_then_every_8_hours(self):
        self.assertFalse(self.tick())
        self.assertTrue(self.tick(service.LIBRARY_UPDATE_STARTUP_DELAY_SECONDS))
        self.assertFalse(self.tick(service.SOUNDPRINT_ANALYSIS_INTERVAL_SECONDS - 1))
        self.assertTrue(self.tick(1))
        self.assertEqual(self.start.call_count, 2)
        self.assertIn("Sound engine analysis started (scheduled)", kodi.log_text())

    def test_after_kodis_music_library_scan_at_once(self):
        service.save_json_file(service.soundprint_analysis_state_path(), {"last_ts": int(self.clock.now)})
        self.tick()
        service.ServiceMonitor().onScanFinished("music")
        self.assertTrue(self.tick())
        self.assertIn("(after Kodi's library scan)", kodi.log_text())
        self.assertFalse(self.tick(1))

    def test_not_when_switched_off(self):
        kodi.settings["soundprint_auto_analyse"] = "false"
        self.tick()
        self.assertFalse(self.tick(service.LIBRARY_UPDATE_STARTUP_DELAY_SECONDS))
        self.assertFalse(self.tick(service.SOUNDPRINT_ANALYSIS_INTERVAL_SECONDS))
        self.start.assert_not_called()

    def test_a_tool_that_is_not_set_up_is_tried_again_only_at_the_next_time(self):
        self.start.side_effect = client.SoundprintError(client.NOT_SET_UP, "not set up")
        self.tick()
        self.assertFalse(self.tick(service.LIBRARY_UPDATE_STARTUP_DELAY_SECONDS))
        self.assertFalse(self.tick(60))
        self.assertEqual(self.start.call_count, 1)
        self.assertEqual(kodi.dialogs("ok"), [])  # quiet in the background

    def test_the_station_warning_names_the_sound_engine(self):
        service.source_outage({}, main, RuntimeError("x"))
        self.assertNotified("The sound engine can't make mixes right now")


class ReadinessTest(KodiTestCase):
    def test_at_the_start_a_sound_engine_that_is_not_set_up_says_where_to_set_it_up(self):
        with mock.patch.object(main.soundprint, "not_ready", return_value="The sound engine isn't set up yet."):
            self.assertEqual(service.announce_sound_engine_readiness(), "The sound engine isn't set up yet.")
        self.assertNotified(f"The sound engine isn't set up yet. {main.SOUND_ENGINE_SETUP_HINT}")
        self.assertIn("The sound engine can't make mixes yet", kodi.log_text())

    def test_a_ready_sound_engine_is_not_announced(self):
        with mock.patch.object(main.soundprint, "not_ready", return_value=""):
            self.assertEqual(service.announce_sound_engine_readiness(), "")
        self.assertEqual(kodi.notification_messages(), [])


class StaleSettings:
    """An xbmcaddon.Addon as Kodi gives it: with the settings as they were when it was made (F39)."""

    def __init__(self, values):
        self.values = dict(values)

    def getSetting(self, key):
        return self.values.get(key, "")

    def getAddonInfo(self, key):
        return kodi.addon_info.get(key, "")


class SettingsChangeTest(KodiTestCase):
    def test_the_service_reads_changed_settings_again(self):
        kodi.settings["mix_variety"] = "0"
        started_with = dict(kodi.settings)
        logging = service.logs
        for module in (service, main, logging):
            patcher = mock.patch.object(module, "ADDON", StaleSettings(started_with))
            patcher.start()
            self.addCleanup(patcher.stop)
        kodi.settings["mix_variety"] = "7"  # chosen in the settings while Kodi runs
        self.assertEqual(main.get_mix_variety(), 0)  # the service's copy still has the old value
        service.ServiceMonitor().onSettingsChanged()
        self.assertEqual(main.get_mix_variety(), 7)
        for module in (service, main, logging):
            self.assertNotIsInstance(module.ADDON, StaleSettings)
        self.assertIn("Settings changed: the service reads them again. Mixing: size 20, variety 7, no artist "
                      "repeat within 0; Radio: variety 0, no artist repeat within 0, 6 songs per refill (from the next station on).",
                      kodi.log_text())


if __name__ == "__main__":
    unittest.main()
