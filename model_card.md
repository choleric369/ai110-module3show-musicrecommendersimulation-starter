# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name

**Cascade 1.0**

Named for how it decides: features are applied in a strict priority order — genre, then
mood, then energy, then acoustic preference — and each one only breaks ties left by the
one above it. The ranking falls through the levels like water down steps.

---

## 2. Intended Use

Cascade takes a listener's stated taste — one genre, one mood, a target energy level, and
whether they prefer acoustic or produced music — and ranks a fixed catalog of songs
against it, returning the top 5 with a plain-English reason for each.

**Who it is for: nobody yet.** This is a classroom exercise, not a product. It has never
been shown to a listener, and no part of the project measures whether its recommendations
are enjoyable — only whether they follow the rules it was given. Deploying this to real
users would mean shipping a system whose quality has never been tested.

**What it assumes about the user**, all of which are shaky:

- That they can name their taste in a single genre and a single mood. Real taste is not
  one word, and it changes across a day.
- That they use the same vocabulary the catalog uses. Someone who asks for "energetic" or
  "upbeat" gets worse results than someone who happens to say "intense", even for
  identical taste.
- That they can express intensity as a number between 0 and 1. Nothing tells them this,
  and getting it wrong fails silently — see §6.
- That the system has something for them at all. It has no way to answer "nothing here
  fits you."

---

## 3. How the Model Works

Imagine you ask a friend who knows your music taste for five songs.

The first thing they check is **genre**. If you asked for rock, they start with the rock
songs — and nothing else is going to jump ahead of a rock song, no matter how well it fits
you otherwise. A jazz track that nails your mood and energy perfectly is still jazz, and
you asked for rock. This is the single most important rule in the system.

Then, among songs that tie on genre, they look at **mood** — does it suit the moment?
After that, **energy**: how intense is it, compared to how intense you wanted? Energy
isn't treated as a yes-or-no question, because it shouldn't be. A song at 0.42 when you
asked for 0.40 is basically what you wanted, and it scores almost as if it were perfect.
Last, a small nudge for whether the song is **acoustic or produced**, which mostly just
settles ties.

Two refinements make it less rigid than plain matching:

**Near-misses get partial credit.** If you ask for pop, an indie pop song is clearly a
better answer than a bluegrass one — so related genres earn half credit. Same for moods:
"relaxed" and "chill" describe the same evening, so a user who asks for one still sees the
other. This matters more than it sounds. The catalog doesn't contain the word "calm" at
all, so without this rule, a user asking for calm music would get nothing relevant.

**Each song is judged alone.** The system scores every song without looking at any other
song, then sorts afterwards. That keeps the logic honest and means it would work the same
way on twenty thousand songs as on twenty.

Finally, **one song per artist**. Without that rule a top-5 can be half the same artist —
technically the best five matches, but a boring playlist.

Every recommendation comes with its reasons, and the reasons are collected *while* the
score is being added up rather than reconstructed afterwards. So the explanation can't
drift away from the number it's explaining.

**What changed from the starter logic.** The starter added features together with similar
weights. I made the weights deliberately lopsided — genre is worth so much more than
everything below it that the lower features can never overturn it. I added the "related"
middle tier for genre and mood, made energy a sliding scale instead of a threshold, and
added the one-song-per-artist rule. I also expanded the catalog, which turned out to
matter more than any code change (see §4).

---

## 4. Data

`data/songs.csv` — **20 songs, 12 genres, 12 artists**, hand-authored for this project.
Each song carries a genre, a mood, and five numbers: energy, tempo, valence,
danceability, and acousticness.

**Genres** (count): lofi 3; ambient, folk, jazz, pop, rock, synthwave 2 each; bluegrass,
electronic, hip hop, indie pop, r&b 1 each.
**Moods**: intense 4; chill 3; confident, melancholy, moody, relaxed, romantic 2 each;
focused 1.

**I added data, and it was the highest-leverage change in the project.** The starter
catalog of 10 songs had a hidden problem: its audio columns were nearly the same signal.
Energy and acousticness correlated at **−0.99**, energy and tempo at **+0.96**. Scoring
all of them wouldn't have been four signals — it would have been one signal counted four
times, quietly drowning out genre and mood. I wrote ten songs chosen specifically to break
those correlations: a loud acoustic bluegrass track, a quiet electronic one, a slow heavy
rock song, a fast weightless ambient one. Afterwards no pair correlated above 0.69.

