# Suggestion Engine Concept

Status: **background** since 2026-10-29: MusicIP was replaced by the sound engine (sound prints of every song, by sound alone), not by the map of related artists drafted here; see [concept_incipit.md](concept_incipit.md). This draft (2026-10-25, work item 3 of 2026-10-24) is kept for the trials that led there and for the relation map as an idea. Terms of AI Mix Assist are in [glossary_ai_mix_assist.md](glossary_ai_mix_assist.md).

## In one sentence

**The add-on suggests songs from what belongs with the seed, not from what sounds like it:** a map of how the library's artists relate (members, solo work, collaborations, scenes, influences, as AllMusic's "related artists" do) picks the songs that have a chance, the profiles already rated by AI Mix Assist sort out the obvious misses, and the AI judges the rest, as it does now.

## Why replace MusicIP

MusicIP compares audio. That gives AI Mix Assist good raw material where sound and intent go together, and poor raw material where they don't:

- For Kraftwerk's "Vitamin", MusicIP's list is mostly lounge, nu-jazz and downtempo. The AI accepted 2 of 144 candidates with Mixed, 9 of 216 with Emotional (F34). The Emotional work of 2026-10-24/25 kept about 1 in 9 at the usual openness. Most of the AI's work, and most of the listener's waiting, goes into turning down songs that never had a chance.
- With "Stay close", every refill asks about the same song and gets much the same list (F34). Variety 0 gives the same 75 songs every time.
- MusicIP is old, Windows-only software that must rescan the library after files move (HTTP 500 for unknown paths) and runs as a separate server.

What the AI judges is intent, and intent travels along human lines: who played with whom, who came from which scene, who learned from whom. A Kraftwerk station wants Neu!, La Düsseldorf, Pyrolator, DAF, Der Plan, YMO, early OMD and Depeche Mode, Cybotron, Drexciya, Dopplereffekt, the Düsseldorf and Detroit lines, before anything that merely has a similar sound. That is the idea of a **relational network**.

## What MusicIP does that must be replaced

| MusicIP gives | Replacement | Gap |
|---|---|---|
| A candidate list from the library for any seed | the relation map plus the profile map (below) | none in principle |
| Songs the AI doesn't know (judged by their sound) | relations from Kodi's own data (credits, compilations, labels); reverse edges (an obscure artist names Kraftwerk, so Kraftwerk finds it); profile neighbours | obscure music without any relation and without a rating stays hard to find |
| Song-level choice: which songs of an album fit | the album's rating plus simple song rules; the AI's verdict per song | **sonic fit within an album** (the ballad on a metal album). The biggest loss; see *Song choice* |
| Fine sonic distinctions (djent vs. traditional progressive metal) | the AI's verdict, which already does this best | the profile's 8 dimensions are too coarse for it |
| The order of a mix | ordering by profile (smooth steps, artist window) | MusicIP's order was never good (it jumps between clusters; see *Drift* in the AI Mix Assist concept) |
| Variety (how wide the list is) | how far out on the map the engine reaches | none |

The seam exists: AI Mix Assist gets MusicIP as a callable (`fetch_mix` in `mixassist/assist.py`), so a second source can stand next to it with the same shape (a seed, a size, back come paths).

## The idea: two maps

