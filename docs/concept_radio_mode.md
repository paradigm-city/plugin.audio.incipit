# Radio Mode Concept

## Goal

Radio mode works like a vintage radio set. You scan through random song snippets, like the scan button of a radio, and once something sounds good you pick that station. From then on, an endless mix plays in full, with no further input.

## Scanning

**Radio mode → Scan stations** starts scanning. It uses Discovery mode's snippet playback: random songs from the Kodi library, each starting at an offset and playing for the excerpt length. Both come from Radio's own settings (Settings > Radio > **Scan stations**: **Excerpt length**, **Start offset into song**; until 2026-10-29 Discovery mode's).

While scanning, the Radio screen offers:

- **Pick this station**: lock onto the snippet that is playing now
- **Skip station**: jump to the next snippet
- **Stop radio**

## Starting from any song

**Start Incipit radio** in the context menu of a library song (next to **Create Incipit mix**) starts a station with that song as seed, without scanning. It replaces any Discovery or radio playback, and the library view stays where it is. The Radio mode screen then offers **Scan again** and **Stop radio** as usual.

## Playing

**Pick this station** asks the sound engine for a mix seeded with the current snippet's song, with Radio's own variety and artist rule (or a favourite's), without a dialog. The playlist is replaced by that mix and the songs play in full, starting with the seed song. Labels carry no track numbers.

The service keeps the station running:

- When fewer than 3 songs are left, it requests a new mix seeded from the **last song in the queue**, so the station drifts gradually, like a radio programme. If that mix brings nothing new, it tries the two songs before it. After a failed or empty request it waits a minute before trying again.
- With the checks, each refill adds **Songs per refill** songs (Settings > Radio > Checks; 2 to 10, default 6; since 2026-10-30 a setting, for experiments with drift, before a fixed 6, and until 2026-10-24 8), chosen from the sound engine's 75 suggestions for the last queued song; the station also starts with that many. Small refills let a station meander in small steps, larger ones move in jumps. A station keeps the value it started with (`batch` in its state; Station information shows it), so a change applies to the next station. Without the checks a refill is a mix of the mix size.
- The station follows edits of Kodi's playlist (since 2026-11-01, F48): songs taken out leave it and don't come back, a new order is kept, and the next refill comes when the edited playlist runs low.
- What ends a playing station: **Stop** (after 3 s, as songs have short gaps), a song played or queued from the library ("Play", "Queue", "Play next": songs that aren't the station's in its playlist, as its context may be tainted), a mix of the add-on's, other media such as a video (at once), another file playing, and Kodi's restart. Pause doesn't. Kodi plays on with what it has; there is no current station until one is started.
- Songs already played or queued in this session are skipped, so nothing repeats: the sound engine leaves them (and the songs the checks turned down) out before it chooses, so each mix brings the nearest songs the station hasn't had, at any variety (since 2026-11-01; before, a station that stayed close used at least variety 2, roadmap I34).
- With the checks on, songs a check turned down are not checked again while the station plays (decided by the user, 2026-10-24). The station forgets them when it stops, and when its Character or Intent changes, since they might fit then. They can still be queued unchecked when the station would otherwise run dry.
- The playlist keeps the last 10 played songs; older ones are removed.

The Radio screen then offers:

- **Scan again**: go back to scanning; new snippets replace the station, and **Pick this station** locks onto a new one
- **Stop radio**

## Stopping

- **Stop radio** stops playback and clears the playlist.
- The player's **Stop** stops the radio. The service waits 3 seconds before deciding, so the short gap between songs does not count.
- **Pause** pauses as usual; the radio stays on.
- Starting other playback (another album, a mix, Discovery mode) stops the radio without touching the new playback. The service allows 3 seconds after a station starts before checking, while the new station replaces the old one's playback.
- If scanning stops (player stop, other playback), the radio switches off too. The service allows 3 seconds after scanning starts before checking, while the plugin starts the snippets.
- A Kodi restart switches the radio off.

## Possible improvements

In [roadmap.md](roadmap.md) (Radio): carry on when the station's own playlist plays again (I5; seen on 2026-10-24: station "Cold Precision Electro" stopped at 13:33 with `player_stop` when Kodi lost its display and audio device; when the device came back at 16:41, Kodi played the remaining two songs and fell silent), a favourite's own songs per refill (I6), describing the seed once on a station that stays close (I7), the artist rule over the queue for unchecked refills (I8).

## Not included

- Radio sessions are not mixes: they are neither the current mix nor listed under **Saved mixes**.
- Radio's own settings (Settings > **Radio**): **Stations** (variety, no artist repeat within N songs, name stations), **Checks** (keep Radio on track, drift, songs per refill), **Character** (tolerance or off), **Intent** (perspective or off, accept borderline) and **Scan stations** (excerpt length, start offset); see [concept_incipit.md](concept_incipit.md). A favourite station keeps its own ("Station settings...").

## State

The plugin and the service share `radio_mode_state.json` in the add-on profile:

- `phase`: `off`, `seeking` (scanning) or `playing`
- `started_ts`: when the radio was turned on (kept across **Scan again**); `tuning_started_ts`: when scanning last started
- `queue`: the station's playlist entries (`file`, `label`)
- `seen`: songs already played or queued in this session (up to 5000)
- `rejected`: songs the station's checks turned down (up to 5000), with `rejected_with`, the Character and Intent they were judged with; removed when the station stops
- `seeds`: the songs that seeded the station's mixes
- `current_*`: the song playing now
- `stop_reason`: why the radio stopped (`manual_stop`, `player_stop`, `external_playback`, `startup_reset`, …)

While scanning, Discovery mode's own state carries `owner: "radio"`.

While Radio mode or Discovery mode is on, the background search for missing files waits.