That fixed the problem by changing the data rather than the code, which is worth
underlining: the model was never broken: the catalog was.

**What's missing from musical taste here:**

- **Scale.** 20 songs with a median under two per genre. Any conclusion drawn from a
  catalog this size is an anecdote with decimal points.
- **Anything about the music itself** — no lyrics, no language, no vocals-vs-instrumental,
  no era, no live-vs-studio, no key or time signature.
- **Whole territories of music.** No classical, metal, country, reggae, punk, gospel,
  reggaeton, afrobeats, K-pop, or any non-English-language music. The artist names and
  song titles are all English-coded. A catalog this narrow cannot represent "music," only
  a slice of Anglophone popular music.
- **Anything social** — no popularity, no release date, no listening history, no sense of
  what a song means to anyone.
- **Ground truth.** No ratings, no skips, no plays. Nothing in this dataset could tell me
  whether a recommendation was good.

---

## 5. Strengths

**The priority design does exactly what it was built to do.** I tested it under maximum
pressure: a song in the right genre and wrong on everything else, against a song in the
wrong genre but perfect on everything else. Right genre scored **20.00**, wrong genre
**7.00**. No combination of lesser features can overturn a genre match — the point gaps
are spaced so it's arithmetically impossible, not just unlikely.

**It works well for a listener whose taste matches the catalog's vocabulary.** Four test
profiles, four sensible lists:

| Profile | Top pick | Score |
|---|---|---|
| High-Energy Pop | Sunrise City `[pop/happy]` | 26.84 |
| Chill Lofi | Library Rain `[lofi/chill]` | **27.00** |
| Deep Intense Rock | Storm Runner `[rock/intense]` | 26.98 |
| Acoustic Folk Wind-Down | Paper Planes Fade `[folk/melancholy]` | 26.98 |

Chill Lofi is the satisfying one: *Library Rain* hits **27.00**, the exact theoretical
ceiling, matching all four features perfectly. And the cascade is visible in the gaps — for
the rock listener, first place is 26.98 and second is 6.94. That cliff *is* genre priority,
legible at a glance.

**The near-miss tier earns its place.** For the pop listener, *Rooftop Lights* (indie pop)
places third at 16.72 — above every non-pop song, below every actual pop song. Removing
the tier costs it the full 10 points, dropping it to 6.72, down among the rock and hip hop
tracks it has nothing in common with. That's exactly the distinction between "wrong genre"
and "nearly right genre."

**Explanations are trustworthy by construction.** Because reasons are collected during
scoring, the quoted points always sum to the displayed score. There's a test asserting it
across every profile, and it isn't decorative — it's checking a real invariant.

**The scoring is genuinely order-independent.** Each song is scored in isolation, so the
logic would scale to a much larger catalog unchanged.

---

## 6. Limitations and Bias

The README's *Limitations and Risks* section covers this at length. The essentials:

### Defects I know about and have not fixed

1. **Bad numbers load silently.** `NaN` and `Infinity` pass the "is this a number" check. A
   row with an infinite acousticness clears the acoustic threshold and scores 21.00,
   outranking clean songs.
2. **Duplicate song IDs are never checked.** Three rows with the same ID load without
   complaint. Worse, the test named for this asserts that *the shipped catalog* has unique
   IDs — not that the loader enforces it. It's a data assertion wearing a function's name,
   and it would pass no matter how broken the loader got.
3. **Artist de-duplication misses spelling variants.** "LoRoom" and "Lo-Room" are treated
   as different artists, so both survive the one-per-artist filter.
4. **An out-of-range energy value kills the feature silently.** A user who enters `80`
   meaning 80% gets *zero* energy points on every song. The tie-breaker the design depends
   on simply vanishes — no error, and the explanation still prints as though it worked.
5. **Only the plain hyphen is understood.** "Indie-Pop" matches; "Indie–Pop" with a
   typographic dash scores zero.
6. **The README documents a mood family that doesn't exist in the code.** It claims
   `intense / energetic` are grouped. They aren't. A user asking for "energetic" scores
   **0.0** against an intense song, where the documentation promises partial credit.

Defects 1 and 4 share a shape that worries me more than either alone: **this system's
failure mode is silence.** It doesn't crash on bad input — it returns a confident,
well-formatted, fully explained ranking that happens to be wrong. Nothing downstream could
detect that.

### Features it does not consider

Tempo and danceability were deliberately dropped as redundant, and valence is computed but
never used — so three of the five audio columns are ignored. A listener who cares about
tempo has no way to say so. The profile also can't express more than one genre, more than
one mood, or any dislikes.

