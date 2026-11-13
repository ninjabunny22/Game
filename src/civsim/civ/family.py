"""Royal families: each civ is ruled by a house (data/houses.json, from the portrait boards) whose
members age, marry, have children, fall ill and die, and whose ruler is followed by an heir.

Ageing is exact: a child is a year older every CHILD_YEAR (120) days until 18, so heirs grow up
within a game, and an adult a year older every 365 days (`age_after`; members alive at the
start are born `born_aged(age)` days before day 0). Once a year (on their
birthday, or for those alive at the start on a day of the year of their own) a character faces
one natural-death check, whose chance rises with every year of age (a Gompertz
curve, `natural_death_chance`); health, an illness and old wounds weigh on it. Apart from that,
sudden deaths can strike on any day and at any age (`sudden_rates`): a stroke, the heart, a
sudden illness, an accident, plague while the realm is sick, and, for a ruler or heir whose
realm has enemies, poison or a knife. A prince who commands an army can also fall or be wounded
in battle (military/warfare.py).

When the ruler dies the eldest son (then daughter) of the ruler takes the throne, their line
before the next child's, then the ruler's brothers and sisters and theirs, then whoever of the
house is left, and if nobody is, a cousin. The heir rules by their own personality (the civ's
strategist plans by it from then on) and the realm is unsettled for UNREST_DAYS: it starts no
war, and its rivals see it as exposed. A ruler or heir murdered by an enemy leaves a grudge.

Ambition breeds plots: once a year an ambitious prince or lord who is not the heir may try to
kill the ruler (more likely when the ruler is old, ill, new, a child, or the realm is losing a
war). A third of attempts succeed; an heir nobody suspects simply takes the throne, but a plot
found out (and every failed one) ends in rebellion: the plotter seizes a castle of the realm
(never its capital) and breaks away as a new civ at war with his king, taking his own army, a
share of the king's soldiers and a general or two (simulation.py, military/warfare.py). With
no castle to seize, he is executed. A child heir rules through a regent, who may seize the
crown; a house whose line dies out is claimed by the blood of a daughter married abroad, a
reason for that realm to go to war (strategy/utility.py). Princes taken in battle are
ransomed. Some are born brave (better commanders), sickly, learned (faster research while
they rule) or cruel (others trust their realm less).

All of it rolls its own dice (seeded from the game's seed), so a family never disturbs the rest
of the game's random streams, and a replay of a seed sees the same deaths.
"""

import math
import random
from dataclasses import dataclass, field

from ..datafiles import load_json
from ..diplomacy.proclamations import proclaim
from .personality import Personality, with_focus

YEAR = 365  # days in a year of an adult's life
CHILD_YEAR = 120  # days in a year of childhood: children grow up faster, so heirs come of age in a game
# Natural death: the chance of dying within the year at `age`, A at 30, multiplied by e^B a year.
MORTALITY_A = 0.0022
MORTALITY_B = 0.075
MORTALITY_CAP = 0.9
# Sudden deaths, as yearly chances (rolled a day at a time).
STROKE = (0.0004, 0.06)  # (chance at 30, growth a year)
HEART = (0.0004, 0.065)
SUDDEN_ILLNESS = 0.001  # dies of a fever, at any age
ACCIDENT = 0.0007  # a fall from a horse, a hunt gone wrong
FALL_ILL = 0.04  # falls ill (and is weaker for ILL_DAYS) without dying of it
ILL_DAYS = 365
ILL_MULT = 2.0  # an illness doubles the natural risk while it lasts
WOUND_MULT = 1.3  # each old wound adds to it
PLAGUE = 0.05  # while the realm has its war sickness
MURDER = 0.006  # for a ruler or heir, for each realm at war with it or bitterly against it
MURDER_CAP = 0.015
BITTER = -2.0  # standing at or below which a realm may stoop to murder
CHILDBIRTH = 0.02  # a mother's risk in each birth
# Families grow.
ADULT = 18
FERTILE_UNTIL = 44
BIRTH_YOUNG = 0.3  # yearly chance of a child for a married couple, the wife under 35
BIRTH_OLDER = 0.12  # and from 35 to FERTILE_UNTIL
MARRY = 0.2  # yearly chance an unmarried adult of the house marries
MARRY_HEIR = 0.35
MATCH_ROYAL = 0.3  # of a marriage, the chance it is with another ruling house (if one will have it)
MATCH_POOL = 0.5  # else with a house that does not rule (a portrait from the boards), else minor nobility
UNREST_DAYS = 60
ROYAL_STANDING = 1.0  # how much better two ruling houses think of each other once joined by marriage

# Plots, rebellion, regency, claims, traits.
PLOT_BASE = 0.01  # yearly chance of a plot for a prince of the greatest ambition, before circumstances
PLOT_FROM = 1000  # no plots before this day
PLOT_SUCCESS = 1 / 3  # share of attempts on the ruler's life that succeed
UNSUSPECTED = 0.5  # chance an heir whose plot succeeded is not found out
MIN_REGIONS = 3  # a realm must hold this many regions for a prince to have a castle to seize
DEFECT_BASE = 0.1  # share of the king's soldiers who go over to a rebel ...
DEFECT_MAX = 0.25  # ... rising with the realm's troubles to this
GENERAL_DEFECTS = 0.5  # chance each of up to two of the king's idle generals goes over
REGENT_USURPS = 0.25  # yearly chance, times the regent's ambition, the regent takes the crown
CLAIM_DAYS = 3000  # how long a claim to a throne through marriage is pressed
TRAITS = ("brave", "sickly", "learned", "cruel", "pious", "shrewd", "kind", "proud")
TRAIT_CHANCE = 1.0  # everyone has one
SICKLY = 1.35  # a sickly character's natural risk
LEARNED = 0.15  # research a learned ruler adds
CRUEL = 0.3  # how much worse each other realm thinks of a cruel ruler's every year
AMBITIOUS = 0.7  # from this ambition a character is shown as ambitious
PATRON_BETRAYS = 0.35  # chance a realm that takes up a rebel's cause means to betray it ...
PATRON_TEMPER = {"Expansionist": 0.2, "Merchant": 0.05, "Builder": -0.1, "Scholar": -0.1, "Agrarian": -0.05}
BETRAY_AFTER = (20, 60)  # ... and how many days later it turns on the rebel
ROYAL_RANSOM = 400  # gold a father pays to have a rebel child back from whoever holds them
SWORN = 3.0  # how the rebel and a patron that keeps its word think of each other

PORTRAITS = "res://assets/portraits"
FACES = {"m": (0, 2, 4), "f": (1, 3, 5)}  # the shared faces (portraits/common), by sex
GROWN = 16  # from this age a shared face is shown grown up
RULE_AGE = 12  # the youngest who rules in their own name; a younger ruler has a regent
# What a governor brings, from their own nature: their trait if it has a bonus, else their
# personality. (modifier, amount, words); "defense" strengthens only the castle they rule.
GOVERNOR_TRAITS = {
    "brave": ("defense", 0.2, "+20% defence of the castle"),
    "learned": ("science_mult", 0.05, "+5% research"),
    "cruel": ("military", 0.05, "+5% army strength"),
    "pious": ("growth", 0.05, "+5% growth"),
    "shrewd": ("gold", 0.08, "+8% gold"),
    "kind": ("food", 0.05, "+5% food"),
    "proud": ("defense", 0.1, "+10% defence of the castle"),
}
ESCAPE = 0.35  # chance a governor gets away when the castle they rule falls
EXECUTE = 0.03  # monthly chance a captor puts a royal captive to death (more if cruel or bitter)
EXECUTION_SHAME = 0.6  # how much worse every other realm thinks of an executioner ...
EXECUTION_FAVOUR = 0.8  # ... and how much better those that hate the victim's realm think of it
KIND = 0.2  # how much better every realm thinks of a kind ruler's each year
GOVERNOR_PERSONALITIES = {
    "Expansionist": ("mobilization", 0.02, "+2% of the people under arms"),
    "Builder": ("build_speed", 0.08, "+8% building speed"),
    "Scholar": ("science_mult", 0.04, "+4% research"),
    "Merchant": ("gold", 0.08, "+8% gold"),
    "Agrarian": ("food", 0.06, "+6% food"),
}


