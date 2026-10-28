"""Sound prints: snippet positions and reading, the spectrogram, the store, the analysis plan, the search, the
song list and the model download. Decoding and the model itself are tested where av and onnxruntime are installed
(the tool's own environment); elsewhere those tests are skipped."""

import hashlib
import io
import json
import os
import sqlite3
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
from soundprint import analyse, analysis_version, audio, model, neighbours, songs, store  # noqa: E402

try:
    import av  # noqa: F401

    HAVE_AV = True
except ImportError:
    HAVE_AV = False
MODEL_FOLDER = os.path.join(cli.kodi_userdata(), "addon_data", "plugin.audio.musicip", "soundprint", "model")


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
        todo, counts = analyse.plan(paths, self.store, analysis_version(6))
        self.assertEqual(sorted(os.path.basename(path) for path, _, _ in todo),
                         ["changed.mp3", "new.mp3", "old_version.mp3"])
        self.assertEqual(counts, {"unchanged": 1, "failed_before": 1, "missing": 1})

    def test_nothing_to_do_finishes_at_once(self):
        status = analyse.run([self.files["same"]], self.folder, "", 6, 1, 1, low=False, say=lambda line: None)
        self.assertEqual((status["state"], status["todo"]), ("finished", 0))
        self.assertEqual(analyse.read_status(self.folder)["state"], "finished")

    def test_a_model_that_cannot_load_stops_the_analysis_before_any_worker_starts(self):
        with unittest.mock.patch.object(model.Model, "__init__", side_effect=ImportError("no onnxruntime")):
            with self.assertRaises(ImportError):
                analyse.run([self.files["new"]], self.folder, "", 6, 2, 1, low=False, say=lambda line: None)
        self.assertEqual(analyse.read_status(self.folder)["state"], "failed")

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
        found, source = neighbours.nearest(self.store, "seed", 2)
        self.assertEqual(source, "stored")
        self.assertEqual([path for path, _ in found], ["close", "middle"])
        self.assertGreater(found[0][1], found[1][1])

    def test_count_larger_than_the_store(self):
        found, _ = neighbours.nearest(self.store, "seed", 50)
        self.assertEqual([path for path, _ in found], ["close", "middle", "far"])

    def test_a_seed_without_vector_and_without_model_gives_nothing(self):
        self.assertEqual(neighbours.nearest(self.store, "D:\\nowhere.mp3", 5), ([], "not a local file"))


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
        self.assertEqual(args.data, os.path.join("U", "addon_data", "plugin.audio.musicip", "soundprint"))
        self.assertEqual(args.model, os.path.join(args.data, "model"))

    def test_status_prints_the_status_file(self):
        folder = tempfile.mkdtemp()
        analyse.write_status(folder, {"state": "running", "done": 3})
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            cli.main(["--data", folder, "status"])
        self.assertEqual(json.loads(out.getvalue())["done"], 3)

    def test_stop_leaves_the_stop_file(self):
        folder = tempfile.mkdtemp()
        cli.main(["--data", folder, "stop"])
        self.assertTrue(os.path.isfile(os.path.join(folder, analyse.STOP_FILE)))


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
