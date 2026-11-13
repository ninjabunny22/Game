"""The league: variants of the strategist played against the standard one."""

import random

import pytest

from civsim import league
from civsim.strategy.utility import DEFAULT


def test_a_game_pits_half_the_civs_on_changed_numbers_against_the_rest():
    result = league.play("small", 0, {"ATTACK_THRESHOLD": 0.4}, game=0, ticks=400)
    assert result["variant"] > 0 and result["standard"] > 0 and result["ended"] == 400
    other = league.play("small", 0, {"ATTACK_THRESHOLD": 0.4}, game=1, ticks=400)
    assert (other["variant"], other["standard"]) != (result["variant"], result["standard"]), "sides are swapped"
    with pytest.raises(ValueError):
        league.play("small", 0, {"NO_SUCH_NUMBER": 1}, game=0, ticks=5)


def test_a_comparison_never_plays_more_than_six_games_and_sums_them_up():
    assert league.MAX_GAMES == 6 == len(league.GAMES)
    result = league.compare({"PARITY": 1.0}, games=2, ticks=120)
    assert result["games"] == 2 and result["advantage"] > 0 and result["length"] == 120


def test_mutations_move_a_few_numbers_a_little_and_keep_whole_numbers_whole():
    rng = random.Random(1)
    tweaks = league.mutate({}, rng)
    assert len(tweaks) == 3
    for name, value in tweaks.items():
        before = getattr(DEFAULT, name)
        assert value != before and abs(value - before) <= abs(before) * league.STEP + 1
        if name in league.INTEGERS:
            assert isinstance(value, int)
    assert len(league.mutate(tweaks, rng)) >= 3, "a mutation builds on what was kept"


def test_a_lively_decided_game_is_better_to_watch_than_a_dull_short_one():
    from civsim.league import entertainment
    lively = {"ended": 5000, "last_day": 8000, "wars": 6, "alliances": 3, "rallies": 2, "lead_changes": 3,
              "prizes_taken": 0.7, "closest": 0.8}
    dull = dict(lively, ended=1500, wars=1, alliances=0, rallies=0, lead_changes=0, prizes_taken=0.1, closest=0.3)
    assert 0.0 <= entertainment(dull) < entertainment(lively) <= 1.0
    assert entertainment(lively) > 0.9
