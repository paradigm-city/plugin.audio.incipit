# Glossary: Incipit's checks (formerly AI Mix Assist)

## Names since 2026-10-29

| Now | Before | Meaning |
|---|---|---|
| **Incipit** | MusicIP (the add-on) | The add-on; its ID is `plugin.audio.incipit` (formerly `plugin.audio.musicip`) |
| **Source** | MusicIP (the server) | Where a mix's songs come from: the sound engine |
| **Sound engine** | | Sound prints of every song (DCLAP, 6 snippets), the nearest by cosine; `soundprint/` |
| **Checks** | AI Mix Assist | Character and Intent together; "Checks..." in a mix's context menu |
| **Character** | the profile check, the vector signal | Each song's 8-value profile against the seed's |
| **Tolerance** | openness, strictness | How far a profile may be off: Focused, Close, Balanced, Open, Adventurous, or Off |
| **Intent** | the AI check, the holistic signal | The AI's judgement of what the seed is about, from a perspective |
| **Perspective** | | Mixed, Technical, Emotional, Cultural, Functional, Lyrical, or Off |
| **Accept borderline** | part of the level Adventurous | Intent also takes songs it calls borderline |
| **Fixed scale** | | Character's typical misfit from the seed's nearest rated songs by sound (F40) |
| **Variety** | MusicIP's variety | How far into the order by sound a mix reaches, 0 to 9 |
| **No artist repeat within N** | MusicIP's reject size | The one artist rule, counted over the finished mix |

The rest of this glossary keeps the terms as they were developed; where it says AI Mix Assist, read the checks.

Terms used in [concept_ai_mix_assist.md](concept_ai_mix_assist.md) and in the pilot (`tools/style_pilot` on the branch `style-pilot`). Where a term replaces earlier wording, the retired words are listed so older notes stay readable.

## Names shown to the listener

| Shown as | Internal term |
|---|---|
| **AI Mix Assist** | the feature as a whole; developed as *style consistency* |
| "Keep … on track" (automatic) | refinement |
| "AI Mix Assist..." > "Run AI Mix Assist" (context menu) | tidy-up (on demand) |
| "What this mix is about" | seed intent |
| "didn't fit" | clearly inconsistent |

## Music and library

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Seed** | The track a mix is started from. It carries the intent of the mix. | |
| **Mix** | The track list MusicIP produces from a seed, as used by the add-on. | |
| **Saved mix** | A mix stored by the add-on and listed under Recent mixes, with its sidecar. Every new mix becomes a saved mix immediately. | |
| **Sidecar** | The JSON metadata file stored next to each saved mix. Style consistency adds a `style` section. | |
| **Refill** | The new mix Radio mode fetches when fewer than 3 songs are left. | "next batch" (*batch* is reserved for the API) |
| **Compilation** | An album with the compilation flag, "Various Artists" as album artist, or more than 8 distinct track artists. | |
| **Genre tag** | The genre field in the file tags. Messy (2,079 distinct values in this library). Used only as a **rating hint**; never a feature, signal or grouping. | |
| **Mood tag** | The mood field in the file tags. Not used: only 0.9 % of songs have one, and the values mix several vocabularies with junk. | |

## Dimensions

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Dimension** | One of the 8 rated properties of version 2: energy, exploration, mood, making, danceability, production, form, sounding year. | "category", "property", "*ness" (as a technical term) |
| **Dimension version** | Which set of dimensions a rating uses. **Version 1** (intensity, darkness, temperature, anthemic, electronic, presence, complexity, sounding year) was the first guess; **version 2** is the current set, chosen by the dependency study. | |
| **Scale** | The value range of a dimension: integers 0–10, or a year for the sounding year. | |
| **Step** | One of the 5 labelled points on a scale, e.g. *still · gentle · steady · driving · ferocious*. Slider positions use these labels. | |
| **Anchor** | Reference artists that pin a step down for the AI, e.g. "ferocious = Motörhead, Meshuggah". **Only this meaning.** | "anchored to the seed": see *reference* |
| **Sounding year** | The year the music sounds like, not when it was released. | "era" (fine as the short name of this dimension) |
| **Candidate dimension** | One of the 22 sharpened properties rated in the dependency study (energy, harmony, polish, vocal role …). | |
| **Dependency study** | The test that rated the pilot's albums on all 22 candidates and measured which of them measure the same thing (correlations, clusters, factors). | |
| **Factor** | An independent axis found in the dependency study; several candidates load on it (e.g. *exploration*: harmony, progressiveness, rhythmic complexity, inverted accessibility). | "cluster" |
| **Effective dimensions** | How many truly independent dimensions a set behaves like. Version 1: 4.4 of 8; version 2: 5.7 of 8. | |

