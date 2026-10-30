# Discovery Mode Concept

## Goal

Discovery mode lets the user sample random songs from the Kodi music library. It plays short excerpts and allows the user to create a mix from the current discovery song at any point.

It is found under **Mix mode** (since 2026-10-30; before, it was an entry of the first screen): Mix mode shows its actions directly, followed by **Saved mixes**, as Radio mode shows its scan actions followed by **Favourite stations**.

## Playback model

Discovery mode uses Kodi's normal music player and a managed Kodi music playlist.

The playlist is not replaced on every song. Instead, Discovery mode maintains a rolling buffer:

- about 10 songs behind the current song
- the current song
- about 10 songs ahead

New songs are appended at the end. Old songs are removed from the top only after the backlog grows beyond the configured internal limit.

## Excerpt behavior

Each discovery song starts at a configured offset, currently based on a percentage of the song duration. The default concept is to start at roughly one third into the song.

Each excerpt plays for the configured excerpt length. When the excerpt length is reached, the service advances to the next playlist item.

## Manual skip

Manual "Skip to next discovery song" calls Kodi `Player.GoTo` directly and immediately updates the Discovery state. This prevents the old excerpt timer from causing a second skip.

## Mix dialog hold

When the user chooses "Generate mix from current discovery song":

1. The current Discovery song is captured immediately as the seed.
2. Discovery mode enters `mix_dialog_active`.
3. Playback continues.
4. The service pauses excerpt-based auto-skip.
5. The mix parameter dialog is shown.

If the user confirms, the mix is generated from the captured seed.

If the user cancels:

- if the dialog was open for at least the excerpt length, Discovery skips directly to the next song
- if the dialog was open for less than the excerpt length, the existing excerpt timer continues as if the dialog had not been opened

## External playback takeover

If the user starts playback outside the add-on while Discovery mode is active, Discovery mode stops itself without touching the new playback.

The current playing file is compared against the Discovery queue. If it is outside the queue, the add-on sets:

```json
"stop_reason": "external_playback"
```

No `Player.stop()` is called. The external media continues.
