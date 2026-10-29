# -*- coding: utf-8 -*-
"""Kodi context menu entry for creating an Incipit mix from a library song."""

from __future__ import annotations

import sys
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui

from logs import ADDON_ID


ADDON = xbmcaddon.Addon(ADDON_ID)


class MusicIPContextError(Exception):
    """Raised for user-facing context menu failures."""


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def notify(message: str, level=xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(ADDON.getAddonInfo("name"), message, level)


def get_setting(name: str, default: str = "") -> str:
    try:
        value = ADDON.getSetting(name)
        return value if value != "" else default
    except Exception:
        return default


def get_setting_int(name: str, default: int) -> int:
    raw = get_setting(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_playlist_size() -> int:
    size = get_setting_int("playlist_size", 20)
    return max(1, size)


def get_context_seed_song() -> str:
    list_item = getattr(sys, "listitem", None)
    if list_item is None:
        raise MusicIPContextError("Kodi did not provide the selected list item.")

    try:
        music_tag = list_item.getMusicInfoTag()
        seed_song = (music_tag.getURL() or "").strip()
    except Exception as exc:
        raise MusicIPContextError("Kodi did not provide a valid song URL for the selected item.") from exc

    if not seed_song:
        raise MusicIPContextError("The selected music item does not provide a usable song URL.")

    return seed_song


def build_browse_url(seed: str, size: int) -> str:
    query = urlencode({
        "action": "browse_mix",
        "seed": seed,
        "size": str(size),
    })
    return f"plugin://{ADDON_ID}/?{query}"


def open_mix(seed: str, size: int) -> None:
    url = build_browse_url(seed, size)
    xbmc.executebuiltin(f"ActivateWindow(Music,{url},return)")


def main() -> None:
    try:
        seed_song = get_context_seed_song()
        open_mix(seed_song, get_playlist_size())
    except MusicIPContextError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(str(exc), xbmc.LOGERROR)
    except Exception as exc:  # pragma: no cover - defensive logging in Kodi runtime
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(f"Unhandled context item error: {exc}", xbmc.LOGERROR)


if __name__ == "__main__":
    main()
