"""AI Mix Assist: the style dimensions (version 2), their slider labels and anchors, and the rating prompt."""

from __future__ import annotations

from typing import NamedTuple


class Dimension(NamedTuple):
    key: str
    name: str
    low: str
    high: str
    labels: tuple  # five labels at 0, 2.5, 5, 7.5 and 10
    anchors: tuple  # one reference string per label
    notes: str


# Version 2: one axis per independent factor found in the dependency study (study.py), plus danceability,
# which parts from "programmed" exactly where it matters (hand-played dance music).
VERSION = 2

# Anchors are artists from the user's own library, so the slider labels and the AI ratings share one scale.
DIMENSIONS = (
    Dimension(
        "energy",
        "Energy",
        "calm",
        "intense",
        ("still", "gentle", "steady", "driving", "ferocious"),
        (
            "Brian Eno (ambient)",
            "Simon & Garfunkel",
            "Tears for Fears",
            "Led Zeppelin, Muse",
            "Motörhead, Meshuggah, Alpha Wolf",
        ),
        "Drive, force and weight together: heaviness, aggressiveness, density and how loudly the music "
        "addresses its audience rise with it.",
    ),
    Dimension(
        "exploration",
        "Exploration",
        "conventional",
        "exploratory",
        ("conventional", "familiar", "inventive", "adventurous", "radical"),
        (
            "AC/DC, Status Quo",
            "Foo Fighters, Erasure",
            "The Beatles, Kate Bush",
            "King Crimson, Radiohead",
            "Frank Zappa, Meshuggah, Aphex Twin",
        ),
        "How far the musical language departs from convention: harmony (diatonic to dissonant), rhythm "
        "(straight to odd, broken, polyrhythmic) and the will to experiment. Easy, catchy music is usually "
        "conventional. Not the same as era: 1970s progressive rock is exploratory and old.",
    ),
    Dimension(
        "mood",
        "Mood",
        "dark, tense",
        "bright, playful",
        ("bleak", "brooding", "bittersweet", "sunny", "exuberant"),
        (
            "Joy Division, Bauhaus",
            "Radiohead, Depeche Mode",
            "Carole King, Aimee Mann",
            "The Beatles, Erasure",
            "Slade, Parliament",
        ),
        "Emotional colour: gloom, tension and detachment against brightness, warmth and humour. Not the same "
        "as energy: dark music can be calm or ferocious.",
    ),
    Dimension(
        "making",
        "Making",
        "played by hand",
        "programmed",
        ("hand-played", "mostly played", "mixed", "mostly programmed", "machine-made"),
        (
            "Mike Dawes, Led Zeppelin",
            "Steely Dan, Talk Talk",
            "Nine Inch Nails, Massive Attack, Sleep Token",
            "Depeche Mode, New Order",
            "Kraftwerk, Aphex Twin",
        ),
        "Who makes the sound: musicians playing (acoustic or electric) or sequencers, samples and drum "
        "machines. An electric band is played by hand; synthesizers played live count as played.",
    ),
    Dimension(
        "danceability",
        "Danceability",
        "not for dancing",
        "made for dancing",
        ("for listening", "swaying", "groovy", "danceable", "dancefloor"),
        (
            "Brian Eno, Dream Theater",
            "Radiohead, Pink Floyd",
            "Steely Dan, Massive Attack",
            "Parliament, The Human League",
            "Erasure, Front 242",
        ),
        "Made for moving to: a steady, inviting pulse. Not the same as energy or making: house music can be "
        "mellow, disco and funk are played by hand, and heavy metal is intense but not dance music.",
    ),
    Dimension(
        "production",
        "Production",
        "raw, gritty",
        "polished",
        ("raw", "rough", "natural", "clean", "glossy"),
        (
            "The Fall, early punk",
            "Sonic Youth, Kyuss",
            "Joni Mitchell, Miles Davis",
            "Pat Metheny, Porcupine Tree",
            "Steely Dan, Def Leppard",
        ),
        "The surface of the recording: lo-fi, noisy, distorted or rough-edged against clean, smooth and "
        "glossy. Not the same as heaviness: heavy music can be polished.",
    ),
    Dimension(
        "form",
        "Form",
        "instrumental, open",
        "vocal song",
        ("open", "instrumental", "loose", "song", "vocal-led"),
        (
            "Brian Eno, Miles Davis (Bitches Brew)",
            "Weather Report, Snarky Puppy",
            "Pink Floyd, Yes",
            "The Beatles, Depeche Mode",
            "Joni Mitchell, Charles Aznavour",
        ),
        "Whether the music is built as vocal songs (verses, chorus, words) or as instrumental, open, "
        "textural or improvised pieces. Improvisation belongs to the open end.",
    ),
)

