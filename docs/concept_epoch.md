# Epoch: a perspective in time

2026-11-10, with the listener's answers (roadmap I39). Not built yet.

## In one sentence

Epoch is a seventh listening perspective: a mix or station of what came out when the seed came out, across genres,
scenes and countries, held together by the mood of that time, with now and then a later song that takes up that
time on purpose.

## The idea (the listener, 2026-11-10)

"Sounds released at the same time as the seed's original release date, reflecting the mood of an era. Could span
cultures and genres. Includes bands from later epochs with a strong reference."

A station that sounds like a year: for a 1977 seed, punk's first albums, disco's sequencer (Donna Summer's "I Feel
Love"), Trans-Europe Express, Rumours, Exodus, Aja; each from another scene, all of the same moment.

## Epoch and Cultural: time against place

Cultural today asks for "the scene, tradition and time" together. That is where I37's trouble comes from: for
station 19 (Legs Diamond, 1977) the shared time let Motörhead in, although the scene is another one. With Epoch,
time gets a perspective of its own, and the two divide the work:

| | Cultural | Epoch |
|---|---|---|
| The question | Where does the music come from, and what does it stand for? | When did it come out, and what was in the air? |
| The axis | a line through time: one scene or tradition, its roots and successors | a slice of time: every scene of the same years |
| What holds it together | the scene's place, people, audience, attitude and lineage | the time's mood, what was new, what the music answered |
| Genres and countries | mostly one family, its kin | any; the more the better |
| Years | those of the scene, which can last decades | a few years around the seed's original release |
| Later music | its successors belong | only with a strong, deliberate reference to the time |
| "Not:" | the nearest other scenes that sound alike (I37) | music that sounds like the seed but comes from another time, and later pastiche |
| For Legs Diamond, 1977 | LA's club hard rock on its way to the arenas (sharp: Montrose, early Van Halen; not Motörhead) | 1977: punk, disco, hard rock, reggae, Krautrock, West Coast; Character keeps the energetic side |

So Cultural can let go of "time" and become place and lineage (what I37 asks for), and Epoch never asks about the
scene. A listener who wants "the London scene of 1977" uses Cultural sharp; "1977 itself" is Epoch.

## What the intent states

Shaped like the other perspectives (`mixassist.checks.PERSPECTIVE_TEXTS`: the view, what the intent describes, the
rule), a first draft:

- **View:** the view of a chronicler of music: the moment the music came out, and what was in the air.
- **Intent:** one sentence on the moment: the seed's years (its first release, not a reissue or a compilation) and
  what was in the air across music then. In two fields of their own, the years that time lasted for the seed's
  sound (`from_year`, `to_year`): a couple of years for a short-lived sound (baroque pop), a decade for a long one
  (grunge). Then 5 to 8 qualities of that moment a fitting track should share: the
  years; the mood and spirit of the time; the sounds and studio techniques that were new or everywhere then (the
  first drum machines, gated reverb, the sampler, Auto-Tune); what music turned against or towards; the world it
  answered (social, political, technological). Reference points from several genres and countries, never only the
  seed's. "Not:" 2 or 3 kinds of music that sound like the seed but belong to another time, and later music that
  only borrows the time's surface.
- **Rule:** a track fits if it came out in those years and shares the time's spirit, in any genre, scene or country;
  or if it came out later and takes up that time with a strong, deliberate reference (a continuation or homage that
  carries its spirit, not only its sound). A track of another time that only sounds alike is an outlier, and so is
  later pastiche (borrowed nostalgia, as Emotional's "Not:" already says for synthwave against Kraftwerk). Judge a
  track's year by its first release: the year shown may be a compilation's (F51).

## The seed's year

"The seed's original release date" is harder than it looks in this library (measured 2026-11-10, Kodi's database read
only):

- 155,819 songs; 147,826 have a year. For an album Kodi keeps an original date as well, and it differs from the
  release date for 8,332 songs (reissues, remasters); that one is reliable.
- 73,393 songs (47 %) are on compilations, dated mostly in the 2000s to 2020s: the compilation's year, not the
  song's. Only 6,440 of them match the artist's own album in the library by artist and title, and half of those carry
  a compilation year more than 3 years later.
- 15,758 compilation songs have a MusicBrainz recording ID, whose first release date MusicBrainz knows.
- The ratings' sounding year (9,429 rated units) is when the music sounds like it was made, not when it came out;
  useful for later music with a reference (below), not as the release year.

So a song's year, in this order: the album's original date for a song on the artist's own album; for a compilation
song, the same song on the artist's own album in the library; then MusicBrainz's first release of the recording
(fetched once in the background, one request a second, kept; I21 and I36's blind spots use MusicBrainz too); else
unknown. The seed itself, if still unknown, gets its year from the AI's statement of the intent (it names the years),
which costs nothing extra. A late song of an old band counts by its own year and sound: a band whose sound changed
over time is in another epoch with each sound (the listener, 2026-11-10), so Kraftwerk's "Vitamin" belongs to 2003,
not to 1978.

## Where the songs come from

This is the part a prompt can't do. The sound engine brings the songs nearest in sound, mostly of the seed's genre
and from every year; the checks can only choose among them. A cross-genre slice of one time must be fetched as such:

- **A time window before the search.** As the station's own songs are left out before the sound engine chooses
  (I34), Epoch leaves out every song whose year is known and outside the window. The order by sound stays, so the
  nearest songs of that time come first, and **variety becomes the reach across genres**: low, the seed's own
  corner of 1977; high, all of 1977. No new setting needed.
- **The window** depends on the seed's time and how distinct its sound is (the listener, 2026-11-10): some sounds
  lasted only a short while, others a decade. So the window is the span the AI states with the intent (`from_year`
  to `to_year`), kept with the station's intent. When in doubt, and as the starting point, the seed's year ±2: for a
  station's first songs (they are fetched before the intent is stated), for a listener's own words, and when the AI
  gives no usable span. In this library ±2 years hold 1,198 songs around 1966, 6,515 around 1977 (158 genre tags),
  16,124 around 1983 and 11,541 around 1994. Enough everywhere but the early sixties, where the window may widen
  until it holds, say, 1,000 songs.
- **Unknown years** stay out of the window at first, so the station isn't diluted by today's compilations, except a
  compilation dated inside the window (made at the time, so its songs can't be later).
- **Later music with a reference:** songs from after the window whose rating's sounding year falls inside it (the AI
  heard them as of that time) join the candidates; the AI's rule then keeps only a strong reference. No limit on
  their share for now: a rule comes later if testing shows the need (the listener, 2026-11-10).
- **Drift** anchors the window at the seed's year: a station that drifts moves through the scenes of its time, not
  into the next decade. A journey through the years (1977, then 1978, …) is another idea (below).

## The profile check

Epoch keeps Character's whole profile, as the other perspectives do (Emotional leaves production out). Sounding
alike can be a strong relation within a time (the listener, 2026-11-10): the nearest songs of 1977 by sound are
good 1977 songs for the seed. How far a station reaches across genres is then up to the controls it already has:
variety (how far into the order by sound), Character's openness (how far the profile may stray) and Epoch's window.
Leaving dimensions out (keeping only energy, mood and sounding year) was considered and stays an option if testing
shows the profile holds a station too close to the seed's genre.

## How sharp (I38)

The window is Epoch's breadth, so I38's three stages map onto it: sharp the seed's own years within the span (±1),
clear the span the AI states (the default), broad the span widened by a few years either side (the time around it).
Later music with a reference might belong only to the broader stages, if testing asks for a rule.

## Costs

No more AI calls than any perspective: one statement of the intent, the usual judging calls. The window, the year
look-ups in Kodi's library and the supply are local. MusicBrainz look-ups are free and kept for good. A narrow window
may make refills scarcer for small years; the window widening keeps it fed.

## Building it, in steps

1. F51 first: a song's original year (own album, then a marked compilation year) in what the AI sees and in the
   ratings. Helps Cultural today.
2. The perspective: the prompt texts, the span fields in Epoch's schema (kept with the station's intent), "Epoch" in
   the Mix and Station perspective settings, the favourite station keeping it, the statistics' counts.
3. The time window in the sound engine's search (the station passes the years; songs outside them are left out like
   I34's): ±2 years for the first songs, the AI's span from then on; and the later songs by sounding year.
4. Test as the perspectives were (concept_ai_mix_assist.md, *Listening perspectives*): seeds of 1966, 1977 (station
   19's Legs Diamond), 1983, a grunge seed and 2003 (Kraftwerk "Vitamin"); check the spans the AI states (short for
   a short-lived sound, long for grunge), count genres, countries and years per refill, and how often Claude takes a
   later song; the listener's ears decide whether the profile or later songs need a rule.
5. Then I37: Cultural without time.

## The listener's answers (2026-11-10)

1. The window depends on the seed's time and how distinct its sound is: some sounds lasted a short while (baroque
   pop), others a decade (grunge). ±2 years when in doubt and as the starting point. Hence the AI's span, with ±2 as
   the fallback.
2. A limit on later music is a later rule, if it becomes necessary; left to testing.
3. Sounding alike can be a strong relation: the profile stays whole.
4. A band whose sound evolved is in a different epoch with each sound: the seed's own year counts.

## Later

- **A journey through the years:** a station that moves the window forward a year every few refills, from the seed's
  year on, like a radio show through a decade.
- **The playback screen** (I36) shows the time in the window below: "1977" with the Epoch intent's moment as its
  text, and the year of each song in the window above.
