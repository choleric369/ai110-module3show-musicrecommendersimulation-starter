import csv
import math
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict

# Columns every row of data/songs.csv must provide.
REQUIRED_COLUMNS = (
    "id", "title", "artist", "genre", "mood",
    "energy", "tempo_bpm", "valence", "danceability", "acousticness",
)

# Columns that must be converted from text to numbers before scoring.
NUMERIC_COLUMNS = ("energy", "tempo_bpm", "valence", "danceability", "acousticness")

# Numeric columns that are proportions and must land in [0.0, 1.0]. tempo_bpm is
# excluded - it is a rate, not a proportion, and has no fixed upper bound.
UNIT_INTERVAL_COLUMNS = ("energy", "valence", "danceability", "acousticness")

# ---------------------------------------------------------------------------
# Scoring configuration
#
# Features are applied in priority order: genre > mood > energy > acoustic.
# The point ranges are spaced so a higher-priority feature cannot be out-voted
# by everything below it: mood + energy + acoustic max out at 7.0, which is less
# than the 10.0 gap between genre tiers. See README "How The System Works".
# ---------------------------------------------------------------------------
GENRE_EXACT = 20.0
GENRE_RELATED = 10.0
MOOD_EXACT = 4.0
MOOD_RELATED = 2.0
ENERGY_WEIGHT = 2.0
ACOUSTIC_WEIGHT = 1.0

# A song counts as "acoustic" above this acousticness value. The catalog splits
# cleanly either side of it - no song sits between 0.44 and 0.64.
ACOUSTIC_THRESHOLD = 0.5

# Genres close enough to earn partial credit instead of nothing.
GENRE_FAMILIES = (
    {"pop", "indie pop"},
    {"folk", "bluegrass"},
    {"r&b", "hip hop"},
)

# Moods that describe the same listening state. Words no song uses - "calm",
# "energetic" - are listed deliberately, so a user who asks for one still matches
# the family the catalog does use.
#
# "romantic" has no family on purpose. Nothing in the catalog is clearly adjacent
# to it, and inventing a partner would be a taste judgement rather than a fact.
MOOD_FAMILIES = (
    {"calm", "chill", "relaxed", "focused"},
    {"happy", "confident"},
    {"moody", "melancholy"},
    {"intense", "energetic"},
)

# Every character a catalog or a user might reasonably use as a hyphen: the ASCII
# hyphen-minus plus the typographic dashes word processors substitute for it.
# Without the full set, "Indie-Pop" matches and "Indie-Pop" with an en dash does not.
_DASHES = "-‐‑‒–—―−"
_DASH_TO_SPACE = {ord(dash): " " for dash in _DASHES}


def _normalise(value) -> str:
    """Lowercase, trim, and treat any dash as a space so 'Indie-Pop' == 'indie pop'."""
    return " ".join(str(value).translate(_DASH_TO_SPACE).lower().split())


def _artist_key(name) -> str:
    """
    Identity key for the one-song-per-artist rule.

    Stricter than _normalise: it drops separators entirely, so "LoRoom",
    "Lo-Room" and "Lo Room" collapse to one artist. _normalise alone turns the
    hyphen into a space and leaves 'lo room' != 'loroom', which let the same
    artist appear twice in a single list.
    """
    return "".join(ch for ch in _normalise(name) if ch.isalnum())


def _are_related(a: str, b: str, families: Tuple[set, ...]) -> bool:
    """True if both values appear in the same family group."""
    return any(a in family and b in family for family in families)

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool

def _profile_to_prefs(user: UserProfile) -> Dict:
    """
    Translates a UserProfile into the preference dict score_song expects.

    The two halves of this project name the same four preferences differently:
    UserProfile uses favorite_genre/favorite_mood/target_energy/likes_acoustic,
    while src/main.py sends genre/mood/energy. This is the single place that
    bridges them, so the scoring rules live in exactly one function.
    """
    return {
        "genre": user.favorite_genre,
        "mood": user.favorite_mood,
        "energy": user.target_energy,
        "likes_acoustic": user.likes_acoustic,
    }


