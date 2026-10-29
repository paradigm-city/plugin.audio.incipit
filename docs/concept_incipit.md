# Incipit: Source, Character, Intent

Status: **current** (2026-10-29). This is how Incipit (formerly MusicIP) makes and keeps mixes now. The documents it
grew from are background: [concept_ai_mix_assist.md](concept_ai_mix_assist.md) (the checks, then called AI Mix
Assist), [concept_suggestion_engine.md](concept_suggestion_engine.md) (replacing MusicIP) and
[glossary_ai_mix_assist.md](glossary_ai_mix_assist.md) (terms, old and new).

## In one sentence

**A mix grows from its first song, its incipit:** the sound engine finds songs that sound alike, as far out as the
variety lets it reach, and two checks keep the mix true to that first song, Character (the music's profile) and
Intent (an AI's judgement of what the song is about).

## Three steps

| Step | What it does | The listener's control | Off |
|---|---|---|---|
| **Source** | The sound engine: the songs nearest to the seed by sound, from sound prints made on this computer | **Variety** 0 to 9; **no artist repeat within N** songs | no (it is the source) |
| **Character** | Each song's 8-value profile against the seed's | **Tolerance**: Focused, Close, Balanced, Open, Adventurous | yes |
| **Intent** | The AI states what the seed is about and judges each song | **Perspective**: Mixed, Technical, Emotional, Cultural, Functional, Lyrical; **Accept borderline** | yes |

A new song must pass every check that is on. A track leaves a mix (tidy-up) only when every check that is on turns
it down. With both checks off the mix is the source's as it is, and nothing is asked of the AI.

Mixing and Radio have their own values for all of these (Settings > **Mixing**, **Radio**). A mix can have its own
Character and Intent ("Checks..." in its context menu); a favourite station keeps all of its own ("Station
settings...").

## Source: the sound engine

- **Sound prints.** Every song of Kodi's music library is analysed once: six 10-second snippets, each with a
  second of pre-roll decoded and dropped, embedded by DCLAP (a distilled CLAP audio model, ONNX; AGPL, downloaded
  at the set-up, never bundled) and averaged into a 512-value vector. No tags are used, so little-known music is
  found as easily as famous music. The whole library (153,000 songs) took about 22 hours on this PC; new songs are
  analysed after Kodi's library scan and every 8 hours. Package `soundprint/`, its own Python environment, its
  store `sound.db` and the matrix cache `vectors.npy` in the add-on's data folder.
- **The nearest songs.** Cosine similarity to the seed's vector; a search takes about a second.
- **Variety** (0 to 9). 0: the nearest songs, nearest first, a very cohesive mix. Each step reaches the same
  factor further (for a mix of 25: the nearest 66, 457, 3,175, 22,039 and all songs at 1, 3, 5, 7 and 9), and each
  song is drawn at random, the nearer the likelier (weight 1 / rank^p, p from 1 at variety 0 to 0.7 at 9). Near and
  far songs alternate, so a loose mix crosses genres and keeps finding its way back to the seed. Measured on the
  whole library: for Kraftwerk's "Vitamin", rock and metal sit at ranks 34,000 to 100,000; at variety 9 about a
  fifth of a mix comes from there.
- **No artist repeat within N** (MusicIP's reject size, kept as the one artist rule): counted over the finished
  mix, the seed first; the checks keep to it too when they add or replace songs, and a station counts the songs
  already queued.
- **The same song** (same artist and title on another album) only once.

## Character: the profile

Every album (or a compilation's track) is rated once by the AI on eight values: energy, exploration, mood, making,
danceability, production, form and the sounding year (`mixassist/dimensions.py`); the ratings are cached. A song's
misfit is its distance from the seed's profile, weighted by what makes the seed unusual. It may be at most the
**Tolerance**'s multiple (1.0 to 1.5) of the seed's typical misfit, and no single value may be clearly off (5
points, or 25 years).

The **typical misfit comes from a fixed scale per seed**: the seed's nearest 120 songs by sound that have a rating
(up to 35). So a loose candidate list is measured as a cohesive one would be (F40). With fewer than 5 rated songs
near the seed, the list's own spread is used, as before. The Emotional perspective leaves production out of the
profile.

## Intent: the AI's judgement

The AI (Claude, through the Claude Code CLI) first states what the seed is about, from the **perspective** chosen,
then judges every candidate: fits, borderline or outlier, with a reason. Perspectives: Mixed (the music's intention
and qualities together), Technical (how it is made), Emotional (what the artist expresses), Cultural (where it
comes from), Functional (what it is for), Lyrical (what the words say). **Accept borderline** also takes songs that
share part of what the seed is about. Music the rating didn't know is marked "little known" in the prompts and is
not turned down for an intent guessed from its names (F38). The same call names a mix or station in two to four
words ("Name mixes", "Name stations").

## Where it is used

- **New mixes**: checked in the background after they are made (Mixing > Checks > "Keep new mixes on track");
  tracks that don't fit are replaced from submixes of tracks that do. Undo in "Checks...".
- **More like this**: the source's candidates for the selected song are checked before they are inserted.
- **Radio**: a station's first songs and every refill are checked; refills are seeded from songs that passed.
  **Drift** lets the station's profile move with it (stay close, drift slowly, wander freely); a station that stays
  close draws its mixes at variety 2 or more, so they don't repeat.
- **Tidy-up on request**: "Checks..." > "Check the mix now".

## Code

| Part | Where |
|---|---|
| The source | `soundprint/` (analysis, store, `neighbours.nearest`), `soundprint/client.py` (Kodi's side), `main.fetch_mix` |
| Character | `mixassist/assist.py` (`analyze`, `character_scale`, `passes`), `mixassist/fit.py`, `main.character_reference` |
| Intent | `mixassist/checks.py` (prompts, perspectives), `mixassist/claude.py` |
| Ratings | `mixassist/rating.py`, `mixassist/cache.py` (`ratings.db`) |
| Settings and their one-time copies | `resources/settings.xml`, `service.migrate_radio_settings`, `service.migrate_intent_borderline` |
| MusicIP (dormant) | `musicip_dormant.py`: its mix request, parameters and library reload, unused since 2026-10-29 |

Internal names still say *mix assist* (`mix_assist_*`, the package `mixassist`, setting ids), and the add-on's ID
stays `plugin.audio.musicip`, so settings and data carry over.

## Ideas kept for later

- **Ordering a mix** by sound distance: shortest path from the seed ("interpolation"), a round trip back to the
  seed ("circle"), the largest smallest step ("contrast"), a bridge to a target song, sets, arcs of a profile value.
- **Keeping the sound prints in step with Kodi's library** as songs are added and removed (F36).
- **The sound engine on a quiet always-on box**: 3 snippets instead of 6 for a slower machine.