@dataclass
class Character:
    id: int
    name: str
    house: str  # the key of the house they belong to now
    sex: str  # "m" | "f"
    birth_day: int
    check_day: int = 0  # the day of the year (0-364) of their yearly check: their birthday if born in the game
    portrait: str = ""  # path of their picture on the boards ("" for someone not on them)
    face: int | None = None  # else one of the shared faces, a child's until GROWN and then grown up
    born: str = ""  # the house they were born to, if not this one
    parents: list[int] = field(default_factory=list)
    spouse: int | None = None
    personality: str = ""  # the archetype they would rule by
    health: float = 1.0  # 0.7 hale to 1.3 frail, from birth
    ill_until: int = -1
    wounds: int = 0
    alive: bool = True
    died: int | None = None
    cause: str = ""
    ruled: bool = False  # has sat on the throne
    ambition: float = 0.0  # 0 to 1: how much they want a crown that is not theirs
    traits: list[str] = field(default_factory=list)  # brave, sickly, learned, cruel
    usurper: bool = False  # took the throne by a crime
    deposed: bool = False  # put aside: out of the line of succession
    captive_of: int | None = None  # the civ holding them prisoner
    governs: int | None = None  # the tile of the castle they rule for the crown, if any

    def age(self, day: int) -> int:
        return age_after(day - self.birth_day)

    def picture(self, day: int) -> str:
        """The portrait to show: their own, or their shared face at their age ("" for none)."""
        if self.portrait or self.face is None:
            return self.portrait
        return f"{PORTRAITS}/common/{'child' if self.age(day) < GROWN else 'adult'}_{self.face}.png"


@dataclass
class House:
    key: str
    name: str
    civ: int | None  # the civ it rules, or None for one that only marries in
    ruler: int | None = None
    members: list[int] = field(default_factory=list)  # every member, living and dead, oldest first
    regent: int | None = None  # who rules for a child on the throne
    branch: str = ""  # for a house founded by a rebel: whose line it is
    origin: str = ""  # ... and the house it broke away from


def age_after(days: int) -> int:
    """How old someone is `days` after their birth: a year every CHILD_YEAR days until ADULT,
    then one every YEAR days."""
    if days < ADULT * CHILD_YEAR:
        return max(0, days) // CHILD_YEAR
    return ADULT + (days - ADULT * CHILD_YEAR) // YEAR


def born_aged(age: int, day: int = 0) -> int:
    """The birth day of someone who is exactly `age` on `day`."""
    lived = age * CHILD_YEAR if age < ADULT else ADULT * CHILD_YEAR + (age - ADULT) * YEAR
    return day - lived


def natural_death_chance(age: int, health: float = 1.0, ill: bool = False, wounds: int = 0) -> float:
    """The chance of dying of old age and ordinary decline within the coming year."""
    chance = MORTALITY_A * math.exp(MORTALITY_B * (age - 30)) * health
    chance *= (ILL_MULT if ill else 1.0) * WOUND_MULT ** wounds
    return min(MORTALITY_CAP, chance)


def sudden_rates(age: int, sick_realm: bool = False, enemies: int = 0, royal: bool = False,
                 intrigue: float = 1.0) -> dict[str, float]:
    """Yearly chances of each sudden death, apart from ageing: any of them can strike at any age."""
    rates = {
        "a stroke": STROKE[0] * math.exp(STROKE[1] * (age - 30)),
        "heart failure": HEART[0] * math.exp(HEART[1] * (age - 30)),
        "a sudden fever": SUDDEN_ILLNESS,
        "a fall from the saddle": ACCIDENT,
    }
    if sick_realm:
        rates["the plague"] = PLAGUE
    if royal and enemies and intrigue > 0:
        murder = min(MURDER_CAP, MURDER * enemies) * intrigue
        rates["poison"] = murder * 0.4
        rates["an assassin's knife"] = murder * 0.6
    return rates


