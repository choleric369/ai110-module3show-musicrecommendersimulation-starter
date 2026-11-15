"""
Evaluation of the recommender against named listener profiles.

tests/test_recommender.py tests the pieces in isolation on synthetic songs.
This file tests the system end to end on the real catalog, through four
listeners with genuinely different taste, and asks: does each one get a list
that a person with that taste would recognise as theirs?

Expected titles below were read off the live catalog, not predicted. If
data/songs.csv changes, these tests are supposed to fail - they are a record
of what the system currently recommends, which is the thing an evaluation
section needs to be able to cite.

Following the lesson in README "Trying to break the tests": the invariant
tests here deliberately do NOT import the scoring weights. A test that
recomputes the expected value from the constant under test cannot fail.
"""
from pathlib import Path

import pytest

from src.recommender import load_songs, recommend_songs, score_song

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = PROJECT_ROOT / "data" / "songs.csv"

# The documented score range, hard-coded on purpose. See module docstring.
MAX_SCORE = 27.0

# --------------------------------------------------------------------------
# Four listeners, chosen to exercise different parts of the design:
#
#   High-Energy Pop   - exact genre with competition; two pop songs to separate
#   Chill Lofi        - exact genre, exact mood, acoustic; hits the 27.0 ceiling
#   Deep Intense Rock - only two rock songs, by the SAME artist; de-dup fires
#   Acoustic Folk     - folk/bluegrass related tier plus an acoustic preference
# --------------------------------------------------------------------------
PROFILES = {
    "high_energy_pop": {
        "genre": "pop", "mood": "happy", "energy": 0.90, "likes_acoustic": False,
    },
    "chill_lofi": {
        "genre": "lofi", "mood": "chill", "energy": 0.35, "likes_acoustic": True,
    },
    "deep_intense_rock": {
        "genre": "rock", "mood": "intense", "energy": 0.90, "likes_acoustic": False,
    },
    "acoustic_folk_winddown": {
        "genre": "folk", "mood": "melancholy", "energy": 0.30, "likes_acoustic": True,
    },
}

PROFILE_NAMES = sorted(PROFILES)


@pytest.fixture(scope="module")
def songs():
    return load_songs(str(SONGS_CSV))


@pytest.fixture(params=PROFILE_NAMES)
def profile(request):
    """Each test using this fixture runs once per listener."""
    return request.param, PROFILES[request.param]


def normalised(value: str) -> str:
    return " ".join(str(value).replace("-", " ").lower().split())


# --------------------------------------------------------------------------
# Per-profile expectations: what each listener actually gets today
# --------------------------------------------------------------------------

EXPECTED_TOP_PICK = {
    "high_energy_pop": ("Sunrise City", 26.84),
    "chill_lofi": ("Library Rain", 27.00),
    "deep_intense_rock": ("Storm Runner", 26.98),
    "acoustic_folk_winddown": ("Paper Planes Fade", 26.98),
}


@pytest.mark.parametrize("name", PROFILE_NAMES)
def test_each_profile_gets_its_expected_top_pick(songs, name):
    title, expected_score = EXPECTED_TOP_PICK[name]

    song, score, _ = recommend_songs(PROFILES[name], songs, k=5)[0]

    assert song["title"] == title
    assert score == pytest.approx(expected_score, abs=0.005)


def test_chill_lofi_finds_a_perfect_match(songs):
    """Library Rain matches all four features exactly - the documented ceiling."""
    _, score, _ = recommend_songs(PROFILES["chill_lofi"], songs, k=1)[0]

    assert score == pytest.approx(MAX_SCORE)


def test_each_profile_leads_with_its_requested_genre(songs):
    """The top pick is in the genre the listener asked for - for every listener."""
    for name, prefs in PROFILES.items():
        song, _, _ = recommend_songs(prefs, songs, k=5)[0]

        assert normalised(song["genre"]) == normalised(prefs["genre"]), name


def test_the_four_profiles_get_genuinely_different_lists(songs):
    """
    Guards against a recommender that ignores the profile. Four listeners with
    four tastes must not be handed the same playlist.
    """
    lists = {
        name: tuple(s["title"] for s, _, _ in recommend_songs(prefs, songs, k=5))
        for name, prefs in PROFILES.items()
    }

    assert len(set(lists.values())) == len(PROFILES)

    # No single song may top every list either.
    assert len({titles[0] for titles in lists.values()}) == len(PROFILES)


