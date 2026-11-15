# 🎵 Music Recommender Simulation

## Project Summary

In this project you will build and explain a small music recommender system.

Your goal is to:

- Represent songs and a user "taste profile" as data
- Design a scoring rule that turns that data into recommendations
- Evaluate what your system gets right and wrong
- Reflect on how this mirrors real world AI recommenders

This version takes a user's taste profile — a genre, a mood, a target energy level, and
whether they like acoustic music — and ranks every song in the catalog against it. The
four features are **not** treated as equals: they are applied in a strict priority order,
so that genre decides the broad shape of the list and the remaining features decide the
order *within* it.

---

## How The System Works

### The idea in one sentence

Features are ranked by importance, not just added together: **genre → mood → energy →
acoustic**. A song that matches on a higher-priority feature always outranks a song that
only matches on lower-priority ones.

### Why priority order, and not a flat score

If you score every feature with similar weights and add them up, a song can win on
accumulated small matches while missing the thing the user actually asked for. A user who
asks for **pop** and gets a jazz track at the top — because it happened to nail energy,
mood, and acousticness — will not trust the system again.

Priority order prevents that. Genre is treated as the near-non-negotiable feature; the
others refine the list rather than overturn it.

### The four features

| Priority | Feature | What it answers | How it's matched |
|---|---|---|---|
| 1 | `genre` | *Is this even the right kind of music?* | Exact match, or partial credit for a related genre |
| 2 | `mood` | *Does it fit the moment?* | Exact match, or partial credit for a related mood |
| 3 | `energy` | *Is the intensity right?* | Closeness on a 0–1 scale — never pass/fail |
| 4 | `acousticness` | *Acoustic or produced?* | A yes/no nudge, used mainly to break ties |

Genre and mood are **categorical** — they either match or they don't, so they're scored in
steps. Energy is **continuous** — a song at 0.42 against a target of 0.40 is nearly
perfect, and the score should reflect that rather than rounding it to a hit or a miss.
Acousticness is continuous in the data but splits cleanly into two groups, so it's used as
a simple boolean preference.

### Partial credit: the "related" tier

Exact string matching is too brittle for a real catalog. Two cases in our own data show
why:

- A user who likes **pop** should still see **indie pop** — just not above actual pop.
- A user who asks for **calm** should still see songs labelled **chill** or **relaxed** —
  the catalog simply doesn't use the word "calm."

So genre and mood each get three tiers instead of two: **exact match**, **related match**,
and **no match**. Related moods are grouped into families (`calm / chill / relaxed /
focused` describe one listening state; `intense / energetic` describe another), and related
genres are grouped by shared roots (`pop` and `indie pop`).

### How the ranking is enforced

Each feature contributes points, and the point ranges are spaced so that a higher-priority
feature can never be out-voted by everything below it combined:

| Feature | Exact | Related | None |
|---|---|---|---|
| Genre | 20 | 10 | 0 |
| Mood | 4 | 2 | 0 |
| Energy | 0 – 2, scaled by closeness | | |
| Acoustic | 1 if the preference agrees | | 0 |

The spacing is the whole trick. Mood, energy and acoustic together can contribute at most
**7 points** — less than the 10-point gap between genre tiers. So no combination of lower
features can ever lift a wrong-genre song above a right-genre one. Genre priority is
absolute.

Mood is deliberately softer. Its tier gap is 2 points, while energy and acoustic together
can contribute up to 3 — so a song with a *related* mood but a near-perfect energy match
can edge out a song with an *exact* mood and badly wrong energy. This is a choice, not an
oversight: mood labels are fuzzy and often disagree between listeners, so they shouldn't be
as rigid as genre. If you'd rather mood be absolute too, widen its tiers to 8 / 4 / 0 and
the same guarantee applies.

### Worked example

**User profile:** `genre=lofi`, `mood=chill`, `energy=0.40`, `likes_acoustic=True`

| Rank | Song | Genre | Mood | Energy | Acoustic | Score |
|---|---|---|---|---|---|---|
| 1 | Midnight Coding | lofi — exact, 20 | chill — exact, 4 | 0.42 → 1.96 | yes, 1 | **26.96** |
| 2 | Library Rain | lofi — exact, 20 | chill — exact, 4 | 0.35 → 1.90 | yes, 1 | **26.90** |
| 3 | Focus Flow | lofi — exact, 20 | focused — related, 2 | 0.40 → 2.00 | yes, 1 | **25.00** |
| 4 | Spacewalk Thoughts | ambient — none, 0 | chill — exact, 4 | 0.28 → 1.76 | yes, 1 | **6.76** |
| 5 | Coffee Shop Stories | jazz — none, 0 | relaxed — related, 2 | 0.37 → 1.94 | yes, 1 | **4.94** |

