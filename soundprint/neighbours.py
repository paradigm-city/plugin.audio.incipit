"""The nearest songs to a seed by sound: cosine of the stored vectors, highest first.

A seed that isn't in the store yet (a new song) is analysed on the spot when the model is at hand, and stored.

For a mix, three rules on top of the order by sound (all optional):
- no artist repeat within `window` songs, as MusicIP's reject size: the seed is the mix's first song, and a song
  whose artist is among the last `window` songs is passed over (an album's songs are often each other's nearest);
  artists are compared as AI Mix Assist compares them (mixassist.cache.artist_key);
- the same song twice (the same artist and title on another album, or a copy) only once, and never the seed's;
- variety: instead of always the same nearest songs, a random choice from the nearest (1 + variety / 3) times as
  many, kept in their order (variety 0 to 9, as MusicIP's setting): each song in turn is taken with the chance
  count / that many, before the artist rule, so the spacing holds in the mix as it is.
"""

from __future__ import annotations

import os
import random
from typing import Callable, List, Optional, Tuple

import numpy as np

from mixassist.cache import artist_key
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
            details: Optional[Lookup] = None, window: int = 0, variety: int = 0,
            rng: Optional[random.Random] = None) -> Tuple[List[Tuple[str, float]], str, dict]:
    """Up to count (path, similarity) pairs in the mix's order, the seed itself left out; where the seed's vector
    came from; and how many songs each rule left out ("artist", "same_song")."""
    left_out = {"artist": 0, "same_song": 0}
    vector, source = seed_vector(store, seed, model_folder, snippets)
    if vector is None:
        return [], source, left_out
    paths, matrix = store.matrix()
    if not paths:
        return [], source, left_out
    vector = vector / (np.linalg.norm(vector) + 1e-9)
    similarity = np.asarray(matrix @ vector)
    chance = count / pool_size(count, variety)
    if details is None and not window and chance >= 1:
        take = min(len(paths), count + 1)
        order = np.argpartition(-similarity, take - 1)[:take]
        order = order[np.argsort(-similarity[order])]
    else:
        order = np.argsort(-similarity)  # the rules may pass over many songs
    draw = (rng or random).random
    seed_details = details(seed) if details else ("", "")
    seen_songs = {song_key(seed_details)} if seed_details[1] else set()
    recent = [artist_key(seed_details[0])]  # the mix's artists so far, the seed first
    mix: List[Tuple[str, float]] = []
    for index in order:
        path = paths[index]
        if path == seed:
            continue
        artist, title = details(path) if details else ("", "")
        key = song_key((artist, title))
        if title and key in seen_songs:
            left_out["same_song"] += 1
            continue
        if chance < 1 and draw() >= chance:
            continue  # variety: not this one
        name = artist_key(artist)
        if window and name and name in recent[-window:]:
            left_out["artist"] += 1
            continue
        if title:
            seen_songs.add(key)
        recent.append(name)
        mix.append((path, float(similarity[index])))
        if len(mix) >= count:
            break
    return mix, source, left_out
