# Radio Mode Concept

## Goal

Radio mode works like a vintage radio set. You scan through random song snippets, like the scan button of a radio, and once something sounds good you pick that station. From then on, an endless MusicIP mix plays in full, with no further input.

## Scanning

**Radio mode → Scan stations** starts scanning. It uses Discovery mode's snippet playback: random songs from the Kodi library, each starting at an offset and playing for the excerpt length. Both come from the Discovery mode settings (**Excerpt length**, **Start offset into song**).

While scanning, the Radio screen offers:

- **Pick this station**: lock onto the snippet that is playing now
- **Skip station**: jump to the next snippet
- **Stop radio**

## Starting from any song

**Start MusicIP radio** in the context menu of a library song (next to **Create MusicIP mix**) starts a station with that song as seed, without scanning. It replaces any Discovery or radio playback, and the library view stays where it is. The Radio mode screen then offers **Scan again** and **Stop radio** as usual.

## Playing

**Pick this station** asks MusicIP for a mix seeded with the current snippet's song, using the configured **Mix parameters** settings, without a dialog. The playlist is replaced by that mix and the songs play in full, starting with the seed song. Labels carry no track numbers.

The service keeps the station running:

- When fewer than 3 songs are left, it requests a new mix seeded from the **last song in the queue**, so the station drifts gradually, like a radio programme. If that mix brings nothing new, it tries the two songs before it. After a failed or empty request it waits a minute before trying again.
- Songs already played or queued in this session are skipped, so nothing repeats.
- With AI Mix Assist, songs a check turned down are not checked again while the station plays (decided by the user, 2026-10-24). The station forgets them when it stops, and when its openness or perspective changes, since they might fit then. They can still be queued unchecked when the station would otherwise run dry.
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

**Carry on when the station's own playlist plays again.** After the radio has stopped, Kodi can go on playing the station's songs that are still in the playlist, while the radio stays off and adds nothing. To the listener it looks like a station that stopped refilling. Seen on 2026-10-24: station "Cold Precision Electro" stopped at 13:33 (`player_stop`) when Kodi lost its display and audio device; when the device came back at 16:41, Kodi played the remaining two songs and then fell silent. Options:

- When playback resumes on the stopped station's playlist (same files, same order) after a `player_stop`, carry on with the station.
- Or, at least, tell the listener in a notification that the station has ended.

## Not included

- Radio sessions are not mixes: they are neither the current mix nor listed under **Saved mixes**.
- Radio's own settings (Settings > **Radio**) are AI Mix Assist's: **Keep Radio on track**, **Station drift**, **Station openness**, **Station perspective** (from which point of view the AI judges the songs; see "Listening perspectives" in `concept_ai_mix_assist.md`).

## State

The plugin and the service share `radio_mode_state.json` in the add-on profile:

- `phase`: `off`, `seeking` (scanning) or `playing`
- `started_ts`: when the radio was turned on (kept across **Scan again**); `tuning_started_ts`: when scanning last started
- `queue`: the station's playlist entries (`file`, `label`)
- `seen`: songs already played or queued in this session (up to 5000)
- `rejected`: songs the station's checks turned down (up to 5000), with `rejected_with`, the openness and perspective they were judged with; removed when the station stops
- `seeds`: the songs that seeded the station's mixes
- `current_*`: the song playing now
- `stop_reason`: why the radio stopped (`manual_stop`, `player_stop`, `external_playback`, `startup_reset`, …)

While scanning, Discovery mode's own state carries `owner: "radio"`.

While Radio mode or Discovery mode is on, the background search for missing files waits.
