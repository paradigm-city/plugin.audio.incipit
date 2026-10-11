# MusicIP Kodi Add-on – Current Concept Snapshot

Version: 1.0.88 documentation snapshot  
Base code: 1.0.87

## Purpose

The add-on integrates a local MusicIP server with Kodi. It can create MusicIP mixes from the currently playing song, from a selected Kodi library song, or from a song discovered through Discovery mode. Radio mode plays an endless mix from a song found by tuning through random snippets.

The core idea is simple: use Kodi for library browsing and playback, use MusicIP for similarity-based mix generation, and keep saved mixes stable and repairable when files are moved or renamed.

## Current major feature areas

1. MusicIP mix generation
2. Mix parameter dialog
3. Saved/recent mixes
4. Mix consistency checking
5. Automatic mix repair
6. Discovery mode
7. Radio mode (tune through snippets, then an endless mix)
8. External playback takeover detection
9. Information dialogs and sidecar metadata

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

