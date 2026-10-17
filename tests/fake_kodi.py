"""In-memory stand-in for Kodi's Python API: xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs.

install() registers the fake modules in sys.modules so the add-on can be imported outside Kodi.
All fakes share one KodiState (``kodi``); tests call kodi.reset() between cases.

What is modelled:
- add-on settings, with defaults read from resources/settings.xml
- special://profile paths, mapped to a temporary directory
- music files and folders: a path "exists" only if a test added it (never the real disk);
  xbmcvfs.listdir() browses what was added
- JSON-RPC: AudioLibrary (songs with filters, properties, scan/clean), Files.GetSources (music sources),
  Player, Playlist, Settings
- player and music playlist, dialogs with scripted answers, plugin directory listings
"""

from __future__ import annotations

import atexit
import json
import ntpath
import os
import re
import shutil
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_ID = "plugin.audio.musicip"
PROFILE_URL = f"special://profile/addon_data/{ADDON_ID}/"

LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL = 0, 1, 2, 3, 4
PLAYLIST_MUSIC, PLAYLIST_VIDEO = 0, 1
NOTIFICATION_INFO, NOTIFICATION_WARNING, NOTIFICATION_ERROR = "info", "warning", "error"

# SQLite LIKE (used by Kodi's "contains" filter) folds case for ASCII letters only.
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def read_setting_defaults() -> dict:
    """Defaults from resources/settings.xml (Kodi's settings format version 1: <default> elements)."""
    tree = ET.parse(os.path.join(ADDON_DIR, "resources", "settings.xml"))
    return {node.get("id"): (node.findtext("default") or "") for node in tree.iter("setting") if node.get("id")}


def read_addon_version() -> str:
    return ET.parse(os.path.join(ADDON_DIR, "addon.xml")).getroot().get("version", "")


def media_key(path: str) -> str:
    return str(path or "").replace("\\", "/").rstrip("/").casefold()


def path_parts(path: str) -> list:
    return [part for part in re.split(r"[\\/]+", str(path or "")) if part]


class JsonRpcError(Exception):
    pass


class InfoTagMusic:
    def __init__(self, **values):
        self.values = {
            "title": "", "artist": "", "album": "", "track": 0, "genres": [], "year": 0,
            "duration": 0, "url": "", "comment": "",
        }
        self.values.update(values)

    def setTitle(self, value): self.values["title"] = value
    def getTitle(self): return self.values["title"]
    def setArtist(self, value): self.values["artist"] = value
    def getArtist(self): return self.values["artist"]
    def setAlbum(self, value): self.values["album"] = value
    def getAlbum(self): return self.values["album"]
    def setTrack(self, value): self.values["track"] = value
    def getTrack(self): return self.values["track"]
    def setGenres(self, value): self.values["genres"] = list(value)
    def getGenres(self): return list(self.values["genres"])
    def getGenre(self): return " / ".join(self.values["genres"])
    def setYear(self, value): self.values["year"] = value
    def getYear(self): return self.values["year"]
    def setDuration(self, value): self.values["duration"] = value
    def getDuration(self): return self.values["duration"]
    def setURL(self, value): self.values["url"] = value
    def getURL(self): return self.values["url"]
    def setComment(self, value): self.values["comment"] = value
    def getComment(self): return self.values["comment"]


class ListItem:
    def __init__(self, label="", label2="", path="", offscreen=False):
        self.label = label
        self.label2 = label2
        self.path = path
        self.properties = {}
        self.art = {}
        self.context_menu = []
        self.tag = InfoTagMusic()

    def getLabel(self): return self.label
    def setLabel(self, label): self.label = label
    def getLabel2(self): return self.label2
    def setLabel2(self, label): self.label2 = label
    def getPath(self): return self.path
    def setPath(self, path): self.path = path
    def setArt(self, art): self.art.update(art)
    def getArt(self, key): return self.art.get(key, "")
    def getMusicInfoTag(self): return self.tag

    # Kodi property keys are case-insensitive.
    def setProperty(self, key, value): self.properties[key.lower()] = value
    def getProperty(self, key): return self.properties.get(key.lower(), "")

    def addContextMenuItems(self, items, replaceItems=False):
        if replaceItems:
            self.context_menu = []
        self.context_menu.extend(items)

    def context_action(self, label):
        for item_label, action in self.context_menu:
            if item_label == label:
                return action
        raise KeyError(f"No context menu item {label!r}; have {[l for l, _a in self.context_menu]}")


