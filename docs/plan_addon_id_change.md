# Plan: changing the add-on's ID to plugin.audio.incipit

Status: **open, not started** (prepared 2026-10-29). The add-on is called Incipit since 2026-10-29, but its ID, and
so its folder, is still `plugin.audio.musicip`. The listener wants the ID to follow the name one day. Nothing here
has been done; do it as one step, with Kodi closed for the data move.

## Why it can't be a folder rename alone

Kodi expects an add-on's folder to be named after the ID in its `addon.xml`. A new ID is, to Kodi, a new add-on:
its data folder, its settings, its entry in Kodi's add-on database, the cached artwork and any Kodi favourite or
shortcut to it belong to the old ID.

## What uses the ID (counted 2026-10-29)

| Where | Uses | What |
|---|---|---|
| `addon.xml` | 1 | `id="plugin.audio.musicip"` |
| `resources/settings.xml` | 7 | the buttons' `RunPlugin(plugin://plugin.audio.musicip/?action=...)`; the section id |
| `resources/keymaps/musicip_mix_editing.xml` and `MUSICIP_KEYMAP_CONTENT` in `main.py`, `service.py` | 24 + copies | the keyboard shortcuts' `RunPlugin(plugin://...)` |
| `main.py` | 24 | `BASE_URL`, plugin URLs, the info window's actions |
| `service.py` | 28 | plugin URLs; which screen is open (`"plugin.audio.musicip" in container_folder`, `get_visible_musicip_mix_context`) |
| `logs.py`, `context_mix.py` | 1 each | `ADDON_ID` (the log tag `[plugin.audio.musicip]`) |
| `soundprint/__main__.py` | 3 | the data folder's default `addon_data/plugin.audio.musicip/soundprint` |
| `soundprint/model.py`, `strings.po`, `README.md`, `docs/` | a few | texts |
| `tools/make_settings.py`, `.gitignore` | 4, 1 | the settings generator; an ignored path |
| `tests/` | about 40 | expected URLs, log tags, `fake_kodi`'s add-on id |

## The listener's data (798 MB in `userdata/addon_data/plugin.audio.musicip`)

- **Settings** (`settings.xml`), saved and current mixes (`mix_*.m3u`, their `.json` sidecars, `current_mix.json`),
  favourite stations (`radio_favourites.json`, artwork in `covers/`), Discovery and Radio state, the checks' ratings
  and statistics (`mixassist/ratings.db`, `usage.db`, `queue.json`), the metadata cache, the migration markers.
- **The sound engine** (`soundprint/`): `sound.db` and `vectors.npy` (153,000 sound prints, about 22 hours of
  analysis; they hold music paths only and move as they are), the model, and its Python environment.
- **Absolute paths inside the data**: 10 or more mix sidecars and `radio_favourites.json` (26 times) contain
  `...\addon_data\plugin.audio.musicip\...` (cover and fanart paths); they need rewriting to the new folder.
- **The sound engine's Python environment** (`soundprint/python`) was made for its old path (`pyvenv.cfg`, the
  launchers in `Scripts`): after the move, run Settings > Advanced > "Set up the sound engine" again (it keeps the
  model and the sound prints; only the environment is made anew).

## Outside the add-on

- `userdata/keymaps/musicip_mix_editing.xml`: the installed shortcuts point to the old ID; remove it (the add-on
  installs it anew, best under a new file name such as `incipit_mix_editing.xml`).
- Kodi's texture cache has 169 entries for `plugin.audio.musicip` URLs (mix collages, artwork): they are rebuilt;
  nothing to move.
- Kodi's add-on database (`Addons33.db`): the new ID appears as a new add-on to enable; the old one disappears with
  its folder.
- Kodi favourites, skin shortcuts or widgets that point to `plugin://plugin.audio.musicip/...` must be made anew.
- Claude Code's memory for this project is kept per folder path
  (`~/.claude/projects/c--Users-lutzh-AppData-Roaming-Kodi-addons-plugin-audio-musicip/memory`); copy it to the new
  path's folder after the rename.

## Instructions

The change has three parts. Part A is done by Claude in the code and changes nothing in Kodi yet. Part B is the
switch, done by the listener with Kodi and VS Code closed. Part C moves Claude's notes. Until part B is finished,
the old add-on keeps working as it is.

### Part A: prepare the code (Claude; Kodi may keep running)

All of part A happens on a separate git branch, `addon-id-incipit`, so the add-on Kodi runs is not touched.

