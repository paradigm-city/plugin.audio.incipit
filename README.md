# Incipit, a Kodi Add-on

Kodi music add-on that can create a mix from the currently playing audio track or from a song selected in the Kodi music library. The mixes come from the sound engine: sound prints made on this computer from a few 10-second snippets of every song (`soundprint/`).

## Features

- Listed under **Music add-ons**
- Can use the **currently playing audio** as the seed song
- Can open **Create Incipit mix** from the **context menu of library songs**
- Playlist size is configurable in add-on settings
- Shows a folder view with one entry per returned track so the user can play a single song
- Includes **Refresh mix** in the context menu to request a new mix for the same seed
- Includes **Remove from mix** in the context menu to remove a track from the stored current mix
- A new mix is the **Current mix**; **Save mix** (context menu) keeps it under **Mix mode** -> **Saved mixes**. A new mix replaces a current mix that was not saved.
- The first screen shows what plays: **Generate mix from playing audio**, then **Current mix** while a mix plays (**Playing mix** for a saved one that is not the current mix) or **Current station** while a station plays, then **Mix mode**, **Radio mode**, **Settings**. A current mix that doesn't play is in Mix mode. Mix mode and Radio mode are built alike: each scans random snippets (Discovery mode; Scan stations) and holds its keepers (**Saved mixes**; **Favourite stations**).

## Settings

- **Mixing**: mix parameters (playlist size, variety, no artist repeat, names), which mixes are checked (new mixes, "More like this"), Character (tolerance, or off), Intent (perspective, or off; accept borderline), Discovery mode (excerpt length, start offset) and saved mixes (consistency check, its interval, automatic repair)
- **Radio**: the stations' own variety, artist rule and names, checks (on, drift, songs per refill), Character, Intent and "Scan stations" (excerpt length, start offset)

A mix is made in three steps: **Source** (the sound engine's songs that sound alike, as far out as the variety lets it reach), **Character** (each song's 8-value profile against the seed's, on a fixed scale for that seed) and **Intent** (the AI's judgement of what the seed is about, from a listening perspective). Character and Intent can each be switched off.

- **Advanced**: the sound engine (automatic analysis, status, analyse now, stop, set-up) and Claude Code (CLI path, statistics)
- **Logging**: one switch per area (General, Mixing, AI and checks, Radio, Discovery mode, Saved-mix checks). With a switch on, that area writes detailed messages to `kodi.log`, each line tagged with its area, e.g. `[plugin.audio.incipit] [radio] ...`. Errors and warnings are always logged. The AI area logs every request to the AI in full, with its answer.

## Prerequisites

Incipit runs inside Kodi. Neither VS Code nor a Claude subscription is needed: without a subscription you get the sound engine's mixes, Radio and Discovery mode; only the AI checks (Character and Intent) and the AI's names for mixes and stations are missing.