class FakeLibrary:
    def __init__(self, kodi_state):
        self.kodi = kodi_state
        self.songs = []

    def add_song(self, file, title="", artist="", album="", present=True, **fields):
        song = {
            "songid": len(self.songs) + 1,
            "file": file,
            "title": title,
            "artist": [artist] if isinstance(artist, str) and artist else list(artist or []),
            "album": album,
        }
        song.update(fields)
        song.setdefault("label", title)
        self.songs.append(song)
        if present:
            self.kodi.add_media(file)
        return song

    @staticmethod
    def field_text(song, field):
        file_value = str(song.get("file") or "")
        if field == "filename":
            return ntpath.basename(file_value)
        if field == "path":
            return file_value[: len(file_value) - len(ntpath.basename(file_value))]
        value = song.get(field)
        if isinstance(value, list):
            return " / ".join(str(item) for item in value)
        return str(value if value is not None else "")

    def matches(self, song, rule):
        if "and" in rule:
            return all(self.matches(song, sub) for sub in rule["and"])
        if "or" in rule:
            return any(self.matches(song, sub) for sub in rule["or"])
        actual = self.field_text(song, rule["field"])
        value = str(rule["value"])
        operator = rule["operator"]
        if operator == "is":
            return actual == value
        if operator == "contains":
            return value.translate(_ASCII_LOWER) in actual.translate(_ASCII_LOWER)
        if operator == "startswith":
            return actual.translate(_ASCII_LOWER).startswith(value.translate(_ASCII_LOWER))
        raise JsonRpcError(f"Unsupported filter operator {operator!r}")

    def get_songs(self, params):
        rule = params.get("filter")
        properties = params.get("properties") or []
        result = []
        for song in self.songs:
            if rule and not self.matches(song, rule):
                continue
            item = {"songid": song["songid"], "label": song.get("label", "")}
            for prop in properties:
                if prop in song:
                    item[prop] = song[prop]
            result.append(item)
        return {"songs": result, "limits": {"start": 0, "end": len(result), "total": len(result)}}

    def get_song_details(self, params):
        for song in self.songs:
            if song["songid"] == params.get("songid"):
                details = {"songid": song["songid"], "label": song.get("label", "")}
                for prop in params.get("properties") or []:
                    if prop in song:
                        details[prop] = song[prop]
                return {"songdetails": details}
        raise JsonRpcError("Invalid params: songid not found")


class PlayerState:
    def __init__(self):
        self.playing = False
        self.position = -1
        self.file = ""
        self.time = 0.0
        self.tag = None
        self.calls = []


