"""A year for every song in Kodi's music library, so a search can stay within a time (the Epoch perspective,
docs/concept_epoch.md).

The year is the song's first release as far as the library tells (F51): for a song on a normal album, the album's
original date (Kodi keeps it where the tags have one); for a song on a compilation, the year of the same song (artist
and title) on the artist's own album, the earliest. A compilation song without one has no year, only the earliest
compilation that holds it: the song came out then or earlier ("latest"). Only a compilation whose date fits its
songs bounds them (trusted_compilations): the tags of some date a series of today in the seventies. And a song
whose sound print is all but the same as that of a dated song by the same artist is that recording (another title's
spelling, another edition): it takes that song's year (same_recordings).

Within a window: a song whose year lies in it is certain. A song without a year is uncertain if it may lie in it (its
latest is in the window or after it, or unknown); the search takes such songs, but only up to a share of a mix, and
the AI judges them as it can (Epoch's rule: a track it can't date is at most borderline). A window that holds too few
certain songs widens a year on each side at a time.

Kodi's music database is opened read-only, as songs.py does. The years are kept in the data folder and made again
when the database or the sound prints change.
"""

from __future__ import annotations

import os
import pickle
import sqlite3
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from mixassist.cache import artist_key, is_compilation

Years = Dict[str, Tuple[int, int]]  # file key -> (year, latest): (1977, 0), or (0, 1994) for "compilation of 1994"
Vectors = Tuple[Sequence[str], object]  # (paths, their sound prints: a numpy matrix, one normalised row each)
CACHE_FILE = "years.pickle"
CACHE_VERSION = 3
MIN_SONGS = 1000  # a window is widened until it holds this many certain songs
MAX_WIDEN = 10  # years on each side at most
UNCERTAIN_SHARE = 0.25  # of a mix, at most, songs whose year is uncertain
# Two sound prints this near, by the same artist, are one recording: on the real library (400 undated songs, each
# against the nearest dated one) the same recordings were 0.9939 to 0.9997 apart (KaS Product "One of a Kind" and
# "One of the Kind"; The Danse Society "2000 Light Years" and "2,000 Light Years"), two songs of one band 0.9912
# (Nickelback) and less.
SAME_RECORDING = 0.993

SONGS = ("SELECT path.strPath || song.strFileName, song.strArtistDisp, song.strTitle, song.idAlbum, "
         "album.bCompilation, album.strArtistDisp, album.strOrigReleaseDate, album.strReleaseDate, "
         "song.strOrigReleaseDate, song.strReleaseDate "
         "FROM song JOIN path ON path.idPath = song.idPath JOIN album ON album.idAlbum = song.idAlbum")
ARTISTS_PER_ALBUM = "SELECT idAlbum, COUNT(DISTINCT strArtistDisp) FROM song GROUP BY idAlbum"


def path_key(path: str) -> str:
    """A song's path as the sound engine compares files (soundprint.neighbours.file_key), without numpy: Windows'
    paths ignore case."""
    key = (path or "").replace("\\", "/").strip()
    return key.casefold() if os.name == "nt" else key


def year_of(*dates: Optional[str]) -> int:
    """The year of the first date that has one ("1977-08-04", "1977"); 0 without."""
    for date in dates:
        text = (date or "").strip()[:4]
        if text.isdigit() and 1000 < int(text) < 2100:
            return int(text)
    return 0


def song_years(database: str, file_key=lambda path: path, vectors: Optional[Vectors] = None) -> Years:
    """Every song's (year, latest), by file_key(path); with vectors, undated songs are matched by sound too."""
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
    if vectors is not None:
        same_recordings(years, [(file_key(path), song[0]) for path, song, _year, _compilation, _album in songs],
                        vectors, file_key)
    return years


LATE_SHARE = 1 / 3  # of a compilation's songs whose artists are known: more this late, and its date isn't trusted
SINGLES_BEFORE_ALBUMS = 2  # years an artist's first songs may come before the first album


