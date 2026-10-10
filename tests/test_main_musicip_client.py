"""Requests to the MusicIP server: reload before every mix, mix fetching, errors and response decoding."""

import socket
import unittest

from fake_kodi import kodi
from support import MusicIPServerTestCase, KodiTestCase, main

SEED = "D:\\music\\Motörhead\\Ace of Spades (1980)\\01 Ace of Spades.mp3"
TRACKS = [
    "D:\\music\\Motörhead\\Overkill (1979)\\01 Overkill.mp3",
    "D:\\music\\Saxon\\Wheels of Steel (1980)\\01 Motorcycle Man.mp3",
]


class FetchMixTest(MusicIPServerTestCase):
    def test_reloads_server_then_fetches_mix_with_seed_first(self):
        self.musicip.set_mix(SEED, TRACKS)
        tracks = main.fetch_mix(SEED, 20)

        self.assertEqual(tracks, [SEED] + TRACKS)
        self.assertEqual([path for path, _query in self.musicip.requests], ["/server/reload", "/api/mix"])
        query = self.musicip.mix_requests()[0]
        self.assertEqual(query["song"], SEED)
        self.assertEqual(query["size"], "20")
        self.assertEqual(query["style"], "40")

    def test_seed_returned_by_server_is_not_duplicated(self):
        self.musicip.set_mix(SEED, [SEED.replace("\\", "/"), TRACKS[0], TRACKS[0]])
        self.assertEqual(main.fetch_mix(SEED, 20), [SEED, TRACKS[0]])

    def test_latin_1_response_is_decoded(self):
        self.musicip.encoding = "iso-8859-1"
        self.musicip.set_mix(SEED, TRACKS)
        self.assertEqual(main.fetch_mix(SEED, 20)[1], TRACKS[0])

    def test_blank_lines_are_ignored(self):
        self.musicip.mix_body = ("\n" + TRACKS[0] + "\r\n\r\n  \n").encode("utf-8")
        self.assertEqual(main.fetch_mix(SEED, 20), [SEED, TRACKS[0]])

    def test_empty_mix_is_an_error(self):
        with self.assertRaisesRegex(main.MusicIPError, "empty mix"):
            main.fetch_mix(SEED, 20)

    def test_http_error_from_mix(self):
        self.musicip.mix_status = 500
        with self.assertRaisesRegex(main.MusicIPError, "HTTP 500"):
            main.fetch_mix(SEED, 20)
        self.assertIn("MusicIP error body: b'server error'", kodi.log_text())

    def test_failed_reload_aborts_mix_generation(self):
        self.musicip.reload_status = 503
        with self.assertRaisesRegex(main.MusicIPError, "reload returned HTTP 503"):
            main.fetch_mix(SEED, 20)
        self.assertEqual(self.musicip.mix_requests(), [])

    def test_fetch_with_defaults_remembers_parameters(self):
        self.musicip.set_mix(SEED, TRACKS)
        main.fetch_mix_with_defaults(SEED, 15)
        self.assertEqual(self.musicip.mix_requests()[0]["size"], "15")
        self.assertEqual(main.pop_mix_generation_parameters(SEED, 15)["size"], 15)

    def test_confirmed_fetch_uses_edited_parameters(self):
        self.musicip.set_mix(SEED, TRACKS)
        kodi.respond("select", 1, 0)
        kodi.respond("numeric", "5")
        main.fetch_mix_confirmed(SEED, 20)
        self.assertEqual(self.musicip.mix_requests()[0]["size"], "5")
        self.assertEqual(main.pop_mix_generation_parameters(SEED, 20)["size"], 5)

    def test_confirmed_fetch_cancelled(self):
        with self.assertRaisesRegex(main.MusicIPError, "cancelled"):
            main.fetch_mix_confirmed(SEED, 20)
        self.assertEqual(self.musicip.requests, [])


class UnreachableServerTest(KodiTestCase):
    def test_unreachable_server(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        kodi.settings.update({"host": "127.0.0.1", "port": str(free_port), "timeout": "2"})
        with self.assertRaisesRegex(main.MusicIPError, f"Could not reload MusicIP server at 127.0.0.1:{free_port}"):
            main.fetch_mix(SEED, 20)


class ResponseHelpersTest(unittest.TestCase):
    def test_decode_response(self):
        self.assertEqual(main.decode_response("Motörhead".encode("utf-8")), "Motörhead")
        self.assertEqual(main.decode_response("Motörhead".encode("iso-8859-1")), "Motörhead")

    def test_prepend_seed_track(self):
        self.assertEqual(main.prepend_seed_track(" a.mp3 ", ["b.mp3", "", "a.mp3", "b.mp3"]), ["a.mp3", "b.mp3"])
        self.assertEqual(main.prepend_seed_track("", ["b.mp3"]), ["b.mp3"])


if __name__ == "__main__":
    unittest.main()
