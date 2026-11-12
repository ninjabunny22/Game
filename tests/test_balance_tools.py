"""The tools that judge the drawn maps: fairness by geography, balance by played games."""

from civsim.balance import interval, summarise
from civsim.fairness import report


def test_the_fairness_report_covers_every_civ_count_and_slot():
    lines = report("highgate")
    assert sum(1 for line in lines if "civs" in line) == 3  # 2, 3 and 4 civs
    assert sum(1 for line in lines if line.strip().startswith(("NW", "NE", "SE", "SW"))) == 2 + 3 + 4


def test_a_win_rate_interval_holds_the_rate_and_narrows_with_more_games():
    lo, hi = interval(5, 10)
    assert lo < 0.5 < hi
    lo2, hi2 = interval(50, 100)
    assert hi2 - lo2 < hi - lo


def test_the_summary_flags_a_slot_that_always_wins():
    games = [{"seed": s, "winner": "A", "kind": "domination", "day": 2000, "first_war": 500,
              "snaps": {1000: {"A": 4, "B": 2}}, "end": {"A": 9, "B": 1}, "dead": [], "prizes": {"Keep": ("A", 900)}}
             for s in range(20)]
    lines = summarise("somewhere", 2, games)
    assert any(line.strip().startswith("A") and "win rate" in line for line in lines)
    assert any("prize Keep: taken in 20/20" in line for line in lines)