### It cannot decline

Asked for a genre no song matches, Cascade returns five songs formatted exactly like a
perfect match. A 5.96 and a 26.96 are visually identical in the output. There is no
threshold below which it says "I don't have anything for you," which means it is always
confident and sometimes baselessly so.

### Where unfairness enters

**The similarity tables are one person's taste presented as fact.** I decided that pop
goes with indie pop, folk with bluegrass, and r&b with hip hop. No listener was consulted.
Pairing r&b with hip hop rather than with soul or pop is a cultural judgment, and the
system shows it to users as if it were a neutral property of the music.

**That judgment hands out advantage unevenly**, and I can quantify it:

| | Genres with a related partner | Genres without |
|---|---|---|
| **Genre** | pop, indie pop, folk, bluegrass, r&b, hip hop | lofi, rock, ambient, jazz, synthwave, electronic |
| **Mood** | chill, calm, relaxed, focused, happy, confident, moody, melancholy | **intense, romantic** |

A song in a covered genre can score up to **17.00** for a listener who asked for its
partner. A song in an uncovered genre is capped at **7.00** against any query but its own
exact name. Six of twelve genres are locked out of the middle tier — not because the music
is less similar to anything, but because nobody wrote their row in the table. The same
holds for moods: *intense* and *romantic* have no family, so **6 of 20 songs** can never
earn mood partial credit at all — and that includes *intense*, the most common mood in the
catalog.

So an artist's reach depends on whether their genre happens to have a well-connected
label. That's a small injustice in a 20-song classroom catalog. At 20,000 songs, the
uncovered genres become systematically harder to discover — and since discovery drives
plays, the gap compounds. Cascade has no popularity signal today, so it can't yet produce
a rich-get-richer loop; adding one without first fixing these tables would bake the
existing advantage into the feedback.

**De-duplication redistributes exposure, which is also a choice.** Capping each artist at
one slot helps artists with a single strong track and penalises a prolific artist whose
catalog genuinely fits the listener. Seven of twelve artists here have multiple tracks, so
this is firing constantly, not occasionally.