SCALE_KEYS = tuple(dimension.key for dimension in DIMENSIONS)

# Sounding era is a year internally; these steps exist only for the slider.
ERA_KEY = "sounding_year"
ERA_STEPS = (
    ("early", None, 1964),
    ("classic", 1965, 1979),
    ("eighties", 1980, 1989),
    ("turn of millennium", 1990, 2009),
    ("contemporary", 2010, None),
)
ERA_ANCHORS = (
    "Elvis Presley",
    "Led Zeppelin, The Doors",
    "Tears for Fears, Def Leppard",
    "Nirvana, Massive Attack",
    "Sleep Token, Periphery",
)

ALL_KEYS = SCALE_KEYS + (ERA_KEY,)

FAMILIARITY_LEVELS = (
    "0 = you do not know the artist; the rating is inferred from names, titles and genre tags",
    "1 = you know the artist, but not this album or track specifically",
    "2 = you know this album or track, or the artist's work in this period well",
)


def label_for(key: str, value: float) -> str:
    """Return the slider label closest to a value (0-10 scale, or a year for the era)."""
    if key == ERA_KEY:
        for label, start, end in ERA_STEPS:
            if (start is None or value >= start) and (end is None or value <= end):
                return label
        return ERA_STEPS[-1][0]
    dimension = next(item for item in DIMENSIONS if item.key == key)
    index = int(max(0.0, min(10.0, value)) / 2.5 + 0.5)
    return dimension.labels[min(index, 4)]


def describe_dimension(dimension: Dimension) -> str:
    steps = ", ".join(
        f"{value} {label} ({anchor})"
        for value, label, anchor in zip(("0", "2.5", "5", "7.5", "10"), dimension.labels, dimension.anchors)
    )
    return f"- {dimension.key} ({dimension.low} 0 ↔ {dimension.high} 10): {dimension.notes}\n  Anchors: {steps}."


def build_system_prompt(include_genres: bool = True) -> str:
    dimensions = "\n".join(describe_dimension(dimension) for dimension in DIMENSIONS)
    era = "; ".join(f"{label} ({anchor})" for (label, _, _), anchor in zip(ERA_STEPS, ERA_ANCHORS))
    levels = FAMILIARITY_LEVELS if include_genres else tuple(
        level.replace("names, titles and genre tags", "names and titles") for level in FAMILIARITY_LEVELS
    )
    familiarity = "\n".join(f"- {level}" for level in levels)
    genre_rule = (
        "\n- The genre tags come from the files and are often inaccurate; use them as a hint only."
        if include_genres
        else ""
    )
    return f"""You rate recorded music on fixed style scales for a personal music library.
The ratings place each item in a shared property space, so that a mix can tell which songs belong together.
Consistency across items matters more than precision: the same music must get the same numbers in every batch.

Scales (integers 0-10). The anchors mark the points 0, 2.5, 5, 7.5 and 10; use any integer in between.
{dimensions}

- {ERA_KEY}: the year the music sounds like, as a four-digit year. This is the era of its style and production,
  not necessarily the release year: a 2015 synthwave record that sounds like 1984 gets 1984.
  Rough steps: {era}.

familiarity (integer 0-2):
{familiarity}

character: at most 15 words on the atmosphere and style, in plain words.

Rules:
- Rate the music itself, judged as a listener would hear it. Do not rate quality or popularity.
- An album is rated as a whole: its typical sound, not its single most extreme track.
- A track is rated as that track.{genre_rule}
- If you do not know an item, still give your best estimate from the available hints and set familiarity to 0.
- Return exactly one rating per input item, with the same id."""


def item_schema() -> dict:
    properties = {"id": {"type": "string"}, "familiarity": {"type": "integer"}}
    for key in SCALE_KEYS:
        properties[key] = {"type": "integer"}
    properties[ERA_KEY] = {"type": "integer"}
    properties["character"] = {"type": "string"}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def output_schema() -> dict:
    return {
        "type": "object",
        "properties": {"ratings": {"type": "array", "items": item_schema()}},
        "required": ["ratings"],
        "additionalProperties": False,
    }
