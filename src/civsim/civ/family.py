"""Royal families: each civ is ruled by a house (data/houses.json, from the portrait boards) whose
members age, marry, have children, fall ill and die, and whose ruler is followed by an heir.

Ageing is exact: a character is one year older for every 365 days (age = (day - birth_day) //
365; members alive at the start are born `age * 365` days before day 0). Once a year (on their
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

All of it rolls its own dice (seeded from the game's seed), so a family never disturbs the rest
of the game's random streams, and a replay of a seed sees the same deaths.
"""

import math
import random
from dataclasses import dataclass, field

from ..datafiles import load_json
from .personality import Personality, with_focus

YEAR = 365
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
PRINCE_COMMANDS = 0.25  # chance a new commander is a prince of the house, if one is free
WOUND_CHANCE = 0.25  # a prince whose army is routed and who escapes comes back wounded
ROYAL_STANDING = 1.0  # how much better two ruling houses think of each other once joined by marriage

PORTRAITS = "res://assets/portraits"
FACES = {"m": (0, 2, 4), "f": (1, 3, 5)}  # the shared faces (portraits/common), by sex
GROWN = 16  # from this age a shared face is shown grown up


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
    commanding: bool = False  # leads an army

    def age(self, day: int) -> int:
        return (day - self.birth_day) // YEAR

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


def natural_death_chance(age: int, health: float = 1.0, ill: bool = False, wounds: int = 0) -> float:
    """The chance of dying of old age and ordinary decline within the coming year."""
    chance = MORTALITY_A * math.exp(MORTALITY_B * (age - 30)) * health
    chance *= (ILL_MULT if ill else 1.0) * WOUND_MULT ** wounds
    return min(MORTALITY_CAP, chance)


def sudden_rates(age: int, sick_realm: bool = False, enemies: int = 0, royal: bool = False) -> dict[str, float]:
    """Yearly chances of each sudden death, apart from ageing: any of them can strike at any age."""
    rates = {
        "a stroke": STROKE[0] * math.exp(STROKE[1] * (age - 30)),
        "heart failure": HEART[0] * math.exp(HEART[1] * (age - 30)),
        "a sudden fever": SUDDEN_ILLNESS,
        "a fall from the saddle": ACCIDENT,
    }
    if sick_realm:
        rates["the plague"] = PLAGUE
    if royal and enemies:
        rates["poison"] = min(MURDER_CAP, MURDER * enemies) * 0.4
        rates["an assassin's knife"] = min(MURDER_CAP, MURDER * enemies) * 0.6
    return rates


