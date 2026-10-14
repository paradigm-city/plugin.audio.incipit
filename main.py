# -*- coding: utf-8 -*-
"""Kodi music add-on for MusicIP mixes."""

from __future__ import annotations

import calendar
import datetime
import glob
import hashlib
import json
import os
import random
import sqlite3
import re
import sys
import time
import unicodedata
from functools import partial
from urllib.parse import parse_qsl, quote_from_bytes, urlencode, unquote
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from mixassist import assist as mix_assist
from mixassist import cache as mix_assist_cache
from mixassist import claude as mix_assist_claude
from mixassist import library as mix_assist_library


ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and str(sys.argv[1]).lstrip("-").isdigit() else -1
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""

LAST_MIX_GENERATION_PARAMS: dict[str, dict] = {}
AUDIO_LIBRARY_FRESHNESS_CACHE = {"fetched_ts": 0, "payload": {}}
TRACK_METADATA_CACHE_SCHEMA_VERSION = 1
SONG_METADATA_PROPERTIES = [
    "title",
    "artist",
    "displayartist",
    "album",
    "albumartist",
    "genre",
    "file",
    "year",
    "duration",
    "track",
    "thumbnail",
    "fanart",
]
SONG_METADATA_SAFE_PROPERTIES = [
    "title",
    "artist",
    "album",
    "genre",
    "year",
    "duration",
    "thumbnail",
    "fanart",
]

KODI_MUSIC_TRACK_TEMPLATE_CACHE = None
KODI_MUSIC_TRACK_TEMPLATE_FALLBACK = "[%N. ]%A - %T"
KODI_MUSIC_TRACK_TEMPLATE_SETTING_CANDIDATES = [
    "musicfiles.trackformat",
    "musiclibrary.trackformat",
    "musicplayer.trackformat",
    "musicfiles.librarytrackformat",
]



class MusicIPError(Exception):
    """Raised for user-facing MusicIP failures."""


MUSICIP_KEYMAP_FILENAME = "musicip_mix_editing.xml"
MUSICIP_KEYMAP_CONTENT = r"""<?xml version="1.0" encoding="UTF-8"?>
<keymap>
  <MyMusicNav>
    <keyboard>
      <delete>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</delete>
      <del>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</del>
      <m>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_more_like_this)</m>
      <l>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_less_like_this)</l>
    </keyboard>
  </MyMusicNav>

  <window10502>
    <keyboard>
      <delete>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</delete>
      <del>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</del>
      <m>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_more_like_this)</m>
      <l>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_less_like_this)</l>
    </keyboard>
  </window10502>

  <MusicPlaylist>
    <keyboard>
      <delete>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</delete>
      <del>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</del>
      <m>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_more_like_this)</m>
      <l>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_less_like_this)</l>
    </keyboard>
  </MusicPlaylist>

  <MusicFiles>
    <keyboard>
      <delete>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</delete>
      <del>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_remove_from_mix)</del>
      <m>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_more_like_this)</m>
      <l>RunPlugin(plugin://plugin.audio.musicip/?action=keyboard_less_like_this)</l>
    </keyboard>
  </MusicFiles>
</keymap>
"""


def get_kodi_user_keymap_dir() -> str:
    path = xbmcvfs.translatePath("special://profile/keymaps")
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)
    return path


def get_musicip_user_keymap_path() -> str:
    return os.path.join(get_kodi_user_keymap_dir(), MUSICIP_KEYMAP_FILENAME)


def ensure_musicip_keymap_installed() -> None:
    target = get_musicip_user_keymap_path()
    current = ""
    try:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as fh:
                current = fh.read()
    except Exception as exc:
        log(f"Could not read existing MusicIP keymap: {exc}", xbmc.LOGWARNING)

    if current == MUSICIP_KEYMAP_CONTENT:
        return

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(MUSICIP_KEYMAP_CONTENT)
        xbmc.executebuiltin("ReloadKeymaps")
        log(f"Installed MusicIP keymap to {target} and reloaded keymaps.", xbmc.LOGINFO)
    except Exception as exc:
        log(f"Could not install MusicIP keymap to {target}: {exc}", xbmc.LOGERROR)


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def is_plugin_extended_logging_enabled() -> bool:
    return get_setting_bool("plugin_extended_logging", False)


def log_info(message: str) -> None:
    if is_plugin_extended_logging_enabled():
        log(message, xbmc.LOGINFO)


def log_library_freshness(message: str) -> None:
    # Library timestamp details belong to the consistency/repair system and follow the service logging setting.
    if get_setting_bool("service_extended_logging", False):
        log(message, xbmc.LOGINFO)


def addon_url(**query: str) -> str:
    return f"{BASE_URL}?{urlencode(query)}"


def run_plugin_url(**query: str) -> str:
    return f"RunPlugin({addon_url(**query)})"


def notify(message: str, level=xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(ADDON_NAME, message, level)


def get_setting(name: str, default: str = "") -> str:
    try:
        value = ADDON.getSetting(name)
        return value if value != "" else default
    except Exception:
        return default


def get_setting_bool(name: str, default: bool = False) -> bool:
    raw = get_setting(name, "true" if default else "false").strip().lower()
    return raw in ("true", "1", "yes", "on")


def get_setting_int(name: str, default: int) -> int:
    raw = get_setting(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_server_host() -> str:
    return get_setting("host", "localhost").strip() or "localhost"


def get_server_port() -> int:
    return get_setting_int("port", 10002)


def get_playlist_size() -> int:
    size = get_setting_int("playlist_size", 20)
    return max(1, size)


def get_timeout() -> int:
    timeout = get_setting_int("timeout", 10)
    return max(1, timeout)


def get_mix_style_preference() -> int:
    value = get_setting_int("mix_style_preference", 2)
    return max(0, min(10, value))


def get_mix_style_api_value() -> int:
    # MusicIP API style range: 0..200.
    # UI scale: 0..10 in steps of 1.
    return get_mix_style_preference() * 20


def get_mix_style_label(value: int | None = None) -> str:
    raw_value = get_mix_style_preference() if value is None else int(value)
    ui_value = max(0, min(10, raw_value))
    labels = {
        0: "ignore",
        1: "barely noticeable",
        2: "weak preference",
        3: "light preference",
        4: "mild preference",
        5: "medium preference",
        6: "balanced preference",
        7: "clear preference",
        8: "strong preference",
        9: "very strong preference",
        10: "strongly prefer",
    }
    return labels.get(ui_value, f"{ui_value}/10")


def get_mix_variety() -> int:
    return max(0, min(9, get_setting_int("mix_variety", 0)))


def get_mix_reject_size() -> int:
    return max(0, min(20, get_setting_int("mix_reject_size", 0)))


def get_mix_filter() -> str:
    return get_setting("mix_filter", "").strip()


def get_effective_mix_parameters(size_override: int | None = None) -> dict:
    size = max(1, int(size_override or get_playlist_size()))
    reject_size = get_mix_reject_size()
    style_ui = get_mix_style_preference()
    return {
        "size": size,
        "sizetype": "tracks",
        "style": style_ui * 20,
        "style_ui": style_ui,
        "style_label": get_mix_style_label(style_ui),
        "variety": get_mix_variety(),
        "filter": get_mix_filter(),
        "rejectsize": reject_size,
        "rejecttype": "tracks",
        "content": "text",
    }


def normalize_mix_parameters(params: dict) -> dict:
    normalized = dict(params or {})
    normalized["size"] = max(1, min(100, int(normalized.get("size") or get_playlist_size())))
    normalized["style_ui"] = max(0, min(10, int(normalized.get("style_ui") or 0)))
    normalized["style"] = max(0, min(200, int(normalized["style_ui"]) * 20))
    normalized["style_label"] = get_mix_style_label(int(normalized["style_ui"]))
    normalized["variety"] = max(0, min(9, int(normalized.get("variety") or 0)))
    # "Restrict to seed genre" was removed: genre tags are too inconsistent to mean much.
    # Parameters recorded by older versions may still contain it.
    normalized.pop("mixgenre", None)
    normalized["filter"] = str(normalized.get("filter") or "").strip()
    normalized["rejectsize"] = max(0, min(20, int(normalized.get("rejectsize") or 0)))
    normalized["rejecttype"] = "tracks"
    normalized["sizetype"] = "tracks"
    normalized["content"] = "text"
    return normalized


def compact_mix_generation_parameters(params: dict) -> dict:
    normalized = normalize_mix_parameters(params)
    return {
        "size": int(normalized.get("size") or 0),
        "sizetype": "tracks",
        "style_ui": int(normalized.get("style_ui") or 0),
        "style": int(normalized.get("style") or 0),
        "style_label": str(normalized.get("style_label") or ""),
        "variety": int(normalized.get("variety") or 0),
        "filter": str(normalized.get("filter") or ""),
        "rejectsize": int(normalized.get("rejectsize") or 0),
        "rejecttype": "tracks",
        "content": "text",
    }


def remember_mix_generation_parameters(seed: str, size: int, params: dict) -> None:
    try:
        LAST_MIX_GENERATION_PARAMS[mix_cache_key(seed, size)] = compact_mix_generation_parameters(params)
    except Exception:
        pass


def pop_mix_generation_parameters(seed: str, size: int) -> dict:
    try:
        return LAST_MIX_GENERATION_PARAMS.pop(mix_cache_key(seed, size), {})
    except Exception:
        return {}


def build_mix_parameter_summary(params: dict) -> str:
    params = normalize_mix_parameters(params)
    reject_size = int(params.get("rejectsize") or 0)
    reject_text = (
        f"do not repeat artist within {reject_size} tracks"
        if reject_size > 0
        else "disabled"
    )
    filter_value = str(params.get("filter") or "").strip() or "<none>"

    lines = [
        f"Size: {int(params.get('size') or 0)} tracks",
        f"Style: {int(params.get('style_ui') or 0)}/10 - {params.get('style_label')}",
        f"MusicIP style value: {int(params.get('style') or 0)}",
        f"Variety: {int(params.get('variety') or 0)}",
        f"Filter: {filter_value}",
        f"Artist repeat: {reject_text}",
    ]
    return "\n".join(lines)


def dialog_slider_int(default_value: int, heading: str, minimum: int, maximum: int, step: int = 1) -> int | None:
    default_value = max(minimum, min(maximum, int(default_value)))
    try:
        result = xbmcgui.Dialog().slider(
            heading,
            default_value,
            type=getattr(xbmcgui, "SLIDER_CONTROL_TYPE_INT", 1),
            min=minimum,
            delta=step,
            max=maximum,
        )
    except Exception:
        result = dialog_number(default_value, heading, minimum, maximum)

    if result is None:
        return None

    try:
        value = int(round(float(result)))
    except (TypeError, ValueError):
        return None

    if value < minimum or value > maximum:
        return None

    return max(minimum, min(maximum, value))


def dialog_number(default_value: int, heading: str, minimum: int, maximum: int) -> int | None:
    value = xbmcgui.Dialog().numeric(0, heading, str(default_value))
    if value is None or str(value).strip() == "":
        return None

    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return max(minimum, min(maximum, parsed))


def edit_mix_generation_parameter(params: dict, option: int) -> dict:
    updated = normalize_mix_parameters(params)

    if option == 1:
        value = dialog_slider_int(int(updated["size"]), "Mix size in tracks", 1, 100, 1)
        if value is not None:
            updated["size"] = value

    elif option == 2:
        value = dialog_slider_int(int(updated["style_ui"]), "Style preference 0..10", 0, 10, 1)
        if value is not None:
            updated["style_ui"] = value

    elif option == 3:
        value = dialog_slider_int(int(updated["variety"]), "Variety 0..9", 0, 9, 1)
        if value is not None:
            updated["variety"] = value

    elif option == 4:
        current = str(updated.get("filter") or "")
        try:
            value = xbmcgui.Dialog().input("MusicIP filter", defaultt=current)
        except TypeError:
            value = xbmcgui.Dialog().input("MusicIP filter", current)
        if value is not None:
            updated["filter"] = str(value).strip()

    elif option == 5:
        value = dialog_slider_int(int(updated["rejectsize"]), "Do not repeat artist within N tracks (0..20)", 0, 20, 1)
        if value is not None:
            updated["rejectsize"] = value

    return normalize_mix_parameters(updated)


def confirm_mix_generation(params: dict) -> dict | None:
    current = normalize_mix_parameters(params)

    while True:
        filter_value = str(current.get("filter") or "").strip() or "<none>"
        reject_size = int(current.get("rejectsize") or 0)
        reject_label = (
            f"do not repeat artist within {reject_size} tracks"
            if reject_size > 0
            else "disabled"
        )

        choices = [
            "Generate mix",
            f"Size: {int(current.get('size') or 0)} tracks",
            f"Style: {int(current.get('style_ui') or 0)}/10 - {current.get('style_label')} (API {int(current.get('style') or 0)})",
            f"Variety: {int(current.get('variety') or 0)}",
            f"Filter: {filter_value}",
            f"Artist repeat: {reject_label}",
        ]

        choice = xbmcgui.Dialog().select(
            "Generate MusicIP mix",
            choices,
        )

        if choice < 0:
            return None
        if choice == 0:
            return normalize_mix_parameters(current)

        current = edit_mix_generation_parameter(current, choice)


def build_musicip_parameter_query(seed_song: str, params: dict) -> str:
    params = normalize_mix_parameters(params)
    # MusicIP on Windows expects the seed path in the Windows code page (cp1252), which also has œ, ’, “ ”, – and …
    encoded_seed = quote_from_bytes(seed_song.encode("cp1252", errors="replace"))

    query_params = {
        "size": str(int(params.get("size") or get_playlist_size())),
        "sizeType": "tracks",
        "style": str(int(params.get("style") or 0)),
        "variety": str(int(params.get("variety") or 0)),
        "mixgenre": "false",
        "content": "text",
    }

    filter_value = str(params.get("filter") or "").strip()
    if filter_value:
        query_params["filter"] = filter_value

    reject_size = int(params.get("rejectsize") or 0)
    if reject_size > 0:
        query_params["rejectsize"] = str(reject_size)
        query_params["rejectType"] = "tracks"

    return f"song={encoded_seed}&{urlencode(query_params)}"


def parse_args() -> dict[str, str]:
    if len(sys.argv) < 3:
        return {}
    return dict(parse_qsl(sys.argv[2].lstrip("?")))


def get_profile_dir() -> str:
    profile = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdirs(profile)
    return profile


def discovery_state_path() -> str:
    return os.path.join(get_profile_dir(), "discovery_mode_state.json")


DISCOVERY_BUFFER_SIZE = 10


def finish_plugin_action(success: bool = True) -> None:
    try:
        if HANDLE >= 0:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=success, cacheToDisc=False)
    except Exception:
        pass


def get_music_playlist() -> xbmc.PlayList:
    return xbmc.PlayList(xbmc.PLAYLIST_MUSIC)


def discovery_song_label_from_song(song: dict) -> str:
    title = str(song.get("title") or "").strip()
    artist = song.get("artist") or song.get("displayartist") or ""
    if isinstance(artist, list):
        artist = ", ".join(str(item) for item in artist if str(item).strip())
    artist = str(artist or "").strip()

    if artist and title:
        return f"{artist} - {title}"
    return title or path_to_label(str(song.get("file") or ""))


def get_discovery_library_songs() -> list[dict]:
    log("Discovery mode: UI loading Kodi music library songs for direct playlist start.", xbmc.LOGINFO)
    try:
        result = execute_jsonrpc(
            "AudioLibrary.GetSongs",
            {
                "properties": ["title", "artist", "displayartist", "album", "duration", "file"],
                "sort": {"method": "random"},
            },
        )
    except Exception as exc:
        log(f"Discovery mode: UI AudioLibrary.GetSongs with random sort failed: {exc}", xbmc.LOGWARNING)
        try:
            result = execute_jsonrpc(
                "AudioLibrary.GetSongs",
                {"properties": ["title", "artist", "displayartist", "album", "duration", "file"]},
            )
        except Exception as exc2:
            log(f"Discovery mode: UI AudioLibrary.GetSongs fallback failed: {exc2}", xbmc.LOGERROR)
            return []

    songs = result.get("songs") or []
    usable = [song for song in songs if str(song.get("file") or "").strip()]
    log(f"Discovery mode: UI loaded {len(usable)} usable song(s).", xbmc.LOGINFO)
    return usable


def calculate_discovery_offset(duration: int, excerpt_seconds: int, offset_percent: int) -> int:
    try:
        duration = int(duration or 0)
        excerpt_seconds = int(excerpt_seconds or 0)
        offset_percent = int(offset_percent or 0)
    except Exception:
        return 0

    if duration <= 0:
        return 0

    offset_seconds = int(duration * (offset_percent / 100.0))
    if duration > excerpt_seconds + 2:
        return min(offset_seconds, max(0, duration - excerpt_seconds - 2))
    return 0


def discovery_playlist_item(entry: dict) -> xbmcgui.ListItem:
    label = str(entry.get("label") or path_to_label(str(entry.get("file") or "")))
    item = xbmcgui.ListItem(label=label, offscreen=True)
    try:
        item.setProperty("StartOffset", str(int(entry.get("offset") or 0)))
        item.setProperty("MusicIP.Discovery", "true")
        item.setProperty("MusicIP.DiscoveryFile", str(entry.get("file") or ""))
        item.setProperty("MusicIP.DiscoveryOffset", str(int(entry.get("offset") or 0)))
    except Exception:
        pass
    apply_music_metadata(item, label)
    return item


def build_discovery_queue_from_library(excerpt_seconds: int, offset_percent: int, size: int = DISCOVERY_BUFFER_SIZE) -> list[dict]:
    songs = get_discovery_library_songs()
    if not songs:
        return []

    queue: list[dict] = []
    attempts = 0
    max_attempts = max(50, size * 10)

    while len(queue) < size and attempts < max_attempts:
        attempts += 1
        song = random.choice(songs)
        file_path = str(song.get("file") or "").strip()
        if not file_path:
            continue

        try:
            duration = int(song.get("duration") or 0)
        except Exception:
            duration = 0

        offset = calculate_discovery_offset(duration, excerpt_seconds, offset_percent)
        queue.append({
            "file": file_path,
            "label": discovery_song_label_from_song(song),
            "duration": duration,
            "offset": offset,
            "songid": song.get("songid"),
        })

    log(f"Discovery mode: UI built direct playlist queue with {len(queue)} item(s).", xbmc.LOGINFO)
    return queue


def start_discovery_playlist_direct(state: dict) -> dict:
    excerpt_seconds = int(state.get("excerpt_seconds") or get_discovery_excerpt_seconds())
    offset_percent = int(state.get("offset_percent") or get_discovery_offset_percent())

    playlist = get_music_playlist()
    try:
        playlist.clear()
        log("Discovery mode: UI cleared Kodi music playlist.", xbmc.LOGINFO)
    except Exception as exc:
        log(f"Discovery mode: UI could not clear Kodi music playlist: {exc}", xbmc.LOGWARNING)

    queue = build_discovery_queue_from_library(excerpt_seconds, offset_percent, DISCOVERY_BUFFER_SIZE)
    if not queue:
        state["enabled"] = False
        state["startup_in_progress"] = False
        state["last_error"] = "Discovery playlist could not be filled from Kodi music library."
        save_discovery_state(state)
        notify(state["last_error"], xbmcgui.NOTIFICATION_ERROR)
        log(f"Discovery mode: {state['last_error']}", xbmc.LOGERROR)
        return state

    for entry in queue:
        try:
            playlist.add(str(entry.get("file") or ""), discovery_playlist_item(entry))
        except Exception as exc:
            log(f"Discovery mode: UI playlist add failed for {entry.get('file')!r}: {exc}", xbmc.LOGWARNING)

    try:
        playlist_size = playlist.size()
    except Exception:
        playlist_size = -1
    log(f"Discovery mode: UI playlist prepared. queue={len(queue)}, kodi_playlist_size={playlist_size}.", xbmc.LOGINFO)

    try:
        xbmc.Player().play(playlist)
        log("Discovery mode: UI called xbmc.Player().play(playlist).", xbmc.LOGINFO)
    except Exception as exc:
        state["enabled"] = False
        state["startup_in_progress"] = False
        state["last_error"] = f"Discovery playlist could not be started: {exc}"
        save_discovery_state(state)
        notify(state["last_error"], xbmcgui.NOTIFICATION_ERROR)
        log(f"Discovery mode: {state['last_error']}", xbmc.LOGERROR)
        return state

    first = queue[0]
    state.update({
        "enabled": True,
        "startup_in_progress": False,
        "queue": queue,
        "buffer_size": DISCOVERY_BUFFER_SIZE,
        "current_playlist_position": 0,
        "current_song": str(first.get("file") or ""),
        "current_label": str(first.get("label") or path_to_label(str(first.get("file") or ""))),
        "current_started_ts": int(time.time()),
        "current_offset_seconds": int(first.get("offset") or 0),
        "current_duration_seconds": int(first.get("duration") or 0),
        "current_startoffset_requested": bool(int(first.get("offset") or 0) > 0),
        "current_seek_confirmed": False,
        "last_error": "",
    })
    save_discovery_state(state)
    return state


def get_discovery_excerpt_seconds() -> int:
    return max(5, min(60, get_setting_int("discovery_excerpt_seconds", 20)))


def get_discovery_offset_percent() -> int:
    return max(0, min(90, get_setting_int("discovery_offset_percent", 33)))


def get_discovery_state() -> dict:
    return load_json_file(discovery_state_path())


def save_discovery_state(state: dict) -> None:
    save_json_file(discovery_state_path(), state or {})


def replace_with_discovery_mode_menu() -> None:
    try:
        xbmc.executebuiltin(
            f"Container.Update({addon_url(action='discovery_mode', nonce=new_nonce())},replace)"
        )
    except Exception as exc:
        log(f"Discovery mode: could not replace container with Discovery screen: {exc}", xbmc.LOGWARNING)


def mix_cache_key(seed: str, size: int) -> str:
    payload = f"{seed}\n{size}".encode("utf-8", errors="replace")
    return hashlib.sha1(payload).hexdigest()


def get_audio_library_freshness_cached(max_age: int = 15, allow_query: bool = True) -> dict:
    global AUDIO_LIBRARY_FRESHNESS_CACHE

    now = int(time.time())
    payload = AUDIO_LIBRARY_FRESHNESS_CACHE.get("payload") or {}
    fetched_ts = int(AUDIO_LIBRARY_FRESHNESS_CACHE.get("fetched_ts") or 0)

    if payload and fetched_ts > 0 and now - fetched_ts <= max_age:
        return payload

    if not allow_query:
        return payload

    payload = get_audio_library_freshness()
    AUDIO_LIBRARY_FRESHNESS_CACHE = {
        "fetched_ts": now,
        "payload": payload,
    }
    return payload


def get_cached_audio_library_freshest_ts(allow_query: bool = True) -> int:
    freshness = get_audio_library_freshness_cached(allow_query=allow_query)
    return int((freshness or {}).get("freshest_ts") or 0)


def get_track_metadata_cache_db_path() -> str:
    return os.path.join(get_profile_dir(), "track_metadata_cache.db")


def get_track_metadata_cache_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_track_metadata_cache_db_path())
    connection.row_factory = sqlite3.Row
    ensure_track_metadata_cache_schema(connection)
    return connection


def ensure_track_metadata_cache_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS track_metadata_cache (
            path TEXT PRIMARY KEY,
            songid INTEGER DEFAULT 0,
            title TEXT DEFAULT '',
            artist TEXT DEFAULT '',
            album TEXT DEFAULT '',
            genre_json TEXT DEFAULT '[]',
            year INTEGER DEFAULT 0,
            decade TEXT DEFAULT '',
            duration INTEGER DEFAULT 0,
            thumbnail TEXT DEFAULT '',
            fanart TEXT DEFAULT '',
            cached_ts INTEGER DEFAULT 0,
            library_freshest_ts INTEGER DEFAULT 0,
            schema_version INTEGER DEFAULT 1
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_metadata_cache_songid "
        "ON track_metadata_cache(songid)"
    )
    connection.commit()


