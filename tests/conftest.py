import pytest

from civsim.diplomacy import rules


@pytest.fixture
def no_war_minimum(monkeypatch):
    """Lift the minimum army for declaring war, for tests that are about some other rule."""
    monkeypatch.setattr(rules, "WAR_MIN_SOLDIERS", 0)
    monkeypatch.setattr(rules, "WAR_MIN_SHARE", 0.0)


# Tests of how battles go were written when one army held every soldier a civ sent out. They
# are about the fighting, not about how many a general can lead, so there they lead any number.
UNCAPPED = {"test_military", "test_commanders", "test_pursuit", "test_diplomacy", "test_hold", "test_water",
            "test_regions", "test_horses"}


@pytest.fixture(autouse=True)
def _generals_lead_any_number(request, monkeypatch):
    if request.module.__name__ in UNCAPPED:
        monkeypatch.setattr("civsim.military.army.CAPACITY", 1e6)
