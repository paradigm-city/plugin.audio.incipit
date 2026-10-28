"""The nearest songs to a seed by sound: cosine of the stored vectors, highest first.

A seed that isn't in the store yet (a new song) is analysed on the spot when the model is at hand, and stored.

For a mix, three rules on top of the order by sound (all optional):
- at most per_artist songs of one artist, the seed counted (an album's songs are often each other's nearest);
- the same song twice (the same artist and title on another album, or a copy) only once, and never the seed's;
- variety: instead of always the same nearest songs, a random choice from the nearest (1 + variety / 3) times as
  many, kept in their order (variety 0 to 9, as MusicIP's setting).
"""

from __future__ import annotations

import os
import random
from typing import Callable, List, Optional, Tuple

import numpy as np

from soundprint import DEFAULT_SNIPPETS, analysis_version
from soundprint.store import Store

Lookup = Callable[[str], Tuple[str, str]]  # path -> (artist, title)


def seed_vector(store: Store, seed: str, model_folder: str = "", snippets: int = DEFAULT_SNIPPETS
                ) -> Tuple[Optional[np.ndarray], str]:
    """The seed's vector and where it came from: "stored", "analysed" (just now), or why there is none."""
    vector = store.vector(seed)
    if vector is not None:
        return vector, "stored"
    if not model_folder or not os.path.isfile(seed):
        return None, "not analysed" if os.path.isfile(seed) else "not a local file"
    from soundprint import audio
    from soundprint.model import Model

    info = os.stat(seed)
    windows, length, _how = audio.snippets(seed, snippets)
    vector = Model(model_folder, threads=2).embed(windows)
    store.put(seed, info.st_size, info.st_mtime, analysis_version(snippets), length, vector)
    store.commit()
    return vector, "analysed"


def song_key(details: Tuple[str, str]) -> Tuple[str, str]:
    return details[0].strip().casefold(), details[1].strip().casefold()


def pool_size(count: int, variety: int) -> int:
    return count + (count * max(0, min(9, variety)) + 2) // 3


def nearest(store: Store, seed: str, count: int, model_folder: str = "", snippets: int = DEFAULT_SNIPPETS,
            details: Optional[Lookup] = None, per_artist: int = 0, variety: int = 0,
            rng: Optional[random.Random] = None) -> Tuple[List[Tuple[str, float]], str, dict]:
    """Up to count (path, similarity) pairs, the seed itself left out; where the seed's vector came from; and how
    many songs each rule left out ("artist", "same_song")."""
    left_out = {"artist": 0, "same_song": 0}
    vector, source = seed_vector(store, seed, model_folder, snippets)
    if vector is None:
        return [], source, left_out
    paths, matrix = store.matrix()
    if not paths:
        return [], source, left_out
    vector = vector / (np.linalg.norm(vector) + 1e-9)
    similarity = np.asarray(matrix @ vector)
    wanted = pool_size(count, variety)
    if details is None and not per_artist:
        take = min(len(paths), wanted + 1)
        order = np.argpartition(-similarity, take - 1)[:take]
        order = order[np.argsort(-similarity[order])]
    else:
        order = np.argsort(-similarity)  # the rules may pass over many songs
    seed_details = details(seed) if details else ("", "")
    seen_songs = {song_key(seed_details)} if seed_details[1] else set()
    artists = {seed_details[0].strip().casefold(): 1} if seed_details[0] else {}  # the seed is in the mix too
    pool: List[Tuple[str, float]] = []
    for index in order:
        path = paths[index]
        if path == seed:
            continue
        if details:
            artist, title = details(path)
            key = song_key((artist, title))
            if title and key in seen_songs:
                left_out["same_song"] += 1
                continue
            if per_artist and artist:
                name = artist.strip().casefold()
                if artists.get(name, 0) >= per_artist:
                    left_out["artist"] += 1
                    continue
                artists[name] = artists.get(name, 0) + 1
            if title:
                seen_songs.add(key)
        pool.append((path, float(similarity[index])))
        if len(pool) >= wanted:
            break
    if len(pool) > count:
        chosen = sorted((rng or random).sample(range(len(pool)), count))
        pool = [pool[index] for index in chosen]
    return pool, source, left_out
