"""The nearest songs to a seed by sound: cosine of the stored vectors, highest first.

A seed that isn't in the store yet (a new song) is analysed on the spot when the model is at hand, and stored.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import numpy as np

from soundprint import DEFAULT_SNIPPETS, analysis_version
from soundprint.store import Store


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


def nearest(store: Store, seed: str, count: int, model_folder: str = "",
            snippets: int = DEFAULT_SNIPPETS) -> Tuple[List[Tuple[str, float]], str]:
    """Up to count (path, similarity) pairs, the seed itself left out, and where the seed's vector came from."""
    vector, source = seed_vector(store, seed, model_folder, snippets)
    if vector is None:
        return [], source
    paths, matrix = store.matrix()
    if not paths:
        return [], source
    vector = vector / (np.linalg.norm(vector) + 1e-9)
    similarity = np.asarray(matrix @ vector)
    take = min(len(paths), count + 1)
    top = np.argpartition(-similarity, take - 1)[:take]
    top = top[np.argsort(-similarity[top])]
    found = [(paths[index], float(similarity[index])) for index in top if paths[index] != seed]
    return found[:count], source