Read the gaps, not just the order. The three lofi songs are clustered at the top and the
non-lofi songs fall off a cliff — that's genre priority doing its job. Within the lofi
block, the top two are separated by **0.06 points**, decided purely by energy: both match
genre and mood exactly, so the lower-priority feature breaks the tie. That is the intended
behaviour at every level of the cascade.

### Choosing what to show

The top *k* songs by score, with one extra rule: **at most one song per artist**. Seven
of the twelve artists in this catalog have multiple tracks, and without that rule a top-5
list can be half the same artist — technically correct, practically useless.

---

## Data Flow

```
┌─ INPUT ──────────────────────────────────────────────────────────────┐
│                                                                      │
│   data/songs.csv                      user_prefs                     │
│   20 rows, 10 columns                 {genre, mood,                  │
│         │                              energy, likes_acoustic}       │
│         ▼                                     │                      │
│   load_songs(path)                            │                      │
│   → List[Dict]                                │                      │
│         │                                     │                      │
└─────────┼─────────────────────────────────────┼──────────────────────┘
          │                                     │
          └──────────────┬──────────────────────┘
                         ▼
┌─ PROCESS ── for each song in songs ──────────────────────────────────┐
│                                                                      │
│   score_song(user_prefs, song) -> (score, reasons)                   │
│                                                                      │
│     normalise  ......  lowercase, strip, hyphen → space              │
│          │                                                           │
│          ▼                                                           │
│     1. GENRE      exact 20  │ related 10 │ none 0   ── priority 1    │
│          +                                                           │
│     2. MOOD       exact  4  │ related  2 │ none 0   ── priority 2    │
│          +                                                           │
│     3. ENERGY     2 x (1 - |song.energy - target|)  ── priority 3    │
│          +                                                           │
│     4. ACOUSTIC   1 if (acousticness > 0.5) == pref  ── priority 4   │
│          =                                                           │
│       score (0.0 - 27.0)  +  reasons ["genre: exact pop", ...]       │
│                                                                      │
│   The loop only JUDGES. It never compares songs to each other        │
│   and never sorts — every song is scored in isolation.               │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
              List[(song, score, reasons)]   ← 20 scored, unordered
                           │
┌─ OUTPUT ──────────────────┼──────────────────────────────────────────┐
│                           ▼                                          │
│   1. sort by score, descending                                       │
│                           │                                          │
│                           ▼                                          │
│   2. filter: keep first song per artist, drop later ones             │
│                           │                                          │
│                           ▼                                          │
│   3. take top k  (default 5)                                         │
│                           │                                          │
│                           ▼                                          │
│   4. join reasons into one explanation string                        │
│                           │                                          │
│                           ▼                                          │
│   List[(song, score, explanation)]  →  printed by src/main.py        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Why the stages are split this way

**Scoring is per-song and order-free.** `score_song()` looks at exactly one song and one
profile. It has no idea what the other songs scored. This keeps the priority logic in one
place, makes the function trivial to unit-test with a single song, and means the catalog
could grow to 20,000 rows without the scoring logic changing at all.

**Ranking is the only stage that compares songs.** Sorting, de-duplicating by artist, and
cutting to *k* all happen after every score is final.

**Order matters inside the output stage.** The artist filter runs *after* the sort but
*before* the top-*k* cut. Sorting first guarantees that the one song kept per artist is
that artist's best match, and cutting last guarantees you still get a full *k* results
rather than a short list with holes in it.

**Reasons are collected during scoring, not reconstructed afterwards.** Each feature
appends its own explanation at the moment it contributes points, so the explanation is
always a true record of the score — it cannot drift out of sync with the number.

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.main
```

### Running Tests

Run the starter tests with:

```bash
pytest
```

You can add more tests in `tests/test_recommender.py`.

---

## Sample Recommendation Output

Produced by `python -m src.main` against the 20-song catalog in `data/songs.csv`.

### Default profile: `genre=pop, mood=happy, energy=0.8`

