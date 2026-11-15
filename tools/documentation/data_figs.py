"""Compute the data behind the signal-processing figures, with the sound engine's own code (run with its Python).
Writes figdata.npz into the scratchpad. Read-only on the add-on's data."""
import json
import os
import sys

import numpy as np

ADDON = sys.argv[1]
DATA = sys.argv[2]
OUT = sys.argv[3]
sys.path.insert(0, ADDON)

from soundprint import audio, model, neighbours  # noqa: E402

with open(os.path.join(DATA, "vectors.json"), encoding="utf-8") as h:
    paths = json.load(h)["paths"]
matrix = np.load(os.path.join(DATA, "vectors.npy"), mmap_mode="r")
seed = next(p for p in paths if "kraftwerk" in p.lower() and "vitamin" in p.lower())
print("seed", seed, len(paths))
row = paths.index(seed)
vec = np.asarray(matrix[row], dtype=np.float32)
sim = np.asarray(matrix @ vec)
order = np.sort(sim)[::-1][1:]  # without the seed

# a snippet of the seed: its third window
length = audio.length_of(seed)
starts = audio.snippet_starts(length, 6)
win = audio.pad(audio.decode(seed, starts[2], 10.0))
mel = model.mel_db(win)[0, 0]
reaches = {v: neighbours.reach(25, v, len(paths) - 1) for v in range(10)}
powers = {v: neighbours.draw_power(v) for v in range(10)}
print("reaches", reaches)
print("starts", starts, "length", length)
print("mel", mel.shape, mel.min(), mel.max())
print("sim stats", order[:5], order[1000], order[20000], order[-1])
np.savez_compressed(OUT, sim=order.astype(np.float32), mel=mel.astype(np.float32), filters=model.FILTERS,
                    wave=win[::10].astype(np.float32), starts=np.array(starts), length=np.array(length),
                    reaches=np.array([reaches[v] for v in range(10)]), powers=np.array([powers[v] for v in range(10)]),
                    hist=np.histogram(order, bins=120, range=(-0.2, 1.0))[0])
