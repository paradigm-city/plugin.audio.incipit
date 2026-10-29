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
The descriptions come from an earlier rating. A line marked "(little known)" is music the rating didn't know: its
description was guessed from the names, the album and the genre, and may be wrong. Judge such a track by what the
guess can show (genre, era, sound). Don't call it borderline or outlier only because the guess suggests another
intent (pop appeal, nostalgia, pastiche, a use): that can't be told from the names. Turn it down only if what is
known clearly clashes."""

# On a Kraftwerk station (2026-10-29) the judge turned down three little-known 80s synth tracks for "pop appeal" or
# "style exercise", read from descriptions the rating had guessed; the listener heard all three as fitting.
LITTLE_KNOWN = " (little known)"

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

# Listening perspectives: from which point of view the seed's intent is stated and the tracks are judged. "mixed" is
# the prompt above (C of 2026-10-24) and stays as it is; the others share its frame and differ in what the intent
# describes and what a track must share to fit.
PERSPECTIVES = ("mixed", "technical", "emotional", "cultural", "functional", "lyrical")
DEFAULT_PERSPECTIVE = "mixed"

SEED_INTENT_HEAD = """You judge whether the tracks of a music mix serve the listener's intent.
The listener started the mix from the first track (the seed); MusicIP then added tracks by comparing audio.
The seed carries the intent of the mix.
"""

SEED_INTENT_TAIL = """The rest of the mix is context only: a track does not fit just because similar tracks are in the mix too.
Verdicts: fits, borderline or outlier. For borderline and outlier tracks give a reason of at most 12 words, naming
what clashes. Give the seed itself the verdict fits.

""" + TRACK_LINES_NOTE

# perspective: (the view, what the intent describes, what a fitting track must share)
PERSPECTIVE_TEXTS = {
    "technical": (
        "the view of an educated musician: what the musicians are doing, and how",
        """First, state that intent (field "character") as an educated musician hears the seed. Begin with one sentence
on the craft at the centre of the music: what the musicians are doing, and how (for example virtuoso improvisation
over shifting harmony, tight interlocking grooves, songcraft built on hooks, a sound built layer by layer in the
studio). Then give 5 to 8 qualities of that craft that a fitting track should share: harmony (its vocabulary, how
far it moves from the conventional), rhythm and metre (straight, odd, shifting, swung, grooving), form (song,
through-composed, open improvisation, build and release), melody and phrasing, the level and kind of musicianship,
how the sound is made (played, programmed, produced) and the lineage the craft builds on. Name instruments and
techniques where the craft depends on them.
End with "Not:" and 2 or 3 kinds of music that sound similar but are made differently.""",
        """Then judge every other track against that intent. A track fits only if it shares the craft: what the musicians do
with harmony, rhythm and form, and how well. Matching mood, energy, genre or era alone is not enough; a track can
fit with a different mood, genre or era if it shares the craft."""),
    "emotional": (
        "the artist's view: the emotion the music sets out to express, and how it means it",
        """First, state that intent (field "character") from the artist's side, as a skilled DJ hears the seed when
