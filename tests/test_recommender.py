import re
from pathlib import Path

import pytest

from src.recommender import (
    Song,
    UserProfile,
    Recommender,
    load_songs,
    score_song,
    recommend_songs,
    GENRE_EXACT,
    GENRE_RELATED,
    MOOD_EXACT,
    MOOD_RELATED,
    ENERGY_WEIGHT,
    ACOUSTIC_WEIGHT,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = PROJECT_ROOT / "data" / "songs.csv"

HEADER = (
    "id,title,artist,genre,mood,energy,tempo_bpm,valence,danceability,acousticness"
)


def make_song(**overrides) -> dict:
    """
    A song dict shaped like load_songs() output.

    Scoring tests build songs here rather than reading data/songs.csv, so they
    keep passing when the catalog changes.
    """
    song = {
        "id": 1,
        "title": "Test Song",
        "artist": "Test Artist",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.8,
        "tempo_bpm": 120.0,
        "valence": 0.9,
        "danceability": 0.8,
        "acousticness": 0.2,
    }
    song.update(overrides)
    return song


def write_csv(path: Path, *rows: str) -> str:
    """Writes a CSV with the standard header and returns its path."""
    path.write_text("\n".join((HEADER,) + rows) + "\n", encoding="utf-8")
    return str(path)

def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


# ---------------------------------------------------------------------------
# load_songs
# ---------------------------------------------------------------------------

def test_load_songs_reads_the_project_catalog():
    songs = load_songs(str(SONGS_CSV))

    assert songs, "data/songs.csv should not be empty"
    for song in songs:
        assert set(song) == {
            "id", "title", "artist", "genre", "mood",
            "energy", "tempo_bpm", "valence", "danceability", "acousticness",
        }


def test_load_songs_converts_numeric_columns():
    # Scoring does arithmetic straight off these values, so they must not
    # arrive as the strings csv.DictReader hands back.
    songs = load_songs(str(SONGS_CSV))

    for song in songs:
        assert isinstance(song["id"], int)
        for column in ("energy", "tempo_bpm", "valence", "danceability", "acousticness"):
            assert isinstance(song[column], float)


def test_load_songs_keeps_text_columns_as_text():
    songs = load_songs(str(SONGS_CSV))

    for song in songs:
        for column in ("title", "artist", "genre", "mood"):
            assert isinstance(song[column], str)
            assert song[column] != ""


def test_load_songs_gives_every_song_a_unique_id():
    ids = [song["id"] for song in load_songs(str(SONGS_CSV))]

    assert len(ids) == len(set(ids))


def test_load_songs_raises_when_the_file_is_missing():
    with pytest.raises(FileNotFoundError):
        load_songs(str(PROJECT_ROOT / "data" / "no_such_file.csv"))


def test_load_songs_raises_when_a_column_is_missing(tmp_path):
    path = tmp_path / "short_header.csv"
    path.write_text("id,title,artist\n1,Song,Artist\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_songs(str(path))

    assert "missing required column" in str(excinfo.value)
    assert "genre" in str(excinfo.value)


def test_load_songs_names_the_line_holding_a_bad_number(tmp_path):
    # A typo in the CSV should be findable, not silently dropped.
    path = write_csv(
        tmp_path / "bad_number.csv",
        "1,Fine,Artist,pop,happy,0.5,120,0.5,0.5,0.5",
        "2,Broken,Artist,pop,happy,NOT_A_NUMBER,120,0.5,0.5,0.5",
    )

    with pytest.raises(ValueError) as excinfo:
        load_songs(path)

    assert "line 3" in str(excinfo.value)


def test_load_songs_skips_blank_lines(tmp_path):
    path = write_csv(
        tmp_path / "blanks.csv",
        "1,Only Song,Artist,pop,happy,0.5,120,0.5,0.5,0.5",
        "",
        "",
    )

    assert len(load_songs(path)) == 1


def test_load_songs_strips_surrounding_whitespace(tmp_path):
    path = write_csv(
        tmp_path / "padded.csv",
        "1,  Padded Title  ,  Padded Artist  ,pop,happy,0.5,120,0.5,0.5,0.5",
    )

    song = load_songs(path)[0]

    assert song["title"] == "Padded Title"
    assert song["artist"] == "Padded Artist"


# ---------------------------------------------------------------------------
# score_song
# ---------------------------------------------------------------------------

def test_score_song_adds_up_every_matching_feature():
    song = make_song(genre="pop", mood="happy", energy=0.8, acousticness=0.2)
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False}

    score, _ = score_song(prefs, song)

    expected = GENRE_EXACT + MOOD_EXACT + ENERGY_WEIGHT + ACOUSTIC_WEIGHT
    assert score == pytest.approx(expected)


def test_genre_outranks_every_lower_priority_feature_combined():
    # The spacing guarantee: a right-genre song that loses on mood, energy and
    # acoustic must still beat a wrong-genre song that wins on all three.
    prefs = {"genre": "pop", "mood": "happy", "energy": 1.0, "likes_acoustic": False}
    right_genre_worst = make_song(genre="pop", mood="moody", energy=0.0, acousticness=0.9)
    wrong_genre_best = make_song(genre="jazz", mood="happy", energy=1.0, acousticness=0.2)

    assert score_song(prefs, right_genre_worst)[0] > score_song(prefs, wrong_genre_best)[0]


def test_weights_preserve_the_priority_spacing_rule():
    # The design depends on arithmetic, not good intentions: each genre tier must
    # sit further apart than everything below genre can contribute in total.
    # Without this, tuning a weight could silently demote genre below mood.
    most_the_lower_features_can_give = MOOD_EXACT + ENERGY_WEIGHT + ACOUSTIC_WEIGHT

    assert GENRE_EXACT - GENRE_RELATED > most_the_lower_features_can_give
    assert GENRE_RELATED > most_the_lower_features_can_give


def test_an_exact_genre_match_beats_a_related_one_that_wins_everything_else():
    prefs = {"genre": "pop", "mood": "happy", "energy": 1.0, "likes_acoustic": False}
    exact_genre_losing_all_else = make_song(
        genre="pop", mood="moody", energy=0.0, acousticness=0.9
    )
    related_genre_winning_all_else = make_song(
        genre="indie pop", mood="happy", energy=1.0, acousticness=0.2
    )

    assert (
        score_song(prefs, exact_genre_losing_all_else)[0]
        > score_song(prefs, related_genre_winning_all_else)[0]
    )


def test_related_genre_scores_between_an_exact_match_and_none():
    prefs = {"genre": "pop"}

    exact, _ = score_song(prefs, make_song(genre="pop"))
    related, _ = score_song(prefs, make_song(genre="indie pop"))
    unrelated, _ = score_song(prefs, make_song(genre="jazz"))

    assert exact == pytest.approx(GENRE_EXACT)
    assert related == pytest.approx(GENRE_RELATED)
    assert unrelated == pytest.approx(0.0)
    assert exact > related > unrelated


def test_related_mood_scores_between_an_exact_match_and_none():
    prefs = {"mood": "moody"}

    exact, _ = score_song(prefs, make_song(mood="moody"))
    related, _ = score_song(prefs, make_song(mood="melancholy"))
    unrelated, _ = score_song(prefs, make_song(mood="happy"))

    assert exact == pytest.approx(MOOD_EXACT)
    assert related == pytest.approx(MOOD_RELATED)
    assert unrelated == pytest.approx(0.0)


def test_a_mood_the_catalog_does_not_use_still_matches_its_family():
    # No song is labelled "calm", but a user may well ask for it.
    score, _ = score_song({"mood": "calm"}, make_song(mood="chill"))

    assert score == pytest.approx(MOOD_RELATED)


def test_energy_is_scored_by_closeness_not_pass_or_fail():
    prefs = {"energy": 0.5}

    spot_on, _ = score_song(prefs, make_song(energy=0.5))
    near, _ = score_song(prefs, make_song(energy=0.6))
    far, _ = score_song(prefs, make_song(energy=0.9))

    assert spot_on > near > far
    assert spot_on == pytest.approx(ENERGY_WEIGHT)


def test_acoustic_preference_rewards_agreement_in_both_directions():
    acoustic_song = make_song(acousticness=0.9)
    produced_song = make_song(acousticness=0.1)

    assert score_song({"likes_acoustic": True}, acoustic_song)[0] == pytest.approx(
        ACOUSTIC_WEIGHT
    )
    assert score_song({"likes_acoustic": False}, produced_song)[0] == pytest.approx(
        ACOUSTIC_WEIGHT
    )
    assert score_song({"likes_acoustic": True}, produced_song)[0] == pytest.approx(0.0)
    assert score_song({"likes_acoustic": False}, acoustic_song)[0] == pytest.approx(0.0)


def test_reasons_add_up_to_the_returned_score():
    # The explanation must never drift away from the number it explains.
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.7, "likes_acoustic": False}

    score, reasons = score_song(prefs, make_song())

    claimed = sum(float(re.search(r"\+([\d.]+)", reason).group(1)) for reason in reasons)
    assert claimed == pytest.approx(score)


