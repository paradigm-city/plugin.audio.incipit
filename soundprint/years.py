"""A year for every song in Kodi's music library, so a search can stay within a time (the Epoch perspective,
docs/concept_epoch.md).

The year is the song's first release as far as the library tells (F51): for a song on a normal album, the album's
original date (Kodi keeps it where the tags have one); for a song on a compilation, the year of the same song (artist
and title) on the artist's own album, the earliest. A compilation song without one has no year, only the earliest
compilation that holds it: the song came out then or earlier ("latest"). Only a compilation whose date fits its
songs bounds them (trusted_compilations): the tags of some date a series of today in the seventies.

Within a window: a song whose year lies in it; a song without a year if its latest lies in it (a compilation made in
those years holds no later songs). A window that holds too few songs widens a year on each side at a time.

Kodi's music database is opened read-only, as songs.py does. The years are kept in the data folder and made again
when the database changes.
"""

from __future__ import annotations

import os
import pickle
import sqlite3
from typing import Dict, Iterable, Optional, Set, Tuple

from mixassist.cache import artist_key, is_compilation

Years = Dict[str, Tuple[int, int]]  # file key -> (year, latest): (1977, 0), or (0, 1994) for "compilation of 1994"
CACHE_FILE = "years.pickle"
CACHE_VERSION = 2
MIN_SONGS = 1000  # a window is widened until it holds this many songs
MAX_WIDEN = 10  # years on each side at most

SONGS = ("SELECT path.strPath || song.strFileName, song.strArtistDisp, song.strTitle, song.idAlbum, "
         "album.bCompilation, album.strArtistDisp, album.strOrigReleaseDate, album.strReleaseDate, "
         "song.strOrigReleaseDate, song.strReleaseDate "
         "FROM song JOIN path ON path.idPath = song.idPath JOIN album ON album.idAlbum = song.idAlbum")
ARTISTS_PER_ALBUM = "SELECT idAlbum, COUNT(DISTINCT strArtistDisp) FROM song GROUP BY idAlbum"


def year_of(*dates: Optional[str]) -> int:
    """The year of the first date that has one ("1977-08-04", "1977"); 0 without."""
    for date in dates:
        text = (date or "").strip()[:4]
        if text.isdigit() and 1000 < int(text) < 2100:
            return int(text)
    return 0


def song_years(database: str, file_key=lambda path: path) -> Years:
    """Every song's (year, latest), by file_key(path)."""
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        artists = dict(connection.execute(ARTISTS_PER_ALBUM).fetchall())
        rows = connection.execute(SONGS).fetchall()
    finally:
        connection.close()
    own: Dict[tuple, int] = {}  # (artist, title) -> earliest year on the artist's own album
    first_album: Dict[str, int] = {}  # artist -> the year of the artist's earliest own album
    songs = []
    for path, artist, title, album, flag, album_artist, album_original, album_release, original, release in rows:
        year = year_of(album_original, album_release, original, release)
        compilation = is_compilation(flag, album_artist or "", int(artists.get(album) or 0))
        song = (artist_key(artist or ""), (title or "").strip().casefold())
        songs.append((path, song, year, compilation, album))
        if year and not compilation and artist_key(album_artist or "") == song[0]:
            own[song] = min(own.get(song) or year, year)
            first_album[song[0]] = min(first_album.get(song[0]) or year, year)
    dated = trusted_compilations(songs, own, first_album)
    on_compilations: Dict[tuple, int] = {}  # (artist, title) -> the earliest trusted compilation holding it
    for _path, song, year, compilation, album in songs:
        if compilation and year and album in dated:
            on_compilations[song] = min(on_compilations.get(song) or year, year)
    years: Years = {}
    for path, song, year, compilation, _album in songs:
        if not compilation:
            years[file_key(path)] = (year, 0)
        elif song in own:
            years[file_key(path)] = (own[song], 0)
        else:
            years[file_key(path)] = (0, on_compilations.get(song, 0))
    return years


LATE_SHARE = 1 / 3  # of a compilation's songs whose artists are known: more this late, and its date isn't trusted
SINGLES_BEFORE_ALBUMS = 2  # years an artist's first songs may come before the first album


def trusted_compilations(songs, own: Dict[tuple, int], first_album: Dict[str, int]) -> Set[int]:
    """The compilations whose date can bound their songs: a series of today dated 1978 by its tags ("Welcome To Rock
    Heaven Vol. 32", with Dream Theater and Volbeat) can't. Of a compilation's songs whose artists the library knows,
    a song is late when it is on the artist's own album only years after the compilation's date, or its artist's
    first album came more than two years after it (an artist's own albums can be a later best-of, so one late song
    proves nothing, nor does a later first album: the library may lack the early ones); with more than a
    third of them late, the compilation isn't trusted."""
    late: Dict[int, int] = {}
    known: Dict[int, int] = {}
    dated: Dict[int, int] = {}
    for _path, song, year, compilation, album in songs:
        if not compilation or not year:
            continue
        dated[album] = year
        if song[0] in first_album:
            known[album] = known.get(album, 0) + 1
            if own.get(song, first_album[song[0]]) > year + SINGLES_BEFORE_ALBUMS:
                late[album] = late.get(album, 0) + 1
    return {album for album in dated if late.get(album, 0) <= LATE_SHARE * known.get(album, 0)}


def cached_years(database: str, folder: str, file_key=lambda path: path) -> Years:
    """song_years, kept in folder until the database changes."""
    stamp = os.stat(database)
    marker = (CACHE_VERSION, database, stamp.st_size, stamp.st_mtime_ns)
    cache = os.path.join(folder, CACHE_FILE)
    try:
        with open(cache, "rb") as handle:
            kept = pickle.load(handle)
        if kept.get("marker") == marker:
            return kept["years"]
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, KeyError, TypeError):
        pass
    years = song_years(database, file_key)
    try:
        with open(cache + ".tmp", "wb") as handle:
            pickle.dump({"marker": marker, "years": years}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(cache + ".tmp", cache)
    except OSError:
        pass
    return years


def inside(entry: Tuple[int, int], first: int, last: int) -> bool:
    year, latest = entry
    return first <= (year or latest) <= last if (year or latest) else False


def within(years: Years, first: int, last: int, keys: Optional[Iterable[str]] = None,
           minimum: int = MIN_SONGS) -> Tuple[Set[str], Tuple[int, int]]:
    """The songs (of keys, default all) within first to last, and the window used: widened a year on each side at a
    time (at most MAX_WIDEN) until it holds minimum songs."""
    pool = {key: years[key] for key in (keys if keys is not None else years) if key in years}
    for widen in range(MAX_WIDEN + 1):
        low, high = first - widen, last + widen
        found = {key for key, entry in pool.items() if inside(entry, low, high)}
        if len(found) >= minimum:
            break
    return found, (low, high)


def parse_window(text: str) -> Tuple[int, int]:
    """"1975-1979" (or "1977") -> (1975, 1979)."""
    parts = [int(part) for part in text.replace("–", "-").split("-") if part.strip()]
    if not parts or len(parts) > 2:
        raise ValueError(f"not a span of years: {text!r}")
    return min(parts), max(parts)