building a mix into one whole experience. Begin with one sentence on the emotional statement at the heart of the
music: what its makers feel and want to convey, and the stance they take towards it (for example earnest longing,
cool fascination with machines and modern life, defiant joy, grief held back, ironic distance, release). Go by what
the artist means, not by how an average listener might use the music: a hypnotic pulse can serve contemplation
rather than dancing.
Then give the qualities in two parts. "Core:" 3 to 5 qualities a fitting track must share: the stance and how
seriously and deeply it is meant (a considered statement, or light, pretty and merely pleasant), what the makers are
after (their own artistic idea, or pop appeal: hooks, sing-along, romantic drama, glamour), whether the feeling is
the music's own or borrowed (nostalgia for an earlier style, pastiche), sincere or ironic. Describe the core in terms
other music can share; leave out the seed's subject. How openly the feeling is shown is not its depth: restrained
music can mean a great deal, and wit or play can be meant seriously. "Colour:" 2 or 3 qualities of the seed's own
shade of the feeling (for example cool, warm, dark, sensual, playful, restrained) and the inner world it takes one
to; other tracks may differ in these. Leave out technique, genre, era and instrumentation unless they carry the
statement.
End with "Not:" and 2 or 3 kinds of music that feel similar on the surface but are after something else, or mean it
less. Don't name other colours of the same core: the "Not:" list must not contradict the qualities above.""",
        """Then judge every other track against that intent. A track fits if it shares the core, in its own way and
in its own colour: a darker, warmer, more sensual, more playful or more restrained track fits, and so does one with a
different subject, genre, era or craft. A track is an outlier if its makers are after something else (for example
pop appeal where the seed follows its own idea), or if it only borrows the surface of the feeling: matching the
pulse, the energy or the sound is not enough, and a track that is lighter, prettier or more nostalgic in intent than
the seed changes the statement. Borderline is for a track that shares the core only in part, not for a different
colour. The "Not:" list marks what changes the statement; a track is not an outlier just because it resembles one of
its kinds on the surface."""),
    "cultural": (
        "the view of a music historian: where the music comes from and what it stands for",
        """First, state that intent (field "character") as a music historian places the seed. Begin with one sentence on
where the music comes from and what it stands for: its scene, era, tradition or movement, and its place in it (for
example founding it, its mainstream, its underground, a revival, a crossover). Then give 5 to 8 qualities of that
background that a fitting track should share: the scene and where it lived, the era (when the music was made and
when it sounds like), the tradition and lineage, the audience and setting it was made for, the scene's attitude
and values, and the sound that marks it. Artists may be named as reference points of the scene.
End with "Not:" and 2 or 3 kinds of music that sound similar but come from another scene, tradition or time.""",
        """Then judge every other track against that intent. A track fits only if it comes from the same scene, tradition and
time, or stands in a direct line with them (its roots, its successors, kindred scenes). Matching sound, mood or
energy alone is not enough."""),
    "functional": (
        "the view of what the music is for: the situation or activity it serves",
        """First, state that intent (field "character") as the moment the seed serves. Begin with one sentence on what a
listener would choose the seed for: the situation, activity or moment it works in (for example a party at its peak,
a long night drive, focused work, a workout, winding down, falling asleep, close listening with full attention).
Then give 5 to 8 qualities that make it work there and that a fitting track should share: the energy level and how
steady it is, tempo and pulse, how much attention it asks for (foreground or background), how smooth or abrupt it
is, how prominent the voice and the words are, how far surprises would disturb the moment, length and flow.
Leave out genre, era and craft unless they matter for the moment.
End with "Not:" and 2 or 3 kinds of music that share the seed's style but would break the moment.""",
        """Then judge every other track against that intent. A track fits only if it serves the same moment without breaking
it: a listener in that moment would not reach for the skip button. A track can fit with a different genre, era or
craft if it serves the moment; a track of the same style does not fit if it would break it."""),
    "lyrical": (
        "the view of the words: what the songs are about and how they speak",
        """First, state that intent (field "character") from the seed's words. Begin with one sentence on what the words
are about and how they speak: the subject, and the singer's stance towards it (for example confession, protest,
storytelling, celebration, longing, irony). Then give 5 to 8 qualities of the words that a fitting track should
share: themes and subject, point of view and voice, tone (earnest, ironic, bitter, playful, tender), the language
(plain, poetic, abstract, slang), how central the words are to the song, and how they are delivered. If the seed is
instrumental or you don't know its words, say so, and describe instead what the music says without words: the
story, image or idea its title and sound suggest.
End with "Not:" and 2 or 3 kinds of songs that share the seed's sound but say something else.""",
        """Then judge every other track against that intent. A track fits only if its words share the subject or the stance,
and the tone; for an instrumental seed, if the track tells a similar story without words. A track can fit with a
different genre, era or sound if its words fit. If you don't know a track's words exactly, judge by what you know of
the song and its artist's writing, and by what its title, its description and its tone suggest; not knowing the
words is no reason for borderline."""),
}


def seed_intent_prompt(perspective: str = DEFAULT_PERSPECTIVE) -> str:
    """The seed-intent check from a perspective; "mixed" (and any unknown perspective) is SEED_INTENT_PROMPT."""
    if perspective not in PERSPECTIVE_TEXTS:
        return SEED_INTENT_PROMPT
    _view, intent, judging = PERSPECTIVE_TEXTS[perspective]
    return SEED_INTENT_HEAD + "\n" + intent + "\n\n" + judging + "\n" + SEED_INTENT_TAIL


