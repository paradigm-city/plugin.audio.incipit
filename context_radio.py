# -*- coding: utf-8 -*-
"""Kodi context menu entry for starting Incipit radio from a library song."""

from __future__ import annotations

from urllib.parse import urlencode

import xbmc
import xbmcgui

from context_mix import ADDON_ID, MusicIPContextError, get_context_seed_song, log, notify


def build_radio_url(seed: str) -> str:
    query = urlencode({
        "action": "radio_start_seed",
        "seed": seed,
    })
    return f"plugin://{ADDON_ID}/?{query}"


def start_radio(seed: str) -> None:
    # Run as an action, not a folder: the radio starts and the current view stays.
    xbmc.executebuiltin(f"RunPlugin({build_radio_url(seed)})")


def main() -> None:
    try:
        start_radio(get_context_seed_song())
    except MusicIPContextError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(str(exc), xbmc.LOGERROR)
    except Exception as exc:  # pragma: no cover - defensive logging in Kodi runtime
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(f"Unhandled context item error: {exc}", xbmc.LOGERROR)


if __name__ == "__main__":
    main()
