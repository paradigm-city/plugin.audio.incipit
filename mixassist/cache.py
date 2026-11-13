"""The rating cache: one style vector per unit (album, or a track from a compilation), stored in SQLite.

Units are keyed by MusicBrainz ID where the files have one (release group for albums, recording for tracks),
otherwise by normalized artist and title. Every entry records the prompt version it was rated with; entries of
another version are ignored and rated again when next needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata
from typing import Dict, Iterable, List, Optional

from mixassist.dimensions import ALL_KEYS, build_system_prompt

SCHEMA = """
CREATE TABLE IF NOT EXISTS units (
    key TEXT PRIMARY KEY,
    prompt_version TEXT NOT NULL,
    kind TEXT NOT NULL,
    vector TEXT NOT NULL,
    familiarity INTEGER NOT NULL,
    description TEXT NOT NULL,
    model TEXT NOT NULL,
    source TEXT NOT NULL,
    rated_ts INTEGER NOT NULL
)
"""

# Compilation albums: flagged, "Various Artists", or more distinct track artists than this.
VARIOUS_ARTISTS = {"various artists", "various", "va", "v.a.", "diverse"}
COMPILATION_ARTIST_LIMIT = 8

# Letters that Unicode does not decompose into a base letter plus accent.
TRANSLITERATION = str.maketrans({"æ": "ae", "ø": "o", "œ": "oe", "ð": "d", "đ": "d", "ł": "l", "þ": "th"})


def prompt_version(prompt: str = "") -> str:
    """Fingerprint of the rating prompt."""
    return hashlib.sha1((prompt or build_system_prompt()).encode("utf-8")).hexdigest()[:12]


def normalize(text: str) -> str:
    """Lower case, accents removed, punctuation and repeated spaces collapsed."""
    decomposed = unicodedata.normalize("NFKD", (text or "").casefold().translate(TRANSLITERATION))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", " ", plain).strip()


def artist_key(artist: str) -> str:
    """Artist names compared loosely: "Medeski Martin & Wood" and "Medeski, Martin and Wood" are the same. One rule
    for "the same artist" everywhere: AI Mix Assist's artist spacing and the sound engine's."""
    return " ".join(word for word in normalize(artist).split() if word not in ("and", "the"))


def album_key(artist: str, title: str, release_group_mbid: str = "") -> str:
    if release_group_mbid:
        return f"rg:{release_group_mbid}"
    return f"album:{normalize(artist)}|{normalize(title)}"


def track_key(artist: str, title: str, recording_mbid: str = "") -> str:
    if recording_mbid:
        return f"rec:{recording_mbid}"
    return f"track:{normalize(artist)}|{normalize(title)}"


def is_compilation(flag: bool, album_artist: str, distinct_track_artists: int) -> bool:
    return (bool(flag) or (album_artist or "").strip().lower() in VARIOUS_ARTISTS
            or distinct_track_artists > COMPILATION_ARTIST_LIMIT)


def kind_of_key(key: str) -> str:
    return "album" if key.startswith(("rg:", "album:")) else "track"


VERDICT_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    key TEXT PRIMARY KEY,
    verdict TEXT NOT NULL,
    reason TEXT NOT NULL,
    stored_ts INTEGER NOT NULL
)
"""

VERDICT_KEEP_DAYS = 365


class VerdictCache:
    """The intent check's verdicts, kept by a fingerprint of everything the verdict depends on (roadmap I41): the
    model and effort that judged (tag), the intent check's prompt (with its perspective), the intent's text, the
    seed's line and the track's line (its description from the rating, year and "little known" mark included). Any
    change to one of them asks the AI again. Shares the rating cache's database file."""

    def __init__(self, connection: sqlite3.Connection, tag: str):
        self.connection = connection
        self.tag = tag
        self.connection.execute(VERDICT_SCHEMA)
        self.connection.execute("DELETE FROM verdicts WHERE stored_ts < ?",
                                (int(time.time()) - VERDICT_KEEP_DAYS * 86400,))
        self.connection.commit()

    def key(self, prompt: str, intent: str, seed_line: str, track_line: str) -> str:
        return hashlib.sha1("\0".join((self.tag, prompt, intent.strip(), seed_line, track_line)).encode("utf-8")
                            ).hexdigest()

    def get_many(self, keys: Iterable[str]) -> Dict[str, dict]:
        wanted = list(dict.fromkeys(keys))
        found: Dict[str, dict] = {}
        for start in range(0, len(wanted), 500):
            chunk = wanted[start:start + 500]
            rows = self.connection.execute(
                f"SELECT key, verdict, reason FROM verdicts WHERE key IN ({','.join('?' * len(chunk))})", chunk
            ).fetchall()
            for key, verdict, reason in rows:
                found[key] = {"verdict": verdict, "reason": reason}
        return found

    def put_many(self, verdicts: Dict[str, dict]) -> None:
        now = int(time.time())
        self.connection.executemany(
            "INSERT OR REPLACE INTO verdicts VALUES (?, ?, ?, ?)",
            [(key, str(value.get("verdict", "")), str(value.get("reason", "")), now)
             for key, value in verdicts.items() if value.get("verdict")])
        self.connection.commit()

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]


