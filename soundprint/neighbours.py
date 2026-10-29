"""The nearest songs to a seed by sound: cosine of the stored vectors, highest first.

A seed that isn't in the store yet (a new song) is analysed on the spot when the model is at hand, and stored.

For a mix, three rules on top of the order by sound (all optional):
- no artist repeat within `window` songs, as MusicIP's reject size: the seed is the mix's first song, and a song
  whose artist is among the last `window` songs is passed over (an album's songs are often each other's nearest);
  artists are compared as AI Mix Assist compares them (mixassist.cache.artist_key);
- the same song twice (the same artist and title on another album, or a copy) only once, and never the seed's;
- variety (0 to 9, as MusicIP's setting): how far into the order by sound a mix reaches, and how random it is.
  0 takes the nearest songs, nearest first. Above 0, a mix chooses from the nearest `reach` songs, each step the same
  factor deeper, up to the whole library at 9. Each song of the mix in turn is drawn at random from those not drawn
  yet, the nearer the likelier: the song at rank r with a weight of 1 / r ** power, where power goes from 1 at
  variety 0 to 0.7 at 9 (draw_power). With 1, the songs spread evenly from near to far (about as many from ranks 2
  to 4 as from 1,000 to 2,000); below 1, the far songs get more. Near and far songs alternate in the mix. The draws
  come before the artist rule, so the spacing holds in the mix as it is; when the rules pass over all of them, the
  mix goes on with the songs further out, nearest first.

Measured on the whole library on 2026-10-29 (153k songs; tools/style_pilot/data/variety_2026-10-29). Genre folders
change from the first songs on (9 to 12 folders among the nearest 100), but for Kraftwerk "Vitamin" the rock and
metal folders sit at ranks 34,000 to 100,000 (folder_ranks_kraftwerk.txt): a mix that only reached the nearest
20,000 with weight 1 / r brought chill, lounge and jazz, hardly any rock (the user's ears; 3% in shape_options.txt).
At 9 now: about 5% of the songs within rank 30, half beyond rank 20,000, rock and metal 18% for Kraftwerk; about 29%
of them fit the seed's profile, against 54% before. The consistency of such a loose mix is then up to AI Mix Assist
(its profile and perspective); in random order it gets far songs among the first candidates, not only near ones.
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
LOOSEST_POWER = 0.7  # the draw weight's power at variety 9


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


def reach(count: int, variety: int, songs: int) -> int:
    """How deep into the order by sound a mix of count songs reaches: count at variety 0, all songs at 9, the same
    factor deeper with each step."""
    count = max(1, count)
    top = max(count, songs)
    return round(count * (top / count) ** (max(0, min(9, variety)) / 9))


def draw_power(variety: int) -> float:
    """The power in the draw weight 1 / rank ** power: 1 at variety 0, LOOSEST_POWER at 9, evenly between."""
    return 1 - (1 - LOOSEST_POWER) * max(0, min(9, variety)) / 9


def nearest(store: Store, seed: str, count: int, model_folder: str = "", snippets: int = DEFAULT_SNIPPETS,
            details: Optional[Lookup] = None, window: int = 0, variety: int = 0,
            rng: Optional[random.Random] = None) -> Tuple[List[Tuple[str, float, int]], str, dict]:
    """Up to count (path, similarity, rank) triples in the mix's order, the seed itself left out (rank 1 is the
    nearest song); where the seed's vector came from; and how many songs each rule left out ("artist",
    "same_song")."""
    left_out = {"artist": 0, "same_song": 0}
    vector, source = seed_vector(store, seed, model_folder, snippets)
    if vector is None:
        return [], source, left_out
    paths, matrix = store.matrix()
    if not paths:
        return [], source, left_out
    vector = vector / (np.linalg.norm(vector) + 1e-9)
    similarity = np.asarray(matrix @ vector)
    variety = max(0, min(9, variety))
    if details is None and not window and not variety:
        take = min(len(paths), count + 1)
        order = np.argpartition(-similarity, take - 1)[:take]
        order = order[np.argsort(-similarity[order])]
    else:
        order = np.argsort(-similarity)  # the rules may pass over many songs
    if seed in paths:
        order = order[order != paths.index(seed)]
    positions = np.arange(len(order))  # rank - 1
    if variety:
        depth = min(len(order), reach(count, variety, len(order)))
        # weighted draws without replacement (Efraimidis and Spirakis): the key u ** (1 / weight), here r ** power * ln u
        draws = np.random.default_rng((rng or random).getrandbits(64)).random(depth)
        keys = (positions[:depth] + 1.0) ** draw_power(variety) * np.log(1 - draws)
        positions = np.concatenate([np.argsort(-keys, kind="stable"), positions[depth:]])
    seed_details = details(seed) if details else ("", "")
    seen_songs = {song_key(seed_details)} if seed_details[1] else set()
    recent = [artist_key(seed_details[0])]  # the mix's artists so far, the seed first
    mix: List[Tuple[str, float, int]] = []
    for position in positions:
        index = order[position]
        path = paths[index]
        artist, title = details(path) if details else ("", "")
        key = song_key((artist, title))
        if title and key in seen_songs:
            left_out["same_song"] += 1
            continue
        name = artist_key(artist)
        if window and name and name in recent[-window:]:
            left_out["artist"] += 1
            continue
        if title:
            seen_songs.add(key)
        recent.append(name)
        mix.append((path, float(similarity[index]), int(position) + 1))
        if len(mix) >= count:
            break
    return mix, source, left_out
