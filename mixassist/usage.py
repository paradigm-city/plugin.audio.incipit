"""AI Mix Assist: what it costs and what it does, counted locally (the statistics in Settings).

The package reports events with emit(); the add-on decides where they go (set_sink), so the package keeps working
without it (tests, the style pilot). UsageLog keeps the events in a small SQLite file shared by the add-on and its
service; summarise() and daily() add them up for the report.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from typing import Callable, Dict, Iterable, List, Optional, Tuple

_SINK: Optional[Callable[..., None]] = None

Event = Tuple[int, str, dict]  # time, kind, fields


def set_sink(sink: Optional[Callable[..., None]]) -> None:
    global _SINK
    _SINK = sink


def emit(kind: str, **fields) -> None:
    """Report an event; never fails the work it describes."""
    if _SINK is None:
        return
    try:
        _SINK(kind, **fields)
    except Exception:
        pass


class UsageLog:
    """Events in SQLite, one connection per call (the add-on, the service and their threads write at once)."""

    def __init__(self, path: str):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("CREATE TABLE IF NOT EXISTS events (ts INTEGER NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS events_ts ON events (ts)")
        return connection

    def record(self, kind: str, ts: Optional[int] = None, **fields) -> None:
        with closing(self.connect()) as connection:
            connection.execute("INSERT INTO events VALUES (?, ?, ?)",
                               (int(ts if ts is not None else time.time()), kind, json.dumps(fields)))
            connection.commit()

    def events(self, since: int = 0) -> List[Event]:
        if not os.path.exists(self.path):
            return []
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT ts, kind, data FROM events WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
        return [(ts, kind, json.loads(data)) for ts, kind, data in rows]

    def prune(self, keep_days: int = 365, now: Optional[float] = None) -> int:
        if not os.path.exists(self.path):
            return 0
        cutoff = int((now if now is not None else time.time()) - keep_days * 86400)
        with closing(self.connect()) as connection:
            removed = connection.execute("DELETE FROM events WHERE ts < ?", (cutoff,)).rowcount
            connection.commit()
        return removed

    def clear(self) -> None:
        if os.path.exists(self.path):
            with closing(self.connect()) as connection:
                connection.execute("DELETE FROM events")
                connection.commit()


PURPOSES = ("rating", "describing", "judging")


def summarise(events: Iterable[Event]) -> Dict[str, float]:
    """The numbers of the report for a set of events (missing ones count 0)."""
    total: Dict[str, float] = {}
    seconds: List[float] = []

    def add(key: str, value: float = 1) -> None:
        total[key] = total.get(key, 0) + (value or 0)

    for _ts, kind, fields in events:
        if kind == "ai_call":
            add("requests")
            add(f"requests_{fields.get('purpose') or 'other'}")
            if not fields.get("ok"):
                add("failed")
                add(f"failed_{fields.get('failure') or 'failed'}")
            for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd"):
                add(key, float(fields.get(key) or 0))
            if fields.get("seconds") is not None:
                seconds.append(float(fields["seconds"]))
        elif kind == "cache":
            add("cache_hits", fields.get("hits", 0))
            add("cache_misses", fields.get("misses", 0))
        elif kind == "rated":
            add("rated", fields.get("count", 0))
        elif kind == "mix":
            event = fields.get("event")
            if event == "ai_tidy_up":
                add("tidy_ups")
                add("tidy_ups_automatic" if fields.get("automatic") else "tidy_ups_requested")
                add("judged", fields.get("judged", 0))
                add("replaced", fields.get("replaced", 0))
                add("removed", fields.get("removed", 0))
                if fields.get("replaced") or fields.get("removed"):
                    add("tidy_ups_changed")
            elif event == "ai_undone":
                add("undone")
            elif event == "intent_edited":
                add("intent_edited")
            elif event == "more_like_this":
                add("more_like_this")
                add("more_added", fields.get("added", 0))
                add("more_skipped", fields.get("skipped", 0))
        elif kind == "radio":
            event = fields.get("event")
            if event == "start_check":
                add("radio_starts")
                add("radio_start_removed", fields.get("removed", 0))
            elif event == "refill" and fields.get("checked"):
                add("radio_refills")
                add("radio_kept", fields.get("added", 0))
                add("radio_skipped", fields.get("skipped", 0))
            elif event == "refill_unchecked":
                add("radio_unchecked")
                add(f"radio_unchecked_{fields.get('reason') or 'other'}")
            elif event == "nothing_fitted":
                add("radio_nothing_fitted")
            elif event == "musicip_failed":
                add("radio_musicip_failed")
    if seconds:
        total["seconds_average"] = sum(seconds) / len(seconds)
        total["seconds_longest"] = max(seconds)
    return total


def daily(events: Iterable[Event], days: int, now: float, keys: Iterable[str]) -> List[Dict[str, float]]:
    """summarise() per day for the last days (oldest first; local days, today last)."""
    keys = list(keys)
    today = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    starts = [today - (days - 1 - index) * 86400 for index in range(days)]
    buckets: List[List[Event]] = [[] for _ in starts]
    for event in events:
        for index in range(days - 1, -1, -1):
            if event[0] >= starts[index]:
                buckets[index].append(event)
                break
    return [{key: summarise(bucket).get(key, 0) for key in keys} for bucket in buckets]
