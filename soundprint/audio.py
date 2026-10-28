"""Decoding: mono 48 kHz snippets from any file FFmpeg reads (PyAV).

The model was trained on audio as librosa loads it: 48 kHz, the mean of all channels, clipped and rounded to
16 bits. Two things matter for snippets (measured 2026-10-27, docs/concept_suggestion_engine.md):
- the first frames after a seek are garbled (an MP3's bit reservoir, the resampler starting up), and the model
  weighs a window's first 50 ms heavily: such a glitch alone gives a cosine of 0.73 to the clean window. So each
  snippet is decoded from 1 s earlier and that second is dropped;
- hard cuts are fine: a 10 ms fade in and out changes nothing.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from soundprint import PREROLL_SECONDS

RATE = 48000
WINDOW = 10 * RATE  # 10 s, as the model was trained
SILENCE_RMS = 1e-4  # about -80 dBFS: a window this quiet says nothing about the song


def prepare(audio: np.ndarray) -> np.ndarray:
    """As the model's training data: clipped and rounded to 16 bits."""
    return (np.clip(audio, -1, 1) * 32767.0).astype(np.int16).astype(np.float32) / 32767.0


def length_of(path: str) -> float:
    """The song's length in seconds as the file states it (0.0 if it doesn't)."""
    import av

    with av.open(path) as container:
        return float(container.duration) / av.time_base if container.duration else 0.0


def decode(path: str, start: float = 0.0, seconds: float = 0.0) -> np.ndarray:
    """Mono float audio at 48 kHz from start (s) for seconds (0: to the end)."""
    import av

    with av.open(path) as container:
        stream = container.streams.audio[0]
        if start > 0:
            container.seek(int(max(0.0, start - PREROLL_SECONDS) * av.time_base), any_frame=False)
        # packed samples, averaged over all channels below; PyAV's planar to_ndarray fails on 8 channels
        resampler = av.audio.resampler.AudioResampler(format="flt", layout=stream.layout, rate=RATE)
        channels = stream.layout.nb_channels
        wanted = int(seconds * RATE) if seconds else 0
        chunks: List[np.ndarray] = []
        total, skip = 0, None
        for packet in container.demux(stream):
            try:
                frames = packet.decode()
            except av.error.InvalidDataError:  # a damaged frame (some MP3s): leave it out, as librosa's decoder does
                continue
            for frame in frames:
                if skip is None:  # the seek lands on a frame boundary before start
                    at = float(frame.pts * frame.time_base) if frame.pts is not None else start
                    skip = max(0, int(round((start - at) * RATE)))
                for out in resampler.resample(frame):
                    samples = out.to_ndarray().reshape(-1, channels).mean(axis=1)
                    if skip:
                        cut = min(skip, samples.size)
                        samples, skip = samples[cut:], skip - cut
                    chunks.append(samples.astype(np.float32))
                    total += samples.size
            if wanted and total >= wanted:
                break
    audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
    return prepare(audio[:wanted] if wanted else audio)


def snippet_starts(length: float, count: int) -> List[float]:
    """Where the snippets begin (s): centred at (i + 0.5) / count of the song, inside the song."""
    longest = max(0.0, length - WINDOW / RATE)
    return [min(max(0.0, (index + 0.5) / count * length - WINDOW / RATE / 2), longest) for index in range(count)]


def pad(audio: np.ndarray) -> np.ndarray:
    return np.pad(audio[:WINDOW], (0, max(0, WINDOW - audio.size)))


def cut(audio: np.ndarray, starts: Sequence[float]) -> List[np.ndarray]:
    return [pad(audio[int(start * RATE):int(start * RATE) + WINDOW]) for start in starts]


def snippets(path: str, count: int) -> Tuple[List[np.ndarray], float, str]:
    """count windows of 10 s, the song's length in s, and how they were read: "seek" (each snippet on its own),
    "whole" (the file's length is missing or wrong, or the song is short: decoded once and cut), "short" (the song
    is one window or less). Near-silent windows are left out unless all are."""
    length = length_of(path)
    how = "seek"
    windows: List[np.ndarray] = []
    if length > WINDOW / RATE + PREROLL_SECONDS:
        for start in snippet_starts(length, count):
            audio = decode(path, start, WINDOW / RATE)
            if audio.size < WINDOW // 2:  # the file claims more than it has (a damaged MP3's length)
                windows = []
                break
            windows.append(pad(audio))
    if not windows:
        audio = decode(path)
        length = audio.size / RATE
        if audio.size <= WINDOW:
            how, windows = "short", [pad(audio)]
        else:
            how, windows = "whole", cut(audio, snippet_starts(length, count))
    loud = [window for window in windows if float(np.sqrt(np.mean(window ** 2))) >= SILENCE_RMS]
    return (loud or windows), length, how