def test_a_partial_profile_still_scores():
    # src/main.py sends no likes_acoustic key at all.
    prefs = {"genre": "pop", "mood": "happy", "energy": 0.8}

    score, reasons = score_song(prefs, make_song())

    assert score > 0
    assert len(reasons) == 3


def test_an_empty_profile_scores_nothing_without_crashing():
    score, reasons = score_song({}, make_song())

    assert score == pytest.approx(0.0)
    assert reasons == []


@pytest.mark.parametrize("spelling", ["indie pop", "Indie-Pop", "  INDIE   POP  ", "indie-pop"])
def test_matching_ignores_case_hyphens_and_padding(spelling):
    score, _ = score_song({"genre": spelling}, make_song(genre="indie pop"))

    assert score == pytest.approx(GENRE_EXACT)


# ---------------------------------------------------------------------------
# recommend_songs
# ---------------------------------------------------------------------------

@pytest.fixture
def three_songs():
    """Two artists, three songs. Artist X's two tracks score 22.0 and 21.8."""
    return [
        make_song(id=1, title="X Best", artist="X", genre="pop", energy=0.8),
        make_song(id=2, title="X Worse", artist="X", genre="pop", energy=0.7),
        make_song(id=3, title="Y Only", artist="Y", genre="pop", energy=0.5),
    ]


