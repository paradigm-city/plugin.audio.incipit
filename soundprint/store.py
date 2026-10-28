"""The sound print store: one row per song file, in SQLite (sound.db in the data folder).

A row holds the vector (512 float16, 1 KB) or the reason the file could not be read, the file's size and change
time when it was analysed, and the analysis version. A song is analysed again when its file changed or the
version differs; a failed file only when it changed. For the nearest-neighbour search, all vectors are kept in a
second file as one matrix (vectors.npy plus vectors.json with the paths), rebuilt when the store has changed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    version TEXT NOT NULL,
    length REAL,
    vector BLOB,
    error TEXT,
    analysed REAL NOT NULL
)
"""
DIMENSIONS = 512


class Store:
    def __init__(self, folder: str):
        os.makedirs(folder, exist_ok=True)
        self.folder = folder
        self.db = sqlite3.connect(os.path.join(folder, "sound.db"))
        self.db.execute(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def known(self) -> Dict[str, Tuple[int, float, str, bool]]:
        """path -> (size, mtime, version, failed)."""
        return {path: (size, mtime, version, bool(failed))
                for path, size, mtime, version, failed in self.db.execute(
                    "SELECT path, size, mtime, version, vector IS NULL FROM songs")}

    def put(self, path: str, size: int, mtime: float, version: str, length: float,
            vector: Optional[np.ndarray], error: str = "") -> None:
        blob = vector.astype(np.float16).tobytes() if vector is not None else None
        self.db.execute("INSERT OR REPLACE INTO songs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (path, size, mtime, version, length, blob, error or None, time.time()))

    def commit(self) -> None:
        self.db.commit()

    def remove(self, paths: Iterable[str]) -> int:
        paths = list(paths)
        self.db.executemany("DELETE FROM songs WHERE path = ?", [(path,) for path in paths])
        self.db.commit()
        return len(paths)

    def vector(self, path: str) -> Optional[np.ndarray]:
        row = self.db.execute("SELECT vector FROM songs WHERE path = ? AND vector IS NOT NULL", (path,)).fetchone()
        return np.frombuffer(row[0], dtype=np.float16).astype(np.float32) if row else None

    def counts(self) -> Dict[str, int]:
        analysed, failed = self.db.execute(
            "SELECT COUNT(vector), COUNT(*) - COUNT(vector) FROM songs").fetchone()
        return {"analysed": analysed, "failed": failed}

    def failures(self) -> List[Tuple[str, str]]:
        return list(self.db.execute("SELECT path, error FROM songs WHERE vector IS NULL ORDER BY path"))

    def last_change(self) -> float:
        return self.db.execute("SELECT COALESCE(MAX(analysed), 0) FROM songs").fetchone()[0]

    # --- The matrix for the search ---------------------------------------------------------------------------------
    # While an analysis runs, the store changes every few seconds; reading all of it for every search took 1.3 s
    # at 10,000 songs (2026-10-28). So the saved matrix is used with only the rows stored since it was written,
    # and written anew once those are many.
    REWRITE_AFTER = 2000  # newer rows

    def rows(self, where: str = "", args: tuple = ()) -> Tuple[List[str], np.ndarray]:
        paths, blobs = [], []
        for path, blob in self.db.execute(
                f"SELECT path, vector FROM songs WHERE vector IS NOT NULL {where} ORDER BY path", args):
            paths.append(path)
            blobs.append(blob)
        vectors = (np.frombuffer(b"".join(blobs), dtype=np.float16).reshape(-1, DIMENSIONS).astype(np.float32)
                   if blobs else np.zeros((0, DIMENSIONS), np.float32))
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
        return paths, vectors

    def matrix(self) -> Tuple[List[str], np.ndarray]:
        """All analysed paths and their vectors (float32, normalised, one row each)."""
        npy, names = os.path.join(self.folder, "vectors.npy"), os.path.join(self.folder, "vectors.json")
        stamp = {"last_change": self.last_change(), "rows": self.counts()["analysed"]}
        saved = {}
        if os.path.isfile(npy) and os.path.isfile(names):
            with open(names, encoding="utf-8") as handle:
                saved = json.load(handle)
            if saved.get("stamp") == stamp:
                return saved["paths"], np.load(npy, mmap_mode="r")
        if saved.get("stamp"):
            newer_paths, newer = self.rows("AND analysed > ?", (saved["stamp"]["last_change"],))
            if len(newer_paths) < self.REWRITE_AFTER:
                again = set(newer_paths)  # analysed again since: the newer vector counts
                kept = [index for index, path in enumerate(saved["paths"]) if path not in again]
                if len(kept) + len(newer_paths) == stamp["rows"]:  # else songs were removed or failed since
                    matrix = np.load(npy, mmap_mode="r")
                    old = matrix if len(kept) == len(saved["paths"]) else matrix[kept]
                    return [saved["paths"][index] for index in kept] + newer_paths, np.concatenate([old, newer])
        paths, vectors = self.rows()
        np.save(npy + ".part.npy", vectors)
        os.replace(npy + ".part.npy", npy)
        with open(names + ".part", "w", encoding="utf-8") as handle:
            json.dump({"stamp": stamp, "paths": paths}, handle)
        os.replace(names + ".part", names)
        return paths, vectors
