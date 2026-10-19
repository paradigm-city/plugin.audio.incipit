# -*- coding: utf-8 -*-
"""Background consistency checker for saved MusicIP mixes."""

from __future__ import annotations

import glob
import hashlib
import importlib
import json
import datetime
import os
import random
import re
import sqlite3
import threading
import time
import urllib.parse
import unicodedata

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL = 0.0
METADATA_REFRESH_BATCH_SIZE = 5
METADATA_REFRESH_INTERVAL_SECONDS = 5
METADATA_REFRESH_MAX_ATTEMPTS = 3
TRACK_METADATA_CACHE_SCHEMA_VERSION = 1
METADATA_REFRESH_PENDING_VIEW_REFRESH = False
METADATA_REFRESH_LAST_SELECTION_TOKEN = ''
METADATA_REFRESH_LAST_REFRESH_TS = 0
METADATA_REFRESH_MIN_REFRESH_GAP_SECONDS = 2
SONG_METADATA_PROPERTIES = [
    "title", "artist", "displayartist", "album", "albumartist",
    "genre", "file", "year", "duration", "track", "thumbnail", "fanart",
]
SONG_METADATA_SAFE_PROPERTIES = [
    "title", "artist", "album", "genre", "year", "duration", "thumbnail", "fanart",
]


def mark_discovery_internal_player_change(seconds: float = 4.0) -> None:
    global DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL
    DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL = time.time() + float(seconds)


def discovery_internal_player_change_active() -> bool:
    return time.time() < DISCOVERY_INTERNAL_PLAYER_CHANGE_UNTIL



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


def is_service_extended_logging_enabled() -> bool:
    return get_setting_bool("service_extended_logging", False)


def log(message: str, level: int = xbmc.LOGINFO, always: bool = False) -> None:
    # Without extended service logging, only errors (and messages marked always) reach kodi.log.
    if not always and level < xbmc.LOGERROR and not is_service_extended_logging_enabled():
        return
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def log_info(message: str) -> None:
    log(message, xbmc.LOGINFO)



def log_discovery(message: str, level: int = xbmc.LOGINFO) -> None:
    log(f"Discovery mode: {message}", level)

def execute_jsonrpc(method: str, params: dict | None = None) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params:
        payload["params"] = params

    raw = xbmc.executeJSONRPC(json.dumps(payload))
    response = json.loads(raw)
    if "error" in response:
        raise RuntimeError(f"Kodi JSON-RPC error for {method}: {response['error']}")
    return response.get("result", {})