1. **One place for the ID.** Put the ID in one constant, `ADDON_ID`, that every Python file takes it from:
   - `logs.py` already has `ADDON_ID`; `main.py`, `service.py` and `context_mix.py` import it from there instead
     of writing the ID themselves.
   - `main.py`: its own `plugin://plugin.audio.musicip/...` URLs (the info window's actions and others; `BASE_URL`
     comes from Kodi and follows by itself) are built from `ADDON_ID`.
   - `service.py`: the checks of which screen is open (`"plugin.audio.musicip" in container_folder`, in three
     places) use `ADDON_ID`.
   - The keyboard shortcut text (`MUSICIP_KEYMAP_CONTENT` in `main.py` and `service.py`) is built from `ADDON_ID`.
   - `soundprint/state.py` gets its own `ADDON_ID` (the sound engine runs outside Kodi and can't import `logs.py`);
     `soundprint/__main__.py` builds its default data folder from it.
2. **Change the ID to `plugin.audio.incipit`** in:
   - the constant(s) from step 1;
   - `addon.xml`: `id="plugin.audio.incipit"`;
   - `resources/settings.xml`: the section id and the 7 `RunPlugin(plugin://plugin.audio.musicip/...)` actions
     (and `tools/make_settings.py`, which writes that file);
   - `resources/keymaps/musicip_mix_editing.xml`: renamed to `incipit_mix_editing.xml`, its 24 `RunPlugin(...)`
     actions changed; `MUSICIP_KEYMAP_FILENAME` becomes `"incipit_mix_editing.xml"`;
   - `.gitignore`: the ignored path `profile/addon_data/plugin.audio.musicip/...`;
   - texts that name the ID (`soundprint/model.py`, `strings.po`, `README.md`, `docs/`).
3. **Take the data over at the first start** (in the service, before anything else runs), once:
   - if `userdata/addon_data/plugin.audio.incipit` doesn't exist and `userdata/addon_data/plugin.audio.musicip`
     does: **copy** the old folder to the new one (copy, not move: the old one stays as a backup);
   - in the new folder's JSON files (mix sidecars, `radio_favourites.json`, the Radio and Discovery state), replace
     `addon_data\plugin.audio.musicip\` with `addon_data\plugin.audio.incipit\` (and the same with `/`);
   - delete the old keyboard shortcut file `userdata/keymaps/musicip_mix_editing.xml` (the new one is installed as
     usual);
   - write a marker file, log every step in full (General area, always), and show one notification: "Incipit has
     taken over your MusicIP data. Run Settings > Advanced > Set up the sound engine once."
4. **Tests**: every expected URL, log tag and path changed; new tests for the take-over (copy, paths rewritten,
   old keymap removed, only once, nothing when there is nothing to take over). The whole suite passes; code and
   tests in separate commits on the branch.
5. Claude reports that part A is ready. Nothing is merged yet.

### Part B: the switch (the listener, with Claude for step 3)

Do these in one go, in this order.

1. **Check that no sound engine analysis is running**: Settings > Advanced > Status. If one is running, wait for
   it to finish, or press "Stop the analysis" and wait until Status says it has stopped.
2. **Close Kodi** completely (Power > Exit), and check in the Task Manager that no `kodi.exe` is left.
3. **Merge the branch** (ask Claude: "merge addon-id-incipit"). Claude merges it into the current branch and
   checks the tests once more. After this, Kodi must not be started from the old folder.
4. **Close VS Code** (it keeps the folder open, and Windows won't rename a folder that is open).
5. **Rename the add-on folder** in Windows Explorer: go to `%APPDATA%\Kodi\addons`, right-click
   `plugin.audio.musicip` > Rename, type `plugin.audio.incipit`, Enter. The git repository moves with it; nothing
   inside the folder changes.
6. **Copy Claude's notes** (part C below), before opening the renamed folder in VS Code.
7. **Start Kodi.** It finds Incipit as a new add-on. If it is disabled: Add-ons > My add-ons > Music add-ons >
   Incipit > Enable. At its first start the service takes over the data (part A, step 3); the notification says
   so.
8. **Set up the sound engine once more**: Settings > Advanced > "Set up the sound engine". This makes its Python
   environment anew in the new folder (a few minutes). The sound prints and the model are kept; nothing is
   analysed again.
9. **Check that everything is there**:
   - Settings: Mixing and Radio still have your values (for example variety 9, no artist repeat within 6);
   - Saved mixes: the list, their covers, opening and playing one;
   - Radio > Favourite stations: the list and their artwork; start one;
   - Settings > Advanced > Status: about 153,000 sound prints stored;
   - Settings > Advanced > Claude statistics: the counts from before;
   - a new mix from a song, and in a mix the keys M (More like this) and Del (Remove from mix);
   - Kodi favourites, widgets or menu shortcuts that pointed to the old add-on: add them anew.
10. **After a few days**, when everything works: delete the backup
    `%APPDATA%\Kodi\userdata\addon_data\plugin.audio.musicip` (798 MB).

**If something goes wrong**: close Kodi, rename the folder back to `plugin.audio.musicip`, and ask Claude to undo
the merge. The old data folder is untouched, so the old add-on runs as before; delete
`addon_data\plugin.audio.incipit` before trying again.

### Part C: Claude's notes (the listener, during part B, step 6)

Claude Code keeps its notes for this project in a folder named after the project's path. In Windows Explorer:

1. Open `C:\Users\lutzh\.claude\projects`.
2. Copy the folder `c--Users-lutzh-AppData-Roaming-Kodi-addons-plugin-audio-musicip`.
3. Paste it in the same place and rename the copy to
   `c--Users-lutzh-AppData-Roaming-Kodi-addons-plugin-audio-incipit`.
4. Then open `%APPDATA%\Kodi\addons\plugin.audio.incipit` in VS Code; Claude finds its notes there. The old folder
   can be deleted once that works.
