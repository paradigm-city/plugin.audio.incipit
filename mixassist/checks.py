"""The AI's judgement of a mix: what the seed says the mix is about, and which tracks fit that.

Two prompts from the pilot:
- the seed-intent check states the intent from the seed (as musical qualities, not surface features) and judges
  every track against it, with the rest of the mix as context only;
- the intent check judges tracks against an intent that is already known (stated earlier, or edited by the
  listener); it is also used for replacement candidates.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from mixassist.rating import Ask

VERDICTS = ("fits", "borderline", "outlier")

TRACK_LINES_NOTE = """Each line gives the position, artist, title, album and year, and a short description where available.
The descriptions come from an earlier rating and may be wrong for little-known music."""

SEED_INTENT_PROMPT = """You judge whether the tracks of a music mix serve the listener's intent.
The listener started the mix from the first track (the seed); MusicIP then added tracks by comparing audio.
The seed carries the intent of the mix.

First, state that intent (field "character"): 5 to 8 musical qualities of the seed that a fitting track should share.
Describe qualities, not surface features: complexity and structure, harmony (conventional or not), rhythm
(straight, broken, danceable or not), how abstract or song-like it is, how progressive or traditional,
handmade or electronic sound, mood and energy, era. Leave out instrumentation, scene, artists and production
details unless they are essential to the music's character.

Then judge every other track against that intent. A track can fit with different instruments, genre or production
if it shares the qualities. The rest of the mix is context only: a track does not fit just because similar tracks
are in the mix too. Verdicts: fits, borderline or outlier. For borderline and outlier tracks give a reason of at
most 12 words, naming the qualities that clash. Give the seed itself the verdict fits.

""" + TRACK_LINES_NOTE

INTENT_PROMPT = """You judge tracks for a music mix against the listener's intent.
The listener started the mix from a seed track. The intent is given below together with the seed; it is either
stated earlier from the seed or written by the listener.

Judge every track against that intent only. Verdicts: fits, borderline or outlier. For borderline and outlier
tracks give a reason of at most 12 words, naming the qualities that clash. Put a one-sentence summary of the intent
in the field "character".

""" + TRACK_LINES_NOTE


def schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "character": {"type": "string"},
            "tracks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {"type": "integer"},
                        "verdict": {"type": "string", "enum": list(VERDICTS)},
                        "reason": {"type": "string"},
                    },
                    "required": ["position", "verdict", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["character", "tracks"],
        "additionalProperties": False,
    }


def track_line(number: int, unit: dict, entry: Optional[dict]) -> str:
    item = unit["item"]
    title = item.get("title") or unit["label"]
    description = (entry or {}).get("description", "")
    return f"{number}. {item.get('artist', '')} – {title} ({item.get('album', '')}, {item.get('year') or ''}) — {description}"


def parse_verdicts(payload: Optional[dict], count: int) -> Dict[int, dict]:
    verdicts = {}
    for entry in (payload or {}).get("tracks", []):
        number = entry.get("position")
        if isinstance(number, int) and 1 <= number <= count and entry.get("verdict") in VERDICTS:
            verdicts[number] = {"verdict": entry["verdict"], "reason": str(entry.get("reason", ""))[:200]}
    return verdicts


def state_intent(units: Sequence[dict], entries: Sequence[Optional[dict]], ask: Ask) -> Tuple[str, Dict[int, dict]]:
    """The seed's intent and a verdict per position (1 = the seed)."""
    lines = [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(SEED_INTENT_PROMPT, schema(), "\n".join(lines))
    return str((payload or {}).get("character", "")), parse_verdicts(payload, len(units))


def judge(intent: str, seed: dict, seed_entry: Optional[dict], units: Sequence[dict],
          entries: Sequence[Optional[dict]], ask: Ask) -> Dict[int, dict]:
    """A verdict per track (numbered from 1) against a known intent."""
    lines = [f"Intent: {intent}", "", "Seed: " + track_line(0, seed, seed_entry)[3:], "", "Tracks:"]
    lines += [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    return parse_verdicts(ask(INTENT_PROMPT, schema(), "\n".join(lines)), len(units))