```
Top recommendations:

Sunrise City - Score: 25.96
Because: genre matches pop (+20); mood matches happy (+4); energy 0.82 vs target 0.80 (+1.96)

Gym Hero - Score: 21.74
Because: genre matches pop (+20); energy 0.93 vs target 0.80 (+1.74)

Rooftop Lights - Score: 15.92
Because: indie pop is close to pop (+10); mood matches happy (+4); energy 0.76 vs target 0.80 (+1.92)

Corner Store Kings - Score: 3.78
Because: confident feels like happy (+2); energy 0.69 vs target 0.80 (+1.78)

Slow Collapse - Score: 2.00
Because: energy 0.80 vs target 0.80 (+2.00)
```

The whole design is legible in those five lines. The two exact-genre songs take the top,
separated only by how close their energy sits to 0.80. *Rooftop Lights* is the
related-genre tier doing its job — indie pop places third, above every non-pop song, but
cannot climb past actual pop no matter how well it matches everything else. Then the
scores fall off a cliff to 3.78, where songs are matching on mood and energy alone.

*Slow Collapse* at the bottom is worth noticing: it matches **nothing** except energy,
and a perfect energy match is worth only 2.00 points. That is the priority order working
as intended — being right about the least important feature earns the least.

### A different taste: `genre=lofi, mood=chill, energy=0.4, likes_acoustic=True`

```
Midnight Coding - Score: 26.96
Because: genre matches lofi (+20); mood matches chill (+4); energy 0.42 vs target 0.40 (+1.96); acoustic, as preferred (+1)

Library Rain - Score: 26.90
Because: genre matches lofi (+20); mood matches chill (+4); energy 0.35 vs target 0.40 (+1.90); acoustic, as preferred (+1)

Spacewalk Thoughts - Score: 6.76
Because: mood matches chill (+4); energy 0.28 vs target 0.40 (+1.76); acoustic, as preferred (+1)

Coffee Shop Stories - Score: 4.94
Because: relaxed feels like chill (+2); energy 0.37 vs target 0.40 (+1.94); acoustic, as preferred (+1)

Dust Road Hymn - Score: 4.76
Because: relaxed feels like chill (+2); energy 0.52 vs target 0.40 (+1.76); acoustic, as preferred (+1)
```

The top two are separated by **0.06 points**. Both match genre and mood exactly and both
are acoustic, so the only thing left to tell them apart is energy — 0.42 against 0.40
beats 0.35 against 0.40. That is the cascade reaching its fourth level.

There is a third lofi song in the catalog, *Focus Flow*, which scores 25.00 and does not
appear. It is by LoRoom, the same artist as *Midnight Coding*, and the
one-song-per-artist rule keeps only that artist's best track. Without it the top three
would be two LoRoom songs and a Paper Lanterns song — a correct ranking, but a dull
playlist.

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or demo video link here -->

---

## Experiments You Tried

All runs below use the profile `genre=pop, mood=happy, energy=0.8, likes_acoustic=False`
unless stated otherwise. The baseline ranking is:

```
26.96  Sunrise City        [pop]
22.74  Gym Hero            [pop]
16.92  Rooftop Lights      [indie pop]
 4.78  Corner Store Kings  [hip hop]
 3.00  Slow Collapse       [rock]
```

### 1. Which features are worth scoring at all

Before writing any scoring code I measured how the audio columns relate to each other
across the catalog. Four of the five numeric columns turned out to be the same signal:

```
energy ↔ tempo_bpm       r = +0.96
energy ↔ acousticness    r = -0.99
energy ↔ danceability    r = +0.86
```

At `r = -0.99`, `acousticness` carries almost no information that `energy` does not
already carry — so a user's `likes_acoustic` preference could never disagree with their
`target_energy`. Scoring all four would not have been four signals; it would have been
one signal counted four times, quietly drowning out genre and mood.

**Outcome:** dropped `tempo_bpm` and `danceability` from scoring entirely. Kept `energy`
as the intensity axis and `acousticness` as a separate yes/no preference. `valence` was
the only numeric column that was genuinely independent (`r = +0.19` against energy), and
it is held in reserve as a tiebreaker rather than scored.

### 2. Fixing the data instead of the code

The correlations above were a property of the starter catalog, not of music. Ten songs
chosen to break them — a loud acoustic bluegrass track, a quiet electronic one, a slow
heavy rock song, a fast weightless ambient one — changed the picture:

| Feature pair | 10 songs | 15 songs | 20 songs |
|---|---|---|---|
| energy ↔ tempo_bpm | +0.96 | +0.92 | **+0.65** |
| energy ↔ acousticness | −0.99 | −0.68 | **−0.69** |
| energy ↔ danceability | +0.86 | +0.79 | **+0.69** |
| danceability ↔ acousticness | −0.85 | −0.71 | **−0.61** |

