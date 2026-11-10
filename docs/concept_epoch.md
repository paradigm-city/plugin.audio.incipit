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
  what was in the air across music then. It begins with the years that time lasted for the seed's sound, as
  "Years: 1976–1979.": a couple of years for a short-lived sound (baroque pop), a decade for a long one (grunge).
  Written into the intent rather than a field of its own, the span is kept wherever the intent is (a station's, a
  favourite's, a mix's), the listener sees it in the information, and a listener's own words can give one too
  (`checks.epoch_span` reads "Years: …" or any "1977–1979"). Then 5 to 8 qualities of that moment a fitting track should share: the
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
   ratings. Helps Cultural today. Done 2026-11-10 (F51): the own album's year, else "compilation of …";
   MusicBrainz for songs the library has only on compilations is still to come.
2. The perspective: the prompt texts, the span at the start of the intent, "Epoch" in the Mix and Station perspective
   settings, the favourite station keeping it, the statistics' counts. Done 2026-11-10.
3. The time window in the sound engine's search (the station passes the years; songs outside them are left out like
   I34's): ±2 years for the first songs, the AI's span from then on; and the later songs by sounding year. Done
   2026-11-10 for Radio, without the later songs (see *The window built* below).
4. Test as the perspectives were (concept_ai_mix_assist.md, *Listening perspectives*): seeds of 1966, 1977 (station
   19's Legs Diamond), 1983, a grunge seed and 2003 (Kraftwerk "Vitamin"); check the spans the AI states (short for
   a short-lived sound, long for grunge), count genres, countries and years per refill, and how often Claude takes a
   later song; the listener's ears decide whether the profile or later songs need a rule.
5. Then I37: Cultural without time.

## First trial of the prompt (2026-11-10)

Built: the prompt (`checks.PERSPECTIVE_TEXTS["epoch"]`), `checks.epoch_span`, "Epoch" as the seventh choice of the
perspective settings. Tried with one seed-intent call per set on songs of this library (lines as the add-on writes
them, with F51's years; Kodi's database read directly, as Kodi was closed), the songs chosen by hand: the seed, its
time in other genres, its own kind from other times, later bands that refer to it.

| Seed | Span stated | Fit from other genres | Its own kind from another time | Later bands |
|---|---|---|---|---|
| Legs Diamond "I Think I Got It" (1977) | 1975–1979 | Sex Pistols, Donna Summer "I Feel Love", Kraftwerk, Television, Ramones, Steely Dan "Aja"; and Motörhead (1979), Judas Priest, UFO | Montrose 1973 and AC/DC 1981 borderline; Fleetwood Mac's 1968 blues and Def Leppard's "Hysteria" outliers | Black Star Riders borderline ("Thin Lizzy successor"); The Winery Dogs, Wolfmother, Rival Sons outliers |
| Soundgarden "Outshined" (1991) | 1989–1994 | Portishead "Glory Box"; Massive Attack's 1995 dub borderline | Black Sabbath 1983 and Neil Young 1979 outliers; Foo Fighters 1997, Blur "Song 2", Radiohead 1995 borderline | Royal Blood outlier |
| Kraftwerk "Vitamin" (2003) | 2001–2005 | Ladytron, Röyksopp, Boards of Canada, Goldfrapp | Kraftwerk's own "The Model", The Human League 1979, Yazoo 1982 outliers; LCD Soundsystem 2007 borderline | Marsheaux, Aurolab (synthwave) outliers |
| The Left Banke "Pedestal" (1968) | 1966–1969 | Hendrix "All Along the Watchtower", The Velvet Underground "Venus in Furs", The Doors | The Zombies 1965 and The Beach Boys 1971 borderline | (none in the set) |

- The spans follow the sound, not a fixed width: four or five years each here; none was the decade grunge might
  have been given (its core, 1989–1994, rather).
- Across genres as intended: a hard-rock seed takes punk, disco, Kraftwerk and Steely Dan of its years.
- The first release counts, not the line's year: Sex Pistols on a "compilation of 1999" fit as 1976, Motörhead on
  "No Remorse, 1984" as 1979, Mudhoney on a 2024 compilation as 1988. The listener's answer 4 holds: Kraftwerk's own
  1978 is another time for "Vitamin".