class KodiState:
    def __init__(self):
        self.root = ""
        self.setting_defaults = read_setting_defaults()
        self.reset()

    def reset(self):
        self.cleanup()
        self.root = tempfile.mkdtemp(prefix="musicip-kodi-")
        self.settings = dict(self.setting_defaults)
        self.addon_info = {
            "id": ADDON_ID,
            "name": "MusicIP",
            "version": read_addon_version(),
            "profile": PROFILE_URL,
            "path": ADDON_DIR,
        }
        self.settings_opened = 0
        self.logs = []
        self.builtins = []
        self.info_labels = {}
        self.window_id = 10000
        self.notifications = []
        self.dialog_calls = []
        self.dialog_responses = {}
        self.directory_items = []
        self.directory_batches = []  # sizes of addDirectoryItems calls
        self.conditions = {}  # xbmc.getCondVisibility answers, e.g. {"Container.IsUpdating": True}
        self.directory_calls = []
        self.ended = []
        self.resolved = []
        self.library = FakeLibrary(self)
        self.library_properties = {}
        self.kodi_settings = {}
        self.jsonrpc_calls = []
        self.jsonrpc_failures = {}
        self.media_files = set()
        self.media_entries = {}  # media_key -> (original path, is_folder), for listdir()
        self.playlist = []
        self.windows = []  # WindowDialogs shown with doModal()
        self.player = PlayerState()
        self.sleeps = 0
        self.abort_after_waits = 1
        self.waits = 0
        # Music sources as Kodi reports them; by default the drives used in tests, all present.
        self.listed = []
        self.music_sources = []
        for drive in ("D:\\", "E:\\", "F:\\"):
            self.add_music_source(drive)

    def cleanup(self):
        if self.root:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = ""

    # --- paths -------------------------------------------------------------------------
    def translate_path(self, path):
        path = str(path or "")
        if path.startswith("special://profile"):
            rest = path[len("special://profile"):].lstrip("/")
            translated = os.path.join(self.root, "profile", *[part for part in rest.split("/") if part])
            return translated + os.sep if path.endswith("/") else translated
        return path

    def profile_dir(self):
        return self.translate_path(PROFILE_URL)

    def is_local(self, path):
        try:
            return os.path.abspath(str(path)).startswith(os.path.abspath(self.root))
        except Exception:
            return False

    def add_media(self, path):
        """A music file that exists on the (fake) disk."""
        self.media_files.add(media_key(path))
        self.media_entries[media_key(path)] = (path, False)

    def add_folder(self, path):
        """A folder that exists on the (fake) disk, even if it holds no files."""
        self.media_files.add(media_key(path))
        self.media_entries[media_key(path)] = (path, True)

    def remove_media(self, path):
        self.media_files.discard(media_key(path))
        self.media_entries.pop(media_key(path), None)

    def listdir(self, path):
        """(folders, files) directly inside path, derived from the files and folders added."""
        base = [part.casefold() for part in path_parts(path)]
        folders, files = set(), set()
        for original, is_folder in self.media_entries.values():
            parts = path_parts(original)
            if len(parts) <= len(base) or [part.casefold() for part in parts[:len(base)]] != base:
                continue
            if len(parts) == len(base) + 1 and not is_folder:
                files.add(parts[-1])
            else:
                folders.add(parts[len(base)])
        self.listed.append(path)
        return sorted(folders), sorted(files)

    # --- dialogs ------------------------------------------------------------------------
    def respond(self, method, *responses):
        self.dialog_responses.setdefault(method, []).extend(responses)

    def dialogs(self, method):
        return [call for call in self.dialog_calls if call[0] == method]

    # --- logs / notifications ------------------------------------------------------------
    def log_text(self):
        return "\n".join(message for message, _level in self.logs)

    def notification_messages(self):
        return [message for _heading, message, _icon in self.notifications]

    # --- player --------------------------------------------------------------------------
    def play_file(self, path, **tag_values):
        """Simulate Kodi playing a single file (e.g. started from the library)."""
        tag_values.setdefault("url", path)
        self.player.playing = True
        self.player.position = -1
        self.player.file = path
        self.player.time = 0.0
        self.player.tag = InfoTagMusic(**tag_values)

    def playlist_files(self):
        return [url for url, _item in self.playlist]

    def go_to(self, position):
        if not 0 <= position < len(self.playlist):
            raise JsonRpcError(f"Invalid playlist position {position}")
        url, item = self.playlist[position]
        self.player.playing = True
        self.player.position = position
        self.player.file = url
        try:
            self.player.time = float(item.getProperty("StartOffset") or 0) if item is not None else 0.0
        except ValueError:
            self.player.time = 0.0
        tag = item.getMusicInfoTag() if item is not None else InfoTagMusic()
        self.player.tag = InfoTagMusic(**dict(tag.values, url=url))

    # --- JSON-RPC -----------------------------------------------------------------------
    def add_music_source(self, path, label="", present=True):
        self.music_sources.append({"file": path, "label": label or path})
        if present:
            self.add_folder(path)

    def fail_jsonrpc(self, method, times=1, message="Invalid params"):
        self.jsonrpc_failures.setdefault(method, []).extend([message] * times)

    def jsonrpc_methods(self):
        return [call["method"] for call in self.jsonrpc_calls]

    def execute_jsonrpc(self, raw):
        request = json.loads(raw)
        method = request["method"]
        params = request.get("params") or {}
        self.jsonrpc_calls.append({"method": method, "params": params})

        failures = self.jsonrpc_failures.get(method)
        if failures:
            message = failures.pop(0)
            return json.dumps({"id": request.get("id"), "jsonrpc": "2.0", "error": {"code": -32602, "message": message}})

        try:
            result = self.dispatch(method, params)
        except JsonRpcError as exc:
            return json.dumps({"id": request.get("id"), "jsonrpc": "2.0", "error": {"code": -32602, "message": str(exc)}})
        return json.dumps({"id": request.get("id"), "jsonrpc": "2.0", "result": result})

    def dispatch(self, method, params):
        if method == "AudioLibrary.GetSongs":
            return self.library.get_songs(params)
        if method == "AudioLibrary.GetSongDetails":
            return self.library.get_song_details(params)
        if method == "AudioLibrary.GetProperties":
            return {key: self.library_properties.get(key, "") for key in params.get("properties") or []}
        if method in ("AudioLibrary.Scan", "AudioLibrary.Clean"):
            return "OK"
        if method == "Files.GetSources":
            if params.get("media") != "music":
                return {"sources": []}
            return {"sources": [dict(source) for source in self.music_sources]}
        if method == "Settings.GetSettingValue":
            setting = params.get("setting")
            if setting not in self.kodi_settings:
                raise JsonRpcError(f"Invalid setting {setting!r}")
            return {"value": self.kodi_settings[setting]}
        if method == "Player.GetProperties":
            if not self.player.playing:
                raise JsonRpcError("No active player")
            return {"position": self.player.position}
        if method == "Player.GoTo":
            self.go_to(int(params["to"]))
            return "OK"
        if method == "Player.Seek":
            value = params.get("value") or {}
            if "time" in value:
                t = value["time"]
                self.player.time = float(t.get("hours", 0) * 3600 + t.get("minutes", 0) * 60 + t.get("seconds", 0))
            return {"time": value.get("time", {})}
        if method == "Playlist.GetItems":
            return {"items": [{"file": url, "type": "song"} for url, _item in self.playlist]}
        if method == "Playlist.Remove":
            position = int(params["position"])
            if position == self.player.position or not 0 <= position < len(self.playlist):
                raise JsonRpcError("Cannot remove playlist item")
            self.playlist.pop(position)
            if position < self.player.position:
                self.player.position -= 1
            return "OK"
        raise JsonRpcError(f"Method not found: {method}")


