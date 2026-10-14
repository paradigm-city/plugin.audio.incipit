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
            model: str = "", progress: Optional[Callable[[str], None]] = None) -> dict:
    """A plan for the mix: the intent, every track's status, and the replacements to make."""
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
    plan = {"intent": intent, "intent_source": intent_source, "rows": rows, "changes": [], "removed": [],
            "paths": paths, "rebuild_suggested": False}
    outliers = [row["position"] for row in rows if row.get("status") == "outlier"]
    if not analysis["ready"] or not outliers:
        return plan
    plan["rebuild_suggested"] = len(outliers) > REBUILD_SHARE * (len(paths) - 1)

    step("Finding replacements")
    fitting = clearly_fitting(rows, strictness)
    excluded = {path_key(path) for path in paths}

    def fresh(tracks: Sequence[str]) -> List[str]:
        result, seen = [], set(excluded)
        for track in tracks:
            if path_key(track) not in seen:
                seen.add(path_key(track))
                result.append(track)
        return result

    gaps = []
    for position in outliers:
        seed_position = submix_seed_position(position, fitting)
        submix: List[str] = []
        while seed_position >= 1:
            try:
                submix = fetch_mix(paths[seed_position - 1], SUBMIX_SIZE)
                break
            except Exception:
                if seed_position == 1:
                    seed_position = 0
                    break
                seed_position = submix_seed_position(seed_position, fitting)
        gaps.append({"position": position, "seed_position": seed_position, "paths": fresh(submix)})
    try:
        fallback_paths = fresh(fetch_mix(paths[0], min(MUSICIP_MAX_MIX, SUBMIX_SIZE * FALLBACK_FACTOR)))
    except Exception:
        fallback_paths = []

    candidate_paths: List[str] = []
    for track in [p for gap in gaps for p in gap["paths"]] + fallback_paths:
        if track not in candidate_paths:
            candidate_paths.append(track)
    if not candidate_paths:
        plan["removed"] = outliers
        plan["paths"] = [path for index, path in enumerate(paths, start=1) if index not in outliers]
        return plan
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

    taken = set(excluded)
    artists = [unit.get("artist", "") for unit in units]
    for position in outliers:  # these tracks leave the mix, so their artists don't block anything
        artists[position - 1] = ""
    new_paths: List[Optional[str]] = list(paths)
    fallback = [scored[p] for p in fallback_paths if p in scored]
    for gap in gaps:
        blocked = nearby_artists(artists, gap["position"], artist_window)
        options = [scored[p] for p in gap["paths"] if p in scored]
        choice, source = pick(options, strictness, taken, blocked), "submix"
        if choice is None:
            choice, source = pick(fallback, strictness, taken, blocked), "seed"
        row = rows[gap["position"] - 1]
        if choice:
            taken.add(path_key(choice["path"]))
            artists[gap["position"] - 1] = choice["artist"]
            new_paths[gap["position"] - 1] = choice["path"]
            plan["changes"].append({"position": gap["position"], "old": paths[gap["position"] - 1],
                                    "old_label": row["unit"]["label"], "reason": row.get("reason") or row.get("why", ""),
                                    "new": choice["path"], "new_label": choice["label"], "source": source})
        else:
            new_paths[gap["position"] - 1] = None
            plan["removed"].append(gap["position"])
    plan["paths"] = [path for path in new_paths if path]
    return plan
