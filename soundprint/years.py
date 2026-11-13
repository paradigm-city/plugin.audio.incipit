"""A year for every song in Kodi's music library, so a search can stay within a time (the Epoch perspective,
docs/concept_epoch.md).

The year is the song's first release as far as the library tells (F51): for a song on a normal album, the album's
original date (Kodi keeps it where the tags have one); for a song on a compilation dated song by song (its songs carry
different dates: the listener's originals, from MusicBrainz through Picard), its own date; else the year of the same
song (artist and title) on the artist's own album or on such a compilation, the earliest. A compilation song without
one has no year, only the earliest
compilation that holds it: the song came out then or earlier ("latest"). Only a compilation whose date fits its
songs bounds them (trusted_compilations): the tags of some date a series of today in the seventies. And a song
whose sound print is all but the same as that of a dated song by the same artist is that recording (another title's
spelling, another edition): it takes that song's year (same_recordings).

Within a window: a song whose year lies in it is certain. A song without a year is uncertain if it may lie in it (its
latest is in the window or after it, or unknown) and its sound hints at that time (era_hints: the years of its
nearest dated songs by sound; a production's sound tells its time, if roughly); the search takes such songs, but only up to a share of a mix, and
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
CACHE_VERSION = 5  # 5: the hints as plain tuples (F54)
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
    track_dates: Dict[int, Set[int]] = {}  # compilation -> the years its songs' own dates name
    songs = []
    for path, artist, title, album, flag, album_artist, album_original, album_release, original, release in rows:
        year = year_of(album_original, album_release, original, release)
        track_year = year_of(original, release)
        compilation = is_compilation(flag, album_artist or "", int(artists.get(album) or 0))
        song = (artist_key(artist or ""), (title or "").strip().casefold())
        songs.append((path, song, year, compilation, album, track_year))
        if compilation and track_year:
            track_dates.setdefault(album, set()).add(track_year)
        if year and not compilation and artist_key(album_artist or "") == song[0]:
            own[song] = min(own.get(song) or year, year)
            first_album[song[0]] = min(first_album.get(song[0]) or year, year)
    # A compilation whose songs carry dates of their own, several different ones, was dated song by song (the
    # listener takes the original dates from MusicBrainz through Picard): those are the songs' years. Kodi dates such
    # an album by one of them ("Welcome To Rock Heaven Vol. 32": 1978, with Dream Theater's 1992 and Black
    # Sabbath's 1970 inside). A compilation with one date for all is dated by its release: a latest, if trusted.
    by_song = {album for album, found in track_dates.items() if len(found) > 1}
    dated_tracks: Dict[tuple, int] = {}  # (artist, title) -> earliest date it carries on such a compilation
    for _path, song, _year, compilation, album, track_year in songs:
        if compilation and album in by_song and track_year:
            dated_tracks[song] = min(dated_tracks.get(song) or track_year, track_year)
    dated = trusted_compilations([entry[:5] for entry in songs if not (entry[3] and entry[4] in by_song)], own,
                                 first_album)
    on_compilations: Dict[tuple, int] = {}  # (artist, title) -> the earliest trusted compilation holding it
    for _path, song, year, compilation, album, _track_year in songs:
        if compilation and year and album in dated:
            on_compilations[song] = min(on_compilations.get(song) or year, year)
    years: Years = {}
    for path, song, year, compilation, album, track_year in songs:
        if not compilation:
            years[file_key(path)] = (year, 0)
        elif song in own or song in dated_tracks:
            years[file_key(path)] = (min(own.get(song, 9999), dated_tracks.get(song, 9999)), 0)
        else:
            years[file_key(path)] = (0, on_compilations.get(song, 0))
    if vectors is not None:
        same_recordings(years, [(file_key(entry[0]), entry[1][0]) for entry in songs], vectors, file_key)
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


# file key -> the years of the nearest dated songs by sound: plain ints, as everything kept in the cache, which Kodi's
# own Python reads too (main.sound_engine_year), where there is no numpy (F54)
Hints = Dict[str, Tuple[int, ...]]
ERA_NEIGHBOURS = 20  # dated songs by other artists, nearest by sound, that hint at an undated song's time
ERA_SHARE = 0.2  # of them within the window (widened by ERA_TOLERANCE), and the undated song may be of that time
ERA_TOLERANCE = 2
# Measured on 3,000 dated songs of the real library (2026-11-10), each against its 20 nearest by other artists: the
# median of their years misses the song's by 5 years (within 5 years for 52%, but pulled towards the library's
# middle: the sixties guessed 16 years later, the 2020s 11 earlier). As a filter for a window it is a hint, not a
# date: for 1975-1979 (5% of songs), "a fifth of the neighbours within the window +-2" keeps 77% of the songs of those
# years and passes 27% of all, three times as many of those years as chance; for 1989-1994, 79% and 43%.


def era_hints(years: Years, artists: Dict[str, str], vectors: Vectors, file_key,
              known: Optional[Hints] = None) -> Hints:
    """For every undated song with a sound print, the years of its ERA_NEIGHBOURS nearest dated songs by other
    artists (an album's songs are each other's nearest); known: hints made before, kept for songs still undated."""
    import numpy as np

    paths, matrix = vectors
    keys = [file_key(path) for path in paths]
    dated = np.array([row for row, key in enumerate(keys) if years.get(key, (0, 0))[0]], dtype=np.int64)
    hints: Hints = {key: value for key, value in (known or {}).items() if key in years and not years[key][0]}
    wanted = [row for row, key in enumerate(keys) if key in years and not years[key][0] and key not in hints]
    if not len(dated) or not wanted:
        return hints
    dated_years = np.array([years[keys[row]][0] for row in dated], dtype=np.int16)
    dated_artists = [artists.get(keys[row], "") for row in dated]
    reference = np.asarray(matrix[dated], dtype=np.float32)
    take = min(len(dated), ERA_NEIGHBOURS * 2)
    for start in range(0, len(wanted), 512):
        rows = wanted[start:start + 512]
        similarity = np.asarray(matrix[rows], dtype=np.float32) @ reference.T
        nearest = np.argpartition(-similarity, take - 1, axis=1)[:, :take]
        for row, columns, values in zip(rows, nearest, similarity):
            columns = columns[np.argsort(-values[columns])]
            artist = artists.get(keys[row], "")
            others = [column for column in columns if not artist or dated_artists[column] != artist]
            hints[keys[row]] = tuple(int(year) for year in dated_years[others[:ERA_NEIGHBOURS]])
    return hints


def era_share(hint, first: int, last: int) -> float:
    """The share of an undated song's neighbours within first to last, widened by ERA_TOLERANCE."""
    if hint is None or not len(hint):
        return 0.0
    return sum(1 for year in hint if first - ERA_TOLERANCE <= year <= last + ERA_TOLERANCE) / len(hint)


