"""
Regression tests for the six defects found by adversarial probing.

Each defect is documented in README "Limitations and Risks" and model_card.md
section 6. One test class per defect, named for it, so a failure here says which
documented bug came back rather than just which assertion broke.

Four of the six were silent failures: the system returned a confident, fully
explained, wrongly ordered list instead of complaining. So most of these tests
assert that something now RAISES - the fix is that bad input becomes loud.
"""
from pathlib import Path

import pytest

from src.recommender import (
    load_songs,
    score_song,
    recommend_songs,
    _normalise,
    _artist_key,
    MOOD_FAMILIES,
    GENRE_FAMILIES,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = PROJECT_ROOT / "data" / "songs.csv"

HEADER = (
    "id,title,artist,genre,mood,energy,tempo_bpm,valence,danceability,acousticness"
)


def write_csv(path, *rows) -> str:
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def make_song(**overrides) -> dict:
    song = {
        "id": 1, "title": "Test Song", "artist": "Test Artist",
        "genre": "pop", "mood": "happy", "energy": 0.8, "tempo_bpm": 120.0,
        "valence": 0.5, "danceability": 0.5, "acousticness": 0.2,
    }
    song.update(overrides)
    return song


def error_text(excinfo) -> str:
    """
    The error message with the file path stripped off.

    Assert against this, never against the raw string. pytest names tmp_path
    directories after the test, so a raw assertion can be satisfied by the path
    instead of the message: "finite" appears in the directory name of
    test_non_finite_energy_is_rejected whether or not the error ever says it.
    That is the cannot-fail pattern from README section 8, and it hid a real
    hole here until a mutation run refused to go red.
    """
    return str(excinfo.value).split(".csv", 1)[-1]


# ---------------------------------------------------------------------------
# Defect 1: float() accepts "NaN" and "Infinity", so they loaded as valid data
# ---------------------------------------------------------------------------

class TestDefect1NonFiniteNumbers:
    @pytest.mark.parametrize("value", ["NaN", "nan", "Infinity", "inf", "-inf", "1e400"])
    def test_non_finite_energy_is_rejected(self, tmp_path, value):
        path = write_csv(
            tmp_path / "nonfinite.csv",
            f"1,Bad,Artist,pop,happy,{value},120,0.5,0.5,0.5",
        )

        with pytest.raises(ValueError) as excinfo:
            load_songs(path)

        assert "is not a finite number" in error_text(excinfo)
        assert "line 2" in error_text(excinfo)

    def test_infinite_acousticness_cannot_sneak_past_the_acoustic_threshold(self, tmp_path):
        """
        The original bug: acousticness=1e400 parsed as inf, cleared the 0.5
        threshold, earned the acoustic point and scored 21.00 - outranking
        clean songs.
        """
        path = write_csv(
            tmp_path / "inf_acoustic.csv",
            "1,Cheater,Artist,pop,happy,0.8,120,0.5,0.5,1e400",
        )

        with pytest.raises(ValueError):
            load_songs(path)

    @pytest.mark.parametrize("column,value", [
        ("energy", "1.5"), ("energy", "-0.1"), ("valence", "2.0"),
        ("danceability", "-1"), ("acousticness", "1.01"),
    ])
    def test_proportions_outside_zero_to_one_are_rejected(self, tmp_path, column, value):
        columns = {"energy": 5, "tempo_bpm": 6, "valence": 7,
                   "danceability": 8, "acousticness": 9}
        fields = ["1", "Song", "Artist", "pop", "happy", "0.5", "120", "0.5", "0.5", "0.5"]
        fields[columns[column]] = value
        path = write_csv(tmp_path / "range.csv", ",".join(fields))

        with pytest.raises(ValueError) as excinfo:
            load_songs(path)

        assert "0.0 to 1.0" in error_text(excinfo)
        assert column in error_text(excinfo)

    def test_tempo_is_not_held_to_the_zero_to_one_range(self, tmp_path):
        """tempo_bpm is a rate, not a proportion. 152 bpm must stay legal."""
        path = write_csv(
            tmp_path / "tempo.csv",
            "1,Fast,Artist,pop,happy,0.9,152,0.5,0.5,0.5",
        )

        assert load_songs(path)[0]["tempo_bpm"] == 152.0


# ---------------------------------------------------------------------------
# Defect 2: no duplicate-id check; the old test asserted the catalog, not the loader
# ---------------------------------------------------------------------------

class TestDefect2DuplicateIds:
    def test_duplicate_ids_are_rejected(self, tmp_path):
        path = write_csv(
            tmp_path / "dupes.csv",
            "7,First,Artist A,pop,happy,0.8,120,0.5,0.5,0.2",
            "7,Second,Artist B,pop,happy,0.8,120,0.5,0.5,0.2",
        )

        with pytest.raises(ValueError) as excinfo:
            load_songs(path)

        assert "duplicate id 7" in error_text(excinfo)

    def test_the_error_names_both_offending_lines(self, tmp_path):
        """A duplicate is only fixable if you know where both copies are."""
        path = write_csv(
            tmp_path / "dupes.csv",
            "1,First,Artist A,pop,happy,0.8,120,0.5,0.5,0.2",
            "2,Second,Artist B,pop,happy,0.8,120,0.5,0.5,0.2",
            "1,Third,Artist C,pop,happy,0.8,120,0.5,0.5,0.2",
        )

        with pytest.raises(ValueError) as excinfo:
            load_songs(path)

        message = error_text(excinfo)
        assert "line 4" in message       # where the duplicate was found
        assert "line 2" in message       # where the id was first used

    def test_the_loader_enforces_uniqueness_not_just_the_shipped_catalog(self):
        """
        The original test asserted that data/songs.csv happened to have unique
        ids - a property of the data, not of load_songs, so it would have passed
        no matter how broken the loader got. This asserts the guarantee itself.
        """
        assert len({s["id"] for s in load_songs(str(SONGS_CSV))}) == 20


# ---------------------------------------------------------------------------
# Defect 3: "LoRoom" and "Lo-Room" counted as different artists
# ---------------------------------------------------------------------------

class TestDefect3ArtistSpellingVariants:
    @pytest.mark.parametrize("spelling", ["LoRoom", "Lo-Room", "Lo Room", "LOROOM  ",
                                          "lo–room", "Lo  -  Room"])
    def test_every_spelling_collapses_to_one_artist_key(self, spelling):
        assert _artist_key(spelling) == "loroom"

    def test_one_artist_cannot_appear_twice_under_two_spellings(self):
        songs = [
            make_song(id=1, title="Track One", artist="LoRoom", energy=0.8),
            make_song(id=2, title="Track Two", artist="Lo-Room", energy=0.8),
            make_song(id=3, title="Track Three", artist="lo room", energy=0.8),
            make_song(id=4, title="Other Band", artist="Paper Lanterns", energy=0.8),
        ]

        results = recommend_songs({"genre": "pop"}, songs, k=5)

        assert len(results) == 2
        assert [s["title"] for s, _, _ in results] == ["Track One", "Other Band"]

    def test_genuinely_different_artists_are_still_kept_apart(self):
        """The fix must not over-merge: distinct names stay distinct."""
        songs = [
            make_song(id=1, title="A", artist="Neon Echo", energy=0.8),
            make_song(id=2, title="B", artist="Neon Echoes", energy=0.8),
            make_song(id=3, title="C", artist="Echo Neon", energy=0.8),
        ]

        assert len(recommend_songs({"genre": "pop"}, songs, k=5)) == 3


# ---------------------------------------------------------------------------
# Defect 4: out-of-range target energy silently zeroed the feature
# ---------------------------------------------------------------------------

class TestDefect4OutOfRangeEnergy:
    @pytest.mark.parametrize("target", [80, 1.5, -0.1, -1, 100, float("inf"), float("nan")])
    def test_energy_outside_zero_to_one_raises(self, target):
        with pytest.raises(ValueError) as excinfo:
            score_song({"energy": target}, make_song())

        assert "between 0.0 and 1.0" in str(excinfo.value)

    def test_the_scale_mistake_is_caught_rather_than_silently_ranked(self):
        """
        The original bug: energy=80 (a user meaning 80%) clamped every song to
        +0.00, switching off the tie-breaker while still printing a confident
        ranking. It must now fail loudly instead.
        """
        songs = load_songs(str(SONGS_CSV))

        with pytest.raises(ValueError):
            recommend_songs({"genre": "pop", "energy": 80}, songs, k=5)

    def test_a_non_numeric_energy_says_so(self):
        with pytest.raises(ValueError) as excinfo:
            score_song({"energy": "loud"}, make_song())

        assert "must be a number" in str(excinfo.value)

    @pytest.mark.parametrize("target", [0.0, 0.5, 1.0, "0.75"])
    def test_valid_energy_values_still_score(self, target):
        score, reasons = score_song({"energy": target}, make_song(energy=0.8))

        assert score > 0
        assert reasons

    def test_energy_zero_is_still_a_real_preference_not_a_missing_key(self):
        """Guards the falsy-value trap: 0.0 is valid input, not absence."""
        score, reasons = score_song({"energy": 0.0}, make_song(energy=0.8))

        assert score == pytest.approx(0.4)
        assert reasons


# ---------------------------------------------------------------------------
# Defect 5: only the ASCII hyphen was treated as a separator
# ---------------------------------------------------------------------------

class TestDefect5TypographicDashes:
    @pytest.mark.parametrize("label", [
        "Indie-Pop",            # ascii hyphen-minus
        "Indie‐Pop",       # hyphen
        "Indie‑Pop",       # non-breaking hyphen
        "Indie‒Pop",       # figure dash
        "Indie–Pop",       # en dash
        "Indie—Pop",       # em dash
        "Indie―Pop",       # horizontal bar
        "Indie−Pop",       # minus sign
        "  INDIE   pop  ",
    ])
    def test_every_dash_spelling_normalises_to_the_same_genre(self, label):
        assert _normalise(label) == "indie pop"

    @pytest.mark.parametrize("label", ["Indie-Pop", "Indie–Pop", "Indie—Pop"])
    def test_a_dashed_genre_still_earns_an_exact_match(self, label):
        score, _ = score_song({"genre": "indie pop"}, make_song(genre=label))

        assert score == pytest.approx(20.0)

    def test_a_dashed_user_query_matches_a_plain_catalog_genre(self):
        """The dash can arrive from either side - user input or the catalog."""
        score, _ = score_song({"genre": "Indie—Pop"}, make_song(genre="indie pop"))

        assert score == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Defect 6: README documented an intense/energetic mood family the code lacked
# ---------------------------------------------------------------------------

class TestDefect6DocumentedMoodFamily:
    def test_intense_and_energetic_are_in_the_same_family(self):
        assert any({"intense", "energetic"} <= family for family in MOOD_FAMILIES)

    def test_asking_for_energetic_earns_partial_credit_on_an_intense_song(self):
        """
        The README promised this tier. The code did not have it, so "energetic"
        scored 0.0 against an intense song.
        """
        score, reasons = score_song({"mood": "energetic"}, make_song(mood="intense"))

        assert score == pytest.approx(2.0)
        assert "energetic" in " ".join(reasons)

    def test_energetic_now_finds_the_catalogs_intense_songs(self):
        songs = load_songs(str(SONGS_CSV))

        results = recommend_songs({"mood": "energetic", "energy": 0.9}, songs, k=3)
        moods = [s["mood"] for s, _, _ in results]

        assert "intense" in moods

    def test_an_exact_mood_still_beats_the_related_one(self):
        """Adding a family must not flatten the tier it belongs to."""
        exact, _ = score_song({"mood": "intense"}, make_song(mood="intense"))
        related, _ = score_song({"mood": "energetic"}, make_song(mood="intense"))

        assert exact > related

    def test_romantic_is_deliberately_left_without_a_family(self):
        """
        Documented choice, not an oversight: nothing in the catalog is clearly
        adjacent to romantic, and inventing a partner would be a taste judgement.
        If a family is added later, update model_card.md section 6 with it.
        """
        covered = set().union(*MOOD_FAMILIES)

        assert "romantic" not in covered


# ---------------------------------------------------------------------------
# The fixes must not have broken the catalog or the guarantees above them
# ---------------------------------------------------------------------------

class TestFixesLeftTheSystemIntact:
    def test_the_shipped_catalog_still_loads_completely(self):
        songs = load_songs(str(SONGS_CSV))

        assert len(songs) == 20
        assert all(0.0 <= s["energy"] <= 1.0 for s in songs)
        assert all(s["tempo_bpm"] > 0 for s in songs)

    def test_genre_priority_is_still_absolute(self):
        prefs = {"genre": "pop", "mood": "happy", "energy": 1.0, "likes_acoustic": False}
        right = score_song(prefs, make_song(genre="pop", mood="moody",
                                            energy=0.0, acousticness=0.9))[0]
        wrong = score_song(prefs, make_song(genre="polka", mood="happy",
                                            energy=1.0, acousticness=0.1))[0]

        assert right > wrong

    def test_the_documented_ceiling_is_unchanged(self):
        score, _ = score_song(
            {"genre": "pop", "mood": "happy", "energy": 1.0, "likes_acoustic": True},
            make_song(genre="pop", mood="happy", energy=1.0, acousticness=0.9),
        )

        assert score == pytest.approx(27.0)

    def test_adding_a_mood_family_did_not_disturb_the_genre_families(self):
        assert len(GENRE_FAMILIES) == 3
        assert {"pop", "indie pop"} in GENRE_FAMILIES