kodi = KodiState()
atexit.register(kodi.cleanup)


# --- xbmc ---------------------------------------------------------------------------------

class Player:
    def __init__(self, *args, **kwargs):
        pass

    def isPlayingAudio(self):
        return kodi.player.playing

    def isPlaying(self):
        return kodi.player.playing

    def getMusicInfoTag(self):
        if not kodi.player.playing:
            raise RuntimeError("Kodi is not playing any media file")
        return kodi.player.tag or InfoTagMusic(url=kodi.player.file)

    def getPlayingFile(self):
        if not kodi.player.playing:
            raise RuntimeError("Kodi is not playing any file")
        return kodi.player.file

    def getTime(self):
        if not kodi.player.playing:
            raise RuntimeError("Kodi is not playing any media file")
        return kodi.player.time

    def seekTime(self, seconds):
        kodi.player.calls.append(("seekTime", seconds))
        kodi.player.time = float(seconds)

    def play(self, item=None, listitem=None, windowed=False, startpos=-1):
        kodi.player.calls.append(("play", item))
        if isinstance(item, PlayList):
            if kodi.playlist:
                kodi.go_to(max(0, startpos))
        elif isinstance(item, str):
            kodi.play_file(item)

    def stop(self):
        kodi.player.calls.append(("stop", None))
        kodi.player.playing = False
        kodi.player.position = -1
        kodi.player.file = ""


class PlayList:
    def __init__(self, playlist_id):
        self.playlist_id = playlist_id

    def clear(self):
        kodi.playlist.clear()

    def add(self, url, listitem=None, index=-1):
        entry = (url, listitem)
        if index < 0:
            kodi.playlist.append(entry)
        else:
            kodi.playlist.insert(index, entry)

    def size(self):
        return len(kodi.playlist)

    def __len__(self):
        return len(kodi.playlist)

    def getposition(self):
        return kodi.player.position


class Monitor:
    def abortRequested(self):
        return kodi.waits >= kodi.abort_after_waits

    def waitForAbort(self, timeout=0):
        kodi.waits += 1
        return kodi.waits >= kodi.abort_after_waits


def _xbmc_log(message, level=LOGDEBUG):
    kodi.logs.append((message, level))


def _executebuiltin(command, wait=False):
    kodi.builtins.append(command)


