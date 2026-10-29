"""A stand-in for the sound engine's mixes (soundprint.client.neighbours), answering from mixes set by the test."""

from __future__ import annotations


class FakeSource:
    def __init__(self):
        self.reset()

    def reset(self):
        self.requests = []
        self.mixes = {}
        self.mix_status = 200  # anything else: the sound engine fails
        self.failing_seeds = set()  # seeds the sound engine fails for

    def set_mix(self, seed, tracks):
        self.mixes[seed] = list(tracks)

    def mix_requests(self):
        """Every mix asked for, as {"song", "size", "rejectsize", "variety"} (numbers as text)."""
        return list(self.requests)

    def neighbours(self, data, userdata, seed, count, window=0, variety=0, runner=None):
        from soundprint import client  # importable once the add-on's folder is on the path (support.py)

        self.requests.append({"song": seed, "size": str(count), "rejectsize": str(window), "variety": str(variety)})
        if self.mix_status != 200 or seed in self.failing_seeds:
            raise client.SoundprintError(client.FAILED, "The sound engine failed: server error")
        tracks = self.mixes.get(seed, [])[:count]
        if not tracks:
            raise client.SoundprintError(client.NOT_ANALYSED, "The sound engine found no songs (stored; 1000 song(s) "
                                                               "analysed).")
        return {"seed": seed, "seed_vector": "stored", "seed_details": ["", ""], "analysed": 1000,
                "left_out": {"artist": 0, "same_song": 0}, "reach": count, "seconds": 0.1,
                "songs": [{"path": path, "similarity": 0.9, "rank": number, "artist": "", "title": ""}
                          for number, path in enumerate(tracks, start=1)]}
