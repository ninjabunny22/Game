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
  - a civ at peace sends an expedition against a neighbouring native capital
    once its army is about twice the garrison's strength.
"""

import random
from collections.abc import Callable

from ..diplomacy import rules
from ..economy.rules import MIN_POPULATION
from ..map import WorldMap, find_path, region_neighbours, step_cost
from .army import XP_PER_LEVEL_STEP, Army, Commander
from .units import BASE_UNIT, UNIT_TYPES, unit_strength

GARRISON_KEEP = 0.2  # share of the soldiers that stays to hold the capital during a war
REINFORCE_RATE = 0.05  # share of the army that can reach a field army per tick once it has left home
MIN_FIELD_ARMY = 3.0  # soldiers below which an army will not set out
REPLAN_TICKS = 15
DEFENCE_RADIUS = 6  # a defending army also answers threats this close to the capital
# Battles have no fixed length: an army breaks when it is outmatched, and nothing else ends one.
# The casualty rate sets the pace. At 2.5 times the base rate a lopsided battle is over in a
# few ticks and a close one (armies within 10% of each other) takes roughly 40 to 100.
BATTLE_INTENSITY = 2.5
ROUT_RATIO = 0.5  # an army breaks when its strength falls below this share of its opponent's
RALLY_TICKS = 30  # rest at the capital after a rout before marching again
COMMANDER_DEATH_CHANCE = 0.15  # when the army is routed
REPLACEMENT_TICKS = 30
XP_PER_BATTLE_TICK = 1.0
XP_FOUGHT = 5.0
XP_WON = 25.0
SWATH = 2  # undefended enemy tiles beside a captured one that fall with it
SWATH_MAX_PRICE = 1.5
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
        self._named = 0
        self._touching = region_neighbours(world)

    # -- strength: the phase 3 formula, per army -----------------------------

    def army_strength(self, army: Army, enemy_units: dict[str, float] | None = None) -> float:
        """Soldiers x unit type (with counters) x quality x commander skill."""
        strength = unit_strength(army.units, enemy_units) * self.diplomacy.quality(self.civs[army.civ])
        if army.commander:
            strength *= 1 + army.commander.strength_bonus
        return strength

    # -- one tick ------------------------------------------------------------

    def update(self, tick: int, events: list) -> None:
        living = [civ for civ in self.civs.values() if civ.alive]
        for civ in living:
            self._sync(civ)
        for civ in living:
            self._organise(civ, tick)
            self._campaign(civ, tick)
        busy = self._fight(tick, events)
        for civ in living:
            for army in list(civ.armies):
                if army.role != "field" or army.id in busy or not civ.alive:
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
            garrison.add(self._recruits(civ, civ.soldiers - total))
        elif total > civ.soldiers + 1e-9:
            factor = civ.soldiers / total
            for army in civ.armies:
                army.scale(factor)

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

    def _organise(self, civ, tick: int) -> None:
        """One field army per enemy, each with a commander; the rest of the soldiers hold the capital."""
        enemies = self.diplomacy.enemies(civ.id)
        garrison = civ.garrison
        fielded = {a.target_civ for a in civ.armies
                   if a.role == "field" and a.state != "returning" and a.target_region is None}
        for enemy in enemies:
            if enemy not in fielded:
                army = Army(self.next_id(), civ.id, civ.capital.tile, "field", target_civ=enemy,
                            commander=self._appoint(civ))
                civ.armies.append(army)
        for army in civ.armies:
            if army.role != "field":
                continue
            if army.target_region is None and army.target_civ not in enemies and army.state != "returning":
                army.state, army.path, army.siege_progress = "returning", [], 0.0  # the war is over: go home
            if army.commander is None and army.tile == civ.capital.tile and tick >= army.leaderless_until:
                army.commander = self._appoint(civ)

        active = [a for a in civ.armies
                  if a.role == "field" and a.state != "returning" and a.target_region is None]
        if not active:
            return
        keep = GARRISON_KEEP * civ.soldiers
        each = (civ.soldiers - keep) / len(active)
        for army in active:
            spare = garrison.size - keep
            need = each - army.size
            if need <= 0 or spare <= 0:
                continue
            # At home an army fills its ranks at once; in the field reinforcements trickle out to it.
            pace = REINFORCE_RATE * (1 + self.mods[civ.id].reinforce)
            limit = need if army.tile == civ.capital.tile else max(1.0, pace * civ.soldiers)
            army.add(garrison.take(min(need, spare, limit)))

    def _appoint(self, civ) -> Commander:
        """The most experienced commander without an army, or a new one."""
        if civ.commanders:
            best = max(civ.commanders, key=lambda c: (c.experience, c.name))
            civ.commanders.remove(best)
            return best
        self._named += 1
        name = COMMANDER_NAMES[self.rng.randrange(len(COMMANDER_NAMES))]
        commander = Commander(f"{name} of {civ.name}" if self._named <= len(COMMANDER_NAMES) else f"{name} {self._named}")
        # Trained officers (Military Academy, General Staff) start above level 1.
        commander.experience = XP_PER_LEVEL_STEP * self.mods[civ.id].commander_start ** 2
        return commander

    def _gain(self, army: Army, experience: float) -> None:
        if army.commander:
            army.commander.experience += experience * (1 + self.mods[army.civ].commander_xp)

    def _disband(self, civ, army: Army) -> None:
        civ.garrison.add(army.units)
        if army.commander:
            civ.commanders.append(army.commander)
        civ.armies.remove(army)
        self._rally.pop(army.id, None)

    # -- orders --------------------------------------------------------------

    def _plan(self, civ, army: Army, tick: int) -> None:
        capital = civ.capital.tile
        if army.state in ("returning", "retreating"):
            if army.tile == capital:
                if army.state == "returning" or army.target_region is not None:
                    self._disband(civ, army)
                    return
                army.state, army.path = "idle", []
                self._rally[army.id] = tick + RALLY_TICKS
            goal = capital
        elif army.target_region is not None:
            goal = self.world.regions[army.target_region].capital
            if army.state == "idle":
                army.state = "marching"
        else:
            enemy = self.civs[army.target_civ]
            war = self.diplomacy.relation(civ.id, enemy.id).war
            rested = tick >= self._rally.get(army.id, 0)
            if war and civ.id in war.aggressors and rested and army.size >= MIN_FIELD_ARMY:
                # Make for the nearest capital the enemy holds: taking it takes its region.
                goal = min((s.tile for s in enemy.settlements), key=lambda t: (self._gap(army.tile, t), t))
                if army.state == "idle":
                    army.state = "marching"
            else:
                intruder = self._nearest_intruder(civ, army, enemy)
                goal = intruder.tile if intruder else capital
                army.state = "marching" if intruder and army.size >= MIN_FIELD_ARMY else "idle"
                if army.state == "idle":
                    goal = capital

        if army.tile == goal:
            army.path = []
            return
        stale = tick - army.path_tick >= REPLAN_TICKS
        if stale or not army.path or army.path[-1] != goal:
            mods = self.mods[civ.id]
            army.path = find_path(self.world, army.tile, goal, bool(mods.bridges), bool(mods.boats)) or []
            army.path_tick = tick

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
        army.move_points = min(army.move_points + speed, 2 * speed + 3)
        while army.path:
            step = army.path[0]
            if world.owner[step] in enemies and army.state not in ("retreating", "returning"):
                # Enemy ground: it has to be taken before the army can move onto it.
                army.move_points = 0.0  # waiting does not bank movement
                return
            cost = step_cost(world, step, bool(mods.bridges), bool(mods.boats))
            if cost is None:
                army.path = []
                return
            if army.move_points < cost:
                return
            army.move_points -= cost
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
        return (strength + militia) * (1 + rules.HOME_BONUS + mods.defense)

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
                army.take(loss)
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
        """A garrison beaten in battle cannot fight again until it has rallied."""
        return army.role == "garrison" and tick < self._rally.get(army.id, 0)

    def _defeat(self, loser: Army, winner: Army, tick: int, events: list) -> None:
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
        fallen = ""
        if loser.commander:
            loser.commander.battles += 1
            self._gain(loser, XP_FOUGHT)
            if loser.size < 1.0 or self.rng.random() < COMMANDER_DEATH_CHANCE:
                fallen = f"; {loser.commander.name} is killed"
                loser.commander = None
                loser.leaderless_until = tick + REPLACEMENT_TICKS
        loser.state, loser.path, loser.siege_progress = "retreating", [], 0.0
        if winner.role == "field" and winner.state == "fighting":
            winner.state = "marching"
        self._battles.pop((loser.id, winner.id), None)
        self._battles.pop((winner.id, loser.id), None)
        events.append({"civ": winning.id, "kind": "war",
                       "text": f"{winning.name}'s army{led} routs {losing.name}'s at ({x}, {y}){fallen}"})
        self.diplomacy.history.append({"tick": tick, "civs": [winning.id, losing.id],
                                       "text": f"{winning.name}'s army routs {losing.name}'s"})

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
        army = Army(self.next_id(), civ.id, civ.capital.tile, "field", target_region=target.id,
                    commander=self._appoint(civ), state="marching")
        army.add(civ.garrison.take((1 - GARRISON_KEEP) * civ.soldiers))
        civ.armies.append(army)

    def _campaign_target(self, civ):
        """The neutral region the civ has settled most of; failing that, the nearest one touching its land."""
        natives = self.diplomacy.natives
        held = {region.id for region in self.world.regions if region.owner == civ.id}
        best, best_key = None, None
        for region in self.world.regions:
            if not region.neutral:
                continue
            share = natives.shares(region).get(civ.id, 0.0)
            if share <= 0 and not (self._touching[region.id] & held):
                continue
            key = (-share, self._gap(civ.capital.tile, region.capital), region.id)
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
            army.take(loss)
            civ.soldiers = max(0.0, civ.soldiers - loss)
            civ.population = max(MIN_POPULATION, civ.population - loss)
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
        return rules.TILE_DEFENSE.get(self.world.biomes[tile], 1.0) * ford * walls

    def _besiege(self, civ, army: Army, tick: int, events: list) -> None:
        """Capture the enemy tile blocking the army's way, by the phase 3 capture rule."""
        if not army.path or army.state in ("retreating", "returning", "idle"):
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

        surprised = war.betrayer == civ.id and tick < war.surprise_until
        mods = self.mods[enemy.id]
        militia = 0.0 if surprised else rules.MILITIA * enemy.population * (1 + mods.military)
        home = 0.0 if surprised else rules.HOME_BONUS
        attack = self.army_strength(army)
        defence = militia * (1 + home + mods.defense)
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

    def _defended(self, tile: int, defender) -> bool:
        x, y = self.world.xy(tile)
        for army in defender.armies:
            ax, ay = self.world.xy(army.tile)
            if army.size >= 0.5 and max(abs(ax - x), abs(ay - y)) <= 1:
                return True
        return False
