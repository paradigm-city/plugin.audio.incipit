# Incipit (formerly MusicIP): Concept Snapshot

Version: 1.0.88 documentation snapshot  
Base code: 1.0.87

## Purpose

The add-on makes mixes from the currently playing song, from a selected Kodi library song, or from a song discovered through Discovery mode. Radio mode plays an endless mix from a song found by tuning through random snippets.

The core idea: use Kodi for library browsing and playback, the sound engine (sound prints of the whole library, made on this computer) for the songs that sound alike, Character and Intent to keep a mix true to its first song, and keep saved mixes stable and repairable when files are moved or renamed. How a mix is made is in [concept_incipit.md](concept_incipit.md). Until 2026-10-29 a local MusicIP server made the mixes; its code is dormant in `musicip_dormant.py`.

## Current major feature areas

1. Mix generation (the sound engine; Character and Intent)
2. Mix parameter dialog
3. The current mix and saved mixes
4. Mix consistency checking
5. Automatic mix repair
6. Discovery mode
7. Radio mode (tune through snippets, then an endless mix)
8. External playback takeover detection
9. Information dialogs and sidecar metadata

## The first screen

**Generate mix from playing audio**, then what plays, then **Mix mode**, **Radio mode**, **Settings**. Since 2026-10-30 the first screen shows the add-on's state, one of three:

1. **A mix plays** (Kodi's music playlist is mostly the current mix or a saved mix: at least 80 % of the playlist's songs are in the mix and at least 50 % of the mix's songs in the playlist, since "More like this", "Less like this", "Remove from mix" and a tidy-up change the mix but not all of the playlist; findings F42): **Current mix**, or **Playing mix** for a saved mix that is not the current mix. Mix mode then lists the current mix only if it is not the one playing.
2. **A station plays**: **Current station**, with what it plays as its second line, the red playing icon and the station's collage. It opens the station's information; its context menu has Station information, Save as favourite station (unless it is one), Scan again and Stop radio. A station exists only while it plays (a stopped one is gone; a favourite starts fresh), so it is never listed in Radio mode, which offers the same actions while it plays.
3. **Neither** (nothing plays, Discovery or the radio's scan plays, or other music): no such entry; the current mix is in Mix mode, first.

On the first screen these entries (Current mix, Playing mix, Current station) have the red playing icon (`icon-playing-red.png`, `PLAYING_ICON`); the current mix in Mix mode has the playlist icon of the saved mixes.

The service redraws the visible first screen or Mix mode when a mix starts or stops playing (whether audio plays and the music playlist's length change; while the radio or Discovery runs, their own redraws follow them).

Mix mode and Radio mode are built alike: each scans random snippets and holds its keepers.

- **Mix mode**: the current mix (when it doesn't play), Discovery mode's actions (Start discovery mode; while it plays: Create mix from current discovery song, Skip, Stop), then **Saved mixes (n)**. Until 2026-10-30 Discovery mode and Saved mixes were entries of the first screen; the old address of the Discovery screen (`action=discovery_mode`, e.g. in a Kodi favourite) opens Mix mode.
- **Radio mode**: Scan stations (while scanning: Pick this station, Skip station, Stop radio; while playing: Scan again, Station information, ...), then **Favourite stations (n)**.

The Mix mode entry shows Discovery's snippet as its second line, the Radio mode entry the radio's scan, each with the snippet's artwork as background. A playing station is shown by the Current station entry, not twice.

## The current mix and saved mixes

A new mix is not saved on its own. Each new mix (from the playing song, a library song, Discovery mode, or "Refresh mix") becomes the **current mix**, shown as **Current mix**: on the first screen while it plays, else in Mix mode. It can be played, edited and checked like any mix, and its information is complete, except that it is listed under its seed song only.

The listener decides whether to keep it: **Save mix**, in the context menu of "Current mix" and of each of the mix's tracks, asks for the mix's name, suggesting the seed song's, and lists it under **Mix mode** -> **Saved mixes** (until 2026-10 called "Recent mixes"). A name of the listener's own is kept in the sidecar as `"name"`; cancelling the name leaves the mix unsaved. A saved mix stays the current mix until the next new mix.

A new mix replaces the current mix. The replaced mix is deleted if it was not saved; a saved one stays under Saved mixes. Each new mix has a file of its own (`mix_<seed and size>_<time>.m3u`), so a new mix from the same song never replaces a saved one. `current_mix.json` in the profile folder names the current mix's file; the sidecar of a mix that is not saved yet has `"unsaved": true`. Mixes from older versions have no such key and are saved mixes.

Opening a library song's mix from the context menu shows the current mix if it was made from that song (and size), else it makes a new current mix.

## Important current baseline

Version 1.0.87 is the active feature baseline.

The experimental crossfade build 1.0.86 was discarded and is not part of this documentation baseline.

## Mix parameters

A mix is made with a size, a variety (0 to 9) and an artist rule (no artist repeat within N tracks); they are recorded with the mix (`mix_generation_parameters`). Mixes MusicIP made keep its parameters too (style, filter) and are described as MusicIP's.

