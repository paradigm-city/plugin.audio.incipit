"""Sound prints: a small acoustic fingerprint per song, the suggestion engine's local part.

Each song gets one 512-number vector from a few 10-second snippets, made by the distilled CLAP audio model (DCLAP,
github.com/NeptuneHub/AudioMuse-AI-DCLAP, AGPL-3.0; downloaded at first use, never shipped with the add-on). Songs
that sound alike have vectors that point the same way, so the nearest vectors to a seed's are the candidates the AI
judge then sorts (docs/concept_suggestion_engine.md).

The package runs outside Kodi, in an ordinary Python 3 with numpy, onnxruntime and av (PyAV): Kodi's own Python
has none of them. The add-on starts it as a separate process, as it starts the Claude CLI. Commands: see
`python -m soundprint --help`.

Nothing here is AudioMuse-AI's code; the spectrogram settings are those the model was trained with.
"""

# What a stored vector was made with; a vector of another version is made again at the next analysis.
MODEL_NAME = "dclap-v1"
DEFAULT_SNIPPETS = 6
PREROLL_SECONDS = 1.0

MODEL_FILES = {  # release v1 of DCLAP: name -> sha256
    "model_epoch_36.onnx": "17860403f8fc90aff8ac0632a0741eb5e58d8c0b0ad2fce5ced967274b0ea971",
    "model_epoch_36.onnx.data": "2a735b23c2aad7b12d9ffc85334cebcc659c07696d2ff60e2e378da28b6df657",
}


def analysis_version(snippets: int) -> str:
    return f"{MODEL_NAME}/snippets-{snippets}/preroll-{PREROLL_SECONDS:g}"
