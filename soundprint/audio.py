"""Decoding: mono 48 kHz snippets from any file FFmpeg reads (PyAV).

The model was trained on audio as librosa loads it: 48 kHz, the mean of all channels, clipped and rounded to
16 bits. Two things matter for snippets (measured 2026-10-27, docs/concept_suggestion_engine.md):
- the first frames after a seek are garbled (an MP3's bit reservoir, the resampler starting up), and the model
  weighs a window's first 50 ms heavily: such a glitch alone gives a cosine of 0.73 to the clean window. So each
  snippet is decoded from 1 s earlier and that second is dropped;
- hard cuts are fine: a 10 ms fade in and out changes nothing.

Two kinds of files FFmpeg doesn't read as they are (found in the first full analysis, 2026-10-28):
- an ID3 tag in front of something other than MP3 frames (an MP3 in a WAV file, Musepack), or a tag over 1 MB
  (a large cover): FFmpeg finds no audio. Such a file is opened again from where the tag ends;
- damaged MP3s: a false frame start in the damage decodes as a frame of another sample rate or channel layout,
  which the resampler refuses. Such frames are left out.
"""

from __future__ import annotations

import contextlib
from typing import Iterator, List, Optional, Sequence, Tuple

import numpy as np

from soundprint import PREROLL_SECONDS

RATE = 48000
WINDOW = 10 * RATE  # 10 s, as the model was trained
SILENCE_RMS = 1e-4  # about -80 dBFS: a window this quiet says nothing about the song


def prepare(audio: np.ndarray) -> np.ndarray:
    """As the model's training data: clipped and rounded to 16 bits."""
    return (np.clip(audio, -1, 1) * 32767.0).astype(np.int16).astype(np.float32) / 32767.0


def tag_end(path: str) -> int:
    """Where an ID3v2 tag at the start of the file ends (0 without one)."""
    with open(path, "rb") as handle:
        head = handle.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return 0
    size = 10 + ((head[6] & 0x7F) << 21 | (head[7] & 0x7F) << 14 | (head[8] & 0x7F) << 7 | head[9] & 0x7F)
    return size + 10 if head[5] & 0x10 else size  # with a footer


class FileFrom:
    """A file as if it began at offset (for FFmpeg, which then sees no tag in front)."""

    def __init__(self, path: str, offset: int):
        self.handle, self.offset = open(path, "rb"), offset
        self.handle.seek(offset)

    def read(self, size: int = -1) -> bytes:
        return self.handle.read(size)

    def seek(self, position: int, whence: int = 0) -> int:
        return self.handle.seek(position + self.offset if whence == 0 else position, whence) - self.offset

    def tell(self) -> int:
        return self.handle.tell() - self.offset

    def close(self) -> None:
        self.handle.close()


@contextlib.contextmanager
def opened(path: str) -> Iterator:
    """The file opened by FFmpeg, with an audio stream; opened again after its ID3 tag if FFmpeg finds none."""
    import av

    view = None
    try:
        container = av.open(path)
    except (av.error.InvalidDataError, IndexError):
        container = None
    if container is not None and not container.streams.audio:
        container.close()
        container = None
    if container is None:
        start = tag_end(path)
        if not start:
            container = av.open(path)  # FFmpeg's own error, or the file without audio as it is
        else:
            view = FileFrom(path, start)
            try:
                container = av.open(view)
            except BaseException:
                view.close()
                raise
    try:
        yield container
    finally:
        container.close()
        if view is not None:
            view.close()


def length_of(path: str) -> float:
    """The song's length in seconds as the file states it (0.0 if it doesn't)."""
    import av

    with opened(path) as container:
        return float(container.duration) / av.time_base if container.duration else 0.0


def decode(path: str, start: float = 0.0, seconds: float = 0.0) -> np.ndarray:
    """Mono float audio at 48 kHz from start (s) for seconds (0: to the end)."""
    import av

    with opened(path) as container:
        stream = container.streams.audio[0]
        if start > 0:
            container.seek(int(max(0.0, start - PREROLL_SECONDS) * av.time_base), any_frame=False)
        # packed samples, averaged over all channels below; PyAV's planar to_ndarray fails on 8 channels
        resampler = av.audio.resampler.AudioResampler(format="flt", layout=stream.layout, rate=RATE)
        channels = stream.layout.nb_channels
        rate = stream.codec_context.sample_rate  # as the file states it; 0 if it doesn't
        kind: Optional[Tuple[str, str, int]] = None  # the song's frames, as the resampler takes the first one
        wanted = int(seconds * RATE) if seconds else 0
        chunks: List[np.ndarray] = []
        total, skip = 0, None
        for packet in container.demux(stream):
            try:
                frames = packet.decode()
            except av.error.InvalidDataError:  # a damaged frame (some MP3s): leave it out, as librosa's decoder does
                continue
            for frame in frames:
                this = (frame.format.name, frame.layout.name, frame.sample_rate)
                if (rate and frame.sample_rate != rate) or (kind is not None and this != kind):
                    continue  # a false frame start in damaged data
                kind = this
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
