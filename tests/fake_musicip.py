"""A local HTTP server standing in for the MusicIP server (/server/reload and /api/mix)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class FakeMusicIP:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.reset()

    def reset(self):
        self.requests = []
        self.mixes = {}
        self.reload_status = 200
        self.mix_status = 200
        self.failing_seeds = set()  # seeds MusicIP answers with HTTP 500
        self.mix_body = None
        self.encoding = "utf-8"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def set_mix(self, seed, tracks):
        self.mixes[seed] = list(tracks)

    def mix_requests(self):
        return [query for path, query in self.requests if path == "/api/mix"]

    def reload_count(self):
        return sum(1 for path, _query in self.requests if path == "/server/reload")

    def _handler_class(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlsplit(self.path)
                # main.py percent-encodes the seed song as cp1252, like MusicIP on Windows expects.
                query = {key: values[0] for key, values in parse_qs(parts.query, encoding="cp1252").items()}
                fake.requests.append((parts.path, query))

                if parts.path == "/server/reload":
                    self.reply(fake.reload_status, b"")
                elif parts.path == "/api/mix":
                    if fake.mix_body is not None:
                        body = fake.mix_body
                    else:
                        tracks = fake.mixes.get(query.get("song", ""), [])
                        body = "\n".join(tracks).encode(fake.encoding)
                    status = 500 if query.get("song", "") in fake.failing_seeds else fake.mix_status
                    self.reply(status, body if status == 200 else b"server error")
                else:
                    self.reply(404, b"not found")

            def reply(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        return Handler
