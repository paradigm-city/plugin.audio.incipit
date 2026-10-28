"""Which songs to analyse: the files of Kodi's music library, or a list of paths.

Kodi's music database (MyMusic<version>.db in userdata/Database) is opened read-only; Kodi may keep running. Only
files on a local or mapped drive can be read; other paths (smb://, nfs://, ...) are counted and left out.
"""

from __future__ import annotations

import glob
import os
import re
import sqlite3
from typing import Iterable, List, Sequence, Tuple


def kodi_database(userdata: str) -> str:
    """The newest MyMusic*.db in userdata/Database."""
    found = glob.glob(os.path.join(userdata, "Database", "MyMusic*.db"))
    if not found:
        raise FileNotFoundError(f"no MyMusic*.db in {os.path.join(userdata, 'Database')}")
    return max(found, key=lambda path: int(re.sub(r"\D", "", os.path.basename(path)) or 0))


def from_kodi(database: str) -> List[str]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        return [path for (path,) in connection.execute(
            "SELECT path.strPath || song.strFileName FROM song JOIN path ON path.idPath = song.idPath "
            "ORDER BY path.strPath, song.strFileName")]
    finally:
        connection.close()


def from_list(filename: str) -> List[str]:
    with open(filename, encoding="utf-8-sig") as handle:
        return [line.strip() for line in handle if line.strip()]


def local(paths: Iterable[str], folders: Sequence[str] = ()) -> Tuple[List[str], int, int]:
    """The distinct paths that are local files (inside one of folders, if given), and how many were left out as
    not local and as outside the folders."""
    prefixes = tuple(os.path.normcase(os.path.join(folder, "")) for folder in folders)
    kept, seen, remote, outside = [], set(), 0, 0
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if "://" in path:
            remote += 1
        elif prefixes and not os.path.normcase(path).startswith(prefixes):
            outside += 1
        else:
            kept.append(path)
    return kept, remote, outside