- Songs just outside the span are borderline, so Adventurous (which takes borderline) widens the window a little.
- Later bands: none fit; only Black Star Riders came close. Whether that is right, or "strong reference" is read too
  strictly, is for listening (the listener's answer 2).
- A song known only from a compilation that the AI can't date (Thomas Fehlmann, "compilation of 2017") is
  borderline: MusicBrainz's dates would help.
- Motörhead fits Epoch with the 1977 seed, as it should (the same years); keeping it apart is Cultural's job (I37).

The trial scripts are kept outside the repository (scratchpad `epoch_try.py`, `db_rpc.py`).

## The window built (2026-11-10)

- **Every song's year** (`soundprint/years.py`), from Kodi's music database read-only, as the sound engine already
  reads it for artists and titles; 2.6 s for 155,816 songs, kept in the data folder (`years.pickle`) until the
  database changes. A normal album's song: the album's original date. A compilation's song: the same song on the
  artist's own album (the earliest), else no year but the earliest compilation that holds it as the latest it can
  be. In this library: 82,717 songs with a year, 37,125 with only a latest, 35,974 with neither (left out of any
  window).
- **Not every compilation's date can be trusted.** The first try let Dream Theater, Volbeat, Alter Bridge and U2
  into 1975–1979: "Welcome To Rock Heaven" (a series of today) is dated 1975 or 1978 by its tags, as are "Golden
  Age – Vintage Synth Pop" (1,351 songs) and "NWOBHM Metal Rarities". A compilation is trusted when no more than a
  third of its songs by artists the library knows came later (the song on the artist's own album, or the artist's
  first album, more than two years after the compilation's date). A fifth was too strict: K-Tel's 1975 collections
  failed it, because the library has ABBA only as "Gold" (1993) and Nazareth from 1978 on. 3,022 of 3,243 dated
  compilations are trusted.
- **The search** (`--years 1975-1979`) leaves out songs of other years before choosing, as it leaves out a
  station's songs (I34); the order by sound stays, so variety is the reach across genres. A window that holds fewer
  than 1,000 analysed songs widens a year on each side at a time, at most ten: ±2 around 1966 hold 1,013 songs only
  as 1964–1968. In this library 1975–1979 holds 5,039 songs, 1989–1994 13,479, 2001–2005 15,698.
- **The station** (`main.station_years`): Epoch as its perspective (Intent), the span its intent states, else the
  picked song's year ±2 (its first songs and the start check's lists, before the intent is stated); the same for a
  favourite with its saved intent. It applies without Claude too: a station from a song's years alone. The window
  stays at the picked song's time while the station drifts. Logged in Radio's and Mixing's areas.
- **On the real library**, Legs Diamond "I Think I Got It" within 1975–1979: at variety 2 Boston, KISS, AC/DC,
  Foghat, Status Quo, Rainbow, Journey, and Joy Division, Magazine, Simple Minds; at 7 also City Boy, The Reducers,
  Foreigner, T. Rex, Led Zeppelin, Animals And Men. Without the window: Avenged Sevenfold, Metallica, Rammstein,
  Godsmack. Soundgarden "Outshined" within 1989–1994: Mother Love Bone, Rollins Band, Corrosion of Conformity, but
  also the glam metal of the same years (FireHouse, Lynch Mob), which the checks judge. Kraftwerk "Vitamin" within
  2001–2005: mostly downtempo and lounge (F34's neighbours) with Der Plan, The Human League's 2001 "Release";
  Kraftwerk's live "Radioaktivität" of 2005 counts as 2005 (a live album is an own album).
- **Not yet:** Epoch for mixes (a mix's perspective can be Epoch, but its search has no window); later songs with a
  reference (by the ratings' sounding year: left to testing, the listener's answer 2); MusicBrainz's dates for the
  songs with neither year nor latest; the AI's lines use their own compilation years, untrusted ones too (F52).

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