## Rating

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Unit** | What gets rated: an **album** for normal albums (all its tracks share the rating), or a single **track** for compilations. | "item" (field name in the pilot code) |
| **Unit key** | The cache key of a unit: the MusicBrainz release-group ID (album) or recording ID (track); otherwise normalized artist and title. | |
| **Rating input** | What the AI receives per unit: artist, album or track title, year, track titles (albums only) and the genre tag as a hint. Never file paths, folders or audio. | |
| **Style vector** | The 8 values of one unit. | "property vector" |
| **Familiarity** | How well the AI knows the unit: 0 unknown, 1 artist known, 2 this album or track known. Unstable at the boundary between 0 and 1. | "confidence" |
| **Guessed unit** | A unit rated *unknown* (familiarity 0): the rating rests on hints alone. It is treated like any other unit (*act on the available facts*); reports mark it. | |
| **Description** | The AI's short wording of a unit's character (15 words at present), shown with reasons and candidates. | "character" (field name in the pilot code) |
| **Rating cache** | Stored style vectors and descriptions, reused by every later mix. | |
| **Prompt version** | A fingerprint of the rating prompt. When it changes, cached vectors are re-rated when next needed. | |
| **Rating on demand** | Units are rated when a mix needs them, not the whole library upfront. | "mix-based retrieval" |
| **Route** | How rating calls reach Claude: **API batch** (Message Batches API, half price, up to an hour), **API direct** (immediate, standard price) or **subscription** (Claude Code CLI with a claude.ai login). | "backend" |

## Fit

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Reference** | The profile a track is compared against. For judging a mix it is always the **seed's style vector** (drift 0). | "anchor" in this sense; "mix centre" as reference |
| **Seed weight** | How unusual the seed is on a dimension (distance from the library average in library standard deviations, scaled to average 1). The dimensions where the seed stands out count most. | "seed distinctiveness" |
| **Library reference** | The pilot's album ratings, used for the library averages and spreads behind the seed weights and for the overlap correction. | |
| **Spread** | How widely a mix's tracks vary on a dimension (robust, with a floor of 1 point or 5 years). Sets the scale of deviations. | |
| **Deviation** | A track's distance from the seed on one dimension, in units of the spread, multiplied by the seed weight. | "z" |
| **Misfit** | A track's weighted deviations combined into one number, corrected for overlap between dimensions. | "fit score", "distance" |
| **Relative misfit** | The misfit divided by the mix's median misfit (at least 1.0). Comparable between mixes; the threshold applies to it. | |
| **Reason** | The largest weighted deviations in slider words, e.g. "exploration: familiar vs. adventurous; form: vocal-led vs. open". | |
| **Signal** | One kind of evidence for misfit: the **vector misfit** (from the rating cache) and the **seed-intent check** (an AI call per mix). | "folder distance" (no longer a signal) |
| **Seed-intent check** | An AI call that first states the seed's intent as 5–8 musical qualities (not instrumentation, scene or production details) and then judges every track against it: fits, borderline or outlier, with a reason. The rest of the mix is context only. | "holistic check" (its general name), "AI teacher" |
| **Seed intent** | The intent stated by the seed-intent check, e.g. "Freely improvised, open-ended structure; … abstract and instrumental rather than song-like …". | "mix character" (that was the earlier check against the mix as a whole) |
| **Outlier** | A track whose relative misfit exceeds the strictness, or that the seed-intent check calls an outlier. | |
| **Flagged** | Internal status: one signal reports an outlier. The track stays; it is not used as a submix seed, and a new track in this state is not added. Not shown to the listener. | |
| **Clearly inconsistent** | Both signals agree. Replaced without asking during refinement, guessed units included. | |
| **Agreement** | How well the vector misfit ranks tracks like the seed-intent check or the user (AUC: 1.0 perfect, 0.5 chance). Used to choose and compare dimension sets. | "agreement score" |