**Outcome:** no pair now correlates above 0.69, so every column carries information no
other column has. This was the single highest-leverage change in the project, and it
involved no code at all.

### 3. Flattening the weights

Set genre to 2/1 and mood to 2/1, leaving energy and acoustic as they were, so all four
features contribute roughly equally:

```
 6.96  Sunrise City        [pop]
 5.92  Rooftop Lights      [indie pop]   <-- climbed past a pop song
 4.74  Gym Hero            [pop]
 3.78  Corner Store Kings  [hip hop]
 3.00  Slow Collapse       [rock]
```

**Outcome:** exactly the failure the priority design exists to prevent. *Rooftop Lights*
overtakes *Gym Hero* — an indie pop song beating actual pop for a user who asked for pop
— purely by accumulating small wins on mood and energy. A user who asks for a genre and
is served something else does not read it as a clever blend; they read it as broken.
This experiment is why the genre tiers are spaced wider than everything below them can
sum to.

### 4. Removing the related tier

Set both family tables to empty, so genre and mood become exact-match-or-nothing:

```
Rooftop Lights:  16.92  ->  6.92
```

**Outcome:** *Rooftop Lights* falls from a clear third place into the same band as the
hip hop and rock songs that match nothing but mood and energy. For a user who likes pop,
an indie pop track is a good recommendation — far better than a rock track — and binary
matching throws that away. The middle tier is what separates "wrong genre" from "nearly
right genre."

### 5. Making mood strict as well

The README design notes that mood's 2-point tier gap is narrower than the 3 points
energy and acoustic can supply, so mood is deliberately *not* absolute. Raising mood to
8/4 would make it strict:

**Outcome: no change.** Both the pop and lofi rankings came out in exactly the same
order, with every score simply shifted upward. The documented trade-off is real in
principle but never fires on this catalog — there is no song here that matches mood
exactly while missing energy badly enough for the gap to matter. Worth knowing before
"fixing" something that is not currently doing any harm.

### 6. Adding the two missing genre families

Six of the twelve genres have no related-tier partner. Added `{electronic, synthwave}`
and `{lofi, ambient}`, then tested with `genre=synthwave, mood=moody, energy=0.7`:

```
                    before    after
Night Drive Loop    25.90     25.90   [synthwave, exact]
Glass Tunnel         5.36    15.36   [electronic, now related]
Static Bloom         3.26     3.26
```

**Outcome:** *Glass Tunnel* moves out of the "matches almost nothing" band and into the
related tier where it belongs. This is a one-line change and is not currently applied —
it is left as a decision rather than an assumption, since genre adjacency is a taste
judgement, not a fact.

### 7. Turning off artist de-duplication

Using the lofi profile:

```
WITH de-dup (current)              WITHOUT de-dup
26.96  Midnight Coding  [LoRoom]   26.96  Midnight Coding  [LoRoom]
26.90  Library Rain               26.90  Library Rain
 6.76  Spacewalk Thoughts         25.00  Focus Flow       [LoRoom]
```

**Outcome:** without the rule, two of the top three are the same artist. The ranking is
*more accurate* — *Focus Flow* really is the third-best match at 25.00 — but the
playlist is worse. This is the one place where the system deliberately returns a less
accurate answer because it is a more useful one.

### 8. Trying to break the tests

After writing the test suite, five deliberate bugs were introduced one at a time to
check the tests would catch them: breaking the genre tier spacing, removing artist
de-duplication, making energy pass/fail, dropping mood scoring, and removing the float
conversion in `load_songs`.

**Outcome:** four were caught immediately. The genre-spacing mutation was **not** — all
37 tests still passed while the central guarantee of the design was broken. The cause
was a test that asserted `related == approx(GENRE_RELATED)` using the constant imported
from the module under test, so the expected value moved with the code and the assertion
could never fail. Replaced with two tests that assert the *invariant* instead: each
genre tier gap must exceed the total the lower-priority features can contribute. A test
that cannot fail is worse than no test, because it reports safety that is not there.

---

## Limitations and Risks

### The one that matters most: nothing here measures whether the recommendations are *good*

76 tests pass. Every one of them checks that the system obeys the rules written for it —
that genre outranks mood, that scores and explanations agree, that no artist appears
twice. **Not one of them checks that a listener would enjoy the result**, because there is
no data in this project that could answer that. There are no listening histories, no
ratings, no skips, no thumbs. The catalog has songs and the profiles are invented.

