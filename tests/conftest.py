import pytest

from civsim.diplomacy import rules


@pytest.fixture
def no_war_minimum(monkeypatch):
    """Lift the minimum army for declaring war, for tests that are about some other rule."""
    monkeypatch.setattr(rules, "WAR_MIN_SOLDIERS", 0)
    monkeypatch.setattr(rules, "WAR_MIN_SHARE", 0.0)
