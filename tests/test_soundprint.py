"""Sound prints: snippet positions and reading, the spectrogram, the store, the analysis plan, the search, the
song list and the model download. Decoding and the model itself are tested where av and onnxruntime are installed
(the tool's own environment); elsewhere those tests are skipped."""

import hashlib
import io
import itertools
import json
import random
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import wave

from fake_kodi import ADDON_DIR

if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

import numpy as np  # noqa: E402

from soundprint import __main__ as cli  # noqa: E402
from soundprint import analyse, analysis_version, audio, model, neighbours, songs, state, store  # noqa: E402

try:
    import av  # noqa: F401

    HAVE_AV = True
except ImportError:
    HAVE_AV = False
MODEL_FOLDER = os.path.join(cli.kodi_userdata(), "addon_data", "plugin.audio.incipit", "soundprint", "model")


def unit(*values):
    vector = np.zeros(store.DIMENSIONS, np.float32)
    vector[:len(values)] = values
    return vector / np.linalg.norm(vector)


class SnippetPositionTest(unittest.TestCase):
    def test_six_snippets_are_centred_on_sixths_of_the_song(self):
        starts = audio.snippet_starts(300.0, 6)
        self.assertEqual([round(start + 5, 1) for start in starts], [25.0, 75.0, 125.0, 175.0, 225.0, 275.0])

    def test_snippets_stay_inside_the_song(self):
        for start in audio.snippet_starts(12.0, 6):
            self.assertGreaterEqual(start, 0.0)
            self.assertLessEqual(start + 10.0, 12.0)

    def test_prepare_clips_and_cuts_to_16_bits_as_the_training_data(self):
        out = audio.prepare(np.array([2.0, -2.0, 0.5], np.float32))
        self.assertEqual(out[0], 1.0)
        self.assertEqual(out[1], -1.0)
        self.assertAlmostEqual(float(out[2]), 16383 / 32767, places=6)  # 16383.5 cut towards zero

    def test_pad_gives_exactly_one_window(self):
        self.assertEqual(audio.pad(np.ones(100, np.float32)).size, audio.WINDOW)
        self.assertEqual(audio.pad(np.ones(audio.WINDOW + 5, np.float32)).size, audio.WINDOW)


class SnippetReadingTest(unittest.TestCase):
    """audio.snippets with the file reading replaced: which way it reads, and what it gives the model."""

    def read(self, length, decode):
        with unittest.mock.patch.object(audio, "length_of", return_value=length), \
                unittest.mock.patch.object(audio, "decode", side_effect=decode):
            return audio.snippets("song.mp3", 6)

    def test_a_normal_song_is_read_by_seeking_to_each_snippet(self):
        calls = []

        def decode(path, start=0.0, seconds=0.0):
            calls.append((start, seconds))
            return np.full(int(seconds * audio.RATE), 0.1, np.float32)

        windows, length, how = self.read(300.0, decode)
        self.assertEqual((len(windows), length, how), (6, 300.0, "seek"))
        self.assertEqual([seconds for _, seconds in calls], [10.0] * 6)

    def test_a_file_that_claims_more_than_it_has_is_decoded_whole(self):
        whole = np.full(120 * audio.RATE, 0.1, np.float32)

        def decode(path, start=0.0, seconds=0.0):
            if seconds and start > 100:
                return np.zeros(0, np.float32)  # past the real end
            return whole[:int(seconds * audio.RATE)] if seconds else whole

        windows, length, how = self.read(1157.0, decode)
        self.assertEqual((len(windows), length, how), (6, 120.0, "whole"))

    def test_a_short_song_is_one_padded_window(self):
        windows, length, how = self.read(4.0, lambda path, start=0.0, seconds=0.0: np.full(4 * audio.RATE, 0.1,
                                                                                               np.float32))
        self.assertEqual((len(windows), how), (1, "short"))
        self.assertEqual(windows[0].size, audio.WINDOW)

    def test_silent_windows_are_left_out_unless_all_are(self):
        def decode(path, start=0.0, seconds=0.0):
            level = 0.0 if start < 100 else 0.1
            return np.full(int(seconds * audio.RATE), level, np.float32)

        windows, _, _ = self.read(300.0, decode)
        self.assertEqual(len(windows), 4)
        windows, _, _ = self.read(300.0, lambda path, start=0.0, seconds=0.0: np.zeros(int(seconds * audio.RATE),
                                                                                       np.float32))
        self.assertEqual(len(windows), 6)