class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py

    Wraps the same scoring rules used by the functional path rather than
    repeating them, so the two can never disagree about what a song is worth.
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def score(self, user: UserProfile, song: Song) -> float:
        """Points this song earns against the profile. See score_song()."""
        return score_song(_profile_to_prefs(user), asdict(song))[0]

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """
        Returns the k best-matching songs, highest score first.

        Unlike recommend_songs(), this does NOT limit results to one song per
        artist - tests/test_recommender.py builds a catalog where every song
        shares an artist and expects all of them back. Use recommend_songs()
        when you want a varied listening list.
        """
        if k <= 0:
            return []

        # Stable sort: songs on equal scores keep their catalog order, so the
        # result is the same on every run.
        ranked = sorted(self.songs, key=lambda s: self.score(user, s), reverse=True)
        return ranked[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """
        Says in plain language why this song suits this profile.

        Built from the reasons score_song collected while adding up the score,
        so the explanation can never disagree with the number.
        """
        _, reasons = score_song(_profile_to_prefs(user), asdict(song))
        return _explain(reasons)

def load_songs(csv_path: str) -> List[Dict]:
    """
    Loads songs from a CSV file.
    Required by src/main.py

    Returns one dict per song. Text columns stay as strings; id becomes an int and
    the five audio columns become floats, so scoring can do arithmetic on them
    without converting first.

    Raises FileNotFoundError if the file is missing, and ValueError if the header
    is missing a column, a row holds a value that is not a finite number, a
    proportion falls outside 0.0-1.0, or two rows share an id.

    "Not a number" has to mean more than "float() refused it": float("NaN") and
    float("Infinity") both succeed. An infinite acousticness would clear the
    acoustic threshold and an infinite energy would silently score zero, so both
    are rejected at the door rather than ranked.
    """
    songs: List[Dict] = []
    id_lines: Dict[int, int] = {}

    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"{csv_path} is missing required column(s): {', '.join(missing)}"
            )

        # Data starts on line 2, because line 1 is the header.
        for line_no, row in enumerate(reader, start=2):
            # Ignore blank lines, including the trailing newline at end of file.
            if not any((row.get(c) or "").strip() for c in REQUIRED_COLUMNS):
                continue

            song = {c: (row.get(c) or "").strip() for c in REQUIRED_COLUMNS}

            try:
                song["id"] = int(song["id"])
                for column in NUMERIC_COLUMNS:
                    song[column] = float(song[column])
            except ValueError as exc:
                raise ValueError(f"{csv_path} line {line_no}: {exc}") from exc

            # float() accepts "NaN" and "Infinity". Scoring cannot.
            for column in NUMERIC_COLUMNS:
                if not math.isfinite(song[column]):
                    raise ValueError(
                        f"{csv_path} line {line_no}: {column} is "
                        f"{row[column].strip()!r}, which is not a finite number"
                    )

            for column in UNIT_INTERVAL_COLUMNS:
                if not 0.0 <= song[column] <= 1.0:
                    raise ValueError(
                        f"{csv_path} line {line_no}: {column} is {song[column]}, "
                        f"which is outside the range 0.0 to 1.0"
                    )

            # Ids identify songs. Two rows sharing one makes any lookup ambiguous.
            if song["id"] in id_lines:
                raise ValueError(
                    f"{csv_path} line {line_no}: duplicate id {song['id']}, "
                    f"already used on line {id_lines[song['id']]}"
                )
            id_lines[song["id"]] = line_no

            songs.append(song)

    return songs