# --------------------------------------------------------------------------
# Invariants that must hold for every listener
# --------------------------------------------------------------------------

def test_results_are_ordered_by_descending_score(songs, profile):
    name, prefs = profile
    scores = [score for _, score, _ in recommend_songs(prefs, songs, k=5)]

    assert scores == sorted(scores, reverse=True), name


def test_no_artist_appears_twice(songs, profile):
    name, prefs = profile
    artists = [normalised(s["artist"]) for s, _, _ in recommend_songs(prefs, songs, k=5)]

    assert len(artists) == len(set(artists)), name


def test_every_score_stays_inside_the_documented_range(songs, profile):
    name, prefs = profile

    for song, score, _ in recommend_songs(prefs, songs, k=5):
        assert 0.0 <= score <= MAX_SCORE, f"{name}: {song['title']} scored {score}"


def test_exact_genre_matches_outrank_every_other_genre(songs, profile):
    """
    The central guarantee, checked on real data rather than a constructed pair:
    no song outside the requested genre may place above one inside it.
    """
    name, prefs = profile
    wanted = normalised(prefs["genre"])

    ranked = sorted(
        ((score_song(prefs, s)[0], normalised(s["genre"]), s["title"]) for s in songs),
        key=lambda item: -item[0],
    )
    exact = [score for score, genre, _ in ranked if genre == wanted]
    other = [score for score, genre, _ in ranked if genre != wanted]

    if exact and other:
        assert min(exact) > max(other), name


def test_every_recommendation_explains_itself(songs, profile):
    name, prefs = profile

    for song, score, explanation in recommend_songs(prefs, songs, k=5):
        assert explanation.strip(), f"{name}: {song['title']} had no explanation"
        if score > 0:
            assert "+" in explanation, f"{name}: {song['title']} cited no points"


def test_explanation_totals_equal_the_reported_score(songs, profile):
    """The explanation is built from the reasons that earned points, so the
    points quoted in it must add up to the score shown next to it."""
    name, prefs = profile

    for song, score, _ in recommend_songs(prefs, songs, k=5):
        direct, reasons = score_song(prefs, song)

        assert direct == pytest.approx(score), name
        quoted = sum(float(r.rsplit("+", 1)[1].rstrip(")")) for r in reasons)
        assert quoted == pytest.approx(score, abs=0.005), f"{name}: {song['title']}"


def test_a_profile_never_returns_more_than_k(songs, profile):
    name, prefs = profile

    for k in (1, 3, 5, 50):
        assert len(recommend_songs(prefs, songs, k=k)) <= k, name


# --------------------------------------------------------------------------
# Cases where the design deliberately gives up accuracy
# --------------------------------------------------------------------------

def test_rock_profile_loses_its_second_best_song_to_artist_dedup(songs):
    """
    Both rock songs are by Voltline. Slow Collapse scores 26.80 - the second
    best match in the catalog - and is dropped so the list is not one artist
    twice. Documents the trade-off rather than hiding it.
    """
    prefs = PROFILES["deep_intense_rock"]
    titles = [s["title"] for s, _, _ in recommend_songs(prefs, songs, k=5)]

    slow_collapse = next(s for s in songs if s["title"] == "Slow Collapse")
    suppressed_score = score_song(prefs, slow_collapse)[0]
    runner_up_score = recommend_songs(prefs, songs, k=5)[1][1]

    assert "Storm Runner" in titles
    assert "Slow Collapse" not in titles
    assert suppressed_score > runner_up_score


def test_folk_profile_suppresses_a_related_genre_song_for_artist_variety(songs):
    """
    Barn Burner Breakdown is bluegrass - the related tier for folk, 11.88 - but
    Copper Holler already appears via Dust Road Hymn, so a 6.94 non-folk song
    takes third place instead.
    """
    prefs = PROFILES["acoustic_folk_winddown"]
    results = recommend_songs(prefs, songs, k=5)
    titles = [s["title"] for s, _, _ in results]

    assert "Dust Road Hymn" in titles
    assert "Barn Burner Breakdown" not in titles

    barn = next(s for s in songs if s["title"] == "Barn Burner Breakdown")
    assert score_song(prefs, barn)[0] > results[2][1]
