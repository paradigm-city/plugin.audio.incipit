"""AI Mix Assist step by step: every AI request with its text and answer, the ratings, both checks per track and
why each candidate was taken or passed over.

The package reports with say(); the add-on decides where it goes (set_sink: kodi.log, when AI Mix Assist logging
is on), so the package keeps working without it (tests, the style pilot). Callers ask active() before building a
long message.
"""

from __future__ import annotations

import hashlib
from typing import Callable, Optional

_SINK: Optional[Callable[[str], None]] = None
_ACTIVE: Callable[[], bool] = lambda: True
_PROMPTS_SHOWN = set()


def set_sink(sink: Optional[Callable[[str], None]], active: Callable[[], bool] = lambda: True) -> None:
    global _SINK, _ACTIVE
    _SINK, _ACTIVE = sink, active


def active() -> bool:
    try:
        return _SINK is not None and bool(_ACTIVE())
    except Exception:
        return False


def say(message: str) -> None:
    """Report a step; never fails the work it describes."""
    if not active():
        return
    try:
        _SINK(message)
    except Exception:
        pass


def prompt_label(system_prompt: str) -> str:
    """A system prompt in full the first time (per process), then by its short hash only: the rating prompt is long
    and the same for every request."""
    digest = hashlib.sha1(system_prompt.encode("utf-8")).hexdigest()[:8]
    if digest in _PROMPTS_SHOWN:
        return f"system prompt #{digest} (in full earlier in the log)"
    _PROMPTS_SHOWN.add(digest)
    return f"system prompt #{digest}:\n{system_prompt}"


def number(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"