class SpectrogramTest(unittest.TestCase):
    def test_filters_cover_0_to_14_khz_in_128_bands(self):
        self.assertEqual(model.FILTERS.shape, (128, 1025))
        self.assertTrue((model.FILTERS >= 0).all())
        bin_hz = audio.RATE / model.N_FFT
        self.assertEqual(float(model.FILTERS[:, int(14100 / bin_hz):].sum()), 0.0)
        self.assertTrue((model.FILTERS.sum(axis=1) > 0).all())

    def test_hann_window_is_periodic(self):
        self.assertEqual(float(model.HANN[0]), 0.0)
        self.assertAlmostEqual(float(model.HANN[model.N_FFT // 2]), 1.0, places=6)
        self.assertGreater(float(model.HANN[-1]), 0.0)

    def test_a_window_gives_1001_frames_in_decibels(self):
        tone = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(audio.WINDOW) / audio.RATE)).astype(np.float32)
        mel = model.mel_db(tone)
        self.assertEqual(mel.shape, (1, 1, 128, 1001))
        self.assertEqual(mel.dtype, np.float32)
        loudest = int(mel[0, 0, :, 500].argmax())
        centres = np.argmax(model.FILTERS, axis=1) * audio.RATE / model.N_FFT
        self.assertLess(abs(centres[loudest] - 1000), 60)
        self.assertEqual(float(model.mel_db(np.zeros(audio.WINDOW, np.float32)).max()), -100.0)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = store.Store(self.folder)

    def tearDown(self):
        self.store.close()

    def test_vectors_round_trip_as_float16(self):
        vector = unit(1, 2, 3)
        self.store.put("a.mp3", 10, 1.5, "v", 200.0, vector)
        self.store.commit()
        self.assertTrue(np.allclose(self.store.vector("a.mp3"), vector, atol=1e-3))
        self.assertEqual(self.store.known(), {"a.mp3": (10, 1.5, "v", False)})

    def test_take_over_copies_a_row_to_another_path(self):
        self.store.put("D:\\a.mp3", 10, 1.5, "v", 200.0, unit(1, 2))
        self.store.put("D:\\bad.mp3", 11, 2.5, "v", 0.0, None, "broken")
        self.store.take_over("D:\\a.mp3", "d:\\a.mp3")
        self.store.take_over("D:\\bad.mp3", "d:\\bad.mp3")
        self.store.commit()
        self.assertTrue(np.allclose(self.store.vector("d:\\a.mp3"), unit(1, 2), atol=1e-3))
        self.assertEqual(self.store.known()["d:\\a.mp3"], (10, 1.5, "v", False))
        self.assertEqual(self.store.failures(), [("D:\\bad.mp3", "broken"), ("d:\\bad.mp3", "broken")])
        self.assertEqual(self.store.counts(), {"analysed": 2, "failed": 2})

    def test_a_failure_keeps_its_reason_and_no_vector(self):
        self.store.put("bad.mp3", 10, 1.5, "v", 0.0, None, "InvalidDataError: x")
        self.assertIsNone(self.store.vector("bad.mp3"))
        self.assertEqual(self.store.failures(), [("bad.mp3", "InvalidDataError: x")])
        self.assertEqual(self.store.counts(), {"analysed": 0, "failed": 1})

    def test_the_matrix_file_is_rebuilt_only_when_the_store_changed(self):
        self.store.put("a.mp3", 1, 1.0, "v", 1.0, unit(1))
        self.store.put("b.mp3", 1, 1.0, "v", 1.0, unit(0, 1))
        self.store.commit()
        paths, matrix = self.store.matrix()
        self.assertEqual(paths, ["a.mp3", "b.mp3"])
        self.assertTrue(np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-3))
        with unittest.mock.patch.object(np, "save") as save:
            self.store.matrix()
        save.assert_not_called()
        self.store.remove(["a.mp3"])
        paths, _ = self.store.matrix()
        self.assertEqual(paths, ["b.mp3"])

    def test_songs_stored_since_the_matrix_file_are_added_without_writing_it_again(self):
        clock = itertools.count(100.0)
        with unittest.mock.patch.object(store.time, "time", side_effect=lambda: next(clock)):
            self.store.put("a.mp3", 1, 1.0, "v", 1.0, unit(1))
            self.store.put("b.mp3", 1, 1.0, "v", 1.0, unit(0, 1))
            self.store.commit()
            self.store.matrix()
            self.store.put("c.mp3", 1, 1.0, "v", 1.0, unit(0, 0, 1))
            self.store.put("a.mp3", 1, 2.0, "v", 1.0, unit(0, 0, 0, 1))  # analysed again
            self.store.commit()
            with unittest.mock.patch.object(np, "save") as save:
                paths, matrix = self.store.matrix()
            save.assert_not_called()
            self.assertEqual(sorted(paths), ["a.mp3", "b.mp3", "c.mp3"])
            self.assertTrue(np.allclose(matrix[paths.index("a.mp3")], unit(0, 0, 0, 1), atol=1e-3))
            self.store.put("b.mp3", 1, 3.0, "v", 0.0, None, "broken now")  # one fewer: written anew
            self.store.commit()
            paths, _ = self.store.matrix()
        self.assertEqual(paths, ["a.mp3", "c.mp3"])

    def test_many_newer_songs_write_the_matrix_file_again(self):
        self.store.put("a.mp3", 1, 1.0, "v", 1.0, unit(1))
        self.store.commit()
        self.store.matrix()
        with unittest.mock.patch.object(store.Store, "REWRITE_AFTER", 1), \
                unittest.mock.patch.object(store.time, "time", return_value=time_after(self.store)):
            self.store.put("b.mp3", 1, 1.0, "v", 1.0, unit(0, 1))
            self.store.commit()
            with unittest.mock.patch.object(np, "save", wraps=np.save) as save:
                paths, _ = self.store.matrix()
        save.assert_called_once()
        self.assertEqual(paths, ["a.mp3", "b.mp3"])