So the whole evaluation is internal consistency, not accuracy. A scoring rule can be
perfectly self-consistent and still have terrible taste. Every claim in this README of the
form "this ranking is better" is an argument from design intuition, and should be read
that way. The honest summary: *this system does what I told it to; whether what I told it
is right is untested.*

### Known defects

Found by adversarial probing, confirmed by running them. All five are open.

| # | Defect | Effect |
|---|---|---|
| 1 | `load_songs` accepts `NaN` and `Infinity` | `float("NaN")` succeeds, so the "not a number" guard misses them. A row with `acousticness=1e400` parses as `inf`, clears the 0.5 threshold, earns the acoustic point and scores **21.00** — outranking clean songs |
| 2 | No duplicate-`id` check | Three rows with `id=7` load without complaint. `test_load_songs_gives_every_song_a_unique_id` asserts uniqueness of *the shipped catalog*, not of the function — a data assertion wearing a function's name |
| 3 | Artist de-dup misses spelling variants | `_normalise` maps hyphen→space, so `LoRoom`→`loroom` but `Lo-Room`→`lo room`. Same artist, both survive the filter |
| 4 | Out-of-range `target_energy` fails silently | `energy=80` (meaning 0.80 on a 0–100 scale) drives closeness negative for every song; `max(0.0, …)` clamps all of them to **+0.00**. The tie-breaker the cascade depends on vanishes, with no error, while the explanation still prints `energy 0.82 vs target 80.00 (+0.00)` |
| 5 | Only the ASCII hyphen is normalised | `Indie-Pop` scores 20.0; `Indie–Pop` with an en or em dash scores 0.0 |

Defects 1 and 4 share a shape worth naming: **the system's failure mode is silence.** It
does not crash or warn on bad input — it returns a confident, well-formatted, fully
explained ranking that is quietly wrong. That is the more dangerous kind of bug, because
nothing downstream can detect it.

### It cannot say "I don't have anything for you"

Asked for `genre=polka`, which no song matches, the output is formatted identically to a
perfect match:

```
5.96  Sunrise City    mood matches happy (+4); energy 0.82 vs target 0.80 (+1.96)
5.92  Rooftop Lights  mood matches happy (+4); energy 0.76 vs target 0.80 (+1.92)
```

A 5.96 and a 26.96 look the same to anyone reading the list. There is no threshold below
which the system declines to recommend, and no signal that the top result is merely the
least bad of twenty wrong answers. Real recommenders need that floor.

### Deliberate trade-offs, restated as costs

- **One song per artist costs real accuracy.** For the Deep Intense Rock profile, *Slow
  Collapse* scores **26.80** — the second-best match in the catalog — and is dropped
  because *Storm Runner* by the same artist already charted. Third place goes to a 5.92
  bluegrass track. The listener gets variety they did not ask for, at the price of the
  match they did.
- **Mood is deliberately not absolute**, so a related mood with good energy can beat an
  exact mood with bad energy. Experiment 5 showed this never fires on the current
  catalog — which means the trade-off is untested in practice, not that it is safe.
- **Three of five numeric columns are ignored.** `tempo_bpm` and `danceability` were
  dropped as redundant and `valence` is held in reserve. A listener who cares about tempo
  has no way to say so.
- **One genre, one mood, one energy.** The profile cannot express "pop *or* rock", "happy
  but not frantic", or any change of mood across a day.

### Data limitations

20 songs, 12 genres, 12 artists — a median of under two songs per genre. Conclusions drawn
from a catalog this size are anecdotes with decimal points. Experiment 2 showed how fragile
this is: adding ten songs moved `energy ↔ acousticness` from −0.99 to −0.69, changing which
features were worth scoring at all. Another ten songs could move it again.

Seven of the twelve artists have more than one track, so the de-dup rule is not an edge
case here — it is suppressing something in almost every list.

### Where bias and unfairness enter

**The genre families are one person's taste, encoded as fact.** `{pop, indie pop}`,
`{folk, bluegrass}`, `{r&b, hip hop}` are assertions about which music is "close to" which,
written by me, with no listener input. Grouping r&b with hip hop rather than with soul or
pop is a cultural judgment, and the system presents it to users as a neutral property of
the music. README experiment 6 left two more families unapplied for exactly this reason —
but the three that *are* applied were never held to the same standard.

**That judgment distributes advantage unevenly.** Only 6 of 12 genres have a related-tier
partner:

