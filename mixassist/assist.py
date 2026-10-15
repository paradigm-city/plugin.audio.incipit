"""Tidying up a mix: find the tracks that don't fit what the seed is about, and replace them from submixes.

tidy_up() returns a plan and changes nothing; the caller applies it (saved mix, playlist) and records it.
Everything outside the package is passed in: resolve (paths -> units), fetch_mix (MusicIP), ask (Claude).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

from mixassist import checks, fit
from mixassist.cache import RatingCache, normalize
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

Resolve = Callable[[Sequence[str]], List[dict]]
FetchMix = Callable[[str, int], List[str]]


def path_key(path: str) -> str:
    return (path or "").replace("\\", "/").strip().lower()


def artist_key(artist: str) -> str:
    """Artist names compared loosely: "Medeski Martin & Wood" and "Medeski, Martin and Wood" are the same."""
    return " ".join(word for word in normalize(artist).split() if word not in ("and", "the"))


def analyze(units: Sequence[dict], entries: Sequence[Optional[dict]], verdicts: Dict[int, dict],
            library: List[dict], strictness: float = DEFAULT_STRICTNESS) -> Dict[str, object]:
    """Per track: weighted misfit against the seed, relative to the mix's median, the AI's verdict and a status."""
    seed = entries[0]
    vectors = [entry for entry in entries if entry]
    if not seed or len(vectors) < 5:
        return {"rows": [], "weights": {}, "spreads": {}, "typical": 1.0, "ready": False}
    spreads = fit.mix_spreads(vectors)
    weights = fit.seed_weights(seed, library)
    weighted = fit.weighted_spreads(spreads, weights)
    inverse = fit.inverse_correlation(library)
    rows = []
    for position, (unit, entry) in enumerate(zip(units, entries), start=1):
        row = {"position": position, "unit": unit, "entry": entry}
        row.update(verdicts.get(position, {"verdict": "", "reason": ""}))
        if entry:
            row["misfit"], deviations = fit.misfit(entry, seed, weighted, inverse)
            row["why"] = fit.reason(entry, seed, deviations)
            row["guessed"] = entry.get("familiarity", 1) == 0
        rows.append(row)
    typical = max(MIN_TYPICAL_MISFIT, median([row["misfit"] for row in rows[1:] if "misfit" in row]))
    for row in rows:
        if "misfit" not in row:
            row["status"] = "unrated"
            continue
        row["relative"] = row["misfit"] / typical
        vector_flag = row["position"] > 1 and row["relative"] > strictness
        holistic_flag = row["verdict"] == "outlier"
        if row["position"] == 1:
            row["status"] = "seed"
        elif vector_flag and holistic_flag:
            row["status"] = "outlier"  # both signals agree; guessed units included (act on the available facts)
        elif vector_flag or holistic_flag:
            row["status"] = "flagged"
        elif row["verdict"] == "borderline":
            row["status"] = "borderline"
        else:
            row["status"] = "fits"
    return {"rows": rows, "weights": weights, "spreads": weighted, "inverse": inverse, "typical": typical,
            "ready": True}


def clearly_fitting(rows: Sequence[dict], strictness: float) -> set:
    fitting = {1}
    for row in rows:
        if row.get("relative") is not None and row["relative"] <= strictness and row.get("verdict") == "fits":
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


def pick(candidates: Sequence[dict], strictness: float, taken: set, blocked: set) -> Optional[dict]:
    passing = [c for c in candidates
               if c.get("relative") is not None and c["relative"] <= strictness and c.get("verdict") == "fits"
               and path_key(c["path"]) not in taken and artist_key(c.get("artist", "")) not in blocked]
    return min(passing, key=lambda c: c["relative"]) if passing else None


def tidy_up(paths: Sequence[str], cache: RatingCache, ask: Ask, resolve: Resolve, fetch_mix: FetchMix,
            intent: str = "", strictness: float = DEFAULT_STRICTNESS, artist_window: int = ARTIST_WINDOW,
            model: str = "", progress: Optional[Callable[[str], None]] = None,
            find_replacements: bool = True) -> dict:
    """A plan for the mix: the intent, every track's status, and the replacements to make.

    With find_replacements=False only the tracks that don't fit are found ("show only")."""
    def step(text: str) -> None:
        if progress:
            progress(text)

    paths = list(paths)
    step("Looking up the tracks")
    units = resolve(paths)
    step("Rating new music")
    rate_missing(units, cache, ask, model=model)
    entries = [cache.get(unit["key"]) for unit in units]

    step("Working out what this mix is about")
    if intent:
        judged = checks.judge(intent, units[0], entries[0], units[1:], entries[1:], ask)
        verdicts = {position + 1: verdict for position, verdict in judged.items()}
        verdicts[1] = {"verdict": "fits", "reason": ""}
        intent_source = "listener"
    else:
        intent, verdicts = checks.state_intent(units, entries, ask)
        intent_source = "ai"

    analysis = analyze(units, entries, verdicts, cache.library(), strictness)
    rows = analysis["rows"]
    outliers = [row["position"] for row in rows if row.get("status") == "outlier"]
    plan = {"intent": intent, "intent_source": intent_source, "rows": rows, "outliers": outliers, "changes": [],
            "removed": [], "paths": paths, "rebuild_suggested": False}
    if not analysis["ready"] or not outliers or not find_replacements:
        return plan
    plan["rebuild_suggested"] = len(outliers) > REBUILD_SHARE * (len(paths) - 1)

    step("Finding replacements")
    fitting = clearly_fitting(rows, strictness)
    examined = {path_key(path) for path in paths}  # in the mix or already offered as a candidate
    mixes: Dict[int, Optional[List[str]]] = {}

    def musicip_mix(position: int) -> Optional[List[str]]:
        """MusicIP's mix for a track of the mix (fetched once, as large as MusicIP allows); None if rejected."""
        if position not in mixes:
            try:
                mixes[position] = list(fetch_mix(paths[position - 1], MUSICIP_MAX_MIX))
            except Exception:
                mixes[position] = None
        return mixes[position]

    def fresh(tracks: Optional[Sequence[str]], limit: int) -> List[str]:
        """The first tracks not yet in the mix or offered; MusicIP lists the closest first."""
        result: List[str] = []
        for track in tracks or []:
            if len(result) >= limit:
                break
            if path_key(track) not in examined:
                examined.add(path_key(track))
                result.append(track)
        return result

    def evaluate(candidate_paths: List[str]) -> Dict[str, dict]:
        """Both signals for the candidates, measured against the master mix (one AI call for all of them)."""
        if not candidate_paths:
            return {}
        step("Checking the replacements")
        candidates = resolve(candidate_paths)
        rate_missing(candidates, cache, ask, model=model)
        candidate_entries = [cache.get(unit["key"]) for unit in candidates]
        candidate_verdicts = checks.judge(intent, units[0], entries[0], candidates, candidate_entries, ask)
        scored: Dict[str, dict] = {}
        for number, (unit, entry) in enumerate(zip(candidates, candidate_entries), start=1):
            verdict = candidate_verdicts.get(number, {})
            candidate = {"path": unit["path"], "label": unit["label"], "artist": unit.get("artist", ""),
                         "verdict": verdict.get("verdict", ""), "reason": verdict.get("reason", "")}
            if entry:
                misfit, _ = fit.misfit(entry, entries[0], analysis["spreads"], analysis["inverse"])
                candidate["relative"] = misfit / analysis["typical"]
            scored[unit["path"]] = candidate
        return scored

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
            choice, origin = pick([scored[p] for p in options if p in scored], strictness, taken, blocked), source
            if choice is None:
                choice = pick(shared, strictness, taken, blocked)
                origin = "seed" if choice and choice["path"] in fallback else source
            if choice is None:
                unfilled.append(position)
                continue
            row = rows[position - 1]
            taken.add(path_key(choice["path"]))
            artists[position - 1] = choice["artist"]
            new_paths[position - 1] = choice["path"]
            plan["changes"].append({"position": position, "old": paths[position - 1],
                                    "old_label": row["unit"]["label"], "reason": row.get("reason") or row.get("why", ""),
                                    "new": choice["path"], "new_label": choice["label"], "source": origin})
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