def time_after(stored):
    return stored.last_change() + 10.0


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = store.Store(self.folder)
        self.files = {}
        for name in ("new", "same", "changed", "failed", "old_version"):
            path = os.path.join(self.folder, name + ".mp3")
            with open(path, "wb") as handle:
                handle.write(b"x" * 10)
            self.files[name] = path
        for name in ("same", "changed", "failed", "old_version"):
            info = os.stat(self.files[name])
            size = info.st_size + (1 if name == "changed" else 0)
            version = "older" if name == "old_version" else analysis_version(6)
            self.store.put(self.files[name], size, info.st_mtime, version, 1.0,
                           None if name == "failed" else unit(1), "broken" if name == "failed" else "")
        self.store.commit()

    def tearDown(self):
        self.store.close()

    def test_new_changed_and_other_version_songs_are_analysed_the_rest_counted(self):
        paths = list(self.files.values()) + [os.path.join(self.folder, "gone.mp3")]
        todo, counts, taken_over = analyse.plan(paths, self.store, analysis_version(6))
        self.assertEqual(sorted(os.path.basename(path) for path, _, _ in todo),
                         ["changed.mp3", "new.mp3", "old_version.mp3"])
        self.assertEqual(counts, {"unchanged": 1, "failed_before": 1, "missing": 1, "taken_over": 0})
        self.assertEqual(taken_over, [])

    def test_songs_that_failed_before_are_analysed_again_when_asked(self):
        todo, counts, _ = analyse.plan(list(self.files.values()), self.store, analysis_version(6), retry_failed=True)
        self.assertIn("failed.mp3", [os.path.basename(path) for path, _, _ in todo])
        self.assertEqual(counts["failed_before"], 0)

    def respelled(self, name):
        """The stored file's path with another case, as Kodi lists it after a scan of a lower-cased folder (F45)."""
        return self.files[name].swapcase()

    @unittest.skipUnless(os.name == "nt", "paths differ only in case on Windows")
    def test_the_same_file_spelled_differently_is_taken_over_not_analysed(self):
        path = self.respelled("same")
        todo, counts, taken_over = analyse.plan([path], self.store, analysis_version(6))
        self.assertEqual((todo, taken_over), ([], [(path, self.files["same"])]))
        self.assertEqual(counts["taken_over"], 1)

    @unittest.skipUnless(os.name == "nt", "paths differ only in case on Windows")
    def test_a_respelled_file_is_analysed_when_the_stored_one_differs(self):
        for name in ("changed", "old_version"):
            todo, counts, taken_over = analyse.plan([self.respelled(name)], self.store, analysis_version(6))
            self.assertEqual(([path for path, _, _ in todo], taken_over), ([self.respelled(name)], []), name)

    @unittest.skipUnless(os.name == "nt", "paths differ only in case on Windows")
    def test_a_respelled_failure_is_taken_over_unless_failures_are_tried_again(self):
        path = self.respelled("failed")
        self.assertEqual(analyse.plan([path], self.store, analysis_version(6))[2], [(path, self.files["failed"])])
        todo, _, taken_over = analyse.plan([path], self.store, analysis_version(6), retry_failed=True)
        self.assertEqual(([p for p, _, _ in todo], taken_over), ([path], []))

    def test_other_files_are_not_taken_over(self):
        path = os.path.join(self.folder, "other.mp3")
        with open(path, "wb") as handle:
            handle.write(b"x" * 10)
        todo, counts, taken_over = analyse.plan([path], self.store, analysis_version(6))
        self.assertEqual(([p for p, _, _ in todo], taken_over, counts["taken_over"]), ([path], [], 0))

    @unittest.skipUnless(os.name == "nt", "paths differ only in case on Windows")
    def test_an_analysis_stores_the_taken_over_print_under_the_new_path_and_keeps_the_old(self):
        self.store.put(self.files["same"], *self.store.known()[self.files["same"]][:2], analysis_version(6), 1.0,
                       unit(1, 2))
        self.store.commit()
        path = self.respelled("same")
        with self.assertLogs("soundprint", "INFO") as logged:
            status = analyse.run([path], self.folder, "", 6, 1, 1, low=False, say=lambda line: None)
        self.assertEqual((status["state"], status["todo"], status["taken_over"]), ("finished", 0, 1))
        self.assertTrue(np.allclose(self.store.vector(path), unit(1, 2), atol=1e-3))
        self.assertIsNotNone(self.store.vector(self.files["same"]))
        self.assertEqual(self.store.known()[path], self.store.known()[self.files["same"]])
        log = "\n".join(logged.output)
        self.assertIn(f"{path}: taken over from {self.files['same']}", log)
        self.assertIn("1 taken over from another spelling of their path", log)

    def test_nothing_to_do_finishes_at_once(self):
        status = analyse.run([self.files["same"]], self.folder, "", 6, 1, 1, low=False, say=lambda line: None)
        self.assertEqual((status["state"], status["todo"]), ("finished", 0))
        self.assertEqual(analyse.read_status(self.folder)["state"], "finished")

    def test_a_model_that_cannot_load_stops_the_analysis_before_any_worker_starts(self):
        with unittest.mock.patch.object(model.Model, "__init__", side_effect=ImportError("no onnxruntime")):
            with self.assertRaises(ImportError):
                analyse.run([self.files["new"]], self.folder, "", 6, 2, 1, low=False, say=lambda line: None)
        self.assertEqual(analyse.read_status(self.folder)["state"], "failed")

    def test_a_second_analysis_does_not_start_while_one_runs(self):
        state.write_status(self.folder, {"state": "running", "pid": os.getppid()})  # a process that is alive
        lines = []
        status = analyse.run([self.files["new"]], self.folder, "", 6, 1, 1, low=False, say=lines.append)
        self.assertEqual(status, {"state": "busy", "pid": os.getppid()})
        self.assertIn("running already", lines[0])
        self.assertEqual(state.read_status(self.folder)["pid"], os.getppid())  # its status left alone

    def test_an_analysis_says_it_runs_while_it_looks_at_the_files(self):
        seen = []
        real_plan = analyse.plan

        def plan(*args):
            seen.append(state.read_status(self.folder))
            return real_plan(*args)

        with unittest.mock.patch.object(analyse, "plan", side_effect=plan):
            analyse.run([self.files["same"]], self.folder, "", 6, 1, 1, low=False, say=lambda line: None)
        self.assertEqual((seen[0]["state"], seen[0]["phase"], seen[0]["pid"]), ("running", "planning", os.getpid()))

    def analyse_with(self, kodi_ended, **kwargs):
        """run() with a stand-in pool that gives one result for each song to analyse; Kodi's process ended or not."""
        def results(_, todo, chunksize=1):
            for path, size, mtime in todo:
                yield {"path": path, "size": size, "mtime": mtime, "length": 1.0, "vector": unit(1), "error": "",
                       "windows": 6, "how": "seek", "decode_s": 0.1, "model_s": 0.1}

        pool = unittest.mock.Mock()
        pool.imap_unordered.side_effect = results
        with unittest.mock.patch.object(model.Model, "__init__", return_value=None), \
                unittest.mock.patch.dict(os.environ), \
                unittest.mock.patch.object(analyse.multiprocessing, "get_context") as context, \
                unittest.mock.patch.object(analyse, "Watched") as watched:
            context.return_value.Pool.return_value = pool
            watched.return_value.ended.return_value = kodi_ended
            status = analyse.run([self.files["new"], self.files["changed"]], self.folder, "", 6, 1, 1, low=False,
                                 say=lambda line: None, **kwargs)
        return status, watched, pool

    def test_an_analysis_started_by_kodi_stops_once_kodi_has_closed(self):
        with self.assertLogs("soundprint", "INFO") as logged:
            status, watched, pool = self.analyse_with(True, kodi_pid=4321)
        self.assertEqual((status["state"], status["stopped_by"], status["done"], status["todo"]),
                         ("stopped", "kodi_closed", 1, 2))
        self.assertEqual(state.read_status(self.folder)["stopped_by"], "kodi_closed")
        watched.assert_called_once_with(4321)
        watched.return_value.close.assert_called_once()
        pool.terminate.assert_called_once()
        self.assertIn("Kodi (process 4321) has closed: the analysis stops after the songs in hand",
                      "\n".join(logged.output))
        self.assertIn(self.files["new"], self.store.known())  # the songs done are stored

    def test_an_analysis_goes_on_while_kodi_runs(self):
        status, _, _ = self.analyse_with(False, kodi_pid=4321)
        self.assertEqual((status["state"], status["done"]), ("finished", 2))
        self.assertNotIn("stopped_by", status)

    def test_a_process_is_followed_until_it_ends(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        watched = state.Watched(process.pid)
        try:
            self.assertFalse(watched.ended())
            process.kill()
            process.wait()
            self.assertTrue(watched.ended())
        finally:
            watched.close()
        self.assertFalse(state.Watched(0).ended())  # nothing to follow: the analysis was started by hand

    def test_the_command_line_passes_kodis_process_on(self):
        args = cli.arguments(["--data", self.folder, "analyse", "--kodi-pid", "4321"])
        self.assertEqual(args.kodi_pid, 4321)
        self.assertEqual(cli.arguments(["--data", self.folder, "analyse"]).kodi_pid, 0)

    def test_analysis_version_names_model_snippets_and_preroll(self):
        self.assertEqual(analysis_version(6), "dclap-v1/snippets-6/preroll-1")


class NearestTest(unittest.TestCase):
    def setUp(self):
        self.store = store.Store(tempfile.mkdtemp())
        for name, vector in (("seed", unit(1, 0)), ("close", unit(1, 0.2)), ("far", unit(0, 1)),
                             ("middle", unit(1, 1))):
            self.store.put(name, 1, 1.0, "v", 1.0, vector)
        self.store.commit()

    def tearDown(self):
        self.store.close()

    def test_nearest_first_without_the_seed(self):
        found, source, left_out = neighbours.nearest(self.store, "seed", 2, in_order=True)
        self.assertEqual(source, "stored")
        self.assertEqual([(path, rank) for path, _, rank in found], [("close", 1), ("middle", 2)])
        self.assertGreater(found[0][1], found[1][1])
        self.assertEqual(left_out, {"artist": 0, "same_song": 0, "listed": 0})

    def test_count_larger_than_the_store(self):
        found, _, _ = neighbours.nearest(self.store, "seed", 50, in_order=True)
        self.assertEqual([path for path, _, _ in found], ["close", "middle", "far"])
        found, _, _ = neighbours.nearest(self.store, "seed", 50, rng=random.Random(1))
        self.assertEqual(sorted(path for path, _, _ in found), ["close", "far", "middle"])

    def test_a_file_under_two_spellings_is_taken_once_in_kodis(self):
        for path, vector in (("D:\\Music\\seed.mp3", unit(1, -0.01)), ("d:\\music\\seed.mp3", unit(1, -0.01)),
                             ("D:\\Music\\twin.mp3", unit(1, 0.05)), ("d:\\music\\twin.mp3", unit(1, 0.05))):
            self.store.put(path, 1, 1.0, "v", 1.0, vector)  # the old spellings ("D:\Music") kept by F45
        self.store.commit()
        known = {"d:\\music\\twin.mp3": ("Neu!", "Hallo Gallo"), "d:\\music\\seed.mp3": ("Neu!", "Seed"),
                 "seed": ("Kraftwerk", "Radioactivity"), "close": ("Cluster", "Close"),
                 "middle": ("Harmonia", "Middle"), "far": ("Moebius", "Far")}
        with unittest.mock.patch.object(neighbours, "CASE_BLIND", True):
            found, _, left_out = neighbours.nearest(self.store, "d:\\music\\seed.mp3", 3, in_order=True,
                                                    details=lambda path: known.get(path, ("", "")))
            self.assertEqual([path for path, _, _ in found], ["seed", "d:\\music\\twin.mp3", "close"])
            self.assertEqual(left_out["same_song"], 2)  # the seed's old spelling and the twin's
            found, _, left_out = neighbours.nearest(self.store, "d:\\music\\seed.mp3", 3, in_order=True,
                                                    details=lambda path: known.get(path, ("", "")),
                                                    leave_out=["D:/MUSIC/TWIN.mp3"])
            self.assertEqual([path for path, _, _ in found], ["seed", "close", "middle"])
            self.assertEqual(left_out["listed"], 2)  # both spellings: one file

    def test_listed_songs_are_left_out_their_paths_compared_as_the_add_on_does(self):
        self.store.put("D:\\music\\close2.mp3", 1, 1.0, "v", 1.0, unit(1, 0.25))
        self.store.commit()
        found, _, left_out = neighbours.nearest(self.store, "seed", 2, in_order=True,
                                                leave_out=["close", " D:/music/close2.mp3", "not stored", "seed"])
        self.assertEqual([(path, rank) for path, _, rank in found], [("middle", 3), ("far", 4)])  # ranks of all songs
        self.assertEqual(left_out["listed"], 3)  # the seed counted: it is the station's too

    def test_a_seed_without_vector_and_without_model_gives_nothing(self):
        self.assertEqual(neighbours.nearest(self.store, "D:\\nowhere.mp3", 5)[:2], ([], "not a local file"))


class MixRulesTest(unittest.TestCase):
    """The rules for a mix: no artist repeat within a window (the seed first), each song once, variety."""

    def setUp(self):
        self.store = store.Store(tempfile.mkdtemp())
        self.details = {"seed": ("Kraftwerk", "Radioactivity")}
        songs_by_closeness = [("k1", "Kraftwerk", "Ohm Sweet Ohm"), ("k2", "Kraftwerk", "Antenna"),
                              ("copy", "Kraftwerk", "Radioactivity"), ("c1", "Cluster", "Sowiesoso"),
                              ("c2", "cluster", "Hollywood"), ("n1", "Neu!", "Hallogallo"),
                              ("c3", "Cluster", "Dem Wanderer"), ("h1", "Harmonia", "Watussi")]
        self.store.put("seed", 1, 1.0, "v", 1.0, unit(1, 0))
        for number, (path, artist, title) in enumerate(songs_by_closeness, start=1):
            self.store.put(path, 1, 1.0, "v", 1.0, unit(1, 0.1 * number))
            self.details[path] = (artist, title)
        self.store.commit()

    def tearDown(self):
        self.store.close()

    def nearest(self, count, **rules):
        rules.setdefault("in_order", "variety" not in rules)  # the rules alone: the nearest songs in order
        found, _, left_out = neighbours.nearest(self.store, "seed", count,
                                                details=lambda path: self.details.get(path, ("", "")), **rules)
        return [path for path, _, _ in found], left_out

    def test_no_artist_repeat_within_the_window_the_seed_first(self):
        found, left_out = self.nearest(4, window=1)
        self.assertEqual(found, ["c1", "n1", "c3", "h1"])  # artist names compared loosely: "cluster" is Cluster
        self.assertEqual(left_out, {"artist": 3, "same_song": 1, "listed": 0})
        found, left_out = self.nearest(5, window=2)
        self.assertEqual(found, ["c1", "n1", "h1"])  # Cluster's third song came too soon after the first
        self.assertEqual(left_out["artist"], 4)

    def test_without_a_window_artists_may_repeat(self):
        self.assertEqual(self.nearest(4)[0], ["k1", "k2", "c1", "c2"])

    def test_the_window_holds_in_a_mix_chosen_with_variety(self):
        for seed in range(20):
            found, _ = self.nearest(3, window=1, variety=6, rng=random.Random(seed))
            artists = [neighbours.artist_key(self.details[path][0]) for path in ["seed"] + found]
            self.assertTrue(all(a != b for a, b in zip(artists, artists[1:])), (seed, found))

    def test_the_seed_itself_on_another_album_is_left_out_even_without_a_limit(self):
        found, left_out = self.nearest(3)
        self.assertEqual(found, ["k1", "k2", "c1"])
        self.assertEqual(left_out["same_song"], 1)

    def test_variety_draws_at_random_from_further_out(self):
        order = ["k1", "k2", "c1", "c2", "n1", "c3", "h1"]
        mixes = {tuple(self.nearest(3, variety=6, rng=random.Random(seed))[0]) for seed in range(20)}
        self.assertGreater(len(mixes), 3)
        self.assertTrue(all(len(found) == 3 and set(found) <= set(order) for found in mixes))
        self.assertTrue(any(list(found) != sorted(found, key=order.index) for found in mixes))  # near and far mixed
        self.assertEqual(self.nearest(3, variety=6, in_order=True)[0], ["k1", "k2", "c1"])  # in order: no draw


class VarietyTest(unittest.TestCase):
    """Variety: how far into the order by sound a mix reaches, each song drawn with a weight of 1 / rank ** power."""

    @classmethod
    def setUpClass(cls):
        cls.store = store.Store(tempfile.mkdtemp())
        cls.store.put("seed", 1, 1.0, "v", 1.0, unit(1, 0))
        for number in range(1, 3001):  # song n is the n-th nearest
            angle = number / 3001 * 3
            cls.store.put(f"s{number}", 1, 1.0, "v", 1.0, unit(np.cos(angle), np.sin(angle)))
        cls.store.commit()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def ranks(self, variety, seed, count=20, window=0, **more):
        def details(path):
            return (f"artist {int(path[1:]) % 4}", path) if path != "seed" else ("seed artist", "seed")
        found, _, _ = neighbours.nearest(self.store, "seed", count, variety=variety, rng=random.Random(seed),
                                         details=details if window else None, window=window, **more)
        self.assertEqual([path for path, _, _ in found], [f"s{rank}" for _, _, rank in found])
        return [rank for _, _, rank in found]

    def test_the_reach_grows_by_the_same_factor_with_each_step(self):
        self.assertEqual([neighbours.reach(25, variety, 153000) for variety in (0, 1, 3, 5, 7, 9)],
                         [38, 66, 457, 3175, 22039, 153000])  # at 0 half as many again as the mix holds
        self.assertEqual(neighbours.reach(25, 9, 3000), 3000)  # a smaller store: all of it
        self.assertEqual(neighbours.reach(25, 12, 153000), 153000)
        self.assertEqual(neighbours.reach(100, 9, 50), 100)
        self.assertEqual(neighbours.reach(100, 1, 120), 120)  # a store hardly larger than the mix: never below 0's

    def test_the_far_songs_weigh_more_with_each_step(self):
        self.assertEqual([round(neighbours.draw_power(variety), 3) for variety in (0, 3, 9, 12)],
                         [1.0, 0.9, 0.7, 0.7])

    def test_variety_0_draws_from_the_nearest_songs_and_varies(self):
        mixes = [self.ranks(0, seed) for seed in range(20)]
        self.assertTrue(all(len(set(ranks)) == 20 and max(ranks) <= 30 for ranks in mixes))  # the nearest 30
        self.assertGreater(len({tuple(sorted(ranks)) for ranks in mixes}), 10)  # other songs each time
        self.assertTrue(any(ranks != sorted(ranks) for ranks in mixes))  # near and far mixed

    def test_in_order_takes_the_nearest_nearest_first(self):
        self.assertEqual(self.ranks(0, seed=1, in_order=True), list(range(1, 21)))
        self.assertEqual(self.ranks(5, seed=1, in_order=True), list(range(1, 21)))

    def test_listed_songs_are_left_out_before_the_draw(self):
        station = [f"s{rank}" for rank in range(1, 31)]
        self.assertEqual(self.ranks(0, seed=1, in_order=True, leave_out=station), list(range(31, 51)))
        for seed in range(10):  # at 0 from the nearest 30 the station hasn't had
            ranks = self.ranks(0, seed, leave_out=station)
            self.assertTrue(len(ranks) == 20 and all(30 < rank <= 60 for rank in ranks), ranks)
        ranks = self.ranks(0, seed=2, window=3, leave_out=station)  # the rules see the same songs
        self.assertTrue(len(ranks) == 20 and min(ranks) > 30, ranks)

    def test_a_loose_mix_spreads_from_near_to_far(self):
        mixes = [self.ranks(9, seed) for seed in range(40)]
        self.assertTrue(all(len(ranks) == 20 and len(set(ranks)) == 20 for ranks in mixes))
        everything = [rank for ranks in mixes for rank in ranks]
        near, far = sum(rank <= 30 for rank in everything), sum(rank > 1000 for rank in everything)
        self.assertGreater(near / len(everything), 0.1)  # the nearer the likelier, but far songs weigh more at 9
        self.assertGreater(far / len(everything), 0.2)
        firsts = [ranks[0] for ranks in mixes]  # the first song is drawn like the others: near or far
        self.assertGreater(max(firsts), 100)

    def test_each_step_reaches_further(self):
        deepest = [sorted(max(self.ranks(variety, seed)) for seed in range(15))[7] for variety in (0, 3, 6, 9)]
        self.assertTrue(20 < deepest[0] <= 30)
        self.assertEqual(deepest, sorted(deepest))
        self.assertLess(deepest[2], deepest[3])
        self.assertTrue(all(max(self.ranks(3, seed)) <= neighbours.reach(20, 3, 3000) for seed in range(15)))

    def test_when_the_rules_pass_over_the_draws_the_mix_goes_on_further_out(self):
        ranks = self.ranks(1, seed=3, count=20, window=3)  # 4 artists in turn: many draws are passed over
        self.assertEqual(len(ranks), 20)


class SongListTest(unittest.TestCase):
    def test_kodi_database_picks_the_newest_version(self):
        userdata = tempfile.mkdtemp()
        os.makedirs(os.path.join(userdata, "Database"))
        for name in ("MyMusic82.db", "MyMusic83.db", "MyVideos131.db"):
            open(os.path.join(userdata, "Database", name), "w").close()
        self.assertEqual(os.path.basename(songs.kodi_database(userdata)), "MyMusic83.db")

    def test_songs_come_from_kodis_song_and_path_tables(self):
        database = os.path.join(tempfile.mkdtemp(), "MyMusic83.db")
        connection = sqlite3.connect(database)
        connection.executescript(
            "CREATE TABLE path (idPath INTEGER, strPath TEXT);"
            "CREATE TABLE song (idSong INTEGER, idPath INTEGER, strFileName TEXT);"
            "INSERT INTO path VALUES (1, 'D:\\music\\a\\'), (2, 'smb://box/music/');"
            "INSERT INTO song VALUES (1, 1, '01.mp3'), (2, 1, '02.flac'), (3, 2, 'x.mp3');")
        connection.commit()
        connection.close()
        self.assertEqual(songs.from_kodi(database), ["D:\\music\\a\\01.mp3", "D:\\music\\a\\02.flac",
                                                      "smb://box/music/x.mp3"])

    def test_local_leaves_out_remote_outside_and_repeated_paths(self):
        inside = os.path.join("D:" + os.sep, "music", "#electronica", "a.mp3")
        outside = os.path.join("D:" + os.sep, "music", "#rock", "b.mp3")
        kept, remote, out = songs.local([inside, inside, outside, "smb://box/c.mp3"],
                                        [os.path.join("D:" + os.sep, "music", "#electronica")])
        self.assertEqual((kept, remote, out), ([inside], 1, 1))

    def test_artist_and_title_come_from_kodis_library(self):
        database = os.path.join(tempfile.mkdtemp(), "MyMusic83.db")
        connection = sqlite3.connect(database)
        connection.executescript(
            "CREATE TABLE path (idPath INTEGER, strPath TEXT);"
            "CREATE TABLE song (idSong INTEGER, idPath INTEGER, strFileName TEXT, strArtistDisp TEXT, strTitle TEXT);"
            "INSERT INTO path VALUES (1, 'D:\\music\\a\\');"
            "INSERT INTO song VALUES (1, 1, '01.mp3', 'Cluster', 'Sowiesoso');")
        connection.commit()
        connection.close()
        details = songs.Details(database)
        self.assertEqual(details("D:\\music\\a\\01.mp3"), ("Cluster", "Sowiesoso"))
        self.assertEqual(details("D:\\music\\a\\02.mp3"), ("", ""))
        details.close()
        self.assertEqual(songs.Details("")("D:\\x.mp3"), ("", ""))

    def test_a_path_splits_into_kodis_folder_and_file_name(self):
        self.assertEqual(songs.split("D:\\music\\a\\01.mp3"), ("D:\\music\\a\\", "01.mp3"))
        self.assertEqual(songs.split("/music/a/01.mp3"), ("/music/a/", "01.mp3"))

    def test_a_list_file_may_start_with_a_byte_order_mark(self):
        name = os.path.join(tempfile.mkdtemp(), "list.txt")
        with open(name, "w", encoding="utf-8-sig") as handle:
            handle.write("a.mp3\n\n b.mp3 \n")
        self.assertEqual(songs.from_list(name), ["a.mp3", "b.mp3"])


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ModelDownloadTest(unittest.TestCase):
    def test_files_are_checked_and_the_licence_noted(self):
        folder = tempfile.mkdtemp()
        payloads = {name: name.encode() * 3 for name in model.FILES}
        digests = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
        opened = []

        def opener(url, timeout):
            opened.append(url)
            return FakeResponse(payloads[url.rsplit("/", 1)[1]])

        with unittest.mock.patch.dict(model.FILES, digests):
            self.assertEqual(sorted(model.missing(folder)), sorted(digests))
            model.fetch(folder, say=lambda line: None, opener=opener)
            self.assertEqual(model.missing(folder), [])
            model.fetch(folder, say=lambda line: None, opener=opener)  # nothing to fetch the second time
        self.assertEqual(len(opened), 2)
        self.assertTrue(all(url.startswith(model.RELEASE) for url in opened))
        with open(os.path.join(folder, "LICENCE.txt"), encoding="utf-8") as handle:
            self.assertIn("AGPL-3.0", handle.read())

    def test_a_download_that_does_not_match_is_thrown_away(self):
        folder = tempfile.mkdtemp()
        with self.assertRaises(RuntimeError):
            model.fetch(folder, say=lambda line: None, opener=lambda url, timeout: FakeResponse(b"wrong"))
        self.assertEqual([name for name in os.listdir(folder) if name.startswith("model")], [])


class CommandLineTest(unittest.TestCase):
    def test_data_and_model_folders_default_to_the_addon_data(self):
        args = cli.arguments(["--userdata", "U", "status"])
        self.assertEqual(args.data, os.path.join("U", "addon_data", "plugin.audio.incipit", "soundprint"))
        self.assertEqual(args.model, os.path.join(args.data, "model"))

    def test_status_prints_the_status_file_and_whether_the_analysis_is_alive(self):
        folder = tempfile.mkdtemp()
        state.write_status(folder, {"state": "running", "done": 3, "pid": os.getpid()})
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            cli.main(["--data", folder, "status"])
        self.assertEqual((json.loads(out.getvalue())["done"], json.loads(out.getvalue())["alive"]), (3, True))

    def test_stop_leaves_the_stop_file(self):
        folder = tempfile.mkdtemp()
        cli.main(["--data", folder, "stop"])
        self.assertTrue(os.path.isfile(os.path.join(folder, state.STOP_FILE)))

    def test_neighbours_answer_with_artist_title_and_what_was_left_out(self):
        userdata, folder = tempfile.mkdtemp(), tempfile.mkdtemp()
        stored = store.Store(folder)
        stored.put("seed.mp3", 1, 1.0, "v", 1.0, unit(1))
        stored.put("near.mp3", 1, 1.0, "v", 1.0, unit(1, 0.1))
        stored.commit()
        stored.close()
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = cli.main(["--userdata", userdata, "--data", folder, "neighbours", "seed.mp3", "--count", "5",
                             "--artist-window", "2"])
        answer = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((answer["seed_vector"], answer["library"], answer["analysed"]), ("stored", "", 2))
        self.assertEqual(answer["songs"], [{"path": "near.mp3", "similarity": answer["songs"][0]["similarity"],
                                            "rank": 1, "artist": "", "title": ""}])
        self.assertEqual(answer["reach"], 5)  # a store smaller than the mix: all of it
        self.assertEqual(answer["left_out"], {"artist": 0, "same_song": 0, "listed": 0})

    def test_neighbours_leave_out_a_list_of_songs_and_take_them_in_order(self):
        userdata, folder = tempfile.mkdtemp(), tempfile.mkdtemp()
        stored = store.Store(folder)
        stored.put("seed.mp3", 1, 1.0, "v", 1.0, unit(1))
        for number in range(1, 6):
            stored.put(f"n{number}.mp3", 1, 1.0, "v", 1.0, unit(1, 0.1 * number))
        stored.commit()
        stored.close()
        listed = os.path.join(folder, "station.txt")
        with open(listed, "w", encoding="utf-8") as handle:
            handle.write("n1.mp3\nn3.mp3\n")
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            cli.main(["--userdata", userdata, "--data", folder, "neighbours", "seed.mp3", "--count", "2",
                      "--in-order", "--leave-out", listed])
        answer = json.loads(out.getvalue())
        self.assertEqual([(song["path"], song["rank"]) for song in answer["songs"]], [("n2.mp3", 2), ("n4.mp3", 4)])
        self.assertEqual((answer["left_out"]["listed"], answer["reach"]), (2, 2))


class RunningTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def test_a_running_analysis_needs_its_process_alive_and_a_recent_status(self):
        state.write_status(self.folder, {"state": "running", "pid": 1234})
        updated = state.read_status(self.folder)["updated"]
        self.assertTrue(state.running(self.folder, alive=lambda pid: pid == 1234))
        self.assertEqual(state.running(self.folder, alive=lambda pid: False), {})
        self.assertEqual(state.running(self.folder, now=updated + state.STALE_SECONDS + 1, alive=lambda pid: True), {})

    def test_a_finished_analysis_is_not_running(self):
        state.write_status(self.folder, {"state": "finished", "pid": os.getpid()})
        self.assertEqual(state.running(self.folder), {})
        self.assertEqual(state.running(tempfile.mkdtemp()), {})

    def test_this_process_is_alive_and_an_unused_number_is_not(self):
        self.assertTrue(state.process_alive(os.getpid()))
        self.assertFalse(state.process_alive(0))
        self.assertFalse(state.process_alive(2 ** 30))


def write_wave(path, seconds, channels=2, rate=44100):
    """A sweep from 200 Hz to 4 kHz, different in each channel."""
    t = np.arange(int(seconds * rate)) / rate
    left = 0.4 * np.sin(2 * np.pi * (200 + 3800 * t / seconds / 2) * t)
    signal = np.stack([left, -left][:channels], axis=1)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((signal * 32767).astype("<i2").tobytes())


def id3_tag(size, footer=False):
    """An ID3v2.3 tag of size bytes in all (padding after one text frame); flagged with a footer, 10 more."""
    body = size - 10
    syncsafe = bytes([(body >> 21) & 0x7F, (body >> 14) & 0x7F, (body >> 7) & 0x7F, body & 0x7F])
    frame = b"TIT2" + (6).to_bytes(4, "big") + b"\x00\x00" + b"\x00Title"
    tag = b"ID3\x03\x00" + (b"\x10" if footer else b"\x00") + syncsafe + frame
    return tag + b"\x00" * (size - len(tag)) + (b"3DI" + b"\x00" * 7 if footer else b"")


class TagTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "song.mp3")

    def write(self, data):
        with open(self.path, "wb") as handle:
            handle.write(data)

    def test_the_end_of_an_id3_tag_counts_its_header_and_footer(self):
        self.write(id3_tag(2210) + b"RIFF")
        self.assertEqual(audio.tag_end(self.path), 2210)
        self.write(id3_tag(300, footer=True) + b"MP+")
        self.assertEqual(audio.tag_end(self.path), 310)

    def test_a_file_without_tag_ends_none(self):
        self.write(b"RIFF" + b"\x00" * 20)
        self.assertEqual(audio.tag_end(self.path), 0)

    def test_a_file_seen_from_the_tags_end_reads_and_seeks_from_there(self):
        self.write(b"x" * 100 + b"0123456789")
        view = audio.FileFrom(self.path, 100)
        try:
            self.assertEqual(view.read(4), b"0123")
            self.assertEqual(view.tell(), 4)
            self.assertEqual(view.seek(2), 2)
            self.assertEqual(view.read(2), b"23")
            self.assertEqual(view.seek(0, os.SEEK_END), 10)
        finally:
            view.close()