def _getInfoLabel(label):
    return kodi.info_labels.get(label, "")


def _sleep(milliseconds):
    kodi.sleeps += 1


# --- xbmcaddon ----------------------------------------------------------------------------

class Addon:
    def __init__(self, id=None):
        self.id = id or ADDON_ID

    def getSetting(self, key):
        return str(kodi.settings.get(key, ""))

    def setSetting(self, key, value):
        kodi.settings[key] = str(value)

    def getSettingBool(self, key):
        return self.getSetting(key).lower() == "true"

    def getSettingInt(self, key):
        return int(self.getSetting(key) or 0)

    def getAddonInfo(self, key):
        return kodi.addon_info.get(key, "")

    def openSettings(self):
        kodi.settings_opened += 1


# --- xbmcgui ------------------------------------------------------------------------------

class Dialog:
    def _respond(self, method, default, *args, **kwargs):
        kodi.dialog_calls.append((method, args, kwargs))
        queue = kodi.dialog_responses.get(method)
        if queue:
            response = queue.pop(0)
            if isinstance(response, BaseException):
                raise response
            if callable(response):
                return response(*args, **kwargs)
            return response
        return default

    def select(self, heading, list, autoclose=0, preselect=-1, useDetails=False):
        return self._respond("select", -1, heading, list)

    def ok(self, heading, message):
        return self._respond("ok", True, heading, message)

    def yesno(self, heading, message, *args, **kwargs):
        return self._respond("yesno", False, heading, message)

    def textviewer(self, heading, text, usemono=False):
        return self._respond("textviewer", None, heading, text)

    def numeric(self, type, heading, defaultt="", bHiddenInput=False):
        # Kodi returns the default value when the dialog is cancelled.
        return self._respond("numeric", defaultt, type, heading, defaultt)

    def input(self, heading, defaultt="", type=0, option=0, autoclose=0):
        # Kodi returns an empty string when the dialog is cancelled.
        return self._respond("input", "", heading, defaultt)

    def notification(self, heading, message, icon=NOTIFICATION_INFO, time=5000, sound=True):
        kodi.notifications.append((heading, message, icon))


class DialogProgressBG:
    """Records create/update/close as dialog calls named progress.*."""

    def create(self, heading, message=""):
        kodi.dialog_calls.append(("progress.create", (heading, message), {}))

    def update(self, percent=0, heading=None, message=None):
        kodi.dialog_calls.append(("progress.update", (percent, heading, message), {}))

    def close(self):
        kodi.dialog_calls.append(("progress.close", (), {}))


class ControlImage:
    def __init__(self, x, y, width, height, filename, aspectRatio=0, colorDiffuse=None):
        self.position, self.filename = (x, y, width, height), filename


class ControlLabel:
    def __init__(self, x, y, width, height, label, font=None, textColor=None, disabledColor=None, alignment=0,
                 hasPath=False, angle=0):
        self.position, self.label, self.textColor, self.alignment = (x, y, width, height), label, textColor, alignment

    def getLabel(self):
        return self.label


class WindowDialog:
    """Records its controls; doModal() returns at once (as if closed) and is recorded in kodi.windows."""

    def __init__(self):
        self.controls = []

    def addControl(self, control):
        self.controls.append(control)

    def doModal(self):
        kodi.windows.append(self)

    def close(self):
        pass

    def labels(self):
        return [control.label for control in self.controls if isinstance(control, ControlLabel)]


class Keyboard:
    """Kodi's keyboard dialog. A queued "keyboard" response is the confirmed text; None (or no response) means
    the dialog was cancelled."""

    def __init__(self, line="", heading="", hidden=False):
        self.line, self.heading = line, heading
        self.text, self.confirmed = line, False

    def doModal(self, autoclose=0):
        kodi.dialog_calls.append(("keyboard", (self.heading, self.line), {}))
        queue = kodi.dialog_responses.get("keyboard")
        response = queue.pop(0) if queue else None
        self.confirmed = response is not None
        if response is not None:
            self.text = response

    def isConfirmed(self):
        return self.confirmed

    def getText(self):
        return self.text


def _getCurrentWindowId():
    return kodi.window_id


# --- xbmcplugin ---------------------------------------------------------------------------

def _addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
    kodi.directory_items.append((url, listitem, isFolder))
    return True


