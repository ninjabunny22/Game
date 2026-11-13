"""Armies on the map: raising them, marching, fighting, and taking ground.

This gives phase 3's war rules a physical form without changing their maths.
Strength is still soldiers x quality (military techs, pay, ore), now summed over
unit types with their counters and multiplied by the commander's skill. The
casualty and capture formulas, home bonus, militia, terrain prices and betrayal
surprise are the ones in diplomacy/rules.py; what is new is *where* they apply:
at an army's position rather than along the whole border.

The strategic layer still only sets intent. Everything here is rule-based:
  - a civ at war fields one army per enemy, each under a commander, plus a
    garrison at the capital;
  - an aggressor's army paths to the enemy capital and captures the enemy tiles
    in its way; a defender's army marches to intercept armies on its land;
  - armies within one tile of each other fight every tick until one breaks; how
    long that takes depends only on how evenly matched they are;
  - cavalry need horses from the stables, one each; a cavalryman who is lost takes his
    horse with him, and those stood down return theirs;
  - a civ keeps at most 20 commanders; new ones cost gold, and those without an
    army are stationed at the capitals nearest an enemy, which they help defend;
  - soldiers the losing side lost in a battle are mostly wounded or scattered,
    and its commander may be killed or captured;
  - the victor of a battle chases the routed army if it can keep up, cutting it
    down as it runs; soldiers lost that way are mostly wounded or scattered rather
    than killed, and a commander whose army is run down may be taken prisoner;
  - a civ at peace sends an expedition against a neighbouring native capital
    once its army is about twice the garrison's strength.
"""

import random
from collections.abc import Callable

from ..diplomacy import rules
from ..economy.harbours import ports
from ..config import HEADCOUNT
from ..economy.production import soldier_cost
from ..economy.rules import HEAL_TICKS, INFIRMARY_BEDS, MIN_POPULATION
from ..map import WorldMap, find_path, region_neighbours, step_cost
from .army import LEADERLESS_CAPACITY, XP_PER_LEVEL_STEP, Army, Captive, Commander, Rally
from .units import BASE_UNIT, MAX_TIER, UNIT_TYPES, tier_strength, unit_strength

GARRISON_KEEP = 0.2  # share of the soldiers that stays to hold the capital during a war ...
GUARDED_KEEP = 0.35  # ... or while a civ it is not yet fighting is set on attacking it
WALL_DETOUR = 4  # tiles further an army will go for a capital one point less strongly held
MAX_ARMIES = 5  # field armies a civ can have out at once; the rest of its soldiers hold its capitals
FULL = 0.9  # share of what its commander can lead at which an army counts as full
EXPEDITION_CAPACITY = 2.0  # an expedition against natives takes levies along: this many times the usual
# Rallies: allies gather in one city and march on an enemy city as a single army.
RALLY_GATHER = 40  # ticks the armies have to reach the city
RALLY_REST = 200  # ticks before a civ calls another
RALLY_REACH = 30  # tiles: armies further than this from the city could not get there in time, and do not try
RALLY_SPOILS = 0.15  # share of the leader's gold divided among those who helped take the city
HOME_CALL = 8  # tiles: an intruder further than this from every army gets a force of its own raised against it
JOINT_PULL = 10  # tiles further an army will go to attack the capital an ally is already attacking
OUTMATCHED = 1.8  # an army falls back from enemies within reach this many times its strength
DANGER_RADIUS = 3  # ... counted this many tiles around it
# An army fills its ranks only in one of its civ's capitals: one worn down in the field goes home for more.
REFIT_BELOW = 0.5  # share of what its commander can lead below which an army goes home to refill ...
REFIT_WAITING = 0.25  # ... if at least this share of that is waiting in the garrison
# Better arms, once the civ has learned to make them, are handed out in its capitals.
UPGRADE_GOLD = 0.3  # to bring one soldier up one tier ...
UPGRADE_ORE = 0.1
UPGRADE_PER_TICK = 3.0  # ... and how many soldiers a day can be re-armed
# Standing with an ally: an army sent to one of its capitals that an enemy is at or near.
REINFORCE_ALERT = 4  # tiles: an enemy army this close to a capital threatens it
REINFORCE_REACH = 40  # tiles from our capital beyond which no help is sent
REINFORCE_STAY = 30  # ticks the army stays on after the threat has gone
REINFORCE_RETRY = 150  # ticks before trying again for a capital there was no way to
SCOUT_RANGE = 6  # tiles within which a civ's armies and capitals can count an army exactly
# Holding a castle: a general near one of his civ's own capitals that is threatened, and too
# weakly held for the threat, leaves part of his army behind to hold it.
DETACH_REACH = 6  # tiles: how near the castle the army must be
DETACH_MAX = 0.5  # the most of his army he will leave
HOLD_STAY = 30  # days the holding force stays once the danger has passed, before joining the garrison
# A castle's garrison is known only roughly, to within this many soldiers either way (in the
# head count shown), unless one of the civ's armies has attacked the castle lately.
GARRISON_GUESS = 30
PROBE_MEMORY = 30  # days for which an attack on a castle keeps its garrison known exactly
GUESS_FRESH = 100  # days after which the guess is made again (it does not wander day to day)
MIN_FIELD_ARMY = 3.0  # soldiers below which an army will not set out
REPLAN_TICKS = 15
DEFENCE_RADIUS = 6  # a defending army also answers threats this close to the capital
# Battles have no fixed length: an army breaks when it is outmatched, and nothing else ends one.
# The casualty rate sets the pace. At 2.5 times the base rate a lopsided battle is over in a
# few ticks and a close one (armies within 10% of each other) takes roughly 40 to 100.
BATTLE_INTENSITY = 2.5
ROUT_RATIO = 0.5  # an army breaks when its strength falls below this share of its opponent's
RALLY_TICKS = 30  # rest at the capital after a rout before marching again
REPLACEMENT_TICKS = 30

# Pursuit: the winner of a battle chases the routed army if it can keep up.
PURSUIT_DAYS = 8  # how long a chase lasts at most
PURSUIT_RANGE = 6  # ... and how far from the battlefield it goes
PURSUIT_THREAT_RADIUS = 3  # no chase with another enemy army this close
PURSUIT_LOSS = 0.15  # share of the army as it was when it broke, cut off each tick it is caught; it cannot fight back
PURSUIT_FINISH = 0.2  # an army reduced to this share of what it had when it broke is finished off
DISORDER = 0.8  # strength of a pursuer if engaged during the chase or just after
DISORDER_DAYS = 5

# What becomes of the soldiers a beaten army lost in the battle, or loses in a pursuit, and of
# its commander: rolled when the army is routed, and again if it is then run down.
WOUNDED_SHARE = 0.6  # out of action: they go to hospital, and die if there is no bed for them
WOUNDED_IN_VICTORY = 0.5  # share of the losses of an army that was not broken who are wounded, not dead
ESCAPE_SHARE = 0.3  # make their own way home and rejoin the garrison
DEAD_SHARE = 0.1
COMMANDER_DEATH_CHANCE = 0.10
CAPTURE_CHANCE = 0.25
# ... and the remaining 65% of the time the commander gets away.

# Captured commanders.
SWITCH_SIDES_CHANCE = 0.5  # rolled once, on capture; otherwise he is held prisoner
RANSOM_BASE = 20  # gold; a captor always accepts
RANSOM_PER_LEVEL = 20
GOLD_RESERVE = 20  # gold a civ keeps back when ransoming or appointing a commander

# The roster: commanders leading armies plus those in reserve.
ROSTER_CAP = 20
STARTING_COMMANDERS = 3
PROMOTION_COST = 20  # gold to raise a new commander from the ranks
APPOINTMENT_COST = 120  # gold for a trained officer (needs Military Academy) ...
APPOINTMENT_LEVELS = 2  # ... who starts this many levels above a promoted one

# A reserve commander stationed at a capital strengthens its defence.
POST_DEFENCE = 0.10
POST_DEFENCE_PER_LEVEL = 0.02
XP_PER_BATTLE_TICK = 1.0
XP_FOUGHT = 5.0
XP_WON = 25.0
SWATH = 2  # undefended enemy tiles beside a captured one that fall with it
SWATH_MAX_PRICE = 1.5
MIN_ROUTE_SEARCH = 6000  # tiles a route search may look at, at least ...
ROUTE_SEARCH = 0.8  # ... or this share of the map's tiles, whichever is more
VALUE_PULL = 4.0  # tiles of march a unit of a region's value (strategy/geography.py) is worth
ACCESS_BY_SHIP = 0.8  # a native region across water is campaigned for once ships and a harbour can reach it
CAMPAIGN_ADVANTAGE = 2.0  # army strength, relative to a native garrison's defence, needed to attack it
CAMPAIGN_REST = 150  # ticks between campaigns
CAMPAIGN_RETRY = 200  # ... or after a failed one
UNSUPPLIED_ORE_UPKEEP = 1.5  # unit types at or above this ore upkeep are avoided when ore is short

COMMANDER_NAMES = (
    "Aldric", "Bashir", "Cassia", "Darius", "Edda", "Farid", "Greta", "Hakon", "Ilse", "Jovan",
    "Kira", "Leoric", "Mirza", "Nadia", "Osric", "Petra", "Quill", "Rurik", "Sabine", "Tariq",
    "Ulla", "Varen", "Wendel", "Xanthe", "Yusuf", "Zora",
)