class Families:
    def __init__(self, civs: list, seed: int, diplomacy=None, intrigue: float = 1.0):
        self.rng = random.Random(seed * 104729 + 7)
        self.intrigue = intrigue  # a factor on plots and murders (config.INTRIGUE)
        self.civs = {civ.id: civ for civ in civs}
        self.diplomacy = diplomacy
        self.military = None  # set by the simulation: commanders who are princes
        self.people: dict[int, Character] = {}
        self.houses: dict[str, House] = {}
        self.by_civ: dict[int, House] = {}
        self.changed = 0  # the last day anything about a family changed (the viewer is sent them then)
        self.unrest_until: dict[int, int] = {}  # civ id -> the day its unrest ends
        self.spawn = None  # set by the simulation: makes a rebel's new civ (or None if it cannot)
        self.rebellions: dict[int, int] = {}  # civ id -> the rebel civ that broke away from it
        self.claims: dict[tuple[int, int], dict] = {}  # (claiming civ, claimed civ) -> {"by", "since"}
        self.betrayals: dict[tuple[int, int], int] = {}  # (patron, rebel civ) -> the day it turns on the rebel
        self.bonds: set[frozenset] = set()  # rebel and patron that kept its word: they never fight
        self.now = 0
        data = load_json("houses.json")
        self._names = data["names"]
        self._archetypes = load_json("personalities.json")
        playing = sorted(key for key, house in data["houses"].items() if house["plays"])
        self.rng.shuffle(playing)
        owners = {key: civ.id for key, civ in zip(playing, civs)}
        for key, house in data["houses"].items():
            self._load(key, house, owners.get(key))
        for civ in civs:  # a civ beyond the houses drawn on the boards gets a minor house
            if civ.id not in self.by_civ:
                self._found(civ)
        for house in list(self.by_civ.values()):
            self._populate(house)
        for civ_id, house in self.by_civ.items():  # a ruling house is known by its realm's name
            house.name = self.civs[civ_id].name

    # -- building the houses ------------------------------------------------

    def _load(self, key: str, data: dict, civ_id: int | None) -> None:
        house = House(key, data["name"], civ_id)
        self.houses[key] = house
        if civ_id is not None:
            self.by_civ[civ_id] = house
        ids = {}
        for entry in data["members"]:
            person = self._add(house, entry["name"], entry["sex"], born_aged(entry.get("age", 0)),
                               f"{PORTRAITS}/{key}/{entry['id']}.png")
            ids[entry["id"]] = person
            person.born = entry.get("born", "")
            person.ruled = entry.get("ruled", False)
            if "age" not in entry:  # dead before the game began
                person.alive, person.died, person.cause = False, None, entry.get("dead", "")
            if entry.get("role") == "ruler":
                house.ruler = person.id
                person.ruled = True
                civ = self.civs.get(civ_id)
                if civ is not None:
                    person.personality = (civ.born or civ.personality).name
        for entry in data["members"]:
            person = ids[entry["id"]]
            if "parent" in entry:
                parent = ids[entry["parent"]]
                person.parents = [parent.id] + ([parent.spouse] if parent.spouse is not None else [])
            if "spouse" in entry:
                person.spouse = ids[entry["spouse"]].id
                ids[entry["spouse"]].spouse = person.id
        for entry in data["members"]:  # parents now know their spouses: children get both
            person = ids[entry["id"]]
            if "parent" in entry:
                parent = ids[entry["parent"]]
                person.parents = [parent.id] + ([parent.spouse] if parent.spouse is not None else [])
            if not person.personality:
                person.personality = self._inherit(person)

    def _found(self, civ) -> None:
        """A minor house for a civ no board was drawn for: a ruler, a consort and two children."""
        name = self._names["minor_houses"][civ.id % len(self._names["minor_houses"])]
        house = House(name.lower(), name, civ.id)
        self.houses[house.key] = house
        self.by_civ[civ.id] = house
        ruler = self._add(house, self._name("m"), "m", born_aged(50))
        consort = self._add(house, self._name("f"), "f", born_aged(46))
        ruler.spouse, consort.spouse = consort.id, ruler.id
        ruler.ruled, house.ruler = True, ruler.id
        ruler.personality = (civ.born or civ.personality).name
        for sex, age in (("m", 24), ("f", 20)):
            child = self._add(house, self._name(sex), sex, born_aged(age))
            child.face = self.rng.choice(FACES[sex])
            child.parents = [ruler.id, consort.id]
            child.personality = self._inherit(child)

    def _add(self, house: House, name: str, sex: str, birth_day: int, portrait: str = "") -> Character:
        person = Character(len(self.people) + 1, name, house.key, sex, birth_day, portrait=portrait)
        person.health = round(self.rng.uniform(0.7, 1.3), 2)
        # Those already alive at the start are checked on a day of their own, so a year's events
        # do not all fall on one day; anyone born later, on their birthday.
        person.check_day = birth_day % YEAR if birth_day > 0 else self.rng.randrange(YEAR)
        person.ambition = round(self.rng.random() ** 1.6, 2)
        if self.rng.random() < TRAIT_CHANCE:
            person.traits.append(self.rng.choice(TRAITS))
            if "sickly" in person.traits:
                person.health = round(person.health * SICKLY, 2)
        self.people[person.id] = person
        house.members.append(person.id)
        return person

    def _name(self, sex: str) -> str:
        return self.rng.choice(self._names[sex])

    def _inherit(self, person: Character) -> str:
        """Half take after a parent who ruled, the rest are their own kind of ruler."""
        ruling = [self.people[p] for p in person.parents if self.people[p].personality]
        if ruling and self.rng.random() < 0.5:
            return ruling[0].personality
        return self.rng.choice(sorted(self._archetypes["archetypes"]))

    # -- who is who ---------------------------------------------------------

    def house_of(self, civ_id: int) -> House | None:
        return self.by_civ.get(civ_id)

    def ruler(self, civ_id: int) -> Character | None:
        house = self.by_civ.get(civ_id)
        return self.people[house.ruler] if house and house.ruler is not None else None

    def children(self, person: Character) -> list[Character]:
        kids = [p for p in self.people.values() if person.id in p.parents]
        return sorted(kids, key=lambda p: (p.sex != "m", p.birth_day, p.id))  # sons first, eldest first

    def line(self, house: House) -> list[Character]:
        """Who would follow the ruler, in order: their children and each child's line in turn,
        then the ruler's brothers and sisters and their lines, then the rest of the house."""
        ruler = self.people[house.ruler] if house.ruler is not None else None
        order: list[Character] = []
        seen: set[int] = set()

        def descend(person: Character) -> None:
            for child in self.children(person):
                if child.id in seen:
                    continue
                seen.add(child.id)
                if child.alive and child.house == house.key and not child.deposed:
                    order.append(child)
                descend(child)

        if ruler is not None:
            seen.add(ruler.id)
            descend(ruler)
            for parent_id in ruler.parents:
                descend(self.people[parent_id])
        rest = [self.people[m] for m in house.members if m not in seen and self.people[m].alive
                and self.people[m].house == house.key and not self.people[m].deposed and self.people[m].id != house.ruler
                and self.people[m].spouse != house.ruler]
        order += sorted(rest, key=lambda p: (p.birth_day, p.id))
        return order

    def heir(self, house: House) -> Character | None:
        line = self.line(house)
        return line[0] if line else None

    def title(self, person: Character, house: House | None = None) -> str:
        house = house or self.houses[person.house]
        male = person.sex == "m"
        if house.ruler == person.id:
            return "King" if male else "Queen"
        ruler = self.people[house.ruler] if house.ruler is not None else None
        if ruler is not None and ruler.spouse == person.id:
            return "Prince" if male else "Queen"
        if any(self.people[p].ruled for p in person.parents):
            return "Prince" if male else "Princess"
        if person.ruled or (person.spouse is not None and self.people[person.spouse].ruled):
            return "King" if male else ("Dowager Queen" if person.alive else "Queen")
        return "Lord" if male else "Lady"

    def full_name(self, person: Character) -> str:
        return f"{self.title(person)} {person.name} {self.houses[person.house].name}"

    # -- every day ----------------------------------------------------------

    def update(self, tick: int, events: list) -> None:
        self.now = tick
        if self.betrayals:
            self._betrayals(tick, events)
        if tick % 30 == 0:
            self._captives_month(tick, events)
            self._govern(tick)
        for house in list(self.by_civ.values()):
            civ = self.civs[house.civ]
            if not civ.alive:
                continue
            if house.regent is not None:
                self._regency(house, civ, tick, events)
            for member_id in list(house.members):
                person = self.people[member_id]
                if not person.alive or person.house != house.key:
                    continue
                self._sudden(person, house, civ, tick, events)
                if person.alive and tick % YEAR == person.check_day:
                    self._birthday(person, house, civ, tick, events)

    def _sudden(self, person: Character, house: House, civ, tick: int, events: list) -> None:
        age = person.age(tick)
        royal = person.id == house.ruler or self.heir(house) is person
        enemies = self._enemies(civ.id) if royal else []
        rates = sudden_rates(age, self._sick(civ), len(enemies) if self.intrigue > 0 else 0, royal, self.intrigue)
        roll = self.rng.random() * YEAR
        for cause, rate in rates.items():
            if roll < rate:
                killer = None
                if cause in ("poison", "an assassin's knife"):
                    killer = self.civs[self.rng.choice(enemies)]
                self.die(person, tick, events, cause, killer)
                return
            roll -= rate
        if tick >= person.ill_until and self.rng.random() * YEAR < FALL_ILL:
            person.ill_until = tick + ILL_DAYS
            self.changed = tick
            if person.id == house.ruler or age < 10:
                self._log(events, civ, "illness", person, f"{self.full_name(person)} of {civ.name} falls gravely ill")

    def _birthday(self, person: Character, house: House, civ, tick: int, events: list) -> None:
        self.changed = tick
        age = person.age(tick)
        if self.rng.random() < natural_death_chance(age, person.health, tick < person.ill_until, person.wounds):
            self.die(person, tick, events, "old age" if age >= 60 else "a long illness")
            return
        if person.spouse is None and age >= ADULT:
            chance = MARRY_HEIR if self.heir(house) is person else MARRY
            if person.id != house.ruler and self.rng.random() < chance:
                self._marry(person, house, civ, tick, events)
        # A married woman of the house (or a man's wife) may give birth.
        wife = person if person.sex == "f" else None
        if wife is not None and wife.spouse is not None:
            husband = self.people[wife.spouse]
            age = wife.age(tick)
            if husband.alive and ADULT <= age <= FERTILE_UNTIL:
                if self.rng.random() < (BIRTH_YOUNG if age < 35 else BIRTH_OLDER):
                    self._birth(wife, husband, tick, events)
        if not person.alive:
            return
        if person.id == house.ruler and self.diplomacy is not None and ({"cruel", "kind"} & set(person.traits)):
            for other in self.civs.values():  # word of a cruel (or a kind) ruler spreads
                if other.id != civ.id and other.alive:
                    self.diplomacy.remember(other.id, civ.id, -CRUEL if "cruel" in person.traits else KIND)
        if house.regent == person.id:
            if self.rng.random() < REGENT_USURPS * person.ambition:
                self._usurp(person, house, civ, tick, events)
            return
        if self._may_plot(person, house, civ, tick) and self.rng.random() < self._plot_chance(person, house, civ, tick):
            self._plot(person, house, civ, tick, events)

    def _enemies(self, civ_id: int) -> list[int]:
        if self.diplomacy is None:
            return []
        foes = set(self.diplomacy.enemies(civ_id))
        foes |= {other for (who, other), value in self.diplomacy.standing.items()
                 if who != civ_id and other == civ_id and value <= BITTER and self.civs[who].alive}
        return sorted(foes)

    def _sick(self, civ) -> bool:
        return self.diplomacy is not None and self.diplomacy.sick(civ)

    # -- life's turns -------------------------------------------------------

    def _marry(self, person: Character, house: House, civ, tick: int, events: list) -> None:
        want = "f" if person.sex == "m" else "m"
        roll = self.rng.random()
        partner = None
        royal = False
        if roll < MATCH_ROYAL:
            partner = self._royal_match(person, house, want, tick)
            royal = partner is not None
        if partner is None and self.rng.random() < MATCH_POOL:
            pool = [p for p in self.people.values() if p.alive and p.sex == want and p.spouse is None
                    and self.houses[p.house].civ is None and abs(p.age(tick) - person.age(tick)) <= 12
                    and p.age(tick) >= ADULT]
            partner = self.rng.choice(pool) if pool else None
        if partner is None:  # a daughter or son of a minor noble family
            family = self.rng.choice(self._names["minor_houses"])
            age = max(ADULT, person.age(tick) + self.rng.randint(-5, 3))
            partner = self._add(house, self._name(want), want, born_aged(age, tick) - self.rng.randrange(YEAR))
            partner.born = family
            partner.face = self.rng.choice(FACES[want])
        # The bride joins her husband's house.
        wife, husband = (partner, person) if person.sex == "m" else (person, partner)
        if wife.house != husband.house:
            wife.born = wife.born or self.houses[wife.house].name
            self.houses[husband.house].members.append(wife.id)
            wife.house = husband.house
        person.spouse, partner.spouse = partner.id, person.id
        self.changed = tick
        if royal:
            a_civ, b_civ = self._civ_of_birth(husband), self._civ_of_birth(wife)
            if self.diplomacy is not None and a_civ is not None and b_civ is not None:
                self.diplomacy.remember(a_civ, b_civ, ROYAL_STANDING)
                self.diplomacy.remember(b_civ, a_civ, ROYAL_STANDING)
            names = [self.civs[c].name for c in (a_civ, b_civ) if c is not None]
            text = (f"{self.title(husband)} {husband.name} {self.houses[husband.house].name} weds "
                    f"{wife.name} of House {wife.born}: {' and '.join(names)} are joined")
            self._log(events, civ, "marriage", person, text, banner=True,
                      line=f"Two houses are joined: let {' and '.join(names)} stand together!",
                      civs=[c for c in (a_civ, b_civ) if c is not None])
        else:
            where = f"of House {partner.born}" if partner.born else ""
            self._log(events, civ, "marriage", person, f"{self.full_name(person)} of {civ.name} weds {partner.name} {where}".rstrip())

    def _house_by_name(self, name: str) -> str | None:
        return next((key for key, house in self.houses.items() if house.name == name), None)

    def _civ_of_birth(self, person: Character) -> int | None:
        key = self._house_by_name(person.born) if person.born else person.house
        return self.houses[key].civ if key in self.houses else None

    def _royal_match(self, person: Character, house: House, want: str, tick: int) -> Character | None:
        """An unmarried son or daughter of another ruling house, of an age, whose realm is not at
        war with this one and does not hate it."""
        options = []
        for other in self.by_civ.values():
            if other.key == house.key or not self.civs[other.civ].alive:
                continue
            if self.diplomacy is not None:
                if other.civ in self.diplomacy.enemies(house.civ):
                    continue
                if self.diplomacy.standing.get((other.civ, house.civ), 0.0) < 0:
                    continue
            heir = self.heir(other)
            for member in self.line(other):
                if (member.sex == want and member.spouse is None and member.age(tick) >= ADULT
                        and abs(member.age(tick) - person.age(tick)) <= 12 and member is not heir):
                    options.append(member)
        return self.rng.choice(options) if options else None

    def _birth(self, mother: Character, father: Character, tick: int, events: list) -> None:
        house = self.houses[father.house]
        sex = self.rng.choice("mf")
        child = self._add(house, self._name(sex), sex, tick)
        child.face = self.rng.choice(FACES[sex])
        child.parents = [father.id, mother.id]
        child.personality = self._inherit(child)
        self.changed = tick
        civ = self.civs[house.civ] if house.civ is not None else None
        if civ is not None:
            self._log(events, civ, "birth", child,
                      f"A {'son' if sex == 'm' else 'daughter'}, {child.name}, is born to {self.full_name(father)} "
                      f"and {mother.name} of {civ.name}")
        if self.rng.random() < CHILDBIRTH:
            self.die(mother, tick, events, "childbirth")

    def die(self, person: Character, tick: int, events: list, cause: str, killer=None, plotter=None,
            quiet: bool = False) -> Character | None:
        """A death, and if it was the ruler's, the succession. `killer` is a realm that had them
        murdered, `plotter` a kinsman who did. Returns the new ruler, if the ruler died."""
        if not person.alive:
            return None
        house = self.houses[person.house]
        civ = self.civs[house.civ] if house.civ is not None else None
        age = person.age(tick)
        name = self.full_name(person)
        person.alive, person.died, person.cause = False, tick, cause
        self.changed = tick
        if house.regent == person.id:
            house.regent = None
        if civ is None:
            return None
        was_ruler = house.ruler == person.id
        murdered = killer is not None
        how = {"old age": "dies of old age", "a long illness": "dies after a long illness",
               "childbirth": "dies in childbirth", "battle": "falls in battle",
               "executed for treason": "is executed for treason"}.get(cause, f"dies of {cause}")
        if murdered:
            how = f"is poisoned, and all eyes turn to {killer.name}" if cause == "poison" else \
                f"is murdered by an assassin, and all eyes turn to {killer.name}"
            if self.diplomacy is not None:
                self.diplomacy.remember(civ.id, killer.id, -2.0)
        elif plotter is not None:
            how = "is poisoned at the high table" if cause == "poison" else "is stabbed in the night"
        text = f"{name} of {civ.name} {how}, aged {age}"
        line = f"{house.name} mourns {person.name}."
        heir = None
        if was_ruler:
            heir = self._succeed(house, civ, tick, events)
            if heir is not None:
                text += f"; {self.title(heir)} {heir.name} takes the throne"
                if house.regent is not None:
                    regent = self.people[house.regent]
                    text += f", with {self.title(regent)} {regent.name} as regent"
                line = (f"The {'king' if person.sex == 'm' else 'queen'} is dead. Long live "
                        f"{self.title(heir)} {heir.name}!")
                if murdered:
                    line = f"{person.name} is slain by treachery! {heir.name} swears vengeance on {killer.name}."
                elif plotter is not None and heir is plotter:
                    line = f"The {'king' if person.sex == 'm' else 'queen'} is dead, and {heir.name} wastes no tears."
        elif murdered:
            line = f"Murder in the hall of {house.name}! {killer.name} will answer for {person.name}."
        if quiet:
            return heir
        kind = "assassination" if murdered or plotter is not None else ("succession" if was_ruler else "death")
        if cause == "executed for treason":
            kind, line = "execution", f"So ends {person.name}, who reached for a crown that was not theirs."
        self._log(events, civ, kind, person, text, banner=True, line=line,
                  civs=[civ.id] + ([killer.id] if murdered else []))
        return heir

    def _succeed(self, house: House, civ, tick: int, events: list | None = None) -> Character | None:
        heir = self.heir(house)
        if heir is None:  # the line is spent: blood married abroad may claim it, and a cousin comes forward
            if events is not None:
                self._claim(house, civ, tick, events)
            heir = self._add(house, self._name("m"), "m", born_aged(35 + self.rng.randrange(20), tick))
            heir.personality = self.rng.choice(sorted(self._archetypes["archetypes"]))
        house.ruler = heir.id
        heir.ruled = True
        house.regent = None
        if heir.age(tick) < RULE_AGE:  # a child on the throne: the mother, else the eldest grown kin, rules for them
            mother = next((self.people[p] for p in heir.parents if self.people[p].sex == "f"), None)
            if mother is not None and mother.alive and mother.house == house.key:
                house.regent = mother.id
            else:
                grown = [p for p in self.line(house) if p is not heir and p.age(tick) >= ADULT]
                house.regent = grown[0].id if grown else None
        self.unrest_until[civ.id] = tick + UNREST_DAYS
        self._crown(civ, heir)
        return heir

    # -- regency ------------------------------------------------------------

    def _regency(self, house: House, civ, tick: int, events: list) -> None:
        """A regency ends when the child on the throne comes of age (or the regent is gone)."""
        ruler = self.people[house.ruler]
        regent = self.people[house.regent]
        if not regent.alive or regent.house != house.key:
            house.regent = None
        elif ruler.age(tick) >= RULE_AGE:
            house.regent = None
            self.changed = tick
            self._log(events, civ, "regency", ruler,
                      f"{self.full_name(ruler)} of {civ.name} comes of age and rules alone; {regent.name}'s regency ends")

    def _usurp(self, regent: Character, house: House, civ, tick: int, events: list) -> None:
        """The regent takes the crown from the child it was holding it for."""
        child = self.people[house.ruler]
        child_name = self.full_name(child)
        house.regent = None
        if self.rng.random() < 0.5:
            self.die(child, tick, events, "a fever in the tower", plotter=regent, quiet=True)
            fate = "dies in the tower, and few believe it was a fever"
        else:
            child.deposed = True
            fate = "is sent to a monastery"
        house.ruler = regent.id
        regent.ruled = regent.usurper = True
        self.unrest_until[civ.id] = tick + UNREST_DAYS
        self._crown(civ, regent)
        self.changed = tick
        self._log(events, civ, "usurpation", regent,
                  f"{child_name} of {civ.name} {fate}; the regent {regent.name} takes the crown", banner=True,
                  line=f"A child cannot hold a kingdom. {regent.name} will.")

    # -- claims through marriage ----------------------------------------------

    def _claim(self, house: House, civ, tick: int, events: list) -> None:
        """A house whose line has died out: the blood of a daughter married into another ruling
        house gives that realm a claim to the throne, and a reason for war."""
        blood = [p for p in self.people.values() if p.alive and p.house != house.key and (
            p.born == house.name or any(self.people[q].born == house.name for q in p.parents))]
        for person in sorted(blood, key=lambda p: (p.birth_day, p.id)):
            other = self.houses[person.house]
            if other.civ is None or other.civ == civ.id or not self.civs[other.civ].alive:
                continue
            claimant = self.civs[other.civ]
            self.claims[(claimant.id, civ.id)] = {"by": person.id, "since": tick}
            self._log(events, claimant, "claim", person,
                      f"The line of {house.name} is spent: {self.full_name(person)} of {claimant.name} claims "
                      f"the crown of {civ.name} by blood", banner=True,
                      line=f"The crown of {civ.name} is {person.name}'s by right of blood!", civs=[claimant.id, civ.id])
            return

    def claim(self, civ_id: int, other_id: int, tick: int) -> str | None:
        """Whose claim `civ_id` has to the throne of `other_id` (a name), if one is pressed."""
        entry = self.claims.get((civ_id, other_id))
        if entry is None:
            return None
        person = self.people[entry["by"]]
        if not person.alive or tick - entry["since"] > CLAIM_DAYS or not self.civs[other_id].alive:
            del self.claims[(civ_id, other_id)]
            return None
        return f"{self.title(person)} {person.name}"

    # -- plots and rebellion ------------------------------------------------

    def _may_plot(self, person: Character, house: House, civ, tick: int) -> bool:
        if tick < PLOT_FROM or person.id == house.ruler or person.house != house.key or person.deposed:
            return False
        if person.age(tick) < ADULT or person.captive_of is not None or person.ambition < 0.3:
            return False
        if person.spouse == house.ruler:
            return False
        king = self.people[house.ruler]
        if self.heir(house) is person and king.age(tick) < 60 and house.regent is None:
            return False  # an heir with time on his side waits
        if len(civ.settlements) < MIN_REGIONS or self.rebellions.get(civ.id) in self._living_civs():
            return False
        return True

    def _living_civs(self) -> set[int]:
        return {c.id for c in self.civs.values() if c.alive}

    def _troubles(self, civ, tick: int) -> float:
        """How shaken the realm is: 0 calm, up to 1 in deep trouble."""
        house = self.by_civ[civ.id]
        king = self.people[house.ruler]
        trouble = 0.0
        # Old age, or a ruler under 18 whose competence is in doubt, invites plots.
        trouble += 0.3 if king.age(tick) >= 65 or king.age(tick) < ADULT else 0.0
        trouble += 0.2 if tick < king.ill_until else 0.0
        trouble += 0.3 if self.unrest(civ.id, tick) else 0.0
        trouble += 0.2 if self._sick(civ) else 0.0
        if self.diplomacy is not None:
            for enemy in self.diplomacy.enemies(civ.id):
                war = self.diplomacy.relation(civ.id, enemy).war
                if war is not None and self.diplomacy.ahead(war) == enemy:
                    trouble += 0.3  # losing a war
                    break
        return min(1.0, trouble)

    def _plot_chance(self, person: Character, house: House, civ, tick: int) -> float:
        ambition = person.ambition
        elder = [p for p in self.line(house) if p.sex == person.sex and p.birth_day < person.birth_day
                 and set(p.parents) & set(person.parents)]
        if elder:
            ambition += 0.15  # a younger son
        if person.personality == "Expansionist" or "cruel" in person.traits:
            ambition += 0.1
        if "proud" in person.traits:
            ambition += 0.15
        if "pious" in person.traits:
            ambition *= 0.5
        circumstances = 1.0 + 2.0 * self._troubles(civ, tick)
        return PLOT_BASE * self.intrigue * min(1.0, ambition) ** 2 * circumstances

    def _plot(self, person: Character, house: House, civ, tick: int, events: list) -> None:
        """An attempt on the ruler's life, and what comes of it."""
        king = self.people[house.ruler]
        was_heir = self.heir(house) is person
        means = self.rng.choice(("poison", "a knife"))
        if self.rng.random() < PLOT_SUCCESS:
            new = self.die(king, tick, events, means, plotter=person)
            if new is person and was_heir and self.rng.random() < UNSUSPECTED:
                person.usurper = True
                return  # he wears the crown, and nobody can prove a thing
            if new is person:  # found out on the throne: he keeps it, but the realm reels
                person.usurper = True
                self.unrest_until[civ.id] = tick + 2 * UNREST_DAYS
                self._log(events, civ, "usurpation", person,
                          f"{self.full_name(person)} of {civ.name} is named the murderer of {king.name}, and keeps the crown",
                          banner=True, line=f"Let them whisper. {person.name} wears the crown.")
                return
            reason = f"found out after the murder of {king.name}"
        else:
            reason = f"caught trying to {'poison' if means == 'poison' else 'stab'} {self.full_name(king)}"
        self._rebel(person, house, civ, tick, events, reason)

    def _rebel(self, person: Character, house: House, civ, tick: int, events: list, reason: str) -> None:
        """A plotter found out flees to a castle of the realm and raises a new realm against his
        king, or, with nowhere to go, is executed."""
        name = self.full_name(person)  # as they were known before
        castles = [s for s in civ.settlements[1:]]
        rebel = None
        castle = None
        if castles and self.spawn is not None:
            governed = next((s for s in castles if s.tile == person.governs), None)
            if governed is not None:  # the castle they rule for the crown is theirs already
                castle = governed
            else:
                castle = self.rng.choice(castles)
            rebel = self.spawn(person, civ, castle.tile, self._defection(person, civ, tick), tick, events)
        if rebel is None:
            self.die(person, tick, events, "executed for treason")
            return
        self.rebellions[civ.id] = rebel.id
        branch = House(f"{house.key}:{person.id}", rebel.name, rebel.id, ruler=person.id,
                       branch=f"{person.name}'s line, of the House of {house.name}", origin=house.key)
        self.houses[branch.key] = branch
        self.by_civ[rebel.id] = branch
        followers = [person] + ([self.people[person.spouse]] if person.spouse is not None else [])
        followers += [p for p in self._descendants(person)]
        for follower in followers:
            if follower.alive and follower.house == house.key:
                follower.house = branch.key
                branch.members.append(follower.id)
        person.ruled = True
        self.unrest_until[rebel.id] = -1
        self.changed = tick
        if self.diplomacy is not None:
            for enemy in self.diplomacy.enemies(civ.id):
                if enemy != rebel.id:
                    self.diplomacy.remember(enemy, rebel.id, 1.0)  # the enemy of my enemy
        line = proclaim(rebel.name, civ.name, "rebellion", person.name, random.Random(tick * 7 + person.id))
        self._log(events, rebel, "rebellion", person,
                  f"{name}, {reason}, seizes {castle.name} and raises the banner of revolt: "
                  f"{rebel.name} breaks away from {civ.name}", banner=True, line=line, civs=[rebel.id, civ.id])
        self._seek_patron(rebel, civ, person, tick, events)

    def _seek_patron(self, rebel, king, person: Character, tick: int, events: list) -> None:
        """The rebel looks abroad for a protector: the strongest realm at war with the king, or
        that hates him. It promises the rebel his land; whether it means it is another matter."""
        d = self.diplomacy
        if d is None:
            return
        options = [c for c in self.civs.values() if c.alive and c.id not in (rebel.id, king.id)
                   and (king.id in d.enemies(c.id) or d.standing.get((c.id, king.id), 0.0) <= -1.0)]
        if not options:
            return
        patron = max(options, key=lambda c: (d.strength(c), -c.id))
        d.pledge(patron, rebel, king, tick, events)
        ruler = self.ruler(patron.id)
        betrays = PATRON_BETRAYS + PATRON_TEMPER.get((patron.born or patron.personality).name, 0.0)
        if ruler is not None and "cruel" in ruler.traits:
            betrays += 0.2
        if self.rng.random() < betrays:
            self.betrayals[(patron.id, rebel.id)] = tick + self.rng.randint(*BETRAY_AFTER)
        else:
            self.bonds.add(frozenset((patron.id, rebel.id)))
            d.standing[(patron.id, rebel.id)] = d.standing[(rebel.id, patron.id)] = SWORN
        self._log(events, patron, "pledge", person,
                  f"{patron.name} takes up the cause of {person.name}, swearing that {rebel.name} shall keep its lands",
                  banner=True, line=f"{rebel.name} does not stand alone. {patron.name} marches with it!",
                  civs=[patron.id, rebel.id, king.id])

    def _betrayals(self, tick: int, events: list) -> None:
        """A patron that never meant its promise falls on the rebel when its day comes."""
        for (patron_id, rebel_id), day in list(self.betrayals.items()):
            if tick < day:
                continue
            del self.betrayals[(patron_id, rebel_id)]
            patron, rebel = self.civs[patron_id], self.civs[rebel_id]
            if not (patron.alive and rebel.alive) or self.diplomacy.relation(patron_id, rebel_id).status != "alliance":
                continue
            self.diplomacy.turn_on(patron, rebel, tick, events)
            leader = self.ruler(rebel_id)
            if leader is not None:
                self._log(events, patron, "betrayal", leader,
                          f"{patron.name} breaks its oath and falls on {rebel.name}: {leader.name}'s lands are its prize",
                          banner=True, line=f"Promises are for the weak. {rebel.name}'s lands are ours now.",
                          civs=[patron_id, rebel_id])

    def realm_fell(self, loser, captor, tick: int, events: list) -> None:
        """A realm is gone. A rebel ruler is taken alive: by his own father's realm he is put
        aside, by anyone else held for ransom (`_ransoms`)."""
        house = self.by_civ.get(loser.id)
        if house is None or not house.origin or house.ruler is None:
            return
        person = self.people[house.ruler]
        if not person.alive:
            return
        father = self.houses.get(house.origin)
        self.changed = tick
        if father is not None and father.civ == captor.id:
            self._return(person, father, deposed=True)
            self._log(events, captor, "captured", person,
                      f"{person.name} is dragged before the court of {captor.name}, stripped of every title, and locked away",
                      banner=True, line=f"The rebellion is over. {person.name} will never see the sky again.",
                      civs=[captor.id])
            return
        person.captive_of = captor.id
        self._log(events, captor, "captured", person,
                  f"{captor.name} takes {person.name} alive as {loser.name} falls, and names a ransom",
                  banner=True, line=f"{person.name} is ours. Let the old king pay to have his child back.",
                  civs=[captor.id] + ([father.civ] if father and father.civ is not None else []))

    def _return(self, person: Character, house: House, deposed: bool) -> None:
        person.house = house.key
        person.captive_of = None
        person.deposed = deposed
        if person.id not in house.members:
            house.members.append(person.id)

    def _ransoms(self, tick: int, events: list) -> None:
        """A realm whose blood is held captive buys them back, if it can afford it."""
        for person in self.people.values():
            if not person.alive or person.captive_of is None:
                continue
            home_id = self._home(person)
            if home_id is None or not self.civs[home_id].alive or not self.civs[person.captive_of].alive:
                continue
            home, captor = self.civs[home_id], self.civs[person.captive_of]
            if home.resources.get("gold", 0.0) < ROYAL_RANSOM + 50:
                continue
            home.resources["gold"] -= ROYAL_RANSOM
            captor.resources["gold"] = captor.resources.get("gold", 0.0) + ROYAL_RANSOM
            rebel = bool(self.houses[person.house].origin)
            self._free(person, tick)
            self._log(events, home, "ransom", person,
                      f"{home.name} pays {captor.name} {ROYAL_RANSOM} gold for {self.full_name(person)}"
                      + (", who comes home in chains" if rebel else ""),
                      banner=True, line=(f"{person.name} is home, and will answer for what was done." if rebel
                                         else f"{person.name} is home! The bells ring in {home.name}."),
                      civs=[home.id, captor.id])

    def _govern(self, tick: int) -> None:
        """Every castle of a realm but its capital (which the ruler holds) is ruled for the
        crown by a grown member of the house: the ruler's children first, then the rest of the
        line. One who dies, is taken, goes to war or loses the castle is replaced."""
        for house in self.by_civ.values():
            civ = self.civs[house.civ]
            if not civ.alive or not civ.settlements:
                continue
            castles = [s.tile for s in civ.settlements[1:]]
            line = self.line(house)
            held = {}
            for person in line:
                if person.governs is not None:
                    if person.governs in castles and person.captive_of is None and person.governs not in held:
                        held[person.governs] = person
                    else:
                        person.governs = None
                        self.changed = tick
            free = [p for p in line if p.governs is None and p.captive_of is None and p.age(tick) >= ADULT]
            for tile in castles:
                if tile not in held and free:
                    free.pop(0).governs = tile
                    self.changed = tick

    def governor_bonus(self, person: Character) -> tuple[str, float, str] | None:
        """What a governor brings: fixed by who they are (their trait, else their personality)."""
        for trait in person.traits:
            if trait in GOVERNOR_TRAITS:
                return GOVERNOR_TRAITS[trait]
        return GOVERNOR_PERSONALITIES.get(person.personality)

    def governors(self, civ_id: int) -> list[Character]:
        house = self.by_civ.get(civ_id)
        return [p for p in self.line(house) if p.governs is not None] if house is not None else []

    def governor_defence(self, civ_id: int, tile: int) -> float:
        """Extra defence a brave governor gives the castle they rule."""
        for person in self.governors(civ_id):
            bonus = self.governor_bonus(person)
            if person.governs == tile and bonus is not None and bonus[0] == "defense":
                return bonus[1]
        return 0.0

    def ruler_of(self, civ_id: int, tile: int) -> str | None:
        """Who rules the castle on `tile` for its realm: the ruler at the capital, else its governor."""
        house = self.by_civ.get(civ_id)
        civ = self.civs.get(civ_id)
        if house is None or civ is None or not civ.settlements or house.ruler is None:
            return None
        if civ.settlements[0].tile == tile:
            return self.full_name(self.people[house.ruler])
        governor = next((p for p in self.line(house) if p.governs == tile), None)
        if governor is None:
            return None
        bonus = self.governor_bonus(governor)
        return self.full_name(governor) + (f" ({bonus[2]})" if bonus is not None else "")

    def _descendants(self, person: Character) -> list[Character]:
        found = []
        for child in self.children(person):
            found.append(child)
            found += self._descendants(child)
        return found

    def _defection(self, person: Character, civ, tick: int) -> float:
        """The share of the king's soldiers who follow a rebel."""
        return min(DEFECT_MAX, DEFECT_BASE + 0.1 * self._troubles(civ, tick) + 0.05 * person.ambition)

    def personality_of(self, person: Character) -> Personality:
        name = person.personality or self.rng.choice(sorted(self._archetypes["archetypes"]))
        jitter = self._archetypes["jitter"]
        return Personality(name, {key: round(value * (1 + self.rng.uniform(-jitter, jitter)), 3)
                                  for key, value in self._archetypes["archetypes"][name].items()})

    # -- captives, traits ---------------------------------------------------

    def _home(self, person: Character) -> int | None:
        """The realm a captive belongs to: their house's, or for a rebel's family their father's."""
        house = self.houses[person.house]
        if house.origin:
            house = self.houses[house.origin]
        return house.civ

    def castle_fell(self, loser, captor, tile: int, was_main: bool, tick: int, events: list) -> None:
        """A castle changes hands. Its governor is taken by the captor, or gets away home; and if
        it was the loser's own capital, any of the captor's family held there are set free."""
        house = self.by_civ.get(loser.id)
        if house is not None:
            governor = next((p for p in self.line(house) if p.governs == tile and p.alive), None)
            if governor is not None:
                governor.governs = None
                self.changed = tick
                if self.rng.random() < ESCAPE:
                    self._log(events, loser, "escape", governor,
                              f"{self.full_name(governor)}, who ruled the fallen castle, escapes to {loser.name}")
                else:
                    governor.captive_of = captor.id
                    self._log(events, captor, "captured", governor,
                              f"{captor.name} takes {self.full_name(governor)} of {loser.name} prisoner with the castle",
                              banner=True, line=f"{governor.name} is ours. {loser.name} will pay to have them back.",
                              civs=[captor.id, loser.id])
        if was_main:
            for person in self.people.values():
                if person.alive and person.captive_of == loser.id and self._home(person) == captor.id:
                    self._free(person, tick)
                    self._log(events, captor, "rescue", person,
                              f"{captor.name} takes {loser.name}'s capital and frees {self.full_name(person)}",
                              banner=True, line=f"{person.name} is free! The prison is ours.", civs=[captor.id, loser.id])

    def _free(self, person: Character, tick: int) -> None:
        """A captive comes home: a rebel's child to their father's house, put aside; anyone else
        to their own."""
        house = self.houses[person.house]
        if house.origin:
            self._return(person, self.houses[house.origin], deposed=True)
        person.captive_of = None
        self.changed = tick

    def _captives_month(self, tick: int, events: list) -> None:
        """Once a month, for each royal held captive: the captor may put them to death; two realms
        holding each other's blood exchange them; or the captive's realm buys them back."""
        held = [p for p in self.people.values() if p.alive and p.captive_of is not None]
        for person in held:
            home_id = self._home(person)
            captor = self.civs.get(person.captive_of)
            if captor is None or not captor.alive or home_id is None or not self.civs[home_id].alive:
                self._free(person, tick)
                continue
            if self._execute(person, captor, self.civs[home_id], tick, events):
                continue
        for person in [p for p in held if p.alive and p.captive_of is not None]:
            home_id = self._home(person)
            other = next((q for q in self.people.values() if q.alive and q is not person and q.captive_of == home_id
                          and self._home(q) == person.captive_of), None)
            if other is not None:  # each realm holds one of the other's: an exchange
                captor = self.civs[person.captive_of]
                self._free(person, tick)
                self._free(other, tick)
                self._log(events, self.civs[home_id], "exchange", person,
                          f"{self.civs[home_id].name} and {captor.name} exchange their prisoners: "
                          f"{self.full_name(person)} for {self.full_name(other)}",
                          banner=True, line=f"{person.name} comes home, and {other.name} goes back to {captor.name}.",
                          civs=[home_id, captor.id])
        self._ransoms(tick, events)

    def _execute(self, person: Character, captor, home, tick: int, events: list) -> bool:
        """The captor puts a royal captive to death: likelier if its ruler is cruel, or it is at
        war with or bitterly against the captive's realm. Never forgiven by that realm (no
        alliance with it ever again), thought unworthy by the rest, and welcomed by those who
        hate the victim's realm."""
        if self.intrigue <= 0 or self.diplomacy is None:
            return False
        chance = EXECUTE * self.intrigue
        ruler = self.ruler(captor.id)
        if ruler is not None and "cruel" in ruler.traits:
            chance *= 2.0
        if self.diplomacy.relation(captor.id, home.id).status == "war":
            chance *= 1.5
        if self.diplomacy.standing.get((captor.id, home.id), 0.0) <= -2.0:
            chance *= 1.5
        if self.rng.random() >= chance:
            return False
        name = self.full_name(person)
        self.die(person, tick, events, f"execution by {captor.name}", quiet=True)
        d = self.diplomacy
        d.feuds.add(frozenset((captor.id, home.id)))
        d.standing[(home.id, captor.id)] = -3.0
        for other in self.civs.values():
            if other.id in (captor.id, home.id) or not other.alive:
                continue
            if d.standing.get((other.id, home.id), 0.0) <= -1.0:
                d.remember(other.id, captor.id, EXECUTION_FAVOUR)  # the enemy of my enemy
            else:
                d.remember(other.id, captor.id, -EXECUTION_SHAME)  # unworthy, and cowardly
        self._log(events, captor, "execution", person,
                  f"{captor.name} puts {name} of {home.name} to death; {home.name} swears it will never forget",
                  banner=True, line=f"There will be no peace of hearts between {home.name} and {captor.name} again.",
                  civs=[captor.id, home.id])
        return True

    def _populate(self, house: House) -> None:
        """More of the family alive at the start: the ruler's grown children and brothers and
        sisters (22 and over) are married, to someone from a house that only marries in or of
        minor nobility, with a child or two of their own (shared faces, grown by their age)."""
        for person in list(self.line(house)):
            age = person.age(0)
            if not person.alive or person.spouse is not None or age < 22:
                continue
            want = "f" if person.sex == "m" else "m"
            pool = [p for p in self.people.values() if p.alive and p.sex == want and p.spouse is None
                    and self.houses[p.house].civ is None and p.age(0) >= ADULT and abs(p.age(0) - age) <= 10]
            if pool:
                partner = self.rng.choice(sorted(pool, key=lambda p: p.id))
                partner.born = partner.born or self.houses[partner.house].name
                house.members.append(partner.id)
                partner.house = house.key
            else:
                partner = self._add(house, self._name(want), want, born_aged(max(ADULT, age - 2)))
                partner.born = self.rng.choice(self._names["minor_houses"])
                partner.face = self.rng.choice(FACES[want])
            person.spouse, partner.spouse = partner.id, person.id
            for k in range(1 if age < 28 else 2):
                child_age = max(1, age - 21 - self.rng.randrange(4) - 3 * k)
                sex = self.rng.choice("mf")
                child = self._add(house, self._name(sex), sex, born_aged(child_age))
                child.face = self.rng.choice(FACES[sex])
                child.parents = [person.id, partner.id]
                child.personality = self._inherit(child)

    def apply_modifiers(self, civ, mods) -> None:
        """A learned ruler's realm learns faster."""
        ruler = self.ruler(civ.id)
        if ruler is not None and "learned" in ruler.traits:
            mods.science_mult += LEARNED
        # Each governor's own bonus, for the whole realm (a brave one's defence is for their castle only).
        for person in self.governors(civ.id):
            bonus = self.governor_bonus(person)
            if bonus is None or bonus[0] == "defense":
                continue
            key, amount, _ = bonus
            if key in mods.yield_mult:
                mods.yield_mult[key] += amount
            else:
                setattr(mods, key, getattr(mods, key) + amount)

    def _crown(self, civ, heir: Character) -> None:
        """The heir rules by their own lights: the civ's personality becomes theirs."""
        if not heir.personality or heir.personality == (civ.born or civ.personality).name:
            return
        jitter = self._archetypes["jitter"]
        weights = {key: round(value * (1 + self.rng.uniform(-jitter, jitter)), 3)
                   for key, value in self._archetypes["archetypes"][heir.personality].items()}
        civ.born = Personality(heir.personality, weights)
        civ.personality = with_focus(civ.born, civ.focus)

    def unrest(self, civ_id: int, tick: int) -> bool:
        return tick < self.unrest_until.get(civ_id, -1)

    # -- telling it ---------------------------------------------------------

    def _log(self, events: list, civ, kind: str, person: Character, text: str, banner: bool = False,
             line: str = "", civs: list | None = None) -> None:
        events.append({"civ": civ.id, "kind": "family", "text": text,
                       "family": {"type": kind, "person": person.id, "portrait": person.picture(self.now),
                                  "crest": f"{PORTRAITS}/{person.house.split(':')[0]}/crest.png", "banner": banner,
                                  "line": line, "dead": not person.alive, "civs": civs or [civ.id]}})
        if self.diplomacy is not None:
            self.diplomacy.history.append({"tick": self.now, "civs": civs or [civ.id], "text": text})

    def describe(self, tick: int) -> list[dict]:
        """Every ruling house for the viewer: its members, living and dead, the ruler first."""
        result = []
        for civ_id, house in sorted(self.by_civ.items()):
            heir = self.heir(house)
            members = []
            for member_id in house.members:
                person = self.people[member_id]
                if person.house != house.key and person.alive:
                    continue  # married away
                members.append({
                    "id": person.id, "name": person.name, "title": self.title(person, house),
                    "sex": person.sex,
                    "age": person.age(person.died if person.died is not None else tick) if person.alive or person.died is not None else None,
                    "alive": person.alive, "died": person.died, "cause": person.cause,
                    "portrait": person.picture(person.died if person.died is not None else tick), "born": person.born,
                    "ruler": house.ruler == person.id, "heir": heir is person,
                    "ill": tick < person.ill_until, "wounds": person.wounds,
                    "personality": person.personality,
                    "parents": list(person.parents), "spouse": person.spouse,
                    "traits": person.traits + (["ambitious"] if person.ambition >= AMBITIOUS and person.alive else [])
                              + (["usurper"] if person.usurper else []),
                    "regent": house.regent == person.id, "deposed": person.deposed,
                    "captive": self.civs[person.captive_of].name if person.captive_of is not None else "",
                    "governs": next((s.name for s in self.civs[house.civ].settlements if s.tile == person.governs), ""),
                    "governor_bonus": (self.governor_bonus(person) or (None, 0, ""))[2] if person.governs is not None else "",
                })
            members.sort(key=lambda m: (not m["ruler"], not m["heir"], not m["alive"], m["died"] or 0,
                                        -(m["age"] or 0)))
            base = house.key.split(":")[0]
            result.append({"civ": civ_id, "house": house.name, "key": house.key, "branch": house.branch,
                           "crest": f"{PORTRAITS}/{base}/crest.png" if base in _BOARD_HOUSES else "",
                           "unrest": self.unrest(civ_id, tick), "members": members})
        return result


_BOARD_HOUSES = set(load_json("houses.json")["houses"])