- **Kodi 21 (Omega)**, with your music scanned into Kodi's music library (browsing folders is not enough). Tested on Windows. Incipit reads Kodi's own music database (`MyMusic*.db`), so a library shared through a MySQL or MariaDB server is not analysed.
- **Music as local files**, on a local drive or a mapped network drive (e.g. `M:\`). Songs that Kodi reaches through a network address (`smb://`, `nfs://`) are left out of the analysis.
- **Python 3.9 or later** from [python.org](https://www.python.org/downloads/), for the sound engine's set-up only (Kodi's built-in Python can't make the environment it needs). On Windows, tick "Add python.exe to PATH" in the installer, or enter the path to `python.exe` in the add-on's settings (**Advanced** -> **Python for the set-up**). Your Python stays as it is: the set-up makes its own environment in the add-on's data folder.
- **An internet connection for the set-up**: it downloads numpy, onnxruntime and PyAV (about 60 MB) and the DCLAP sound model (22 MB, licence AGPL-3.0, not part of the add-on). After that the sound engine works offline.
- **Disk space**: about 200 MB for the environment, plus about 3.5 MB per 1,000 songs for the sound prints (about 550 MB for 153,000 songs).
- **Time for the first analysis**: about 0.4 s per song on a 4-core PC, in the background at low priority; 153,000 songs took about 22 hours. A stopped analysis goes on where it stopped, and afterwards only new songs are analysed. No graphics card is needed.

### Without Claude: switch the AI checks off

Character and Intent are on by default and ask Claude through the Claude Code CLI. Without it, switch both off for mixes and for Radio:

- **Mixing** -> **Tolerance**: Off, and **Mixing** -> **Perspective**: Off
- **Radio** -> **Tolerance**: Off, and **Radio** -> **Perspective**: Off

With both off, nothing is asked of an AI: a mix is the sound engine's songs as they are, a station plays its refills unchecked, and mixes and stations are named after their seed song (you can still name them yourself). Variety and "No artist repeat" still shape every mix.

### With a Claude subscription (optional)

For the checks, Incipit needs a Claude Pro or Max subscription and the Claude Code CLI, installed on its own (VS Code is not needed). On Windows, in PowerShell: `irm https://claude.ai/install.ps1 | iex`, then run `claude` once and log in. Incipit finds the CLI by itself (or enter its path under **Advanced** -> **Claude Code CLI**). It always uses the subscription: an Anthropic API key in the environment is ignored.

## Install

1. Put the add-on files into a folder named `plugin.audio.incipit`.
2. Zip that folder itself, not only its contents.
3. In Kodi, go to **Add-ons** -> **Install from ZIP file**.
4. Install the zip.
5. Set up the sound engine in the add-on's settings (**Advanced** -> **Set up the sound engine**); it then analyses the library in the background.
6. Open **Music** -> **Music add-ons** -> **Incipit**.

## Notes

- The add-on uses the song title from Kodi metadata when available.
- If no title tag is available, it falls back to the current filename without extension.
- The refresh action forces Kodi to re-run the request and bypass plugin disk caching.
- At variety 0 the sound engine returns the same nearest songs for the same seed, so the refreshed mix is identical; raise the variety for a different choice.

- When a list item path is set in Kodi, the add-on also writes the same value into the corresponding `MusicInfoTag` URL field.
- The add-on now also writes artist and album into the corresponding `MusicInfoTag` when Kodi can resolve that metadata from the current player or the music library.

## Documentation snapshot 1.0.88

The add-on package now contains an updated `docs/` folder with concept notes and flow diagrams.

Current feature baseline: **1.0.87**.

The discarded crossfade experiment from 1.0.86 is not included.

Included documentation:

- `docs/concept_overview.md`
- `docs/concept_discovery_mode.md`
- `docs/concept_repair_strategy.md`
- `docs/concept_sidecar_metadata.md`
- `docs/testing_quality_notes.md`
- `docs/diagrams/*.mmd`
- `docs/diagrams/*.png`

Key documented flows:

- Discovery mode playback and state transitions
- Rolling playlist buffer with backlog and future items
- Mix dialog hold behavior
- External playback takeover handling
- Repair readiness and auto-repair decision flow

## Generate mix autoplay note 1.0.90

`Generate mix from playing audio` now behaves like the Discovery mix path after successful mix creation:

- generate the mix
- save the mix
- start playback immediately
- show the generated mix view

The working Discovery mix route is intentionally left unchanged.

## Mix track label formatting note 1.0.91

Generated mix track rows and generated mix playback playlist items now use Kodi's configured music track naming template where available.

For the common Kodi template:

```text
[%N. ]%A - %T
```

`%N` is set to the position inside the generated mix, not the original album track number.

Discovery mode labels are intentionally unchanged in this build.

## Mix label display fix 1.0.92

Kodi's music views may display `MusicInfoTag.title` instead of the raw `ListItem` label. Generated mix items now set the formatted mix label as the MusicInfoTag title as well.

This means a Kodi-style template such as:

```text
[%N. ]%A - %T
```

is visible in the mix view, with `%N` reflecting the generated mix position.

Discovery mode remains unchanged.

## Mix editing keyboard shortcuts 1.0.93

Mix rows now expose keyboard shortcut actions in the Kodi music window:

- `DEL` → Remove from mix
- `+` / Numpad `+` → More like this
- `-` / Numpad `-` → Less like this

The keymap is shipped as:

```text
resources/keymaps/incipit_mix_editing.xml
```

The shortcut handlers only act on selected mix rows. Discovery mode is unchanged.

## Mix editing keyboard shortcuts update 1.0.94

The mix editing keymap was adjusted:

- `DEL` → Remove from mix
- `m` → More like this
- `l` → Less like this

The previous `+` / `-` bindings were removed.

The shortcut keymap now targets multiple Kodi music window contexts for better reliability:

- `MyMusicNav`
- `MusicPlaylist`
- `MusicFiles`

For `DEL`, both `<delete>` and `<del>` are included.

Discovery mode remains unchanged.

## Keymap installation and icon fix 1.0.95

The mix editing keymap is now actively installed into Kodi's user keymap folder:

```text
special://profile/keymaps/incipit_mix_editing.xml
```

and reloaded with `ReloadKeymaps` when it changes.

The key bindings now also target the numeric Kodi music navigation window:

```text
window10502
```

This addresses cases where Kodi reports the active music window as `10502` and no action is mapped.

Also, the add-on package now really includes the agreed abstract orb icon as `icon.png`.

## Track metadata cache phase 1 – 1.0.96

This build introduces the first phase of metadata caching for generated mixes.

What changes:

- generated mix rows first use sidecar metadata snapshots
- if no sidecar snapshot exists, the add-on uses a global SQLite metadata cache
- live Kodi JSON-RPC lookup is now only the last fallback
- generated mix playback reuses preloaded metadata instead of looking up each track again
- the mix sidecar now records per-track metadata snapshots

Phase 1 goal:
- reduce repeated JSON-RPC metadata lookups when reopening or replaying mixes

Phase 2 is still open:
- background metadata refresh for stale or missing cache entries
- queued refresh batches without blocking the mix view

Discovery mode remains unchanged.

## Metadata cache phase 1 hotfix – 1.0.97

Fixed a regression from 1.0.96 when opening a mix:

```text
name 'KODI_MUSIC_TRACK_TEMPLATE_CACHE' is not defined
```

This build only hardens the Kodi track-label template cache initialization.
The phase 1 metadata cache concept remains unchanged.

## Verified metadata cache hotfix – 1.0.98

This build carries forward and tightens the 1.0.97 fix for:

```text
name 'KODI_MUSIC_TRACK_TEMPLATE_CACHE' is not defined
```

No new feature was added.

The Kodi track-label template globals are now explicitly initialized together:

- `KODI_MUSIC_TRACK_TEMPLATE_CACHE`
- `KODI_MUSIC_TRACK_TEMPLATE_FALLBACK`
- `KODI_MUSIC_TRACK_TEMPLATE_SETTING_CANDIDATES`

Additional pre-package checks were run for the mix-opening path, metadata cache path, keymap install, icon, and Discovery preservation.

## Metadata lookup repair – 1.0.99

This build fixes a regression where mix metadata could appear missing after the phase 1 cache change.

Fixes:

- `songid` is no longer requested as a Kodi `AudioLibrary.GetSongs` property
- metadata lookup retries with a reduced safe property list if Kodi rejects the full property list
- stale/empty sidecar snapshots are no longer accepted only because they contain `cached_ts`
- existing empty sidecar snapshots from 1.0.96/1.0.97/1.0.98 are ignored and live lookup is attempted again

No background refresh is included yet.

## Background metadata refresh – 1.0.100

This build adds phase 2 of the metadata cache work.

Mix rendering now avoids live per-track JSON-RPC metadata lookups. The mix list is built from:

1. per-mix sidecar metadata
2. global SQLite metadata cache
3. fallback filename/path display

Missing or stale metadata is queued in:

```text
metadata_refresh_queue.json
```

The background service processes the queue in small batches, writes refreshed data to:

```text
track_metadata_cache.db
```

and updates the relevant mix sidecar snapshots. If the currently visible container is a mix view, the service refreshes it once after a successful batch.

Discovery mode behavior remains unchanged.

## Selection-triggered metadata presentation – 1.0.101

This build changes phase 2 presentation behavior.

1.0.100 refreshed the visible mix view immediately after a successful background metadata batch. In 1.0.101 the service instead marks the visible mix view as having updated metadata available and waits for the next selection movement.

Flow:

1. mix opens quickly from sidecar/cache/fallback labels
2. background service fills missing metadata
3. service marks the visible mix view as pending refresh
4. when the user moves the selection, the service rebuilds the container once

This presents updated metadata without requiring manual navigation out and back into the mix, while avoiding sudden list rebuilds during passive viewing.