def cached(database: str, folder: str, file_key=lambda path: path,
           vectors: Optional[Vectors] = None) -> Tuple[Years, Hints]:
    """song_years and (with vectors) era_hints, kept in folder until the database or the sound prints change; the
    hints made before are kept for songs still undated, so a change costs only the new songs' hints."""
    stamp = os.stat(database)
    marker = (CACHE_VERSION, database, stamp.st_size, stamp.st_mtime_ns, len(vectors[0]) if vectors else 0)
    cache = os.path.join(folder, CACHE_FILE)
    kept: dict = {}
    try:
        with open(cache, "rb") as handle:
            kept = pickle.load(handle)
        if kept.get("marker") == marker:
            return kept["years"], kept.get("hints") or {}
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, KeyError, TypeError):
        kept = {}
    years = song_years(database, file_key, vectors)
    hints: Hints = {}
    if vectors is not None:
        artists = song_artists(database, file_key)
        same_version = isinstance(kept.get("marker"), tuple) and kept["marker"][:1] == (CACHE_VERSION,)
        hints = era_hints(years, artists, vectors, file_key, kept.get("hints") if same_version else None)
    try:
        with open(cache + ".tmp", "wb") as handle:
            pickle.dump({"marker": marker, "years": years, "hints": hints}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(cache + ".tmp", cache)
    except OSError:
        pass
    return years, hints


def cached_years(database: str, folder: str, file_key=lambda path: path, vectors: Optional[Vectors] = None) -> Years:
    return cached(database, folder, file_key, vectors)[0]


def song_artists(database: str, file_key=lambda path: path) -> Dict[str, str]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return {file_key(path): artist_key(artist or "") for path, artist in connection.execute(
            "SELECT path.strPath || song.strFileName, song.strArtistDisp FROM song "
            "JOIN path ON path.idPath = song.idPath")}
    finally:
        connection.close()


def load(folder: str) -> Optional[Years]:
    """The years last kept in folder, however old; None without, or when they can't be read here (a cache of an older
    version may hold numpy's arrays, which Kodi's Python can't load: F54)."""
    try:
        with open(os.path.join(folder, CACHE_FILE), "rb") as handle:
            return pickle.load(handle)["years"]
    except Exception:
        return None


def certain(entry: Tuple[int, int], first: int, last: int) -> bool:
    return bool(entry[0]) and first <= entry[0] <= last


def uncertain(entry: Tuple[int, int], first: int) -> bool:
    """No year, and it may lie in a window from first on: its latest is first or later, or unknown."""
    year, latest = entry
    return not year and (not latest or latest >= first)


def within(years: Years, first: int, last: int, keys: Optional[Iterable[str]] = None,
           minimum: int = MIN_SONGS, hints: Optional[Hints] = None) -> Tuple[Set[str], Set[str], Tuple[int, int]]:
    """The songs (of keys, default all) certainly within first to last, those that may be, and the window used:
    widened a year on each side at a time (at most MAX_WIDEN) until it holds minimum certain songs. With hints, an
    undated song may be of the window only if its sound says so too (era_share at least ERA_SHARE)."""
    pool = {key: years[key] for key in (keys if keys is not None else years) if key in years}
    for widen in range(MAX_WIDEN + 1):
        low, high = first - widen, last + widen
        found = {key for key, entry in pool.items() if certain(entry, low, high)}
        if len(found) >= minimum:
            break
    maybe = {key for key, entry in pool.items() if uncertain(entry, low)}
    if hints is not None:
        maybe = {key for key in maybe if era_share(hints.get(key), low, high) >= ERA_SHARE}
    return found, maybe, (low, high)


def parse_window(text: str) -> Tuple[int, int]:
    """"1975-1979" (or "1977") -> (1975, 1979)."""
    parts = [int(part) for part in text.replace("–", "-").split("-") if part.strip()]
    if not parts or len(parts) > 2:
        raise ValueError(f"not a span of years: {text!r}")
    return min(parts), max(parts)