class RatingCache:
    """model: only ratings by this model count (a rating from another model is rated again when needed, so two
    models' ratings never share one property space); "" takes any. verdict_tag (the checks' model and effort): also
    keep the intent check's verdicts (self.verdicts); without it self.verdicts is None and nothing is kept."""

    def __init__(self, path: str, version: str = "", model: str = "", verdict_tag: str = ""):
        self.path = path
        self.version = version or prompt_version()
        self.model = model
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute(SCHEMA)
        self.connection.commit()
        self.verdicts = VerdictCache(self.connection, verdict_tag) if verdict_tag else None

    def close(self) -> None:
        self.connection.close()

    def where(self) -> tuple:
        """The condition for entries that count: the current prompt (and model, when one is set)."""
        if self.model:
            return "prompt_version = ? AND model = ?", [self.version, self.model]
        return "prompt_version = ?", [self.version]

    def get(self, key: str) -> Optional[dict]:
        return self.get_many([key]).get(key)

    def get_many(self, keys: Iterable[str]) -> Dict[str, dict]:
        wanted = list(dict.fromkeys(keys))
        found: Dict[str, dict] = {}
        condition, values = self.where()
        for start in range(0, len(wanted), 500):
            chunk = wanted[start:start + 500]
            rows = self.connection.execute(
                f"SELECT key, vector, familiarity, description FROM units "
                f"WHERE {condition} AND key IN ({','.join('?' * len(chunk))})",
                values + chunk,
            ).fetchall()
            for key, vector, familiarity, description in rows:
                entry = json.loads(vector)
                entry.update(familiarity=familiarity, description=description)
                found[key] = entry
        return found

    def put(self, key: str, rating: dict, model: str, source: str, kind: str = "", commit: bool = True) -> None:
        vector = {name: rating[name] for name in ALL_KEYS}
        self.connection.execute(
            "INSERT OR REPLACE INTO units VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (key, self.version, kind or kind_of_key(key), json.dumps(vector), int(rating.get("familiarity") or 0),
             str(rating.get("description") or rating.get("character") or ""), model, source, int(time.time())),
        )
        if commit:
            self.connection.commit()

    def library(self, kind: str = "album") -> List[dict]:
        """All vectors of one kind rated with the current prompt (and model): the library reference."""
        condition, values = self.where()
        rows = self.connection.execute(
            f"SELECT vector FROM units WHERE {condition} AND kind = ?", values + [kind]).fetchall()
        return [json.loads(vector) for (vector,) in rows]

    def count(self) -> int:
        condition, values = self.where()
        return self.connection.execute(f"SELECT COUNT(*) FROM units WHERE {condition}", values).fetchone()[0]

    def import_pilot(self, path: str) -> int:
        """Take over the pilot's JSON cache (tools/style_pilot/data/rating_cache.json): entries rated with the
        current prompt and not cached yet. Returns how many were added."""
        with open(path, encoding="utf-8") as handle:
            units = json.load(handle).get("units", {})
        existing = set(self.get_many(units))
        added = 0
        for key, entry in units.items():
            if entry.get("prompt_version") != self.version or key in existing:
                continue
            if any(name not in entry for name in ALL_KEYS):
                continue
            self.put(key, entry, model=str(entry.get("model", "")), source="pilot", commit=False)
            added += 1
        self.connection.commit()
        return added
