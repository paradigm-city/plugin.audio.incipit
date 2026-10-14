"""From a mix's file paths to rating units, through Kodi's JSON-RPC (passed in as a callable).

A normal album is one unit (all its tracks share the rating); a track from a compilation is its own unit.
Tracks Kodi does not know fall back to the mix's recorded metadata or to the file name.
"""

from __future__ import annotations

import ntpath
import os
import re
from typing import Callable, Dict, List, Optional, Sequence

from mixassist.cache import album_key, is_compilation, track_key

JsonRpc = Callable[[str, dict], dict]

SONG_PROPERTIES = ["title", "displayartist", "album", "albumid", "year", "genre", "file", "musicbrainztrackid", "track"]
ALBUM_PROPERTIES = ["title", "displayartist", "year", "genre", "musicbrainzreleasegroupid", "compilation"]
MAX_TRACK_TITLES = 15


def split_path(path: str):
    """Kodi stores Windows paths with backslashes; use ntpath for those, posixpath otherwise."""
    module = ntpath if "\\" in path or re.match(r"^[A-Za-z]:", path) else os.path
    return module.dirname(path), module.basename(path)


def same_file(first: str, second: str) -> bool:
    return (first or "").replace("\\", "/").lower() == (second or "").replace("\\", "/").lower()


def first_text(value) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(part) for part in value if part)
    return str(value or "")


def guess_from_filename(path: str):
    """(artist, title) from a file name like 'ARTIST - Title.mp3' or '03 Title.mp3'."""
    stem = os.path.splitext(split_path(path)[1])[0]
    stem = re.sub(r"^\d+[\s._-]+", "", stem)
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


class Library:
    """Looks songs and albums up once per mix and remembers them."""

    def __init__(self, jsonrpc: JsonRpc):
        self.jsonrpc = jsonrpc
        self.albums: Dict[int, dict] = {}

    def song(self, path: str) -> Optional[dict]:
        _, filename = split_path(path)
        try:
            result = self.jsonrpc("AudioLibrary.GetSongs", {
                "properties": SONG_PROPERTIES,
                "filter": {"field": "filename", "operator": "is", "value": filename},
            })
        except Exception:
            return None
        return next((song for song in result.get("songs") or [] if same_file(song.get("file"), path)), None)

    def album(self, album_id: int) -> dict:
        if album_id in self.albums:
            return self.albums[album_id]
        album: dict = {"albumid": album_id, "title": "", "displayartist": "", "year": 0, "genre": [],
                       "musicbrainzreleasegroupid": "", "compilation": False, "songs": []}
        try:
            album.update(self.jsonrpc("AudioLibrary.GetAlbumDetails",
                                      {"albumid": album_id, "properties": ALBUM_PROPERTIES}).get("albumdetails") or {})
            songs = self.jsonrpc("AudioLibrary.GetSongs", {
                "properties": ["title", "displayartist", "track"], "filter": {"albumid": album_id},
            }).get("songs") or []
            album["songs"] = sorted(songs, key=lambda song: (song.get("track") or 0, song.get("title") or ""))
        except Exception:
            pass
        self.albums[album_id] = album
        return album


def unit_for_song(song: dict, album: dict) -> dict:
    """The rating unit of a library song: its album, or the track itself on a compilation."""
    artists = {song_entry.get("displayartist") for song_entry in album["songs"] if song_entry.get("displayartist")}
    compilation = is_compilation(album.get("compilation"), album.get("displayartist", ""), len(artists))
    genres = first_text(song.get("genre")) or first_text(album.get("genre"))
    year = int(song.get("year") or album.get("year") or 0)
    if compilation:
        return {
            "kind": "track",
            "key": track_key(song.get("displayartist", ""), song.get("title", ""), song.get("musicbrainztrackid", "")),
            "label": f"{song.get('displayartist', '')} – {song.get('title', '')}",
            "artist": song.get("displayartist", ""),
            "item": {"artist": song.get("displayartist", ""), "title": song.get("title", ""),
                     "album": album.get("title", ""), "year": year, "genres": genres},
        }
    titles: List[str] = []
    for entry in album["songs"]:
        title = entry.get("title") or ""
        if title and title not in titles:
            titles.append(title)
    return {
        "kind": "album",
        "key": album_key(album.get("displayartist", ""), album.get("title", ""),
                         album.get("musicbrainzreleasegroupid", "")),
        "label": f"{song.get('displayartist', '')} – {song.get('title', '')} ({album.get('title', '')})",
        "artist": song.get("displayartist", ""),
        "item": {"artist": album.get("displayartist", ""), "album": album.get("title", ""),
                 "year": int(album.get("year") or year), "genres": first_text(album.get("genre")) or genres,
                 "tracks": titles[:MAX_TRACK_TITLES]},
    }


def unit_for_unknown(path: str, metadata: Optional[dict] = None) -> dict:
    """A track Kodi does not know: from recorded metadata if there is any, else from its file name."""
    metadata = metadata or {}
    artist, title = metadata.get("artist", ""), metadata.get("title", "")
    if isinstance(artist, list):
        artist = ", ".join(artist)
    if not title:
        artist, title = guess_from_filename(path)
    return {
        "kind": "track",
        "key": track_key(artist, title),
        "label": f"{artist} – {title}" if artist else title,
        "artist": artist,
        "item": {"artist": artist, "title": title, "album": metadata.get("album", ""),
                 "year": int(metadata.get("year") or 0), "genres": first_text(metadata.get("genre"))},
    }


def resolve(paths: Sequence[str], jsonrpc: JsonRpc, metadata: Optional[Dict[str, dict]] = None) -> List[dict]:
    """One unit per path, in order; each carries its path."""
    library = Library(jsonrpc)
    metadata = metadata or {}
    units = []
    for path in paths:
        song = library.song(path)
        if song and song.get("albumid"):
            unit = unit_for_song(song, library.album(int(song["albumid"])))
        else:
            unit = unit_for_unknown(path, metadata.get(path.replace("\\", "/").lower()))
        unit["path"] = path
        units.append(unit)
    return units