def parse_kodi_datetime(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0

    match = re.search(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[ T]([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?)?",
        text,
    )
    if not match:
        log_info(f"Library freshness: could not parse Kodi datetime value {text!r}")
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
        log_info(f"Library freshness: parsed Kodi datetime {text!r} as timestamp {timestamp}")
        return timestamp
    except Exception as exc:
        log_info(f"Library freshness: failed to convert Kodi datetime {text!r}: {exc}")
        return 0


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
        log(f"Library freshness: could not read Kodi audio library properties: {exc}", xbmc.LOGERROR)
        return {
            "properties": {},
            "timestamps": {},
            "freshest_ts": 0,
            "freshest_property": "",
        }

    timestamps = {}
    for key in properties:
        timestamps[key] = parse_kodi_datetime(result.get(key))
        log_info(
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


def get_repair_readiness_for_consistency(consistency: dict, mix_label: str = "", search: dict | None = None) -> dict:
    # The rule lives in the plugin module; the service only logs with its own setting.
    plugin = load_plugin_module()
    readiness = plugin.evaluate_repair_readiness(consistency, search)
    log_info(plugin.format_repair_readiness_log(readiness, mix_label))
    return readiness


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
    try:
        return int(get_setting(name, str(default)))
    except (TypeError, ValueError):
        return default


def is_consistency_service_enabled() -> bool:
    return get_setting_bool("consistency_enabled", True)


def is_service_auto_repair_enabled() -> bool:
    return get_setting_bool("service_auto_repair_enabled", False)


def get_check_interval_seconds() -> int:
    minutes = max(1, get_setting_int("consistency_interval_minutes", 60))
    return minutes * 60


def get_profile_dir() -> str:
    profile = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    if not xbmcvfs.exists(profile):
        xbmcvfs.mkdirs(profile)
    return profile


DISCOVERY_BUFFER_SIZE = 10
DISCOVERY_REFILL_THRESHOLD = 5
DISCOVERY_BACKLOG_SIZE = 10



def load_json_file(path: str) -> dict:
    try:
        if not xbmcvfs.exists(path):
            return {}
        with xbmcvfs.File(path, "r") as handle:
            raw = handle.read()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception as exc:
        log(f"Could not load JSON file {path!r}: {exc}", xbmc.LOGWARNING)
        return {}


def save_json_file(path: str, payload: dict) -> None:
    try:
        parent = os.path.dirname(path)
        if parent and not xbmcvfs.exists(parent):
            xbmcvfs.mkdirs(parent)
        with xbmcvfs.File(path, "w") as handle:
            handle.write(json.dumps(payload or {}, indent=2, ensure_ascii=False))
    except Exception as exc:
        log(f"Could not save JSON file {path!r}: {exc}", xbmc.LOGERROR)

def get_music_playlist() -> xbmc.PlayList:
    return xbmc.PlayList(xbmc.PLAYLIST_MUSIC)


class DiscoveryPlaybackMonitor(xbmc.Player):
    def _stop_discovery_from_player_event(self, event_name: str) -> None:
        if discovery_internal_player_change_active():
            log_info(f"Discovery mode: ignored {event_name} during internal player change.")
            return

        state = load_discovery_state()
        if not state.get("enabled"):
            return

        state["enabled"] = False
        state["stopped_ts"] = int(time.time())
        state["stop_reason"] = event_name
        state["resume_allowed"] = False
        state["ui_refresh_requested"] = True
        state["ui_refresh_ts"] = int(time.time())
        save_discovery_state(state)
        log_info(f"Discovery mode stopped because Kodi player event occurred: {event_name}.")

    def onPlayBackStopped(self) -> None:
        if discovery_internal_player_change_active():
            log_info("Discovery mode: ignored player_stop during internal player change.")
            return

        state = load_discovery_state()
        if not state.get("enabled"):
            return

        state["pending_player_stop"] = True
        state["pending_player_stop_ts"] = int(time.time())
        state["pending_player_stop_reason"] = "player_stop_event"
        save_discovery_state(state)
        log_info("Discovery mode: player_stop event received; deferring classification.")

    def onPlayBackEnded(self) -> None:
        if discovery_internal_player_change_active():
            log_info("Discovery mode: ignored player_end during internal player change.")
            return

        state = load_discovery_state()
        if not state.get("enabled"):
            return

        state["playlist_change_pending"] = True
        state["playlist_change_pending_ts"] = int(time.time())
        save_discovery_state(state)
        log_info("Discovery mode: player ended; playlist change pending.")

    def onPlayBackError(self) -> None:
        self._stop_discovery_from_player_event("player_error")


def discovery_state_path() -> str:
    return os.path.join(get_profile_dir(), "discovery_mode_state.json")


def get_discovery_excerpt_seconds() -> int:
    try:
        value = int(ADDON.getSetting("discovery_excerpt_seconds") or 20)
    except Exception:
        value = 20
    return max(5, min(60, value))


def get_discovery_offset_percent() -> int:
    try:
        value = int(ADDON.getSetting("discovery_offset_percent") or 33)
    except Exception:
        value = 33
    return max(0, min(90, value))


def load_discovery_state() -> dict:
    return load_json_file(discovery_state_path())


def save_discovery_state(state: dict) -> None:
    save_json_file(discovery_state_path(), state or {})


def discovery_song_label(song: dict) -> str:
    title = str(song.get("title") or "").strip()
    artist = song.get("artist") or song.get("displayartist") or ""
    if isinstance(artist, list):
        artist = ", ".join(str(item) for item in artist if item)

    artist = str(artist or "").strip()
    if artist and title:
        return f"{artist} - {title}"
    return title or path_to_label(str(song.get("file") or ""))


def get_song_duration_seconds(song: dict) -> int:
    try:
        duration = int(song.get("duration") or 0)
    except Exception:
        duration = 0

    if duration > 0:
        return duration

    song_id = song.get("songid")
    if song_id is None:
        return 0

    try:
        result = execute_jsonrpc(
            "AudioLibrary.GetSongDetails",
            {
                "songid": int(song_id),
                "properties": ["duration"],
            },
        )
        details = result.get("songdetails") or {}
        return max(0, int(details.get("duration") or 0))
    except Exception as exc:
        log_info(f"Discovery mode: could not read song duration for songid={song_id!r}: {exc}")
        return 0


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


def discovery_queue_entry(song: dict, excerpt_seconds: int, offset_percent: int) -> dict:
    file_path = str(song.get("file") or "").strip()
    duration = get_song_duration_seconds(song)
    offset = calculate_discovery_offset(duration, excerpt_seconds, offset_percent)
    return {
        "file": file_path,
        "label": discovery_song_label(song),
        "duration": duration,
        "offset": offset,
        "songid": song.get("songid"),
    }


def discovery_playlist_item(entry: dict) -> xbmcgui.ListItem:
    label = str(entry.get("label") or path_to_label(str(entry.get("file") or "")))
    item = xbmcgui.ListItem(label=label, offscreen=True)
    try:
        item.setProperty("StartOffset", str(int(entry.get("offset") or 0)))
    except Exception:
        pass
    try:
        item.setProperty("MusicIP.Discovery", "true")
        item.setProperty("MusicIP.DiscoveryFile", str(entry.get("file") or ""))
        item.setProperty("MusicIP.DiscoveryOffset", str(int(entry.get("offset") or 0)))
    except Exception:
        pass
    return item


def append_discovery_entry_to_playlist(entry: dict) -> bool:
    file_path = str(entry.get("file") or "").strip()
    if not file_path:
        log_discovery("not appending empty playlist entry.", xbmc.LOGWARNING)
        return False
    try:
        get_music_playlist().add(file_path, discovery_playlist_item(entry))
        log_discovery(
            f"appended playlist item: label={entry.get('label')!r}, "
            f"offset={entry.get('offset')}s, file={file_path!r}"
        )
        return True
    except Exception as exc:
        log_discovery(f"could not append playlist item {file_path!r}: {exc}", xbmc.LOGERROR)
        return False


def state_playlist_position(state: dict, default: int = -1) -> int:
    try:
        value = state.get("current_playlist_position")
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def player_position() -> int:
    try:
        props = execute_jsonrpc("Player.GetProperties", {"playerid": 0, "properties": ["position"]})
        return int(props.get("position"))
    except Exception:
        return -1


def goto_music_playlist_position(position: int) -> None:
    execute_jsonrpc("Player.GoTo", {"playerid": 0, "to": int(position)})


def ensure_discovery_queue(state: dict, song_cache: list[dict]) -> tuple[dict, list[dict]]:
    queue = state.get("queue")
    if not isinstance(queue, list):
        queue = []

    excerpt_seconds = int(state.get("excerpt_seconds") or get_discovery_excerpt_seconds())
    offset_percent = int(state.get("offset_percent") or get_discovery_offset_percent())

    if not song_cache:
        song_cache = get_music_library_songs()

    log_discovery(
        f"ensuring playlist buffer: current_queue={len(queue)}, "
        f"target={DISCOVERY_BUFFER_SIZE}, song_cache={len(song_cache)}"
    )

    added = 0
    attempts = 0
    max_attempts = max(50, DISCOVERY_BUFFER_SIZE * 10)

    while len(queue) < DISCOVERY_BUFFER_SIZE and song_cache and attempts < max_attempts:
        attempts += 1
        song = choose_discovery_song(song_cache)
        entry = discovery_queue_entry(song, excerpt_seconds, offset_percent)
        if not entry.get("file"):
            continue
        if append_discovery_entry_to_playlist(entry):
            queue.append(entry)
            added += 1

    state["queue"] = queue
    state["buffer_size"] = DISCOVERY_BUFFER_SIZE
    state["refill_threshold"] = DISCOVERY_REFILL_THRESHOLD

    if added:
        log_discovery(f"playlist buffer appended {added} item(s); queue now {len(queue)}.")
    else:
        log_discovery(
            f"playlist buffer appended no items. attempts={attempts}, "
            f"song_cache={len(song_cache)}, queue={len(queue)}",
            xbmc.LOGWARNING,
        )

    return state, song_cache


def refill_discovery_playlist_if_needed(state: dict, song_cache: list[dict]) -> tuple[dict, list[dict]]:
    if not state.get("enabled") or state.get("startup_in_progress"):
        return state, song_cache

    position = player_position()
    queue = state.get("queue")
    if not isinstance(queue, list):
        queue = []

    remaining = len(queue) - position - 1 if position >= 0 else len(queue)
    if remaining >= DISCOVERY_REFILL_THRESHOLD:
        return state, song_cache

    target_len = max(DISCOVERY_BUFFER_SIZE, (position if position >= 0 else 0) + 1 + DISCOVERY_BUFFER_SIZE)
    excerpt_seconds = int(state.get("excerpt_seconds") or get_discovery_excerpt_seconds())
    offset_percent = int(state.get("offset_percent") or get_discovery_offset_percent())

    if not song_cache:
        song_cache = get_music_library_songs()

    added = 0
    while len(queue) < target_len and song_cache:
        song = choose_discovery_song(song_cache)
        entry = discovery_queue_entry(song, excerpt_seconds, offset_percent)
        if not entry.get("file"):
            continue
        if append_discovery_entry_to_playlist(entry):
            queue.append(entry)
            added += 1

    state["queue"] = queue
    if added:
        save_discovery_state(state)
        log_info(
            f"Discovery mode: appended {added} item(s) at playlist end; "
            f"remaining_future={len(queue) - position - 1 if position >= 0 else len(queue)}."
        )

    return state, song_cache


def prune_discovery_playlist_backlog(state: dict) -> dict:
    if not state.get("enabled") or state.get("startup_in_progress"):
        return state

    position = player_position()
    if position <= DISCOVERY_BACKLOG_SIZE:
        return state

    queue = state.get("queue")
    if not isinstance(queue, list):
        return state

    remove_count = position - DISCOVERY_BACKLOG_SIZE
    if remove_count <= 0:
        return state

    removed = 0
    for _i in range(remove_count):
        try:
            execute_jsonrpc("Playlist.Remove", {"playlistid": 0, "position": 0})
            removed += 1
        except Exception as exc:
            log_info(f"Discovery mode: Playlist.Remove backlog prune failed: {exc}")
            break

    if removed <= 0:
        return state

    state["queue"] = queue[removed:]
    state["current_playlist_position"] = max(0, position - removed)
    state["playlist_pruned_count"] = int(state.get("playlist_pruned_count") or 0) + removed
    save_discovery_state(state)

    log_info(
        f"Discovery mode: pruned {removed} old playlist item(s); "
        f"backlog kept={DISCOVERY_BACKLOG_SIZE}, new_position={state.get('current_playlist_position')}."
    )
    return state


def update_discovery_current_from_playlist(state: dict) -> dict:
    if not state.get("enabled"):
        return state

    position = player_position()
    queue = state.get("queue")
    if not isinstance(queue, list) or position < 0 or position >= len(queue):
        return state

    entry = queue[position]
    current_file = str(entry.get("file") or "")
    if not current_file:
        return state

    previous_file = str(state.get("current_song") or "")
    previous_position = state_playlist_position(state, -1)

    if current_file != previous_file or position != previous_position:
        state["current_song"] = current_file
        state["current_label"] = str(entry.get("label") or path_to_label(current_file))
        state["current_playlist_position"] = position
        state["current_started_ts"] = int(time.time())
        state["current_offset_seconds"] = int(entry.get("offset") or 0)
        state["current_duration_seconds"] = int(entry.get("duration") or 0)
        state["current_seek_confirmed"] = False
        state["current_startoffset_requested"] = bool(int(entry.get("offset") or 0) > 0)
        state["playlist_change_pending"] = False
        save_discovery_state(state)
        log_info(
            f"Discovery mode: current playlist item is now position={position}, "
            f"label={state.get('current_label')!r}, offset={state.get('current_offset_seconds')}s."
        )

    return state


def correct_current_playlist_offset_if_needed(state: dict) -> dict:
    if not state.get("enabled"):
        return state

    try:
        offset_seconds = int(state.get("current_offset_seconds") or 0)
    except Exception:
        offset_seconds = 0

    if offset_seconds <= 3:
        return state

    try:
        started_ts = int(state.get("current_started_ts") or 0)
    except Exception:
        started_ts = 0

    if started_ts <= 0 or int(time.time()) - started_ts < 2:
        return state

    if discovery_internal_player_change_active():
        return state

    try:
        player = xbmc.Player()
        if not player.isPlayingAudio():
            return state
        current_time = int(player.getTime() or 0)
    except Exception:
        return state

    if current_time < max(1, offset_seconds - 5):
        try:
            mark_discovery_internal_player_change(2.0)
            player.seekTime(float(offset_seconds))
            state["last_seek_correction_ts"] = int(time.time())
            state["last_seek_correction_from"] = current_time
            state["last_seek_correction_to"] = offset_seconds
            save_discovery_state(state)
            log_info(
                f"Discovery mode: corrected playlist playback position from {current_time}s "
                f"back to offset {offset_seconds}s."
            )
        except Exception as exc:
            log_info(f"Discovery mode: playlist offset correction failed: {exc}")

    return state


def advance_discovery_playlist(state: dict, song_cache: list[dict], reason: str) -> tuple[dict, list[dict]]:
    if not state.get("enabled"):
        return state, song_cache

    state, song_cache = refill_discovery_playlist_if_needed(state, song_cache)

    position = player_position()
    queue = state.get("queue") if isinstance(state.get("queue"), list) else []
    next_position = position + 1 if position >= 0 else 0

    if next_position >= len(queue):
        state, song_cache = ensure_discovery_queue(state, song_cache)
        queue = state.get("queue") if isinstance(state.get("queue"), list) else []

    if next_position < len(queue):
        mark_discovery_internal_player_change(3.0)
        try:
            goto_music_playlist_position(next_position)
            state["last_next_reason"] = reason
            state["last_next_ts"] = int(time.time())
            save_discovery_state(state)
            log_info(f"Discovery mode: advanced playlist to position {next_position} ({reason}).")
        except Exception as exc:
            log_info(f"Discovery mode: Player.GoTo next failed: {exc}")

    return update_discovery_current_from_playlist(state), song_cache


def get_music_library_songs() -> list[dict]:
    log_discovery("loading Kodi music library songs for playlist buffer.")
    params = {
        "properties": ["title", "artist", "displayartist", "album", "duration", "file"],
        "sort": {"method": "random"},
    }

    try:
        result = execute_jsonrpc("AudioLibrary.GetSongs", params)
    except Exception as exc:
        log_discovery(f"AudioLibrary.GetSongs with random sort failed: {exc}", xbmc.LOGWARNING)
        try:
            result = execute_jsonrpc(
                "AudioLibrary.GetSongs",
                {"properties": ["title", "artist", "displayartist", "album", "duration", "file"]},
            )
        except Exception as exc2:
            log_discovery(f"AudioLibrary.GetSongs fallback failed: {exc2}", xbmc.LOGERROR)
            return []

    songs = result.get("songs") or []
    usable = []
    for song in songs:
        file_path = str(song.get("file") or "").strip()
        if file_path:
            usable.append(song)

    log_discovery(f"loaded {len(usable)} usable song(s) from Kodi music library.")
    return usable


def choose_discovery_song(song_cache: list[dict]) -> dict:
    if not song_cache:
        return {}
    return random.choice(song_cache)


def kodi_is_loading_a_list() -> bool:
    """Kodi is still loading a list (or shows its busy dialog). A redraw now would make Kodi drop that list while it
    is being filled, which has crashed Kodi (findings F14); the service redraws a second later instead."""
    for condition in ("Container.IsUpdating", "Window.IsActive(busydialog)", "Window.IsActive(busydialognocancel)"):
        try:
            if xbmc.getCondVisibility(condition):
                return True
        except Exception:
            pass
    return False


def refresh_discovery_menu_if_visible() -> None:
    state = load_discovery_state()
    if not state.get("ui_refresh_requested") or kodi_is_loading_a_list():
        return

    try:
        container_folder = xbmc.getInfoLabel("Container.FolderPath")
    except Exception:
        container_folder = ""

    if not (is_addon_root(container_folder) or
            "plugin.audio.musicip" in container_folder and "action=discovery_mode" in container_folder):
        return

    state["ui_refresh_requested"] = False
    save_discovery_state(state)

    try:
        xbmc.executebuiltin("Container.Refresh")  # a refresh keeps the focused item (Container.Update resets it)
        log_info("Discovery mode: refreshed visible Discovery mode menu.")
    except Exception as exc:
        log_info(f"Discovery mode: could not refresh Discovery mode menu: {exc}")


def stop_discovery_playback(state: dict | None = None) -> dict:
    state = dict(state or load_discovery_state())
    state["enabled"] = False
    state["stopped_ts"] = int(time.time())
    state["resume_allowed"] = False
    state["startup_in_progress"] = False
    state["next_requested"] = False
    state["next_reason"] = ""
    state["pending_player_stop"] = False
    state["pending_player_stop_reason"] = ""
    state["mix_dialog_active"] = False
    state["mix_dialog_seed"] = ""
    state["mix_dialog_started_ts"] = 0
    state["mix_dialog_excerpt_seconds"] = 0
    if not state.get("stop_reason"):
        state["stop_reason"] = "manual_stop"
    save_discovery_state(state)
    try:
        xbmc.Player().stop()
    except Exception:
        pass
    return state


def handle_pending_discovery_player_stop(state: dict) -> dict:
    if not state.get("enabled") or not state.get("pending_player_stop"):
        return state

    try:
        pending_ts = int(state.get("pending_player_stop_ts") or 0)
    except Exception:
        pending_ts = 0

    if pending_ts > 0 and int(time.time()) - pending_ts < 1:
        return state

    try:
        player = xbmc.Player()
        still_playing = bool(player.isPlayingAudio())
    except Exception:
        still_playing = False

    if not still_playing:
        state["enabled"] = False
        state["stopped_ts"] = int(time.time())
        state["stop_reason"] = "player_stop"
        state["resume_allowed"] = False
        state["startup_in_progress"] = False
        state["pending_player_stop"] = False
        state["pending_player_stop_reason"] = ""
        state["next_requested"] = False
        state["next_reason"] = ""
        state["ui_refresh_requested"] = True
        state["ui_refresh_ts"] = int(time.time())
        save_discovery_state(state)
        log_info("Discovery mode stopped after confirmed Kodi player stop.")
        return state

    # In buffered playlist mode, Kodi emits player_stop-like events for
    # perfectly valid playlist transitions: manual Next, automatic GoTo(next),
    # and sometimes player-internal item changes. Do not convert such an event
    # into a second next request. Just clear it and let the playlist position
    # tracker update the current Discovery item.
    try:
        current_time = int(player.getTime() or 0)
    except Exception:
        current_time = 0

    try:
        offset_seconds = int(state.get("current_offset_seconds") or 0)
    except Exception:
        offset_seconds = 0

    state["pending_player_stop"] = False
    state["pending_player_stop_reason"] = ""

    # If Kodi restarted the item near the beginning although Discovery mode
    # expects an offset, correct the position. This also helps Previous/backlog
    # navigation when StartOffset is not applied by Kodi.
    if offset_seconds > 3 and current_time < max(1, offset_seconds - 5):
        try:
            mark_discovery_internal_player_change(2.0)
            player.seekTime(float(offset_seconds))
            state["last_seek_correction_ts"] = int(time.time())
            state["last_seek_correction_from"] = current_time
            state["last_seek_correction_to"] = offset_seconds
            save_discovery_state(state)
            log_info(
                f"Discovery mode: treated pending player_stop as playlist transition; "
                f"corrected from {current_time}s to {offset_seconds}s."
            )
        except Exception as exc:
            save_discovery_state(state)
            log_info(f"Discovery mode: pending transition seek correction failed: {exc}")
        return state

    save_discovery_state(state)
    log_info("Discovery mode: ignored pending player_stop because playback continues.")
    return state



def discovery_next_requested(state: dict) -> bool:
    return bool(state.get("enabled") and state.get("next_requested"))


def clear_discovery_next_request(state: dict) -> dict:
    state["next_requested"] = False
    state["next_reason"] = ""
    return state


def discovery_player_was_stopped_by_user(state: dict) -> bool:
    if not state.get("enabled"):
        return False

    current_song = str(state.get("current_song") or "").strip()
    if not current_song:
        return False

    started_ts = int(state.get("current_started_ts") or 0)
    if started_ts <= 0:
        return False

    # Kodi needs a short grace period after Player.play() before
    # Player.isPlayingAudio() becomes reliable.
    if int(time.time()) - started_ts < 3:
        return False

    try:
        return not xbmc.Player().isPlayingAudio()
    except Exception:
        return False


def discovery_needs_next_song(state: dict) -> bool:
    if not state.get("enabled") or state.get("mix_dialog_active"):
        return False

    try:
        started_ts = int(state.get("current_started_ts") or 0)
    except Exception:
        started_ts = 0

    try:
        last_ui_next_ts = int(state.get("last_ui_next_ts") or 0)
    except Exception:
        last_ui_next_ts = 0

    if last_ui_next_ts > 0 and int(time.time()) - last_ui_next_ts < 2:
        return False

    if started_ts <= 0:
        return False

    try:
        excerpt_seconds = int(state.get("excerpt_seconds") or get_discovery_excerpt_seconds())
    except Exception:
        excerpt_seconds = get_discovery_excerpt_seconds()

    return int(time.time()) - started_ts >= excerpt_seconds


def normalize_discovery_playback_path(path: str) -> str:
    if not path:
        return ""

    try:
        value = urllib.parse.unquote(str(path))
    except Exception:
        value = str(path)

    value = value.replace("\\", "/").strip().lower()

    while "//" in value and not value.startswith("smb://"):
        value = value.replace("//", "/")

    return value


def get_current_playing_file_for_discovery() -> str:
    try:
        player = xbmc.Player()
        if not player.isPlayingAudio():
            return ""
        return str(player.getPlayingFile() or "")
    except Exception as exc:
        log_info(f"Discovery mode: could not read current playing file: {exc}")
        return ""


def current_playback_belongs_to_discovery(state: dict) -> bool:
    current_file = get_current_playing_file_for_discovery()
    if not current_file:
        return True

    current_norm = normalize_discovery_playback_path(current_file)
    if not current_norm:
        return True

    queue = state.get("queue")
    if not isinstance(queue, list) or not queue:
        return True

    discovery_files = set()
    for entry in queue:
        if not isinstance(entry, dict):
            continue
        file_path = normalize_discovery_playback_path(str(entry.get("file") or ""))
        if file_path:
            discovery_files.add(file_path)

    if current_norm in discovery_files:
        return True

    expected = normalize_discovery_playback_path(str(state.get("current_song") or ""))
    if expected and current_norm == expected:
        return True

    log_info(
        f"Discovery mode: current playback is outside Discovery queue. "
        f"current={current_file!r}, queue_size={len(discovery_files)}."
    )
    return False


def stop_discovery_due_to_external_playback(state: dict) -> dict:
    state["enabled"] = False
    state["stopped_ts"] = int(time.time())
    state["stop_reason"] = "external_playback"
    state["resume_allowed"] = False
    state["startup_in_progress"] = False
    state["mix_dialog_active"] = False
    state["mix_dialog_seed"] = ""
    state["mix_dialog_started_ts"] = 0
    state["mix_dialog_excerpt_seconds"] = 0
    state["next_requested"] = False
    state["next_reason"] = ""
    state["pending_player_stop"] = False
    state["pending_player_stop_reason"] = ""
    state["playlist_change_pending"] = False
    state["ui_refresh_requested"] = True
    state["ui_refresh_ts"] = int(time.time())
    save_discovery_state(state)
    log_info("Discovery mode stopped because playback changed outside MusicIP.")
    try:
        refresh_discovery_menu_if_visible()
    except Exception as exc:
        log_info(f"Discovery mode: could not refresh menu after external playback takeover: {exc}")
    return state


def run_discovery_tick(song_cache: list[dict]) -> list[dict]:
    state = load_discovery_state()

    if state.get("startup_in_progress"):
        log_info("Discovery mode: startup in progress; service maintenance skipped.")
        return song_cache

    if not state.get("enabled"):
        return song_cache

    state = handle_pending_discovery_player_stop(state)
    if not state.get("enabled"):
        return song_cache

    if not state.get("startup_in_progress") and not current_playback_belongs_to_discovery(state):
        stop_discovery_due_to_external_playback(state)
        return song_cache

    if discovery_next_requested(state):
        state = clear_discovery_next_request(state)
        state, song_cache = advance_discovery_playlist(state, song_cache, "next_requested")
        return song_cache

    if state.get("mix_dialog_active"):
        state = handle_pending_discovery_player_stop(state)
        if not state.get("enabled"):
            return song_cache
        state = update_discovery_current_from_playlist(state)
        state, song_cache = refill_discovery_playlist_if_needed(state, song_cache)
        state = prune_discovery_playlist_backlog(state)
        state = update_discovery_current_from_playlist(state)
        state = correct_current_playlist_offset_if_needed(state)
        log_info("Discovery mode: mix dialog active; auto-skip paused.")
        return song_cache

    state = update_discovery_current_from_playlist(state)
    state, song_cache = refill_discovery_playlist_if_needed(state, song_cache)
    state = prune_discovery_playlist_backlog(state)
    state = update_discovery_current_from_playlist(state)
    state = correct_current_playlist_offset_if_needed(state)

    if discovery_player_was_stopped_by_user(state):
        state["enabled"] = False
        state["stopped_ts"] = int(time.time())
        state["stop_reason"] = "player_stop"
        state["resume_allowed"] = False
        state["ui_refresh_requested"] = True
        state["ui_refresh_ts"] = int(time.time())
        state["next_requested"] = False
        state["next_reason"] = ""
        state["pending_player_stop"] = False
        state["pending_player_stop_reason"] = ""
        save_discovery_state(state)
        log_info("Discovery mode stopped because Kodi player playback was stopped.")
        return song_cache

    if state.get("enabled") and discovery_needs_next_song(state):
        state, song_cache = advance_discovery_playlist(state, song_cache, "excerpt_elapsed")
        return song_cache

    return song_cache


def load_plugin_module():
    # Mix storage, consistency analysis and repair live in the plugin module (main.py).
    # Importing it has no side effects; the service's own main() is unrelated.
    return importlib.import_module("main")


# --- Radio mode ------------------------------------------------------------------------------
# The plugin scans stations (Discovery snippet playback) and picks one ("Pick this station").
# While it plays, the service follows the playlist, tops it up with new MusicIP mixes seeded from
# the last queued song, prunes old songs, and stops the radio on the player's Stop or when other
# playback takes over. Pause does not stop it.

RADIO_REFILL_THRESHOLD = 3       # top up when fewer future songs remain
RADIO_BACKLOG_SIZE = 10          # played songs kept in the playlist
RADIO_REFILL_SEEDS = 3           # last queued songs tried as seed when a mix brings nothing new
RADIO_REFILL_RETRY_SECONDS = 60  # wait after a failed or empty top-up
RADIO_OUTAGE_MAX_WAIT_SECONDS = 600  # MusicIP failing again and again: the wait doubles up to this
RADIO_STOP_GRACE_SECONDS = 3     # playback must be stopped this long (gaps between songs are shorter)
RADIO_MAX_SEEN = 5000            # songs remembered per session to avoid repeats
RADIO_CHECKED_THRESHOLD = 3      # with AI Mix Assist: top up when fewer songs remain (the check takes 1-2 minutes)
RADIO_CHECK_SIZE = 75            # MusicIP candidates per checked refill (MusicIP's maximum)
RADIO_CHECKED_BATCH = 6          # songs per checked refill (15-40 minutes): small steps for a smooth meander; 6 is an experiment (was 8)

# One AI Mix Assist check at a time, in a background thread; the radio tick applies its result.
RADIO_CHECK: dict = {"thread": None, "station": 0, "kind": "", "result": None, "fallback": [], "seed": "",
                     "superseded": False}


def radio_state_path() -> str:
    return os.path.join(get_profile_dir(), "radio_mode_state.json")


def load_radio_state() -> dict:
    return load_json_file(radio_state_path())


def save_radio_state(state: dict) -> None:
    save_json_file(radio_state_path(), state or {})


def radio_is_active() -> bool:
    return str(load_radio_state().get("phase") or "off") in ("seeking", "playing")


def end_radio(state: dict, reason: str) -> dict:
    state.update({
        "phase": "off",
        "stopped_ts": int(time.time()),
        "stop_reason": reason,
        "ui_refresh_requested": True,
        "ui_refresh_ts": int(time.time()),
    })
    save_radio_state(state)
    log_info(f"Radio mode stopped: {reason}.")
    return state


def run_radio_tick() -> None:
    state = load_radio_state()
    phase = str(state.get("phase") or "off")

    if phase == "seeking":
        if int(time.time()) - int(state.get("tuning_started_ts") or 0) < RADIO_STOP_GRACE_SECONDS:
            return  # the plugin is still starting the snippet playback
        discovery = load_discovery_state()
        if not discovery.get("enabled") and not discovery.get("startup_in_progress"):
            # Tuning plays Discovery snippets; when they stop (player stop, other playback), so does the radio.
            end_radio(state, str(discovery.get("stop_reason") or "tuning_stopped"))
            return
        snippet = str(discovery.get("current_song") or "")
        if snippet and snippet != state.get("scan_song"):
            # The next snippet plays: the Radio screen shows it in its title, so it is redrawn (if it is open).
            state["scan_song"] = snippet
            state["ui_refresh_requested"] = True
            save_radio_state(state)
        return

    if phase != "playing":
        return

    now = int(time.time())
    try:
        playing = bool(xbmc.Player().isPlayingAudio())  # stays True while paused
    except Exception:
        playing = False

    if not playing:
        since = int(state.get("not_playing_since") or 0)
        if since <= 0:
            state["not_playing_since"] = now
            save_radio_state(state)
        elif now - since >= RADIO_STOP_GRACE_SECONDS and now - int(state.get("playing_started_ts") or 0) >= RADIO_STOP_GRACE_SECONDS:
            end_radio(state, "player_stop")
        return
    state["not_playing_since"] = 0

    queue = [entry for entry in state.get("queue") or [] if isinstance(entry, dict) and entry.get("file")]
    state["queue"] = queue
    current_file = get_current_playing_file_for_discovery()
    queued = {normalize_discovery_playback_path(str(entry["file"])) for entry in queue}
    just_started = now - int(state.get("playing_started_ts") or 0) < RADIO_STOP_GRACE_SECONDS
    if current_file and normalize_discovery_playback_path(current_file) not in queued and not just_started:
        # A new station may still be replacing the old one's playback during the grace period.
        end_radio(state, "external_playback")
        return

    position = player_position()
    if 0 <= position < len(queue):
        entry = queue[position]
        if state.get("current_position") != position or state.get("current_song") != entry["file"]:
            state["current_position"] = position
            state["current_song"] = entry["file"]
            state["current_label"] = entry.get("label") or path_to_label(entry["file"])
            state["played"] = int(state.get("played") or 0) + (1 if position > 0 else 0)
            log_info(f"Radio mode: now playing {state['current_label']!r} (position {position}).")

    position = prune_radio_backlog(state, position)

    plugin = load_plugin_module()
    assisted = radio_mix_assist_enabled(plugin)
    if assisted:
        apply_radio_check(state, plugin, position)
        keep_radio_from_running_dry(state, plugin, position)
        if not state.get("start_checked") and not radio_check_busy():
            state["start_checked"] = True
            start_radio_start_check(state, plugin)

    remaining = len(state["queue"]) - position - 1 if position >= 0 else len(state["queue"])
    threshold = RADIO_CHECKED_THRESHOLD if assisted else RADIO_REFILL_THRESHOLD
    if remaining < threshold and now >= int(state.get("next_refill_ts") or 0) and not radio_check_busy():
        refill_radio_queue(state, checked=assisted)

    save_radio_state(state)


RADIO_MAX_EVENTS = 200


def add_radio_event(state: dict, kind: str, **details) -> None:
    """Record what happened to the station (shown in "Station information")."""
    events = [event for event in state.get("events") or [] if isinstance(event, dict)]
    events.append(dict(details, kind=kind, ts=int(time.time())))
    state["events"] = events[-RADIO_MAX_EVENTS:]


def radio_song_label(state: dict, path: str) -> str:
    return next((str(entry.get("label")) for entry in state.get("queue") or [] if entry.get("file") == path and entry.get("label")),
                path_to_label(path))


def radio_mix_assist_enabled(plugin) -> bool:
    try:
        return bool(plugin.mix_assist_for_radio())
    except Exception:
        return False


def radio_station_id(state: dict) -> int:
    """Changes with every new station (each starts playing anew)."""
    return int(state.get("playing_started_ts") or 0)


def radio_check_running() -> bool:
    thread = RADIO_CHECK.get("thread")
    return thread is not None and thread.is_alive()


def radio_check_busy() -> bool:
    """A check is running, or its result waits to be applied."""
    return radio_check_running() or RADIO_CHECK.get("result") is not None


def start_radio_check(state: dict, kind: str, job, fallback=(), seed: str = "") -> None:
    """Run job() (an AI Mix Assist check) in a background thread; apply_radio_check() takes the result."""
    monitor = xbmc.Monitor()

    def check() -> None:
        if monitor.abortRequested():
            raise RuntimeError("Kodi is shutting down.")

    def run() -> None:
        try:
            RADIO_CHECK["result"] = job(check)
        except Exception as exc:
            RADIO_CHECK["result"] = {"error": exc}

    RADIO_CHECK.update(station=radio_station_id(state), kind=kind, result=None, fallback=list(fallback), seed=seed,
                       superseded=False)
    RADIO_CHECK["thread"] = threading.Thread(target=run, daemon=True)
    RADIO_CHECK["thread"].start()


def start_radio_start_check(state: dict, plugin) -> None:
    seed = str(state.get("seed") or "")
    files = [str(entry["file"]) for entry in state.get("queue") or []]
    tracks = [seed] + [track for track in files if plugin.normalize_track_identity(track) != plugin.normalize_track_identity(seed)]
    if seed and len(tracks) > 2:
        log_info(f"Radio mode: AI Mix Assist checks the station's first {len(tracks) - 1} song(s).")
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else None
        start_radio_check(state, "start", lambda check: plugin.check_radio_start(tracks, check=check, settings=settings))


def keep_radio_from_running_dry(state: dict, plugin, position: int) -> None:
    """The last song plays and the refill check is still running: queue MusicIP's songs unchecked now, or the
    player would stop (and with it the radio). The check's songs are then not added; its profile still counts."""
    if not radio_check_running() or RADIO_CHECK["kind"] != "refill" or RADIO_CHECK["superseded"]:
        return
    if RADIO_CHECK["station"] != radio_station_id(state) or position < 0 or position < len(state["queue"]) - 1:
        return
    RADIO_CHECK["superseded"] = True
    log_info("Radio mode: the refill check is taking long; adding MusicIP's songs unchecked so the music goes on.")
    append_radio_tracks(state, plugin, RADIO_CHECK["seed"], RADIO_CHECK["fallback"],
                        event={"kind": "refill_unchecked", "reason": "the AI check took too long"})


def apply_radio_check(state: dict, plugin, position: int) -> None:
    """Apply a finished check to the station it was made for."""
    if radio_check_running() or RADIO_CHECK.get("result") is None:
        return
    kind, result, station = RADIO_CHECK["kind"], RADIO_CHECK["result"], RADIO_CHECK["station"]
    fallback, seed, superseded = RADIO_CHECK["fallback"], RADIO_CHECK["seed"], RADIO_CHECK["superseded"]
    RADIO_CHECK.update(thread=None, result=None, fallback=[], seed="", superseded=False)
    if station != radio_station_id(state):
        return  # the station changed meanwhile
    if superseded:
        if result.get("reference"):
            state["reference"] = result["reference"]  # its songs were replaced by the unchecked ones
            add_radio_event(state, "profile", profile=result["reference"])
        return

    error = result.get("error")
    if error is not None:
        log(f"Radio mode: AI Mix Assist check failed: {error}", xbmc.LOGWARNING)
        if getattr(error, "kind", ""):
            plugin.report_automatic_mix_assist_error(error)
        if kind == "refill" and fallback:  # keep the station going, unchecked
            append_radio_tracks(state, plugin, seed, fallback,
                                event={"kind": "refill_unchecked", "reason": "the AI check failed"})
        return

    if kind == "start":
        remove = {plugin.normalize_track_identity(track) for track in result.get("remove") or []}
        reasons = {plugin.normalize_track_identity(entry.get("path", "")): entry for entry in result.get("removed") or []}
        removed_songs = []
        removed = 0
        for index in range(len(state["queue"]) - 1, position + 1, -1):  # never the playing song or the next one
            if plugin.normalize_track_identity(str(state["queue"][index]["file"])) not in remove:
                continue
            try:
                execute_jsonrpc("Playlist.Remove", {"playlistid": 0, "position": index})
            except Exception as exc:
                log_info(f"Radio mode: removing a song that doesn't fit failed: {exc}")
                continue
            entry = state["queue"].pop(index)
            removed += 1
            reason = reasons.get(plugin.normalize_track_identity(str(entry["file"])), {}).get("reason", "")
            removed_songs.insert(0, {"track": entry.get("label") or path_to_label(str(entry["file"])), "reason": reason})
        state["intent"] = result.get("intent") or ""
        state["reference"] = result.get("reference")
        if result.get("name") and not state.get("favourite_id"):
            state["name"] = result["name"]
        add_radio_event(state, "start_check", removed=removed_songs, intent=state["intent"], profile=state["reference"],
                        name=result.get("name") or "")
        log_info(f"Radio mode: AI Mix Assist took out {removed} song(s) that didn't fit the station.")
        return

    chosen = list(result.get("chosen") or [])
    if result.get("reference"):
        state["reference"] = result["reference"]
    skipped = len(result.get("not_fitting") or [])
    if chosen:
        not_fitting = result.get("not_fitting") or []
        append_radio_tracks(state, plugin, seed, chosen, event={
            "kind": "refill", "checked": True, "intent": result.get("intent") or "", "profile": result.get("reference"),
            "skipped_count": skipped,
            "skipped": [{"track": entry.get("label", ""), "reason": entry.get("reason", "")} for entry in not_fitting[:10]]})
        state["refill_seed_offset"] = 0
        log_info(f"Radio mode: AI Mix Assist kept {len(chosen)} song(s), skipped {skipped}.")
        return
    remaining = len(state["queue"]) - position - 1 if position >= 0 else len(state["queue"])
    if remaining <= 1 and fallback:
        log_info("Radio mode: nothing fitted and the station is about to run dry; adding MusicIP's songs unchecked.")
        append_radio_tracks(state, plugin, seed, fallback, event={
            "kind": "refill_unchecked", "reason": "nothing fitted and the station was about to run dry"})
        return
    # Nothing fitted the song before this refill: next time, seed from an earlier song.
    add_radio_event(state, "nothing_fitted", seed=radio_song_label(state, seed), skipped_count=skipped,
                    intent=result.get("intent") or "")
    state["refill_seed_offset"] = int(state.get("refill_seed_offset") or 0) + 1
    state["next_refill_ts"] = int(time.time()) + RADIO_REFILL_RETRY_SECONDS
    log_info(f"Radio mode: none of {skipped} song(s) fitted; trying an earlier seed.")


def prune_radio_backlog(state: dict, position: int) -> int:
    """Remove songs played longer ago than the backlog; returns the adjusted playlist position."""
    if position <= RADIO_BACKLOG_SIZE:
        return position
    removed = 0
    for _index in range(position - RADIO_BACKLOG_SIZE):
        try:
            execute_jsonrpc("Playlist.Remove", {"playlistid": 0, "position": 0})
            removed += 1
        except Exception as exc:
            log_info(f"Radio mode: removing an old playlist entry failed: {exc}")
            break
    if removed:
        state["queue"] = state["queue"][removed:]
        state["current_position"] = max(0, position - removed)
        log_info(f"Radio mode: removed {removed} old song(s) from the playlist.")
    return position - removed


def refill_radio_queue(state: dict, checked: bool = False) -> int:
    """Top up the station with a MusicIP mix seeded from the last queued song. Returns songs added. With checked,
    MusicIP's songs go to AI Mix Assist first (in the background) and are added when the check is done."""
    plugin = load_plugin_module()
    queue = state["queue"]
    seen_set = set(state.get("seen") or [])
    now = int(time.time())
    new_tracks: list[str] = []
    used_seed = ""
    size = plugin.get_playlist_size()
    offset = int(state.get("refill_seed_offset") or 0) if checked else 0

    server_error = None
    for attempt, entry in enumerate(list(reversed(queue))[offset:offset + RADIO_REFILL_SEEDS]):
        seed = str(entry["file"])
        try:
            request_size = RADIO_CHECK_SIZE if checked else size
            tracks = plugin.fetch_mix(seed, request_size, plugin.get_effective_mix_parameters(size_override=request_size),
                                      reload=attempt == 0)
        except Exception as exc:
            if isinstance(exc, plugin.MusicIPError) and "empty mix" in str(exc):
                log_info(f"Radio mode: MusicIP returned no songs for {seed!r}.")
                continue  # try the song before it
            log(f"Radio mode: MusicIP mix for {seed!r} failed: {exc}", xbmc.LOGWARNING)
            if server_error is None:
                server_error = exc
                continue  # it may be this song: try the one before it, once
            break  # two songs failed: MusicIP itself has a problem
        server_error = None
        new_tracks = []
        for track in tracks:
            identity = plugin.normalize_track_identity(track)
            if identity not in seen_set and identity not in {plugin.normalize_track_identity(t) for t in new_tracks}:
                new_tracks.append(track)
        if new_tracks:
            used_seed = seed
            break
        log_info(f"Radio mode: mix from {seed!r} brought no new songs.")

    if server_error is not None:
        musicip_outage(state, plugin, server_error)
        return 0
    if int(state.get("musicip_failures") or 0):
        state["musicip_failures"] = 0
        add_radio_event(state, "musicip_back")
        log_info("Radio mode: MusicIP makes mixes again.")
    if not new_tracks:
        state["next_refill_ts"] = now + RADIO_REFILL_RETRY_SECONDS
        state["refill_seed_offset"] = 0
        log_info(f"Radio mode: no new songs for the station; retrying in {RADIO_REFILL_RETRY_SECONDS} s.")
        return 0

    if checked:
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else None  # a favourite's own
        drifting = plugin.get_radio_drift_half_life(settings) > 0
        reference_song = used_seed if drifting else str(state.get("seed") or used_seed)
        reference = state.get("reference") if isinstance(state.get("reference"), dict) else None
        neighbours = [str(entry["file"]) for entry in queue]
        candidates, fallback = list(new_tracks), list(new_tracks[:RADIO_CHECKED_BATCH])
        log_info(f"Radio mode: AI Mix Assist picks {RADIO_CHECKED_BATCH} song(s) from MusicIP's {len(candidates)} "
                 f"suggestion(s) for {used_seed!r} (closest first, checked in groups).")
        start_radio_check(
            state, "refill",
            lambda check: plugin.check_radio_refill(reference_song, candidates, RADIO_CHECKED_BATCH, reference, neighbours,
                                                    check=check, settings=settings),
            fallback=fallback, seed=used_seed)
        return 0

    return append_radio_tracks(state, plugin, used_seed, new_tracks, event={"kind": "refill", "checked": False})


def musicip_outage(state: dict, plugin, error: Exception) -> None:
    """MusicIP failed for two songs in a row: wait longer each time (1, 2, 4, 8, then 10 minutes), so a struggling
    server isn't asked (and reloaded) every minute; say so once, on the screen and in the station's history."""
    failures = int(state.get("musicip_failures") or 0) + 1
    wait = min(RADIO_OUTAGE_MAX_WAIT_SECONDS, RADIO_REFILL_RETRY_SECONDS * 2 ** (failures - 1))
    state["musicip_failures"] = failures
    state["next_refill_ts"] = int(time.time()) + wait
    state["refill_seed_offset"] = 0
    log(f"Radio mode: MusicIP can't make mixes ({error}); trying again in {wait} s.", xbmc.LOGWARNING)
    if failures == 1:
        add_radio_event(state, "musicip_failed", error=str(error))
        try:
            plugin.notify("MusicIP can't make mixes right now. The station plays on and tries again; if it lasts, "
                          "restart the MusicIP server.", xbmcgui.NOTIFICATION_WARNING)
        except Exception:
            pass


def append_radio_tracks(state: dict, plugin, used_seed: str, new_tracks: list[str], event: dict | None = None) -> int:
    """Queue songs at the end of the station's playlist; they count as seen for the rest of the session. event
    (with its "kind") is recorded for "Station information", with the seed and the songs added."""
    queue = state["queue"]
    seed_label = radio_song_label(state, used_seed)
    first_new = len(queue)
    seen = list(state.get("seen") or [])
    # Look songs up in the library: a station's songs are mostly new to the metadata cache (labels need artists).
    metadata_list = plugin.collect_mix_track_metadata(new_tracks, allow_live_lookup=True, include_player_metadata=False)
    playlist = get_music_playlist()
    for track, metadata in zip(new_tracks, metadata_list):
        item = plugin.build_mix_playlist_item(track, metadata, 0)
        playlist.add(track, item)
        queue.append({"file": track, "label": item.getLabel()})
        seen.append(plugin.normalize_track_identity(track))

    plugin.enqueue_metadata_refresh_for_tracks(new_tracks, metadata_list=metadata_list, reason_context="radio")
    state["seen"] = seen[-RADIO_MAX_SEEN:]
    state["seeds"] = (list(state.get("seeds") or []) + [used_seed])[-50:]
    state["next_refill_ts"] = 0
    if event:
        details = dict(event)
        add_radio_event(state, details.pop("kind"), seed=seed_label,
                        added=[str(entry.get("label") or "") for entry in queue[first_new:]], **details)
    log_info(f"Radio mode: added {len(new_tracks)} song(s) seeded from {used_seed!r}.")
    return len(new_tracks)


def is_addon_root(folder: str) -> bool:
    """The add-on's first screen (its icons show what Radio and Discovery are doing)."""
    return folder.rstrip("/").rstrip("?").rstrip("/") == f"plugin://{ADDON_ID}"


def refresh_radio_menu_if_visible() -> None:
    state = load_radio_state()
    if not state.get("ui_refresh_requested") or kodi_is_loading_a_list():
        return
    try:
        container_folder = xbmc.getInfoLabel("Container.FolderPath")
    except Exception:
        container_folder = ""
    if not (is_addon_root(container_folder) or
            "plugin.audio.musicip" in container_folder and "action=radio_mode" in container_folder):
        return
    state["ui_refresh_requested"] = False
    save_radio_state(state)
    try:
        xbmc.executebuiltin("Container.Refresh")  # a refresh keeps the focused item (Container.Update resets it)
    except Exception as exc:
        log_info(f"Radio mode: could not refresh the Radio screen: {exc}")


def reset_radio_mode_on_startup() -> None:
    state = load_radio_state()
    if str(state.get("phase") or "off") != "off":
        state.update({"phase": "off", "stopped_ts": int(time.time()), "stop_reason": "startup_reset"})
        save_radio_state(state)
        log_info("Radio mode: reset at service start.")


def run_consistency_check() -> int:
    """Check all saved mixes for missing files; auto-repair when enabled and safe. Returns inconsistent mixes."""
    plugin = load_plugin_module()
    auto_repair = is_service_auto_repair_enabled()
    cache_paths = plugin.list_saved_mix_cache_paths()
    repaired_tracks = 0
    blocked_labels: list[str] = []
    sources_blocked = False

    checked: list[tuple[str, dict, dict, str]] = []
    for cache_path in cache_paths:
        try:
            consistency = plugin.analyze_mix_consistency(cache_path)
            if str(consistency.get("status") or "") != "inconsistent":
                continue
            meta = plugin.get_saved_mix_metadata(cache_path)
            label = str(meta.get("label") or os.path.basename(cache_path))
            log_info(f"Consistency check: {label!r} has {consistency.get('missing_files')} missing track(s).")
            checked.append((cache_path, consistency, meta, label))
        except Exception as exc:
            log(f"Consistency check failed for {cache_path!r}: {exc}", xbmc.LOGWARNING)

    newly_found, newly_unscanned = update_missing_file_searches(plugin, checked)

    for cache_path, consistency, meta, label in checked:
        try:
            search = meta.get("missing_file_search")
            readiness = get_repair_readiness_for_consistency(consistency, label, search)
            if auto_repair and readiness.get("status") == "ready":
                repaired = plugin.repair_saved_mix_automatic_only(cache_path)
                repaired_tracks += repaired
                log_info(f"Consistency check: automatic repair of {label!r} replaced {repaired} track(s).")
                if repaired:
                    meta = plugin.get_saved_mix_metadata(cache_path)
                    readiness = get_repair_readiness_for_consistency(plugin.get_consistency_status(meta), label, search)
            elif auto_repair and readiness.get("status") in ("update_library_before_repair", "update_sources_before_repair"):
                blocked_labels.append(label)
                sources_blocked = sources_blocked or readiness.get("status") == "update_sources_before_repair"

            meta["repair_readiness"] = readiness
            save_json_file(mix_meta_path_from_cache_path(cache_path), meta)
        except Exception as exc:
            log(f"Consistency check failed for {cache_path!r}: {exc}", xbmc.LOGWARNING)

    log_info(
        f"Consistency check: checked {len(cache_paths)} mix(es), {len(checked)} inconsistent, "
        f"automatic repair {'enabled' if auto_repair else 'disabled'}, repaired {repaired_tracks} track(s)."
    )
    if newly_found:
        notify_missing_files_found_outside_sources(newly_found)
    if newly_unscanned:
        notify_missing_files_found_in_unscanned_sources(newly_unscanned)
    if blocked_labels:
        notify_repair_waiting_for_library(blocked_labels, sources_blocked)
    return len(checked)


def update_missing_file_searches(plugin, checked: list[tuple[str, dict, dict, str]]) -> tuple[list[str], list[str]]:
    """Search the disks for missing files of mixes whose last search is out of date.

    Stores the result in each mix's sidecar (meta["missing_file_search"]) and returns what was not reported
    for those mixes before: locations of missing files found outside the music sources, and never-scanned
    music sources in which missing files were found.
    """
    outdated = [
        entry for entry in checked
        if not plugin.missing_file_search_is_current(entry[2].get("missing_file_search"), entry[1])
    ]
    if not outdated:
        return [], []
    if load_discovery_state().get("enabled") or radio_is_active():
        log_info("Consistency check: missing-file search postponed while Discovery or Radio mode is active.")
        return [], []

    try:
        sources = plugin.get_music_source_paths()
    except Exception as exc:
        log_info(f"Consistency check: missing-file search skipped, music sources unreadable: {exc}")
        return [], []

    missing_paths = sorted({
        str(item.get("path") or "")
        for _cache_path, consistency, _meta, _label in outdated
        for item in consistency.get("missing") or []
        if isinstance(item, dict) and item.get("path")
    })
    result = plugin.search_missing_files_outside_sources(missing_paths, sources)
    log_info(
        f"Consistency check: searched {result['folders_searched']} folder(s) below {result['roots']!r} for "
        f"{len(missing_paths)} missing file(s); found {len(result['found_outside_sources'])} outside the music sources"
        f"{'' if result['complete'] else ' (search stopped at its time limit)'}: "
        f"{sorted(result['found_outside_sources'].values())!r}; found {len(result['found_in_unscanned_sources'])} "
        f"in music sources not scanned into the library {result['unscanned_sources']!r}."
    )

    newly_found: list[str] = []
    newly_unscanned: list[str] = []
    for cache_path, consistency, meta, _label in outdated:
        own_paths = {str(item.get("path") or "") for item in consistency.get("missing") or [] if isinstance(item, dict)}
        found = {old: new for old, new in result["found_outside_sources"].items() if old in own_paths}
        in_unscanned = {old: new for old, new in result["found_in_unscanned_sources"].items() if old in own_paths}
        unscanned = sorted({
            plugin.find_covering_music_source(location, result["unscanned_sources"]) for location in in_unscanned.values()
        })
        previous = meta.get("missing_file_search") if isinstance(meta.get("missing_file_search"), dict) else {}
        reported = set((previous.get("found_outside_sources") or {}).values())
        for location in found.values():
            if location not in reported and location not in newly_found:
                newly_found.append(location)
        for source in unscanned:
            if source not in (previous.get("unscanned_sources") or []) and source not in newly_unscanned:
                newly_unscanned.append(source)
        meta["missing_file_search"] = {
            "checked_ts": result["checked_ts"],
            "signature": str(consistency.get("missing_signature") or ""),
            "roots": result["roots"],
            "found_outside_sources": found,
            "found_in_unscanned_sources": in_unscanned,
            "unscanned_sources": unscanned,
            "complete": result["complete"],
        }
        save_json_file(mix_meta_path_from_cache_path(cache_path), meta)
    return newly_found, newly_unscanned


def notify_missing_files_found_outside_sources(locations: list[str]) -> None:
    # Only informs: whether to add the location to the music sources is the user's decision.
    if len(locations) == 1:
        message = f"Missing file found outside of the music sources: {locations[0]}"
    else:
        message = f"{len(locations)} missing files found outside of the music sources, e.g. {locations[0]}"
    log_info(f"Consistency check: notifying about missing files outside the music sources: {locations!r}")
    try:
        xbmcgui.Dialog().notification(ADDON.getAddonInfo("name"), message, xbmcgui.NOTIFICATION_INFO)
    except Exception as exc:
        log(f"Could not show notification about missing files outside the music sources: {exc}", xbmc.LOGWARNING)


def notify_missing_files_found_in_unscanned_sources(sources: list[str]) -> None:
    # The question itself is asked in the plugin ("Scan music source before repair"), not from the background.
    if len(sources) == 1:
        message = f"Missing file found in a music source that is not scanned into the library: {sources[0]}"
    else:
        message = f"Missing files found in {len(sources)} music sources that are not scanned into the library."
    log_info(f"Consistency check: notifying about missing files in unscanned music sources: {sources!r}")
    try:
        xbmcgui.Dialog().notification(ADDON.getAddonInfo("name"), message, xbmcgui.NOTIFICATION_INFO)
    except Exception as exc:
        log(f"Could not show notification about unscanned music sources: {exc}", xbmc.LOGWARNING)


def notify_repair_waiting_for_library(labels: list[str], sources_blocked: bool = False) -> None:
    action = "Check the Kodi music sources" if sources_blocked else "Update the Kodi music library"
    if len(labels) == 1:
        message = f"Mix '{labels[0]}' has missing tracks. {action} to allow automatic repair."
    else:
        message = f"{len(labels)} mixes have missing tracks. {action} to allow automatic repair."
    log_info(f"Consistency check: notifying that automatic repair is waiting for a library update: {labels!r}")
    try:
        xbmcgui.Dialog().notification(ADDON.getAddonInfo("name"), message, xbmcgui.NOTIFICATION_WARNING)
    except Exception as exc:
        log(f"Could not show repair notification: {exc}", xbmc.LOGWARNING)


def reset_discovery_mode_on_startup() -> None:
    state = load_discovery_state()
    now = int(time.time())

    state.update({
        "enabled": False,
        "startup_in_progress": False,
        "stopped_ts": now,
        "stop_reason": "startup_reset",
        "resume_allowed": False,
        "current_started_ts": 0,
        "current_song": "",
        "current_label": "",
        "current_playlist_position": -1,
        "current_offset_seconds": 0,
        "current_duration_seconds": 0,
        "current_seek_confirmed": False,
        "current_startoffset_requested": False,
        "ui_refresh_requested": False,
        "next_requested": False,
        "next_reason": "",
        "pending_player_stop": False,
        "pending_player_stop_reason": "",
        "playlist_change_pending": False,
        "mix_dialog_active": False,
        "mix_dialog_seed": "",
        "mix_dialog_started_ts": 0,
        "mix_dialog_excerpt_seconds": 0,
        "queue": [],
        "last_error": "",
    })

    save_discovery_state(state)

    try:
        get_music_playlist().clear()
        log_discovery("startup reset cleared Kodi music playlist.")
    except Exception as exc:
        log_discovery(f"startup reset could not clear Kodi music playlist: {exc}", xbmc.LOGWARNING)

    log_discovery(
        f"startup reset completed. state_path={discovery_state_path()}"
    )


def metadata_refresh_queue_path() -> str:
    return os.path.join(get_profile_dir(), "metadata_refresh_queue.json")


def track_metadata_cache_db_path() -> str:
    return os.path.join(get_profile_dir(), "track_metadata_cache.db")


def mix_meta_path_from_cache_path(cache_path: str) -> str:
    return f"{cache_path}.json"


def canonical_audio_path(path: str) -> str:
    value = (path or "").strip()
    value = urllib.parse.unquote(value)
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


def path_to_label(path: str) -> str:
    base = os.path.basename(str(path or "").rstrip("/\\"))
    title, _ext = os.path.splitext(base)
    return title if title else base if base else str(path or "")


def split_full_path(path: str) -> tuple[str, str]:
    value = (path or "").strip().rstrip("/\\")
    if not value:
        return "", ""

    slash_pos = max(value.rfind("/"), value.rfind("\\"))
    if slash_pos < 0:
        return value, ""

    return value[slash_pos + 1 :], value[:slash_pos]


def build_path_candidates(directory: str) -> list[str]:
    raw = (directory or "").strip().rstrip("/\\")
    if not raw:
        return []

    candidates: list[str] = []

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(raw)
    normalized = raw.replace("\\", "/")
    add(normalized)

    if "://" in normalized:
        add(normalized + "/")
    else:
        add(raw + os.sep)
        add(normalized + "/")
        if "\\" in raw:
            add(raw + "\\")

    return candidates


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


def first_non_empty_text(value: object) -> str:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return " / ".join(parts)
    return str(value or "").strip()


def normalize_genres(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text_value = str(value or "").strip()
    if not text_value:
        return []

    return [text_value]


def parse_year(value: object) -> int:
    try:
        year = int(value or 0)
    except (TypeError, ValueError):
        return 0

    return year if year > 0 else 0


def parse_duration_seconds(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def format_decade(year: int) -> str:
    parsed_year = parse_year(year)
    if parsed_year <= 0:
        return ""

    decade_start = (parsed_year // 10) * 10
    return f"{decade_start}s"


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


def get_track_metadata_cache_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(track_metadata_cache_db_path())
    connection.row_factory = sqlite3.Row
    ensure_track_metadata_cache_schema(connection)
    return connection


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
        log(f"Background metadata cache write failed for {path!r}: {exc}", xbmc.LOGWARNING)


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


def query_library_songs_by_filename(filename: str) -> list[dict]:
    if not filename:
        return []

    return audio_library_get_songs_with_metadata_properties(
        {
            "filter": {"field": "filename", "operator": "is", "value": filename},
        },
        f"Background filename-only library lookup for {filename!r}",
    )


def query_library_songs_strict(filename: str, directory: str) -> list[dict]:
    if not filename:
        return []

    filters: list[dict] = [
        {"field": "filename", "operator": "is", "value": filename},
    ]

    path_candidates = build_path_candidates(directory)
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
        f"Background strict library lookup for {filename!r}",
    )


def extract_song_metadata(song: dict) -> dict[str, object]:
    artist_value = ""
    for key in ("artist", "displayartist", "albumartist"):
        artist_value = first_non_empty_text(song.get(key))
        if artist_value:
            break

    year_value = parse_year(song.get("year"))

    return {
        "songid": int(song.get("songid") or 0),
        "title": str(song.get("title") or "").strip(),
        "artist": artist_value,
        "album": str(song.get("album") or "").strip(),
        "genre": normalize_genres(song.get("genre")),
        "year": year_value,
        "decade": format_decade(year_value),
        "duration": parse_duration_seconds(song.get("duration")),
        "thumbnail": str(song.get("thumbnail") or "").strip(),
        "fanart": str(song.get("fanart") or "").strip(),
    }


def get_library_track_metadata(path: str) -> dict[str, object]:
    filename, directory = split_full_path(path)
    if not filename:
        return {}

    strict_candidates = query_library_songs_strict(filename, directory)
    matched_song = find_song_by_file_relaxed(strict_candidates, path)
    if matched_song is not None:
        return extract_song_metadata(matched_song)

    if len(strict_candidates) == 1:
        return extract_song_metadata(strict_candidates[0])

    filename_candidates = query_library_songs_by_filename(filename)
    matched_song = find_song_by_file_relaxed(filename_candidates, path)
    if matched_song is not None:
        return extract_song_metadata(matched_song)

    if len(filename_candidates) == 1:
        return extract_song_metadata(filename_candidates[0])

    return {}


def update_mix_sidecar_track_metadata(cache_path: str, path: str, metadata: dict) -> None:
    cache_path = str(cache_path or "").strip()
    if not cache_path:
        return

    key = canonical_audio_path(path)
    if not key:
        return

    sidecar_path = mix_meta_path_from_cache_path(cache_path)
    meta = load_json_file(sidecar_path)
    if not isinstance(meta, dict):
        meta = {}

    track_map = meta.get("track_metadata_by_path")
    if not isinstance(track_map, dict):
        track_map = {}

    track_map[key] = normalize_track_metadata_snapshot(path, metadata)
    meta["track_metadata_by_path"] = track_map
    meta["track_metadata_cached_ts"] = int(time.time())

    try:
        library_ts = int(metadata.get("library_freshest_ts") or 0)
    except Exception:
        library_ts = 0

    if library_ts > 0:
        meta["track_metadata_library_freshest_ts"] = library_ts

    save_json_file(sidecar_path, meta)


def load_metadata_refresh_queue() -> dict:
    payload = load_json_file(metadata_refresh_queue_path())
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


def save_metadata_refresh_queue(entries: list[dict]) -> None:
    save_json_file(
        metadata_refresh_queue_path(),
        {
            "version": 1,
            "updated_ts": int(time.time()),
            "entries": entries,
        },
    )


def get_visible_musicip_mix_context() -> dict:
    try:
        container_folder = xbmc.getInfoLabel("Container.FolderPath") or ""
    except Exception:
        container_folder = ""

    try:
        window_id = xbmcgui.getCurrentWindowId()
    except Exception:
        window_id = 0

    folder_lc = container_folder.casefold()

    is_musicip_view = (
        "plugin.audio.musicip" in folder_lc
        or "plugin://plugin.audio.musicip" in folder_lc
    )

    is_mix_view = (
        "action=browse_mix" in folder_lc
        or "action=browse_saved_mix" in folder_lc
        or "browse_mix" in folder_lc
        or "browse_saved_mix" in folder_lc
        or "cache_path=" in folder_lc
    )

    is_music_nav = int(window_id or 0) in (10500, 10501, 10502, 10503)

    return {
        "folder": container_folder,
        "window_id": int(window_id or 0),
        "is_musicip_view": is_musicip_view,
        "is_mix_view": is_mix_view,
        "is_music_nav": is_music_nav,
        "is_visible_mix": bool(is_musicip_view and (is_mix_view or is_music_nav)),
    }


def get_visible_selection_token() -> str:
    parts: list[str] = []

    for label in (
        "Container.CurrentItem",
        "ListItem.FileNameAndPath",
        "ListItem.FilenameAndPath",
        "ListItem.Path",
        "ListItem.Label",
    ):
        try:
            value = xbmc.getInfoLabel(label) or ""
        except Exception:
            value = ""
        parts.append(str(value))

    return "|".join(parts)


def mark_metadata_refresh_pending_view_refresh(refreshed_count: int) -> None:
    global METADATA_REFRESH_PENDING_VIEW_REFRESH
    global METADATA_REFRESH_LAST_SELECTION_TOKEN

    if refreshed_count <= 0:
        return

    context = get_visible_musicip_mix_context()
    if not context.get("is_visible_mix"):
        return

    METADATA_REFRESH_PENDING_VIEW_REFRESH = True
    METADATA_REFRESH_LAST_SELECTION_TOKEN = get_visible_selection_token()

    log(
        "Background metadata refresh is pending visible presentation "
        f"after selection change; refreshed={refreshed_count}, "
        f"window_id={context.get('window_id')}, folder={context.get('folder')!r}.",
        xbmc.LOGINFO,
    )


def apply_pending_metadata_refresh_on_selection_change() -> None:
    global METADATA_REFRESH_PENDING_VIEW_REFRESH
    global METADATA_REFRESH_LAST_SELECTION_TOKEN
    global METADATA_REFRESH_LAST_REFRESH_TS

    if not METADATA_REFRESH_PENDING_VIEW_REFRESH or kodi_is_loading_a_list():
        return

    context = get_visible_musicip_mix_context()
    if not context.get("is_visible_mix"):
        METADATA_REFRESH_PENDING_VIEW_REFRESH = False
        METADATA_REFRESH_LAST_SELECTION_TOKEN = ""
        return

    current_token = get_visible_selection_token()
    if not current_token or current_token == METADATA_REFRESH_LAST_SELECTION_TOKEN:
        return

    now = int(time.time())
    if METADATA_REFRESH_LAST_REFRESH_TS > 0 and now - METADATA_REFRESH_LAST_REFRESH_TS < METADATA_REFRESH_MIN_REFRESH_GAP_SECONDS:
        return

    folder = str(context.get("folder") or "")

    try:
        if folder:
            xbmc.executebuiltin(f"Container.Update({folder},replace)")
        else:
            xbmc.executebuiltin("Container.Refresh")
        METADATA_REFRESH_LAST_REFRESH_TS = now
        log(
            "Background metadata refresh presented updated metadata after selection change.",
            xbmc.LOGINFO,
        )
    except Exception as exc:
        log(f"Selection-triggered metadata presentation refresh failed: {exc}", xbmc.LOGWARNING)
        try:
            xbmc.executebuiltin("Container.Refresh")
            METADATA_REFRESH_LAST_REFRESH_TS = now
        except Exception as fallback_exc:
            log(f"Fallback selection-triggered Container.Refresh failed: {fallback_exc}", xbmc.LOGWARNING)

    METADATA_REFRESH_PENDING_VIEW_REFRESH = False
    METADATA_REFRESH_LAST_SELECTION_TOKEN = current_token


def refresh_visible_mix_view_if_needed(refreshed_count: int) -> None:
    # In Kodi plugin directory views, list rows cannot be mutated directly after
    # xbmcplugin.endOfDirectory(). Instead of refreshing immediately when the
    # background batch finishes, defer presentation until the user's next
    # selection movement. That avoids surprising list rebuilds while the user is
    # reading the current row, but still presents metadata without navigating out.
    mark_metadata_refresh_pending_view_refresh(refreshed_count)

def run_metadata_refresh_tick(max_items: int = METADATA_REFRESH_BATCH_SIZE) -> int:
    queue = load_metadata_refresh_queue()
    entries = queue.get("entries")
    if not isinstance(entries, list) or not entries:
        return 0

    freshness = get_audio_library_freshness()
    library_freshest_ts = int((freshness or {}).get("freshest_ts") or 0)
    now = int(time.time())

    processed = 0
    refreshed = 0
    remaining: list[dict] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        if processed >= max_items:
            remaining.append(entry)
            continue

        path = str(entry.get("path") or "").strip()
        if not path:
            continue

        processed += 1
        metadata = get_library_track_metadata(path)

        if metadata and track_metadata_snapshot_has_payload(path, metadata):
            snapshot = normalize_track_metadata_snapshot(
                path,
                metadata,
                cached_ts=now,
                library_freshest_ts=library_freshest_ts,
            )
            write_track_metadata_cache(path, snapshot)

            cache_paths = entry.get("cache_paths")
            if isinstance(cache_paths, list):
                for cache_path in cache_paths:
                    update_mix_sidecar_track_metadata(str(cache_path or ""), path, snapshot)

            refreshed += 1
            continue

        attempts = int(entry.get("attempts") or 0) + 1
        if attempts < METADATA_REFRESH_MAX_ATTEMPTS:
            entry["attempts"] = attempts
            entry["last_attempt_ts"] = now
            remaining.append(entry)
        else:
            log(f"Background metadata refresh dropped unresolved track after {attempts} attempts: {path}", xbmc.LOGWARNING)

    if processed > 0:
        save_metadata_refresh_queue(remaining)

    if refreshed > 0:
        log(f"Background metadata refresh processed={processed}, refreshed={refreshed}, remaining={len(remaining)}.", xbmc.LOGINFO)
        refresh_visible_mix_view_if_needed(refreshed)

    return refreshed


# --- AI Mix Assist ---------------------------------------------------------------------------
# The plugin queues new mixes; the service tidies them up one at a time in a background thread, so the
# service loop (Discovery, Radio, consistency) keeps running while Claude and MusicIP are busy.

MIX_ASSIST_WORKER: threading.Thread | None = None


def run_mix_assist_tick() -> None:
    global MIX_ASSIST_WORKER
    if MIX_ASSIST_WORKER is not None and MIX_ASSIST_WORKER.is_alive():
        return
    plugin = load_plugin_module()
    entry = plugin.pop_mix_assist_request()
    if not entry:
        return
    log_info(f"AI Mix Assist: tidying up {entry.get('cache_path')!r} ({entry.get('mode')}).")
    MIX_ASSIST_WORKER = threading.Thread(target=run_mix_assist_request, args=(plugin, entry), daemon=True)
    MIX_ASSIST_WORKER.start()


def run_mix_assist_request(plugin, entry: dict) -> None:
    try:
        plugin.process_mix_assist_request(entry)
    except Exception as exc:
        log(f"AI Mix Assist: tidying up {entry.get('cache_path')!r} failed: {exc}", xbmc.LOGERROR)


# --- Cover collages for saved mixes: one mix at a time, now and then, so the service loop stays quick ---------

MIX_COLLAGE_INTERVAL_SECONDS = 15
MIX_COLLAGE_STATE = {"last_ts": 0, "tried": {}}  # cache path -> collage path tried (too few covers: not again)


def run_mix_collage_tick() -> str:
    """Draw the collage of one saved mix that has none for its current tracks. Returns its path or ""."""
    now = time.time()
    if now - MIX_COLLAGE_STATE["last_ts"] < MIX_COLLAGE_INTERVAL_SECONDS:
        return ""
    MIX_COLLAGE_STATE["last_ts"] = now
    plugin = load_plugin_module()
    for cache_path in plugin.list_saved_mix_cache_paths():
        try:
            tracks = plugin.load_mix_by_cache_path(cache_path)
            wanted = plugin.mix_collage_path(cache_path, tracks)
        except Exception:
            continue
        if os.path.isfile(wanted) or MIX_COLLAGE_STATE["tried"].get(cache_path) == wanted:
            continue
        MIX_COLLAGE_STATE["tried"][cache_path] = wanted
        path = plugin.make_mix_collage(cache_path)
        log_info(f"Mix cover collage for {cache_path!r}: {path or 'too few covers'}.")
        return path
    return ""


def main() -> None:
    monitor = xbmc.Monitor()
    playback_monitor = DiscoveryPlaybackMonitor()
    last_run_ts = 0
    last_metadata_refresh_ts = 0
    song_cache: list[dict] = []

    ensure_musicip_keymap_installed()

    log(
        f"MusicIP service started. "
        f"version={ADDON.getAddonInfo('version')}, "
        f"profile={get_profile_dir()}, "
        f"discovery_state={discovery_state_path()}, "
        f"consistency_enabled={is_consistency_service_enabled()}, "
        f"interval={get_check_interval_seconds()} seconds.",
        xbmc.LOGINFO,
        always=True,
    )

    reset_discovery_mode_on_startup()
    reset_radio_mode_on_startup()

    while not monitor.abortRequested():
        try:
            apply_pending_metadata_refresh_on_selection_change()
            refresh_discovery_menu_if_visible()
            song_cache = run_discovery_tick(song_cache)
        except Exception as exc:
            log(f"Discovery mode tick failed: {exc}", xbmc.LOGERROR)

        try:
            run_radio_tick()
            refresh_radio_menu_if_visible()
        except Exception as exc:
            log(f"Radio mode tick failed: {exc}", xbmc.LOGERROR)

        try:
            run_mix_assist_tick()
        except Exception as exc:
            log(f"AI Mix Assist tick failed: {exc}", xbmc.LOGERROR)

        try:
            run_mix_collage_tick()
        except Exception as exc:
            log(f"Mix cover collage tick failed: {exc}", xbmc.LOGERROR)

        now_for_metadata = int(time.time())
        if last_metadata_refresh_ts <= 0 or now_for_metadata - last_metadata_refresh_ts >= METADATA_REFRESH_INTERVAL_SECONDS:
            try:
                run_metadata_refresh_tick()
            except Exception as exc:
                log(f"Background metadata refresh tick failed: {exc}", xbmc.LOGERROR)
            last_metadata_refresh_ts = now_for_metadata

        if is_consistency_service_enabled():
            now = int(time.time())
            interval = get_check_interval_seconds()

            if last_run_ts <= 0 or now - last_run_ts >= interval:
                run_consistency_check()
                last_run_ts = now
        else:
            log_info("Consistency service is disabled in settings.")

        if monitor.waitForAbort(1):
            break

    try:
        state = load_discovery_state()
        if state.get("enabled"):
            stop_discovery_playback(state)
    except Exception:
        pass

    log_info("MusicIP service stopped.")


if __name__ == "__main__":
    main()
