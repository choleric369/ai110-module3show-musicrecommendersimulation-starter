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

The top *k* songs by score, with one extra rule: **at most one song per artist**. Six
artists in this catalog have multiple tracks, and without that rule a top-5 list can be
half the same artist — technically correct, practically useless.

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

Paste a sample of your recommender's output here as a text block so a reader can see what it produces:

```
# e.g.:
# User profile: genre=indie, mood=chill, energy=low
# Recommendations:
#   1. ...
#   2. ...
#   3. ...
```

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or demo video link here -->

---

## Experiments You Tried

Use this section to document the experiments you ran. For example:

- What happened when you changed the weight on genre from 2.0 to 0.5
- What happened when you added tempo or valence to the score
- How did your system behave for different types of users

---

## Limitations and Risks

Summarize some limitations of your recommender.

Examples:

- It only works on a tiny catalog
- It does not understand lyrics or language
- It might over favor one genre or mood

You will go deeper on this in your model card.

---

## Reflection

Read and complete `model_card.md`:

[**Model Card**](model_card.md)

Write 1 to 2 paragraphs here about what you learned:

- about how recommenders turn data into predictions
- about where bias or unfairness could show up in systems like this