## Settings

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Name** | A mix's or station's short title, 2 to 4 words saying what it is about, given by the AI at the first check (or by the listener). | "title" |
| **Openness** | What the listener sets: how much variety a mix or station welcomes. One scale for mixes and Radio, set separately ("Mix openness", "Station openness"): Focused, Close, Balanced (default), Open, Adventurous. Each level is a strictness. | "strictness" (in the settings), "station steps", "variety" (that is MusicIP's mix parameter) |
| **Single-dimension miss** | A track that differs from the seed (or a station's profile) by at least 5 points on one dimension, or 25 years in sounding year: flagged by the profile check however close it is overall. | |
| **Strictness** | Internal: the threshold on the relative misfit, plus whether new songs the AI calls borderline are accepted. The openness levels map to 1.0, 1.1, 1.2 (calibrated default), 1.35 and 1.5 with borderline songs. | "rigidity", "strength", "tolerance" |
| **Dimension weight** | A user setting per dimension: off, or how much it counts, on top of the seed weight. | per-category "strength" slider |
| **Target values** | Slider positions that set the desired value of a dimension directly instead of taking it from the seed. | |
| **Drift** | When tracks are chosen one after another (Radio, journeys): how the reference moves. **0** = stays at the seed, **1** = always the predecessor. Not used for judging finished mixes. | "memory" (meant the inverse) |
| **Step size** | How different consecutive tracks may be (the predecessor check). | |
| **Leash** | How far a mix may move from the seed in total (the seed check). | |

## Changing mixes

| Term | Meaning | Retired or ambiguous words |
|---|---|---|
| **Refinement** | A style-based change made **while a mix is being created**: in the background for new mixes and Radio's first refill, before queueing for later refills. Patches the playlist and the saved mix, notifies, and can be undone. | "style repair", "filter" |
| **Style check** | Planned on-demand check of a saved mix that would show flagged tracks for the listener to decide. Not built: the on-demand action is the tidy-up ("Run AI Mix Assist"), with Undo and the history. | "repair" |
| **Repair** | **Only** the existing recovery of moved or deleted files. | |
| **Over-fetch** | Requesting more tracks from MusicIP than the mix needs (e.g. 3×), so there is a choice. | |
| **Submix** | A small MusicIP mix created to replace an outlier, as in "More like this". It goes through the same consistency mechanisms as the master mix, measured against the master seed. | |
| **Submix seed** | The nearest earlier track that clearly fits (both signals clean), at worst the master seed. | |
| **Candidate** | A track from a submix that could replace an outlier, scored by weighted misfit against the master seed and checked against the master's seed intent. | |
| **Artist window** | The add-on's "Do not repeat artist within this many tracks" (5); replacements respect it, with artist names compared loosely. | |
| **Rebuild** | When much of a mix fails the seed's intent, fetching a new, larger selection instead of patching track by track. | |
| **Protected zone** | The playing track and the next one; refinement never changes them. | |
| **Decision record** | Planned: the listener's choices per track in a style check, as labels for calibration. Not built (no style check). | |

## Pilot (`tools/style_pilot`)

| Term | Meaning |
|---|---|
| **Pilot** | The experiments on this library: 486 albums and 200 compilation tracks rated on the dimensions, the dependency study, and dry runs on real mixes. |
| **Folder** | The genre folders of this library (`#metalcore_modern` …). Used **only as a test label** in the pilot: a convention of this library, not something other libraries have. |
| **Run** | One complete rating pass over the pilot sample. Runs 1–4 use dimension version 1, run 5 version 2. |
| **Stability** | How closely two runs agree. |
| **Folder recovery** | Whether a unit's style vector is nearest to its own folder's profile. |
| **Dry run** | Flagging tracks on a real mix without changing anything, for the user's judgement. |
| **Judgement** | The user's verdicts on a dry-run mix (out, ok, could), stored in `data/judgements/`. |

## Known gaps

| Term | Meaning |
|---|---|
| **Sound gap** | Acoustic ↔ electric sound is not represented: *making* only separates played from programmed. Kept in mind; candidate fix is a *sound* dimension. |

## Later ideas, deferred

Collected with numbers, with the other ideas, in [roadmap.md](roadmap.md).

| Term | Meaning | Why deferred |
|---|---|---|
| **Context tags** | 2–4 tags per unit from a fixed list of ~30 settings or scenes (*late night, road trip, club…*), compared by overlap. | First step **if** dry runs show "right values, wrong world" misses. |
| **Colour vector** | An embedding of the description (about 384 numbers) to compare unnamed context. | Needs an embedding model that Kodi can't run, likely re-encodes genre, and the seed-intent check covers the same ground. |
| **MusicBrainz genres** | Community-voted genres fetched through the unit key. | A cleaner rating hint than the genre tag; obscure music is often untagged there as well. |
| **Folder signal** | Folder distance as a signal, behind a setting for libraries organized by genre. | Not general. |
| **Journey** | The reference moves from the seed to a chosen destination over the mix length. | |
| **Arc** | A planned curve of one dimension over a mix, e.g. energy rising and falling. | |
| **Smooth ordering** | Re-ordering a mix so consecutive steps are as small as possible. | |
| **Map** | A mix's path drawn on two main axes. | |
