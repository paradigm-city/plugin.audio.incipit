"""The DCLAP audio model: log-mel spectrogram of a 10 s window -> 512 numbers.

The spectrogram is the one the model was trained on (librosa.feature.melspectrogram + power_to_db): 128 mel bands
(Slaney scale and norm), n_fft 2048 with a periodic Hann window, hop 480, 0 to 14 kHz, power in dB, frames centred
with mirrored edges. This numpy version gives the same vectors as AudioMuse-AI (cosine 1.000, 2026-10-27).

The model files come from the DCLAP release (see fetch): model_epoch_36.onnx and its external weights
model_epoch_36.onnx.data, which must lie in the same folder.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from typing import Callable, List, Optional, Sequence

import numpy as np

from soundprint import MODEL_FILES
from soundprint.audio import RATE

N_FFT, HOP, N_MELS, F_MIN, F_MAX = 2048, 480, 128, 0.0, 14000.0

RELEASE = "https://github.com/NeptuneHub/AudioMuse-AI-DCLAP/releases/download/v1/"
FILES = MODEL_FILES
MODEL_FILE = "model_epoch_36.onnx"
LICENCE_NOTE = """DCLAP audio model, release v1 of AudioMuse-AI Distilled CLAP
Source: https://github.com/NeptuneHub/AudioMuse-AI-DCLAP
Licence: GNU Affero General Public License v3.0 (AGPL-3.0), see the source repository.
Distilled from LAION CLAP (music_audioset_epoch_15_esc_90.14.pt, CC0-1.0) on Creative Commons and public-domain
music. Downloaded by Incipit (plugin.audio.incipit) at the listener's request; not part of the add-on.
"""


def mel_filters() -> np.ndarray:
    """librosa.filters.mel(htk=False, norm="slaney"): Slaney's mel scale, each band normalised to equal area."""
    f_sp, min_log_hz, min_log_mel, logstep = 200.0 / 3, 1000.0, 15.0, np.log(6.4) / 27.0

    def to_mel(hz):
        hz = np.asarray(hz, dtype=np.float64)
        return np.where(hz >= min_log_hz, min_log_mel + np.log(np.maximum(hz, 1e-12) / min_log_hz) / logstep, hz / f_sp)

    def to_hz(mel):
        return np.where(mel >= min_log_mel, min_log_hz * np.exp(logstep * (mel - min_log_mel)), f_sp * mel)

    mel_f = to_hz(np.linspace(to_mel(F_MIN), to_mel(F_MAX), N_MELS + 2))
    fft_f = np.linspace(0, RATE / 2, 1 + N_FFT // 2)
    fdiff, ramps = np.diff(mel_f), mel_f[:, None] - fft_f[None, :]
    lower, upper = -ramps[:-2] / fdiff[:-1, None], ramps[2:] / fdiff[1:, None]
    weights = np.maximum(0, np.minimum(lower, upper))
    return (weights * (2.0 / (mel_f[2:] - mel_f[:-2]))[:, None]).astype(np.float32)


FILTERS = mel_filters()
HANN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)  # periodic


def mel_db(window: np.ndarray) -> np.ndarray:
    """[1, 1, 128, frames] log-mel spectrogram of one window, as the model's input."""
    padded = np.pad(window, N_FFT // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP]
    power = np.abs(np.fft.rfft(frames * HANN, axis=1)) ** 2
    mel = FILTERS @ power.T.astype(np.float32)
    return (10.0 * np.log10(np.maximum(mel, 1e-10)))[None, None].astype(np.float32)


class Model:
    def __init__(self, folder: str, threads: int = 1):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max(1, threads)
        options.inter_op_num_threads = 1
        # waiting threads would spin and take the CPU from the other analysis processes
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        self.session = onnxruntime.InferenceSession(os.path.join(folder, MODEL_FILE), options,
                                                    providers=["CPUExecutionProvider"])

    def embed(self, windows: Sequence[np.ndarray]) -> np.ndarray:
        """The song's vector: the mean of the windows' vectors, scaled to length 1."""
        vectors = np.vstack([self.session.run(None, {"mel_spectrogram": mel_db(window)})[0] for window in windows])
        mean = vectors.mean(axis=0)
        return (mean / (np.linalg.norm(mean) + 1e-9)).astype(np.float32)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def missing(folder: str) -> List[str]:
    """Model files that are absent or not those of release v1."""
    return [name for name, digest in FILES.items()
            if not os.path.isfile(os.path.join(folder, name)) or sha256(os.path.join(folder, name)) != digest]


def fetch(folder: str, say: Callable[[str], None] = print, opener: Optional[Callable] = None) -> None:
    """Download the model files of release v1 into folder (checked by sha256), with a note on their licence."""
    opener = opener or urllib.request.urlopen
    os.makedirs(folder, exist_ok=True)
    for name in missing(folder):
        target = os.path.join(folder, name)
        say(f"downloading {RELEASE + name}")
        with opener(RELEASE + name, timeout=60) as response, open(target + ".part", "wb") as handle:
            for block in iter(lambda: response.read(1 << 20), b""):
                handle.write(block)
        if sha256(target + ".part") != FILES[name]:
            os.remove(target + ".part")
            raise RuntimeError(f"{name}: the download does not match release v1 (sha256)")
        os.replace(target + ".part", target)
        say(f"{name}: {os.path.getsize(target)} bytes, sha256 checked")
    with open(os.path.join(folder, "LICENCE.txt"), "w", encoding="utf-8") as handle:
        handle.write(LICENCE_NOTE)
