# Roadmap

Where the add-on could go next: ideas that are not built (yet), collected in one place. The numbers say nothing
about the order in which they will be built. Problems in the code are in [findings.md](findings.md); this file holds
what could be added or changed.

How this file is kept up to date:

- Each idea has a permanent number (I1, I2, …). New ideas get the next free number; numbers are never reused.
- Each idea says where it came from (date; the listener, a test, a conversation or a concept doc) and what is known
  about it. The concept docs may hold the longer reasoning; the idea links to it.
- **Open** ideas wait to be picked up; **Parked** ideas were looked at and put aside, with the reason. A built idea
  moves to **Done** with the commit; a rejected one stays under **Parked**, saying why.

Collected on 2026-10-31 from the concept docs (*Ideas kept for later* in concept_incipit.md, *Deferred*, *Known
gaps* and *Next steps* in concept_ai_mix_assist.md, *Later ideas* in glossary_ai_mix_assist.md, *Possible
improvements* in concept_radio_mode.md), from the notes of earlier sessions and from conversations not written down
before.

## Open

### Mixes

#### I1 · Ordering a mix by sound

From the listener, 2026-10-29. Sort a mix (new and saved ones) by the sound engine's distances: **interpolation**
(the shortest path from the seed), **circle** (the shortest round trip back to the seed), **contrast** (the largest
smallest step; proposed instead of "maximise chaos", which as a sum would ping-pong). Later: a **bridge** from the
seed to a chosen song, **sets**, **arcs** of one profile value (energy rising and falling), and a **map** of a mix's
path on two main axes. The artist rule stays a constraint and the seed stays first. Proposed first step: "Sort
mix..." on saved mixes with the first three, plus a setting for new mixes. Open questions: sort in place or as a new
saved mix; what "chaos" should mean. MusicIP's own order was never good (it jumped between clusters), which is why
finished mixes are judged at drift 0 (concept_ai_mix_assist.md, *Drift*).

#### I2 · "More like this", "Less like this" and "Remove from mix" update Kodi's queue

From a conversation, 2026-10-30. The three edits change the stored mix, but while the mix plays, Kodi's play queue
keeps the old songs: removed songs still play, inserted ones only play after the listing is opened again. Since F42
the first screen still counts the edited mix as playing. The edits could change the queue the same way (remove,
insert after the selected song), without stopping the song that plays.

#### I3 · Rebuild a mix instead of patching it

From concept_ai_mix_assist.md (*Next steps*, *Known gaps*), 2026-10-17. When more than a third of a mix fails the
checks, the tidy-up plan marks it `rebuild_suggested`, but nothing acts on it. In such a mix the mix's median is
inflated and the relative threshold catches fewer misfits. A rebuild would make the mix anew from the seed.

#### I4 · Mix from a prompt

From concept_ai_mix_assist.md (*Deferred*), 2026-10-15. The reverse way: from a description to a seed to a mix. The
AI rates the prompt on the 8 values; the closest rated albums and descriptions are seed candidates; the AI picks
the album and its most typical track; the sound engine mixes; the checks hold the mix to the prompt, which becomes
its description "in your words". Catch: only rated music can be found (2026-10-15: about 19 % of the albums);
remedy: rate the whole library in small portions in the background. Next step: a spike with 3 or 4 prompts showing
the top seed candidates.

#### I33 · Mix recipes

From the listener, 2026-10-31. Worked out in [concept_mix_recipes.md](concept_mix_recipes.md) (draft). A
**recipe** is a named set of the settings that shape a mix or a station: Source (variety, no artist repeat),
Character (tolerance, or off), Intent (perspective, or off; accept borderline), the mix size, a station's drift and
songs per refill (which covers I6); not the seed. Example: a maximally wide source, filtered only through the
emotional intent (variety 9, Character off, Intent Emotional).

Factory recipes come with the add-on, the listener's own are saved from any mix, station or favourite ("Save as
recipe...", without the seed). A recipe can be applied to an existing mix (rework: narrow down with the new
checks, then fill back with "More like this"; or remake from the seed, I3) or to a station (from its next refill).
Five decisions are still open; see the concept.

### Radio

#### I5 · Carry on when the station's own playlist plays again

From the listener, 2026-10-24 (concept_radio_mode.md, *Possible improvements*). After the radio has stopped (e.g.
`player_stop` when Kodi lost its audio device), Kodi can go on playing the station's songs still in the playlist
while the radio adds nothing; to the listener it looks like a station that stopped refilling. Options: when playback
resumes on the stopped station's playlist (same files, same order), carry on with the station; or at least say in a
notification that the station has ended. Since 2026-11-01 a station records why it ended (`player_stop`,
`songs_added`, `mix_started`, `other_media`, `external_playback`, `manual_stop`): only a stop would carry on, the
others ended it on purpose (F48). The end forgets the songs the checks turned down (`rejected`); a station that
carries on would have to keep them.

#### I6 · A favourite station keeps its own "Songs per refill"

