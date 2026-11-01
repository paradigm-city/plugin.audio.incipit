"""The nearest songs to a seed by sound: cosine of the stored vectors, highest first.

A seed that isn't in the store yet (a new song) is analysed on the spot when the model is at hand, and stored.

Songs listed by the caller (a station's played, queued and turned-down songs) are left out before anything is chosen,
so a station's next mix comes from the nearest songs it hasn't had yet; ranks stay those of the whole order by sound.

For a mix, three rules on top of the order by sound (all optional):
- no artist repeat within `window` songs, as MusicIP's reject size: the seed is the mix's first song, and a song
  whose artist is among the last `window` songs is passed over (an album's songs are often each other's nearest);
  artists are compared as AI Mix Assist compares them (mixassist.cache.artist_key);
- the same song twice (the same artist and title on another album, or a copy) only once, and never the seed's;
- variety (0 to 9, as MusicIP's setting): how far into the order by sound a mix reaches, and how random it is.
  A mix chooses from the nearest `reach` songs: at 0 half as many again as it holds (TIGHTEST_REACH), so it still
  varies from one time to the next, then each step the same factor deeper, up to the whole library at 9 (a measure,
  such as Character's scale, asks for the nearest songs in order instead: in_order). Each song of the mix in turn is
  drawn at random from those not drawn yet, the nearer the likelier: the song at rank r with a weight of
  1 / r ** power, where power goes from 1 at variety 0 to 0.7 at 9 (draw_power). With 1, the songs spread evenly
  from near to far (about as many from ranks 2 to 4 as from 1,000 to 2,000); below 1, the far songs get more. Near
  and far songs alternate in the mix (at 0, a mix of 75 draws from the nearest 112: still close, seldom the same).
  The draws come before the artist rule, so the spacing holds in the mix as it is; when the rules pass over all of
  them, the mix goes on with the songs further out, nearest first.

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
from typing import Callable, Iterable, List, Optional, Tuple

import numpy as np

from mixassist.cache import artist_key
from soundprint import DEFAULT_SNIPPETS, analysis_version
from soundprint.store import Store

Lookup = Callable[[str], Tuple[str, str]]  # path -> (artist, title)
LOOSEST_POWER = 0.7  # the draw weight's power at variety 9
TIGHTEST_REACH = 1.5  # at variety 0 a mix draws from this many times its size (variety 1: about 2.3 to 2.7 times)


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


def identity(path: str) -> str:
    """A song's path as the add-on compares a station's songs (main.normalize_track_identity)."""
    return (path or "").replace("\\", "/").strip()


def reach(count: int, variety: int, songs: int) -> int:
    """How deep into the order by sound a mix of count songs reaches: TIGHTEST_REACH times count at variety 0, all
    songs at 9, the same factor deeper with each step (never less than at 0)."""
    count = max(1, count)
    top = max(count, songs)
    return min(top, max(round(count * TIGHTEST_REACH), round(count * (top / count) ** (max(0, min(9, variety)) / 9))))


def draw_power(variety: int) -> float:
    """The power in the draw weight 1 / rank ** power: 1 at variety 0, LOOSEST_POWER at 9, evenly between."""
    return 1 - (1 - LOOSEST_POWER) * max(0, min(9, variety)) / 9


def nearest(store: Store, seed: str, count: int, model_folder: str = "", snippets: int = DEFAULT_SNIPPETS,
            details: Optional[Lookup] = None, window: int = 0, variety: int = 0,
            rng: Optional[random.Random] = None, leave_out: Iterable[str] = (), in_order: bool = False
            ) -> Tuple[List[Tuple[str, float, int]], str, dict]:
    """Up to count (path, similarity, rank) triples in the mix's order, the seed itself left out (rank 1 is the
    nearest song); where the seed's vector came from; and how many songs each rule left out ("artist",
    "same_song"), and how many of the songs in leave_out (paths) the store has ("listed"). in_order: the nearest
    songs, nearest first, without a draw."""
    left_out = {"artist": 0, "same_song": 0, "listed": 0}
    vector, source = seed_vector(store, seed, model_folder, snippets)
    if vector is None:
        return [], source, left_out
    paths, matrix = store.matrix()
    if not paths:
        return [], source, left_out
    vector = vector / (np.linalg.norm(vector) + 1e-9)
    similarity = np.asarray(matrix @ vector)
    variety = max(0, min(9, variety))
    listed = {identity(path) for path in leave_out}
    leave = np.array([index for index, path in enumerate(paths) if identity(path) in listed], dtype=np.int64) \
        if listed else np.empty(0, dtype=np.int64)
    left_out["listed"] = int(len(leave))
    if details is None and not window and in_order:
        take = min(len(paths), count + 1 + len(leave))
        order = np.argpartition(-similarity, take - 1)[:take]
        order = order[np.argsort(-similarity[order])]
    else:
        order = np.argsort(-similarity)  # the rules may pass over many songs
    if seed in paths:
        order = order[order != paths.index(seed)]
    ranks = np.arange(1, len(order) + 1)  # in the whole order by sound
    if len(leave):
        keep = ~np.isin(order, leave)
        order, ranks = order[keep], ranks[keep]
    positions = np.arange(len(order))  # among the songs left to choose from
    if not in_order:
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
        mix.append((path, float(similarity[index]), int(ranks[position])))
        if len(mix) >= count:
            break
    return mix, source, left_out
