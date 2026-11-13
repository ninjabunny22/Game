"""Royal families: exact ageing, a mortality that rises with age, deaths that follow a seed,
succession in order, murder only by an enemy, children only to a married couple."""

from types import SimpleNamespace

from civsim.civ import family
from civsim.civ.family import YEAR, Families, natural_death_chance, sudden_rates
from civsim.civ.personality import Personality


def _civs(count=3):
    return [SimpleNamespace(id=i, name=f"Realm{i}", alive=True, focus="balanced", born=None, settlements=[],
                            personality=Personality("Builder", {"military": 1.0})) for i in range(count)]


class _Diplomacy:
    def __init__(self, wars=(), standing=None):
        self.wars = set(wars)
        self.standing = standing or {}
        self.history = []
        self.now = 0

    def enemies(self, civ_id):
        return [b if a == civ_id else a for a, b in self.wars if civ_id in (a, b)]

    def sick(self, civ):
        return False

    def remember(self, who, of, amount):
        self.standing[(who, of)] = self.standing.get((who, of), 0.0) + amount


def test_age_rises_by_exactly_one_year_every_365_days():
    families = Families(_civs(), seed=1)
    ruler = families.ruler(0)
    start = ruler.age(0)
    assert ruler.age(364) == start and ruler.age(365) == start + 1
    assert ruler.age(5 * YEAR) == start + 5  # 45 is 50 on day 1,825
    person = family.Character(99, "Test", ruler.house, "m", birth_day=family.born_aged(45))
    assert person.age(1825) == 50 and person.age(1824) == 49


def test_mortality_rises_with_every_year_and_sudden_death_strikes_the_young():
    chances = [natural_death_chance(age) for age in range(20, 100)]
    assert all(b > a for a, b in zip(chances, chances[1:]) if b < family.MORTALITY_CAP)
    assert natural_death_chance(25) < 0.01 < natural_death_chance(70) < natural_death_chance(85)
    assert natural_death_chance(60, ill=True) > natural_death_chance(60)
    assert natural_death_chance(60, wounds=2) > natural_death_chance(60, wounds=1)
    young = sudden_rates(25)
    assert sum(young.values()) > 0  # a stroke, a fever or a fall can take anyone
    assert "an assassin's knife" not in sudden_rates(40, enemies=0, royal=True)
    assert "an assassin's knife" in sudden_rates(40, enemies=1, royal=True)


def test_the_yearly_check_falls_once_every_365_days():
    families = Families(_civs(1), seed=2)
    calls = []
    families._birthday = lambda person, house, civ, tick, events: calls.append((person.id, tick))
    families._sudden = lambda *args: None
    for tick in range(1, 3 * YEAR + 1):
        families.update(tick, [])
    by_person = {}
    for person, tick in calls:
        by_person.setdefault(person, []).append(tick)
    assert by_person and all(len(ticks) == 3 and ticks[1] - ticks[0] == ticks[2] - ticks[1] == YEAR
                             for ticks in by_person.values())
    assert len({ticks[0] for ticks in by_person.values()}) > 1  # not all on the same day


def _run(seed, days=20 * YEAR):
    families = Families(_civs(), seed=seed, diplomacy=_Diplomacy())
    events = []
    for tick in range(1, days):
        families.update(tick, events)
    return [(e["text"]) for e in events]


def test_the_same_seed_sees_the_same_lives():
    assert _run(5) == _run(5)
    assert _run(5) != _run(6)


def test_the_eldest_son_then_his_line_follows_the_ruler():
    civs = _civs(1)
    families = Families(civs, seed=3)
    house = families.house_of(0)
    ruler = families.ruler(0)
    line = families.line(house)
    children = families.children(ruler)
    assert line[0] is children[0] and line[0].sex == "m" or not any(c.sex == "m" for c in children)
    heir = line[0]
    events = []
    families.die(ruler, 100, events, "a stroke")
    assert house.ruler == heir.id and families.unrest(0, 120) and not families.unrest(0, 100 + family.UNREST_DAYS)
    assert events and events[-1]["family"]["type"] == "succession" and events[-1]["family"]["banner"]
    assert (civs[0].born or civs[0].personality).name == heir.personality


def test_a_spent_line_brings_a_cousin():
    families = Families(_civs(1), seed=4)
    house = families.house_of(0)
    for member in house.members:
        person = families.people[member]
        if person.alive and person.id != house.ruler:
            person.alive = False
    old = house.ruler
    families.die(families.people[old], 50, [], "old age")
    assert house.ruler != old and families.people[house.ruler].alive


def test_murder_needs_an_enemy_and_leaves_a_grudge():
    peace = Families(_civs(), seed=7, diplomacy=_Diplomacy())
    assert peace._enemies(0) == []
    diplomacy = _Diplomacy(wars=[(0, 1)])
    families = Families(_civs(), seed=7, diplomacy=diplomacy)
    assert families._enemies(0) == [1]
    ruler = families.ruler(0)
    events = []
    families.die(ruler, 10, events, "poison", killer=families.civs[1])
    assert events[-1]["family"]["type"] == "assassination"
    assert diplomacy.standing[(0, 1)] < 0


def test_children_are_born_only_to_married_couples():
    families = Families(_civs(), seed=8, diplomacy=_Diplomacy())
    for tick in range(1, 25 * YEAR):
        families.update(tick, [])
    born = [p for p in families.people.values() if p.birth_day > 0 and p.parents]  # not spouses from outside
    assert born, "a long reign should see children born"
    for child in born:
        father, mother = (families.people[p] for p in child.parents)
        assert father.spouse == mother.id and mother.sex == "f"
        assert child.face is not None and child.picture(child.birth_day).endswith(f"child_{child.face}.png")
        assert child.picture(child.birth_day + family.GROWN * family.CHILD_YEAR).endswith(f"adult_{child.face}.png")
    assert family.age_after(18 * family.CHILD_YEAR) == 18 and family.age_after(17 * family.CHILD_YEAR) == 17
    assert family.age_after(18 * family.CHILD_YEAR + YEAR) == 19  # grown up, a year is 365 days again


def test_every_portrait_on_the_boards_was_cut():
    import os
    root = os.path.join(os.path.dirname(__file__), "..", "godot", "assets", "portraits")
    families = Families(_civs(5), seed=9)
    for person in families.people.values():
        if person.portrait:
            assert os.path.exists(os.path.join(root, person.portrait.split("portraits/", 1)[1])), person.portrait
