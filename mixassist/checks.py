"""The AI's judgement of a mix: what the seed says the mix is about, and which tracks fit that.

Two prompts from the pilot:
- the seed-intent check states the intent from the seed (its intention, then musical qualities, not surface
  features, then what it is not) and judges every track against it, with the rest of the mix as context only;
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

First, state that intent (field "character"). Begin with the seed's intention in one sentence: what the music sets
out to do, and how its makers stand towards the listener and the world (for example celebrating and showing off,
provoking and tearing down, consoling, unsettling, hypnotising). Then give 5 to 8 musical qualities of the seed
that a fitting track should share.
Describe qualities, not surface features: complexity and structure, harmony (conventional or not), rhythm
(straight, broken, danceable or not), how abstract or song-like it is, how progressive or traditional,
handmade or electronic sound, mood and energy, era. Leave out instrumentation, scene, artists and production
details unless they are essential to the music's character.
End with "Not:" and 2 or 3 kinds of music that share many of these qualities but not the intention.

Then judge every other track against that intent. A track fits only if it shares the intention as well as the
qualities; matching energy, era or sound alone is not enough. A track can fit with different instruments, genre or
production if it shares both. The rest of the mix is context only: a track does not fit just because similar
tracks are in the mix too. Verdicts: fits, borderline or outlier. For borderline and outlier tracks give a reason
of at most 12 words, naming what clashes. Give the seed itself the verdict fits.

""" + TRACK_LINES_NOTE

NAME_NOTE = """Also give the mix a name (field "name"): 2 to 4 words in title case that capture its character, like
"Cosmic Analog Journeys" or "Dark Ambitious 80s Metal". No artist or song names, no quotation marks."""

INTENT_PROMPT = """You judge tracks for a music mix against the listener's intent.
The listener started the mix from a seed track. The intent is given below together with the seed; it is either
stated earlier from the seed or written by the listener.

Judge every track against that intent only. Verdicts: fits, borderline or outlier. For borderline and outlier
tracks give a reason of at most 12 words, naming the qualities that clash. Put a one-sentence summary of the intent
in the field "character".

""" + TRACK_LINES_NOTE


def schema(with_name: bool = False) -> dict:
    result = {
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
    if with_name:
        result["properties"]["name"] = {"type": "string"}
        result["required"].append("name")
    return result


def parse_name(payload: Optional[dict]) -> str:
    """The mix's name: 2 to 4 words, without quotes; "" when missing or unusable."""
    name = " ".join(str((payload or {}).get("name") or "").replace('"', "").replace("\u201c", "").replace("\u201d", "").split())
    words = name.split()
    return " ".join(words[:5]) if words and len(name) <= 60 else ""


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


def describe(units: Sequence[dict], entries: Sequence[Optional[dict]], ask: Ask) -> Tuple[str, Dict[int, dict], str]:
    """As state_intent, plus a short name for the mix (2 to 4 words), in the same call."""
    lines = [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(SEED_INTENT_PROMPT + "\n\n" + NAME_NOTE, schema(with_name=True), "\n".join(lines))
    return str((payload or {}).get("character", "")), parse_verdicts(payload, len(units)), parse_name(payload)


def judge_named(intent: str, seed: dict, seed_entry: Optional[dict], units: Sequence[dict],
                entries: Sequence[Optional[dict]], ask: Ask) -> Tuple[Dict[int, dict], str]:
    """As judge, plus a short name for the mix taken from the intent, in the same call."""
    lines = [f"Intent: {intent}", "", "Seed: " + track_line(0, seed, seed_entry)[3:], "", "Tracks:"]
    lines += [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(INTENT_PROMPT + "\n\n" + NAME_NOTE, schema(with_name=True), "\n".join(lines))
    return parse_verdicts(payload, len(units)), parse_name(payload)
