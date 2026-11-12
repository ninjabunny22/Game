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


def test_a_comparison_never_plays_more_than_ten_games_and_sums_them_up():
    assert league.MAX_GAMES == 10 == len(league.GAMES)
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