**Overfitting to one preference is the design, not a bug.** Genre is so dominant that
Cascade is effectively a genre filter with tie-breakers. A listener with narrow genre
taste is served well; a listener who describes themselves by mood ("I want something
melancholy, I don't care what style") is served badly, because the feature they care about
is worth at most 4 points against genre's 20.

---

## 7. Evaluation

**76 automated tests**, in two layers: 39 unit tests on the individual pieces using
synthetic songs, and 37 end-to-end tests running four named listener profiles against the
real catalog.

**Profiles tested:** High-Energy Pop, Chill Lofi, Deep Intense Rock, and Acoustic Folk
Wind-Down. The fourth exists because folk/bluegrass is the only pairing that exercises the
related-genre tier and the artist de-duplication rule at the same time.

**What I checked:** that each listener's top pick is in the genre they asked for; that no
out-of-genre song ever outranks an in-genre one; that results are ordered, capped at *k*,
free of repeated artists, and inside the documented 0–27 range; that the points quoted in
each explanation sum to the score displayed beside it; and that four different listeners
get four genuinely different lists — a guard against a recommender that quietly ignores its
input.

I also ran **adversarial probes** against the specific claims the README makes, rather than
testing randomly. That's where all six defects in §6 came from. Four claims survived
unscathed: genre priority really is absolute, the 27.00 ceiling is exact, an empty profile
degrades gracefully instead of crashing, and the falsy-value trap is handled correctly —
`energy=0` and `likes_acoustic=False` both score rather than being mistaken for absent.

**Mutation testing.** Passing tests prove nothing until you've watched them fail, so I
deliberately broke the code to see whether the suite would notice. Flattening the genre
weights failed 8 tests; disabling artist de-duplication failed 6. Both were reverted and
the source confirmed unchanged.

### What surprised me

**A test that could not fail.** After writing the suite I introduced five deliberate bugs
to check it would catch them. Four were caught instantly. The fifth — breaking the genre
spacing that the entire design rests on — was missed, and all 37 tests still passed. The
cause: the test compared the score against the very constant it was supposed to be
checking, imported from the module under test. When the constant moved, the expectation
moved with it. The assertion was incapable of failing. I replaced it with tests that assert
the *invariant* instead: each genre tier gap must exceed everything the lower features can
contribute combined. **A test that cannot fail is worse than no test, because it reports
safety that isn't there.**

**A documented trade-off that never actually fires.** The README explains that mood is
deliberately softer than genre, so a related mood with great energy can beat an exact mood
with poor energy. I raised mood's weights to make it strict and expected the rankings to
shift. Nothing moved — every ranking came out in exactly the same order. The trade-off is
real in principle but never triggers on this catalog. I'd been documenting a behaviour I
had never observed.

**De-duplication costing more than I expected.** For the rock listener, *Slow Collapse*
scores 26.80 — the second-best match in the entire catalog — and gets dropped because the
same artist already charted. Third place goes to a 5.92 bluegrass track instead. The
system is knowingly returning a less accurate answer, and I'm still not certain that's the
right call.

---

## 8. Future Work

**Fix the six defects first.** None are hard; leaving them documented but unfixed is a
choice I'd reverse before anyone used this. Reject non-finite numbers at load, enforce
unique IDs in the loader rather than in a test that checks the data, normalise typographic
dashes, validate that energy is within 0–1, and either add the `intense/energetic` mood
family or correct the README that promises it.

**Add a confidence floor.** Below some score, the honest output is "nothing here fits
you." Shipping a confident top-5 of bad matches trains users to distrust the whole list.

**Stop inventing the similarity tables.** The genre and mood families should come from
listener data — co-listening patterns, or even a handful of people sorting genre cards into
piles — rather than from my assumptions. At minimum, every genre and mood should have a
partner, so the middle tier stops being a privilege of six of twelve.

**Let taste be plural.** Accept several genres, several moods, a range rather than a point
for energy, and explicit dislikes. "Pop or indie, upbeat but not frantic, nothing acoustic"
is a normal sentence that Cascade cannot currently hear.

**Make diversity adjustable rather than absolute.** One-song-per-artist is a blunt rule
that cost the rock listener a 26.80 match. A tunable penalty for repeats — rather than a
hard cap — would keep variety without discarding excellent matches outright.

**Get ground truth, however small.** A dozen listeners rating a dozen lists would turn
every "this ranking is better" claim in this project from an argument into a measurement.
This is the one item that would change the character of the work rather than just improve
it.

**Use valence, or remove it.** It's the one audio column that carries independent
information (+0.19 against energy) and it's currently computed and ignored.

---

## 9. Personal Reflection

> *Draft — rewrite this in your own voice before submitting. The observations are drawn
> from what actually happened while building the project, but the conclusions should be
> yours.*

The thing I expected to learn was how to design a scoring rule. What I actually learned is
that the scoring rule was the easy part.

The single biggest improvement I made involved no code at all. I'd been tuning weights,
when the real problem was that my catalog's audio features were all measuring the same
thing — energy and acousticness correlated at −0.99, so a user's acoustic preference could
never disagree with their energy preference. Adding ten carefully chosen songs fixed what
no amount of weight-tuning would have. The model wasn't broken; the data was. I don't think
I'd have believed how much of a recommender's behaviour lives in its dataset rather than
its algorithm if I hadn't watched it happen.

The most uncomfortable discovery was the test that couldn't fail. It compared the output
against the same constant it was meant to be checking, so when I deliberately broke the
core guarantee of the design, all 37 tests stayed green. A green suite had felt like proof.
It was proof of nothing — and I only found out because I went looking for ways to break
things on purpose. I now think "did the tests pass?" is a much weaker question than "have I
seen these tests fail?"

On bias: I came in expecting unfairness in a recommender to be something subtle, buried in
statistics. In mine it's three lines of code. I decided pop belongs with indie pop, folk
with bluegrass, r&b with hip hop — and in doing so, I quietly gave six genres a path to
being recommended that the other six don't have. A lofi song is capped at 7 points for
anyone who doesn't name lofi exactly; a pop song can earn 17 from someone who asked for
indie pop. I didn't intend to rank genres by how discoverable they'd be. I did it anyway,
in a table I wrote in about a minute, and I only noticed because I went looking for it
afterwards. Scaled up, with a feedback loop, that minute of unexamined assumption decides
whose music gets heard.

What's changed is how I read the apps I use. When Spotify tells me why it picked something,
I now wonder which features it's quietly ignoring, whose similarity judgments are encoded
in it, and whether anyone ever checked that the explanation matches the actual reason. Mine
does — but only because I built it that way on purpose, and I can see precisely how easy it
would have been not to.