def test_recommend_songs_returns_results_in_descending_order(three_songs):
    prefs = {"genre": "pop", "energy": 0.8}

    scores = [score for _, score, _ in recommend_songs(prefs, three_songs, k=5)]

    assert scores == sorted(scores, reverse=True)


def test_recommend_songs_keeps_only_each_artists_best_track(three_songs):
    prefs = {"genre": "pop", "energy": 0.8}

    results = recommend_songs(prefs, three_songs, k=5)

    titles = [song["title"] for song, _, _ in results]
    assert titles == ["X Best", "Y Only"]  # "X Worse" dropped, not "X Best"


def test_recommend_songs_returns_song_score_explanation(three_songs):
    result = recommend_songs({"genre": "pop"}, three_songs, k=1)[0]

    song, score, explanation = result  # the shape src/main.py unpacks
    assert isinstance(song, dict) and "title" in song
    assert isinstance(score, float)
    assert isinstance(explanation, str) and explanation.strip() != ""


@pytest.mark.parametrize("k, expected", [(0, 0), (-1, 0), (1, 1), (2, 2), (99, 2)])
def test_recommend_songs_respects_k(three_songs, k, expected):
    # 99 yields 2, not 3: the catalog only holds two distinct artists.
    assert len(recommend_songs({"genre": "pop"}, three_songs, k=k)) == expected


def test_recommend_songs_handles_an_empty_catalog():
    assert recommend_songs({"genre": "pop"}, [], k=5) == []


def test_recommend_songs_explains_a_song_that_matches_nothing():
    results = recommend_songs({"genre": "polka"}, [make_song()], k=1)

    _, score, explanation = results[0]
    assert score == pytest.approx(0.0)
    assert explanation.strip() != ""


def test_recommend_songs_is_deterministic_when_scores_tie():
    tied = [
        make_song(id=1, title="First", artist="A"),
        make_song(id=2, title="Second", artist="B"),
    ]
    prefs = {"genre": "pop"}

    runs = [[s["title"] for s, _, _ in recommend_songs(prefs, tied, k=2)] for _ in range(5)]

    assert all(run == runs[0] for run in runs)


def test_recommend_songs_agrees_with_score_song(three_songs):
    # The ranking stage must not invent scores of its own.
    prefs = {"genre": "pop", "energy": 0.8}

    for song, score, _ in recommend_songs(prefs, three_songs, k=5):
        assert score == pytest.approx(score_song(prefs, song)[0])