def build_empty_track_metadata(path: str) -> dict[str, object]:
    return {
        "songid": 0,
        "title": path_to_label(path),
        "artist": "",
        "album": "",
        "genre": [],
        "year": 0,
        "decade": "",
        "duration": 0,
        "thumbnail": "",
        "fanart": "",
        "cached_ts": 0,
        "library_freshest_ts": 0,
    }


def normalize_track_metadata_snapshot(
    path: str,
    metadata: dict | None,
    cached_ts: int | None = None,
    library_freshest_ts: int | None = None,
) -> dict[str, object]:
    snapshot = build_empty_track_metadata(path)
    metadata = metadata if isinstance(metadata, dict) else {}

    try:
        snapshot["songid"] = int(metadata.get("songid") or 0)
    except Exception:
        snapshot["songid"] = 0

    title = str(metadata.get("title") or "").strip()
    if title:
        snapshot["title"] = title

    snapshot["artist"] = str(metadata.get("artist") or "").strip()
    snapshot["album"] = str(metadata.get("album") or "").strip()
    snapshot["genre"] = normalize_genres(metadata.get("genre"))
    snapshot["year"] = parse_year(metadata.get("year"))
    snapshot["decade"] = str(metadata.get("decade") or format_decade(snapshot["year"]))
    snapshot["duration"] = parse_duration_seconds(metadata.get("duration"))
    snapshot["thumbnail"] = str(metadata.get("thumbnail") or "").strip()
    snapshot["fanart"] = str(metadata.get("fanart") or "").strip()

    try:
        snapshot["cached_ts"] = int(
            cached_ts
            if cached_ts is not None
            else (metadata.get("cached_ts") or 0)
        )
    except Exception:
        snapshot["cached_ts"] = 0

    try:
        snapshot["library_freshest_ts"] = int(
            library_freshest_ts
            if library_freshest_ts is not None
            else (metadata.get("library_freshest_ts") or 0)
        )
    except Exception:
        snapshot["library_freshest_ts"] = 0

    return snapshot


def track_metadata_snapshot_has_payload(path: str, metadata: dict | None) -> bool:
    if not isinstance(metadata, dict):
        return False

    fallback_title = path_to_label(path)
    title = str(metadata.get("title") or "").strip()

    return bool(
        int(metadata.get("songid") or 0) > 0
        or (title and title != fallback_title)
        or str(metadata.get("artist") or "").strip()
        or str(metadata.get("album") or "").strip()
        or normalize_genres(metadata.get("genre"))
        or parse_year(metadata.get("year")) > 0
        or parse_duration_seconds(metadata.get("duration")) > 0
        or str(metadata.get("thumbnail") or "").strip()
        or str(metadata.get("fanart") or "").strip()
    )

def read_track_metadata_cache(path: str) -> dict[str, object]:
    cache_key = canonical_audio_path(path)
    if not cache_key:
        return {}

    try:
        connection = get_track_metadata_cache_connection()
        try:
            row = connection.execute(
                """
                SELECT path, songid, title, artist, album, genre_json, year, decade,
                       duration, thumbnail, fanart, cached_ts, library_freshest_ts
                FROM track_metadata_cache
                WHERE path = ?
                """,
                (cache_key,),
            ).fetchone()
        finally:
            connection.close()
    except Exception as exc:
        log(f"Track metadata cache read failed for {path!r}: {exc}", xbmc.LOGDEBUG)
        return {}

    if row is None:
        return {}

    try:
        genres = json.loads(row["genre_json"] or "[]")
    except Exception:
        genres = []

    snapshot = normalize_track_metadata_snapshot(
        path,
        {
            "songid": row["songid"],
            "title": row["title"],
            "artist": row["artist"],
            "album": row["album"],
            "genre": genres,
            "year": row["year"],
            "decade": row["decade"],
            "duration": row["duration"],
            "thumbnail": row["thumbnail"],
            "fanart": row["fanart"],
            "cached_ts": row["cached_ts"],
            "library_freshest_ts": row["library_freshest_ts"],
        },
    )
    return snapshot if track_metadata_snapshot_has_payload(path, snapshot) else {}


def write_track_metadata_cache(path: str, metadata: dict | None) -> None:
    snapshot = normalize_track_metadata_snapshot(path, metadata)
    if not track_metadata_snapshot_has_payload(path, snapshot):
        return

    cache_key = canonical_audio_path(path)
    if not cache_key:
        return

    try:
        connection = get_track_metadata_cache_connection()
        try:
            connection.execute(
                """
                INSERT INTO track_metadata_cache (
                    path, songid, title, artist, album, genre_json, year, decade,
                    duration, thumbnail, fanart, cached_ts, library_freshest_ts, schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    songid = excluded.songid,
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    genre_json = excluded.genre_json,
                    year = excluded.year,
                    decade = excluded.decade,
                    duration = excluded.duration,
                    thumbnail = excluded.thumbnail,
                    fanart = excluded.fanart,
                    cached_ts = excluded.cached_ts,
                    library_freshest_ts = excluded.library_freshest_ts,
                    schema_version = excluded.schema_version
                """,
                (
                    cache_key,
                    int(snapshot.get("songid") or 0),
                    str(snapshot.get("title") or ""),
                    str(snapshot.get("artist") or ""),
                    str(snapshot.get("album") or ""),
                    json.dumps(normalize_genres(snapshot.get("genre")), ensure_ascii=False),
                    int(snapshot.get("year") or 0),
                    str(snapshot.get("decade") or ""),
                    int(snapshot.get("duration") or 0),
                    str(snapshot.get("thumbnail") or ""),
                    str(snapshot.get("fanart") or ""),
                    int(snapshot.get("cached_ts") or 0),
                    int(snapshot.get("library_freshest_ts") or 0),
                    TRACK_METADATA_CACHE_SCHEMA_VERSION,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    except Exception as exc:
        log(f"Track metadata cache write failed for {path!r}: {exc}", xbmc.LOGDEBUG)


def build_sidecar_track_metadata_map(meta: dict | None) -> dict[str, dict]:
    meta = meta if isinstance(meta, dict) else {}
    raw = meta.get("track_metadata_by_path")
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, dict] = {}
    for key, value in raw.items():
        cache_key = canonical_audio_path(str(key or ""))
        if not cache_key or not isinstance(value, dict):
            continue
        snapshot = normalize_track_metadata_snapshot(key, value)
        if track_metadata_snapshot_has_payload(key, snapshot):
            normalized[cache_key] = snapshot

    return normalized


def collect_mix_track_metadata(
    tracks: list[str],
    sidecar_map: dict[str, dict] | None = None,
    allow_live_lookup: bool = True,
    include_player_metadata: bool = True,
) -> list[dict]:
    sidecar_map = sidecar_map if isinstance(sidecar_map, dict) else {}
    metadata_list: list[dict] = []

    for track in tracks:
        cache_key = canonical_audio_path(track)
        sidecar_snapshot = sidecar_map.get(cache_key) if cache_key else None
        metadata_list.append(
            get_track_metadata(
                track,
                sidecar_snapshot=sidecar_snapshot,
                allow_live_lookup=allow_live_lookup,
                include_player_metadata=include_player_metadata,
            )
        )

    return metadata_list


def build_mix_track_metadata_snapshot_map(
    tracks: list[str],
    metadata_list: list[dict] | None,
) -> dict[str, dict]:
    metadata_list = metadata_list if isinstance(metadata_list, list) else []
    snapshot_map: dict[str, dict] = {}

    for index, track in enumerate(tracks):
        cache_key = canonical_audio_path(track)
        if not cache_key:
            continue

        source = metadata_list[index] if index < len(metadata_list) and isinstance(metadata_list[index], dict) else {}
        snapshot = normalize_track_metadata_snapshot(
            track,
            source,
            cached_ts=int(source.get("cached_ts") or int(time.time())) if isinstance(source, dict) else int(time.time()),
            library_freshest_ts=int(source.get("library_freshest_ts") or 0) if isinstance(source, dict) else 0,
        )
        if track_metadata_snapshot_has_payload(track, snapshot):
            snapshot_map[cache_key] = snapshot

    return snapshot_map


def set_mix_track_metadata_snapshot(
    cache_path: str,
    tracks: list[str],
    metadata_list: list[dict] | None,
) -> None:
    if not tracks:
        return

    meta = get_saved_mix_metadata(cache_path, tracks)
    snapshot_map = build_mix_track_metadata_snapshot_map(tracks, metadata_list)

    if not snapshot_map:
        return

    meta["track_count"] = len(tracks)
    meta["track_metadata_by_path"] = snapshot_map
    meta["track_metadata_cached_ts"] = int(time.time())

    freshest_ts = 0
    for item in metadata_list or []:
        try:
            freshest_ts = max(freshest_ts, int(item.get("library_freshest_ts") or 0))
        except Exception:
            pass

    if freshest_ts > 0:
        meta["track_metadata_library_freshest_ts"] = freshest_ts

    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)


def get_metadata_refresh_queue_path() -> str:
    return os.path.join(get_profile_dir(), "metadata_refresh_queue.json")


def load_metadata_refresh_queue() -> dict:
    payload = load_json_file(get_metadata_refresh_queue_path())
    if not isinstance(payload, dict):
        payload = {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {
        "version": 1,
        "updated_ts": int(payload.get("updated_ts") or 0),
        "entries": entries,
    }


def save_metadata_refresh_queue(queue: dict) -> None:
    entries = queue.get("entries") if isinstance(queue, dict) else []
    if not isinstance(entries, list):
        entries = []
    save_json_file(
        get_metadata_refresh_queue_path(),
        {
            "version": 1,
            "updated_ts": int(time.time()),
            "entries": entries,
        },
    )


def track_metadata_needs_background_refresh(
    path: str,
    metadata: dict | None,
    library_freshest_ts: int,
) -> tuple[bool, str]:
    if not track_metadata_snapshot_has_payload(path, metadata):
        return True, "missing"

    if library_freshest_ts <= 0:
        return False, ""

    try:
        metadata_library_ts = int((metadata or {}).get("library_freshest_ts") or 0)
    except Exception:
        metadata_library_ts = 0

    try:
        metadata_cached_ts = int((metadata or {}).get("cached_ts") or 0)
    except Exception:
        metadata_cached_ts = 0

    if metadata_library_ts > 0 and metadata_library_ts < library_freshest_ts:
        return True, "stale"

    if metadata_library_ts <= 0 and metadata_cached_ts > 0 and metadata_cached_ts < library_freshest_ts:
        return True, "stale"

    if metadata_library_ts <= 0 and metadata_cached_ts <= 0:
        return True, "missing_timestamp"

    return False, ""


def enqueue_metadata_refresh_for_tracks(
    tracks: list[str],
    cache_path: str = "",
    metadata_list: list[dict] | None = None,
    reason_context: str = "",
) -> int:
    if not tracks:
        return 0

    metadata_list = metadata_list if isinstance(metadata_list, list) else []
    library_freshest_ts = get_cached_audio_library_freshest_ts(allow_query=True)

    queue = load_metadata_refresh_queue()
    existing_entries = queue.get("entries") if isinstance(queue, dict) else []
    if not isinstance(existing_entries, list):
        existing_entries = []

    entries_by_key: dict[str, dict] = {}
    order: list[str] = []

    for entry in existing_entries:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        key = canonical_audio_path(path)
        if not key:
            continue

        cache_paths = entry.get("cache_paths")
        if not isinstance(cache_paths, list):
            cache_paths = []
        entry["cache_paths"] = [str(item) for item in cache_paths if str(item or "").strip()]
        entries_by_key[key] = entry
        order.append(key)

    queued_count = 0
    now = int(time.time())

    for index, track in enumerate(tracks):
        key = canonical_audio_path(track)
        if not key:
            continue

        metadata = metadata_list[index] if index < len(metadata_list) and isinstance(metadata_list[index], dict) else {}
        needs_refresh, reason = track_metadata_needs_background_refresh(track, metadata, library_freshest_ts)
        if not needs_refresh:
            continue

        if key not in entries_by_key:
            entries_by_key[key] = {
                "path": track,
                "cache_paths": [],
                "queued_ts": now,
                "updated_ts": now,
                "attempts": 0,
                "reason": reason,
                "context": reason_context,
            }
            order.append(key)
            queued_count += 1
        else:
            entries_by_key[key]["updated_ts"] = now
            entries_by_key[key]["reason"] = reason or entries_by_key[key].get("reason") or "refresh"
            if reason_context:
                entries_by_key[key]["context"] = reason_context

        if cache_path:
            cache_paths = entries_by_key[key].get("cache_paths")
            if not isinstance(cache_paths, list):
                cache_paths = []
            if cache_path not in cache_paths:
                cache_paths.append(cache_path)
            entries_by_key[key]["cache_paths"] = cache_paths

    if queued_count or cache_path:
        queue["entries"] = [entries_by_key[key] for key in order if key in entries_by_key]
        save_metadata_refresh_queue(queue)

    if queued_count:
        log(
            f"Queued {queued_count} track(s) for background metadata refresh "
            f"context={reason_context!r}, cache_path={cache_path!r}.",
            xbmc.LOGINFO,
        )

    return queued_count


def mix_cache_path(seed: str, size: int) -> str:
    return os.path.join(get_profile_dir(), f"mix_{mix_cache_key(seed, size)}.m3u")


def mix_meta_path_from_cache_path(cache_path: str) -> str:
    return f"{cache_path}.json"


def save_json_file(path: str, payload: dict) -> None:
    handle = xbmcvfs.File(path, "w")
    try:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        handle.close()


def load_json_file(path: str) -> dict:
    if not xbmcvfs.exists(path):
        return {}
    handle = xbmcvfs.File(path, "r")
    try:
        payload = handle.read()
    finally:
        handle.close()
    try:
        return json.loads(payload) if payload else {}
    except Exception:
        return {}


def save_mix(seed: str, size: int, tracks: list[str], track_metadata_list: list[dict] | None = None) -> None:
    path = mix_cache_path(seed, size)
    payload = "\n".join(tracks)
    handle = xbmcvfs.File(path, "w")
    try:
        handle.write(payload)
    finally:
        handle.close()

    meta = load_json_file(mix_meta_path_from_cache_path(path))
    if not isinstance(meta, dict):
        meta = {}

    meta.update({
        "seed": seed,
        "size": size,
        "track_count": len(tracks),
        "label": path_to_label(seed),
        "updated_ts": int(time.time()),
    })

    generation_params = pop_mix_generation_parameters(seed, size)
    if generation_params:
        meta["mix_generation_parameters"] = generation_params
        meta["mix_generation_parameters_ts"] = int(time.time())

    if isinstance(track_metadata_list, list) and track_metadata_list:
        meta["track_metadata_by_path"] = build_mix_track_metadata_snapshot_map(tracks, track_metadata_list)
        meta["track_metadata_cached_ts"] = int(time.time())

        freshest_ts = 0
        for item in track_metadata_list:
            try:
                freshest_ts = max(freshest_ts, int(item.get("library_freshest_ts") or 0))
            except Exception:
                pass
        if freshest_ts > 0:
            meta["track_metadata_library_freshest_ts"] = freshest_ts

    save_json_file(mix_meta_path_from_cache_path(path), meta)

def save_mix_by_cache_path(cache_path: str, tracks: list[str]) -> None:
    payload = "\n".join(tracks)
    handle = xbmcvfs.File(cache_path, "w")
    try:
        handle.write(payload)
    finally:
        handle.close()

    meta = get_saved_mix_metadata(cache_path, tracks)
    original_updated_ts = int(meta.get("updated_ts") or 0)
    meta["track_count"] = len(tracks)
    # Keep updated_ts stable. It is the visible ordering/date-group timestamp.
    # Use modified_ts for repair/edit time instead.
    if original_updated_ts > 0:
        meta["updated_ts"] = original_updated_ts
    else:
        meta["updated_ts"] = int(time.time())
    meta["modified_ts"] = int(time.time())
    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)


def load_mix(seed: str, size: int) -> list[str]:
    return load_mix_by_cache_path(mix_cache_path(seed, size))


def load_mix_by_cache_path(cache_path: str) -> list[str]:
    if not xbmcvfs.exists(cache_path):
        raise MusicIPError("No stored mix found for this song.")

    handle = xbmcvfs.File(cache_path, "r")
    try:
        payload = handle.read()
    finally:
        handle.close()

    return [line.strip() for line in payload.splitlines() if line.strip()]


def saved_mix_order_timestamp(cache_path: str) -> int:
    try:
        tracks = load_mix_by_cache_path(cache_path)
        meta = get_saved_mix_metadata(cache_path, tracks)
        updated_ts = int(meta.get("updated_ts") or 0)
        if updated_ts > 0:
            return updated_ts
    except Exception:
        pass

    try:
        return int(os.path.getmtime(cache_path))
    except Exception:
        return 0


def list_saved_mix_cache_paths() -> list[str]:
    pattern = os.path.join(get_profile_dir(), "mix_*.m3u")
    paths = [path for path in glob.glob(pattern) if os.path.isfile(path)]

    # Do not sort by the M3U file modification time here.
    # Auto-repair and More/Less like this rewrite the M3U and therefore change
    # its filesystem mtime. The visible recent-mix order should remain based on
    # the original saved timestamp in the sidecar metadata.
    paths.sort(key=lambda p: (saved_mix_order_timestamp(p), os.path.basename(p)), reverse=True)
    return paths


def infer_saved_mix_metadata(cache_path: str, tracks: list[str]) -> dict:
    seed = tracks[0] if tracks else ""
    try:
        modified_ts = int(os.path.getmtime(cache_path))
    except Exception:
        modified_ts = 0
    return {
        "seed": seed,
        "size": len(tracks),
        "track_count": len(tracks),
        "label": path_to_label(seed) if seed else os.path.basename(cache_path),
        "updated_ts": modified_ts,
        "cache_path": cache_path,
    }


def get_saved_mix_metadata(cache_path: str, tracks: list[str] | None = None) -> dict:
    meta = load_json_file(mix_meta_path_from_cache_path(cache_path))
    if tracks is None:
        tracks = load_mix_by_cache_path(cache_path)
    inferred = infer_saved_mix_metadata(cache_path, tracks)
    merged = dict(inferred)
    merged.update({k: v for k, v in meta.items() if v not in ("", None)})
    merged["cache_path"] = cache_path
    if not merged.get("track_count"):
        merged["track_count"] = len(tracks)
    if not merged.get("label"):
        merged["label"] = path_to_label(merged.get("seed", "")) or os.path.basename(cache_path)
    return merged


def problem_marker_label(label: str) -> str:
    return f"[B][COLOR red]![/COLOR][/B] {label}"


def get_consistency_status(meta: dict) -> dict:
    value = meta.get("consistency")
    if isinstance(value, dict):
        return value
    return {}


def is_mix_inconsistent(meta: dict) -> bool:
    return str(get_consistency_status(meta).get("status") or "").lower() == "inconsistent"


def get_consistency_label(meta: dict) -> str:
    consistency = get_consistency_status(meta)
    status = str(consistency.get("status") or "").strip().lower()

    if status == "ok":
        return "OK"

    if status == "inconsistent":
        missing = int(consistency.get("missing_files") or 0)
        if missing == 1:
            return "Inconsistent: 1 missing"
        if missing > 1:
            return f"Inconsistent: {missing} missing"
        return "Inconsistent"

    return ""


def track_file_exists(path: str) -> bool:
    value = str(path or "").strip()
    if not value:
        return False

    try:
        return bool(xbmcvfs.exists(value))
    except Exception:
        return False


def missing_signature(missing: list[dict]) -> str:
    payload = [
        {
            "index": int(item.get("index") or 0),
            "path": str(item.get("path") or ""),
        }
        for item in missing
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def build_consistency_payload(old_consistency: dict, tracks: list[str], missing: list[dict]) -> dict:
    now = int(time.time())
    checked_tracks = len(tracks)

    if not missing:
        return {
            "status": "ok",
            "checked_ts": now,
            "checked_tracks": checked_tracks,
            "missing_files": 0,
            "missing": [],
            "missing_signature": "",
        }

    signature = missing_signature(missing)
    old_status = str(old_consistency.get("status") or "").lower()
    old_signature = str(old_consistency.get("missing_signature") or "")
    old_first = int(old_consistency.get("first_inconsistent_ts") or 0)
    old_changed = int(old_consistency.get("last_inconsistency_change_ts") or 0)

    first_inconsistent_ts = old_first if old_status == "inconsistent" and old_first > 0 else now
    last_inconsistency_change_ts = old_changed or first_inconsistent_ts
    if old_status != "inconsistent" or old_signature != signature:
        last_inconsistency_change_ts = now

    previous_missing = {}
    for item in old_consistency.get("missing") or []:
        path = str(item.get("path") or "")
        if path:
            previous_missing[path] = int(item.get("first_missing_ts") or first_inconsistent_ts)

    enriched_missing: list[dict] = []
    for item in missing:
        path = str(item.get("path") or "")
        enriched_missing.append({
            "index": int(item.get("index") or 0),
            "path": path,
            "first_missing_ts": previous_missing.get(path, now),
        })

    return {
        "status": "inconsistent",
        "checked_ts": now,
        "checked_tracks": checked_tracks,
        "missing_files": len(enriched_missing),
        "missing": enriched_missing,
        "missing_signature": signature,
        "first_inconsistent_ts": first_inconsistent_ts,
        "last_inconsistency_change_ts": last_inconsistency_change_ts,
    }


def set_mix_consistency_metadata(cache_path: str, tracks: list[str], consistency: dict) -> None:
    meta = get_saved_mix_metadata(cache_path, tracks)
    meta["track_count"] = len(tracks)
    meta["consistency"] = consistency
    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)


def analyze_mix_consistency(cache_path: str) -> dict:
    tracks = load_mix_by_cache_path(cache_path)
    meta = get_saved_mix_metadata(cache_path, tracks)
    old_consistency = meta.get("consistency") if isinstance(meta.get("consistency"), dict) else {}
    missing: list[dict] = []

    for index, track in enumerate(tracks):
        if track_file_exists(track):
            continue

        missing.append({
            "index": index,
            "path": track,
        })

    consistency = build_consistency_payload(old_consistency, tracks, missing)
    set_mix_consistency_metadata(cache_path, tracks, consistency)
    return consistency


def is_track_missing(path: str) -> bool:
    return not track_file_exists(path)