def _addDirectoryItems(handle, items, totalItems=0):
    kodi.directory_batches.append(len(items))
    for url, listitem, is_folder in items:
        kodi.directory_items.append((url, listitem, is_folder))
    return True


def _endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    kodi.ended.append({"succeeded": succeeded, "updateListing": updateListing, "cacheToDisc": cacheToDisc})


def _setResolvedUrl(handle, succeeded, listitem):
    kodi.resolved.append((succeeded, listitem))


def _record(name):
    def call(handle, *args, **kwargs):
        kodi.directory_calls.append((name,) + args)
    return call


# --- xbmcvfs ------------------------------------------------------------------------------

class File:
    def __init__(self, path, mode="r"):
        if kodi.is_local(path):
            if "w" in mode:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            self.handle = open(path, "w" if "w" in mode else "r", encoding="utf-8")
        else:
            raise OSError(f"Fake Kodi cannot open non-profile path {path!r}")

    def read(self, *args):
        return self.handle.read()

    def write(self, data):
        self.handle.write(data)
        return True

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _exists(path):
    if kodi.is_local(path):
        return os.path.exists(path)
    return media_key(path) in kodi.media_files


def _listdir(path):
    if kodi.is_local(path):
        entries = list(os.scandir(path))
        return [e.name for e in entries if e.is_dir()], [e.name for e in entries if not e.is_dir()]
    return kodi.listdir(path)


def _mkdirs(path):
    os.makedirs(path, exist_ok=True)
    return True


def _delete(path):
    if kodi.is_local(path) and os.path.isfile(path):
        os.remove(path)
        return True
    return False


def install():
    if "xbmc" in sys.modules and getattr(sys.modules["xbmc"], "FAKE_KODI", False):
        return

    xbmc = types.ModuleType("xbmc")
    xbmc.FAKE_KODI = True
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR, xbmc.LOGFATAL = (
        LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL,
    )
    xbmc.PLAYLIST_MUSIC, xbmc.PLAYLIST_VIDEO = PLAYLIST_MUSIC, PLAYLIST_VIDEO
    xbmc.Player, xbmc.PlayList, xbmc.Monitor, xbmc.InfoTagMusic = Player, PlayList, Monitor, InfoTagMusic
    xbmc.Keyboard = Keyboard
    xbmc.log = _xbmc_log
    xbmc.executebuiltin = _executebuiltin
    xbmc.executeJSONRPC = kodi_execute_jsonrpc
    xbmc.getInfoLabel = _getInfoLabel
    xbmc.getCondVisibility = lambda condition: bool(kodi.conditions.get(condition))
    xbmc.sleep = _sleep

    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = Addon

    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.ListItem, xbmcgui.Dialog, xbmcgui.DialogProgressBG = ListItem, Dialog, DialogProgressBG
    xbmcgui.WindowDialog, xbmcgui.ControlImage, xbmcgui.ControlLabel = WindowDialog, ControlImage, ControlLabel
    xbmcgui.NOTIFICATION_INFO = NOTIFICATION_INFO
    xbmcgui.NOTIFICATION_WARNING = NOTIFICATION_WARNING
    xbmcgui.NOTIFICATION_ERROR = NOTIFICATION_ERROR
    xbmcgui.getCurrentWindowId = _getCurrentWindowId

    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.SORT_METHOD_UNSORTED = 0
    xbmcplugin.addDirectoryItem = _addDirectoryItem
    xbmcplugin.addDirectoryItems = _addDirectoryItems
    xbmcplugin.endOfDirectory = _endOfDirectory
    xbmcplugin.setResolvedUrl = _setResolvedUrl
    xbmcplugin.setPluginCategory = _record("setPluginCategory")
    xbmcplugin.setContent = _record("setContent")
    xbmcplugin.addSortMethod = _record("addSortMethod")

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.File = File
    xbmcvfs.translatePath = lambda path: kodi.translate_path(path)
    xbmcvfs.exists = _exists
    xbmcvfs.mkdirs = _mkdirs
    xbmcvfs.delete = _delete
    xbmcvfs.listdir = _listdir

    for module in (xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs):
        sys.modules[module.__name__] = module


def kodi_execute_jsonrpc(raw):
    return kodi.execute_jsonrpc(raw)