class Families:
    def __init__(self, civs: list, seed: int, diplomacy=None):
        self.rng = random.Random(seed * 104729 + 7)
        self.civs = {civ.id: civ for civ in civs}
        self.diplomacy = diplomacy
        self.military = None  # set by the simulation: commanders who are princes
        self.people: dict[int, Character] = {}
        self.houses: dict[str, House] = {}
        self.by_civ: dict[int, House] = {}
        self.changed = 0  # the last day anything about a family changed (the viewer is sent them then)
        self.unrest_until: dict[int, int] = {}  # civ id -> the day its unrest ends
        self.later: list[dict] = []  # events from elsewhere in the day (a prince falling in battle)
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

    # -- building the houses ------------------------------------------------

    def _load(self, key: str, data: dict, civ_id: int | None) -> None:
        house = House(key, data["name"], civ_id)
        self.houses[key] = house
        if civ_id is not None:
            self.by_civ[civ_id] = house
        ids = {}
        for entry in data["members"]:
            person = self._add(house, entry["name"], entry["sex"], -entry.get("age", 0) * YEAR,
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
        ruler = self._add(house, self._name("m"), "m", -50 * YEAR)
        consort = self._add(house, self._name("f"), "f", -46 * YEAR)
        ruler.spouse, consort.spouse = consort.id, ruler.id
        ruler.ruled, house.ruler = True, ruler.id
        ruler.personality = (civ.born or civ.personality).name
        for sex, age in (("m", 24), ("f", 20)):
            child = self._add(house, self._name(sex), sex, -age * YEAR)
            child.face = self.rng.choice(FACES[sex])
            child.parents = [ruler.id, consort.id]
            child.personality = self._inherit(child)

    def _add(self, house: House, name: str, sex: str, birth_day: int, portrait: str = "") -> Character:
        person = Character(len(self.people) + 1, name, house.key, sex, birth_day, portrait=portrait)
        person.health = round(self.rng.uniform(0.7, 1.3), 2)
        # Those already alive at the start are checked on a day of their own, so a year's events
        # do not all fall on one day; anyone born later, on their birthday.
        person.check_day = birth_day % YEAR if birth_day > 0 else self.rng.randrange(YEAR)
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
                if child.alive and child.house == house.key:
                    order.append(child)
                descend(child)

        if ruler is not None:
            seen.add(ruler.id)
            descend(ruler)
            for parent_id in ruler.parents:
                descend(self.people[parent_id])
        rest = [self.people[m] for m in house.members if m not in seen and self.people[m].alive
                and self.people[m].house == house.key and self.people[m].id != house.ruler
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
        events.extend(self.later)
        self.later.clear()
        for house in list(self.by_civ.values()):
            civ = self.civs[house.civ]
            if not civ.alive:
                continue
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
        rates = sudden_rates(age, self._sick(civ), len(enemies), royal)
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
            partner = self._add(house, self._name(want), want, tick - age * YEAR - self.rng.randrange(YEAR))
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

    def wound(self, person_id: int, tick: int) -> None:
        person = self.people.get(person_id)
        if person is not None and person.alive and self.rng.random() < WOUND_CHANCE:
            person.wounds += 1
            self.changed = tick

    def die(self, person: Character, tick: int, events: list, cause: str, killer=None) -> None:
        """A death, and if it was the ruler's, the succession."""
        if not person.alive:
            return
        house = self.houses[person.house]
        civ = self.civs[house.civ] if house.civ is not None else None
        age = person.age(tick)
        name = self.full_name(person)
        person.alive, person.died, person.cause = False, tick, cause
        self.changed = tick
        if self.military is not None and person.commanding:
            self.military.lose_prince(person.id, tick)
        if civ is None:
            return
        was_ruler = house.ruler == person.id
        murdered = killer is not None
        how = {"old age": "dies of old age", "a long illness": "dies after a long illness",
               "childbirth": "dies in childbirth", "battle": "falls in battle"}.get(cause, f"dies of {cause}")
        if murdered:
            how = f"is poisoned, and all eyes turn to {killer.name}" if cause == "poison" else \
                f"is murdered by an assassin, and all eyes turn to {killer.name}"
            if self.diplomacy is not None:
                self.diplomacy.remember(civ.id, killer.id, -2.0)
        text = f"{name} of {civ.name} {how}, aged {age}"
        line = f"{house.name} mourns {person.name}."
        if was_ruler:
            heir = self._succeed(house, civ, tick)
            if heir is not None:
                text += f"; {self.title(heir)} {heir.name} takes the throne"
                line = (f"The {'king' if person.sex == 'm' else 'queen'} is dead. Long live "
                        f"{self.title(heir)} {heir.name}!")
                if murdered:
                    line = f"{person.name} is slain by treachery! {heir.name} swears vengeance on {killer.name}."
        elif murdered:
            line = f"Murder in the hall of {house.name}! {killer.name} will answer for {person.name}."
        kind = "assassination" if murdered else ("succession" if was_ruler else "death")
        self._log(events, civ, kind, person, text, banner=True, line=line,
                  civs=[civ.id] + ([killer.id] if murdered else []))

    def _succeed(self, house: House, civ, tick: int) -> Character | None:
        heir = self.heir(house)
        if heir is None:  # the line is spent: a cousin comes forward
            heir = self._add(house, self._name("m"), "m", tick - (35 + self.rng.randrange(20)) * YEAR)
            heir.personality = self.rng.choice(sorted(self._archetypes["archetypes"]))
        house.ruler = heir.id
        heir.ruled = True
        self.unrest_until[civ.id] = tick + UNREST_DAYS
        self._crown(civ, heir)
        return heir

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

    # -- commanders ---------------------------------------------------------

    def free_prince(self, civ_id: int, tick: int) -> Character | None:
        """A grown son of the house, not the ruler and not already in command, who can lead an
        army; picked now and then (PRINCE_COMMANDS)."""
        house = self.by_civ.get(civ_id)
        if house is None or self.rng.random() >= PRINCE_COMMANDS:
            return None
        options = [p for p in self.line(house) if p.sex == "m" and not p.commanding and ADULT <= p.age(tick) <= 55]
        return options[0] if options else None

    # -- telling it ---------------------------------------------------------

    def _log(self, events: list, civ, kind: str, person: Character, text: str, banner: bool = False,
             line: str = "", civs: list | None = None) -> None:
        events.append({"civ": civ.id, "kind": "family", "text": text,
                       "family": {"type": kind, "person": person.id, "portrait": person.picture(self.now),
                                  "crest": f"{PORTRAITS}/{person.house}/crest.png", "banner": banner,
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
                    "ill": tick < person.ill_until, "wounds": person.wounds, "commanding": person.commanding,
                    "personality": person.personality,
                })
            members.sort(key=lambda m: (not m["ruler"], not m["heir"], not m["alive"], m["died"] or 0,
                                        -(m["age"] or 0)))
            result.append({"civ": civ_id, "house": house.name, "key": house.key,
                           "crest": f"{PORTRAITS}/{house.key}/crest.png" if house.key in _BOARD_HOUSES else "",
                           "unrest": self.unrest(civ_id, tick), "members": members})
        return result


_BOARD_HOUSES = set(load_json("houses.json")["houses"])