| Has a partner | No partner |
|---|---|
| pop, indie pop, folk, bluegrass, r&b, hip hop | lofi, rock, ambient, jazz, synthwave, electronic |

A song in a covered genre can score up to **17.00** for a listener who asked for its
partner. A song in an uncovered genre is capped at **7.00** against any query but its own
exact name. Six genres are structurally locked out of the middle tier — not because the
music is less similar to anything, but because nobody wrote their row in the table. An
artist's reach depends on whether their genre has a well-connected label.

**Scale would make this worse, not better.** On 20 songs a missing family is a curiosity.
On 20,000, the uncovered genres become systematically harder to discover, and since
discovery drives plays, the gap compounds. This system has no popularity signal, so it
cannot yet produce a rich-get-richer loop — but adding one without first fixing the family
table would bake the existing advantage into the feedback.

**The de-dup rule redistributes exposure, and that is a choice too.** Capping every artist
at one slot helps artists with a single strong track and penalises a prolific artist whose
catalog genuinely fits the listener. *Neon Echo* has three tracks and can never place more
than one. Defensible — but it is the system deciding how attention is shared, not the
listener.

### What would move this past guesswork

Ground truth. Even a dozen listeners rating a dozen lists would turn every "this ranking is
better" claim in this README into something falsifiable. Until then the right posture is
that the design is *reasoned*, not *validated*.

You will go deeper on this in your model card.

---

## Reflection

Read and complete `model_card.md`:

[**Model Card**](model_card.md)

Write 1 to 2 paragraphs here about what you learned:

- about how recommenders turn data into predictions
- about where bias or unfairness could show up in systems like this



The profiles

┌─────────────────────────┬───────┬────────────┬────────┬──────────┐
│         Profile         │ genre │    mood    │ energy │ acoustic │
├─────────────────────────┼───────┼────────────┼────────┼──────────┤
│ High-Energy Pop         │ pop   │ happy      │ 0.90   │ no       │
├─────────────────────────┼───────┼────────────┼────────┼──────────┤
│ Chill Lofi              │ lofi  │ chill      │ 0.35   │ yes      │
├─────────────────────────┼───────┼────────────┼────────┼──────────┤
│ Deep Intense Rock       │ rock  │ intense    │ 0.90   │ no       │
├─────────────────────────┼───────┼────────────┼────────┼──────────┤
│ Acoustic Folk Wind-Down │ folk  │ melancholy │ 0.30   │ yes      │
└─────────────────────────┴───────┴────────────┴────────┴──────────┘

I added a fourth beyond the three you named — folk/bluegrass is the only family that exercises the related tier and the artist de-dup rule simultaneously, which turned out to matter.

What each listener actually gets

High-Energy Pop — clean cascade, pop → indie pop → everything else.
26.84  Sunrise City        [pop/happy]         genre +20; mood +4; energy 0.82 vs 0.90 +1.84; produced +1
22.94  Gym Hero            [pop/intense]       genre +20; energy 0.
16.72  Rooftop Lights      [indie pop/happy]   indie pop close to pop +10; mood +4; energy +1.72; produced +1
 4.58  Corner Store Kings  [hip hop/confident]
 2.98  Storm Runner        [rock/intense]

Chill Lofi — hits exactly 27.00, the documented ceiling, on real data. All four features match.
27.00  Library Rain        [lofi/chill]   genre +20; mood +4; energc +1
26.86  Midnight Coding     [lofi/chill]
 6.86  Spacewalk Thoughts  [ambient/chill]

Deep Intense Rock — the most revealing. Both rock songs are by Voltllapse at 26.80 — the second-best match in the whole catalog — andthird place falls to a 5.92 bluegrass track.
26.98  Storm Runner           [rock/intense]      Voltline
 6.94  Gym Hero               [pop/intense]       <- 20-point cliff
 5.92  Barn Burner Breakdown  [bluegrass/intense]
suppressed: 26.80 Slow Collapse [Voltline]                                                                                                                          
Acoustic Folk Wind-Down — same trade-off, sharper. Barn Burner Breakdown (bluegrass, related tier, 11.88) is suppressed because Copper Holler already charted, so a 6.94 ambient song takes third.
26.98  Paper Planes Fade  [folk/melancholy]
22.56  Dust Road Hymn     [folk/relaxed]      Copper Holler
 6.94  Static Bloom       [ambient/melancholy]
suppressed: 11.88 Barn Burner Breakdown [Copper Holler]