@unittest.skipUnless(HAVE_AV, "needs av (PyAV), as in the tool's own environment")
class DecodingTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sweep.wav")
        write_wave(self.path, 30.0, channels=1)

    def test_whole_file_at_48_khz(self):
        self.assertAlmostEqual(audio.decode(self.path).size / audio.RATE, 30.0, places=2)
        self.assertAlmostEqual(audio.length_of(self.path), 30.0, places=1)

    def test_a_seeked_snippet_matches_the_same_stretch_of_the_whole_decode(self):
        whole = audio.decode(self.path)
        part = audio.decode(self.path, 12.0, 5.0)
        self.assertEqual(part.size, 5 * audio.RATE)
        stretch = whole[12 * audio.RATE:17 * audio.RATE]
        self.assertLess(float(np.abs(part - stretch).max()), 2e-3)

    def test_channels_are_averaged(self):
        write_wave(self.path, 3.0, channels=2)  # right = -left
        self.assertLess(float(np.abs(audio.decode(self.path)).max()), 1e-3)

    def test_a_wave_file_behind_an_id3_tag_is_read_after_the_tag(self):
        # as some MP3s in a WAV file: FFmpeg doesn't look for the RIFF header behind the tag
        with open(self.path, "rb") as handle:
            wave_data = handle.read()
        tagged = os.path.join(os.path.dirname(self.path), "tagged.mp3")
        with open(tagged, "wb") as handle:
            handle.write(id3_tag(2210) + wave_data)
        self.assertAlmostEqual(audio.length_of(tagged), 30.0, places=1)
        whole = audio.decode(self.path)
        self.assertLess(float(np.abs(audio.decode(tagged) - whole).max()), 1e-6)
        part = audio.decode(tagged, 12.0, 5.0)
        self.assertLess(float(np.abs(part - whole[12 * audio.RATE:17 * audio.RATE]).max()), 2e-3)


@unittest.skipUnless(HAVE_AV and not model.missing(MODEL_FOLDER) if HAVE_AV else False,
                     "needs av, onnxruntime and the model, as after `python -m soundprint setup`")
class ModelTest(unittest.TestCase):
    def test_a_song_vector_has_length_one_and_is_repeatable(self):
        path = os.path.join(tempfile.mkdtemp(), "sweep.wav")
        write_wave(path, 40.0)
        engine = model.Model(MODEL_FOLDER, threads=1)
        windows, length, how = audio.snippets(path, 3)
        first, second = engine.embed(windows), engine.embed(windows)
        self.assertEqual((first.shape, how), ((512,), "seek"))
        self.assertAlmostEqual(float(np.linalg.norm(first)), 1.0, places=4)
        self.assertTrue(np.allclose(first, second))


if __name__ == "__main__":
    unittest.main()