def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """
    Scores a single song against user preferences.
    Required by recommend_songs() and src/main.py

    Judges one song in isolation - it never looks at the other songs and never
    sorts. Ranking happens later, in recommend_songs().

    Recognised keys in user_prefs, all optional: "genre", "mood", "energy",
    "likes_acoustic". A key that is absent simply contributes no points, so a
    partial profile still produces a usable score.

    Returns (score, reasons) where reasons lists only the features that actually
    earned points, in priority order.
    """
    score = 0.0
    reasons: List[str] = []

    # --- Priority 1: genre -------------------------------------------------
    wanted_genre = user_prefs.get("genre")
    if wanted_genre:
        wanted = _normalise(wanted_genre)
        actual = _normalise(song["genre"])
        if actual == wanted:
            score += GENRE_EXACT
            reasons.append(f"genre matches {song['genre']} (+{GENRE_EXACT:.0f})")
        elif _are_related(actual, wanted, GENRE_FAMILIES):
            score += GENRE_RELATED
            reasons.append(
                f"{song['genre']} is close to {wanted_genre} (+{GENRE_RELATED:.0f})"
            )

    # --- Priority 2: mood --------------------------------------------------
    wanted_mood = user_prefs.get("mood")
    if wanted_mood:
        wanted = _normalise(wanted_mood)
        actual = _normalise(song["mood"])
        if actual == wanted:
            score += MOOD_EXACT
            reasons.append(f"mood matches {song['mood']} (+{MOOD_EXACT:.0f})")
        elif _are_related(actual, wanted, MOOD_FAMILIES):
            score += MOOD_RELATED
            reasons.append(
                f"{song['mood']} feels like {wanted_mood} (+{MOOD_RELATED:.0f})"
            )

    # --- Priority 3: energy ------------------------------------------------
    # Continuous, not pass/fail: 0.42 against a target of 0.40 is nearly perfect
    # and should score as such. This is what breaks ties inside a genre+mood tier.
    target_energy = user_prefs.get("energy")
    if target_energy is not None:
        # Out of range, every song clamps to +0.00 and the feature silently stops
        # discriminating - a profile asking for energy=80 (meaning 80%) would get
        # a confident ranking with the tie-breaker quietly switched off. Refuse it.
        try:
            target = float(target_energy)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"energy preference must be a number, got {target_energy!r}"
            ) from exc

        if not math.isfinite(target) or not 0.0 <= target <= 1.0:
            raise ValueError(
                f"energy preference must be between 0.0 and 1.0, got {target_energy!r}"
            )

        closeness = 1.0 - abs(song["energy"] - target)
        points = ENERGY_WEIGHT * max(0.0, closeness)
        score += points
        reasons.append(
            f"energy {song['energy']:.2f} vs target {target:.2f} (+{points:.2f})"
        )

    # --- Priority 4: acoustic ----------------------------------------------
    likes_acoustic = user_prefs.get("likes_acoustic")
    if likes_acoustic is not None:
        is_acoustic = song["acousticness"] > ACOUSTIC_THRESHOLD
        if is_acoustic == bool(likes_acoustic):
            score += ACOUSTIC_WEIGHT
            label = "acoustic" if is_acoustic else "produced"
            reasons.append(f"{label}, as preferred (+{ACOUSTIC_WEIGHT:.0f})")

    return score, reasons

def _explain(reasons: List[str]) -> str:
    """Turns the reasons collected during scoring into one readable sentence."""
    if not reasons:
        return "nothing in this song matches the profile"
    return "; ".join(reasons)


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """
    Functional implementation of the recommendation logic.
    Required by src/main.py

    Scores every song, ranks them, and returns the best k as
    (song, score, explanation) tuples.

    The order of the three steps matters. Sorting first guarantees the one song
    kept per artist is that artist's best match; cutting to k last guarantees a
    full list rather than a short one with holes.
    """
    if k <= 0:
        return []

    # 1. Judge every song on its own. No comparison happens here.
    scored = [(song, *score_song(user_prefs, song)) for song in songs]

    # 2. Rank. Python's sort is stable, so songs on equal scores keep catalog
    #    order and the output stays deterministic run to run.
    scored.sort(key=lambda item: item[1], reverse=True)

    # 3. Keep one song per artist, then cut to k.
    recommendations: List[Tuple[Dict, float, str]] = []
    seen_artists = set()

    for song, score, reasons in scored:
        if len(recommendations) >= k:
            break
        artist = _artist_key(song["artist"])
        if artist in seen_artists:
            continue
        seen_artists.add(artist)
        recommendations.append((song, score, _explain(reasons)))

    return recommendations