From a conversation, 2026-10-30. "Songs per refill" (2 to 10) is a Radio setting; a station keeps the value it
started with. A favourite could keep its own value with its other settings ("Station settings..."), like variety
and drift, so a drift experiment can be saved with the station.

#### I7 · A station that stays close describes its seed once

From a conversation, 2026-10-30. A station that stays close seeds every refill from the same song, and every refill
asks the AI again what that song is about. The description from the start (or the favourite's saved one, F44) could
be reused for refills from the same seed, which saves one AI request per refill. Not changed so far: the new
description per refill is also what lets a drifting station move.

#### I8 · Refills without checks keep the artist rule against the queue

From the notes of 2026-10-29. With the checks on, a refill keeps "no artist repeat within N songs" counted over the
queue's tail; without them, the rule holds only inside the new mix, so an artist can return right after the
previous refill. To verify, then fix (it may be recorded as a finding).

#### I32 · A Radio check moves on when a batch brings almost nothing

From F34 (2026-10-24, closed 2026-10-31). A Radio check examines its batches from the first candidate list and
brings further lists (from the songs that fit) only when that list runs out. When a batch brings almost nothing
(0 or 1 of 18), the check could move on to the next list at once, and a check that keeps choosing too little
could get more batches. Seen with MusicIP's lists; with the sound engine's not so far.

### Sound engine

#### I9 · Sound prints in step with Kodi's library

From the listener, 2026-10-28; the planned fix of F36. Adds and deletes in Kodi's music library are picked up as
they happen: `onNotification` AudioLibrary.OnUpdate / OnRemove (and onCleanFinished), new songs analysed as a list
of paths (no walk over every file), removed songs pruned, a low-priority run with prune at startup, and the search
leaves out stored songs Kodi doesn't list. This also removes the old spellings of paths kept since F45.

#### I10 · A library health check for songs listed twice

From a conversation, 2026-10-31 (F45). A scan of a lower-cased folder made Kodi list about 3,850 songs twice, under
`D:\` and `d:\`; Kodi's library clean doesn't remove them, because Windows finds the files under both spellings.
The add-on could find songs whose paths differ only in case, show them, and offer to remove the spelling that is not
the music source's. Changing Kodi's database needs care: a dry run first, a backup, Kodi's own JSON-RPC where it
can do it.

#### I11 · A faster search

From the notes of 2026-10-28. With 153,000 songs the matrix (vectors.npy, about 314 MB float32) makes a search take
about 0.9 s, and about 4 s for the first one after many new songs. Options: keep the matrix as float16 (half the
reading), or a resident helper process that keeps it loaded, instead of a new Python process per search.

#### I12 · Fewer snippets for a slower box

From the trials of 2026-10-27 and the target hardware (an always-on, quiet box). 3 snippets instead of 6 halve the
analysis time (about 16 h instead of 31 h for 153,000 songs on this PC) at about the same quality of the AI's
verdicts (cos 0.983 to the whole song instead of 0.995). A setting for a Raspberry Pi or similar.

#### I13 · Intro and outro windows

From the listener, 2026-10-27. Whole songs have natural fades at the start and the end; AudioMuse's whole-song mean
includes those windows, mid-song snippets never do. DCLAP leans on a window's first ~50 ms (a 200 ms fade changes a
window as much as 1 snippet instead of 6). Check how much intro and outro windows shape the whole-song vector, and
whether snippets should include or avoid them.

#### I14 · Other sound models

From the trials of 2026-10-25 and the licence check of 2026-10-27. Self-supervised models (MuQ, MERT) as a later
comparison with DCLAP, judged by CPU-only speed on this PC. If DCLAP's AGPL licence ever matters, its CC0 teacher
(LAION CLAP, HTSAT) is the fallback: free to bundle, but 5 to 6 times slower.

#### I15 · The worker processes watch their parent

From a conversation, 2026-10-31 (F46). When the analysis's main process ends, its workers end by themselves after
the song in hand (a broken pipe) or at once when idle; tested. An explicit watch of the parent in each worker would
end them at once. Small gain; not needed so far.

#### I16 · The set-up stops when Kodi closes

From a conversation, 2026-10-31 (F46). The analysis stops when Kodi closes; the set-up (pip and the model download,
a few minutes) still finishes on its own. It could follow Kodi's process as the analysis does. Rare.

### Character and Intent

#### I17 · Acoustic, electric, electronic

From concept_ai_mix_assist.md (*Known gaps*). The listener rejected Crosby, Stills & Nash, Isabelle Mayereau and
The Doors from an electronic mix as "acoustic, not electronic, handmade". *Making* only tells played from
programmed. Candidate: a *sound* value (acoustic, electric, electronic) instead of or next to *making*.

#### I18 · The intent check reads the intent as a summary

From concept_ai_mix_assist.md (*Known gaps*), 2026-10-24. Judged against the stated intent alone (later batches,
replacements), songs get stricter verdicts than in the call that stated it (Steve Vai and Tigran Hamasyan for
Machacek). Candidate: tell the intent check that the intent summarises the seed, not a checklist to tick off.

#### I19 · Longer descriptions

From concept_ai_mix_assist.md (*Next steps*). Album descriptions have 15 words; about 40 would keep later context
features possible without rating everything again.

#### I20 · Context tags

From concept_ai_mix_assist.md (*Deferred*). 2 to 4 tags per album from a fixed list of about 30 settings or scenes
(late night, road trip, club…), compared by overlap. The first step if listening shows "right values, wrong world"
misses.

#### I21 · MusicBrainz genres as a rating hint

From concept_ai_mix_assist.md (*Deferred*). Community-voted genres fetched by the album, a cleaner hint for the
rating than the genre tag; often missing for obscure music. Worth a pilot comparison.

#### I22 · The folder as a signal

From concept_ai_mix_assist.md (*Deferred*). In a library sorted into genre folders (as this one: `#hardrock`,
`#electronica`, …), the folder distance could be a signal, behind a setting. Not general.

