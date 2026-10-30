"""Tidying up a mix: find the tracks that don't fit what the seed is about, and replace them from submixes.

tidy_up() returns a plan and changes nothing; the caller applies it (saved mix, playlist) and records it.
Everything outside the package is passed in: resolve (paths -> units), fetch_mix (the source), ask (Claude).

Two checks follow the source (the sound engine), each of which can be off:
- Character: the 8-value profile against the seed's, within a limit (strictness; None: off). Measured on a fixed
  scale for the seed when the caller gives its nearest songs by sound that have a rating (scale_entries, F40), else
  on the spread of the tracks checked (which makes a loose list look closer than it is).
- Intent: the AI states what the seed is about from a listening perspective and judges each track (perspective;
  None: off); accept_borderline also takes the tracks it calls borderline.
A new track must pass every check that is on; a track leaves a mix when every check that is on turns it down.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

from mixassist import checks, dimensions, fit, trace
from mixassist.cache import RatingCache, artist_key
from mixassist.rating import Ask, rate_missing
from mixassist.stats import median

# Calibrated in the pilot on five mixes: 1.2 x the mix's median misfit caught 33 of 47 outliers of the seed-intent
# check and flagged 1 of 70 fitting tracks. The median has a floor, so a very consistent mix doesn't flag trivia.
DEFAULT_STRICTNESS = 1.2
MIN_TYPICAL_MISFIT = 1.0
SUBMIX_SIZE = 15
FALLBACK_FACTOR = 3
MUSICIP_MAX_MIX = 75
ARTIST_WINDOW = 5
# A mix where more than this share fails would rather be rebuilt than patched.
REBUILD_SHARE = 1 / 3
# The second profile rule: a track whose single dimension is clearly off, however close it is overall. Tested on the
# pilot's 5 mixes: with these limits the profile check caught 45 of the AI's 47 outliers (36 without) and all 9 of the
# user's, and flagged 2 of 70 fitting tracks (1 without); at 4 points / 20 years it flagged 26 fitting tracks.
SINGLE_DIMENSION_POINTS = 5  # on the 0-10 scales
SINGLE_DIMENSION_YEARS = 25  # sounding year
# Dimensions the profile check leaves out for a listening perspective whose prompt says they don't matter. Emotional
# judges what the artist expresses, with production left out "unless it carries the statement"; on a Kraftwerk
# station the production rating alone overruled 5 of the AI's 14 fits (F35).
PROFILE_LEAVES_OUT = {"emotional": ("production",)}

Resolve = Callable[[Sequence[str]], List[dict]]
FetchMix = Callable[[str, int], List[str]]


def path_key(path: str) -> str:
    return (path or "").replace("\\", "/").strip().lower()


def profile_keys(perspective: str = checks.DEFAULT_PERSPECTIVE) -> tuple:
    """The dimensions the profile check compares for a listening perspective."""
    return tuple(key for key in dimensions.ALL_KEYS if key not in PROFILE_LEAVES_OUT.get(perspective, ()))


def single_dimension_miss(entry: dict, reference: dict, keys: Sequence[str] = dimensions.ALL_KEYS) -> str:
    """The dimension on which entry is clearly off from reference (the largest such), "" if none."""
    misses = []
    for key in keys:
        if not isinstance(entry.get(key), (int, float)) or not isinstance(reference.get(key), (int, float)):
            continue
        gap = abs(float(entry[key]) - float(reference[key]))
        limit = SINGLE_DIMENSION_YEARS if key == dimensions.ERA_KEY else SINGLE_DIMENSION_POINTS
        if gap >= limit:
            misses.append((gap / limit, key))
    return max(misses)[1] if misses else ""


SCALE_MIN_ENTRIES = 5  # rated songs needed for the seed's fixed scale


def character_scale(seed: Optional[dict], reference: Sequence[Optional[dict]], library: List[dict],
                    keys: Sequence[str]) -> Optional[dict]:
    """Character's fixed scale for a seed (F40): the spreads of its nearest songs by sound (reference, those with a
    rating) and their median misfit, so every list checked against the seed is measured alike, however loose it
    is. None with fewer than SCALE_MIN_ENTRIES."""
    reference = [entry for entry in reference if entry]
    if not seed or len(reference) < SCALE_MIN_ENTRIES:
        return None
    weights = fit.seed_weights(seed, library, keys)
    spreads = fit.weighted_spreads(fit.mix_spreads(reference + [seed], keys), weights)
    inverse = fit.inverse_correlation(library, keys)
    typical = max(MIN_TYPICAL_MISFIT, median([fit.misfit(entry, seed, spreads, inverse, keys)[0] for entry in reference]))
    return {"spreads": spreads, "typical": typical, "weights": weights, "inverse": inverse, "count": len(reference)}


def analyze(units: Sequence[dict], entries: Sequence[Optional[dict]], verdicts: Dict[int, dict],
            library: List[dict], strictness: Optional[float] = DEFAULT_STRICTNESS,
            perspective: Optional[str] = checks.DEFAULT_PERSPECTIVE,
            scale_entries: Sequence[Optional[dict]] = ()) -> Dict[str, object]:
    """Per track: the checks that are on (see the module's docstring) and a status. Character: the weighted misfit
    against the seed, relative to the typical misfit (of the seed's fixed scale, else of these tracks), on the
    dimensions that matter for the listening perspective (profile_keys). Intent: the AI's verdict."""
    seed = entries[0]
    vectors = [entry for entry in entries if entry]
    keys = profile_keys(perspective or checks.DEFAULT_PERSPECTIVE)
    character, judged = strictness is not None, perspective is not None
    if (character and (not seed or len(vectors) < 5)) or not (character or judged):
        return {"rows": [], "weights": {}, "spreads": {}, "typical": 1.0, "ready": False, "keys": keys}
    weights, weighted, inverse, fixed = {}, {}, None, None
    if character:
        fixed = character_scale(seed, scale_entries, library, keys)
        if fixed:
            weights, weighted, inverse = fixed["weights"], fixed["spreads"], fixed["inverse"]
        else:
            weights = fit.seed_weights(seed, library, keys)
            weighted = fit.weighted_spreads(fit.mix_spreads(vectors, keys), weights)
            inverse = fit.inverse_correlation(library, keys)
    rows = []
    for position, (unit, entry) in enumerate(zip(units, entries), start=1):
        row = {"position": position, "unit": unit, "entry": entry}
        row.update(verdicts.get(position, {"verdict": "", "reason": ""}))
        if entry:
            row["guessed"] = entry.get("familiarity", 1) == 0
            if character:
                row["misfit"], deviations = fit.misfit(entry, seed, weighted, inverse, keys)
                row["why"] = fit.reason(entry, seed, deviations)
                row["single"] = single_dimension_miss(entry, seed, keys) if position > 1 else ""
        rows.append(row)
    typical = fixed["typical"] if fixed else max(MIN_TYPICAL_MISFIT, median(
        [row["misfit"] for row in rows[1:] if "misfit" in row])) if character else 1.0
    for row in rows:
        if character and "misfit" not in row:
            row["status"] = "unrated"
            continue
        flags = []
        if character:
            row["relative"] = row["misfit"] / typical
            flags.append(row["position"] > 1 and (row["relative"] > strictness or bool(row.get("single"))))
        if judged:
            flags.append(row["verdict"] == "outlier")
        if row["position"] == 1:
            row["status"] = "seed"
        elif all(flags):
            row["status"] = "outlier"  # every check that is on agrees; guessed units included (act on the facts)
        elif any(flags):
            row["status"] = "flagged"
        elif row["verdict"] == "borderline":
            row["status"] = "borderline"
        else:
            row["status"] = "fits"
    if trace.active():
        trace_rows(rows, typical, strictness, weights, perspective, fixed)
    return {"rows": rows, "weights": weights, "spreads": weighted, "inverse": inverse, "typical": typical,
            "ready": True, "keys": keys, "scale": "fixed" if fixed else "list"}


def trace_rows(rows: Sequence[dict], typical: float, strictness: Optional[float], weights: Dict[str, float],
               perspective: Optional[str] = checks.DEFAULT_PERSPECTIVE, fixed: Optional[dict] = None) -> None:
    character = (f"Character: typical misfit {trace.number(typical)} ("
                 + (f"the seed's fixed scale, from {fixed['count']} rated songs nearest to it by sound" if fixed else
                    "these tracks' own scale: too few rated songs near the seed by sound")
                 + f"), a track is off beyond {trace.number(strictness)} x that; seed weights "
                 + ", ".join(f"{key} {trace.number(value)}" for key, value in weights.items())) \
        if strictness is not None else "Character: off"
    trace.say(f"Checks against the seed {rows[0]['unit']['label']!r}: {character}; Intent: "
              + (f"{perspective} perspective" if perspective is not None else "off"))
    for row in rows:
        trace.say(f"  {row['position']:>2}. {row.get('status', ''):<10} {row['unit']['label']!r}: relative "
                  f"{trace.number(row.get('relative'))} (misfit {trace.number(row.get('misfit'))})"
                  + (f", clearly off in {row['single']}" if row.get("single") else "")
                  + (", rating guessed" if row.get("guessed") else "")
                  + f"; AI: {row.get('verdict') or '-'}" + (f" ({row['reason']})" if row.get("reason") else "")
                  + (f"; profile: {row['why']}" if row.get("why") else ""))


def clearly_fitting(rows: Sequence[dict], strictness: Optional[float], judged: bool = True) -> set:
    """The positions every check that is on says fit (the seed too)."""
    fitting = {1}
    for row in rows:
        character = strictness is None or (row.get("relative") is not None and row["relative"] <= strictness
                                           and not row.get("single"))
        if character and (not judged or row.get("verdict") == "fits"):
            fitting.add(row["position"])
    return fitting


def submix_seed_position(position: int, fitting) -> int:
    """The nearest earlier track that clearly fits; at worst the seed. A submix inherits its seed's direction."""
    candidate = position - 1
    while candidate > 1 and candidate not in fitting:
        candidate -= 1
    return max(candidate, 1)


def nearby_artists(artists: Sequence[str], position: int, window: int) -> set:
    index = position - 1
    return {artist_key(artists[i]) for i in range(max(0, index - window), min(len(artists), index + window + 1))
            if i != index and artists[i]}


def pick(candidates: Sequence[dict], strictness: Optional[float], taken: set, blocked: set,
         accept_borderline: bool = False, judged: bool = True) -> Optional[dict]:
    """The passing candidate closest in profile (with Character off: the first)."""
    passing = [c for c in candidates if passes(c, strictness, accept_borderline, judged)
               and path_key(c["path"]) not in taken and artist_key(c.get("artist", "")) not in blocked]
    return min(passing, key=lambda c: c.get("relative", 0.0)) if passing else None


def rating_progress(progress: Optional[Callable[..., None]], text: str, share: float = 1.0):
    """rate_missing's progress(done, total) as progress("<text> (done of total)", fraction of the step)."""
    if not progress:
        return None
    return lambda done, total: progress(f"{text} ({done} of {total})", share * done / max(1, total))


def score_candidates(candidate_paths: Sequence[str], units: Sequence[dict], entries: Sequence[Optional[dict]],
                     intent: str, analysis: Dict[str, object], cache: RatingCache, ask: Ask, resolve: Resolve,
                     model: str = "", progress: Optional[Callable[..., None]] = None,
                     label: str = "Checking the replacements",
                     perspective: str = checks.DEFAULT_PERSPECTIVE) -> Dict[str, dict]:
    """Both signals for candidate tracks, measured against the master mix (one AI call for all of them).
    Keyed by path: label, artist, the AI's verdict and reason, and the relative misfit if the track is rated.
    progress(text, fraction) reports the parts of this step (`label`)."""
    candidates = resolve(candidate_paths)
    rate_missing(candidates, cache, ask, model=model,
                 progress=rating_progress(progress, f"{label}: rating new music", 0.7))
    candidate_entries = [cache.get(unit["key"]) for unit in candidates]
    verdicts = {}
    if perspective is not None:
        if progress:
            progress(f"{label}: asking the AI about {len(candidates)} tracks", 0.75)
        verdicts = checks.judge(intent, units[0], entries[0], candidates, candidate_entries, ask, perspective)
    scored: Dict[str, dict] = {}
    for number, (unit, entry) in enumerate(zip(candidates, candidate_entries), start=1):
        verdict = verdicts.get(number, {})
        candidate = {"path": unit["path"], "label": unit["label"], "artist": unit.get("artist", ""),
                     "verdict": verdict.get("verdict", ""), "reason": verdict.get("reason", "")}
        if entry and analysis.get("spreads"):
            keys = analysis.get("keys", dimensions.ALL_KEYS)
            misfit, _ = fit.misfit(entry, entries[0], analysis["spreads"], analysis["inverse"], keys)
            candidate["relative"] = misfit / analysis["typical"]
            candidate["single"] = single_dimension_miss(entry, entries[0], keys)
            candidate["entry"] = entry
        scored[unit["path"]] = candidate
        trace.say(f"  candidate {unit['label']!r}: relative {trace.number(candidate.get('relative'))}"
                  + (f", clearly off in {candidate['single']}" if candidate.get("single") else "")
                  + f"; AI: {candidate['verdict'] or '-'}" + (f" ({candidate['reason']})" if candidate["reason"] else ""))
    return scored


def passes(candidate: Optional[dict], strictness: Optional[float], accept_borderline: bool = False,
           judged: bool = True) -> bool:
    """Every check that is on says the candidate fits. Character: its misfit is within the strictness and no single
    dimension is clearly off. Intent (judged): the AI says "fits" (or "borderline", when that is accepted)."""
    if not candidate:
        return False
    if strictness is not None and (candidate.get("relative") is None or candidate["relative"] > strictness
                                   or candidate.get("single")):
        return False
    return not judged or candidate.get("verdict") in (("fits", "borderline") if accept_borderline else ("fits",))


def turned_down_reason(row: dict, strictness: Optional[float], accept_borderline: bool = False,
                       judged: bool = True) -> str:
    """Why a candidate doesn't pass: the AI's reason, or the profile's when the AI would have taken it (F35)."""
    if judged and row.get("verdict") not in (("fits", "borderline") if accept_borderline else ("fits",)):
        return row.get("reason") or row.get("why", "")
    if not judged:
        said = "Intent is off"
    else:
        said = "the AI says it " + ("fits" if row["verdict"] == "fits" else "is borderline")
    profile = f" ({row['why']})" if row.get("why") else ""
    if row.get("relative") is None:
        return f"{said}, but it has no rating to compare"
    if row.get("single"):
        return f"{said}, but its profile is clearly off in {row['single']}{profile}"
    return (f"{said}, but its profile is too far from the seed's (relative "
            f"{trace.number(row['relative'])}, at most {trace.number(strictness)}){profile}")


def tidy_up(paths: Sequence[str], cache: RatingCache, ask: Ask, resolve: Resolve, fetch_mix: FetchMix,
            intent: str = "", strictness: Optional[float] = DEFAULT_STRICTNESS, artist_window: int = ARTIST_WINDOW,
            model: str = "", progress: Optional[Callable[..., None]] = None,
            find_replacements: bool = True, accept_borderline: bool = False,
            perspective: Optional[str] = checks.DEFAULT_PERSPECTIVE, scale_entries: Sequence[Optional[dict]] = ()) -> dict:
    """A plan for the mix: the intent, every track's status, and the replacements to make.

    With find_replacements=False only the tracks that don't fit are found ("show only"). With Intent on, the intent
    is stated and the tracks are judged from the listening perspective (checks.PERSPECTIVES); scale_entries: see
    analyze."""
    def step(text: str, fraction: Optional[float] = None) -> None:
        """progress(text) at the start of a step, progress(text, fraction) within it."""
        if progress:
            progress(text) if fraction is None else progress(text, fraction)

    paths = list(paths)
    step("Looking up the tracks")
    units = resolve(paths)
    step("Rating new music")
    rate_missing(units, cache, ask, model=model, progress=rating_progress(step, "Rating new music"))
    entries = [cache.get(unit["key"]) for unit in units]

    judging = perspective is not None
    name = ""
    if not judging:
        verdicts, intent_source = {}, "listener" if intent else "none"
        trace.say("Intent is off: no AI judgement, the profile alone decides.")
    elif intent:
        step("Working out what this mix is about")
        judged, name = checks.judge_named(intent, units[0], entries[0], units[1:], entries[1:], ask, perspective)
        verdicts = {position + 1: verdict for position, verdict in judged.items()}
        verdicts[1] = {"verdict": "fits", "reason": ""}
        intent_source = "listener"
    else:
        step("Working out what this mix is about")
        intent, verdicts, name = checks.describe(units, entries, ask, perspective)
        intent_source = "ai"

    if judging:
        trace.say(f"What the mix is about ({intent_source}, {perspective} perspective): {intent}"
                  + (f"; name: {name}" if name else ""))
    analysis = analyze(units, entries, verdicts, cache.library(), strictness, perspective, scale_entries)
    rows = analysis["rows"]
    outliers = [row["position"] for row in rows if row.get("status") == "outlier"]
    trace.say(f"Tidy-up: {len(outliers)} of {len(rows) - 1} track(s) don't fit by every check that is on: {outliers}"
              + ("" if analysis["ready"] else " (too few rated tracks to measure)"))
    plan = {"intent": intent, "intent_source": intent_source, "perspective": perspective or "", "name": name,
            "rows": rows, "outliers": outliers, "changes": [],
            "removed": [], "paths": paths, "rebuild_suggested": False}
    if not analysis["ready"] or not outliers or not find_replacements:
        return plan
    plan["rebuild_suggested"] = len(outliers) > REBUILD_SHARE * (len(paths) - 1)

    step("Finding replacements")
    fitting = clearly_fitting(rows, strictness, judging)
    examined = {path_key(path) for path in paths}  # in the mix or already offered as a candidate
    mixes: Dict[int, Optional[List[str]]] = {}

    def musicip_mix(position: int) -> Optional[List[str]]:
        """The source's mix for a track of the mix (fetched once, MUSICIP_MAX_MIX songs); None if it fails."""
        if position not in mixes:
            try:
                mixes[position] = list(fetch_mix(paths[position - 1], MUSICIP_MAX_MIX))
            except Exception:
                mixes[position] = None
        return mixes[position]

    def fresh(tracks: Optional[Sequence[str]], limit: int) -> List[str]:
        """The first tracks not yet in the mix or offered, in the source's order."""
        result: List[str] = []
        for track in tracks or []:
            if len(result) >= limit:
                break
            if path_key(track) not in examined:
                examined.add(path_key(track))
                result.append(track)
        return result

    def evaluate(candidate_paths: List[str]) -> Dict[str, dict]:
        # Gaps that share a submix share its tracks: each candidate is rated and judged once.
        candidate_paths = list(dict.fromkeys(candidate_paths))
        if not candidate_paths:
            return {}
        step("Checking the replacements")
        return score_candidates(candidate_paths, units, entries, intent, analysis, cache, ask, resolve, model,
                                progress=step, perspective=perspective)

    taken = {path_key(path) for path in paths}
    artists = [unit.get("artist", "") for unit in units]
    for position in outliers:  # these tracks leave the mix, so their artists don't block anything
        artists[position - 1] = ""
    new_paths: List[Optional[str]] = list(paths)

    def fill(gaps: List[tuple], fallback: List[str], scored: Dict[str, dict], source: str) -> List[int]:
        """Fill each gap from its own candidates, else from any candidate of this round (the other gaps' and the
        fallback); returns the unfilled gaps."""
        unfilled = []
        shared = list(scored.values())
        for position, options in gaps:
            blocked = nearby_artists(artists, position, artist_window)
            choice = pick([scored[p] for p in options if p in scored], strictness, taken, blocked, accept_borderline,
                          judging)
            origin = source
            if choice is None:
                choice = pick(shared, strictness, taken, blocked, accept_borderline, judging)
                origin = "seed" if choice and choice["path"] in fallback else source
            if choice is None:
                trace.say(f"Replacement for {position}. {rows[position - 1]['unit']['label']!r}: none of "
                          f"{len(options)} {source} candidate(s) or the round's others passes.")
                unfilled.append(position)
                continue
            row = rows[position - 1]
            trace.say(f"Replacement for {position}. {row['unit']['label']!r}: {choice['label']!r} ({origin}, relative "
                      f"{trace.number(choice.get('relative'))}, AI: {choice['verdict']}).")
            taken.add(path_key(choice["path"]))
            artists[position - 1] = choice["artist"]
            new_paths[position - 1] = choice["path"]
            plan["changes"].append({"position": position, "old": paths[position - 1],
                                    "old_label": row["unit"]["label"], "reason": row.get("reason") or row.get("why", ""),
                                    "new": choice["path"], "new_label": choice["label"], "source": origin,
                                    "entry": choice.get("entry")})
        return unfilled

    # Round 1: a submix from the nearest earlier track that clearly fits. Gaps that share a submix seed share one
    # larger submix, so they don't all compete for the same 15 tracks.
    groups: Dict[int, List[int]] = {}
    for position in outliers:
        seed_position = submix_seed_position(position, fitting)
        while musicip_mix(seed_position) is None and seed_position > 1:
            seed_position = submix_seed_position(seed_position, fitting)
        groups.setdefault(seed_position, []).append(position)
    gaps = []
    for seed_position, members in groups.items():
        options = fresh(musicip_mix(seed_position), SUBMIX_SIZE * len(members))
        trace.say(f"Submix from {seed_position}. {rows[seed_position - 1]['unit']['label']!r} for position(s) {members}: "
                  f"{len(options)} fresh candidate(s).")
        gaps.extend((position, options) for position in members)
    gaps.sort()
    fallback = fresh(musicip_mix(1), SUBMIX_SIZE * FALLBACK_FACTOR)
    unfilled = fill(gaps, fallback, evaluate([p for _, options in gaps for p in options] + fallback), "submix")

    # Round 2: for gaps still open, submixes from other clearly fitting tracks, the nearest first.
    if unfilled:
        step("Finding replacements")
        gaps = []
        for position in unfilled:
            nearby = sorted((p for p in fitting if p not in mixes), key=lambda p: (abs(p - position), p > position))
            options = []
            for seed_position in nearby[:3]:
                options = fresh(musicip_mix(seed_position), SUBMIX_SIZE)
                if options:
                    break
            gaps.append((position, options))
        unfilled = fill(gaps, [], evaluate([p for _, options in gaps for p in options]), "nearby")

    for position in unfilled:
        new_paths[position - 1] = None
        plan["removed"].append(position)
    plan["paths"] = [path for path in new_paths if path]
    return plan


def choose_additions(selected: str, candidates: Sequence[str], count: int, cache: RatingCache, ask: Ask,
                     resolve: Resolve, before: Sequence[str] = (), after: Sequence[str] = (),
                     strictness: Optional[float] = DEFAULT_STRICTNESS,
                     artist_window: int = ARTIST_WINDOW, model: str = "",
                     progress: Optional[Callable[..., None]] = None, reference: Optional[dict] = None,
                     accept_borderline: bool = False, name: bool = False, max_batches: int = 2,
                     more: Optional[Callable[[List[str]], Sequence[str]]] = None,
                     perspective: Optional[str] = checks.DEFAULT_PERSPECTIVE,
                     scale_entries: Sequence[Optional[dict]] = (), intent: str = "") -> dict:
    """"More like this" (and Radio refills): the selected song and the source's candidates for it form a small mix
    with the selected song as its seed. New tracks are held to the same rule as replacements: every check that is on
    must say a candidate fits what the selected song is about (strictness None: Character off; perspective None:
    Intent off; scale_entries: see analyze). The first `count` fitting candidates, in the source's order, are
    chosen.

    Artists are spaced as in the final mix, where the chosen songs go in one after another between `before` (the
    tracks up to the insertion point, by default the selected song) and `after` (the tracks that follow it): no
    artist within `artist_window` songs (0: repeats allowed), the rule of the reject size. A fitting song
    whose artist played too recently waits and is taken as soon as enough other songs lie between; an artist among
    the first `artist_window` songs after the insertion point is kept out (the new songs might all go before it).

    `reference` (a rating, e.g. a Radio station's drifting profile) replaces the selected song's own rating in the
    vector part; the AI still judges against the selected song. accept_borderline also takes candidates the AI
    calls borderline (Radio's bold steps).

    Returns intent (the selected song's), chosen (paths), entries (the chosen tracks' ratings by path), seed_entry
    (the selected song's rating), not_fitting ([{path, label, reason}]) and checked (False if the candidates
    couldn't be measured; then the first ones are taken unchecked). With name, also a name for what the selected
    song is about (2 to 4 words, from the same AI call).

    Candidates are examined in batches until `count` are chosen or `max_batches` were examined (a stricter choice
    needs more to choose from). When the candidates run out first, more(chosen so far) may bring further ones
    (another candidate list); [] ends the search. Also returns examined (how many) and lists (candidate lists used).
    Every batch is judged from the same listening perspective (checks.PERSPECTIVES). A given `intent` (what the
    selected song is about, stated before: a favourite station's) is judged against from the first batch on, and not
    stated again (no name then either)."""
    def step(text: str, fraction: Optional[float] = None) -> None:
        if progress:
            progress(text) if fraction is None else progress(text, fraction)

    candidates = list(candidates)
    result = {"intent": intent, "name": "", "chosen": [], "entries": {}, "seed_entry": None, "not_fitting": [],
              "checked": False, "examined": 0, "lists": 1 if candidates else 0}
    step("Looking up the tracks")
    selected_unit = resolve([selected])[0]
    window = max(0, artist_window)
    # the final mix's artists in order up to the newest chosen song, and the artists right after the new songs
    placed = [artist_key(unit.get("artist", "")) for unit in resolve(list(before[-window:]) or [selected])] \
        if window else []
    following = [artist_key(unit.get("artist", "")) for unit in resolve(list(after[:window]))] if window else []
    waiting: List[dict] = []  # fitting songs whose artist played too recently, closest first

    def too_soon(artist: str) -> bool:
        return bool(window and artist and (artist in placed[-window:] or artist in following))

    def choose(row: dict, note: str = "") -> None:
        trace.say(f"  chosen {row['unit']['label']!r}{note}.")
        result["chosen"].append(row["unit"]["path"])
        result["entries"][row["unit"]["path"]] = row["entry"]
        placed.append(artist_key(row["unit"].get("artist", "")))

    def take_waiting() -> None:
        """The waiting songs that the songs chosen since put far enough from their artist's last song."""
        changed = True
        while changed and waiting and len(result["chosen"]) < count:
            changed = False
            for row in list(waiting):
                if len(result["chosen"]) >= count:
                    break
                if not too_soon(artist_key(row["unit"].get("artist", ""))):
                    waiting.remove(row)
                    choose(row, f" (its artist is {window} or more songs back now)")
                    changed = True

    batch_size = max(3 * count, 10)
    pending, examined, batches = list(candidates), {path_key(selected)}, 0
    while len(result["chosen"]) < count and batches < max_batches:
        pending = [path for path in dict.fromkeys(pending) if path_key(path) not in examined]
        if not pending and more:
            pending = [path for path in dict.fromkeys(more(list(result["chosen"]))) if path_key(path) not in examined]
            result["lists"] += 1 if pending else 0
        if not pending:
            break
        batch, pending = pending[:batch_size], pending[batch_size:]
        examined.update(path_key(path) for path in batch)
        batches += 1
        trace.say(f"Candidates for {selected_unit['label']!r}: batch {batches} of at most {max_batches}, {len(batch)} "
                  f"track(s); {len(result['chosen'])} of {count} chosen so far; Character "
                  f"{'off' if strictness is None else 'within ' + trace.number(strictness)}; Intent "
                  f"{'off' if perspective is None else perspective + (', borderline accepted' if accept_borderline else '')}; "
                  + (f"no artist repeat within {window}: the last artists {placed[-window:]}, the next {following}"
                     + (f", waiting {[row['unit']['label'] for row in waiting]}" if waiting else "") + "."
                     if window else "artists may repeat."))
        result["examined"] += len(batch)
        units = [selected_unit] + resolve(batch)
        step("Rating new music")
        rate_missing(units, cache, ask, model=model, progress=rating_progress(step, "Rating new music"))
        entries = [cache.get(unit["key"]) for unit in units]
        if perspective is None:
            verdicts = {}  # Intent is off: the profile alone decides
        elif result["intent"]:  # a second batch is judged against the intent stated for the first
            step(f"Checking the new tracks: asking the AI about {len(batch)} tracks", 0.1)
            judged = checks.judge(result["intent"], units[0], entries[0], units[1:], entries[1:], ask, perspective)
            verdicts = {number + 1: verdict for number, verdict in judged.items()}
        elif name:
            step(f"Checking the new tracks: asking the AI about {len(batch)} tracks", 0.1)
            result["intent"], verdicts, result["name"] = checks.describe(units, entries, ask, perspective)
        else:
            step(f"Checking the new tracks: asking the AI about {len(batch)} tracks", 0.1)
            result["intent"], verdicts = checks.state_intent(units, entries, ask, perspective)
        result["seed_entry"] = result["seed_entry"] or entries[0]
        if batches == 1 and perspective is not None:
            trace.say(f"What {selected_unit['label']!r} is about ({perspective} perspective"
                      f"{', as stated before' if intent else ''}): {result['intent']}"
                      + (f"; name: {result['name']}" if result["name"] else ""))
        vector_entries = [reference] + entries[1:] if reference else entries
        analysis = analyze(units, vector_entries, verdicts, cache.library(), strictness, perspective, scale_entries)
        if not analysis["ready"]:
            trace.say("Candidates: too few rated tracks to measure"
                      + ("; the first ones are taken unchecked." if not result["checked"] else "; the search ends."))
            if not result["checked"]:
                for unit in units[1:]:  # unchecked, but spaced as the checked ones
                    if len(result["chosen"]) >= count:
                        break
                    row = {"unit": unit, "entry": cache.get(unit["key"])}
                    if too_soon(artist_key(unit.get("artist", ""))):
                        waiting.append(row)
                        continue
                    choose(row, " (unchecked)")
                    take_waiting()
                return result
            break
        result["checked"] = True
        for row in analysis["rows"][1:]:
            if len(result["chosen"]) >= count:
                break
            path = row["unit"]["path"]
            if not passes(row, strictness, accept_borderline, perspective is not None):
                reason = turned_down_reason(row, strictness, accept_borderline, perspective is not None)
                result["not_fitting"].append({"path": path, "label": row["unit"]["label"], "reason": reason})
                trace.say(f"  passed over {row['unit']['label']!r}: doesn't fit ({reason}).")
                continue
            if too_soon(artist_key(row["unit"].get("artist", ""))):
                trace.say(f"  waiting {row['unit']['label']!r}: fits, but its artist plays within {window} songs.")
                waiting.append(row)
                continue
            choose(row)
            take_waiting()
    trace.say(f"Candidates for {selected_unit['label']!r}: {len(result['chosen'])} of {count} chosen from "
              f"{result['examined']} examined in {batches} batch(es) and {result['lists']} list(s); "
              f"{len(result['not_fitting'])} didn't fit"
              + (f"; {len(waiting)} fitting song(s) left waiting, their artist too close: "
                 f"{[row['unit']['label'] for row in waiting]}" if waiting else "") + ".")
    return result


def drift_reference(reference: dict, added: Sequence[Optional[dict]], half_life: float) -> dict:
    """A Radio station's profile after songs were added: it moves towards each added song in turn, so that it has
    gone half the way to where the station went after `half_life` songs, whatever the refill size. Later songs
    count more. half_life 0 keeps the picked song's profile."""
    moved = dict(reference)
    if not half_life or half_life <= 0:
        return moved
    step = 1 - 0.5 ** (1 / half_life)
    for entry in added:
        if not entry:
            continue
        for key in dimensions.ALL_KEYS:
            if isinstance(entry.get(key), (int, float)) and isinstance(moved.get(key), (int, float)):
                moved[key] = (1 - step) * float(moved[key]) + step * float(entry[key])
    return moved
