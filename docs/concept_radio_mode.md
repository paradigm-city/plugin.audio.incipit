# Radio Mode Concept

## Goal

Radio mode works like a vintage radio set. You tune through random song snippets, as if turning the dial, and once something sounds good you start the radio. From then on, an endless MusicIP mix plays in full, with no further input.

## Tuning

**Radio mode → Turn on radio** starts tuning. It uses Discovery mode's snippet playback: random songs from the Kodi library, each starting at an offset and playing for the excerpt length. Both come from the Discovery mode settings (**Excerpt length**, **Start offset into song**).

While tuning, the Radio screen offers:

- **Start radio**: lock onto the snippet that is playing now
- **Next station**: jump to the next snippet
- **Stop radio**

## Playing

**Start radio** asks MusicIP for a mix seeded with the current snippet's song, using the configured **Mix parameters** settings, without a dialog. The playlist is replaced by that mix and the songs play in full, starting with the seed song. Labels carry no track numbers.

The service keeps the station running:

- When fewer than 3 songs are left, it requests a new mix seeded from the **last song in the queue**, so the station drifts gradually, like a radio programme. If that mix brings nothing new, it tries the two songs before it. After a failed or empty request it waits a minute before trying again.
- Songs already played or queued in this session are skipped, so nothing repeats.
- The playlist keeps the last 10 played songs; older ones are removed.

The Radio screen then offers only **Stop radio**.

## Stopping

- **Stop radio** stops playback and clears the playlist.
- The player's **Stop** stops the radio. The service waits 3 seconds before deciding, so the short gap between songs does not count.
- **Pause** pauses as usual; the radio stays on.
- Starting other playback (another album, a mix, Discovery mode) stops the radio without touching the new playback.
- If tuning stops (player stop, other playback), the radio switches off too.
- A Kodi restart switches the radio off.

## Not included

- Radio sessions are not saved under **Recent mixes**.
- There are no radio-specific settings.

## State

The plugin and the service share `radio_mode_state.json` in the add-on profile:

- `phase`: `off`, `seeking` (tuning) or `playing`
- `queue`: the station's playlist entries (`file`, `label`)
- `seen`: songs already played or queued in this session (up to 5000)
- `seeds`: the songs that seeded the station's mixes
- `current_*`: the song playing now
- `stop_reason`: why the radio stopped (`manual_stop`, `player_stop`, `external_playback`, `startup_reset`, …)

While tuning, Discovery mode's own state carries `owner: "radio"`.

While Radio mode or Discovery mode is on, the background search for missing files waits.