def intent_prompt(perspective: str = DEFAULT_PERSPECTIVE) -> str:
    """The intent check from a perspective: the intent was stated from it, so the tracks are judged from it too."""
    if perspective not in PERSPECTIVE_TEXTS:
        return INTENT_PROMPT
    view, _intent, judging = PERSPECTIVE_TEXTS[perspective]
    rule = judging.replace("Then judge every other track against that intent. ", "")
    return f"""You judge tracks for a music mix against the listener's intent, from {view}.
The listener started the mix from a seed track. The intent is given below together with the seed; it is either
stated earlier from the seed or written by the listener.

Judge every track against that intent only. {rule}
Verdicts: fits, borderline or outlier. For borderline and outlier tracks give a reason of at most 12 words, naming
what clashes. Put a one-sentence summary of the intent in the field "character".

""" + TRACK_LINES_NOTE


def perspective_of(system_prompt: str) -> Optional[Tuple[str, str]]:
    """(purpose, perspective) of a check's system prompt, purpose "describing" or "judging"; None for other prompts."""
    for perspective in PERSPECTIVES:
        if system_prompt.startswith(seed_intent_prompt(perspective)):
            return "describing", perspective
        if system_prompt.startswith(intent_prompt(perspective)):
            return "judging", perspective
    return None


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
    guessed = LITTLE_KNOWN if entry and entry.get("familiarity", 1) == 0 else ""
    return (f"{number}. {item.get('artist', '')} – {title} ({item.get('album', '')}, {item.get('year') or ''}){guessed}"
            f" — {description}")


def parse_verdicts(payload: Optional[dict], count: int) -> Dict[int, dict]:
    verdicts = {}
    for entry in (payload or {}).get("tracks", []):
        number = entry.get("position")
        if isinstance(number, int) and 1 <= number <= count and entry.get("verdict") in VERDICTS:
            verdicts[number] = {"verdict": entry["verdict"], "reason": str(entry.get("reason", ""))[:200]}
    return verdicts


def state_intent(units: Sequence[dict], entries: Sequence[Optional[dict]], ask: Ask,
                 perspective: str = DEFAULT_PERSPECTIVE) -> Tuple[str, Dict[int, dict]]:
    """The seed's intent and a verdict per position (1 = the seed)."""
    lines = [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(seed_intent_prompt(perspective), schema(), "\n".join(lines))
    return str((payload or {}).get("character", "")), parse_verdicts(payload, len(units))


def judge(intent: str, seed: dict, seed_entry: Optional[dict], units: Sequence[dict],
          entries: Sequence[Optional[dict]], ask: Ask, perspective: str = DEFAULT_PERSPECTIVE) -> Dict[int, dict]:
    """A verdict per track (numbered from 1) against a known intent."""
    lines = [f"Intent: {intent}", "", "Seed: " + track_line(0, seed, seed_entry)[3:], "", "Tracks:"]
    lines += [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    return parse_verdicts(ask(intent_prompt(perspective), schema(), "\n".join(lines)), len(units))


def describe(units: Sequence[dict], entries: Sequence[Optional[dict]], ask: Ask,
             perspective: str = DEFAULT_PERSPECTIVE) -> Tuple[str, Dict[int, dict], str]:
    """As state_intent, plus a short name for the mix (2 to 4 words), in the same call."""
    lines = [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(seed_intent_prompt(perspective) + "\n\n" + NAME_NOTE, schema(with_name=True), "\n".join(lines))
    return str((payload or {}).get("character", "")), parse_verdicts(payload, len(units)), parse_name(payload)


def judge_named(intent: str, seed: dict, seed_entry: Optional[dict], units: Sequence[dict],
                entries: Sequence[Optional[dict]], ask: Ask,
                perspective: str = DEFAULT_PERSPECTIVE) -> Tuple[Dict[int, dict], str]:
    """As judge, plus a short name for the mix taken from the intent, in the same call."""
    lines = [f"Intent: {intent}", "", "Seed: " + track_line(0, seed, seed_entry)[3:], "", "Tracks:"]
    lines += [track_line(number, unit, entry) for number, (unit, entry) in enumerate(zip(units, entries), start=1)]
    payload = ask(intent_prompt(perspective) + "\n\n" + NAME_NOTE, schema(with_name=True), "\n".join(lines))
    return parse_verdicts(payload, len(units)), parse_name(payload)