def trusted_compilations(songs, own: Dict[tuple, int], first_album: Dict[str, int]) -> Set[int]:
    """The compilations whose date can bound their songs: a series of today dated 1978 by its tags ("Welcome To Rock
    Heaven Vol. 32", with Dream Theater and Volbeat) can't. Of a compilation's songs whose artists the library knows,
    a song is late when it is on the artist's own album only years after the compilation's date, or its artist's
    first album came more than two years after it (an artist's own albums can be a later best-of, so one late song
    proves nothing, nor does a later first album: the library may lack the early ones); with more than a third of
    them late, the compilation isn't trusted."""
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


def same_recordings(years: Years, songs: List[Tuple[str, str]], vectors: Vectors, file_key) -> int:
    """Give an undated song the year of a dated song by the same artist whose sound print is all but the same
    (SAME_RECORDING); songs: (file key, artist key). Returns how many were dated so."""
    import numpy as np

    paths, matrix = vectors
    rows = {file_key(path): row for row, path in enumerate(paths)}
    dated: Dict[str, List[Tuple[int, int]]] = {}
    undated: Dict[str, List[Tuple[str, int]]] = {}
    for key, artist in songs:
        if key not in rows or not artist:
            continue
        if years[key][0]:
            dated.setdefault(artist, []).append((rows[key], years[key][0]))
        else:
            undated.setdefault(artist, []).append((key, rows[key]))
    found = 0
    for artist, wanted in undated.items():
        known = dated.get(artist)
        if not known:
            continue
        similarity = (np.asarray(matrix[[row for _key, row in wanted]], dtype=np.float32)
                      @ np.asarray(matrix[[row for row, _year in known]], dtype=np.float32).T)
        best = similarity.argmax(axis=1)
        for (key, _row), column, values in zip(wanted, best, similarity):
            if values[column] >= SAME_RECORDING:
                years[key] = (known[column][1], 0)
                found += 1
    return found


def cached_years(database: str, folder: str, file_key=lambda path: path, vectors: Optional[Vectors] = None) -> Years:
    """song_years, kept in folder until the database or the sound prints change."""
    stamp = os.stat(database)
    marker = (CACHE_VERSION, database, stamp.st_size, stamp.st_mtime_ns, len(vectors[0]) if vectors else 0)
    cache = os.path.join(folder, CACHE_FILE)
    try:
        with open(cache, "rb") as handle:
            kept = pickle.load(handle)
        if kept.get("marker") == marker:
            return kept["years"]
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, KeyError, TypeError):
        pass
    years = song_years(database, file_key, vectors)
    try:
        with open(cache + ".tmp", "wb") as handle:
            pickle.dump({"marker": marker, "years": years}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(cache + ".tmp", cache)
    except OSError:
        pass
    return years


def load(folder: str) -> Optional[Years]:
    """The years last kept in folder, however old; None without."""
    try:
        with open(os.path.join(folder, CACHE_FILE), "rb") as handle:
            return pickle.load(handle)["years"]
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, KeyError, TypeError, ValueError):
        return None


def certain(entry: Tuple[int, int], first: int, last: int) -> bool:
    return bool(entry[0]) and first <= entry[0] <= last


def uncertain(entry: Tuple[int, int], first: int) -> bool:
    """No year, and it may lie in a window from first on: its latest is first or later, or unknown."""
    year, latest = entry
    return not year and (not latest or latest >= first)


def within(years: Years, first: int, last: int, keys: Optional[Iterable[str]] = None,
           minimum: int = MIN_SONGS) -> Tuple[Set[str], Set[str], Tuple[int, int]]:
    """The songs (of keys, default all) certainly within first to last, those that may be, and the window used:
    widened a year on each side at a time (at most MAX_WIDEN) until it holds minimum certain songs."""
    pool = {key: years[key] for key in (keys if keys is not None else years) if key in years}
    for widen in range(MAX_WIDEN + 1):
        low, high = first - widen, last + widen
        found = {key for key, entry in pool.items() if certain(entry, low, high)}
        if len(found) >= minimum:
            break
    return found, {key for key, entry in pool.items() if uncertain(entry, low)}, (low, high)


def parse_window(text: str) -> Tuple[int, int]:
    """"1975-1979" (or "1977") -> (1975, 1979)."""
    parts = [int(part) for part in text.replace("–", "-").split("-") if part.strip()]
    if not parts or len(parts) > 2:
        raise ValueError(f"not a span of years: {text!r}")
    return min(parts), max(parts)
