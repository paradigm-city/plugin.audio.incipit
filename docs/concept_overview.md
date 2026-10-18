# MusicIP Kodi Add-on – Current Concept Snapshot

Version: 1.0.88 documentation snapshot  
Base code: 1.0.87

## Purpose

The add-on integrates a local MusicIP server with Kodi. It can create MusicIP mixes from the currently playing song, from a selected Kodi library song, or from a song discovered through Discovery mode. Radio mode plays an endless mix from a song found by tuning through random snippets.

The core idea is simple: use Kodi for library browsing and playback, use MusicIP for similarity-based mix generation, and keep saved mixes stable and repairable when files are moved or renamed.

## Current major feature areas

1. MusicIP mix generation
2. Mix parameter dialog
3. The current mix and saved mixes
4. Mix consistency checking
5. Automatic mix repair
6. Discovery mode
7. Radio mode (tune through snippets, then an endless mix)
8. External playback takeover detection
9. Information dialogs and sidecar metadata

## The current mix and saved mixes

A new mix is not saved on its own. Each new mix (from the playing song, a library song, Discovery mode, or "Refresh mix") becomes the **current mix**, which the first screen shows as **Current mix**, after "Generate mix from playing audio". It can be played, edited and checked like any mix, and its information is complete, except that it is listed under its seed song only.

The listener decides whether to keep it: **Save mix**, in the context menu of "Current mix" and of each of the mix's tracks, asks for the mix's name, suggesting the seed song's, and lists it under **Saved mixes** (until 2026-10 called "Recent mixes"). A name of the listener's own is kept in the sidecar as `"name"`; cancelling the name leaves the mix unsaved. A saved mix stays the current mix until the next new mix.

A new mix replaces the current mix. The replaced mix is deleted if it was not saved; a saved one stays under Saved mixes. Each new mix has a file of its own (`mix_<seed and size>_<time>.m3u`), so a new mix from the same song never replaces a saved one. `current_mix.json` in the profile folder names the current mix's file; the sidecar of a mix that is not saved yet has `"unsaved": true`. Mixes from older versions have no such key and are saved mixes.

Opening a library song's mix from the context menu shows the current mix if it was made from that song (and size), else it makes a new current mix.

## Important current baseline

Version 1.0.87 is the active feature baseline.

The experimental crossfade build 1.0.86 was discarded and is not part of this documentation baseline.

## MusicIP API parameter naming

The add-on stores mix parameters internally with simple lowercase keys. When sending the HTTP request to MusicIP, these keys are mapped to the API spelling expected by the server.

Important outgoing API keys:

- `sizeType=tracks`
- `rejectType=tracks`
- `content=text`

The lowercase internal keys `sizetype` and `rejecttype` should not be sent directly to the MusicIP server.

