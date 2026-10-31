# Mix recipes

Status: **draft** (2026-10-31), not built; roadmap idea I33 ([roadmap.md](roadmap.md)). The listener's idea, worked
out once and saved for later; the decisions at the end are still open.

## In one sentence

A **recipe** is a named set of the settings that shape a mix or a station (Source, Character, Intent, and a few of
Mixing's and Radio's own), chosen together because they give a certain kind of outcome; factory recipes come with
the add-on, the listener's own can be saved from any mix or station, and a recipe can be applied to a mix or a
station that exists already.

Example (the listener's): a maximally wide source, filtered only through the emotional intent: variety 9 (the whole
library), Character off, Intent Emotional, so the songs may come from anywhere and are held together only by what
the artists express.

## Why

Today these values are set one by one in four places (Settings > Mixing, Settings > Radio, a mix's "Checks...", a
favourite's "Station settings..."), and a combination that works has no name and can't be reused.

## What a recipe holds

| Group | Field | Mix | Station |
|---|---|---|---|
| Source | variety (0 to 9), no artist repeat within N | yes | yes |
| Character | tolerance (Focused … Adventurous), or Off | yes | yes |
| Intent | perspective, or Off; accept borderline | yes | yes |
| Shape | mix size | yes | ignored |
| Station | drift, songs per refill | ignored | yes |

- **Not in it:** the seed, and what the seed is about. The statement of intent belongs to the song, not to the
  recipe; it is worked out again for each seed.
- **One kind of recipe for both:** fields that don't apply are ignored, so a recipe saved from a station works for a
  mix and the other way round.
- **Partial recipes** (proposed): any field may be left as "keep"; then the mix's or station's own value, or the
  setting, applies. A recipe such as "Emotional lens" (Intent Emotional, Character off, everything else kept)
  becomes a filter that can be laid over anything.

Data, in the add-on's data folder (`recipes.json`; `null` = keep):

```json
{"id": "wide-emotional", "name": "Wide emotional", "factory": true,
 "variety": 9, "rejectsize": null, "character": -1, "perspective": 2, "borderline": false,
 "size": null, "drift": 2, "batch": null}
```

## Factory and own recipes

- **Factory recipes** ship with the add-on and are read-only; updates may improve them. "Save a copy as..." makes
  one the listener's own, to change.
- **Own recipes** are never overwritten by updates; names are unique.
- **"Save as recipe..."** on a mix, a station or a favourite takes its current values, without the seed (a
  station's drift and songs per refill come along).

A starter set, to be tuned by listening:

| Recipe | Source | Character | Intent | Station | The idea |
|---|---|---|---|---|---|
| **Focused** | variety 0 | Focused | Mixed | stay close | tight, one world |
| **Wide emotional** | variety 9 | Off | Emotional | wander freely | anywhere, held together by what the artist expresses |
| **Cultural journey** | variety 6 | Open | Cultural | drift slowly | across genres along a scene, an era, a lineage |
| **Lyrical thread** | variety 9 | Off | Lyrical | wander freely | songs about the same thing, in any genre |
| **Sound only** | variety 3 | Off | Off | stay close | no AI: works without a Claude subscription |

## Choosing a recipe

- **Settings:** Mixing and Radio each get "Recipe for new mixes / stations": none (the settings below apply) or a
  recipe. The individual settings stay as the baseline.
- **Creating:** "Create Incipit mix" uses the default; a second entry "Incipit mix with recipe..." asks first. The
  same for Radio.
- **A Recipes folder** in Mix mode and in Radio mode lists the factory recipes and the listener's own; their
  context menu: Edit, Rename, Save a copy, Delete, Set as default.
- **Information:** a mix's or a station's information names its recipe and what changed since, e.g. "Recipe: Wide
  emotional (variety changed to 7)".

## Applying a recipe to a station

- The station takes the recipe's values; they apply **from the next refill**, and the queued songs stay.
- A new perspective: what the station is about is stated again at the next refill; a favourite drops its saved
  description, as it does today with a new perspective (F44).
- The station's name stays. The station information notes the change ("14:02 Recipe 'Wide emotional' applied").
- A favourite that isn't playing takes the recipe's values as its saved settings.
- Option **"Apply now"**: drop the queued songs that haven't played and refill at once, so the change is heard
  right away.

## Applying a recipe to an existing mix

Two ways, offered when the recipe is applied:

**Rework: keep what fits, fill the gaps** (narrow down, then "More like this"):

1. The mix takes the recipe's values; the old ones are kept for undo.
2. A new perspective: what the seed is about is stated again (if the listener wrote it in their own words, they are
   asked whether to keep them).
3. **Narrow down:** every track but the seed is judged with the new checks; the ones that don't fit leave.
4. **Fill back to size:** the tracks that stayed seed "More like this" with the recipe's variety and artist rule;
   the new songs must pass its checks, and go next to the track that brought them, so the order stays coherent.
5. The whole step is one entry in the mix history, undone with "Undo the changes of the checks".

**Remake: a new mix from the same seed with the recipe.** The honest way when the *source* changes a lot: "Wide
emotional" applied to a tight mix can only narrow it, not widen it, because the kept core stays close to the seed.
Remake is roadmap I3 ("rebuild instead of patch") with a recipe.

Both run in the background with a progress bar, like the tidy-up; about as many AI requests as a tidy-up plus "More
like this" (1 to 3 minutes for a mix of 25).

## Building it, in steps

1. Recipes as data: the factory set, the defaults in the settings, "with recipe..." when creating, the recipe in
   the information.
2. Own recipes: "Save as recipe..." from a mix, station or favourite; the Recipes folders.
3. Applying to a station or a favourite (cheap, and heard at once).
4. Applying to a mix: Rework and Remake.

## Open decisions

1. **Partial recipes** (fields left as "keep"), or always complete ones? Proposed: partial.
2. **Narrowing rule** when a recipe is applied to a mix. Today's tidy-up removes a track only when every active
   check turns it down; for a deliberate re-cut, proposed: the rule for new songs (a track stays only if it passes
   every active check), stricter, but then the mix follows the recipe.
3. **Rework in place** (with undo), or always as a new mix that keeps the old one?
4. **Choosing when creating:** a second context menu entry ("...with recipe..."), or a setting "Ask for a recipe"
   that makes the existing entry ask?
5. **The factory set:** the right five to start with? A "Functional" one missing (focus, work)?
