"""Rating units that are not cached yet: requests in batches, answers validated and stored in the cache."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from mixassist.cache import RatingCache
from mixassist.claude import USAGE_LIMIT, ClaudeError
from mixassist.dimensions import ALL_KEYS, ERA_KEY, SCALE_KEYS, build_system_prompt, output_schema

ALBUMS_PER_REQUEST = 20
TRACKS_PER_REQUEST = 25
ALBUM_FIELDS = ("id", "artist", "album", "year", "genres", "tracks")
TRACK_FIELDS = ("id", "artist", "title", "album", "year", "genres")

# ask(system_prompt, schema, message) -> structured output; normally claude.ask with the CLI bound.
Ask = Callable[[str, dict, str], dict]


def user_message(kind: str, items: Sequence[dict]) -> str:
    if kind == "album":
        intro, fields = "Rate each of these albums as a whole.", ALBUM_FIELDS
    else:
        intro, fields = "Rate each of these tracks. They are single songs taken from compilations.", TRACK_FIELDS
    lines = [json.dumps({field: item.get(field, "") for field in fields}, ensure_ascii=False) for item in items]
    return intro + "\n\n" + "\n".join(lines)


def batches(units: Iterable[dict]) -> List[Tuple[str, List[dict]]]:
    """Units without duplicates, grouped by kind into request-sized batches, each item with a short id."""
    by_key: Dict[str, dict] = {}
    for unit in units:
        by_key.setdefault(unit["key"], unit)
    result = []
    for kind, size in (("album", ALBUMS_PER_REQUEST), ("track", TRACKS_PER_REQUEST)):
        group = [unit for unit in by_key.values() if unit["kind"] == kind]
        for start in range(0, len(group), size):
            result.append((kind, group[start:start + size]))
    return result


def clamp_int(value, low: int, high: int) -> Optional[int]:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(low, min(high, number))


def parse_ratings(payload: Optional[dict], expected_ids: Sequence[str]) -> Dict[str, dict]:
    """Ratings for the expected ids; entries with unknown ids or missing values are dropped, values clamped."""
    ratings: Dict[str, dict] = {}
    for entry in (payload or {}).get("ratings", []):
        item_id = str(entry.get("id", ""))
        if item_id not in expected_ids:
            continue
        rating = {"familiarity": clamp_int(entry.get("familiarity"), 0, 2)}
        for key in SCALE_KEYS:
            rating[key] = clamp_int(entry.get(key), 0, 10)
        rating[ERA_KEY] = clamp_int(entry.get(ERA_KEY), 1900, 2030)
        if any(rating[key] is None for key in ("familiarity",) + ALL_KEYS):
            continue
        rating["description"] = str(entry.get("character", ""))[:200]
        ratings[item_id] = rating
    return ratings


def rate_missing(units: Sequence[dict], cache: RatingCache, ask: Ask, model: str = "",
                 parallel: int = 3, progress: Optional[Callable[[int, int], None]] = None) -> int:
    """Rate every unit the cache does not have yet; returns how many were stored.

    Stops early when the subscription's usage limit is reached and raises that ClaudeError afterwards, so what
    was rated is kept."""
    cached = cache.get_many(unit["key"] for unit in units)
    work = batches(unit for unit in units if unit["key"] not in cached)
    if not work:
        return 0
    system_prompt, schema = build_system_prompt(), output_schema()
    stored, done, limit_error = 0, 0, None

    def run(batch):
        kind, group = batch
        items = [dict(unit["item"], id=f"u{index}") for index, unit in enumerate(group)]
        return batch, ask(system_prompt, schema, user_message(kind, items))

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = [pool.submit(run, batch) for batch in work]
        for future in as_completed(futures):
            done += 1
            try:
                (kind, group), payload = future.result()
            except ClaudeError as exc:
                if exc.kind == USAGE_LIMIT:
                    limit_error = exc
                    for other in futures:
                        other.cancel()
                continue
            ratings = parse_ratings(payload, [f"u{index}" for index in range(len(group))])
            for index, unit in enumerate(group):
                rating = ratings.get(f"u{index}")
                if rating:
                    cache.put(unit["key"], rating, model=model, source="mixassist", kind=kind)
                    stored += 1
            if progress:
                progress(done, len(work))
    if limit_error:
        raise limit_error
    return stored