#### I23 · Seed weights for narrow libraries

From concept_ai_mix_assist.md (*Deferred*). Seed weights measure "unusual within this library"; in a narrow library
the values that define the listener's taste become ordinary and lose weight. Remedies: measure against a fixed,
genre-balanced reference, and raise the weight floor (e.g. 0.5).

#### I24 · Running Claude with an API key

From concept_ai_mix_assist.md (*Build decisions*, 2026-10-14). The checks run through the Claude Code CLI on a
Claude subscription, and the add-on removes `ANTHROPIC_API_KEY` from every call so the subscription is used. An API
key as an alternative route would give the checks to listeners without a subscription (README, *Prerequisites*);
the costs per mix would have to be shown (the statistics already count tokens).

### Housekeeping

#### I25 · GitHub Actions on Node.js 24

From a conversation, 2026-10-30. The workflow's `actions/checkout@v4` and `actions/setup-python@v5` target Node.js
20, which GitHub retires; for now GitHub runs them on Node.js 24 with a warning. Move to `checkout@v5` and
`setup-python@v6`.

#### I26 · MusicIP out of the add-on's description and the README's version notes

From a conversation, 2026-10-31. addon.xml's description still ends with "Formerly MusicIP, whose server made the
mixes until 2026." (Kodi shows it on the add-on's page). The README's version notes 1.0.88 to 1.0.101 repeat
CHANGELOG.md and are partly out of date; a link to the changelog could replace them.

## Parked

### I27 · A relation map of artists

From the suggestion engine concept, 2026-10-25 (concept_suggestion_engine.md). Candidates from how the library's
artists relate (members, solo work, collaborations, scenes, influences, as AllMusic's "related artists" do) instead
of by sound. Parked on 2026-10-26 for the sound engine, which found the right world in the trials; kept as a
possible second source next to it, e.g. for an artist's own circle.

### I28 · Sound words for little-known music

From the pilot of 2026-10-29. Albums the AI doesn't know get a guessed description; the idea was to ground it in
words from the sound print (from LAION's CC0 text tower). Parked: the listener's ears showed the AI's errors there
came from intent read from the names, which F38 fixed by marking such songs "little known".

### I29 · Colour vector

From concept_ai_mix_assist.md (*Deferred*). An embedding of the album's description (about 384 numbers) to compare
context without names. Parked: needs a model Kodi can't run, likely encodes genre again, and the intent check covers
the same ground.

### I30 · A language rule

From concept_ai_mix_assist.md (decided 2026-10-18). A sung track in another language than the seed's counts as a
miss, from a per-album language label asked of the AI. Not built: no mix so far was spoiled by a language jump.
Revisit if listening shows it.

### I31 · Slider labels by library percentiles

From concept_ai_mix_assist.md (*Build decisions*). Placing the labels of value sliders by the library's
percentiles. Only needed for advanced sliders, which are not built.

## Done

### I34 · A station's search leaves out the station's songs

From a conversation, 2026-11-01; built the same day on `feature/radio-unheard-search`. A station that stayed close
drew its mixes at variety 2 or more (`RADIO_STAY_CLOSE_MIN_VARIETY`), overriding a lower variety set by the
listener: when no song of a station had passed a check yet, every refill asked the sound engine about the picked
song again, at variety 0 that gave the same 75 nearest songs each time, and the station's songs were filtered out
only afterwards, so the station ran dry. Now a station's mixes pass its played, queued and turned-down songs to the
search (a file of paths, `neighbours --leave-out`), which leaves them out before it chooses: each mix comes from the
nearest songs the station hasn't had, at any variety, and the floor is gone. Variety 0 draws at random too (decided
in the same conversation, for mixes and Radio alike): from the nearest 1.5 times the mix's size, the nearer the
likelier, so two stations or two mixes from the same song differ (on the real library: 54 of 75 songs shared, in
another order). Character's fixed scale still takes the nearest songs in order (`--in-order`).