class Military:
    def __init__(self, world: WorldMap, civs: list, modifiers: dict, diplomacy, rng: random.Random,
                 next_id: Callable[[], int]):
        self.world = world
        self.civs = {civ.id: civ for civ in civs}
        self.mods = modifiers
        self.diplomacy = diplomacy
        self.rng = rng
        self.next_id = next_id
        self._battles: dict[tuple[int, int], int] = {}  # (army id, army id) -> tick the battle began
        self._rally: dict[int, int] = {}  # army id -> tick until which it rests after a rout
        self.rallies: list[Rally] = []  # rallies gathering or on the march
        self._called: dict[int, int] = {}  # civ -> tick before which it calls no new rally
        self._no_way: dict[tuple[int, int], int] = {}  # (civ, region) -> tick until which no expedition is sent there
        self._lost: dict[tuple[int, int], dict[str, float]] = {}  # (army id, enemy id) -> soldiers lost in the battle
        self._stay: dict[int, int] = {}  # reinforcing army id -> tick until which it stays though the threat is gone
        self.probed: dict[tuple[int, int], int] = {}  # (civ, capital tile) -> last tick its armies attacked that castle
        self._named = 0
        self._names = random.Random(sum(civ.capital.tile for civ in civs))  # naming never disturbs the game's dice
        self.geography = None  # strategy.geography.Geography, set by the simulation
        self._tick = 0
        self._touching = region_neighbours(world)
        for civ in civs:
            civ.commanders.extend(self._new_commander(civ, 0) for _ in range(STARTING_COMMANDERS))

    # -- strength: the phase 3 formula, per army -----------------------------

    def army_strength(self, army: Army, enemy_units: dict[str, float] | None = None) -> float:
        """Soldiers x unit type (with counters) x quality x commander skill."""
        strength = unit_strength(army.units, enemy_units) * self.diplomacy.quality(self.civs[army.civ])
        strength *= tier_strength(army.tier)
        if army.commander:
            strength *= 1 + army.commander.strength_bonus
        if army.state == "pursuing" or self._tick < army.disordered_until:
            strength *= DISORDER  # strung out in a chase: vulnerable to a fresh enemy
        return strength

    # -- one tick ------------------------------------------------------------

    def update(self, tick: int, events: list) -> None:
        self._tick = tick
        living = [civ for civ in self.civs.values() if civ.alive]
        for civ in living:
            self._sync(civ)
        for civ in living:
            self._heal(civ, tick)
            self._upgrade(civ)
            self._organise(civ, tick)
            self._support(civ, tick, events)
            self._hold_castles(civ, tick, events)
            self._campaign(civ, tick)
            self._station(civ)
            self._hold_captives(civ, tick, events)
        self._rallies(tick, events)
        busy = self._fight(tick, events)
        self._relieve(tick, events)
        for civ in living:
            for army in list(civ.armies):
                if army.pursuing is not None and army.state != "pursuing":
                    self._end_pursuit(army, tick)  # drawn into a fight, or called home
                if army.role != "field" or army.id in busy or not civ.alive or army not in civ.armies:
                    continue
                if army.rally is not None and army.size < 0.5:
                    continue  # its soldiers are away with the rally: it waits for them
                if army.state == "pursuing":
                    self._pursue(civ, army, tick, events)
                    continue
                self._plan(civ, army, tick)
                if army in civ.armies:
                    self._march(civ, army)
                    if army.target_region is not None:
                        self._storm(civ, army, tick, events)
                    else:
                        self._besiege(civ, army, tick, events)

    # -- raising and organising ----------------------------------------------

    def _sync(self, civ) -> None:
        """Keep the armies' head count equal to civ.soldiers, which the economy recruits and pays."""
        garrison = civ.garrison
        if garrison is None:
            garrison = Army(self.next_id(), civ.id, civ.capital.tile, "garrison")
            civ.armies.insert(0, garrison)
        garrison.tile = civ.capital.tile
        total = sum(army.size for army in civ.armies)
        if civ.soldiers > total + 1e-9:
            garrison.add(self._mount(civ, self._recruits(civ, civ.soldiers - total)), self.best_tier(civ))
        elif total > civ.soldiers + 1e-9:
            factor = civ.soldiers / total
            riders = civ.unit_counts().get("cavalry", 0.0)
            for army in civ.armies:
                army.scale(factor)
            civ.horses += riders * (1 - factor)  # cavalry stood down bring their horses back

    def best_tier(self, civ) -> float:
        """How well the civ can arm a soldier: what its research allows."""
        return float(max(1, min(MAX_TIER, self.mods[civ.id].tier)))

    def _upgrade(self, civ) -> None:
        """Soldiers standing in one of the civ's capitals are given the best arms it can make,
        a few a day, as far as its gold and ore go. Armies in the field keep what they have."""
        best = self.best_tier(civ)
        cost = soldier_cost(self.mods[civ.id])
        gold, ore = UPGRADE_GOLD * cost, UPGRADE_ORE * cost
        left = UPGRADE_PER_TICK
        for army in civ.armies:
            if army.size < 0.5:
                army.tier = best if army.size <= 0 else army.tier
                continue
            behind = (best - army.tier) * army.size  # soldier-tiers still to make up
            if behind <= 1e-6 or not self._at_home(civ, army.tile) or army.state in ("fighting", "retreating"):
                continue
            affordable = min(max(0.0, civ.resources["gold"] - GOLD_RESERVE) / gold, civ.resources["ore"] / ore)
            done = min(behind, left, affordable)
            if done <= 0:
                continue
            civ.resources["gold"] -= done * gold
            civ.resources["ore"] -= done * ore
            army.tier = min(best, army.tier + done / army.size)
            left -= done

    # -- hospitals -----------------------------------------------------------

    def beds(self, civ) -> float:
        """Hospital beds: every castle has its hospital, and research adds beds to each."""
        return (INFIRMARY_BEDS + self.mods[civ.id].beds) * len(civ.settlements)

    def _admit(self, civ, units: dict[str, float], tier: float) -> float:
        """Wounded soldiers are put to bed, as many as there are beds free; the rest die.
        Returns how many died. The wounded stay among the civ's people but are no longer
        counted as soldiers until they are healed."""
        amount = sum(units.values())
        if amount <= 0:
            return 0.0
        share = min(1.0, max(0.0, self.beds(civ) - civ.wounded) / amount)
        if share > 0:
            civ.hospital.append([self._tick + HEAL_TICKS, {u: count * share for u, count in units.items()}, tier])
            civ.wounded += share * amount
        dead = (1 - share) * amount
        if dead > 1e-9:
            civ.beds_short = self._tick
            civ.hospital_deaths += dead
        return dead

    def _casualties(self, civ, fallen: dict[str, float], tier: float, share: float) -> None:
        """Of soldiers already struck off as lost, `share` were only wounded: they are among
        the civ's people again, in hospital if there is a bed for them."""
        wounded = {unit: count * share for unit, count in fallen.items()}
        amount = sum(wounded.values())
        if amount <= 0:
            return
        civ.population += amount - self._admit(civ, wounded, tier)

    def _heal(self, civ, tick: int) -> None:
        """Soldiers whose stay in hospital is over join the garrison. They do not go back to
        the army they fell with: it has them again only when it next fills its ranks in a capital."""
        for batch in [b for b in civ.hospital if b[0] <= tick]:
            civ.hospital.remove(batch)
            healed = sum(batch[1].values())
            civ.soldiers += healed
            if civ.garrison is not None:
                civ.garrison.add(self._mount(civ, batch[1]), batch[2])
        civ.wounded = sum(sum(batch[1].values()) for batch in civ.hospital)

    def _mount(self, civ, recruits: dict[str, float]) -> dict[str, float]:
        """Cavalry recruits each need a horse from the stables; those without one serve on foot."""
        wanted = recruits.get("cavalry", 0.0)
        mounted = min(wanted, max(0.0, civ.horses))
        if wanted - mounted <= 1e-9:
            civ.horses -= mounted
            return recruits
        civ.horses -= mounted
        on_foot = {unit: count for unit, count in recruits.items() if unit != "cavalry"}
        spare = wanted - mounted
        total = sum(on_foot.values())
        if total > 0:
            on_foot = {unit: count + spare * count / total for unit, count in on_foot.items()}
        else:
            on_foot = {BASE_UNIT: spare}
        if mounted > 0:
            on_foot["cavalry"] = mounted
        return on_foot

    def _recruits(self, civ, amount: float) -> dict[str, float]:
        """New soldiers by type: whatever moves the army toward the mix the civ wants."""
        weights = self._desired_mix(civ)
        counts = civ.unit_counts()
        new_total = sum(counts.values()) + amount
        short = {u: max(0.0, w * new_total - counts.get(u, 0.0)) for u, w in weights.items()}
        total_short = sum(short.values())
        if total_short <= 0:
            return {u: amount * w for u, w in weights.items()}
        return {u: amount * s / total_short for u, s in short.items() if s > 0}

    def _desired_mix(self, civ) -> dict[str, float]:
        known = set(civ.known_techs)
        weights = {u.id: u.share for u in UNIT_TYPES.values() if known.issuperset(u.requires)} or {BASE_UNIT: 1.0}
        if civ.unsupplied:  # short of ore: lean on troops that need little of it
            for unit_id in weights:
                if UNIT_TYPES[unit_id].upkeep["ore"] >= UNSUPPLIED_ORE_UPKEEP:
                    weights[unit_id] *= 0.2
        for enemy_id in self.diplomacy.enemies(civ.id):  # and on whatever counters the enemy's main arm
            main = max(self.civs[enemy_id].unit_counts().items(), key=lambda item: item[1], default=(None, 0))[0]
            for unit_id in weights:
                if main in UNIT_TYPES[unit_id].counters:
                    weights[unit_id] *= 1.5
        total = sum(weights.values())
        return {unit_id: weight / total for unit_id, weight in weights.items()}

    def capacity(self, army: Army) -> float:
        """Soldiers an army can hold: what its commander can lead. A rally marches as one,
        whatever its size."""
        rally = self.rally_of(army)
        if rally is not None and rally.army == army.id:
            return float("inf")
        base = army.commander.capacity if army.commander else LEADERLESS_CAPACITY
        return base * (EXPEDITION_CAPACITY if army.target_region is not None else 1.0)

    def _organise(self, civ, tick: int) -> None:
        """Field armies against each enemy, each as large as its commander can lead and no more
        than MAX_ARMIES in all; the rest of the soldiers hold the capitals, and fill the ranks
        of armies that come home. Nobody is sent out to an army in the field."""
        enemies = self.diplomacy.enemies(civ.id)
        garrison = civ.garrison
        # More stays at home while someone it is not yet fighting is set on attacking it.
        watched = any(self.diplomacy.intent(other, civ.id).stance.value == "aggression"
                      for other in self.diplomacy.others(civ.id)
                      if self.civs[other].alive and other not in enemies)
        keep = (GUARDED_KEEP if watched else GARRISON_KEEP) * civ.soldiers

        def out() -> int:
            return sum(1 for a in civ.armies if a.role == "field" and a.state != "returning")

        def raise_army(enemy: int, **kind) -> Army | None:
            if out() >= MAX_ARMIES:
                return None
            army = Army(self.next_id(), civ.id, civ.capital.tile, "field", target_civ=enemy,
                        commander=self._appoint(civ), **kind)
            civ.armies.append(army)
            return army

        for enemy in enemies:
            foe = self.civs[enemy]
            mine = [a for a in civ.armies if a.role == "field" and a.target_civ == enemy
                    and a.state != "returning" and a.target_region is None]
            attack = [a for a in mine if a.duty == "attack"]
            war = self.diplomacy.relation(civ.id, enemy).war
            if not attack:
                raise_army(enemy)
            elif (war and civ.id in war.aggressors and garrison.size - keep >= 2 * MIN_FIELD_ARMY
                  and (civ.commanders or civ.resources["gold"] >= PROMOTION_COST + GOLD_RESERVE)
                  and all(a.size >= FULL * self.capacity(a) for a in attack)):
                # Every army against this enemy is as large as its commander can lead, and there
                # are soldiers to spare: another column sets out, for another of its capitals.
                raise_army(enemy, wing=len(attack))
            # Home defence: an enemy on our land with every army far away gets a force of its own.
            intruder = self._besieger(civ, foe) or self._nearest_intruder(civ, garrison, foe)
            guard = next((a for a in mine if a.duty == "defend"), None)
            if intruder is not None and guard is None and all(
                    self._reach(a.tile, intruder.tile) > HOME_CALL for a in attack):
                raise_army(enemy, duty="defend")
            elif intruder is None and guard is not None and guard.state not in ("fighting", "retreating"):
                guard.state, guard.path = "returning", []  # the land is clear: stand down
        for army in civ.armies:
            if army.role != "field":
                continue
            if (army.target_region is None and army.target_civ not in enemies and army.state != "returning"
                    and army.rally is None and army.duty not in ("reinforce", "hold")):
                army.state, army.path, army.siege_progress = "returning", [], 0.0  # the war is over: go home
            if army.commander is None and self._at_home(civ, army.tile) and tick >= army.leaderless_until:
                army.commander = self._appoint(civ)
        if self.roster(civ) < STARTING_COMMANDERS and civ.resources["gold"] >= PROMOTION_COST + GOLD_RESERVE:
            recruit = self._raise_commander(civ)  # keep a few in hand when the treasury allows
            if recruit:
                civ.commanders.append(recruit)

        active = sorted((a for a in civ.armies if a.role == "field" and a.state != "returning"
                         and a.target_region is None and a.rally is None and a.duty != "hold"),
                        key=lambda a: (a.duty != "defend", a.wing, a.id))  # the home force first
        for army in active:
            room = self.capacity(army) - army.size
            home = self._at_home(civ, army.tile)
            if room < 0 and home:
                garrison.add(army.take(-room), army.tier)  # more than its commander can lead: the rest stay behind
                continue
            spare = garrison.size - keep
            if room <= 0 or spare <= 0 or not home or army.state == "retreating":
                continue  # ranks are filled in the civ's own capitals, and nowhere else
            army.add(garrison.take(min(room, spare)), garrison.tier)
            army.refit = False

    def roster(self, civ) -> int:
        """Commanders the civ has: those leading armies and those in reserve."""
        return len(civ.commanders) + sum(1 for army in civ.armies if army.commander)

    def _appoint(self, civ) -> Commander | None:
        """The most experienced commander without an army, or a new one if the civ can pay for him."""
        if civ.commanders:
            best = max(civ.commanders, key=lambda c: (c.experience, c.name))
            civ.commanders.remove(best)
            best.post = None
            return best
        return self._raise_commander(civ)

    def _raise_commander(self, civ) -> Commander | None:
        """A new commander, for gold: a trained officer if the civ can appoint one, else promoted
        from the ranks. None when the roster is full or the treasury cannot pay."""
        if self.roster(civ) >= ROSTER_CAP:
            return None
        mods = self.mods[civ.id]
        gold = civ.resources["gold"]
        if mods.officer_appointment > 0 and gold >= APPOINTMENT_COST + GOLD_RESERVE:
            civ.resources["gold"] -= APPOINTMENT_COST
            return self._new_commander(civ, mods.commander_start + APPOINTMENT_LEVELS)
        if gold >= PROMOTION_COST:
            civ.resources["gold"] -= PROMOTION_COST
            return self._new_commander(civ, mods.commander_start)  # officer training raises where he starts
        return None

    def _new_commander(self, civ, levels: int) -> Commander:
        self._named += 1
        name = COMMANDER_NAMES[self._names.randrange(len(COMMANDER_NAMES))]
        commander = Commander(f"{name} of {civ.name}" if self._named <= len(COMMANDER_NAMES) else f"{name} {self._named}")
        commander.experience = XP_PER_LEVEL_STEP * levels ** 2
        return commander

    # -- capitals --------------------------------------------------------------

    def _at_home(self, civ, tile: int) -> bool:
        return any(s.tile == tile for s in civ.settlements)

    def _refuge(self, civ, tile: int) -> int:
        """The nearest capital the civ holds: where a beaten army falls back to."""
        return min((s.tile for s in civ.settlements), key=lambda t: (self._gap(tile, t), t))

    def _station(self, civ) -> None:
        """Commanders without an army hold the civ's capitals, the most experienced nearest the enemy."""
        threats = [region.capital for region in self.world.regions
                   if region.owner in self.diplomacy.enemies(civ.id)]
        if not threats:
            threats = [region.capital for region in self.world.regions
                       if region.owner is not None and region.owner != civ.id]
        capitals = [s.tile for s in civ.settlements]
        if threats:
            capitals.sort(key=lambda t: (min(self._gap(t, threat) for threat in threats), t))
        reserve = sorted(civ.commanders, key=lambda c: (-c.experience, c.name))
        for place, commander in enumerate(reserve):
            commander.post = capitals[place] if place < len(capitals) else None

    def post_defence(self, civ, tile: int) -> float:
        """Extra defence a capital has from the commander stationed there."""
        for commander in civ.commanders:
            if commander.post == tile:
                return POST_DEFENCE + POST_DEFENCE_PER_LEVEL * commander.level
        return 0.0

    def capital_fell(self, captor, loser, tile: int, tick: int, events: list) -> None:
        """The commander holding a capital that falls is killed, captured or gets away."""
        for commander in [c for c in loser.commanders if c.post == tile]:
            commander.post = None
            fate = self._commander_fate(commander, loser, captor, tick)
            if fate:
                loser.commanders.remove(commander)
                events.append({"civ": captor.id, "kind": "war", "text": f"{commander.name}, who held the city, {fate}"})

    def _commander_fate(self, commander: Commander, losing, winning, tick: int) -> str:
        """Roll a beaten commander's fate. Returns what befell him, or "" if he escaped; a captured
        commander is handed to the victor here, and the caller removes him from where he was."""
        roll = self.rng.random()
        if roll < COMMANDER_DEATH_CHANCE:
            return "is killed"
        if roll >= COMMANDER_DEATH_CHANCE + CAPTURE_CHANCE:
            return ""
        commander.post = None
        if self.rng.random() < SWITCH_SIDES_CHANCE and self.roster(winning) < ROSTER_CAP:
            winning.commanders.append(commander)
            return "is captured and changes sides"
        winning.captives.append(Captive(commander, losing.id, tick))
        return "is taken prisoner"

    def _gain(self, army: Army, experience: float) -> None:
        if army.commander:
            army.commander.experience += experience * (1 + self.mods[army.civ].commander_xp)

    def _disband(self, civ, army: Army) -> None:
        civ.garrison.add(army.units, army.tier)
        if army.commander:
            civ.commanders.append(army.commander)
        civ.armies.remove(army)
        self._rally.pop(army.id, None)
        self._stay.pop(army.id, None)

    # -- orders --------------------------------------------------------------

    def _plan(self, civ, army: Army, tick: int) -> None:
        capital = civ.capital.tile
        others: list[int] = []  # for an attacker: every capital the enemy holds, nearest first
        if army.state == "returning" or (army.state == "retreating" and army.target_region is not None):
            if army.tile == capital:
                self._disband(civ, army)
                return
            goal = capital
        elif army.state == "retreating":
            # A beaten army falls back on the nearest capital its civ holds and rests there.
            goal = self._refuge(civ, army.tile)
            if army.tile == goal:
                army.state, army.path = "idle", []
                self._rally[army.id] = tick + RALLY_TICKS
        elif self.rally_of(army) is not None:
            rally = self.rally_of(army)
            if rally.state == "gathering":
                # Make for the city the rally gathers in, and wait there.
                goal = rally.city
                army.state = "marching" if army.tile != goal else "idle"
            else:
                goal = rally.target  # the rally has one purpose, and is not turned from it
                army.state = "marching"
        elif army.target_region is not None:
            goal = self.world.regions[army.target_region].capital
            if army.state == "idle":
                army.state = "marching"
        elif army.duty in ("reinforce", "hold"):
            # Stand in the ally's capital; a beaten one rests at home first.
            fit = tick >= self._rally.get(army.id, 0) and army.size >= MIN_FIELD_ARMY
            goal = army.post if fit else self._refuge(civ, army.tile)
            army.state = "marching" if army.tile != goal else "idle"
        else:
            enemy = self.civs[army.target_civ]
            war = self.diplomacy.relation(civ.id, enemy.id).war
            rested = tick >= self._rally.get(army.id, 0)
            besieger = self._besieger(civ, enemy) if war else None
            guarded = army.duty == "attack" and any(
                a.duty == "defend" and a.target_civ == enemy.id and a.size >= MIN_FIELD_ARMY
                and a.state not in ("retreating", "returning") for a in civ.armies)
            if army.duty == "defend":
                # The home force never leaves its own land: it goes for whoever is on it.
                intruder = besieger or self._nearest_intruder(civ, army, enemy)
                goal = intruder.tile if intruder else capital
                army.state = "marching" if intruder and rested and army.size >= MIN_FIELD_ARMY else "idle"
            elif besieger is not None and rested and army.size >= MIN_FIELD_ARMY and not guarded:
                # One of our capitals is held: nothing matters more than driving them out.
                goal = besieger.tile
                army.state = "marching"
            elif war and civ.id in war.aggressors and rested and (army.refit or self._worn_down(civ, army)):
                # Too few left to go on, and more waiting at home: back to fill the ranks.
                army.refit = True
                goal = self._refuge(civ, army.tile)
                army.siege_progress = 0.0
                army.state = "marching" if army.tile != goal else "idle"
            elif war and civ.id in war.aggressors and rested and army.size >= MIN_FIELD_ARMY:
                # Make for the nearest capital the enemy holds: taking it takes its region.
                # Make for the capital that is cheapest to take: near, and not too strongly held.
                joint = self._allied_targets(civ, enemy)  # where an ally is already attacking: join it there
                worth = self.geography.values(civ, tick) if self.geography is not None else {}
                others = sorted((s.tile for s in enemy.settlements),
                                key=lambda t: (self._gap(army.tile, t) + WALL_DETOUR * self.tile_price(civ, t)
                                               - (JOINT_PULL if t in joint else 0)
                                               - VALUE_PULL * self._worth(worth, t), t))
                # Each column takes the next capital along, so the enemy has several to save.
                goal = others[army.wing % len(others)]
                others = [goal] + [t for t in others if t != goal]
                if army.state == "idle":
                    army.state = "marching"
                if self._outmatched(civ, army):
                    # No sense in being cut to pieces: fall back, rest, and come again stronger.
                    army.state, army.path, army.siege_progress = "retreating", [], 0.0
                    goal = self._refuge(civ, army.tile)
            else:
                intruder = self._nearest_intruder(civ, army, enemy)
                goal = intruder.tile if intruder else capital
                # A beaten army rests until it has rallied, whoever is at the gates.
                army.state = "marching" if intruder and rested and army.size >= MIN_FIELD_ARMY else "idle"
                if army.state == "idle":
                    goal = capital

        if army.tile == goal:
            army.path = []
            return
        stale = tick - army.path_tick >= REPLAN_TICKS
        if not stale and army.no_route == goal:
            return  # no way there when last looked: do not search again every tick
        if stale or not army.path or army.path[-1] not in (goal, *others):
            # The nearest enemy capital may lie across water the army cannot take ship for:
            # then it makes for the nearest one it can get to, and failing that goes home.
            path = None
            for target in (goal, *others[1:]):
                path = self._route(civ, army.tile, target)
                if path is not None:
                    break
            army.no_route = goal if path is None else None
            if path is None and army.target_region is not None and army.state == "marching":
                # An expedition whose way has closed (a harbour lost, say) comes home.
                self._no_way[(civ.id, army.target_region)] = tick + CAMPAIGN_RETRY
                army.state, goal = "returning", capital
            if path is None and capital not in (goal, army.tile):
                path = self._route(civ, army.tile, capital)
            army.path = path or []
            army.path_tick = tick

    # -- rallies ------------------------------------------------------------------

    def rally_of(self, army: Army) -> Rally | None:
        if army.rally is None:
            return None
        return next((r for r in self.rallies if r.id == army.rally), None)

    def rally_led_by(self, civ_id: int) -> Rally | None:
        return next((r for r in self.rallies if r.leader == civ_id), None)

    def _war_allies(self, civ, enemy_id: int) -> list:
        """The civ's allies who are at war with the same enemy."""
        return [self.civs[a] for a in self.diplomacy.allies(civ.id)
                if self.civs[a].alive and self.diplomacy.relation(a, enemy_id).status == "war"]

    def _free_to_rally(self, army: Army, enemy_id: int) -> bool:
        return (army.role == "field" and army.duty == "attack" and army.target_civ == enemy_id
                and army.rally is None and army.target_region is None and army.size >= MIN_FIELD_ARMY
                and army.state in ("idle", "marching", "besieging") and not self._holding(army))

    def _rally_ground(self, civ, enemy, mine: list) -> tuple[int, int]:
        """Where a rally against `enemy` would gather, and the capital it would march on: the
        enemy capital cheapest to take, and the civ's own city nearest it that one of its armies
        can reach in time."""
        start = civ.capital.tile
        target = min((s.tile for s in enemy.settlements),
                     key=lambda t: (self._gap(start, t) + WALL_DETOUR * self.tile_price(civ, t), t))
        cities = [s.tile for s in civ.settlements]
        within = [t for t in cities if any(self._gap(a.tile, t) <= RALLY_REACH for a in mine)]
        largest = max(mine, key=lambda a: (a.size, -a.id))
        city = (min(within, key=lambda t: (self._gap(t, target), t)) if within
                else min(cities, key=lambda t: (self._gap(t, largest.tile), t)))
        return city, target

    def start_rally(self, civ, enemy_id: int, tick: int, events: list) -> Rally | str:
        """Call a rally against an enemy: the civ's own armies make for the city nearest the
        enemy capital that is cheapest to take, and its allies have RALLY_GATHER days to join
        them there. Returns the rally, or what is wrong."""
        enemy = self.civs.get(enemy_id)
        war = self.diplomacy.relation(civ.id, enemy_id).war if enemy is not None and enemy.alive else None
        if war is None:
            return "you are not at war with that civ"
        if self.rally_led_by(civ.id) is not None:
            return "you are already leading a rally"
        if not self._war_allies(civ, enemy_id):
            return "no ally is at war with that civ"
        mine = [a for a in civ.armies if self._free_to_rally(a, enemy_id)]
        if not mine:
            return "no army is free to lead it"
        city, target = self._rally_ground(civ, enemy, mine)
        rally = Rally(self.next_id(), civ.id, enemy_id, city, target, tick, tick + RALLY_GATHER)
        self.rallies.append(rally)
        for army in mine:
            if self._gap(army.tile, city) <= RALLY_REACH:
                army.rally, army.path, army.path_tick = rally.id, [], -10_000
        self.diplomacy._log(tick, events, "war", [civ, enemy],
                            f"{civ.name} calls a rally at {self._city_name(city)} against "
                            f"{self._city_name(target)}: its allies have {RALLY_GATHER} days to join")
        return rally

    def join_rally(self, civ, rally: Rally, tick: int, events: list) -> str | None:
        """Send the civ's main army against that enemy to the rally. Returns what is wrong, if anything."""
        if rally not in self.rallies or rally.state != "gathering":
            return "that rally is no longer gathering"
        if self.diplomacy.relation(civ.id, rally.leader).status != "alliance":
            return "only allies may join a rally"
        if self.diplomacy.relation(civ.id, rally.enemy).status != "war":
            return "you are not at war with that civ"
        free = [a for a in civ.armies if self._free_to_rally(a, rally.enemy)]
        if not free:
            return "no army is free to join"
        army = max(free, key=lambda a: (a.size, -a.id))
        army.rally, army.path, army.path_tick = rally.id, [], -10_000
        self.diplomacy._log(tick, events, "war", [civ, self.civs[rally.leader]],
                            f"{civ.name}'s army sets out to join {self.civs[rally.leader].name}'s rally "
                            f"at {self._city_name(rally.city)}")
        return None

    def cancel_rally(self, rally: Rally, tick: int, events: list, why: str = "") -> None:
        """Call a rally off: every army goes back to what it was doing. One already on the
        march breaks up where it stands, and each ally's soldiers go home."""
        if rally not in self.rallies:
            return
        if rally.state == "marching":
            self._disband_rally(rally, tick, events, taken=False)
            return
        self._release(rally)
        leader = self.civs[rally.leader]
        self.diplomacy._log(tick, events, "war", [leader],
                            f"{leader.name} calls off its rally at {self._city_name(rally.city)}{why}")

    def _release(self, rally: Rally) -> None:
        self.rallies.remove(rally)
        self._called[rally.leader] = self._tick + RALLY_REST
        for civ in self.civs.values():
            for army in civ.armies:
                if army.rally == rally.id:
                    army.rally, army.path, army.path_tick = None, [], -10_000
                    if army.state == "idle" and army.size >= MIN_FIELD_ARMY:
                        army.state = "marching"

    def _city_name(self, tile: int) -> str:
        region_id = self.world.capital_tiles.get(tile)
        return self.world.regions[region_id].capital_name if region_id is not None else "the frontier"

    def _rallies(self, tick: int, events: list) -> None:
        """Call, join, launch and end rallies. A human ruler's civ does none of this by itself."""
        player = self.diplomacy.player
        for rally in list(self.rallies):
            leader, enemy = self.civs[rally.leader], self.civs[rally.enemy]
            region = self.world.regions[self.world.capital_tiles[rally.target]]
            on = (leader.alive and enemy.alive and region.owner == enemy.id
                  and self.diplomacy.relation(leader.id, enemy.id).war is not None)
            if rally.state == "gathering":
                if not on:
                    self.cancel_rally(rally, tick, events, ": there is nothing left to march on")
                elif tick >= rally.departs:
                    self._launch(rally, tick, events)
                else:
                    for ally in self._war_allies(leader, enemy.id):
                        if ally.id != player and not any(a.rally == rally.id for a in ally.armies):
                            near = any(self._free_to_rally(a, enemy.id) and self._gap(a.tile, rally.city) <= RALLY_REACH
                                       for a in ally.armies)
                            if near:
                                self.join_rally(ally, rally, tick, events)
            else:
                army = self._find_army(rally.army)
                if (not on or army is None or army.size < 1.0 or army.rally != rally.id
                        or army.state in ("retreating", "returning")):
                    self._disband_rally(rally, tick, events, taken=region.owner == leader.id)
        for civ in self.civs.values():
            if (not civ.alive or civ.id == player or tick < self._called.get(civ.id, 0)
                    or self.rally_led_by(civ.id) is not None or any(a.rally is not None for a in civ.armies)):
                continue
            for enemy_id in self.diplomacy.enemies(civ.id):
                war = self.diplomacy.relation(civ.id, enemy_id).war
                # Worth calling when an ally shares the war, the army has not yet committed
                # itself, and an ally's army could reach the city it would gather in.
                if not (war and civ.id in war.aggressors and self.civs[enemy_id].settlements):
                    continue
                home = [a for a in civ.armies if self._free_to_rally(a, enemy_id) and a.state in ("idle", "marching")]
                if not home:
                    continue
                city, _ = self._rally_ground(civ, self.civs[enemy_id], home)
                if any(self._free_to_rally(a, enemy_id) and self._gap(a.tile, city) <= RALLY_REACH
                       for ally in self._war_allies(civ, enemy_id) for a in ally.armies):
                    if isinstance(self.start_rally(civ, enemy_id, tick, events), Rally):
                        break

    def _launch(self, rally: Rally, tick: int, events: list) -> None:
        """The gathering is over: whoever has reached the city marches as one army under the
        leader's best general. A rally nobody else came to is called off."""
        leader = self.civs[rally.leader]
        present = [a for civ in self.civs.values() for a in civ.armies
                   if a.rally == rally.id and a.size >= MIN_FIELD_ARMY and self._reach(a.tile, rally.city) <= 1]
        own = [a for a in present if a.civ == leader.id]
        guests = [a for a in present if a.civ != leader.id]
        if not own or not guests:
            self.cancel_rally(rally, tick, events, ": too few came")
            return
        head = max(own, key=lambda a: (a.commander.level if a.commander else 0, a.size, -a.id))
        for army in own:
            if army is not head:
                head.add(army.take(army.size), army.tier)
                army.rally = None
        lent: dict[int, float] = {}
        for army in guests:
            owner = self.civs[army.civ]
            count = army.size
            head.add(army.take(count), army.tier)
            # The soldiers march under the leader's banner, and are his to pay, until the rally is over.
            owner.soldiers -= count
            owner.population = max(MIN_POPULATION, owner.population - count)
            leader.soldiers += count
            leader.population += count
            lent[owner.id] = lent.get(owner.id, 0.0) + count
            army.state, army.path = "idle", []
        rally.shares = {civ_id: count / head.size for civ_id, count in lent.items()}
        rally.state, rally.army = "marching", head.id
        head.tile, head.state, head.path, head.path_tick = rally.city, "marching", [], -10_000
        for civ in self.civs.values():  # whoever did not get there in time is left behind
            for army in civ.armies:
                if army.rally == rally.id and army is not head and army not in guests:
                    army.rally = None
        names = " and ".join([leader.name, *sorted(self.civs[c].name for c in lent)])
        led = f" under {head.commander.name}" if head.commander else ""
        self.diplomacy._log(tick, events, "war", [leader, self.civs[rally.enemy]],
                            f"The rally marches on {self._city_name(rally.target)}: {round(head.size)} soldiers "
                            f"of {names}{led}")

    def _disband_rally(self, rally: Rally, tick: int, events: list, taken: bool) -> None:
        """The rally is over, won or lost: what is left of it is divided as it was made up, and
        each ally's soldiers go home under their own commander. Those who helped take a city
        are paid from the leader's treasury and thought the better of."""
        leader = self.civs[rally.leader]
        head = self._find_army(rally.army)
        size = head.size if head is not None else 0.0
        for civ_id, share in rally.shares.items():
            owner = self.civs[civ_id]
            theirs = next((a for a in owner.armies if a.rally == rally.id), None)
            back = head.take(share * size) if head is not None and owner.alive else {}
            count = sum(back.values())
            leader.soldiers = max(0.0, leader.soldiers - count)
            leader.population = max(MIN_POPULATION, leader.population - count)
            if owner.alive:
                owner.soldiers += count
                owner.population += count
                home = theirs if theirs is not None else owner.garrison
                if home is not None and back:  # nothing comes back from a rally whose army is gone
                    home.add(back, head.tier)
                if theirs is not None and head is not None:
                    theirs.tile, theirs.state, theirs.path = head.tile, "returning", []
                if taken:
                    purse = RALLY_SPOILS * share * leader.resources["gold"]
                    leader.resources["gold"] -= purse
                    owner.resources["gold"] = min(self.mods[civ_id].storage["gold"], owner.resources["gold"] + purse)
                    self.diplomacy.remember(leader.id, civ_id, 1.0)
                    self.diplomacy.remember(civ_id, leader.id, 0.5)
        self._release(rally)
        outcome = (f"takes {self._city_name(rally.target)} and breaks up, its allies paid from the spoils" if taken
                   else "breaks up")
        self.diplomacy._log(tick, events, "war", [leader], f"{leader.name}'s rally {outcome}")

    def _allied_targets(self, civ, enemy) -> set[int]:
        """The enemy capitals that allies of `civ`, also at war with it, are marching on or besieging."""
        capitals = {s.tile for s in enemy.settlements}
        found: set[int] = set()
        for ally in self.diplomacy.allies(civ.id):
            if self.diplomacy.relation(ally, enemy.id).status != "war":
                continue
            for other in self.civs[ally].armies:
                if other.role == "field" and other.target_civ == enemy.id and other.path and other.path[-1] in capitals:
                    found.add(other.path[-1])
        return found

    # -- standing with an ally -------------------------------------------------

    def _threatened(self, ally, tile: int) -> bool:
        """Whether an enemy holds this capital of `ally`, or has an army close to it."""
        region = self.world.regions[self.world.capital_tiles[tile]]
        if region.owner != ally.id:
            return False
        if region.held_by is not None:
            return True
        for enemy_id in self.diplomacy.enemies(ally.id):
            for other in self.civs[enemy_id].armies:
                if (other.role == "field" and other.size >= MIN_FIELD_ARMY
                        and other.state not in ("retreating", "returning")
                        and self._reach(other.tile, tile) <= REINFORCE_ALERT):
                    return True
        return False

    def _guests(self, tile: int) -> list[Army]:
        """Allied armies standing in the capital on this tile to help hold it."""
        return [army for civ in self.civs.values() if civ.alive for army in civ.armies
                if army.duty in ("reinforce", "hold") and army.post == tile and army.size >= 0.5
                and army.state not in ("retreating", "returning") and self._reach(army.tile, tile) <= 1]

    def reinforcing(self, civ) -> Army | None:
        """The army the civ has sent to stand with an ally, if any."""
        return next((a for a in civ.armies if a.duty == "reinforce" and a.state != "returning"), None)

    def _support(self, civ, tick: int, events: list) -> None:
        """Send an army to stand in an ally's capital that an enemy is at or near, and bring it
        home once the danger has passed. A human ruler's civ sends one only when he orders it,
        and it stays until he calls it back."""
        ruled = civ.id == self.diplomacy.player
        out = self.reinforcing(civ)
        if out is not None:
            ally = self.civs.get(self.world.owner[out.post])
            allied = (ally is not None and ally.alive and ally.id != civ.id
                      and self.diplomacy.relation(civ.id, ally.id).status == "alliance")
            if allied and self._threatened(ally, out.post):
                self._stay[out.id] = tick + REINFORCE_STAY
            wanted = allied and (civ.reinforce_order == ally.id if ruled else tick < self._stay.get(out.id, 0))
            if not wanted:
                out.state, out.path = "returning", []
                if ruled:
                    civ.reinforce_order = None
            return
        if ruled and civ.reinforce_order is None:
            return
        garrison = civ.garrison
        spare = garrison.size - GARRISON_KEEP * civ.soldiers
        if (spare < 2 * MIN_FIELD_ARMY
                or sum(1 for a in civ.armies if a.role == "field" and a.state != "returning") >= MAX_ARMIES):
            return
        if not ruled and any(r.owner == civ.id and r.held_by is not None for r in self.world.regions):
            return  # its own capitals come first
        allies = [civ.reinforce_order] if ruled else self.diplomacy.allies(civ.id)
        for ally_id in allies:
            ally = self.civs.get(ally_id)
            if ally is None or not ally.alive or self.diplomacy.relation(civ.id, ally_id).status != "alliance":
                if ruled:
                    civ.reinforce_order = None
                continue
            capitals = sorted((s.tile for s in ally.settlements),
                              key=lambda t: (not self._threatened(ally, t), self._gap(civ.capital.tile, t), t))
            for tile in capitals:
                if not ruled and (not self._threatened(ally, tile)
                                  or self._gap(civ.capital.tile, tile) > REINFORCE_REACH):
                    continue
                if tick < self._no_way.get((civ.id, -tile - 1), 0):
                    continue
                if self._route(civ, civ.capital.tile, tile) is None:
                    self._no_way[(civ.id, -tile - 1)] = tick + REINFORCE_RETRY
                    continue
                army = Army(self.next_id(), civ.id, civ.capital.tile, "field", commander=self._appoint(civ),
                            state="marching", duty="reinforce", post=tile)
                army.add(garrison.take(min(spare, self.capacity(army))), garrison.tier)
                civ.armies.append(army)
                self._stay[army.id] = tick + REINFORCE_STAY
                self.diplomacy.remember(ally.id, civ.id, 0.5)  # help that came is not forgotten
                self.diplomacy._log(tick, events, "war", [civ, ally],
                                    f"{civ.name} sends an army to stand with {ally.name} in {self._city_name(tile)}")
                return

    # -- castles' garrisons ------------------------------------------------------

    def castle_garrison(self, civ) -> float:
        """Soldiers holding each of the civ's castles: its garrison is spread through them all."""
        return civ.garrison.size / max(1, len(civ.settlements)) if civ.garrison is not None else 0.0

    def garrison_known(self, viewer, tile: int) -> bool:
        """Whether `viewer` knows exactly how many hold the castle on `tile`: its own or an
        ally's, or one its armies have attacked in the last PROBE_MEMORY days."""
        owner = self.world.owner[tile]
        if owner == viewer.id or (owner >= 0 and self.diplomacy.relation(viewer.id, owner).status == "alliance"):
            return True
        return self._tick - self.probed.get((viewer.id, tile), -10_000) <= PROBE_MEMORY

    def garrison_guess(self, viewer, tile: int, actual: float) -> int:
        """A rough count of a castle's garrison as `viewer` sees it, in shown heads: within
        GARRISON_GUESS of the truth, rounded to tens, and the same from one day to the next."""
        dice = random.Random(f"{self.world.seed}:{viewer.id}:{tile}:{self._tick // GUESS_FRESH}")
        off = dice.uniform(-(GARRISON_GUESS - 5), GARRISON_GUESS - 5)
        return max(0, int(round((actual + off) / 10.0)) * 10)

    # -- holding castles ---------------------------------------------------------

    def _threat(self, civ, tile: int) -> float:
        """Strength of the enemy armies at or near one of the civ's capitals."""
        return sum(self.army_strength(other) for enemy_id in self.diplomacy.enemies(civ.id)
                   for other in self.civs[enemy_id].armies
                   if other.role == "field" and other.size >= 0.5 and other.state not in ("retreating", "returning")
                   and self._reach(other.tile, tile) <= REINFORCE_ALERT)

    def _held_by(self, civ, tile: int) -> float:
        """Strength holding one of the civ's castles: its share of the garrison and any armies
        standing in it to hold it."""
        share = unit_strength(civ.garrison.units) * tier_strength(civ.garrison.tier) * self.diplomacy.quality(civ)
        return share / max(1, len(civ.settlements)) + sum(self.army_strength(a) for a in self._guests(tile))

    def _hold_castles(self, civ, tick: int, events: list) -> None:
        """A general near a threatened castle of his own that is too weakly held for the threat
        leaves part of his army there to hold it; once the danger has passed for a while, those
        soldiers join the garrison."""
        for army in [a for a in civ.armies if a.duty == "hold"]:
            if army.post not in {s.tile for s in civ.settlements}:
                army.duty, army.post, army.state, army.path = "attack", None, "returning", []  # the castle fell
                continue
            if self._threatened(civ, army.post):
                self._stay[army.id] = tick + HOLD_STAY
            elif tick >= self._stay.get(army.id, 0) and self._reach(army.tile, army.post) <= 1:
                self._disband(civ, army)  # the danger is past: into the garrison
        if sum(1 for a in civ.armies if a.role == "field" and a.state != "returning") >= MAX_ARMIES:
            return
        # The castles worth most first (strategy/geography.py): a prize is held before a backwater.
        worth = self.geography.values(civ, tick) if self.geography is not None else {}
        for settlement in sorted(civ.settlements, key=lambda s: (-self._worth(worth, s.tile), s.tile)):
            tile = settlement.tile
            if not self._threatened(civ, tile):
                continue
            threat, held = self._threat(civ, tile), self._held_by(civ, tile)
            if threat <= held:
                continue
            near = [a for a in civ.armies if a.role == "field" and a.commander is not None
                    and a.duty in ("attack", "defend") and a.rally is None and not a.refit
                    and a.target_region is None and a.state not in ("fighting", "retreating", "returning", "pursuing")
                    and a.size >= 2 * MIN_FIELD_ARMY and self._reach(a.tile, tile) <= DETACH_REACH
                    and not self._holding(a)]
            if not near:
                continue
            army = min(near, key=lambda a: (self._reach(a.tile, tile), a.id))
            per_soldier = self.army_strength(army) / max(army.size, 1e-9)
            wanted = (threat - held) / max(per_soldier, 1e-9)
            count = min(DETACH_MAX * army.size, max(MIN_FIELD_ARMY, wanted))
            if army.size - count < MIN_FIELD_ARMY:
                continue
            force = Army(self.next_id(), civ.id, army.tile, "field", target_civ=army.target_civ,
                         state="marching", duty="hold", post=tile)
            force.add(army.take(count), army.tier)
            civ.armies.append(force)
            self._stay[force.id] = tick + HOLD_STAY
            self.diplomacy._log(tick, events, "war", [civ],
                                f"{army.commander.name} of {civ.name} leaves {round(count * HEADCOUNT)} "
                                f"soldiers to hold {settlement.name}")
            return  # one at a time

    def castle_defenders(self, civ, tile: int) -> float:
        """Soldiers holding a castle: its share of the garrison and any armies standing in it."""
        return self.castle_garrison(civ) + sum(a.size for a in self._guests(tile) if a.civ == civ.id)

    # -- scouting ----------------------------------------------------------------

    def scouted(self, viewer, army: Army) -> bool:
        """Whether `viewer` can count this army: it is its own or an ally's, or one of its
        armies or capitals is within sight of it."""
        if army.civ == viewer.id or self.diplomacy.relation(viewer.id, army.civ).status == "alliance":
            return True
        spots = [s.tile for s in viewer.settlements]
        spots += [a.tile for a in viewer.armies if a.role == "field" and a.size >= 0.5]
        return any(self._reach(spot, army.tile) <= SCOUT_RANGE for spot in spots)

    def sighted(self, viewer, other) -> float:
        """The share of `other`'s soldiers that `viewer` can count."""
        total = sum(army.size for army in other.armies)
        if total <= 0:
            return 1.0
        return sum(army.size for army in other.armies if self.scouted(viewer, army)) / total

    def _worn_down(self, civ, army: Army) -> bool:
        """Whether an army in the field should go home to fill its ranks: it is well below what
        its commander can lead, and there are soldiers waiting in the garrison. An army holding
        a capital stays to see it through."""
        capacity = self.capacity(army)
        if army.size >= REFIT_BELOW * capacity or self._at_home(civ, army.tile) or self._holding(army):
            return False
        waiting = civ.garrison.size - GARRISON_KEEP * civ.soldiers
        return waiting >= max(MIN_FIELD_ARMY, REFIT_WAITING * capacity)

    def _outmatched(self, civ, army: Army) -> bool:
        """Whether enemy armies close by are far too strong for this one to face. An army that
        is holding a capital stays to see it through."""
        if self._holding(army):
            return False
        x, y = self.world.xy(army.tile)
        against = 0.0
        for enemy_id in self.diplomacy.enemies(civ.id):
            for other in self.civs[enemy_id].armies:
                if other.role != "field" or other.size < 0.5 or other.state in ("retreating", "returning"):
                    continue
                ox, oy = self.world.xy(other.tile)
                if max(abs(ox - x), abs(oy - y)) <= DANGER_RADIUS:
                    against += self.army_strength(other)
        return against > OUTMATCHED * self.army_strength(army)

    def _route(self, civ, start: int, goal: int, max_nodes: int | None = None) -> list[int] | None:
        """The way an army of this civ would go. Open water needs boats, and can only be put out
        onto from land near one of the civ's working harbours. The search may look at up to
        ROUTE_SEARCH times the map's tiles (at least MIN_ROUTE_SEARCH): on the large maps the
        way round can be long, like the Narrow Sea's from one continent's east to the other's."""
        mods = self.mods[civ.id]
        if max_nodes is None:
            max_nodes = max(MIN_ROUTE_SEARCH, int(ROUTE_SEARCH * self.world.width * self.world.height))
        return find_path(self.world, start, goal, bool(mods.bridges), bool(mods.boats), max_nodes,
                         ports(civ, self.world))

    def _gap(self, a: int, b: int) -> int:
        ax, ay = self.world.xy(a)
        bx, by = self.world.xy(b)
        return abs(ax - bx) + abs(ay - by)

    def _nearest_intruder(self, civ, army: Army, enemy) -> Army | None:
        """The closest enemy army on the civ's land, at its border, or near its capital."""
        world = self.world
        cx, cy = world.xy(civ.capital.tile)
        ax, ay = world.xy(army.tile)
        best, best_distance = None, None
        for other in enemy.armies:
            if other.role != "field" or other.size < 0.5 or other.state in ("retreating", "returning"):
                continue
            x, y = world.xy(other.tile)
            at_the_border = any(world.owner[n] == civ.id for n in world.neighbors(other.tile))
            if (world.owner[other.tile] != civ.id and not at_the_border
                    and max(abs(x - cx), abs(y - cy)) > DEFENCE_RADIUS):
                continue
            distance = abs(x - ax) + abs(y - ay)
            if best_distance is None or distance < best_distance:
                best, best_distance = other, distance
        return best

    # -- movement ------------------------------------------------------------

    def _march(self, civ, army: Army) -> None:
        if not army.path:
            army.move_points = 0.0
            return
        world = self.world
        mods = self.mods[civ.id]
        enemies = set(self.diplomacy.enemies(civ.id))
        speed = army.speed + (mods.home_speed if world.owner[army.tile] == civ.id else 0.0)
        if army.refit or army.state == "returning":
            speed += mods.reinforce  # the way home is the quickest once there are railways
        army.move_points = min(army.move_points + speed, 2 * speed + 3)
        while army.path:
            step = army.path[0]
            if (world.owner[step] in enemies and not army.refit
                    and army.state not in ("retreating", "returning", "pursuing")):
                # Enemy ground: it has to be taken before the army can move onto it.
                army.move_points = 0.0  # waiting does not bank movement
                return
            cost = step_cost(world, step, bool(mods.bridges), bool(mods.boats))
            embarking = world.is_boat_water(step) and not world.is_boat_water(army.tile)
            if cost is None or (embarking and army.tile not in ports(civ, world)):
                # No way on: the harbour it was to sail from may have been lost since the
                # route was planned. It stays ashore and plans again.
                army.path = []
                army.path_tick = -10_000
                return
            if army.move_points < cost:
                return
            army.move_points -= cost
            # On open water an army is aboard ship: it can only have put out from land near one
            # of its civ's working harbours, and stays aboard until it lands.
            army.boat = world.is_boat_water(step)
            army.tile = army.path.pop(0)

    # -- battles -------------------------------------------------------------

    def _fight(self, tick: int, events: list) -> set[int]:
        """Armies of warring civs within one tile of each other fight. Returns the ids of armies engaged."""
        world = self.world
        pairs: list[tuple[Army, Army]] = []
        for (a, b), relation in self.diplomacy.relations.items():
            if relation.status != "war":
                continue
            for mine in self.civs[a].armies:
                if mine.size < 0.5 or mine.state in ("retreating", "returning") or self._broken(mine, tick):
                    continue
                mx, my = world.xy(mine.tile)
                for theirs in self.civs[b].armies:
                    if theirs.size < 0.5 or theirs.state in ("retreating", "returning") or self._broken(theirs, tick):
                        continue
                    tx, ty = world.xy(theirs.tile)
                    if max(abs(mx - tx), abs(my - ty)) <= 1:
                        pairs.append((mine, theirs))

        busy: set[int] = set()
        seen: set[tuple[int, int]] = set()
        for one, two in pairs:
            for army, other in ((one, two), (two, one)):
                if other.role == "garrison":  # fighting a castle's garrison shows how many hold it
                    self.probed[(army.civ, other.tile)] = tick
            key = (one.id, two.id)
            seen.add(key)
            started = self._battles.setdefault(key, tick)
            busy.update(key)
            for army in (one, two):
                if army.role == "field":
                    army.state = "fighting"
            self._battle_tick(one, two, tick, started, events)
        for key in [k for k in self._battles if k not in seen]:
            del self._battles[key]
        fighting = set(self._battles) | {(b, a) for a, b in self._battles}
        for key in [k for k in self._lost if k not in fighting]:
            del self._lost[key]
        return busy

    def _battle_strength(self, army: Army, enemy: Army, tick: int) -> float:
        """An army's strength in this battle; on its own ground it adds militia and the home bonus."""
        civ = self.civs[army.civ]
        strength = self.army_strength(army, enemy.units)
        if self.world.owner[army.tile] != civ.id:
            return strength
        war = self.diplomacy.relation(army.civ, enemy.civ).war
        if war and war.betrayer == enemy.civ and tick < war.surprise_until:
            return strength  # betrayed: caught off guard, no militia and no home advantage yet
        mods = self.mods[civ.id]
        militia = rules.MILITIA * civ.population * (1 + mods.military)
        held = 1 + self.post_defence(civ, army.tile)  # a commander stationed at this capital
        return (strength + militia) * (1 + rules.HOME_BONUS + mods.defense) * held

    def _battle_tick(self, one: Army, two: Army, tick: int, started: int, events: list) -> None:
        strengths = {one.id: self._battle_strength(one, two, tick), two.id: self._battle_strength(two, one, tick)}
        total = sum(strengths.values())
        war = self.diplomacy.relation(one.civ, two.civ).war
        engaged = min(one.size, two.size)
        if total > 0 and engaged > 0:
            for army, enemy in ((one, two), (two, one)):
                # The phase 3 casualty rule, at battle intensity; a skilled commander loses fewer.
                loss = 2 * BATTLE_INTENSITY * rules.CASUALTY_RATE * engaged * strengths[enemy.id] / total
                if army.commander:
                    loss *= 1 - army.commander.casualty_reduction
                loss *= max(0.2, 1 + self.mods[army.civ].casualties)
                loss = min(loss, army.size)
                fallen = self._lost.setdefault((army.id, enemy.id), {})
                for unit, count in army.take(loss).items():
                    fallen[unit] = fallen.get(unit, 0.0) + count
                civ = self.civs[army.civ]
                civ.soldiers = max(0.0, civ.soldiers - loss)
                civ.population = max(MIN_POPULATION, civ.population - loss)
                if war:
                    war.casualties[civ.id] += loss
                self._gain(army, XP_PER_BATTLE_TICK)

        # An army breaks when it is wiped out or its strength falls below half its opponent's.
        # The weaker side loses a larger share each tick, so the gap widens until that happens:
        # quickly when the armies are unequal, slowly when they are close.
        for army, enemy in ((one, two), (two, one)):
            if army.size < 1.0 or strengths[army.id] < ROUT_RATIO * strengths[enemy.id]:
                self._defeat(army, enemy, tick, events)
                return

    def _broken(self, army: Army, tick: int) -> bool:
        """An army beaten in battle cannot fight again until it has rallied: a garrison where it
        stands, a field army once it has fallen back to a capital and is resting there."""
        return tick < self._rally.get(army.id, 0) and (army.role == "garrison" or army.state == "idle")

    def _spare(self, loser: Army, winner: Army) -> None:
        """Not all a battle's losses are dead. Of the beaten side's, 60% are wounded and 30% got
        away unharmed; of the winner's, half are wounded. The wounded go to hospital."""
        fallen = self._lost.pop((loser.id, winner.id), {})
        self._casualties(self.civs[winner.civ], self._lost.pop((winner.id, loser.id), {}), winner.tier,
                         WOUNDED_IN_VICTORY)
        amount = sum(fallen.values())
        if amount <= 0:
            return
        civ = self.civs[loser.civ]
        self._casualties(civ, fallen, loser.tier, WOUNDED_SHARE)
        civ.population += ESCAPE_SHARE * amount
        civ.soldiers += ESCAPE_SHARE * amount
        # Their horses are lost in the rout: riders who got away ride again only on horses the
        # stables can spare (which keeps the herd within what the stables can keep).
        civ.garrison.add(self._mount(civ, {unit: count * ESCAPE_SHARE for unit, count in fallen.items()}), loser.tier)
        war = self.diplomacy.relation(loser.civ, winner.civ).war
        if war:
            war.casualties[civ.id] = max(0.0, war.casualties[civ.id] - ESCAPE_SHARE * amount)

    def _defeat(self, loser: Army, winner: Army, tick: int, events: list) -> None:
        self._spare(loser, winner)
        if loser.role == "field":
            self._rout(loser, winner, tick, events)
            return
        # A garrison has nowhere to fall back to: it is scattered and takes time to rally.
        self._rally[loser.id] = tick + RALLY_TICKS
        self._battles.pop((loser.id, winner.id), None)
        self._battles.pop((winner.id, loser.id), None)
        if winner.commander:
            winner.commander.battles += 1
            winner.commander.wins += 1
            self._gain(winner, XP_WON)
        if winner.role == "field" and winner.state == "fighting":
            winner.state = "marching"
        winning, losing = self.civs[winner.civ], self.civs[loser.civ]
        events.append({"civ": winning.id, "kind": "war",
                       "text": f"{winning.name}'s army scatters the garrison of {losing.capital.name}"})

    def _rout(self, loser: Army, winner: Army, tick: int, events: list) -> None:
        losing, winning = self.civs[loser.civ], self.civs[winner.civ]
        x, y = self.world.xy(loser.tile)
        led = f" under {winner.commander.name}" if winner.commander else ""
        if winner.commander:
            winner.commander.battles += 1
            winner.commander.wins += 1
            self._gain(winner, XP_WON)
        fate = ""
        if loser.commander:
            loser.commander.battles += 1
            self._gain(loser, XP_FOUGHT)
            fate = self._commander_fate(loser.commander, losing, winning, tick)
            if fate:
                fate = f"; {loser.commander.name} {fate}"
                loser.commander = None
                loser.leaderless_until = tick + REPLACEMENT_TICKS
        loser.state, loser.path, loser.siege_progress = "retreating", [], 0.0
        loser.rout_size = loser.size
        losing.last_rout = tick
        loser.pursuing = None
        if winner.role == "field" and winner.state == "fighting":
            winner.state = "marching"
        self._battles.pop((loser.id, winner.id), None)
        self._battles.pop((winner.id, loser.id), None)
        events.append({"civ": winning.id, "kind": "war",
                       "text": f"{winning.name}'s army{led} routs {losing.name}'s at ({x}, {y}){fate}"})
        self.diplomacy.history.append({"tick": tick, "civs": [winning.id, losing.id],
                                       "text": f"{winning.name}'s army routs {losing.name}'s"})
        if loser.size < 1.0:
            self._finish_off(loser, winner, tick, events)  # nothing left to run
        elif self._can_pursue(winner, loser) and not self._holding(winner):
            winner.state, winner.path = "pursuing", []
            winner.pursuing = loser.id
            winner.pursuit_origin = winner.tile
            winner.pursuit_until = tick + PURSUIT_DAYS

    # -- pursuit -------------------------------------------------------------

    def _can_pursue(self, winner: Army, loser: Army) -> bool:
        """A victor gives chase if it can keep up and nothing else threatens it nearby."""
        if winner.role != "field" or winner.size < 1.0 or winner.speed < loser.speed:
            return False
        if self._at_home(self.civs[loser.civ], loser.tile):
            return False  # already safe behind walls
        for enemy_id in self.diplomacy.enemies(winner.civ):
            for other in self.civs[enemy_id].armies:
                if other is loser or other.size < 0.5 or other.state in ("retreating", "returning"):
                    continue
                if self._reach(winner.tile, other.tile) <= PURSUIT_THREAT_RADIUS:
                    return False
        return True

    def _reach(self, a: int, b: int) -> int:
        ax, ay = self.world.xy(a)
        bx, by = self.world.xy(b)
        return max(abs(ax - bx), abs(ay - by))

    def _find_army(self, army_id: int) -> Army | None:
        for civ in self.civs.values():
            for army in civ.armies:
                if army.id == army_id:
                    return army
        return None

    def _pursue(self, civ, army: Army, tick: int, events: list) -> None:
        """Chase the routed army. While it is within a tile, it is cut down as it runs."""
        quarry = self._find_army(army.pursuing) if army.pursuing is not None else None
        if quarry is None or quarry.state != "retreating":
            self._end_pursuit(army, tick)
            return
        fled = self.civs[quarry.civ]
        escaped = (tick >= army.pursuit_until
                   or self._gap(army.tile, army.pursuit_origin) > PURSUIT_RANGE
                   or self._at_home(fled, quarry.tile)
                   or any(other is not quarry and other.size >= 0.5 and other.state != "retreating"
                          and self._reach(other.tile, quarry.tile) <= 1 for other in fled.armies))
        if escaped:
            self._end_pursuit(army, tick)
            return
        army.path = self._route(civ, army.tile, quarry.tile, max_nodes=1500) or []
        self._march(civ, army)
        if self._reach(army.tile, quarry.tile) > 1:
            return
        war = self.diplomacy.relation(civ.id, fled.id).war
        self._scatter_soldiers(fled, quarry, PURSUIT_LOSS * quarry.rout_size, war)
        if quarry.size < 1.0 or quarry.size < PURSUIT_FINISH * quarry.rout_size:
            self._finish_off(quarry, army, tick, events)
            self._end_pursuit(army, tick)

    def _end_pursuit(self, army: Army, tick: int) -> None:
        army.pursuing = None
        army.path = []
        army.disordered_until = tick + DISORDER_DAYS
        if army.state == "pursuing":
            army.state = "marching"

    def _scatter_soldiers(self, civ, army: Army, amount: float, war) -> None:
        """Soldiers cut off from a fleeing army: most are wounded, some get home, a few die."""
        amount = min(amount, army.size)
        if amount <= 0:
            return
        taken = army.take(amount)
        civ.garrison.add({unit: count * ESCAPE_SHARE for unit, count in taken.items()}, army.tier)
        wounded, dead = WOUNDED_SHARE * amount, DEAD_SHARE * amount
        civ.soldiers = max(0.0, civ.soldiers - wounded - dead)
        dead += self._admit(civ, {unit: count * WOUNDED_SHARE for unit, count in taken.items()}, army.tier)
        civ.population = max(MIN_POPULATION, civ.population - dead)
        if war:
            war.casualties[civ.id] += wounded + dead

    def _finish_off(self, loser: Army, winner: Army, tick: int, events: list) -> None:
        """A routed army that is caught and broken up ceases to exist; its commander meets his fate."""
        losing, winning = self.civs[loser.civ], self.civs[winner.civ]
        war = self.diplomacy.relation(losing.id, winning.id).war
        self._scatter_soldiers(losing, loser, loser.size, war)
        fate = ""
        commander = loser.commander
        if commander:
            fate = self._commander_fate(commander, losing, winning, tick)
            if not fate:
                losing.commanders.append(commander)  # he gets away, to be posted to a capital
            fate = f"; {commander.name} {fate or 'escapes'}"
            loser.commander = None
        if winner.commander:
            winner.commander.wins += 1
            self._gain(winner, XP_WON)
        if loser in losing.armies:
            losing.armies.remove(loser)
        self._rally.pop(loser.id, None)
        events.append({"civ": winning.id, "kind": "war",
                       "text": f"{winning.name}'s army runs down and destroys {losing.name}'s routed army{fate}"})
        self.diplomacy.history.append({"tick": tick, "civs": [winning.id, losing.id],
                                       "text": f"{winning.name} destroys a routed army of {losing.name}{fate}"})

    # -- captured commanders -------------------------------------------------

    def ransom(self, commander: Commander) -> int:
        return RANSOM_BASE + RANSOM_PER_LEVEL * commander.level

    def _hold_captives(self, civ, tick: int, events: list) -> None:
        """A captive is bought back by his own side when it can afford him, and goes free
        when the two civs are at peace."""
        for captive in list(civ.captives):
            home = self.civs[captive.home]
            name = captive.commander.name
            if not home.alive:
                self._enlist(civ, captive, f"{name}, his people gone, takes service with {civ.name}", events)
                continue
            price = self.ransom(captive.commander)
            if home.resources["gold"] >= price + GOLD_RESERVE:
                home.resources["gold"] -= price
                civ.resources["gold"] += price
                civ.captives.remove(captive)
                home.commanders.append(captive.commander)
                events.append({"civ": home.id, "kind": "war",
                               "text": f"{home.name} ransoms {name} from {civ.name} for {price} gold"})
                continue
            if self.diplomacy.relation(civ.id, home.id).status != "war":
                civ.captives.remove(captive)
                home.commanders.append(captive.commander)
                events.append({"civ": home.id, "kind": "war",
                               "text": f"{civ.name} releases {name} to {home.name} now that they are at peace"})

    def _enlist(self, civ, captive: Captive, text: str, events: list) -> None:
        civ.captives.remove(captive)
        if self.roster(civ) >= ROSTER_CAP:
            return  # no place for him: he is simply let go
        civ.commanders.append(captive.commander)
        events.append({"civ": civ.id, "kind": "war", "text": text})

    # -- campaigns against the native faction --------------------------------

    def _campaign(self, civ, tick: int) -> None:
        """A civ at peace takes a neighbouring native capital by force when it can field about
        twice the garrison's strength. No declaration, no strategist: this is plain policy."""
        world = self.world
        natives = self.diplomacy.natives
        expedition = next((a for a in civ.armies if a.target_region is not None), None)
        at_war = bool(self.diplomacy.enemies(civ.id))
        if expedition:
            region = world.regions[expedition.target_region]
            if (at_war or not region.neutral) and expedition.state not in ("returning", "retreating"):
                expedition.state, expedition.path = "returning", []  # needed at home, or someone got there first
            if expedition.state in ("returning", "retreating"):
                civ.campaign_muster = 0.0
            return
        civ.campaign_muster = 0.0
        if natives is None or at_war or tick < civ.campaign_cooldown:
            return
        if sum(1 for a in civ.armies if a.role == "field" and a.state != "returning") >= MAX_ARMIES:
            return
        target = self._campaign_target(civ)
        if target is None:
            return
        need = CAMPAIGN_ADVANTAGE * natives.defence(target)
        soldiers = need / max(self.diplomacy.quality(civ), 0.1) / (1 - GARRISON_KEEP)
        if soldiers > self.diplomacy.mobilization_cap(civ) * civ.population:
            return  # not strong enough yet
        if civ.income["gold"] <= 0 and civ.resources["gold"] < 0.2 * self.mods[civ.id].storage["gold"]:
            return  # cannot pay an army just now
        civ.campaign_muster = 1.1 * soldiers / max(civ.population, 1.0)
        if self.diplomacy.strength(civ) * (1 - GARRISON_KEEP) < need:
            return  # still mustering
        if self._route(civ, civ.capital.tile, target.capital) is None:
            # Across water it has no harbour for, or cut off: look elsewhere for a good while.
            self._no_way[(civ.id, target.id)] = tick + CAMPAIGN_RETRY
            return
        army = Army(self.next_id(), civ.id, civ.capital.tile, "field", target_region=target.id,
                    commander=self._appoint(civ), state="marching")
        army.add(civ.garrison.take(min((1 - GARRISON_KEEP) * civ.soldiers, self.capacity(army))), civ.garrison.tier)
        civ.armies.append(army)

    def _worth(self, values: dict, tile: int) -> float:
        """What the region whose capital stands on `tile` is worth to the civ, 0 without a valuation."""
        region = self.world.region_of[tile]
        return values[region].total if region in values else 0.0

    def _campaign_target(self, civ):
        """The native region worth most to the civ (strategy/geography.py) among those it can get
        at: touching its land, partly settled by it, or across water it has ships and a harbour
        for. Without a valuation: the one it has settled most of, else the nearest touching it."""
        natives = self.diplomacy.natives
        held = {region.id for region in self.world.regions if region.owner == civ.id}
        values = self.geography.values(civ, self._tick) if self.geography is not None else None
        best, best_key = None, None
        for region in self.world.regions:
            if not region.neutral:
                continue
            if self._tick < self._no_way.get((civ.id, region.id), 0):
                continue  # no army could get there when last tried
            share = natives.shares(region).get(civ.id, 0.0)
            near = share > 0 or bool(self._touching[region.id] & held)
            if values is None:
                if not near:
                    continue
                key = (-share, self._gap(civ.capital.tile, region.capital), region.id)
            elif region.id in values:
                worth = values[region.id]
                overseas = worth.by_sea and worth.access >= ACCESS_BY_SHIP
                if not (near or overseas):
                    continue
                key = (-worth.total, region.id)
            else:
                continue
            if best_key is None or key < best_key:
                best, best_key = region, key
        return best

    def _storm(self, civ, army: Army, tick: int, events: list) -> None:
        """An expedition next to its target capital fights the native garrison until one side gives way."""
        if army.state in ("returning", "retreating"):
            return
        region = self.world.regions[army.target_region]
        natives = self.diplomacy.natives
        ax, ay = self.world.xy(army.tile)
        cx, cy = self.world.xy(region.capital)
        if not region.neutral or max(abs(ax - cx), abs(ay - cy)) > 1:
            return
        if army.engaged_since is None:
            army.engaged_since = tick
        army.state, army.path = "fighting", []
        region.under_attack = tick
        attack, defence = self.army_strength(army), natives.defence(region)
        engaged = min(army.size, region.garrison)
        if attack + defence > 0 and engaged > 0:
            rate = 2 * BATTLE_INTENSITY * rules.CASUALTY_RATE
            loss = rate * engaged * defence / (attack + defence)
            if army.commander:
                loss *= 1 - army.commander.casualty_reduction
            loss = min(army.size, loss * max(0.2, 1 + self.mods[civ.id].casualties))
            fallen = army.take(loss)
            civ.soldiers = max(0.0, civ.soldiers - loss)
            civ.population = max(MIN_POPULATION, civ.population - loss)
            self._casualties(civ, fallen, army.tier, WOUNDED_IN_VICTORY)
            region.garrison = max(0.0, region.garrison - rate * engaged * attack / (attack + defence))
            self._gain(army, XP_PER_BATTLE_TICK)

        # Like any battle, the assault runs until one side is broken.
        attack, defence = self.army_strength(army), natives.defence(region)
        if region.garrison < 1.0:
            if army.commander:
                army.commander.battles += 1
                army.commander.wins += 1
                self._gain(army, XP_WON)
            self.diplomacy.capture_region(civ, region, tick, events)
            army.state, army.engaged_since = "returning", None
            civ.campaign_cooldown = tick + CAMPAIGN_REST
        elif army.size < 1.0 or attack < ROUT_RATIO * defence:
            if army.commander:
                army.commander.battles += 1
                self._gain(army, XP_FOUGHT)
            army.state, army.engaged_since = "retreating", None
            civ.campaign_cooldown = tick + CAMPAIGN_RETRY
            events.append({"civ": civ.id, "kind": "region",
                           "text": f"{civ.name}'s attack on {region.capital_name} is beaten off by {self.diplomacy.faction}"})

    # -- taking ground -------------------------------------------------------

    def tile_price(self, attacker, tile: int) -> float:
        """Capture progress a tile costs: its terrain, times three for an unbridged river or a capital."""
        ford = self.world.crossing_cost(tile, bool(self.mods[attacker.id].bridges), boats=True) or 1.0
        walls = rules.CAPITAL_DEFENSE if tile in self.world.capital_tiles else 1.0
        holder = self.civs.get(self.world.owner[tile])
        if holder is not None and tile in self.world.capital_tiles:
            walls *= 1 + self.post_defence(holder, tile)  # a commander stationed there
        return rules.TILE_DEFENSE.get(self.world.biomes[tile], 1.0) * ford * walls

    def _besiege(self, civ, army: Army, tick: int, events: list) -> None:
        """Capture the enemy tile blocking the army's way, by the phase 3 capture rule."""
        if not army.path or army.refit or army.state in ("retreating", "returning", "idle"):
            return
        target = army.path[0]
        enemy = self.civs.get(army.target_civ)
        if enemy is None or not enemy.alive:
            return
        relation = self.diplomacy.relation(civ.id, enemy.id)
        war = relation.war
        if war is None or self.world.owner[target] != enemy.id or civ.id not in war.aggressors:
            return
        army.state = "besieging"
        if target in self.world.capital_tiles:
            self.probed[(civ.id, target)] = tick  # at the walls: the defenders can be counted

        surprised = war.betrayer == civ.id and tick < war.surprise_until
        mods = self.mods[enemy.id]
        militia = 0.0 if surprised else rules.MILITIA * enemy.population * (1 + mods.military)
        home = 0.0 if surprised else rules.HOME_BONUS
        attack = self.army_strength(army)
        defence = militia * (1 + home + mods.defense)
        if target in self.world.capital_tiles and target != enemy.capital.tile and enemy.garrison is not None:
            # The soldiers no general is leading are spread through the civ's capitals.
            held = unit_strength(enemy.garrison.units) * self.diplomacy.quality(enemy) / max(1, len(enemy.settlements))
            defence += held * tier_strength(enemy.garrison.tier) * (1 + home + mods.defense)
        if target in self.world.capital_tiles:
            # Allies standing in the capital help hold it.
            defence += sum(self.army_strength(guest) for guest in self._guests(target)) * (1 + home + mods.defense)
        if attack > defence:
            gain = rules.CAPTURE_RATE * (attack - defence) / (attack + defence)
            if surprised:
                gain *= rules.SURPRISE_CAPTURE
            gain *= 1 + self.mods[civ.id].capture_speed
            army.siege_progress = min(army.siege_progress + gain,
                                      4 * max(rules.TILE_DEFENSE.values()) * rules.CAPITAL_DEFENSE)
        price = self.tile_price(civ, target)
        if army.siege_progress < price:
            return
        region = self._capital_region(target, enemy)
        if region is not None:
            # A capital does not fall the moment it is breached: the army has to hold it.
            if region.held_by is None:
                region.held_by, region.hold = civ.id, 0
                self.diplomacy._log(tick, events, "war", [civ, enemy],
                                    f"{civ.name}'s army breaks into {region.capital_name}: {region.name} "
                                    f"falls unless {enemy.name} drives it out within {rules.CAPITAL_HOLD} days")
            if region.held_by != civ.id:
                # An ally got there first: the hold is theirs, but a second army in the breach
                # brings the end on half as fast again.
                if (attack > defence and tick % 2 == 0
                        and self.diplomacy.relation(civ.id, region.held_by).status == "alliance"):
                    region.hold = min(rules.CAPITAL_HOLD - 1, region.hold + 1)
                return
            if attack > defence:
                region.hold += 1  # a tick spent fighting off a relief never reaches here
            if region.hold < rules.CAPITAL_HOLD:
                return
            region.held_by, region.hold = None, 0
        army.siege_progress -= price
        self.diplomacy._capture_tile(relation, civ, enemy, target, tick, events)

        # Undefended ground beside the breach falls with it. Capitals never fall this way.
        taken = 0
        for side in sorted(self.world.neighbors(target)):
            if relation.war is not war or taken >= SWATH or not enemy.alive:
                break
            if (self.world.owner[side] == enemy.id and side not in self.world.capital_tiles
                    and self.tile_price(civ, side) <= SWATH_MAX_PRICE and not self._defended(side, enemy)):
                self.diplomacy._capture_tile(relation, civ, enemy, side, tick, events)
                taken += 1

    def _capital_region(self, tile: int, holder):
        """The region whose capital stands on this tile, if `holder` owns that region."""
        region_id = self.world.capital_tiles.get(tile)
        if region_id is None:
            return None
        region = self.world.regions[region_id]
        return region if region.owner == holder.id else None

    def _holder(self, region) -> Army | None:
        """The army holding a breached capital: the occupier's strongest one beside it still in the fight."""
        occupier = self.civs.get(region.held_by)
        if occupier is None or not occupier.alive:
            return None
        cx, cy = self.world.xy(region.capital)
        best = None
        for army in occupier.armies:
            if army.role != "field" or army.size < 0.5 or army.state in ("retreating", "returning", "idle"):
                continue
            x, y = self.world.xy(army.tile)
            if max(abs(x - cx), abs(y - cy)) <= 1 and (best is None or army.size > best.size):
                best = army
        return best

    def _holding(self, army: Army) -> bool:
        """Whether the army stands beside a capital its civ is holding: it does not leave to chase anyone."""
        x, y = self.world.xy(army.tile)
        for region in self.world.regions:
            if region.held_by == army.civ:
                cx, cy = self.world.xy(region.capital)
                if max(abs(x - cx), abs(y - cy)) <= 1:
                    return True
        return False

    def _relieve(self, tick: int, events: list) -> None:
        """A hold on a capital is broken once the occupier has no army left beside it, or the war is over."""
        for region in self.world.regions:
            if region.held_by is None:
                continue
            occupier, owner = self.civs.get(region.held_by), self.civs.get(region.owner)
            at_war = (occupier is not None and owner is not None and occupier.alive and owner.alive
                      and self.diplomacy.relation(occupier.id, owner.id).war is not None)
            if at_war and self._holder(region) is not None:
                continue
            region.held_by, region.hold = None, 0
            if at_war:
                self.diplomacy._log(tick, events, "war", [owner, occupier],
                                    f"{owner.name} relieves {region.capital_name}: {occupier.name}'s hold on it is broken")
                self.diplomacy.remember(owner.id, occupier.id, -0.2)

    def _besieger(self, civ, enemy) -> Army | None:
        """The enemy army holding one of the civ's capitals, if any: the one nearest to falling first."""
        held = [r for r in self.world.regions if r.owner == civ.id and r.held_by == enemy.id]
        for region in sorted(held, key=lambda r: (-r.hold, r.id)):
            army = self._holder(region)
            if army is not None:
                return army
        return None

    def _defended(self, tile: int, defender) -> bool:
        x, y = self.world.xy(tile)
        for army in defender.armies:
            ax, ay = self.world.xy(army.tile)
            if army.size >= 0.5 and max(abs(ax - x), abs(ay - y)) <= 1:
                return True
        return False