def parse_kodi_datetime(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0

    # Expected Kodi examples:
    #   2026-05-08 22:16:17
    #   2026-05-08T22:16:17Z
    #   2026-05-08
    #
    # Use [0-9] explicitly to avoid backslash escaping issues in embedded regex strings.
    match = re.search(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[ T]([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?)?",
        text,
    )
    if not match:
        log_library_freshness(f"Library freshness: could not parse Kodi datetime value {text!r}")
        return 0

    try:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        second = int(match.group(6) or 0)
        parsed = datetime.datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            tzinfo=datetime.timezone.utc,
        )
        timestamp = int(parsed.timestamp())
        log_library_freshness(f"Library freshness: parsed Kodi datetime {text!r} as timestamp {timestamp}")
        return timestamp
    except Exception as exc:
        log_library_freshness(f"Library freshness: failed to convert Kodi datetime {text!r}: {exc}")
        return 0


def format_ts_for_display(value: int) -> str:
    ts = int(value or 0)
    if ts <= 0:
        return "unknown"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def get_audio_library_freshness() -> dict:
    properties = [
        "librarylastupdated",
        "librarylastcleaned",
        "songslastadded",
        "songsmodified",
    ]

    try:
        result = execute_jsonrpc(
            "AudioLibrary.GetProperties",
            {"properties": properties},
        )
    except Exception as exc:
        log_library_freshness(f"Library freshness: could not read Kodi audio library properties: {exc}")
        return {
            "properties": {},
            "timestamps": {},
            "freshest_ts": 0,
            "freshest_property": "",
        }

    timestamps = {}
    for key in properties:
        timestamps[key] = parse_kodi_datetime(result.get(key))
        log_library_freshness(
            f"Library freshness: Kodi library property {key}="
            f"{str(result.get(key) or '')!r}, parsed_ts={timestamps[key]}"
        )

    freshest_property = ""
    freshest_ts = 0
    for key, value in timestamps.items():
        if value > freshest_ts:
            freshest_ts = value
            freshest_property = key

    return {
        "properties": {key: result.get(key, "") for key in properties},
        "timestamps": timestamps,
        "freshest_ts": freshest_ts,
        "freshest_property": freshest_property,
    }


def find_missing_paths_still_in_library(paths: list[str]) -> list[str]:
    """The missing files that the Kodi music library still lists. Raises MusicIPError if Kodi cannot be queried."""
    still_listed: list[str] = []
    for path in paths:
        filename, _directory = split_full_path(path)
        if not filename:
            continue
        result = execute_jsonrpc(
            "AudioLibrary.GetSongs",
            {
                "properties": ["file"],
                "filter": {"field": "filename", "operator": "is", "value": filename},
            },
        )
        if find_song_by_file(result.get("songs") or [], path) is not None:
            still_listed.append(path)
    return still_listed


def expand_music_source_path(path: str) -> list[str]:
    # A source with several folders is reported as multipath://<url-encoded path>/<url-encoded path>/
    if path.startswith("multipath://"):
        return [unquote(part) for part in path[len("multipath://"):].split("/") if part]
    return [path] if path else []


def get_music_source_paths() -> list[str]:
    """Folders of Kodi's music sources. Raises MusicIPError if Kodi cannot be queried."""
    result = execute_jsonrpc("Files.GetSources", {"media": "music"})
    paths: list[str] = []
    for source in result.get("sources") or []:
        paths.extend(expand_music_source_path(str(source.get("file") or "").strip()))
    return paths


def music_source_exists(source: str) -> bool:
    folder = source if source.endswith(("/", "\\")) else source + ("/" if "://" in source else os.sep)
    try:
        return bool(xbmcvfs.exists(folder))
    except Exception:
        return False


def find_covering_music_source(path: str, sources: list[str]) -> str:
    key = canonical_audio_path(path)
    best = ""
    for source in sources:
        source_key = canonical_audio_path(source)
        if source_key and (key == source_key or key.startswith(source_key + "/")):
            if len(source_key) > len(canonical_audio_path(best)):
                best = source
    return best


def check_music_sources_for_missing_files(paths: list[str]) -> dict:
    """Can Kodi's music sources still add or update the missing files?

    unavailable_sources: sources that covered a missing file but no longer exist (folders reorganized,
    drive or share offline); the library cannot pick up the moved files there until the sources are fixed.
    outside_sources: missing files that no configured source covers. Only informational, because that is
    also the normal state after an obsolete source has been removed.
    """
    sources = get_music_source_paths()
    unavailable: list[str] = []
    outside: list[str] = []
    for path in paths:
        source = find_covering_music_source(path, sources)
        if not source:
            outside.append(path)
        elif source not in unavailable and not music_source_exists(source):
            unavailable.append(source)
    return {"sources": sources, "unavailable_sources": unavailable, "outside_sources": outside}


MISSING_FILE_SEARCH_SKIP_FOLDERS = {
    "$recycle.bin", "recycler", "system volume information", "@eadir", "#recycle", ".trash", ".trashes",
}
MISSING_FILE_SEARCH_MAX_SECONDS = 60
MISSING_FILE_SEARCH_MAX_FOLDERS = 100000
MISSING_FILE_SEARCH_MAX_AGE_SECONDS = 24 * 3600


def split_source_volume(path: str) -> tuple[str, list[str], str]:
    """(volume, folder names below it, separator) of a source folder; volume "" if it cannot be searched."""
    value = str(path or "").strip()
    if "://" in value:
        scheme, rest = value.split("://", 1)
        parts = [part for part in rest.split("/") if part]
        if scheme.lower() not in ("smb", "nfs") or len(parts) < 2:
            return "", [], "/"
        return f"{scheme}://{parts[0]}/{parts[1]}/", parts[2:], "/"
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return value[:2] + "\\", [part for part in re.split(r"[\\/]", value[3:]) if part], "\\"
    if value.startswith("/"):
        parts = [part for part in value.split("/") if part]
        return (f"/{parts[0]}/", parts[1:], "/") if parts else ("", [], "/")
    return "", [], "/"


def get_virtual_library_roots(sources: list[str]) -> list[str]:
    """One root per disk, share or root folder: the deepest folder that contains all of its music sources.

    If a source itself is that folder (for example the only source on a disk), the root is one level higher,
    so folders next to it are searched too.
    """
    groups: dict[str, list[tuple[str, list[str], str]]] = {}
    for source in sources:
        volume, parts, separator = split_source_volume(source)
        if volume:
            groups.setdefault(volume.casefold(), []).append((volume, parts, separator))

    roots: list[str] = []
    for entries in groups.values():
        volume, common, separator = entries[0]
        for _volume, parts, _separator in entries[1:]:
            length = 0
            while length < min(len(common), len(parts)) and common[length].casefold() == parts[length].casefold():
                length += 1
            common = common[:length]
        if any(len(parts) == len(common) for _volume, parts, _separator in entries):
            common = common[:-1]
        roots.append(volume + "".join(part + separator for part in common))
    return roots


def is_inside_music_source(path: str, source_keys: list[str]) -> bool:
    key = canonical_audio_path(path)
    return any(key == source_key or key.startswith(source_key + "/") for source_key in source_keys)


def music_source_has_library_content(source: str) -> bool:
    """Has this music source been scanned into the library? Configured sources can be left unscanned."""
    try:
        result = execute_jsonrpc(
            "AudioLibrary.GetSongs",
            {
                "properties": [],
                "limits": {"start": 0, "end": 1},
                "filter": {"field": "path", "operator": "startswith", "value": source},
            },
        )
    except Exception:
        return True  # Unknown: treat it as part of the library, as before.
    return bool(result.get("songs")) or int((result.get("limits") or {}).get("total") or 0) > 0


def search_missing_files_outside_sources(missing_paths: list[str], sources: list[str]) -> dict:
    """Look for missing files below the virtual library roots, outside the music library.

    Folders inside music sources that have been scanned into the library are skipped: the library already
    covers them. Music sources without library content (never scanned) are searched like other folders.

    found_outside_sources: files outside every music source; only reported to the user, since some folders
    are left out of the library on purpose.
    found_in_unscanned_sources: files inside a configured source that was never scanned into the library;
    unscanned_sources lists those sources, which the user can be offered to scan.

    A file matches when its name and its folder name both match the missing file, which keeps moved albums
    and rejects unrelated files with common names.
    """
    wanted: dict[tuple[str, str], list[str]] = {}
    for missing in missing_paths:
        filename, directory = split_full_path(missing)
        folder_name = split_full_path(directory)[0]
        if filename and folder_name:
            wanted.setdefault((folder_name.casefold(), filename.casefold()), []).append(missing)

    library_sources = [source for source in sources if music_source_has_library_content(source)]
    unscanned_sources = [source for source in sources if source not in library_sources]
    library_keys = [key for key in (canonical_audio_path(source) for source in library_sources) if key]
    roots = get_virtual_library_roots(sources)
    found: dict[str, str] = {}
    started = time.time()
    folders_searched = 0
    complete = True
    pending = list(roots)

    while pending and len(found) < len(missing_paths):
        if time.time() - started > MISSING_FILE_SEARCH_MAX_SECONDS or folders_searched >= MISSING_FILE_SEARCH_MAX_FOLDERS:
            complete = False
            break
        folder = pending.pop()
        if is_inside_music_source(folder, library_keys):
            continue
        try:
            directories, files = xbmcvfs.listdir(folder)
        except Exception:
            continue
        folders_searched += 1
        folder_name = split_full_path(folder)[0].casefold()
        for name in files:
            for missing in wanted.get((folder_name, str(name).casefold()), []):
                found.setdefault(missing, folder + name)
        separator = "/" if folder.endswith("/") else "\\"
        for name in directories:
            name = str(name)
            if name.casefold() in MISSING_FILE_SEARCH_SKIP_FOLDERS or name.startswith((".", "$")):
                continue
            pending.append(folder + name + separator)

    outside: dict[str, str] = {}
    in_unscanned: dict[str, str] = {}
    found_unscanned_sources: list[str] = []
    for missing, location in found.items():
        source = find_covering_music_source(location, unscanned_sources)
        if source:
            in_unscanned[missing] = location
            if source not in found_unscanned_sources:
                found_unscanned_sources.append(source)
        else:
            outside[missing] = location

    return {
        "checked_ts": int(time.time()),
        "roots": roots,
        "found_outside_sources": outside,
        "found_in_unscanned_sources": in_unscanned,
        "unscanned_sources": sorted(found_unscanned_sources),
        "complete": complete,
        "folders_searched": folders_searched,
    }


def missing_file_search_is_current(search: object, consistency: dict) -> bool:
    # An unfinished search (time limit) also counts, so a huge disk is not searched again on every check.
    if not isinstance(search, dict):
        return False
    if str(search.get("signature") or "") != str(consistency.get("missing_signature") or ""):
        return False
    return int(time.time()) - int(search.get("checked_ts") or 0) < MISSING_FILE_SEARCH_MAX_AGE_SECONDS


def repair_readiness_action_label(readiness: dict) -> str:
    if str(readiness.get("status") or "") == "update_sources_before_repair":
        return "Check music sources before repair"
    if str(readiness.get("status") or "") == "scan_source_before_repair":
        return "Scan music source before repair"
    return "Update library before repair"


def evaluate_repair_readiness(consistency: dict, search: dict | None = None) -> dict:
    """Repair is ready once Kodi's music sources are available and the library no longer lists any of
    the mix's missing files.

    A source that no longer exists cannot provide the moved files. A missing file found (by the service's
    disk search) in a music source that was never scanned into the library cannot reach the library until
    that source is scanned. A library that still lists a missing file has not caught up with the move or
    deletion yet, so its repair candidates cannot be trusted.
    Shared by the plugin and the service.
    """
    consistency = consistency if isinstance(consistency, dict) else {}
    now = int(time.time())

    if str(consistency.get("status") or "").lower() != "inconsistent":
        return {"status": "not_needed", "reason": "Mix is not inconsistent.", "checked_ts": now}

    missing_paths = [
        str(item.get("path") or "")
        for item in consistency.get("missing") or []
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    readiness = {
        "status": "update_library_before_repair",
        "reason": "",
        "checked_ts": now,
        "first_inconsistent_ts": int(consistency.get("first_inconsistent_ts") or 0),
        "last_inconsistency_change_ts": int(consistency.get("last_inconsistency_change_ts") or 0),
        "missing_files": len(missing_paths),
        "still_listed": [],
    }

    if not missing_paths:
        readiness["reason"] = "No missing files are recorded yet. Run the consistency check again."
        return readiness

    try:
        source_check = check_music_sources_for_missing_files(missing_paths)
    except Exception:
        source_check = None  # Sources could not be read; the library check below still applies.

    readiness["sources_checked"] = source_check is not None
    if source_check is not None:
        readiness["unavailable_sources"] = source_check["unavailable_sources"]
        readiness["outside_sources"] = source_check["outside_sources"]
        if not source_check["sources"]:
            readiness["status"] = "update_sources_before_repair"
            readiness["reason"] = "Kodi has no music sources, so the library cannot add the missing files. Add a music source."
            return readiness
        if source_check["unavailable_sources"]:
            readiness["status"] = "update_sources_before_repair"
            readiness["reason"] = (
                f"Kodi music source(s) no longer available: {', '.join(source_check['unavailable_sources'])}. "
                "Update the music sources to the new folder structure (or reconnect the drive), then update the library."
            )
            return readiness

    unscanned = unscanned_sources_holding_missing_files(consistency, search, missing_paths)
    if unscanned:
        found = search.get("found_in_unscanned_sources") or {}
        readiness["status"] = "scan_source_before_repair"
        readiness["unscanned_sources"] = unscanned
        readiness["found_in_unscanned_sources"] = {old: new for old, new in found.items() if old in missing_paths}
        readiness["reason"] = (
            f"{len(readiness['found_in_unscanned_sources'])} missing file(s) were found in music source(s) that are "
            f"not scanned into the library: {', '.join(unscanned)}. Scan the source into the library."
        )
        return readiness

    try:
        still_listed = find_missing_paths_still_in_library(missing_paths)
    except Exception as exc:
        readiness["reason"] = f"Kodi music library could not be queried: {exc}"
        return readiness

    readiness["still_listed"] = still_listed
    if still_listed:
        readiness["reason"] = (
            f"Kodi music library still lists {len(still_listed)} of {len(missing_paths)} missing file(s). "
            "Update and clean the library."
        )
    else:
        readiness["status"] = "ready"
        readiness["reason"] = "Kodi music library no longer lists the missing files."
        outside = len(readiness.get("outside_sources") or [])
        if outside:
            readiness["reason"] += f" {outside} of them were outside all Kodi music sources."
    return readiness


def unscanned_sources_holding_missing_files(consistency: dict, search: object, missing_paths: list[str]) -> list[str]:
    """Never-scanned music sources in which the disk search found this mix's missing files, still unscanned."""
    if not isinstance(search, dict):
        return []
    if str(search.get("signature") or "") != str(consistency.get("missing_signature") or ""):
        return []
    found = search.get("found_in_unscanned_sources") if isinstance(search.get("found_in_unscanned_sources"), dict) else {}
    if not any(old in missing_paths for old in found):
        return []
    return [
        str(source)
        for source in search.get("unscanned_sources") or []
        if not music_source_has_library_content(str(source))
    ]


def get_mix_repair_readiness(meta: dict) -> dict:
    readiness = evaluate_repair_readiness(get_consistency_status(meta), meta.get("missing_file_search"))
    log_repair_readiness(readiness, str(meta.get("label") or meta.get("cache_path") or ""))
    return readiness


def format_repair_readiness_log(readiness: dict, mix_label: str = "") -> str:
    status = str(readiness.get("status") or "")
    target = f" for {mix_label!r}" if mix_label else ""
    availability = "available" if status == "ready" else "not available"
    details = f"status={status}, reason={readiness.get('reason') or ''!r}"
    if "still_listed" in readiness:
        details += (
            f", missing_files={readiness.get('missing_files')}"
            f", still_listed_by_kodi={len(readiness.get('still_listed') or [])}"
        )
    if readiness.get("sources_checked") is False:
        details += ", music_sources=unreadable"
    elif "unavailable_sources" in readiness:
        details += (
            f", unavailable_sources={len(readiness.get('unavailable_sources') or [])}"
            f", outside_sources={len(readiness.get('outside_sources') or [])}"
        )
    if readiness.get("unscanned_sources"):
        details += f", unscanned_sources={readiness.get('unscanned_sources')!r}"
    return f"Repair readiness: repair {availability}{target}; {details}"


def log_repair_readiness(readiness: dict, mix_label: str = "") -> None:
    log_info(format_repair_readiness_log(readiness, mix_label))


def update_mix_repair_readiness_metadata(cache_path: str, tracks: list[str], meta: dict) -> dict:
    readiness = get_mix_repair_readiness(meta)
    updated_meta = dict(meta)
    updated_meta["track_count"] = len(tracks)
    updated_meta["repair_readiness"] = readiness
    save_json_file(mix_meta_path_from_cache_path(cache_path), updated_meta)
    return readiness


def get_or_update_mix_repair_readiness(cache_path: str, tracks: list[str], meta: dict) -> dict:
    # Repair readiness depends on the Kodi library, which can change outside the
    # add-on while Kodi keeps running. Recalculate it whenever an inconsistent mix
    # is rendered, so the context menu reflects a recent scan or clean immediately.
    return update_mix_repair_readiness_metadata(cache_path, tracks, meta)


def is_repair_ready(readiness: dict) -> bool:
    return str(readiness.get("status") or "").lower() == "ready"


def build_repair_readiness_message(readiness: dict) -> str:
    reason = str(readiness.get("reason") or "")
    still_listed = [str(path) for path in readiness.get("still_listed") or []]

    lines = [
        reason or "Kodi music library should be updated before repair.",
        "",
        f"First inconsistency: {format_ts_for_display(int(readiness.get('first_inconsistent_ts') or 0))}",
        f"Latest inconsistency change: {format_ts_for_display(int(readiness.get('last_inconsistency_change_ts') or 0))}",
        f"Missing files: {int(readiness.get('missing_files') or 0)}",
    ]
    unavailable_sources = [str(source) for source in readiness.get("unavailable_sources") or []]
    if unavailable_sources:
        lines.extend(["", "Kodi music sources that no longer exist:"])
        lines.extend(f"- {source}" for source in unavailable_sources)
    outside = len(readiness.get("outside_sources") or [])
    if outside:
        lines.extend(["", f"Missing files outside all Kodi music sources: {outside}"])
    if still_listed:
        lines.extend(["", "Still listed by the Kodi music library:"])
        lines.extend(f"- {path}" for path in still_listed[:10])
        if len(still_listed) > 10:
            lines.append(f"- ... and {len(still_listed) - 10} more")

    unscanned = [str(source) for source in readiness.get("unscanned_sources") or []]
    if unscanned:
        lines.extend(["", "Found in music sources that are not scanned into the library:"])
        found = readiness.get("found_in_unscanned_sources") or {}
        lines.extend(f"- {location}" for location in list(found.values())[:10])
        if len(found) > 10:
            lines.append(f"- ... and {len(found) - 10} more")

    if str(readiness.get("status") or "") == "scan_source_before_repair":
        advice = "Scan these music sources into the library, then try repair again:\n" + "\n".join(
            f"- {source}" for source in unscanned
        )
    elif str(readiness.get("status") or "") == "update_sources_before_repair":
        advice = (
            "Update the Kodi music sources to match the folder structure on disk, "
            "then update and clean the library, then try repair again."
        )
    else:
        advice = "Update and clean the Kodi music library so it no longer lists these files, then try repair again."
    lines.extend(["", advice])
    return "\n".join(lines)


def show_update_library_before_repair(cache_path: str) -> None:
    tracks = load_mix_by_cache_path(cache_path)
    meta = get_saved_mix_metadata(cache_path, tracks)
    readiness = update_mix_repair_readiness_metadata(cache_path, tracks, meta)

    if is_repair_ready(readiness):
        xbmcgui.Dialog().ok(
            "Repair is now available",
            "The Kodi music library no longer lists the missing files.\n\n"
            "Close this dialog and reopen the context menu. "
            "Auto-repair this mix should now be available.",
        )
        return

    if str(readiness.get("status") or "") == "scan_source_before_repair":
        offer_to_scan_unscanned_sources(readiness)
        return

    if str(readiness.get("status") or "") == "update_sources_before_repair":
        # Scanning cannot help until the sources match the folders on disk.
        xbmcgui.Dialog().ok(repair_readiness_action_label(readiness), build_repair_readiness_message(readiness))
        return

    choice = xbmcgui.Dialog().select(
        "Update library before repair",
        [
            "Show details only",
            "Run Kodi music library scan",
            "Run Kodi music library cleanup",
            "Run scan, then cleanup",
        ],
    )

    if choice == 1:
        run_audio_library_maintenance("scan")
    elif choice == 2:
        run_audio_library_maintenance("clean")
    elif choice == 3:
        run_audio_library_maintenance("scan_clean")
    elif choice < 0:
        return

    xbmcgui.Dialog().ok("Update library before repair", build_repair_readiness_message(readiness))


def offer_to_scan_unscanned_sources(readiness: dict) -> bool:
    """Ask whether to scan the never-scanned sources that hold missing files; start the scan on yes."""
    sources = [str(source) for source in readiness.get("unscanned_sources") or []]
    if not sources:
        return False
    found = readiness.get("found_in_unscanned_sources") or {}
    message = (
        f"{len(found)} missing track(s) of this mix were found in music source(s) that are set up in Kodi "
        "but not scanned into the music library:\n"
        + "\n".join(f"- {source}" for source in sources)
        + "\n\nScan them into the library now?"
    )
    if not xbmcgui.Dialog().yesno("Scan music source before repair", message):
        return False
    for source in sources:
        execute_jsonrpc("AudioLibrary.Scan", {"directory": source})
    notify(f"Kodi music library scan started for {', '.join(sources)}.")
    return True


def ensure_repair_ready(cache_path: str) -> None:
    tracks = load_mix_by_cache_path(cache_path)
    meta = get_saved_mix_metadata(cache_path, tracks)
    readiness = update_mix_repair_readiness_metadata(cache_path, tracks, meta)
    if not is_repair_ready(readiness):
        raise MusicIPError(f"{repair_readiness_action_label(readiness)}.")


def format_saved_mix_label(meta: dict) -> str:
    label = meta.get("label") or path_to_label(meta.get("seed", ""))
    track_count = int(meta.get("track_count") or 0)
    if track_count > 0:
        return f"{label} ({track_count} tracks)"
    return label or "Stored mix"

def format_calendar_date(ts: int) -> str:
    if ts <= 0:
        return "Unknown date"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def build_saved_date_browse_url(date_key: str) -> str:
    return addon_url(action="saved_mixes_by_date", date=date_key, nonce=new_nonce())


def group_saved_mixes_by_date(cache_paths: list[str]) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    for cache_path in cache_paths:
        try:
            tracks = load_mix_by_cache_path(cache_path)
            meta = get_saved_mix_metadata(cache_path, tracks)
            updated_ts = int(meta.get("updated_ts") or 0)
        except Exception:
            updated_ts = 0
        date_key = format_calendar_date(updated_ts)
        grouped.setdefault(date_key, []).append(cache_path)

    def sort_key(item: tuple[str, list[str]]) -> tuple[int, str]:
        key = item[0]
        if key == "Unknown date":
            return (1, key)
        return (0, key)

    items = sorted(grouped.items(), key=sort_key, reverse=True)
    return items


def build_cleanup_date_action(date_key: str, include_older: bool = False) -> str:
    cleanup_url = addon_url(
        action="cleanup_saved_mixes",
        date=date_key,
        older="1" if include_older else "0",
        nonce=new_nonce(),
    )
    return f"RunPlugin({cleanup_url})"


def build_cleanup_saved_mix_action(cache_path: str) -> str:
    cleanup_url = addon_url(
        action="cleanup_saved_mix",
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({cleanup_url})"


def build_check_mix_action(cache_path: str) -> str:
    check_url = addon_url(
        action="check_mix_consistency",
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({check_url})"


def build_repair_mix_action(cache_path: str) -> str:
    repair_url = addon_url(
        action="repair_mix",
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({repair_url})"


def build_update_library_before_repair_action(cache_path: str) -> str:
    update_url = addon_url(
        action="update_library_before_repair",
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({update_url})"


def delete_saved_mix_files(cache_path: str) -> None:
    try:
        xbmcvfs.delete(cache_path)
    except Exception:
        pass
    meta_path = mix_meta_path_from_cache_path(cache_path)
    try:
        xbmcvfs.delete(meta_path)
    except Exception:
        pass


def cleanup_saved_mixes_for_date(date_key: str, include_older: bool = False) -> int:
    grouped = group_saved_mixes_by_date(list_saved_mix_cache_paths())
    removed = 0
    for group_date, cache_paths in grouped:
        match = False
        if include_older:
            if group_date == "Unknown date":
                match = False
            else:
                match = group_date <= date_key
        else:
            match = group_date == date_key

        if not match:
            continue

        for cache_path in cache_paths:
            delete_saved_mix_files(cache_path)
            removed += 1

    return removed

def get_current_seed_song() -> str:
    player = xbmc.Player()

    if not player.isPlayingAudio():
        raise MusicIPError("No audio is currently playing.")

    try:
        playing_file = player.getMusicInfoTag().getURL()
    except Exception as exc:
        raise MusicIPError("Kodi did not provide a playable filename.") from exc

    seed_song = (playing_file or "").strip()
    if not seed_song:
        raise MusicIPError("Could not determine the current song path.")

    return seed_song


def build_musicip_url(seed_song: str, size: int, mix_params: dict | None = None) -> str:
    params = mix_params or get_effective_mix_parameters(size_override=size)
    host = get_server_host()
    port = get_server_port()
    query = build_musicip_parameter_query(seed_song, params)
    return f"http://{host}:{port}/api/mix?{query}"


def decode_response(data: bytes) -> str:
    for enc in ("utf-8", "iso-8859-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def normalize_track_identity(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def prepend_seed_track(seed_song: str, tracks: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for track in [seed_song] + list(tracks):
        cleaned = (track or "").strip()
        normalized = normalize_track_identity(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)

    return result


def build_musicip_reload_url() -> str:
    host = get_server_host()
    port = get_server_port()
    return f"http://{host}:{port}/server/reload"


def reload_musicip_server_before_mix_generation() -> None:
    url = build_musicip_reload_url()
    timeout = get_timeout()

    log(f"Requesting MusicIP server reload before mix generation: {url!r}")

    try:
        with urlopen(url, timeout=timeout) as response:
            try:
                response.read()
            except Exception:
                pass
    except HTTPError as exc:
        try:
            error_body = exc.read()
        except Exception:
            error_body = b""

        log(f"MusicIP server reload HTTP error {exc.code}", xbmc.LOGERROR)
        log(f"MusicIP server reload URL: {url!r}", xbmc.LOGERROR)
        log(f"MusicIP server reload error body: {error_body!r}", xbmc.LOGERROR)
        raise MusicIPError(f"MusicIP server reload returned HTTP {exc.code}.") from exc
    except URLError as exc:
        log(f"MusicIP server reload URL error for {url!r}: {exc}", xbmc.LOGERROR)
        raise MusicIPError(f"Could not reload MusicIP server at {get_server_host()}:{get_server_port()}.") from exc
    except Exception as exc:
        log(f"MusicIP server reload failed for {url!r}: {exc}", xbmc.LOGERROR)
        raise MusicIPError(f"MusicIP server reload failed: {exc}") from exc


def fetch_mix(seed_song: str, size: int, mix_params: dict | None = None) -> list[str]:
    params = mix_params or get_effective_mix_parameters(size_override=size)
    reload_musicip_server_before_mix_generation()
    url = build_musicip_url(seed_song, size, params)
    timeout = get_timeout()

    try:
        encoded_seed = url.split("song=", 1)[1].split("&", 1)[0]
    except Exception:
        encoded_seed = ""

    log(f"MusicIP seed raw: {seed_song!r}", xbmc.LOGDEBUG)
    log(f"MusicIP seed encoded: {encoded_seed!r}", xbmc.LOGDEBUG)
    log(f"MusicIP playlist size: {size}", xbmc.LOGDEBUG)
    log(f"MusicIP mix parameters: {params!r}", xbmc.LOGDEBUG)
    log(f"MusicIP request URL: {url!r}", xbmc.LOGDEBUG)
    log(f"Requesting MusicIP mix: {url}")

    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        try:
            error_body = exc.read()
        except Exception:
            error_body = b""

        log(f"MusicIP HTTP error {exc.code}", xbmc.LOGERROR)
        log(f"MusicIP error URL: {url!r}", xbmc.LOGERROR)
        log(f"MusicIP error seed raw: {seed_song!r}", xbmc.LOGERROR)
        log(f"MusicIP error seed encoded: {encoded_seed!r}", xbmc.LOGERROR)
        log(f"MusicIP error playlist size: {size}", xbmc.LOGERROR)
        log(f"MusicIP error body: {error_body!r}", xbmc.LOGERROR)
        raise MusicIPError(f"MusicIP server returned HTTP {exc.code}.") from exc
    except URLError as exc:
        log(f"MusicIP URL error for {url!r}: {exc}", xbmc.LOGERROR)
        raise MusicIPError(f"Could not reach MusicIP server at {get_server_host()}:{get_server_port()}.") from exc
    except Exception as exc:
        log(f"MusicIP request failed for {url!r}: {exc}", xbmc.LOGERROR)
        raise MusicIPError(f"MusicIP request failed: {exc}") from exc

    text = decode_response(body)
    tracks = [line.strip() for line in text.splitlines() if line.strip()]
    if not tracks:
        raise MusicIPError("MusicIP returned an empty mix.")

    return prepend_seed_track(seed_song, tracks)


def fetch_mix_with_defaults(seed_song: str, size: int) -> list[str]:
    params = get_effective_mix_parameters(size_override=size)
    remember_mix_generation_parameters(seed_song, size, params)
    return fetch_mix(seed_song, size, mix_params=params)


def fetch_mix_confirmed(seed_song: str, size: int) -> list[str]:
    params = get_effective_mix_parameters(size_override=size)
    params = confirm_mix_generation(params)
    if params is None:
        raise MusicIPError("Mix generation cancelled.")

    remember_mix_generation_parameters(seed_song, size, params)
    return fetch_mix(seed_song, int(params.get("size") or size), mix_params=params)


def path_to_label(path: str) -> str:
    base = os.path.basename(path.rstrip("/\\"))
    title, _ext = os.path.splitext(base)
    return title if title else base if base else path


def new_nonce() -> str:
    return str(int(time.time() * 1000))


def build_focus_token(focus_index: int = -1) -> str:
    if focus_index < 0:
        return ""

    return new_nonce()


def build_browse_url(
    seed: str,
    size: int,
    refresh: bool = False,
    focus_index: int = -1,
    focus_token: str = "",
) -> str:
    query = {
        "action": "browse_mix",
        "seed": seed,
        "size": str(size),
        "nonce": new_nonce(),
    }
    if refresh:
        query["refresh"] = "1"
    if focus_index >= 0:
        query["focus_index"] = str(focus_index)
        query["focus_token"] = focus_token or build_focus_token(focus_index)
    return addon_url(**query)


def build_saved_browse_url(
    cache_path: str,
    refresh: bool = False,
    focus_index: int = -1,
    focus_token: str = "",
) -> str:
    query = {
        "action": "browse_saved_mix",
        "cache_path": cache_path,
        "nonce": new_nonce(),
    }
    if refresh:
        query["refresh"] = "1"
    if focus_index >= 0:
        query["focus_index"] = str(focus_index)
        query["focus_token"] = focus_token or build_focus_token(focus_index)
    return addon_url(**query)


def build_saved_mixes_url() -> str:
    return addon_url(action="saved_mixes", nonce=new_nonce())


def build_refresh_action(seed: str, size: int, cache_path: str = "") -> str:
    if cache_path:
        return f"Container.Update({build_saved_browse_url(cache_path, refresh=True)},replace)"
    return f"Container.Update({build_browse_url(seed, size, refresh=True)},replace)"


def build_remove_action(seed: str, size: int, index: int, path: str, cache_path: str = "") -> str:
    remove_url = addon_url(
        action="remove_track",
        seed=seed,
        size=str(size),
        index=str(index),
        path=path,
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({remove_url})"


def build_more_like_this_action(seed: str, size: int, index: int, path: str, cache_path: str = "") -> str:
    more_url = addon_url(
        action="more_like_this",
        seed=seed,
        size=str(size),
        index=str(index),
        path=path,
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({more_url})"


def build_less_like_this_action(seed: str, size: int, index: int, path: str, cache_path: str = "") -> str:
    less_url = addon_url(
        action="less_like_this",
        seed=seed,
        size=str(size),
        index=str(index),
        path=path,
        cache_path=cache_path,
        nonce=new_nonce(),
    )
    return f"RunPlugin({less_url})"


def remove_track_from_mix(seed: str, size: int, index: int, path: str, cache_path: str = "") -> str:
    target_cache_path = cache_path or mix_cache_path(seed, size)
    tracks = load_mix_by_cache_path(target_cache_path)
    if not tracks:
        raise MusicIPError("Stored mix is already empty.")

    removed_path = ""

    if 0 <= index < len(tracks):
        if not path or tracks[index] == path:
            removed_path = tracks.pop(index)

    if not removed_path and path:
        for pos, track in enumerate(tracks):
            if track == path:
                removed_path = tracks.pop(pos)
                break

    if not removed_path:
        raise MusicIPError("Could not remove the selected item from the stored mix.")

    payload = "\n".join(tracks)
    handle = xbmcvfs.File(target_cache_path, "w")
    try:
        handle.write(payload)
    finally:
        handle.close()

    meta = get_saved_mix_metadata(target_cache_path, tracks)
    meta["track_count"] = len(tracks)
    meta["updated_ts"] = int(time.time())
    save_json_file(mix_meta_path_from_cache_path(target_cache_path), meta)
    return removed_path



def get_more_like_this_target_size() -> int:
    return max(1, round(get_playlist_size() * 0.20))


def refresh_mix_container(url: str) -> None:
    xbmc.executebuiltin(f"Container.Update({url},replace)")


def focus_state_path() -> str:
    return os.path.join(get_profile_dir(), "focus_state.json")


def was_focus_token_already_applied(focus_token: str) -> bool:
    if not focus_token:
        return True

    state = load_json_file(focus_state_path())
    return str(state.get("last_focus_token") or "") == focus_token


def mark_focus_token_applied(focus_token: str) -> None:
    if not focus_token:
        return

    state = load_json_file(focus_state_path())
    state["last_focus_token"] = focus_token
    state["last_focus_ts"] = int(time.time())
    save_json_file(focus_state_path(), state)


def apply_pending_focus(focus_index: int = -1, focus_token: str = "") -> None:
    if focus_index < 0:
        return

    if was_focus_token_already_applied(focus_token):
        return

    mark_focus_token_applied(focus_token)

    try:
        xbmc.sleep(250)

        for _ in range(max(0, focus_index)):
            xbmc.executebuiltin("Action(Down)")
            xbmc.sleep(25)
    except Exception:
        pass


def find_track_position(tracks: list[str], index: int, path: str) -> int:
    if 0 <= index < len(tracks):
        if not path or tracks[index] == path:
            return index

    normalized_path = normalize_track_identity(path)
    if normalized_path:
        for pos, track in enumerate(tracks):
            if normalize_track_identity(track) == normalized_path:
                return pos

    if 0 <= index < len(tracks):
        return index

    return len(tracks) - 1


def insert_more_like_this_into_mix(seed: str, size: int, index: int, path: str, cache_path: str = "") -> int:
    if not path:
        raise MusicIPError("No seed track was supplied for More like this.")

    target_cache_path = cache_path or mix_cache_path(seed, size)
    source_tracks = load_mix_by_cache_path(target_cache_path)
    if not source_tracks:
        raise MusicIPError("Stored mix is empty.")

    insert_after = find_track_position(source_tracks, index, path)
    if insert_after < 0:
        raise MusicIPError("Could not locate the selected track in the source mix.")

    target_count = get_more_like_this_target_size()
    submix_tracks = fetch_mix_with_defaults(path, get_playlist_size())
    existing = {
        normalize_track_identity(track)
        for track in source_tracks
        if normalize_track_identity(track)
    }

    new_tracks: list[str] = []
    for track in submix_tracks:
        cleaned = (track or "").strip()
        normalized = normalize_track_identity(cleaned)
        if not cleaned or not normalized or normalized in existing:
            continue

        existing.add(normalized)
        new_tracks.append(cleaned)

        if len(new_tracks) >= target_count:
            break

    if not new_tracks:
        raise MusicIPError("No new tracks found for this song.")

    insert_at = insert_after + 1
    updated_tracks = source_tracks[:insert_at] + new_tracks + source_tracks[insert_at:]
    save_mix_by_cache_path(target_cache_path, updated_tracks)
    return len(new_tracks)



def remove_less_like_this_from_mix(seed: str, size: int, index: int, path: str, cache_path: str = "") -> int:
    if not path:
        raise MusicIPError("No seed track was supplied for Less like this.")

    target_cache_path = cache_path or mix_cache_path(seed, size)
    source_tracks = load_mix_by_cache_path(target_cache_path)
    if not source_tracks:
        raise MusicIPError("Stored mix is empty.")

    selected_position = find_track_position(source_tracks, index, path)
    if selected_position < 0:
        raise MusicIPError("Could not locate the selected track in the source mix.")

    target_count = get_more_like_this_target_size()
    submix_request_size = max(1, get_playlist_size() * 2)
    submix_tracks = fetch_mix_with_defaults(path, submix_request_size)
    selected_seed_identity = normalize_track_identity(path)

    removable_matches: set[str] = set()
    if selected_seed_identity:
        removable_matches.add(selected_seed_identity)

    for track in submix_tracks:
        normalized = normalize_track_identity((track or "").strip())
        if normalized:
            removable_matches.add(normalized)

    if not removable_matches:
        raise MusicIPError("No matching tracks found for this song.")

    removed = 0
    updated_tracks: list[str] = []

    for pos, track in enumerate(source_tracks):
        normalized = normalize_track_identity(track)

        if pos == selected_position:
            removed += 1
            continue

        if normalized in removable_matches and removed < target_count:
            removed += 1
            continue

        updated_tracks.append(track)

    if removed <= 0:
        raise MusicIPError("No matching tracks from the source mix could be removed.")

    save_mix_by_cache_path(target_cache_path, updated_tracks)
    return removed


def is_addon_mix_container_active() -> bool:
    try:
        plugin_name = (xbmc.getInfoLabel("Container.PluginName") or "").strip()
        folder_path = (xbmc.getInfoLabel("Container.FolderPath") or "").strip()
    except Exception:
        return False

    if plugin_name == ADDON_ID:
        return True

    return folder_path.startswith(f"plugin://{ADDON_ID}/")


def ensure_remove_allowed_from_addon_container() -> None:
    if not is_addon_mix_container_active():
        raise MusicIPError("Remove from mix is only available inside the MusicIP add-on.")


def get_current_music_tag() -> object | None:
    try:
        player = xbmc.Player()
        if not player.isPlayingAudio():
            return None
        return player.getMusicInfoTag()
    except Exception:
        return None


def get_current_player_metadata(path: str | None = None) -> dict[str, str]:
    music_tag = get_current_music_tag()
    if music_tag is None:
        return {}

    try:
        current_path = (music_tag.getURL() or '').strip()
    except Exception:
        current_path = ''

    if path and current_path and current_path != path:
        return {}

    data: dict[str, str] = {}

    try:
        title = (music_tag.getTitle() or '').strip()
        if title:
            data['title'] = title
    except Exception:
        pass

    try:
        artist = (music_tag.getArtist() or '').strip()
        if artist:
            data['artist'] = artist
    except Exception:
        pass

    try:
        album = (music_tag.getAlbum() or '').strip()
        if album:
            data['album'] = album
    except Exception:
        pass

    try:
        year = parse_year(music_tag.getYear())
        if year > 0:
            data['year'] = year
    except Exception:
        pass

    try:
        genres = normalize_genres(music_tag.getGenres())
        if genres:
            data['genre'] = genres
    except Exception:
        try:
            genres = normalize_genres(music_tag.getGenre())
            if genres:
                data['genre'] = genres
        except Exception:
            pass

    try:
        duration = parse_duration_seconds(music_tag.getDuration())
        if duration > 0:
            data['duration'] = duration
    except Exception:
        pass

    return data


def execute_jsonrpc(method: str, params: dict | None = None) -> dict:
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': method,
    }
    if params:
        payload['params'] = params

    raw = xbmc.executeJSONRPC(json.dumps(payload))
    response = json.loads(raw)
    if 'error' in response:
        raise MusicIPError(f"Kodi JSON-RPC error for {method}: {response['error']}")
    return response.get('result', {})


def run_audio_library_maintenance(mode: str) -> None:
    if mode == "scan":
        execute_jsonrpc("AudioLibrary.Scan")
        notify("Kodi music library scan started.")
    elif mode == "clean":
        execute_jsonrpc("AudioLibrary.Clean")
        notify("Kodi music library cleanup started.")
    elif mode == "scan_clean":
        execute_jsonrpc("AudioLibrary.Scan")
        execute_jsonrpc("AudioLibrary.Clean")
        notify("Kodi music library scan and cleanup started.")
    else:
        notify("No library action selected.", xbmcgui.NOTIFICATION_WARNING)


def split_full_path(path: str) -> tuple[str, str]:
    value = (path or '').strip().rstrip('/\\')
    if not value:
        return '', ''

    slash_pos = max(value.rfind('/'), value.rfind('\\'))
    if slash_pos < 0:
        return value, ''

    return value[slash_pos + 1 :], value[:slash_pos]


def build_path_candidates(directory: str) -> list[str]:
    raw = (directory or '').strip().rstrip('/\\')
    if not raw:
        return []

    candidates: list[str] = []

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(raw)
    normalized = raw.replace('\\', '/')
    add(normalized)

    if '://' in normalized:
        add(normalized + '/')
    else:
        add(raw + os.sep)
        add(normalized + '/')
        if '\\' in raw:
            add(raw + '\\')

    return candidates


def canonical_audio_path(path: str) -> str:
    value = (path or "").strip()
    value = unquote(value)
    value = unicodedata.normalize("NFC", value)
    value = value.replace("\\", "/")

    if "://" in value:
        scheme, rest = value.split("://", 1)
        while "//" in rest:
            rest = rest.replace("//", "/")
        value = f"{scheme.lower()}://{rest}"
    else:
        while "//" in value:
            value = value.replace("//", "/")

    return value.rstrip("/").casefold()


def basename_key(path: str) -> str:
    value = canonical_audio_path(path)
    slash_pos = value.rfind("/")
    return value[slash_pos + 1:] if slash_pos >= 0 else value


def tail_key(path: str, segments: int = 3) -> str:
    value = canonical_audio_path(path)
    parts = [part for part in value.split("/") if part]
    if not parts:
        return ""
    return "/".join(parts[-segments:])


def find_song_by_file(songs: list[dict], path: str) -> dict | None:
    target = canonical_audio_path(path)

    for song in songs:
        song_file = canonical_audio_path(str(song.get("file") or ""))
        if song_file == target:
            return song

    return None


def find_song_by_file_relaxed(songs: list[dict], path: str) -> dict | None:
    matched_song = find_song_by_file(songs, path)
    if matched_song is not None:
        return matched_song

    target_base = basename_key(path)
    basename_matches = [
        song for song in songs
        if basename_key(str(song.get("file") or "")) == target_base
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]

    target_tail = tail_key(path, segments=3)
    suffix_matches: list[dict] = []
    for song in songs:
        song_file = canonical_audio_path(str(song.get("file") or ""))
        if target_tail and song_file.endswith(target_tail):
            suffix_matches.append(song)

    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


def log_library_candidates(path: str, songs: list[dict]) -> None:
    log(f"MusicIP path: {path!r}", xbmc.LOGDEBUG)
    log(f"Canonical MusicIP path: {canonical_audio_path(path)!r}", xbmc.LOGDEBUG)
    for song in songs:
        file_value = str(song.get("file") or "")
        log(f"Kodi candidate file: {file_value!r}", xbmc.LOGDEBUG)
        log(f"Kodi candidate canonical: {canonical_audio_path(file_value)!r}", xbmc.LOGDEBUG)


def get_unique_song_candidates(songs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []

    for song in songs:
        file_value = str(song.get("file") or "").strip()
        key = canonical_audio_path(file_value)
        if not file_value or not key or key in seen:
            continue

        seen.add(key)
        result.append(song)

    return result


def strip_audio_extension(value: str) -> str:
    return re.sub(r"\.(mp3|flac|m4a|mp4|aac|ogg|opus|wav|aiff|ape|wma)$", "", value or "", flags=re.IGNORECASE).strip()


def normalize_repair_text(value: object) -> str:
    text = first_non_empty_text(value)
    text = unicodedata.normalize("NFC", text)
    text = unquote(text)
    text = strip_audio_extension(text)
    text = text.casefold()
    text = re.sub(r"[\[\(]\s*(19|20)\d{2}\s*[\]\)]\s*$", " ", text)
    text = re.sub(r"\b(19|20)\d{2}\b\s*$", " ", text)
    text = re.sub(r"^\s*\d{1,3}\s*[\.\-_\)]\s*", " ", text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


REPAIR_BROAD_TERMS = {"music", "modernrock", "rock", "compilations", "various artists"}


def repair_match_key(value: object) -> str:
    # Comparison only: "Motörhead" equals "Motorhead". Kodi queries keep the diacritics.
    text = unicodedata.normalize("NFKD", normalize_repair_text(value))
    return "".join(char for char in text if not unicodedata.combining(char))


def add_unique_text(values: list[str], value: object) -> None:
    text = normalize_repair_text(value)
    if text and len(text) >= 3 and text not in values:
        values.append(text)


def extract_year_hint(value: str) -> int:
    match = re.search(r"[\[\(]?\b((?:19|20)\d{2})\b[\]\)]?", value or "")
    if not match:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def split_leading_track_number(stem: str) -> tuple[int, int, str, str]:
    """
    Split a leading track number off a filename stem.

    Returns (track_number, possible_track_number, stem_without_number, ambiguous_stem).
    "03 - Title", "3. Title", "03 Title" and "1-03 Title" carry a reliable track number.
    An unpadded number followed only by a space ("12 Title") may also be part of the
    title ("99 Luftballons"), so it is only reported as possible_track_number and the
    unstripped stem is returned as ambiguous_stem.
    """
    text = (stem or "").strip()

    match = re.match(r"^\d{1,2}-(\d{2,3})\s*[\.\-_\)]?\s+(\S.*)$", text)
    if match:
        return int(match.group(1)), 0, match.group(2).strip(), ""

    match = re.match(r"^(\d{1,3})\s*[\.\-_\)]\s*(.*)$", text)
    if match:
        return int(match.group(1)), 0, match.group(2).strip(), ""

    match = re.match(r"^(\d{1,3})\s+(\S.*)$", text)
    if match:
        if match.group(1).startswith("0"):
            return int(match.group(1)), 0, match.group(2).strip(), ""
        return 0, int(match.group(1)), match.group(2).strip(), text

    return 0, 0, text, ""


def split_artist_title_hints(stem: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    parts = re.split(r"\s+[-–—]\s+", stem or "", maxsplit=1)
    if len(parts) != 2:
        return result

    left = normalize_repair_text(parts[0])
    right = normalize_repair_text(parts[1])
    if left and right:
        result.append((left, right))
        result.append((right, left))

    return result


def directory_hint_values(directory: str) -> list[str]:
    value = canonical_audio_path(directory)
    parts = [part for part in value.split("/") if part]
    result: list[str] = []

    for part in parts[-4:]:
        # "#genre" folders are library categories, not artist or album names.
        if part.startswith("#"):
            continue
        cleaned = re.sub(r"[\[\(]?\b(19|20)\d{2}\b[\]\)]?", " ", part)
        if normalize_repair_text(cleaned) in REPAIR_BROAD_TERMS:
            continue
        add_unique_text(result, cleaned)

    return result


def parse_structured_filename_hints(stem: str) -> dict:
    parts = [part.strip() for part in re.split(r"\s+[-–—]\s+", stem or "") if part.strip()]
    result = {"artist": "", "album": "", "title": "", "track_number": 0}

    # Common pattern: Artist - Album - 12 - Title
    if len(parts) >= 4 and re.fullmatch(r"\d{1,3}", parts[-2]):
        result["artist"] = normalize_repair_text(parts[0])
        result["album"] = normalize_repair_text(" - ".join(parts[1:-2]))
        result["track_number"] = int(parts[-2])
        result["title"] = normalize_repair_text(parts[-1])
        return result

    # Also accept: Artist - Album - 12 Title
    if len(parts) >= 3:
        match = re.match(r"^\s*(\d{1,3})\s+(.+)$", parts[-1])
        if match:
            result["artist"] = normalize_repair_text(parts[0])
            result["album"] = normalize_repair_text(" - ".join(parts[1:-1]))
            result["track_number"] = int(match.group(1))
            result["title"] = normalize_repair_text(match.group(2))
            return result

    return result


def repair_tokens(value: object) -> set[str]:
    return {token for token in normalize_repair_text(value).split() if len(token) >= 2}


def is_strong_text_match(expected: str, actual: str) -> bool:
    expected_norm = repair_match_key(expected)
    actual_norm = repair_match_key(actual)
    if not expected_norm or not actual_norm:
        return False
    if expected_norm == actual_norm:
        return True

    expected_tokens = repair_tokens(expected_norm)
    actual_tokens = repair_tokens(actual_norm)
    if not expected_tokens or not actual_tokens:
        return False

    overlap = expected_tokens & actual_tokens
    if len(overlap) < 2:
        return False

    coverage_actual = len(overlap) / max(1, len(actual_tokens))
    coverage_expected = len(overlap) / max(1, len(expected_tokens))
    return coverage_actual >= 0.80 and coverage_expected >= 0.60


def build_repair_hints(old_path: str) -> dict:
    filename, directory = split_full_path(old_path)
    stem = strip_audio_extension(filename)
    filename_track, possible_track, stem_no_track, ambiguous_stem = split_leading_track_number(stem)
    stem_no_year = re.sub(r"[\[\(]?\b(19|20)\d{2}\b[\]\)]?\s*$", "", stem_no_track).strip()

    structured = parse_structured_filename_hints(stem_no_year)

    possible_titles: list[str] = []
    possible_artists: list[str] = []
    possible_albums: list[str] = []
    search_terms: list[str] = []

    if structured.get("title"):
        add_unique_text(possible_titles, structured.get("title"))
        add_unique_text(search_terms, structured.get("title"))
    if structured.get("artist"):
        add_unique_text(possible_artists, structured.get("artist"))
        add_unique_text(search_terms, structured.get("artist"))
    if structured.get("album"):
        add_unique_text(possible_albums, structured.get("album"))
        add_unique_text(search_terms, structured.get("album"))

    if not structured.get("title"):
        add_unique_text(possible_titles, stem_no_year)
        add_unique_text(possible_titles, stem_no_track)
        add_unique_text(search_terms, stem_no_year)
        add_unique_text(search_terms, stem_no_track)
        if ambiguous_stem:
            add_unique_text(possible_titles, ambiguous_stem)
            add_unique_text(search_terms, ambiguous_stem)

        pairs = split_artist_title_hints(stem_no_year)
        for possible_artist, possible_title in pairs:
            add_unique_text(possible_artists, possible_artist)
            add_unique_text(possible_titles, possible_title)
            add_unique_text(search_terms, possible_artist)
            add_unique_text(search_terms, possible_title)

    folder_hints = directory_hint_values(directory)
    for hint in folder_hints:
        add_unique_text(search_terms, hint)

    year = extract_year_hint(stem) or extract_year_hint(directory)
    track_number = int(structured.get("track_number") or 0) or filename_track

    return {
        "old_path": old_path,
        "filename": filename,
        "stem": stem,
        "track_number": track_number,
        "possible_track_number": 0 if track_number else possible_track,
        "year": year,
        "possible_titles": possible_titles,
        "possible_artists": possible_artists,
        "possible_albums": possible_albums,
        "folder_hints": folder_hints,
        "search_terms": search_terms[:8],
    }


def audio_library_get_songs_with_metadata_properties(params: dict, context: str) -> list[dict]:
    request_params = dict(params or {})
    request_params["properties"] = SONG_METADATA_PROPERTIES

    try:
        result = execute_jsonrpc("AudioLibrary.GetSongs", request_params)
        return result.get("songs") or []
    except Exception as exc:
        log(f"{context}: metadata lookup failed with full properties: {exc}", xbmc.LOGDEBUG)

    safe_params = dict(params or {})
    safe_params["properties"] = SONG_METADATA_SAFE_PROPERTIES

    try:
        result = execute_jsonrpc("AudioLibrary.GetSongs", safe_params)
        songs = result.get("songs") or []
        log(f"{context}: metadata lookup retried with safe properties; returned {len(songs)} song(s).", xbmc.LOGDEBUG)
        return songs
    except Exception as exc:
        log(f"{context}: metadata lookup failed with safe properties: {exc}", xbmc.LOGDEBUG)
        return []


def query_library_songs_contains(field: str, value: str) -> list[dict]:
    term = (value or "").strip()
    if not term:
        return []

    return audio_library_get_songs_with_metadata_properties(
        {
            "filter": {"field": field, "operator": "contains", "value": term},
        },
        f"Auto-repair fallback {field} contains {term!r}",
    )

def collect_fallback_repair_candidates(hints: dict) -> list[dict]:
    raw_candidates: list[dict] = []
    seen_queries: set[tuple[str, str]] = set()

    def run_query(field: str, value: str) -> None:
        normalized_value = normalize_repair_text(value)
        if len(normalized_value) < 3:
            return
        if normalized_value in REPAIR_BROAD_TERMS:
            log_info(f"Auto-repair fallback: skipping broad query term {normalized_value!r}")
            return

        query_key = (field, normalized_value)
        if query_key in seen_queries:
            return

        seen_queries.add(query_key)
        log_info(f"Auto-repair fallback: query {field} contains {normalized_value!r}")
        result = query_library_songs_contains(field, normalized_value)
        log_info(f"Auto-repair fallback: query returned {len(result)} candidate(s).")
        raw_candidates.extend(result)

    for term in hints.get("search_terms") or []:
        run_query("title", term)
        run_query("filename", term)

    for title in hints.get("possible_titles") or []:
        run_query("title", title)

    for artist in hints.get("possible_artists") or []:
        run_query("artist", artist)

    for folder_hint in hints.get("folder_hints") or []:
        # Folder hints are weak evidence only. Query album, never artist.
        run_query("album", folder_hint)

    unique_candidates = get_unique_song_candidates(raw_candidates)
    log_info(
        f"Auto-repair fallback: collected {len(raw_candidates)} raw candidate(s), "
        f"{len(unique_candidates)} unique candidate(s)."
    )
    return unique_candidates


def candidate_artist_values(song: dict) -> list[str]:
    values: list[str] = []
    for key in ("artist", "displayartist", "albumartist"):
        value = song.get(key)
        if isinstance(value, list):
            for item in value:
                add_unique_text(values, item)
        else:
            add_unique_text(values, value)
    return values


def candidate_file_stem(song: dict) -> str:
    return normalize_repair_text(path_to_label(str(song.get("file") or "")))


def score_repair_candidate(song: dict, hints: dict) -> tuple[int, list[str], bool]:
    score = 0
    reasons: list[str] = []
    strong_title_match = False
    strong_track_mismatch = False

    artist_match = False
    album_match = False

    candidate_title = repair_match_key(song.get("title"))
    candidate_album = repair_match_key(song.get("album"))
    candidate_artists = [repair_match_key(artist) for artist in candidate_artist_values(song)]
    candidate_file = candidate_file_stem(song)
    possible_titles = hints.get("possible_titles") or []
    possible_artists = [repair_match_key(artist) for artist in hints.get("possible_artists") or []]
    possible_albums = [repair_match_key(album) for album in hints.get("possible_albums") or []]
    folder_hints = [repair_match_key(hint) for hint in hints.get("folder_hints") or []]

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(f"+{points} {reason}")

    def subtract(points: int, reason: str) -> None:
        nonlocal score
        score -= points
        reasons.append(f"-{points} {reason}")

    for title in possible_titles:
        if is_strong_text_match(title, candidate_title):
            add(90, f"strong title match {title!r}")
            strong_title_match = True
            break

    if not strong_title_match:
        for title in possible_titles:
            if is_strong_text_match(title, candidate_file):
                add(70, f"strong filename title match {title!r}")
                strong_title_match = True
                break

    if possible_artists and candidate_artists:
        for artist in possible_artists:
            if artist in candidate_artists:
                add(35, f"artist match {artist!r}")
                artist_match = True
                break
        else:
            for artist in possible_artists:
                if any(is_strong_text_match(artist, candidate_artist) for candidate_artist in candidate_artists):
                    add(20, f"artist partial match {artist!r}")
                    artist_match = True
                    break

    if not artist_match and candidate_artists:
        for folder_hint in folder_hints:
            if folder_hint in candidate_artists:
                add(20, f"folder/artist hint match {folder_hint!r}")
                artist_match = True
                break

    for album in possible_albums:
        if album and candidate_album == album:
            add(25, f"album match {album!r}")
            album_match = True
            break

    for folder_hint in folder_hints:
        if folder_hint and candidate_album == folder_hint:
            add(15, f"folder/album hint match {folder_hint!r}")
            album_match = True
            break

    hint_year = int(hints.get("year") or 0)
    candidate_year = parse_year(song.get("year"))
    if hint_year and candidate_year and hint_year == candidate_year:
        add(20, f"year match {hint_year}")

    hint_track = int(hints.get("track_number") or 0)
    candidate_track = parse_track_number(song.get("track"))
    if hint_track and candidate_track:
        if hint_track == candidate_track:
            add(40, f"track number match {hint_track}")
        elif album_match:
            strong_track_mismatch = True
            subtract(80, f"track number mismatch expected {hint_track}, got {candidate_track}")
        else:
            # Same song on another release: a different track number is expected.
            reasons.append(f"0 track number {candidate_track} differs from {hint_track} on another album")
    else:
        # Unpadded leading number ("12 Title") may be part of the title: reward a match, never penalize.
        possible_track = int(hints.get("possible_track_number") or 0)
        if possible_track and candidate_track and possible_track == candidate_track:
            add(40, f"possible track number match {possible_track}")

    # Year and track number alone do not identify a song.
    if not (strong_title_match or artist_match or album_match):
        reasons.append("no title, artist or album evidence")
        return 0, reasons, False

    return score, reasons, strong_title_match and not strong_track_mismatch


def score_fallback_repair_candidates(candidates: list[dict], hints: dict) -> list[dict]:
    scored: list[dict] = []
    for candidate in candidates:
        score, reasons, safe_auto = score_repair_candidate(candidate, hints)
        if score <= 0:
            continue

        enriched = dict(candidate)
        enriched["_repair_score"] = score
        enriched["_repair_reasons"] = reasons
        enriched["_repair_safe_auto"] = safe_auto
        scored.append(enriched)

    scored.sort(key=lambda item: int(item.get("_repair_score") or 0), reverse=True)
    log_info(f"Auto-repair fallback: {len(scored)} scored candidate(s).")
    for index, candidate in enumerate(scored[:15], start=1):
        log_info(
            f"Auto-repair fallback score {index}: "
            f"score={candidate.get('_repair_score')}, "
            f"safe_auto={candidate.get('_repair_safe_auto')}, "
            f"file={str(candidate.get('file') or '').strip()!r}, "
            f"reasons={candidate.get('_repair_reasons')}"
        )

    return scored


def get_fallback_repair_candidates(old_path: str) -> list[dict]:
    hints = build_repair_hints(old_path)
    log_info(
        "Auto-repair fallback hints: "
        f"titles={hints.get('possible_titles')}, "
        f"artists={hints.get('possible_artists')}, "
        f"albums={hints.get('possible_albums')}, "
        f"year={hints.get('year')}, "
        f"track={hints.get('track_number')}, "
        f"possible_track={hints.get('possible_track_number')}, "
        f"terms={hints.get('search_terms')}"
    )

    candidates = collect_fallback_repair_candidates(hints)
    return score_fallback_repair_candidates(candidates, hints)


def get_repair_candidates_for_path(old_path: str) -> list[dict]:
    filename, _directory = split_full_path(old_path)
    if not filename:
        log_info(f"Auto-repair: no filename could be extracted from old path: {old_path!r}")
        return []

    log_info(f"Auto-repair: primary lookup by exact filename: {filename!r}")
    candidates = query_library_songs_by_filename(filename)
    unique_candidates = get_unique_song_candidates(candidates)
    log_info(
        f"Auto-repair: primary lookup returned {len(candidates)} raw candidate(s), "
        f"{len(unique_candidates)} unique candidate(s) for {filename!r}."
    )

    if unique_candidates:
        log_info("Auto-repair: using primary filename candidate strategy.")
        return unique_candidates

    log_info("Auto-repair: primary lookup returned no candidates; starting fallback heuristics.")
    return get_fallback_repair_candidates(old_path)


def format_repair_candidate_label(song: dict) -> str:
    title = str(song.get("title") or "").strip()
    artist = first_non_empty_text(song.get("artist"))
    album = str(song.get("album") or "").strip()
    file_value = str(song.get("file") or "").strip()
    score = int(song.get("_repair_score") or 0)
    reasons = song.get("_repair_reasons") or []

    parts: list[str] = []
    if score:
        parts.append(str(score))
    if artist:
        parts.append(artist)
    if title:
        parts.append(title)
    if album:
        parts.append(f"[{album}]")

    label = " - ".join(parts) if parts else (file_value or "Unknown candidate")
    if score and reasons:
        label = f"{label} · {', '.join(str(reason) for reason in reasons[:3])}"

    if file_value:
        return f"{label} · {file_value}"

    return label


def log_repair_candidates(old_path: str, candidates: list[dict]) -> None:
    log_info(f"Auto-repair: missing path: {old_path!r}")
    log_info(f"Auto-repair: candidate count: {len(candidates)}")
    for index, candidate in enumerate(candidates, start=1):
        log_info(
            "Auto-repair candidate "
            f"{index}: file={str(candidate.get('file') or '').strip()!r}, "
            f"title={str(candidate.get('title') or '').strip()!r}, "
            f"artist={first_non_empty_text(candidate.get('artist'))!r}, "
            f"album={str(candidate.get('album') or '').strip()!r}"
        )


def choose_repair_candidate(old_path: str, candidates: list[dict]) -> str:
    log_repair_candidates(old_path, candidates)

    if not candidates:
        log_info("Auto-repair: no repair candidates found.")
        return ""

    scored_candidates = [candidate for candidate in candidates if int(candidate.get("_repair_score") or 0) > 0]
    if scored_candidates:
        sorted_candidates = sorted(scored_candidates, key=lambda item: int(item.get("_repair_score") or 0), reverse=True)
        best = sorted_candidates[0]
        best_score = int(best.get("_repair_score") or 0)
        second_score = int(sorted_candidates[1].get("_repair_score") or 0) if len(sorted_candidates) > 1 else 0
        score_gap = best_score - second_score

        best_safe_auto = bool(best.get("_repair_safe_auto"))
        if best_safe_auto and best_score >= 120 and score_gap >= 35:
            value = str(best.get("file") or "").strip()
            if value:
                log_info(
                    f"Auto-repair fallback: high-confidence candidate selected automatically: "
                    f"score={best_score}, gap={score_gap}, safe_auto={best_safe_auto}, file={value!r}"
                )
                return value

        log_info(
            f"Auto-repair fallback: no high-confidence automatic match. "
            f"best_score={best_score}, second_score={second_score}, gap={score_gap}, "
            f"safe_auto={best_safe_auto}."
        )
        candidates = sorted_candidates[:25]
    else:
        matched = find_song_by_file_relaxed(candidates, old_path)
        if matched is not None:
            value = str(matched.get("file") or "").strip()
            if value:
                log_info(f"Auto-repair: relaxed lookup selected candidate automatically: {value!r}")
                return value

        if len(candidates) == 1:
            value = str(candidates[0].get("file") or "").strip()
            log_info(f"Auto-repair: single candidate selected automatically: {value!r}")
            return value

    log_info("Auto-repair: ambiguous candidates found, showing manual selection dialog.")
    labels = ["Skip this track"] + [format_repair_candidate_label(song) for song in candidates]
    selected = xbmcgui.Dialog().select(
        f"Repair missing track: {path_to_label(old_path)}",
        labels,
    )

    if selected < 0:
        log_info("Auto-repair: manual selection cancelled.")
        raise MusicIPError("Repair cancelled.")

    if selected == 0:
        log_info("Auto-repair: user skipped this track.")
        return ""

    value = str(candidates[selected - 1].get("file") or "").strip()
    log_info(f"Auto-repair: user selected repair candidate: {value!r}")
    return value


def choose_repair_candidate_automatic_only(old_path: str, candidates: list[dict]) -> str:
    log_repair_candidates(old_path, candidates)

    if not candidates:
        log_info("Auto-repair service: no repair candidates found.")
        return ""

    scored_candidates = [candidate for candidate in candidates if int(candidate.get("_repair_score") or 0) > 0]
    if scored_candidates:
        sorted_candidates = sorted(scored_candidates, key=lambda item: int(item.get("_repair_score") or 0), reverse=True)
        best = sorted_candidates[0]
        best_score = int(best.get("_repair_score") or 0)
        second_score = int(sorted_candidates[1].get("_repair_score") or 0) if len(sorted_candidates) > 1 else 0
        score_gap = best_score - second_score
        best_safe_auto = bool(best.get("_repair_safe_auto"))

        high_confidence_candidates = [
            candidate
            for candidate in sorted_candidates
            if bool(candidate.get("_repair_safe_auto"))
            and int(candidate.get("_repair_score") or 0) >= 120
        ]

        if len(high_confidence_candidates) == 1 and best_safe_auto and best_score >= 120 and score_gap >= 35:
            value = str(best.get("file") or "").strip()
            if value:
                log_info(
                    f"Auto-repair service: high-confidence fallback candidate selected: "
                    f"score={best_score}, gap={score_gap}, file={value!r}"
                )
                return value

        log_info(
            f"Auto-repair service: no safe automatic fallback match. "
            f"best_score={best_score}, second_score={second_score}, gap={score_gap}, "
            f"safe_auto={best_safe_auto}, high_confidence_count={len(high_confidence_candidates)}."
        )
        return ""

    matched = find_song_by_file_relaxed(candidates, old_path)
    if matched is not None:
        value = str(matched.get("file") or "").strip()
        if value:
            log_info(f"Auto-repair service: relaxed lookup selected candidate: {value!r}")
            return value

    if len(candidates) == 1:
        value = str(candidates[0].get("file") or "").strip()
        log_info(f"Auto-repair service: single primary candidate selected: {value!r}")
        return value

    log_info(f"Auto-repair service: {len(candidates)} unscored candidates found; manual repair required.")
    return ""


def repair_saved_mix_automatic_only(cache_path: str) -> int:
    log_info(f"Auto-repair service: started for saved mix: {cache_path!r}")

    tracks = load_mix_by_cache_path(cache_path)
    if not tracks:
        log_info("Auto-repair service: stored mix is empty.")
        return 0

    repaired = 0
    missing = 0
    updated_tracks: list[str] = []

    for index, track in enumerate(tracks):
        if track_file_exists(track):
            updated_tracks.append(track)
            continue

        missing += 1
        log_info(f"Auto-repair service: track {index} is missing: {track!r}")

        candidates = get_repair_candidates_for_path(track)
        replacement = choose_repair_candidate_automatic_only(track, candidates)

        if replacement:
            log_info(f"Auto-repair service: replacing {track!r} with {replacement!r}")
            updated_tracks.append(replacement)
            repaired += 1
        else:
            log_info(f"Auto-repair service: no safe automatic replacement for {track!r}")
            updated_tracks.append(track)

    log_info(f"Auto-repair service: completed candidate handling. Missing={missing}, repaired={repaired}.")

    if repaired <= 0:
        return 0

    save_mix_by_cache_path(cache_path, updated_tracks)
    analyze_mix_consistency(cache_path)
    log_info(f"Auto-repair service: saved repaired mix. Repaired={repaired}.")
    return repaired


def repair_saved_mix_foreground(cache_path: str) -> int:
    log_info(f"Auto-repair: started for saved mix: {cache_path!r}")

    tracks = load_mix_by_cache_path(cache_path)
    if not tracks:
        log_info("Auto-repair: stored mix is empty.")
        raise MusicIPError("Stored mix is empty.")

    repaired = 0
    missing = 0
    updated_tracks: list[str] = []

    for index, track in enumerate(tracks):
        if track_file_exists(track):
            updated_tracks.append(track)
            continue

        missing += 1
        log_info(f"Auto-repair: track {index} is missing: {track!r}")

        candidates = get_repair_candidates_for_path(track)
        replacement = choose_repair_candidate(track, candidates)

        if replacement:
            log_info(f"Auto-repair: replacing {track!r} with {replacement!r}")
            updated_tracks.append(replacement)
            repaired += 1
        else:
            log_info(f"Auto-repair: no replacement selected for {track!r}")
            updated_tracks.append(track)

    log_info(f"Auto-repair: completed candidate handling. Missing={missing}, repaired={repaired}.")

    if repaired <= 0:
        analyze_mix_consistency(cache_path)
        log_info("Auto-repair: no tracks were repaired.")
        raise MusicIPError("No tracks were repaired.")

    save_mix_by_cache_path(cache_path, updated_tracks)
    analyze_mix_consistency(cache_path)
    log_info(f"Auto-repair: saved repaired mix. Repaired={repaired}.")
    return repaired


def query_library_songs_by_filename(filename: str) -> list[dict]:
    if not filename:
        return []

    return audio_library_get_songs_with_metadata_properties(
        {
            "filter": {"field": "filename", "operator": "is", "value": filename},
        },
        f"Filename-only library lookup for {filename!r}",
    )

def query_library_songs_strict(filename: str, directory: str) -> list[dict]:
    if not filename:
        return []

    filters: list[dict] = [
        {"field": "filename", "operator": "is", "value": filename},
    ]

    path_candidates = build_path_candidates(directory)
    log(f"Library lookup filename={filename!r} path_candidates={path_candidates!r}", xbmc.LOGDEBUG)
    if path_candidates:
        filters.append({
            "or": [
                {"field": "path", "operator": "is", "value": candidate}
                for candidate in path_candidates
            ]
        })

    return audio_library_get_songs_with_metadata_properties(
        {
            "filter": {"and": filters},
        },
        f"Strict library lookup for {filename!r}",
    )

def first_non_empty_text(value: object) -> str:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ' / '.join(parts)
    return str(value or '').strip()


def parse_duration_seconds(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def parse_year(value: object) -> int:
    try:
        year = int(value or 0)
    except (TypeError, ValueError):
        return 0

    if year <= 0:
        return 0

    return year


def parse_track_number(value: object) -> int:
    if isinstance(value, list):
        value = value[0] if value else 0

    text = str(value or "").strip()
    if not text:
        return 0

    try:
        return max(0, int(text))
    except (TypeError, ValueError):
        match = re.match(r"^\s*(\d{1,3})", text)
        if not match:
            return 0
        try:
            return max(0, int(match.group(1)))
        except (TypeError, ValueError):
            return 0


def normalize_genres(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text_value = str(value or '').strip()
    if not text_value:
        return []

    return [text_value]


def format_genres(value: object) -> str:
    return ' / '.join(normalize_genres(value))


def format_decade(year: int) -> str:
    parsed_year = parse_year(year)
    if parsed_year <= 0:
        return ''

    decade_start = (parsed_year // 10) * 10
    return f"{decade_start}s"


def format_duration(duration: int) -> str:
    seconds = parse_duration_seconds(duration)
    if seconds <= 0:
        return ""

    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:d}:{seconds:02d}"


def extract_song_metadata(song: dict) -> dict[str, str]:
    artist_value = ''
    for key in ('artist', 'displayartist', 'albumartist'):
        artist_value = first_non_empty_text(song.get(key))
        if artist_value:
            break

    year_value = parse_year(song.get('year'))

    return {
        'songid': int(song.get('songid') or 0),
        'title': str(song.get('title') or '').strip(),
        'artist': artist_value,
        'album': str(song.get('album') or '').strip(),
        'genre': normalize_genres(song.get('genre')),
        'year': year_value,
        'decade': format_decade(year_value),
        'duration': parse_duration_seconds(song.get('duration')),
        'thumbnail': str(song.get('thumbnail') or '').strip(),
        'fanart': str(song.get('fanart') or '').strip(),
    }


def get_library_track_metadata(path: str) -> dict[str, str]:
    filename, directory = split_full_path(path)
    if not filename:
        return {}

    strict_candidates = query_library_songs_strict(filename, directory)
    log(f"Strict library lookup returned {len(strict_candidates)} candidate song(s) for {path}", xbmc.LOGDEBUG)

    matched_song = find_song_by_file_relaxed(strict_candidates, path)
    if matched_song is not None:
        return extract_song_metadata(matched_song)

    if len(strict_candidates) == 1:
        log("Using single strict library candidate without file-match confirmation.", xbmc.LOGDEBUG)
        return extract_song_metadata(strict_candidates[0])

    filename_candidates = query_library_songs_by_filename(filename)
    log(f"Filename-only library lookup returned {len(filename_candidates)} candidate song(s) for {path}", xbmc.LOGDEBUG)

    matched_song = find_song_by_file_relaxed(filename_candidates, path)
    if matched_song is not None:
        return extract_song_metadata(matched_song)

    if len(filename_candidates) == 1:
        log("Using single filename-only library candidate without file-match confirmation.", xbmc.LOGDEBUG)
        return extract_song_metadata(filename_candidates[0])

    if strict_candidates:
        log("No unique relaxed match found in strict library candidates.", xbmc.LOGDEBUG)
        log_library_candidates(path, strict_candidates)
    if filename_candidates:
        log("No unique relaxed match found in filename-only library candidates.", xbmc.LOGDEBUG)
        log_library_candidates(path, filename_candidates)

    return {}

def get_track_metadata(
    path: str,
    sidecar_snapshot: dict | None = None,
    allow_live_lookup: bool = True,
    include_player_metadata: bool = True,
) -> dict[str, object]:
    metadata = build_empty_track_metadata(path)

    cached_snapshot = normalize_track_metadata_snapshot(path, sidecar_snapshot)
    if track_metadata_snapshot_has_payload(path, cached_snapshot):
        metadata.update(cached_snapshot)
    else:
        cache_data = read_track_metadata_cache(path)
        if cache_data:
            metadata.update(cache_data)
        elif allow_live_lookup:
            library_data = get_library_track_metadata(path)
            if library_data:
                snapshot = normalize_track_metadata_snapshot(
                    path,
                    library_data,
                    cached_ts=int(time.time()),
                    library_freshest_ts=get_cached_audio_library_freshest_ts(allow_query=True),
                )
                write_track_metadata_cache(path, snapshot)
                metadata.update(snapshot)

    # A Discovery snippet's player tag carries "Artist - Title" as its title, so callers building
    # labels while a snippet plays can leave the player out.
    current_data = get_current_player_metadata(path) if include_player_metadata else {}
    for key, value in current_data.items():
        if value:
            metadata[key] = value

    metadata['genre'] = normalize_genres(metadata.get('genre'))
    metadata['year'] = parse_year(metadata.get('year'))
    metadata['decade'] = format_decade(metadata.get('year'))
    metadata['duration'] = parse_duration_seconds(metadata.get('duration'))
    return metadata

def get_kodi_setting_value_safe(setting_id: str):
    try:
        return execute_jsonrpc("Settings.GetSettingValue", {"setting": setting_id}).get("value")
    except Exception as exc:
        log(f"Could not read Kodi setting {setting_id!r}: {exc}", xbmc.LOGDEBUG)
        return None


def get_kodi_music_track_template() -> str:
    global KODI_MUSIC_TRACK_TEMPLATE_CACHE

    cached_value = globals().get("KODI_MUSIC_TRACK_TEMPLATE_CACHE")
    if isinstance(cached_value, str) and cached_value:
        return cached_value

    for setting_id in KODI_MUSIC_TRACK_TEMPLATE_SETTING_CANDIDATES:
        value = get_kodi_setting_value_safe(setting_id)
        if isinstance(value, str) and "%" in value:
            KODI_MUSIC_TRACK_TEMPLATE_CACHE = value
            log(f"Using Kodi music track template from {setting_id!r}: {value!r}", xbmc.LOGINFO)
            return value

    KODI_MUSIC_TRACK_TEMPLATE_CACHE = KODI_MUSIC_TRACK_TEMPLATE_FALLBACK
    log(
        f"Using fallback Kodi music track template: {KODI_MUSIC_TRACK_TEMPLATE_FALLBACK!r}",
        xbmc.LOGINFO,
    )
    return KODI_MUSIC_TRACK_TEMPLATE_CACHE

def format_template_optional_blocks(template: str, values: dict[str, str]) -> str:
    def replace_optional(match):
        content = match.group(1)

        tokens = re.findall(r"%[A-Za-z]", content)
        for token in tokens:
            if not str(values.get(token, "")).strip():
                return ""

        result = content
        for token, value in values.items():
            result = result.replace(token, str(value or ""))

        return result

    return re.sub(r"\[([^\[\]]*)\]", replace_optional, template)


def cleanup_music_label(label: str, fallback: str) -> str:
    value = re.sub(r"\s+", " ", str(label or "")).strip()
    value = re.sub(r"^\s*[-–—:|]+\s*", "", value)
    value = re.sub(r"\s*[-–—:|]+\s*$", "", value)
    value = value.strip()
    return value or fallback


UNKNOWN_ARTIST_LABEL = "(Unknown Artist)"
UNKNOWN_TITLE_LABEL = "(Unknown Title)"


def format_mix_track_label(path: str, metadata: dict, mix_position: int) -> str:
    # Placeholders keep the template's separators meaningful ("1. (Unknown Artist) - Title", not "1. - Title").
    title = str(metadata.get("title") or path_to_label(path) or "").strip() or UNKNOWN_TITLE_LABEL
    artist = str(metadata.get("artist") or "").strip() or UNKNOWN_ARTIST_LABEL
    album = str(metadata.get("album") or "").strip()

    try:
        number = str(int(mix_position)) if int(mix_position) > 0 else ""
    except Exception:
        number = ""

    fallback = title or path_to_label(path)
    template = get_kodi_music_track_template()

    values = {
        "%N": number,
        "%A": artist,
        "%T": title,
        "%B": album,
        "%L": album,
    }

    label = format_template_optional_blocks(template, values)
    for token, value in values.items():
        label = label.replace(token, str(value or ""))

    # Remove unknown template tokens only if they are isolated leftovers.
    label = re.sub(r"%[A-Za-z]", "", label)
    return cleanup_music_label(label, fallback)


def apply_music_metadata(
    list_item: xbmcgui.ListItem,
    title: str,
    artist: str = '',
    album: str = '',
    year: int = 0,
    duration: int = 0,
    genres: object = None,
    track_number: int = 0,
) -> None:
    try:
        music_tag = list_item.getMusicInfoTag()
        music_tag.setTitle(title)
        if artist:
            music_tag.setArtist(artist)
        if album:
            music_tag.setAlbum(album)

        try:
            parsed_track = int(track_number or 0)
            if parsed_track > 0:
                music_tag.setTrack(parsed_track)
        except Exception:
            pass

        genre_values = normalize_genres(genres)
        if genre_values:
            try:
                music_tag.setGenres(genre_values)
            except Exception:
                pass

        parsed_year = parse_year(year)
        if parsed_year > 0:
            try:
                music_tag.setYear(parsed_year)
            except Exception:
                pass

        duration_seconds = parse_duration_seconds(duration)
        if duration_seconds > 0:
            music_tag.setDuration(duration_seconds)
    except Exception:
        pass


def apply_music_extra_properties(
    list_item: xbmcgui.ListItem,
    decade: str = '',
    genres: object = None,
) -> None:
    decade_label = str(decade or '').strip()
    genre_label = format_genres(genres)

    try:
        if decade_label:
            list_item.setProperty('MusicIP.Decade', decade_label)
        if genre_label:
            list_item.setProperty('MusicIP.Genre', genre_label)
    except Exception:
        pass


def apply_music_path(list_item: xbmcgui.ListItem, path: str) -> None:
    list_item.setPath(path)
    try:
        music_tag = list_item.getMusicInfoTag()
        music_tag.setURL(path)
    except Exception:
        pass


def apply_music_artwork(
    list_item: xbmcgui.ListItem,
    thumbnail: str = '',
    fanart: str = '',
) -> None:
    art: dict[str, str] = {}

    if thumbnail:
        art['thumb'] = thumbnail
        art['icon'] = thumbnail

    if fanart:
        art['fanart'] = fanart

    if not art:
        return

    try:
        list_item.setArt(art)
    except Exception:
        pass


def format_track_details(
    year: int = 0,
    decade: str = '',
    genres: object = None,
    duration: int = 0,
) -> str:
    parts: list[str] = []

    decade_label = (decade or format_decade(year)).strip()
    if decade_label:
        parts.append(decade_label)

    genre_label = format_genres(genres)
    if genre_label:
        parts.append(genre_label)

    duration_label = format_duration(duration)
    if duration_label:
        parts.append(duration_label)

    return " · ".join(parts)


def apply_track_detail_display(
    list_item: xbmcgui.ListItem,
    year: int = 0,
    decade: str = '',
    genres: object = None,
    duration: int = 0,
) -> None:
    label = format_track_details(year=year, decade=decade, genres=genres, duration=duration)
    if not label:
        return

    try:
        list_item.setLabel2(label)
    except Exception:
        pass


def add_error_item(label: str) -> None:
    item = xbmcgui.ListItem(label=label, offscreen=True)
    try:
        apply_music_metadata(item, label)
    except Exception:
        pass
    xbmcplugin.addDirectoryItem(HANDLE, "", item, isFolder=False)


def run_selected_mix_keyboard_action(property_name: str, action_label: str) -> None:
    try:
        command = (xbmc.getInfoLabel(f"ListItem.Property({property_name})") or "").strip()
    except Exception:
        command = ""

    if not command:
        notify(f"No '{action_label}' action is available for the selected item.", xbmcgui.NOTIFICATION_WARNING)
        finish_plugin_action()
        return

    try:
        xbmc.executebuiltin(command)
        log(f"Keyboard shortcut executed {action_label}: {command}", xbmc.LOGINFO)
    except Exception as exc:
        log(f"Keyboard shortcut failed for {action_label}: {exc}", xbmc.LOGERROR)
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)

    finish_plugin_action()


def add_track_item(
    seed: str,
    size: int,
    index: int,
    path: str,
    cache_path: str = '',
    metadata: dict | None = None,
) -> None:
    metadata = metadata if isinstance(metadata, dict) else get_track_metadata(path)
    mix_position = int(index) + 1
    title = metadata.get('title') or path_to_label(path)
    label = format_mix_track_label(path, metadata, mix_position)
    missing = is_track_missing(path)
    display_label = problem_marker_label(label) if missing else label
    list_item = xbmcgui.ListItem(label=display_label, offscreen=True)
    list_item.setProperty("IsPlayable", "true")
    list_item.setProperty("MusicIP.OriginalTitle", str(title or ""))
    list_item.setProperty("MusicIP.DisplayTitle", str(display_label or ""))
    if missing:
        list_item.setProperty("MusicIP.Missing", "true")
    apply_music_metadata(
        list_item,
        display_label,
        artist=metadata.get('artist', ''),
        album=metadata.get('album', ''),
        year=parse_year(metadata.get('year')),
        duration=parse_duration_seconds(metadata.get('duration')),
        genres=metadata.get('genre'),
        track_number=mix_position,
    )
    apply_music_extra_properties(
        list_item,
        decade=str(metadata.get('decade') or ''),
        genres=metadata.get('genre'),
    )
    apply_track_detail_display(
        list_item,
        year=parse_year(metadata.get('year')),
        decade=str(metadata.get('decade') or ''),
        genres=metadata.get('genre'),
        duration=parse_duration_seconds(metadata.get('duration')),
    )
    if missing:
        try:
            list_item.setLabel2("[B][COLOR red]![/COLOR][/B] Missing file")
        except Exception:
            pass
    apply_music_path(list_item, path)
    apply_music_artwork(
        list_item,
        thumbnail=metadata.get('thumbnail', ''),
        fanart=metadata.get('fanart', ''),
    )

    refresh_action = build_refresh_action(seed, size, cache_path=cache_path)
    more_like_this_action = build_more_like_this_action(seed, size, index, path, cache_path=cache_path)
    remove_action = build_remove_action(seed, size, index, path, cache_path=cache_path)

    list_item.setProperty("MusicIP.MixAction.Remove", remove_action)
    list_item.setProperty("MusicIP.MixAction.MoreLikeThis", more_like_this_action)

    context_items = [
        ("Refresh mix", refresh_action),
        ("More like this", more_like_this_action),
    ]

    if index > 0:
        less_like_this_action = build_less_like_this_action(seed, size, index, path, cache_path=cache_path)
        list_item.setProperty("MusicIP.MixAction.LessLikeThis", less_like_this_action)
        context_items.append(("Less like this", less_like_this_action))
    else:
        list_item.setProperty("MusicIP.MixAction.LessLikeThis", "")

    context_items.append(("Remove from mix", remove_action))
    list_item.addContextMenuItems(context_items)

    url = addon_url(
        action="play_track",
        path=path,
    )
    xbmcplugin.addDirectoryItem(HANDLE, url, list_item, isFolder=False)

def add_saved_mix_date_item(date_key: str, cache_paths: list[str]) -> None:
    count = len(cache_paths)
    inconsistent = 0

    for cache_path in cache_paths:
        try:
            tracks = load_mix_by_cache_path(cache_path)
            meta = get_saved_mix_metadata(cache_path, tracks)
            if is_mix_inconsistent(meta):
                inconsistent += 1
        except Exception:
            pass

    label = f"{date_key} ({count} mix{'es' if count != 1 else ''})"
    warning_label = ""
    if inconsistent:
        warning_label = f"{inconsistent} warning{'s' if inconsistent != 1 else ''}"
        label = problem_marker_label(f"{label} · {warning_label}")

    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    if warning_label:
        try:
            list_item.setLabel2(warning_label)
        except Exception:
            pass
    apply_music_metadata(list_item, label)
    list_item.setProperty("IsPlayable", "false")
    list_item.addContextMenuItems([
        ("Cleanup mixes from this date", build_cleanup_date_action(date_key, include_older=False)),
        ("Cleanup mixes from this date and older", build_cleanup_date_action(date_key, include_older=True)),
    ])
    xbmcplugin.addDirectoryItem(
        HANDLE,
        build_saved_date_browse_url(date_key),
        list_item,
        isFolder=True,
    )


def add_saved_mix_item(cache_path: str) -> None:
    tracks = load_mix_by_cache_path(cache_path)
    meta = get_saved_mix_metadata(cache_path, tracks)
    label = format_saved_mix_label(meta)
    consistency_label = get_consistency_label(meta)
    inconsistent = is_mix_inconsistent(meta)

    display_label = problem_marker_label(label) if inconsistent else label
    list_item = xbmcgui.ListItem(label=display_label, offscreen=True)
    apply_music_metadata(list_item, display_label)
    apply_saved_mix_info_metadata(list_item, cache_path)
    list_item.setProperty("IsPlayable", "false")
    if inconsistent:
        list_item.setProperty("MusicIP.Inconsistent", "true")

    context_items = [
        ("Information", f"RunPlugin({addon_url(action='mix_info', cache_path=cache_path, nonce=new_nonce())})"),
        ("Show mix information", f"RunPlugin({addon_url(action='mix_info', cache_path=cache_path, nonce=new_nonce())})"),
        ("Check consistency", build_check_mix_action(cache_path)),
    ]
    repair_readiness = {}
    if inconsistent:
        repair_readiness = get_or_update_mix_repair_readiness(cache_path, tracks, meta)
        if is_repair_ready(repair_readiness):
            context_items.append(("Auto-repair this mix", build_repair_mix_action(cache_path)))
        else:
            context_items.append((
                repair_readiness_action_label(repair_readiness),
                build_update_library_before_repair_action(cache_path),
            ))
    context_items.append(("Tidy up with AI Mix Assist", build_mix_assist_action("mix_assist_tidy_up", cache_path)))
    context_items.append(("Edit what this mix is about", build_mix_assist_action("mix_assist_edit_intent", cache_path)))
    if get_mix_assist_section(meta).get("previous_tracks"):
        context_items.append(("Undo AI Mix Assist changes", build_mix_assist_action("mix_assist_undo", cache_path)))
    context_items.append(("Cleanup this mix", build_cleanup_saved_mix_action(cache_path)))
    list_item.addContextMenuItems(context_items)

    updated_ts = int(meta.get("updated_ts") or 0)
    detail_parts: list[str] = []
    if updated_ts > 0:
        detail_parts.append(time.strftime("%Y-%m-%d %H:%M", time.localtime(updated_ts)))
    if consistency_label and consistency_label != "OK":
        detail_parts.append(consistency_label)
    if inconsistent and repair_readiness and not is_repair_ready(repair_readiness):
        detail_parts.append(repair_readiness_action_label(repair_readiness))
    if detail_parts:
        list_item.setLabel2(" · ".join(detail_parts))

    xbmcplugin.addDirectoryItem(
        HANDLE,
        build_saved_browse_url(cache_path),
        list_item,
        isFolder=True,
    )


def show_root() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "MusicIP")
    xbmcplugin.setContent(HANDLE, "files")

    generate_label = "Generate mix from playing audio"
    generate_item = xbmcgui.ListItem(label=generate_label, offscreen=True)
    apply_music_metadata(generate_item, generate_label)
    xbmcplugin.addDirectoryItem(
        HANDLE,
        addon_url(action="generate_current_mix"),
        generate_item,
        isFolder=True,
    )

    discovery_item = xbmcgui.ListItem(label="Discovery mode", offscreen=True)
    apply_music_metadata(discovery_item, "Discovery mode")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        addon_url(action="discovery_mode"),
        discovery_item,
        isFolder=True,
    )

    radio_item = xbmcgui.ListItem(label="Radio mode", offscreen=True)
    apply_music_metadata(radio_item, "Radio mode")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        addon_url(action="radio_mode"),
        radio_item,
        isFolder=True,
    )

    recent_item = xbmcgui.ListItem(label="Recent mixes", offscreen=True)
    apply_music_metadata(recent_item, "Recent mixes")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        build_saved_mixes_url(),
        recent_item,
        isFolder=True,
    )

    settings_item = xbmcgui.ListItem(label="Settings", offscreen=True)
    apply_music_metadata(settings_item, "Settings")
    settings_item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        addon_url(action="open_settings", nonce=new_nonce()),
        settings_item,
        # An action, not a folder: Kodi runs it without expecting a directory listing.
        isFolder=False,
    )

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def add_discovery_run_action_item(label: str, action: str) -> None:
    item = xbmcgui.ListItem(label=label, offscreen=True)
    apply_music_metadata(item, label)
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        run_plugin_url(action=action, nonce=new_nonce()),
        item,
        isFolder=False,
    )


def add_discovery_action_item(label: str, action: str, is_folder: bool = True) -> None:
    item = xbmcgui.ListItem(label=label, offscreen=True)
    apply_music_metadata(item, label)
    if not is_folder:
        item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(
        HANDLE,
        addon_url(action=action, nonce=new_nonce()),
        item,
        isFolder=is_folder,
    )


def show_discovery_mode_menu() -> None:
    state = get_discovery_state()
    active = bool(state.get("enabled"))

    title = "MusicIP discovery mode"
    if active:
        current = str(state.get("current_label") or state.get("current_song") or "").strip()
        if current:
            title = f"Discovery mode: {current}"
        else:
            title = "Discovery mode: active"

    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.setContent(HANDLE, "files")

    if active:
        add_discovery_action_item("Create mix from current discovery song", "discovery_mix_current", is_folder=True)
        add_discovery_action_item("Skip to next discovery song", "discovery_next", is_folder=True)
        add_discovery_action_item("Stop discovery mode", "discovery_stop", is_folder=True)
    else:
        add_discovery_action_item("Start discovery mode", "discovery_start", is_folder=True)

    add_discovery_action_item("Discovery mode settings", "open_settings", is_folder=False)

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def start_discovery_mode() -> None:
    begin_discovery_playback()
    notify("Discovery mode started.")
    replace_with_discovery_mode_menu()


def begin_discovery_playback(owner: str = "") -> dict:
    """Start Discovery snippet playback. owner "radio" marks the radio's tuning phase."""
    state = get_discovery_state()
    state.update({
        "owner": owner,
        "enabled": False,
        "startup_in_progress": True,
        "started_ts": int(time.time()),
        "stopped_ts": 0,
        "excerpt_seconds": get_discovery_excerpt_seconds(),
        "offset_percent": get_discovery_offset_percent(),
        "stop_reason": "",
        "resume_allowed": True,
        "current_started_ts": 0,
        "current_song": "",
        "current_label": "",
        "current_playlist_position": -1,
        "queue": [],
        "last_error": "",
    })
    save_discovery_state(state)

    state = start_discovery_playlist_direct(state)

    log(
        f"Discovery mode: UI completed direct playlist start. state_path={discovery_state_path()}",
        xbmc.LOGINFO,
    )
    return state

def stop_discovery_mode() -> None:
    end_discovery_playback()
    notify("Discovery mode stopped.")
    replace_with_discovery_mode_menu()


def end_discovery_playback(reason: str = "manual_stop") -> None:
    state = get_discovery_state()
    state["enabled"] = False
    state["stopped_ts"] = int(time.time())
    state["stop_reason"] = reason
    state["resume_allowed"] = False
    state["startup_in_progress"] = False
    state["next_requested"] = False
    state["next_reason"] = ""
    save_discovery_state(state)
    try:
        xbmc.Player().stop()
    except Exception:
        pass

    try:
        get_music_playlist().clear()
    except Exception:
        pass

# --- Radio mode ------------------------------------------------------------------------------
# Like a vintage radio set: tune through random snippets (Discovery playback), then "Start radio"
# locks onto the current song. The station is an endless MusicIP mix with the configured mix
# parameters; the service plays it, tops it up from the last queued song and stops it on the
# player's Stop.


def radio_state_path() -> str:
    return os.path.join(get_profile_dir(), "radio_mode_state.json")


def get_radio_state() -> dict:
    return load_json_file(radio_state_path())


def save_radio_state(state: dict) -> None:
    save_json_file(radio_state_path(), state or {})


def radio_mode_url() -> str:
    return addon_url(action="radio_mode", nonce=new_nonce())


def replace_with_radio_mode_menu() -> None:
    try:
        xbmc.executebuiltin(f"Container.Update({radio_mode_url()},replace)")
    except Exception as exc:
        log(f"Radio mode: could not show the Radio screen: {exc}", xbmc.LOGWARNING)


def radio_phase() -> str:
    phase = str(get_radio_state().get("phase") or "off")
    return phase if phase in ("seeking", "playing") else "off"


def add_radio_action_item(label: str, action: str) -> None:
    # Actions, not folders: Kodi runs them without expecting a directory listing.
    item = xbmcgui.ListItem(label=label, offscreen=True)
    apply_music_metadata(item, label)
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(HANDLE, addon_url(action=action, nonce=new_nonce()), item, isFolder=False)


def show_radio_mode_menu() -> None:
    state = get_radio_state()
    phase = radio_phase()

    if phase == "seeking":
        current = str(get_discovery_state().get("current_label") or "").strip()
        title = f"Radio: tuning - {current}" if current else "Radio: tuning"
    elif phase == "playing":
        current = str(state.get("current_label") or "").strip()
        title = f"Radio: {current}" if current else "Radio: playing"
    else:
        title = "MusicIP radio"

    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.setContent(HANDLE, "files")

    if phase == "seeking":
        add_radio_action_item("Start radio", "radio_play")
        add_radio_action_item("Next station", "radio_tune")
        add_radio_action_item("Stop radio", "radio_stop")
    elif phase == "playing":
        add_radio_action_item("Change station", "radio_retune")
        add_radio_action_item("Stop radio", "radio_stop")
    else:
        add_radio_action_item("Turn on radio", "radio_on")

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def begin_radio_tuning() -> bool:
    """Tune through random snippets, as in Discovery mode. False if no snippets could be played."""
    now = int(time.time())
    started_ts = int(get_radio_state().get("started_ts") or 0) if radio_phase() != "off" else 0
    save_radio_state({"phase": "seeking", "started_ts": started_ts or now, "tuning_started_ts": now, "stop_reason": ""})
    discovery = begin_discovery_playback(owner="radio")
    if not discovery.get("enabled"):
        save_radio_state({"phase": "off", "stopped_ts": int(time.time()), "stop_reason": "tuning_failed"})
        return False
    return True


def turn_radio_on() -> None:
    if begin_radio_tuning():
        notify("Radio on. Tuning in.")
    replace_with_radio_mode_menu()


def change_radio_station() -> None:
    """Leave the playing station and tune again."""
    if radio_phase() != "playing":
        replace_with_radio_mode_menu()
        return
    if begin_radio_tuning():
        notify("Changing station. Tuning in.")
    replace_with_radio_mode_menu()


def tune_radio() -> None:
    if radio_phase() != "seeking":
        replace_with_radio_mode_menu()
        return
    if skip_discovery_song() is None:
        notify("No next station buffered yet.", xbmcgui.NOTIFICATION_WARNING)
    replace_with_radio_mode_menu()


def start_radio() -> None:
    """Lock onto the current snippet: an endless MusicIP mix with the configured mix parameters, no dialog."""
    if radio_phase() != "seeking":
        replace_with_radio_mode_menu()
        return

    seed = str(get_discovery_state().get("current_song") or "").strip()
    if not seed:
        try:
            seed = get_current_seed_song()
        except Exception:
            seed = ""
    if not seed:
        notify("No song is playing to start the radio from.", xbmcgui.NOTIFICATION_WARNING)
        replace_with_radio_mode_menu()
        return

    # Keep the current snippet playing while MusicIP builds the station.
    set_discovery_mix_dialog_hold(seed)
    if not start_radio_station(seed):
        clear_discovery_mix_dialog_hold()
    replace_with_radio_mode_menu()


def start_radio_from_song(seed: str) -> None:
    """Start a station from any song (library context menu), without tuning. Replaces Discovery or radio playback."""
    seed = str(seed or "").strip()
    if not seed:
        notify("No song was supplied to start the radio from.", xbmcgui.NOTIFICATION_ERROR)
        return
    start_radio_station(seed)


def start_radio_station(seed: str) -> bool:
    """Play an endless MusicIP mix seeded with seed, using the configured mix parameters. False on failure."""
    try:
        tracks = fetch_mix(seed, get_playlist_size(), get_effective_mix_parameters())
    except Exception as exc:
        notify(f"Radio could not start: {exc}", xbmcgui.NOTIFICATION_ERROR)
        log(f"Radio mode: start failed for seed {seed!r}: {exc}", xbmc.LOGERROR)
        return False

    discovery = get_discovery_state()
    if discovery.get("enabled") or discovery.get("mix_dialog_active"):
        # The station replaces Discovery's snippets (the radio's tuning or a separate Discovery session).
        discovery.update({
            "enabled": False,
            "stopped_ts": int(time.time()),
            "stop_reason": "radio_started",
            "resume_allowed": False,
            "startup_in_progress": False,
            "mix_dialog_active": False,
            "mix_dialog_seed": "",
            "mix_dialog_started_ts": 0,
            "mix_dialog_excerpt_seconds": 0,
        })
        save_discovery_state(discovery)

    metadata_list = collect_mix_track_metadata(tracks, allow_live_lookup=False, include_player_metadata=False)
    now = int(time.time())
    previous = get_radio_state()
    started_ts = int(previous.get("started_ts") or 0) if radio_phase() != "off" else 0
    queue = [
        {"file": track, "label": format_mix_track_label(track, metadata, 0)}
        for track, metadata in zip(tracks, metadata_list)
    ]
    save_radio_state({
        "phase": "playing",
        "started_ts": started_ts or now,
        "playing_started_ts": now,
        "seed": seed,
        "seeds": [seed],
        "queue": queue,
        "seen": [normalize_track_identity(track) for track in tracks],
        "current_position": 0,
        "current_song": tracks[0],
        "current_label": queue[0]["label"],
        "stop_reason": "",
        "ui_refresh_requested": True,
    })

    try:
        play_tracks_as_music_playlist(tracks, metadata_list, numbered=False)
        enqueue_metadata_refresh_for_tracks(tracks, metadata_list=metadata_list, reason_context="radio")
    except Exception as exc:
        save_radio_state({"phase": "off", "stopped_ts": int(time.time()), "stop_reason": "playback_failed"})
        notify(f"Radio could not start: {exc}", xbmcgui.NOTIFICATION_ERROR)
        log(f"Radio mode: playback failed: {exc}", xbmc.LOGERROR)
        return False

    log(f"Radio mode: started from {seed!r} with {len(tracks)} song(s).", xbmc.LOGINFO)
    notify("Radio started.")
    return True


def stop_radio() -> None:
    phase = radio_phase()
    if phase == "seeking":
        end_discovery_playback(reason="radio_stopped")
    elif phase == "playing":
        try:
            xbmc.Player().stop()
        except Exception:
            pass
        try:
            get_music_playlist().clear()
        except Exception:
            pass

    state = get_radio_state()
    state.update({"phase": "off", "stopped_ts": int(time.time()), "stop_reason": "manual_stop"})
    save_radio_state(state)
    if phase != "off":
        notify("Radio stopped.")
    replace_with_radio_mode_menu()


def get_current_music_playlist_position(default: int = -1) -> int:
    try:
        result = execute_jsonrpc("Player.GetProperties", {"playerid": 0, "properties": ["position"]})
        return int(result.get("position"))
    except Exception:
        return default


def set_discovery_mix_dialog_hold(seed: str) -> dict:
    state = get_discovery_state()
    now = int(time.time())
    excerpt_seconds = int(state.get("excerpt_seconds") or get_discovery_excerpt_seconds())
    state.update({
        "mix_dialog_active": True,
        "mix_dialog_seed": seed,
        "mix_dialog_started_ts": now,
        "mix_dialog_excerpt_seconds": excerpt_seconds,
        "next_requested": False,
        "next_reason": "",
        "pending_player_stop": False,
        "pending_player_stop_reason": "",
    })
    save_discovery_state(state)
    log(
        f"Discovery mode: mix dialog hold started for seed={seed!r}, "
        f"excerpt_seconds={excerpt_seconds}.",
        xbmc.LOGINFO,
    )
    return state


def clear_discovery_mix_dialog_hold(skip_if_elapsed: bool = False) -> None:
    state = get_discovery_state()
    now = int(time.time())

    try:
        started_ts = int(state.get("mix_dialog_started_ts") or 0)
    except Exception:
        started_ts = 0

    try:
        excerpt_seconds = int(
            state.get("mix_dialog_excerpt_seconds")
            or state.get("excerpt_seconds")
            or get_discovery_excerpt_seconds()
        )
    except Exception:
        excerpt_seconds = get_discovery_excerpt_seconds()

    elapsed = max(0, now - started_ts) if started_ts > 0 else 0

    state["mix_dialog_active"] = False
    state["mix_dialog_seed"] = ""
    state["mix_dialog_started_ts"] = 0
    state["mix_dialog_excerpt_seconds"] = 0
    state["next_requested"] = False
    state["next_reason"] = ""
    state["pending_player_stop"] = False
    state["pending_player_stop_reason"] = ""

    if not state.get("enabled"):
        save_discovery_state(state)
        return

    if skip_if_elapsed and elapsed >= excerpt_seconds:
        position = get_current_music_playlist_position(state.get("current_playlist_position", -1))
        if position < 0:
            try:
                position = int(state.get("current_playlist_position") or 0)
            except Exception:
                position = 0

        target_pos = position + 1
        queue = state.get("queue")
        if isinstance(queue, list) and target_pos < len(queue):
            try:
                execute_jsonrpc("Player.GoTo", {"playerid": 0, "to": target_pos})
                log(
                    f"Discovery mode: mix dialog was open {elapsed}s >= {excerpt_seconds}s; "
                    f"skipping directly to playlist position {target_pos}.",
                    xbmc.LOGINFO,
                )
                update_discovery_state_for_playlist_position(state, target_pos)
                return
            except Exception as exc:
                log(f"Discovery mode: mix dialog cancel skip failed: {exc}", xbmc.LOGWARNING)

    # Dialog was shorter than the excerpt length, or direct skip failed:
    # keep current_started_ts unchanged so the Discovery timer continues as if
    # the dialog had never been opened.
    save_discovery_state(state)
    log(
        f"Discovery mode: mix dialog hold cleared after {elapsed}s; "
        f"continuing existing excerpt timer.",
        xbmc.LOGINFO,
    )



def update_discovery_state_for_playlist_position(state: dict, position: int) -> dict:
    queue = state.get("queue")
    if not isinstance(queue, list):
        return state

    try:
        position = int(position)
    except Exception:
        return state

    if position < 0 or position >= len(queue):
        return state

    entry = queue[position]
    file_path = str(entry.get("file") or "")
    if not file_path:
        return state

    now = int(time.time())
    state.update({
        "enabled": True,
        "startup_in_progress": False,
        "current_playlist_position": position,
        "current_song": file_path,
        "current_label": str(entry.get("label") or path_to_label(file_path)),
        "current_started_ts": now,
        "current_offset_seconds": int(entry.get("offset") or 0),
        "current_duration_seconds": int(entry.get("duration") or 0),
        "current_startoffset_requested": bool(int(entry.get("offset") or 0) > 0),
        "current_seek_confirmed": False,
        "next_requested": False,
        "next_reason": "",
        "pending_player_stop": False,
        "pending_player_stop_reason": "",
        "playlist_change_pending": False,
        "mix_dialog_active": False,
        "mix_dialog_seed": "",
        "mix_dialog_started_ts": 0,
        "mix_dialog_excerpt_seconds": 0,
        "last_ui_next_ts": now,
        "last_error": "",
    })
    save_discovery_state(state)
    log(
        f"Discovery mode: UI updated state for playlist position {position}, "
        f"label={state.get('current_label')!r}.",
        xbmc.LOGINFO,
    )
    return state


def discovery_next_track() -> None:
    if skip_discovery_song() is None:
        notify("No buffered next discovery song available yet.", xbmcgui.NOTIFICATION_WARNING)
        replace_with_discovery_mode_menu()
        return
    notify("Discovery mode: skipping to next song.")
    replace_with_discovery_mode_menu()


def skip_discovery_song() -> bool | None:
    """Jump to the next buffered snippet. None if no next snippet is buffered yet."""
    try:
        state = get_discovery_state()
        raw_pos = state.get("current_playlist_position")
        pos = int(raw_pos) if raw_pos is not None else 0
        target_pos = pos + 1

        queue = state.get("queue")
        if isinstance(queue, list) and target_pos >= len(queue):
            return None

        execute_jsonrpc("Player.GoTo", {"playerid": 0, "to": target_pos})
        log(f"Discovery mode: UI requested direct Player.GoTo({target_pos}).", xbmc.LOGINFO)
        update_discovery_state_for_playlist_position(state, target_pos)
        return True
    except Exception as exc:
        log(f"Discovery mode: UI direct next failed: {exc}", xbmc.LOGWARNING)
        return False

def discovery_mix_from_current() -> None:
    state = get_discovery_state()
    seed = str(state.get("current_song") or "").strip()

    if not seed:
        try:
            seed = get_current_seed_song()
        except Exception:
            seed = ""

    if not seed:
        notify("No discovery song is currently available.", xbmcgui.NOTIFICATION_WARNING)
        replace_with_discovery_mode_menu()
        return

    # Capture the seed immediately, then put the Discovery service into a
    # temporary hold. Playback continues, but excerpt-based auto-skip is paused.
    set_discovery_mix_dialog_hold(seed)
    size = get_playlist_size()

    try:
        tracks = fetch_mix_confirmed(seed, size)
    except MusicIPError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
        log(str(exc), xbmc.LOGERROR)
        clear_discovery_mix_dialog_hold(skip_if_elapsed=True)
        replace_with_discovery_mode_menu()
        return
    except Exception as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(f"Discovery mix generation failed: {exc}", xbmc.LOGERROR)
        clear_discovery_mix_dialog_hold(skip_if_elapsed=True)
        replace_with_discovery_mode_menu()
        return

    stop_state = get_discovery_state()
    stop_state["enabled"] = False
    stop_state["stopped_ts"] = int(time.time())
    stop_state["stop_reason"] = "mix_from_discovery_song"
    stop_state["resume_allowed"] = False
    stop_state["startup_in_progress"] = False
    stop_state["mix_dialog_active"] = False
    stop_state["mix_dialog_seed"] = ""
    stop_state["mix_dialog_started_ts"] = 0
    stop_state["mix_dialog_excerpt_seconds"] = 0
    save_discovery_state(stop_state)

    try:
        xbmc.Player().stop()
    except Exception:
        pass

    try:
        get_music_playlist().clear()
    except Exception:
        pass

    track_metadata_list = collect_mix_track_metadata(tracks, allow_live_lookup=False)

    try:
        save_mix(seed, size, tracks, track_metadata_list=track_metadata_list)
        enqueue_metadata_refresh_for_tracks(
            tracks,
            cache_path=mix_cache_path(seed, size),
            metadata_list=track_metadata_list,
            reason_context="discovery_mix_from_current",
        )
        play_tracks_as_music_playlist(tracks, track_metadata_list)
    except Exception as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        log(f"Discovery mix playback failed: {exc}", xbmc.LOGERROR)
        replace_with_discovery_mode_menu()
        return

    notify("Discovery mode stopped. Playing generated mix.")
    try:
        xbmc.executebuiltin(f"Container.Update({build_browse_url(seed, size)},replace)")
    except Exception as exc:
        log(f"Discovery mode: could not replace container with generated mix: {exc}", xbmc.LOGWARNING)
        replace_with_discovery_mode_menu()

def show_saved_mixes() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "MusicIP recent mixes")
    xbmcplugin.setContent(HANDLE, "files")

    cache_paths = list_saved_mix_cache_paths()
    if not cache_paths:
        info_label = "No recent mixes found yet."
        info_item = xbmcgui.ListItem(label=info_label, offscreen=True)
        apply_music_metadata(info_item, info_label)
        xbmcplugin.addDirectoryItem(HANDLE, "", info_item, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return

    grouped = group_saved_mixes_by_date(cache_paths)
    for date_key, group_paths in grouped:
        add_saved_mix_date_item(date_key, group_paths)

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def show_saved_mixes_by_date(date_key: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, f"MusicIP recent mixes: {date_key}")
    xbmcplugin.setContent(HANDLE, "files")

    cache_paths = list_saved_mix_cache_paths()
    grouped = dict(group_saved_mixes_by_date(cache_paths))
    selected = grouped.get(date_key, [])

    if not selected:
        info_label = "No recent mixes found for this date."
        info_item = xbmcgui.ListItem(label=info_label, offscreen=True)
        apply_music_metadata(info_item, info_label)
        xbmcplugin.addDirectoryItem(HANDLE, "", info_item, isFolder=False)
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return

    for cache_path in selected:
        try:
            add_saved_mix_item(cache_path)
        except Exception as exc:
            log(f"Skipping invalid stored mix {cache_path}: {exc}", xbmc.LOGDEBUG)

    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)

def generate_current_mix() -> None:
    seed = get_current_seed_song()
    if not seed:
        notify("No playing song found.", xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
        return

    size = get_playlist_size()

    try:
        tracks = fetch_mix_confirmed(seed, size)
    except MusicIPError as exc:
        message = str(exc)
        notify(message, xbmcgui.NOTIFICATION_WARNING if "cancelled" in message.lower() else xbmcgui.NOTIFICATION_ERROR)
        log(message, xbmc.LOGERROR)
        add_error_item(f"MusicIP mix failed: {message}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
        return
    except Exception as exc:
        message = str(exc)
        notify(message, xbmcgui.NOTIFICATION_ERROR)
        log(f"Generate mix from playing audio failed: {message}", xbmc.LOGERROR)
        add_error_item(f"MusicIP mix failed: {message}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
        return

    track_metadata_list = collect_mix_track_metadata(tracks, allow_live_lookup=False)

    try:
        save_mix(seed, size, tracks, track_metadata_list=track_metadata_list)
        enqueue_metadata_refresh_for_tracks(
            tracks,
            cache_path=mix_cache_path(seed, size),
            metadata_list=track_metadata_list,
            reason_context="generate_current_mix",
        )
        play_tracks_as_music_playlist(tracks, track_metadata_list)
    except Exception as exc:
        message = str(exc)
        notify(message, xbmcgui.NOTIFICATION_ERROR)
        log(f"Generate mix playback failed: {message}", xbmc.LOGERROR)
        add_error_item(f"MusicIP mix playback failed: {message}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
        return

    notify("Playing generated mix.")
    try:
        xbmc.executebuiltin(f"Container.Update({build_browse_url(seed, size)},replace)")
    except Exception as exc:
        log(f"Generate mix: could not replace container with generated mix: {exc}", xbmc.LOGWARNING)
        browse_mix(seed, size, force_refresh=False, update_listing=False)

def browse_mix(
    seed: str,
    size: int,
    force_refresh: bool = False,
    update_listing: bool = False,
    focus_index: int = -1,
    focus_token: str = "",
) -> None:
    xbmcplugin.setPluginCategory(HANDLE, f"MusicIP mix: {path_to_label(seed)}")
    xbmcplugin.setContent(HANDLE, "songs")
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)

    try:
        if force_refresh:
            tracks = fetch_mix_confirmed(seed, size)
            save_mix(seed, size, tracks)
        else:
            try:
                tracks = load_mix(seed, size)
                log("Loaded stored mix from cache.")
            except MusicIPError:
                tracks = fetch_mix_confirmed(seed, size)
                save_mix(seed, size, tracks)
    except MusicIPError as exc:
        message = str(exc)
        notify(message, xbmcgui.NOTIFICATION_WARNING if "cancelled" in message.lower() else xbmcgui.NOTIFICATION_ERROR)
        log(message, xbmc.LOGERROR)
        add_error_item(f"MusicIP mix failed: {message}")
        xbmcplugin.endOfDirectory(HANDLE, succeeded=True, updateListing=update_listing, cacheToDisc=False)
        return

    if not tracks:
        info_label = "Mix is empty. Use Refresh mix to generate a new one."
        info_item = xbmcgui.ListItem(label=info_label, offscreen=True)
        apply_music_metadata(info_item, info_label)
        xbmcplugin.addDirectoryItem(HANDLE, "", info_item, isFolder=False)
    else:
        cache_path = mix_cache_path(seed, size)
        meta = get_saved_mix_metadata(cache_path, tracks)
        sidecar_map = build_sidecar_track_metadata_map(meta)
        track_metadata_list = collect_mix_track_metadata(
            tracks,
            sidecar_map=sidecar_map,
            allow_live_lookup=False,
        )
        set_mix_track_metadata_snapshot(cache_path, tracks, track_metadata_list)
        enqueue_metadata_refresh_for_tracks(
            tracks,
            cache_path=cache_path,
            metadata_list=track_metadata_list,
            reason_context="browse_mix",
        )

        for index, path in enumerate(tracks):
            add_track_item(
                seed,
                size,
                index,
                path,
                cache_path=cache_path,
                metadata=track_metadata_list[index] if index < len(track_metadata_list) else None,
            )

    xbmcplugin.endOfDirectory(HANDLE, updateListing=update_listing, cacheToDisc=False)
    apply_pending_focus(focus_index, focus_token)

def browse_saved_mix(
    cache_path: str,
    force_refresh: bool = False,
    update_listing: bool = False,
    focus_index: int = -1,
    focus_token: str = "",
) -> None:
    try:
        tracks = load_mix_by_cache_path(cache_path)
        meta = get_saved_mix_metadata(cache_path, tracks)
        seed = (meta.get("seed") or (tracks[0] if tracks else "")).strip()
        size = int(meta.get("size") or len(tracks) or get_playlist_size())
    except MusicIPError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
        log(str(exc), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False, updateListing=update_listing, cacheToDisc=False)
        return

    xbmcplugin.setPluginCategory(HANDLE, f"Saved MusicIP mix: {path_to_label(seed)}")
    xbmcplugin.setContent(HANDLE, "songs")
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)

    if force_refresh:
        if not seed:
            notify("Stored mix does not contain a valid seed song.", xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, updateListing=update_listing, cacheToDisc=False)
            return
        try:
            tracks = fetch_mix_confirmed(seed, size)
            save_mix(seed, size, tracks)
            cache_path = mix_cache_path(seed, size)
            meta = get_saved_mix_metadata(cache_path, tracks)
        except MusicIPError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, updateListing=update_listing, cacheToDisc=False)
            return

    if not tracks:
        info_label = "Mix is empty. Use Refresh mix to generate a new one."
        info_item = xbmcgui.ListItem(label=info_label, offscreen=True)
        apply_music_metadata(info_item, info_label)
        xbmcplugin.addDirectoryItem(HANDLE, "", info_item, isFolder=False)
    else:
        sidecar_map = build_sidecar_track_metadata_map(meta)
        track_metadata_list = collect_mix_track_metadata(
            tracks,
            sidecar_map=sidecar_map,
            allow_live_lookup=False,
        )
        set_mix_track_metadata_snapshot(cache_path, tracks, track_metadata_list)
        enqueue_metadata_refresh_for_tracks(
            tracks,
            cache_path=cache_path,
            metadata_list=track_metadata_list,
            reason_context="browse_saved_mix",
        )

        for index, path in enumerate(tracks):
            add_track_item(
                seed,
                size,
                index,
                path,
                cache_path=cache_path,
                metadata=track_metadata_list[index] if index < len(track_metadata_list) else None,
            )

    xbmcplugin.endOfDirectory(HANDLE, updateListing=update_listing, cacheToDisc=False)
    apply_pending_focus(focus_index, focus_token)

def format_sidecar_ts(value: object) -> str:
    try:
        ts = int(value or 0)
    except Exception:
        ts = 0

    if ts <= 0:
        return "unknown"

    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)


def build_mix_info_message(cache_path: str) -> str:
    tracks = load_mix_by_cache_path(cache_path)
    meta = get_saved_mix_metadata(cache_path, tracks)

    params = meta.get("mix_generation_parameters")
    if not isinstance(params, dict):
        params = {}

    consistency = meta.get("consistency")
    if not isinstance(consistency, dict):
        consistency = {}

    readiness = meta.get("repair_readiness")
    if not isinstance(readiness, dict):
        readiness = {}

    lines = [
        f"Label: {meta.get('label') or path_to_label(meta.get('seed') or cache_path)}",
        f"Seed: {meta.get('seed') or 'unknown'}",
        f"Tracks: {meta.get('track_count') or len(tracks)}",
        f"Saved: {format_sidecar_ts(meta.get('updated_ts'))}",
        f"Modified: {format_sidecar_ts(meta.get('modified_ts'))}",
        "",
        "Mix generation parameters:",
    ]

    if params:
        reject_size = int(params.get("rejectsize") or 0)
        reject_text = (
            f"do not repeat artist within {reject_size} tracks"
            if reject_size > 0
            else "disabled"
        )
        lines.extend([
            f"Size: {params.get('size', 'unknown')} {params.get('sizetype', 'tracks')}",
            f"Style: {params.get('style_ui', 'unknown')}/10 - {params.get('style_label', '')} (API {params.get('style', 'unknown')})",
            f"Variety: {params.get('variety', 'unknown')}",
            f"Filter: {params.get('filter') or '<none>'}",
            f"Artist repeat: {reject_text}",
            f"Recorded: {format_sidecar_ts(meta.get('mix_generation_parameters_ts'))}",
        ])
    else:
        lines.append("No generation parameters recorded for this mix.")

    lines.extend([
        "",
        "Consistency:",
        f"Status: {consistency.get('status') or 'unknown'}",
        f"Missing files: {consistency.get('missing_files', 0)}",
        f"Checked: {format_sidecar_ts(consistency.get('checked_ts'))}",
    ])

    if readiness:
        lines.extend([
            "",
            "Repair readiness:",
            f"Status: {readiness.get('status') or 'unknown'}",
            f"Reason: {readiness.get('reason') or ''}",
            f"Missing files still listed by Kodi: {len(readiness.get('still_listed') or [])}",
            f"Checked: {format_sidecar_ts(readiness.get('checked_ts'))}",
        ])

    lines.extend(build_mix_assist_info_lines(meta))
    return "\n".join(lines)


def show_mix_info(cache_path: str) -> None:
    try:
        message = build_mix_info_message(cache_path)
    except Exception as exc:
        xbmcgui.Dialog().ok("MusicIP mix information", f"Could not read mix information.\n\n{exc}")
        return

    try:
        xbmcgui.Dialog().textviewer("MusicIP mix information", message)
    except Exception:
        xbmcgui.Dialog().ok("MusicIP mix information", message)


def selected_mix_cache_path() -> str:
    labels = [
        "ListItem.Property(MusicIP.CachePath)",
        "Container.ListItem.Property(MusicIP.CachePath)",
        "ListItem.Property(cache_path)",
        "Container.ListItem.Property(cache_path)",
    ]
    for label in labels:
        try:
            value = xbmc.getInfoLabel(label)
        except Exception:
            value = ""
        if value:
            return value.strip()
    return ""


def show_selected_mix_info() -> None:
    cache_path = selected_mix_cache_path()
    if not cache_path:
        notify("No saved mix is selected.", xbmcgui.NOTIFICATION_WARNING)
        return
    show_mix_info(cache_path)


def apply_saved_mix_info_metadata(list_item: xbmcgui.ListItem, cache_path: str) -> None:
    try:
        list_item.setProperty("MusicIP.CachePath", cache_path)
        list_item.setProperty("cache_path", cache_path)
        list_item.setProperty("InfoAction", addon_url(action="mix_info", cache_path=cache_path, nonce=new_nonce()))
        list_item.setProperty("MusicIP.InfoAction", addon_url(action="mix_info", cache_path=cache_path, nonce=new_nonce()))
    except Exception:
        pass

    try:
        message = build_mix_info_message(cache_path)
        list_item.setProperty("Plot", message)
        list_item.setProperty("plot", message)
        list_item.setProperty("Description", message)
    except Exception:
        message = ""

    try:
        tag = list_item.getMusicInfoTag()
        if hasattr(tag, "setComment") and message:
            tag.setComment(message)
    except Exception:
        pass


def build_mix_playlist_item(track: str, metadata: dict, mix_position: int) -> xbmcgui.ListItem:
    """A music playlist entry with the mix label and metadata. mix_position 0 leaves out the number."""
    title = metadata.get("title") or path_to_label(track)
    label = format_mix_track_label(track, metadata, mix_position)
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setProperty("MusicIP.OriginalTitle", str(title or ""))
    list_item.setProperty("MusicIP.DisplayTitle", str(label or ""))
    try:
        apply_music_metadata(
            list_item,
            label,
            artist=metadata.get("artist", ""),
            album=metadata.get("album", ""),
            year=parse_year(metadata.get("year")),
            duration=parse_duration_seconds(metadata.get("duration")),
            genres=metadata.get("genre"),
            track_number=mix_position,
        )
    except Exception:
        apply_music_metadata(list_item, label, track_number=mix_position)
    return list_item


def play_tracks_as_music_playlist(
    tracks: list[str],
    track_metadata_list: list[dict] | None = None,
    numbered: bool = True,
) -> list[xbmcgui.ListItem]:
    playable_tracks = [track for track in tracks if str(track or "").strip()]
    if not playable_tracks:
        raise MusicIPError("The generated mix contains no playable tracks.")

    if not isinstance(track_metadata_list, list) or len(track_metadata_list) != len(playable_tracks):
        track_metadata_list = collect_mix_track_metadata(playable_tracks, allow_live_lookup=False)
        enqueue_metadata_refresh_for_tracks(
            playable_tracks,
            metadata_list=track_metadata_list,
            reason_context="play_tracks_as_music_playlist",
        )

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()

    items: list[xbmcgui.ListItem] = []
    for index, track in enumerate(playable_tracks):
        metadata = track_metadata_list[index] if index < len(track_metadata_list) else get_track_metadata(track)
        list_item = build_mix_playlist_item(track, metadata, index + 1 if numbered else 0)
        playlist.add(track, list_item)
        items.append(list_item)

    xbmc.Player().play(playlist)
    return items

def play_track(path: str) -> None:
    metadata = get_track_metadata(path)
    label = metadata['title'] or path_to_label(path)
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    apply_music_metadata(
        list_item,
        label,
        artist=metadata.get('artist', ''),
        album=metadata.get('album', ''),
        year=parse_year(metadata.get('year')),
        duration=parse_duration_seconds(metadata.get('duration')),
        genres=metadata.get('genre'),
    )
    apply_music_extra_properties(
        list_item,
        decade=str(metadata.get('decade') or ''),
        genres=metadata.get('genre'),
    )
    apply_track_detail_display(
        list_item,
        year=parse_year(metadata.get('year')),
        decade=str(metadata.get('decade') or ''),
        genres=metadata.get('genre'),
        duration=parse_duration_seconds(metadata.get('duration')),
    )
    apply_music_path(list_item, path)
    apply_music_artwork(
        list_item,
        thumbnail=metadata.get('thumbnail', ''),
        fanart=metadata.get('fanart', ''),
    )
    xbmcplugin.setResolvedUrl(HANDLE, True, list_item)


def open_settings() -> None:
    ADDON.openSettings()
    try:
        # Show changed settings in the list the user opened them from.
        xbmc.executebuiltin("Container.Refresh")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# AI Mix Assist (docs/concept_ai_mix_assist.md): tidying up saved mixes on demand.
# ---------------------------------------------------------------------------

# "Strictness" setting: lenient … very strict, as multiples of a mix's median misfit (1.2 = calibrated default).
MIX_ASSIST_STRICTNESS = (1.5, 1.35, 1.2, 1.1, 1.0)
MIX_ASSIST_SECTION = "mix_assist"
MIX_ASSIST_MESSAGES = {
    mix_assist_claude.NOT_FOUND: "AI Mix Assist needs the Claude Code CLI. Install it, or set its path in the settings.",
    mix_assist_claude.NOT_LOGGED_IN: "AI Mix Assist: Claude Code is not logged in. Run \"claude\" once and log in.",
    mix_assist_claude.USAGE_LIMIT: "AI Mix Assist: Claude's usage limit is reached. Please try again later.",
    mix_assist_claude.TIMEOUT: "AI Mix Assist: Claude did not answer in time.",
    mix_assist_claude.FAILED: "AI Mix Assist: Claude could not judge this mix.",
}


def get_mix_assist_strictness() -> float:
    index = max(0, min(len(MIX_ASSIST_STRICTNESS) - 1, get_setting_int("mix_assist_strictness", 2)))
    return MIX_ASSIST_STRICTNESS[index]


def mix_assist_cache_path() -> str:
    return os.path.join(get_profile_dir(), "mixassist", "ratings.db")


def mix_assist_ask():
    cli = mix_assist_claude.find_cli(get_setting("mix_assist_cli_path", "").strip())
    if not cli:
        raise mix_assist_claude.ClaudeError(mix_assist_claude.NOT_FOUND, "The Claude CLI was not found.")
    return partial(mix_assist_claude.ask, cli)


def get_mix_assist_section(meta: dict) -> dict:
    section = meta.get(MIX_ASSIST_SECTION)
    return dict(section) if isinstance(section, dict) else {}


def mix_assist_track_metadata(meta: dict) -> dict[str, dict]:
    """Recorded track metadata, keyed the way mixassist.library looks it up."""
    raw = meta.get("track_metadata_by_path")
    if not isinstance(raw, dict):
        return {}
    return {str(key).replace("\\", "/").lower(): value for key, value in raw.items() if isinstance(value, dict)}


def run_mix_assist_on_saved_mix(cache_path: str) -> dict:
    """Tidy up a saved mix: replace the tracks that don't fit what it is about. Returns the applied plan."""
    tracks = load_mix_by_cache_path(cache_path)
    if len(tracks) < 2:
        raise MusicIPError("This mix is too short to tidy up.")
    meta = get_saved_mix_metadata(cache_path, tracks)
    section = get_mix_assist_section(meta)
    recorded = mix_assist_track_metadata(meta)
    ask = mix_assist_ask()
    store = mix_assist_cache.RatingCache(mix_assist_cache_path())
    progress = xbmcgui.DialogProgressBG()
    progress.create("AI Mix Assist", "Starting")
    steps = ["Looking up the tracks", "Rating new music", "Working out what this mix is about",
             "Finding replacements", "Checking the replacements"]

    def show(text: str) -> None:
        percent = int(100 * (steps.index(text) + 1) / (len(steps) + 1)) if text in steps else 0
        progress.update(percent, "AI Mix Assist", text)

    try:
        plan = mix_assist.tidy_up(
            tracks, store, ask,
            resolve=lambda paths: mix_assist_library.resolve(paths, execute_jsonrpc, recorded),
            fetch_mix=lambda seed, size: fetch_mix(seed, size),
            intent=str(section.get("listener_intent") or ""),
            strictness=get_mix_assist_strictness(),
            artist_window=get_mix_reject_size() or mix_assist.ARTIST_WINDOW,
            model=mix_assist_claude.DEFAULT_MODEL,
            progress=show,
        )
    finally:
        progress.close()
        store.close()

    changed = bool(plan["changes"] or plan["removed"])
    if changed:
        save_mix_by_cache_path(cache_path, plan["paths"])
    meta = get_saved_mix_metadata(cache_path, plan["paths"])
    section = get_mix_assist_section(meta)
    labels = {row["position"]: row["unit"]["label"] for row in plan["rows"]}
    section.update({
        "checked_ts": int(time.time()),
        "intent": plan["intent"],
        "intent_source": plan["intent_source"],
        "replaced": [
            {"old": change["old"], "old_label": change["old_label"], "new": change["new"],
             "new_label": change["new_label"], "reason": change["reason"]}
            for change in plan["changes"]
        ],
        "removed": [labels.get(position, "") for position in plan["removed"]],
        "rebuild_suggested": bool(plan["rebuild_suggested"]),
    })
    if changed:
        section["previous_tracks"] = list(tracks)
    meta[MIX_ASSIST_SECTION] = section
    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)
    return plan


def mix_assist_result_message(plan: dict) -> str:
    replaced, removed = len(plan["changes"]), len(plan["removed"])
    if not replaced and not removed:
        return "AI Mix Assist: every track fits."
    parts = []
    if replaced:
        parts.append(f"{replaced} track{'s' if replaced != 1 else ''} didn't fit and {'were' if replaced != 1 else 'was'} replaced")
    if removed:
        parts.append(f"{removed} without a fitting replacement {'were' if removed != 1 else 'was'} removed")
    return "AI Mix Assist: " + ", ".join(parts) + "."


def undo_mix_assist_on_saved_mix(cache_path: str) -> int:
    meta = get_saved_mix_metadata(cache_path, load_mix_by_cache_path(cache_path))
    section = get_mix_assist_section(meta)
    previous = section.get("previous_tracks")
    if not isinstance(previous, list) or not previous:
        raise MusicIPError("There are no AI Mix Assist changes to undo.")
    save_mix_by_cache_path(cache_path, [str(track) for track in previous])
    meta = get_saved_mix_metadata(cache_path, previous)
    section = get_mix_assist_section(meta)
    for key in ("previous_tracks", "replaced", "removed"):
        section.pop(key, None)
    meta[MIX_ASSIST_SECTION] = section
    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)
    return len(previous)


def edit_mix_assist_intent(cache_path: str) -> bool:
    """Let the listener write what the mix is about; an empty text goes back to the AI's statement."""
    meta = get_saved_mix_metadata(cache_path, load_mix_by_cache_path(cache_path))
    section = get_mix_assist_section(meta)
    current = str(section.get("listener_intent") or section.get("intent") or "")
    try:
        value = xbmcgui.Dialog().input("What is this mix about?", defaultt=current)
    except TypeError:
        value = xbmcgui.Dialog().input("What is this mix about?", current)
    if value is None or value == current:
        return False
    value = str(value).strip()
    if value:
        section["listener_intent"] = value
    else:
        section.pop("listener_intent", None)
    meta[MIX_ASSIST_SECTION] = section
    save_json_file(mix_meta_path_from_cache_path(cache_path), meta)
    return True


def build_mix_assist_info_lines(meta: dict) -> list[str]:
    section = get_mix_assist_section(meta)
    if not section:
        return []
    lines = ["", "AI Mix Assist:"]
    intent = section.get("listener_intent") or section.get("intent")
    if intent:
        source = "your words" if section.get("listener_intent") else "stated by the AI"
        lines.append(f"What this mix is about ({source}): {intent}")
    if section.get("checked_ts"):
        lines.append(f"Last tidied up: {format_sidecar_ts(section.get('checked_ts'))}")
    for change in section.get("replaced") or []:
        lines.append(f"Replaced: {change.get('old_label', '')} → {change.get('new_label', '')} ({change.get('reason', '')})")
    for label in section.get("removed") or []:
        lines.append(f"Removed: {label}")
    return lines


def build_mix_assist_action(action: str, cache_path: str) -> str:
    return f"RunPlugin({addon_url(action=action, cache_path=cache_path, nonce=new_nonce())})"


def router() -> None:
    ensure_musicip_keymap_installed()
    params = parse_args()
    action = params.get("action", "")

    if not action:
        show_root()
        return

    if action == "mix_info":
        cache_path = params.get("cache_path", "").strip()
        if cache_path:
            show_mix_info(cache_path)
        else:
            show_selected_mix_info()
        return

    if action == "mix_info_selected":
        show_selected_mix_info()
        return

    if action == "keyboard_remove_from_mix":
        run_selected_mix_keyboard_action("MusicIP.MixAction.Remove", "Remove from mix")
        return

    if action == "keyboard_more_like_this":
        run_selected_mix_keyboard_action("MusicIP.MixAction.MoreLikeThis", "More like this")
        return

    if action == "keyboard_less_like_this":
        run_selected_mix_keyboard_action("MusicIP.MixAction.LessLikeThis", "Less like this")
        return

    if action == "discovery_mode":
        show_discovery_mode_menu()
        return

    if action == "discovery_start":
        start_discovery_mode()
        return

    if action == "discovery_stop":
        stop_discovery_mode()
        return

    if action == "discovery_next":
        discovery_next_track()
        return

    if action == "discovery_mix_current":
        discovery_mix_from_current()
        return

    if action == "radio_mode":
        show_radio_mode_menu()
        return

    if action == "radio_on":
        turn_radio_on()
        return

    if action == "radio_tune":
        tune_radio()
        return

    if action == "radio_play":
        start_radio()
        return

    if action == "radio_retune":
        change_radio_station()
        return

    if action == "radio_start_seed":
        # From the library context menu (context_radio.py), run as an action: the current view stays.
        start_radio_from_song(params.get("seed", ""))
        return

    if action == "radio_stop":
        stop_radio()
        return

    if action == "saved_mixes":
        show_saved_mixes()
        return

    if action == "saved_mixes_by_date":
        date_key = params.get("date", "").strip()
        if not date_key:
            notify("No date was supplied.", xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)
            return
        show_saved_mixes_by_date(date_key)
        return

    if action == "cleanup_saved_mixes":
        date_key = params.get("date", "").strip()
        include_older = params.get("older") == "1"
        if not date_key:
            notify("No date was supplied.", xbmcgui.NOTIFICATION_ERROR)
            return
        try:
            removed = cleanup_saved_mixes_for_date(date_key, include_older=include_older)
        except Exception as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            return
        if include_older:
            notify(f"Removed {removed} stored mix(es) from {date_key} and older.")
        else:
            notify(f"Removed {removed} stored mix(es) from {date_key}.")
        xbmc.executebuiltin(f"Container.Update({build_saved_mixes_url()},replace)")
        return

    if action == "cleanup_saved_mix":
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No stored mix path was supplied.", xbmcgui.NOTIFICATION_ERROR)
            return
        try:
            delete_saved_mix_files(cache_path)
        except Exception as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            return
        notify("Removed mix.")
        xbmc.executebuiltin(f"Container.Update({build_saved_mixes_url()},replace)")
        return

    if action == "check_mix_consistency":
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No saved mix was selected.", xbmcgui.NOTIFICATION_ERROR)
            return

        consistency = analyze_mix_consistency(cache_path)
        missing = int(consistency.get("missing_files") or 0)

        if missing:
            notify(f"Mix inconsistent: {missing} missing.", xbmcgui.NOTIFICATION_WARNING)
        else:
            notify("Mix consistency OK.")

        xbmc.executebuiltin("Container.Refresh")
        return

    if action == "update_library_before_repair":
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No saved mix was selected.", xbmcgui.NOTIFICATION_ERROR)
            return

        show_update_library_before_repair(cache_path)
        xbmc.executebuiltin("Container.Refresh")
        return

    if action in ("mix_assist_tidy_up", "mix_assist_undo", "mix_assist_edit_intent"):
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No saved mix was selected.", xbmcgui.NOTIFICATION_ERROR)
            return
        try:
            if action == "mix_assist_tidy_up":
                notify(mix_assist_result_message(run_mix_assist_on_saved_mix(cache_path)))
            elif action == "mix_assist_undo":
                undo_mix_assist_on_saved_mix(cache_path)
                notify("AI Mix Assist: the changes were undone.")
            elif edit_mix_assist_intent(cache_path):
                notify("Saved. Tidy up the mix to apply it.")
        except mix_assist_claude.ClaudeError as exc:
            log(f"AI Mix Assist: {exc.kind}: {exc}", xbmc.LOGERROR)
            notify(MIX_ASSIST_MESSAGES.get(exc.kind, str(exc)), xbmcgui.NOTIFICATION_ERROR)
        except MusicIPError as exc:
            log(f"AI Mix Assist: {exc}", xbmc.LOGERROR)
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        xbmc.executebuiltin("Container.Refresh")
        return

    if action == "repair_mix":
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No saved mix was selected.", xbmcgui.NOTIFICATION_ERROR)
            return

        try:
            ensure_repair_ready(cache_path)
            repaired = repair_saved_mix_foreground(cache_path)
        except MusicIPError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            xbmc.executebuiltin("Container.Refresh")
            return

        notify(f"Repaired {repaired} track(s).")
        xbmc.executebuiltin("Container.Refresh")
        return

    if action == "generate_current_mix":
        generate_current_mix()
        return

    if action == "browse_mix":
        seed = params.get("seed", "").strip()
        if not seed:
            notify("No seed song was supplied.", xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)
            return
        size = int(params.get("size") or get_playlist_size())
        refresh = params.get("refresh") == "1"
        try:
            focus_index = int(params.get("focus_index", "-1"))
        except (TypeError, ValueError):
            focus_index = -1
        focus_token = params.get("focus_token", "").strip()
        browse_mix(
            seed,
            size,
            force_refresh=refresh,
            update_listing=refresh,
            focus_index=focus_index,
            focus_token=focus_token,
        )
        return

    if action == "browse_saved_mix":
        cache_path = params.get("cache_path", "").strip()
        if not cache_path:
            notify("No stored mix path was supplied.", xbmcgui.NOTIFICATION_ERROR)
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)
            return
        refresh = params.get("refresh") == "1"
        try:
            focus_index = int(params.get("focus_index", "-1"))
        except (TypeError, ValueError):
            focus_index = -1
        focus_token = params.get("focus_token", "").strip()
        browse_saved_mix(
            cache_path,
            force_refresh=refresh,
            update_listing=refresh,
            focus_index=focus_index,
            focus_token=focus_token,
        )
        return

    if action == "play_track":
        path = params.get("path", "")
        if not path:
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            return
        play_track(path)
        return

    if action == "remove_track":
        seed = params.get("seed", "").strip()
        size = int(params.get("size") or get_playlist_size())
        try:
            index = int(params.get("index", "-1"))
        except (TypeError, ValueError):
            index = -1
        path = params.get("path", "")
        cache_path = params.get("cache_path", "").strip()

        try:
            ensure_remove_allowed_from_addon_container()
            removed_path = remove_track_from_mix(seed, size, index, path, cache_path=cache_path)
        except MusicIPError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            return

        notify(f"Removed: {path_to_label(removed_path)}")
        if cache_path:
            xbmc.executebuiltin(f"Container.Update({build_saved_browse_url(cache_path)},replace)")
        else:
            xbmc.executebuiltin(f"Container.Update({build_browse_url(seed, size)},replace)")
        return

    if action == "more_like_this":
        seed = params.get("seed", "").strip()
        size = int(params.get("size") or get_playlist_size())
        try:
            index = int(params.get("index", "-1"))
        except (TypeError, ValueError):
            index = -1
        path = params.get("path", "")
        cache_path = params.get("cache_path", "").strip()

        try:
            ensure_remove_allowed_from_addon_container()
            inserted = insert_more_like_this_into_mix(seed, size, index, path, cache_path=cache_path)
        except MusicIPError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            return

        notify(f"Inserted {inserted} track(s).")
        if cache_path:
            refresh_mix_container(build_saved_browse_url(cache_path, focus_index=index))
        else:
            refresh_mix_container(build_browse_url(seed, size, focus_index=index))
        return
    if action == "less_like_this":
        seed = params.get("seed", "").strip()
        size = int(params.get("size") or get_playlist_size())
        try:
            index = int(params.get("index", "-1"))
        except (TypeError, ValueError):
            index = -1
        path = params.get("path", "")
        cache_path = params.get("cache_path", "").strip()

        try:
            ensure_remove_allowed_from_addon_container()
            removed = remove_less_like_this_from_mix(seed, size, index, path, cache_path=cache_path)
        except MusicIPError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
            log(str(exc), xbmc.LOGERROR)
            return

        notify(f"Removed {removed} track(s).")
        focus_index = max(0, index - 1)
        if cache_path:
            refresh_mix_container(build_saved_browse_url(cache_path, focus_index=focus_index))
        else:
            refresh_mix_container(build_browse_url(seed, size, focus_index=focus_index))
        return


    if action == "open_settings":
        open_settings()
        return

    notify(f"Unknown action: {action}", xbmcgui.NOTIFICATION_ERROR)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)


if __name__ == "__main__":
    try:
        router()
    except Exception as exc:  # pragma: no cover - defensive logging in Kodi runtime
        log(f"Unhandled error: {exc}", xbmc.LOGERROR)
        notify(str(exc), xbmcgui.NOTIFICATION_WARNING if "cancelled" in str(exc).lower() else xbmcgui.NOTIFICATION_ERROR)
        try:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False, cacheToDisc=False)
        except Exception:
            pass