| Map | Says | Source | State |
|---|---|---|---|
| **Relation map** | who belongs with whom, and how | facts (Kodi's credits, compilations, labels, biographies; MusicBrainz) and the AI's knowledge | new |
| **Profile map** | how a unit sounds and feels: the 8 dimensions and a description | the rating cache | exists (6,840 units rated) |

A candidate is a song **near the seed on the relation map and not far from it on the profile map**. A few **wildcards** come from the profile map alone, so the engine still finds what nobody connected (the role MusicIP had). The AI's seed-intent check then judges them, unchanged.

The two steps stay independent: the judge is not told why a song was proposed, so the proposal can't talk the judge into it.

## The relation map

### Nodes

Library artists (12,751 album artists, 36,563 song artists in all), plus **bridge artists** that aren't in the library but connect ones that are (Neu! connects Kraftwerk with Michael Rother and La Düsseldorf even when no Neu! album is there).

### Edges, after AllMusic's "related artists"

Each edge has a type, a strength, a source and a short reason ("Düsseldorf school; drummer Klaus Dinger"):

| Type | Example | Default strength |
|---|---|---|
| **member** (band ↔ member, either way) | Kraftwerk ↔ Florian Schneider | 1.0 |
| **solo / side project / alias** | Allan Holdsworth → Soft Machine, U.K., Tony Williams Lifetime | 1.0 |
| **collaboration** (joint album, featured artist) | Holdsworth ↔ Gordon Beck | 0.8 |
| **kindred** (the same idea in another place: scene, school, movement) | Kraftwerk ↔ YMO | 0.7 |
| **influence** (influenced by / followers) | Kraftwerk → Cybotron, Drexciya | 0.6 |
| **similar** (AllMusic's "similar artists") | | 0.5 |
| **player / producer credit** | Brian Eno produced Talking Heads | 0.3 |
| **label** (small labels only) | Kling Klang, Ata Tak, ECM | 0.3 |
| **compilation** (on the same compilation) | | 0.2 |

The strengths are guesses to calibrate. Two rules keep them honest:

- **Hubs count less.** An edge counts less the more edges its end has (like a word that appears in every document): Brian Eno, a major label or a 700-artist compilation connect everything and so say little.
- **The perspective weights the types.** Technical leans on players, collaborations and members; Cultural on kindred, label, compilation and influence; Emotional on kindred and influence, and less on "similar", which follows the consensus of what sounds alike; Lyrical on songwriters and lyricists; Functional relies more on the profile map. Mixed takes the defaults.

### Sources

| Source | What it gives | In this library (measured 2026-10-25) | Cost |
|---|---|---|---|
| **The AI**, asked per artist | all types, especially kindred, influence and similar: AllMusic's categories from the AI's knowledge, from the artist's side (what the makers were after), as a DJ knows them | everything the AI knows; familiarity marks guesses | ~25 artists per call: ~510 calls for all album artists, on demand first |
| **Kodi credits** (`song_artist` roles) | players, producers, composers, remixers | 6,819 artists in non-artist roles; 426 links between album artists | free, local |
| **Featured artists** | collaborations | 3,961 artist pairs on non-compilation albums | free, local |
| **Compilations** | who a compiler put together: library-specific, made by a person, not a consensus | 3,164 compilations, 24,490 artists, 8,123 pairs on 2+ compilations | free, local; noisy (see below) |
| **Labels** | scene and school (ECM, Warp, Kling Klang) | 2,949 labels, 559 with 3+ albums; major labels say nothing | free, local |
| **Biographies** (scraped) | members, groups, side projects, often as Discogs links `[a=Neu!]` | 2,965 album artists; 753 with `[a=Name]`, 510 with `[a123]` | free, local |
| **MusicBrainz** artist relations | members, collaborations, aliases, supporting musicians: facts, no style | 3,995 album artists have an MBID | free web API, 1 request per second |
| Last.fm / ListenBrainz similar artists | listening behaviour | not used | it is exactly the mainstream consensus the DJ stance avoids; at most a weak "similar" |

AllMusic itself has no public API, and Kodi no longer stores its similar artists. The AI is the closest thing to AllMusic's editors, and it can be asked from the artist's side, as the Emotional work showed.

**Reverse edges matter most for fringe music.** Asking only about the seed finds what the seed is known for. Asking every library artist "who are you related to" finds the obscure artist whose entry names Kraftwerk; that edge points back. So the map is built for the whole library over time, not per seed.

**Compilation edges are noisy.** Kraftwerk is on 8 compilations here; the one with 21 artists is a Neue Deutsche Welle collection with Falco, Spliff, Karl Gott and Nina Hagen: a shared era and language, not a shared intent. Hence the low strength, the hub rule and a cap on compilation size (2 to 40 artists).

### Storage

`relations.db` (SQLite, next to `ratings.db`): artists (name, normalized key, MBID), edges (from, to, type, strength, source, reason, version, time). Built on demand, cached forever, like ratings (principle 5); a new prompt version re-asks when next needed.

## Step 1: from the seed to candidates

1. **Rings around the seed artist.** Ring 0: the seed artist's other albums. Ring 1: direct edges. Ring 2: two steps (strength multiplied, halved per step, bridges included). Wildcards: units near the seed's profile, outside the rings.
2. **Relation score** per artist: the strongest path from the seed, typed by the perspective.
3. **Profile gate** per unit (arithmetic only): the weighted misfit against the seed and the single-dimension rule, at a looser limit than the openness (the AI decides, the gate only removes the obvious). An unrated unit passes and is rated in the background.
4. **A batch** of 18 is mixed from the rings, for example 2 from ring 0, 8 from ring 1, 5 from ring 2 and 3 wildcards, with the artist window and no more than 2 songs per artist.
5. **Every candidate carries its path** ("Pyrolator: member of DAF; DAF kindred to Kraftwerk, Düsseldorf 1980"). It goes into the log and the station information ("why this song is here"), not into the AI's judging.

### Song choice

The unit is the album; the engine still has to pick songs. Without audio:

- skip what is rarely meant for a mix: under 90 seconds (2,744 songs), and titles marked intro, interlude, skit, live, demo or remix, unless the seed is one;
- prefer the listener's rated songs (1,524 have a user rating); skip songs a station has turned down or played lately;
- spread over the album; take a famous track only where the AI's verdict says it fits;
- the AI's verdict is per song, from the title and the unit's description. For music it doesn't know, it can't tell the ballad from the rocker. That gap remains unless MusicIP stays as a sonic second opinion (see *Phases*).

Kodi's song-level data is thin: BPM for 4,877 of 153,615 songs, no mood.

## Step 2 and the loop: one engine

Today: MusicIP proposes, AI Mix Assist refines, and F34 is a refinement waiting for a better list. In one engine the loop is **propose → judge → learn**:

- **Moving outward replaces "the next list".** When a batch brings almost nothing, the next one reaches further out (ring 2, wildcards), or along the branch that fitted (from Fred und Luna rather than from "Vitamin" again). The open half of F34 becomes the engine's normal behaviour.
- **The station learns its shares.** If ring 2 fits better than ring 1 for this seed, the next batches take more of it (a simple running share per ring and edge type, per station).
- **Verdicts flow back into the map, per perspective.** An edge whose songs keep failing loses strength for that seed or perspective; one that keeps fitting gains. The rejected-song memory of a playing station already does the song-level part.
- **Drift walks the map.** "Stay close" keeps the centre on the picked artist; "drift slowly" and "wander freely" move the centre to the artists of songs that passed, with the half-life Radio already has. The profile drift stays as it is. A station's journey becomes explainable: Kraftwerk → Pyrolator → DAF → Liaisons Dangereuses.

## Cost and coverage

| Need | Size | Cost |
|---|---|---|
| Relations for all album artists | 12,751 artists | ~510 AI calls; seed neighbourhoods first, the rest in the background over days (usage limits) |
| Ratings for all normal albums | ~18,300 albums, part of them rated | ~500-600 calls at 20 per call |
| Ratings for compilation tracks | 59,251 tracks (39 % of the library) | too many to rate up front: rate on demand as today; before that, judge by the artist's other albums or the compilation's own character |
| Free sources (credits, compilations, labels, biographies) | the whole library | one local pass over Kodi's database |
| MusicBrainz relations | 3,995 artists | about 70 minutes at 1 request per second, once |

The whole-library rating is the same work the deferred "Mix from prompt" needs, so both gain from it.

## Risks

| Risk | Counter |
|---|---|
| **The consensus again.** "Similar artists" follows what most people hear; that is what the DJ stance avoids. | ask for relations from the artist's side; weight kindred and influence over similar; compilations and credits are made by people, not averaged |
| **Famous artists pull everything** (hubs). | the hub rule; the artist cap per batch |
| **Obscure artists stay invisible.** | reverse edges; Kodi's own data; wildcards; the share of wildcards grows when the rings run dry |
| **Invented relations** (the AI names a member who wasn't). | match against library names (and MBIDs); keep the AI's familiarity; facts from credits and MusicBrainz count more than guesses; an invented edge costs little, the judge still decides |
| **Too predictable** (always the same Kraftwerk family). | rings 2 and wildcards; the station's own memory of played and turned-down songs |
| **Song-level misses** within albums. | song rules; the per-song verdict; MusicIP as a second opinion while it is there |

## Phases

1. **Experiment, offline** (no change to the add-on). For four seeds with logged results and the user's verdicts (Kraftwerk "Vitamin", Van Halen, Holdsworth, Machacek): build the relation pool from the free sources and one AI relation call per ring-1 artist, draw batches as above, and judge them with today's prompts (Mixed and Emotional E3). Compare with MusicIP's lists: share of fits per batch, agreement with the user's 25 Kraftwerk verdicts, and how many of the songs that fitted from MusicIP's lists the pool also finds (what would be lost). Success: clearly more fits per batch, the user's fits found, few of MusicIP's good songs lost.
2. **Second source.** The relation pool next to MusicIP in Radio refills and replacements: when MusicIP's batch brings almost nothing, the next batch comes from the pool (closes F34). The log says which source a song came from, so listening shows which is better.
3. **Relations first.** The pool proposes, MusicIP fills in for unrated or unconnected seeds and, optionally, gives a sonic second opinion on songs.
4. **Without MusicIP.** One engine, once the map and the ratings cover the library. MusicIP becomes optional; "Generate mix" and Radio work without the MusicIP server.

## Open questions for the user

1. Is the edge vocabulary right (member, solo/side project, collaboration, kindred, influence, similar, credit, label, compilation)? Anything a DJ uses that is missing (shared producer as a "sound", the same studio, a record shop's shelf)?
2. Should the seed artist's own other albums take part (ring 0), and how many per batch?
3. How much surprise: what share of wildcards (unconnected, profile only) feels right, before the station loses its line?
4. Song choice within albums without MusicIP: acceptable with the rules above, or should MusicIP stay as a sonic second opinion?
5. Order of the experiment: Kraftwerk first (where MusicIP fails), or a seed where MusicIP does well (Holdsworth), to see what would be lost?
