"""Relations between civs: carries out, every tick, what the strategic layer intends.

The strategic layer only sets an Intent per neighbour at its check-ins. Everything
mechanical happens here: opening and running trade deals, forming and dissolving
alliances, declaring wars, resolving combat and moving borders.
"""

from ..economy import recompute_capacity
from ..economy.rules import (
    GARRISON,
    MAX_MOBILIZATION,
    MIN_POPULATION,
    RESOURCES,
    UNPAID_QUALITY,
    UNSUPPLIED_QUALITY,
)
from ..map import Biome, WorldMap
from . import rules
from .model import FRIENDLY, Deal, Intent, Relation, Stance, War

REACH_CACHE_TICKS = 10
HISTORY_LIMIT = 200


class Diplomacy:
    def __init__(self, world: WorldMap, civs: list, modifiers: dict, building_defs: dict):
        self.world = world
        self.building_defs = building_defs
        self.civs = {civ.id: civ for civ in civs}
        self.mods = modifiers  # civ id -> Modifiers; the simulation keeps this current
        ids = sorted(self.civs)
        self.intents: dict[tuple[int, int], Intent] = {(a, b): Intent() for a in ids for b in ids if a != b}
        self.relations: dict[tuple[int, int], Relation] = {(a, b): Relation() for a in ids for b in ids if a < b}
        self.deals: list[Deal] = []
        self.history: list[dict] = []  # {"tick", "civs", "text"}, oldest first
        self._next_deal_id = 1
        self._reach_cache: dict[tuple[int, int], tuple[int, bool]] = {}

    # -- queries -------------------------------------------------------------

    def relation(self, a: int, b: int) -> Relation:
        return self.relations[(a, b) if a < b else (b, a)]

    def intent(self, a: int, b: int) -> Intent:
        """What `a` currently intends toward `b`."""
        return self.intents[(a, b)]

    def others(self, civ_id: int) -> list[int]:
        return [other for other in self.civs if other != civ_id]

    def allies(self, civ_id: int) -> list[int]:
        return [o for o in self.others(civ_id) if self.relation(civ_id, o).status == "alliance"]

    def enemies(self, civ_id: int) -> list[int]:
        return [o for o in self.others(civ_id) if self.relation(civ_id, o).status == "war"]

    def deal_between(self, a: int, b: int) -> Deal | None:
        return next((d for d in self.deals if {d.a, d.b} == {a, b}), None)

    def quality(self, civ) -> float:
        """Fighting strength of one soldier."""
        quality = 1 + self.mods[civ.id].military
        if civ.unpaid:
            quality *= UNPAID_QUALITY
        if civ.unsupplied:
            quality *= UNSUPPLIED_QUALITY
        return quality

    def strength(self, civ) -> float:
        """Strength of the army as it stands."""
        return civ.soldiers * self.quality(civ)

    def power(self, civ) -> float:
        """Strength the civ could field if it mobilised fully."""
        return civ.population * MAX_MOBILIZATION * (1 + self.mods[civ.id].military)

    def in_reach(self, a: int, b: int, tick: int) -> bool:
        """True if the two territories are close enough to fight over."""
        key = (a, b) if a < b else (b, a)
        cached = self._reach_cache.get(key)
        if cached is None or tick - cached[0] >= REACH_CACHE_TICKS:
            cached = (tick, bool(self._nearest_tiles(self.civs[a], self.civs[b], rules.REACH)))
            self._reach_cache[key] = cached
        return cached[1]

    def recent_history(self, civ_id: int, limit: int) -> list[dict]:
        return [entry for entry in self.history if civ_id in entry["civs"]][-limit:]

    # -- input from the strategic layer --------------------------------------

    def set_intents(self, civ_id: int, intents: dict[int, Intent]) -> None:
        for other, intent in intents.items():
            if other != civ_id and (civ_id, other) in self.intents:
                self.intents[(civ_id, other)] = intent

    def apply_modifiers(self, civ, mods) -> None:
        allies = len(self.allies(civ.id))
        mods.science_mult += rules.ALLY_SCIENCE * allies
        mods.defense += rules.ALLY_DEFENSE * allies

    # -- per-tick execution --------------------------------------------------

    def update(self, tick: int, events: list) -> None:
        for a, b in self.relations:
            self._resolve_pair(a, b, tick, events)
        self._run_deals(tick, events)
        for relation in self.relations.values():
            if relation.war:
                self._fight(relation, tick, events)
        self._issue_orders(tick)

    def _resolve_pair(self, a: int, b: int, tick: int, events: list) -> None:
        relation = self.relations[(a, b)]
        civ_a, civ_b = self.civs[a], self.civs[b]
        to_b, to_a = self.intents[(a, b)], self.intents[(b, a)]
        hostile = [civ for civ, intent in ((civ_a, to_b), (civ_b, to_a)) if intent.stance is Stance.AGGRESSION]

        if relation.status == "war":
            war = relation.war
            war.aggressors = {civ.id for civ in hostile}
            age = tick - war.start
            if age >= rules.MAX_WAR:
                self._end_war(relation, tick, events, rules.TRUCE,
                              f"{civ_a.name} and {civ_b.name} are exhausted and stop fighting")
            elif age >= rules.MIN_WAR and not hostile:
                self._end_war(relation, tick, events, rules.TRUCE, f"{civ_a.name} and {civ_b.name} make peace")
            return

        if hostile:
            if relation.status == "alliance":
                other = civ_b if hostile[0] is civ_a else civ_a
                self._set_status(relation, "peace", tick)
                self._log(tick, events, "diplomacy", [hostile[0], other],
                          f"{hostile[0].name} breaks its alliance with {other.name}")
            declarer = next((civ for civ in hostile if civ.resources["gold"] >= rules.WAR_COST), None)
            if declarer and tick >= relation.truce_until and self.in_reach(a, b, tick):
                target = civ_b if declarer is civ_a else civ_a
                declarer.resources["gold"] -= rules.WAR_COST
                self.deals = [d for d in self.deals if {d.a, d.b} != {a, b}]
                self._set_status(relation, "war", tick)
                relation.war = War(a, b, tick, aggressors={civ.id for civ in hostile},
                                   progress={a: 0.0, b: 0.0}, tiles_taken={a: 0, b: 0}, casualties={a: 0.0, b: 0.0})
                self._log(tick, events, "war", [declarer, target], f"{declarer.name} declares war on {target.name}")
            return

        friendly = to_b.stance in FRIENDLY and to_a.stance in FRIENDLY
        if relation.status == "alliance":
            if not friendly:
                self._set_status(relation, "peace", tick)
                self._log(tick, events, "diplomacy", [civ_a, civ_b],
                          f"The alliance between {civ_a.name} and {civ_b.name} lapses")
            else:
                for civ in (civ_a, civ_b):
                    civ.resources["gold"] = max(0.0, civ.resources["gold"] - rules.ALLIANCE_UPKEEP)
        elif (to_b.stance is Stance.ALLY and to_a.stance is Stance.ALLY
              and min(civ_a.resources["gold"], civ_b.resources["gold"]) >= rules.ALLIANCE_COST):
            for civ in (civ_a, civ_b):
                civ.resources["gold"] -= rules.ALLIANCE_COST
            self._set_status(relation, "alliance", tick)
            self._log(tick, events, "diplomacy", [civ_a, civ_b], f"{civ_a.name} and {civ_b.name} form an alliance")

        if friendly and self.deal_between(a, b) is None:
            self._try_deal(civ_a, civ_b, to_b, to_a, relation, tick, events)

    def _set_status(self, relation: Relation, status: str, tick: int) -> None:
        relation.status = status
        relation.since = tick

    # -- trade ---------------------------------------------------------------

    def _try_deal(self, civ_a, civ_b, a_offer: Intent, b_offer: Intent, relation: Relation,
                  tick: int, events: list) -> None:
        """Open a deal if each side's offer is something the other can use and both can pay the fee."""
        if not a_offer.give or not b_offer.give or a_offer.give == b_offer.give:
            return
        a_rate = self._deal_rate(civ_a, civ_b, a_offer, b_offer)
        b_rate = self._deal_rate(civ_b, civ_a, b_offer, a_offer)
        if a_rate < rules.MIN_RATE or b_rate < rules.MIN_RATE:
            return
        fee = 0 if relation.status == "alliance" else rules.DEAL_FEE
        if min(civ_a.resources["gold"], civ_b.resources["gold"]) < fee:
            return
        for civ in (civ_a, civ_b):
            civ.resources["gold"] -= fee
        deal = Deal(self._next_deal_id, civ_a.id, civ_b.id, (a_offer.give, a_rate), (b_offer.give, b_rate), tick)
        self._next_deal_id += 1
        self.deals.append(deal)
        self._log(tick, events, "trade", [civ_a, civ_b],
                  f"{civ_a.name} trades {a_rate:g} {a_offer.give}/tick to {civ_b.name} for {b_rate:g} {b_offer.give}/tick")

    def _deal_rate(self, giver, receiver, offer: Intent, request: Intent) -> float:
        """Per-tick amount of the giver's offered resource; 0 if the receiver has no use for it."""
        res = offer.give
        if receiver.resources[res] >= rules.SURPLUS_FILL * self.mods[receiver.id].storage[res]:
            return 0.0
        rate = min(offer.give_rate, rules.MAX_RATE, giver.resources[res] / rules.SUSTAIN_TICKS)
        if request.want == res and request.want_rate > 0:
            rate = min(rate, request.want_rate)
        return round(rate, 2)

    def _run_deals(self, tick: int, events: list) -> None:
        for deal in list(self.deals):
            defaulter = None
            for giver_id, receiver_id, res, rate in deal.flows():
                giver, receiver = self.civs[giver_id], self.civs[receiver_id]
                sent = min(rate, giver.resources[res])
                giver.resources[res] -= sent
                room = self.mods[receiver_id].storage[res] - receiver.resources[res]
                receiver.resources[res] += max(0.0, min(sent, room))
                deal.missed[giver_id] = deal.missed.get(giver_id, 0) + 1 if sent < 0.5 * rate else 0
                if deal.missed[giver_id] >= rules.DEAL_MISS_LIMIT:
                    defaulter = giver
            if defaulter:
                self.deals.remove(deal)
                other = self.civs[deal.b if defaulter.id == deal.a else deal.a]
                self._log(tick, events, "trade", [defaulter, other],
                          f"{defaulter.name} can no longer supply its trade with {other.name}; the deal is cancelled")
            elif tick >= deal.end:
                self.deals.remove(deal)
                self._log(tick, events, "trade", [self.civs[deal.a], self.civs[deal.b]],
                          f"The trade deal between {self.civs[deal.a].name} and {self.civs[deal.b].name} expires")

    # -- war -----------------------------------------------------------------

    def _fight(self, relation: Relation, tick: int, events: list) -> None:
        war = relation.war
        sides = (self.civs[war.a], self.civs[war.b])
        troops = {civ.id: civ.soldiers / max(1, len(self.enemies(civ.id))) for civ in sides}
        strength = {civ.id: troops[civ.id] * self.quality(civ) for civ in sides}

        # Each side pushes into the other when its attack beats the other's defence.
        for attacker, defender in (sides, sides[::-1]):
            attack = strength[attacker.id] * (1.0 if attacker.id in war.aggressors else rules.COUNTER_ATTACK)
            militia = rules.MILITIA * defender.population * (1 + self.mods[defender.id].military)
            defence = (strength[defender.id] + militia) * (1 + rules.HOME_BONUS + self.mods[defender.id].defense)
            if attack > defence:
                gain = rules.CAPTURE_RATE * (attack - defence) / (attack + defence)
                war.progress[attacker.id] = min(war.progress[attacker.id] + gain, 2 * max(rules.TILE_DEFENSE.values()))

        # Both sides lose troops; the weaker side loses more.
        engaged = min(troops.values())
        total = sum(strength.values())
        if engaged > 0 and total > 0:
            for civ, enemy in (sides, sides[::-1]):
                loss = min(civ.soldiers, 2 * rules.CASUALTY_RATE * engaged * strength[enemy.id] / total)
                civ.soldiers -= loss
                civ.population = max(MIN_POPULATION, civ.population - loss)
                war.casualties[civ.id] += loss

        for attacker, defender in (sides, sides[::-1]):
            if relation.war is war:  # the other side may just have surrendered
                self._advance(relation, attacker, defender, tick, events)

    def _advance(self, relation: Relation, attacker, defender, tick: int, events: list) -> None:
        """Spend capture progress on the cheapest defender tile within reach."""
        war = relation.war
        if war.progress[attacker.id] < min(1.0, *rules.TILE_DEFENSE.values()):
            return
        world = self.world
        capital = defender.capital.tile
        cx, cy = world.xy(capital)

        def price(tile: int) -> float:
            return rules.TILE_DEFENSE.get(world.biomes[tile], 1.0)

        def order(tile: int) -> tuple[float, int]:
            x, y = world.xy(tile)
            return price(tile) + 0.3 * (abs(x - cx) + abs(y - cy)), tile

        candidates = [t for t in self._nearest_tiles(attacker, defender, rules.REACH) if t != capital]
        if not candidates:
            return
        tile = min(candidates, key=order)
        if war.progress[attacker.id] < price(tile):
            return
        war.progress[attacker.id] -= price(tile)
        self._capture_tile(relation, attacker, defender, tile, tick, events)

    def _capture_tile(self, relation: Relation, attacker, defender, tile: int, tick: int, events: list) -> None:
        """Move a tile, and everything standing on it, from the defender to the attacker."""
        world = self.world
        war = relation.war
        world.claim(tile, attacker.id)
        defender.territory.discard(tile)
        attacker.territory.add(tile)
        # Whatever stands on the tile now belongs to the captor, finished or not.
        for building in [b for b in defender.buildings if b.tile == tile]:
            defender.buildings.remove(building)
            attacker.buildings.append(building)
            bdef = self.building_defs[building.type]
            text = f"{attacker.name} captures a {bdef.name} from {defender.name}"
            if building.complete:
                text += self._seize_stores(bdef, attacker, defender)
            self._log(tick, events, "war", [attacker, defender], text)
        recompute_capacity(attacker, world)
        recompute_capacity(defender, world)
        war.tiles_taken[attacker.id] += 1
        self._reach_cache.clear()

        if tile in set(world.neighbors(defender.capital.tile, diagonal=True)):
            self._surrender(relation, attacker, defender, tick, events)

    def _seize_stores(self, bdef, attacker, defender) -> str:
        """What a captured storage building holds goes with it. Returns a note for the log.

        Stock is taken to be spread evenly over the defender's capacity for that
        resource. The captor keeps all of it even above its own cap; it just
        produces no more of that resource until it is back under.
        """
        note = ""
        for res, capacity in bdef.stores.items():
            share = defender.resources[res] * min(1.0, capacity / self.mods[defender.id].storage[res])
            defender.resources[res] -= share
            attacker.resources[res] += share
            # Caps move with the building; keep them in step until modifiers refresh next tick.
            self.mods[defender.id].storage[res] -= capacity
            self.mods[attacker.id].storage[res] += capacity
            note += f" holding {share:.0f} {res}"
        return note

    def _surrender(self, relation: Relation, winner, loser, tick: int, events: list) -> None:
        for res in RESOURCES:
            taken = rules.TRIBUTE * loser.resources[res]
            loser.resources[res] -= taken
            room = self.mods[winner.id].storage[res] - winner.resources[res]
            winner.resources[res] += max(0.0, min(taken, room))
        taken = relation.war.tiles_taken[winner.id]
        self._end_war(relation, tick, events, rules.SURRENDER_TRUCE,
                      f"{loser.name} surrenders to {winner.name}, having lost {taken} tiles, and pays tribute")
        self.intents[(loser.id, winner.id)] = Intent(tick=tick)

    def _end_war(self, relation: Relation, tick: int, events: list, truce: int, text: str) -> None:
        war = relation.war
        relation.war = None
        relation.truce_until = tick + truce
        self._set_status(relation, "peace", tick)
        self._log(tick, events, "war", [self.civs[war.a], self.civs[war.b]], text)

    def _nearest_tiles(self, attacker, defender, limit: int) -> list[int]:
        """The defender's tiles closest to the attacker's territory, if within `limit` steps."""
        world = self.world
        seen = set(attacker.territory)
        frontier = sorted(seen)
        for _ in range(limit):
            found, reached = [], []
            for tile in frontier:
                for n in world.neighbors(tile):
                    if n in seen:
                        continue
                    seen.add(n)
                    if world.owner[n] == defender.id:
                        found.append(n)
                    elif world.biomes[n] != Biome.OCEAN:
                        reached.append(n)
            if found:
                return found
            frontier = reached
        return []

    # -- standing orders for the economy and the AI --------------------------

    def _issue_orders(self, tick: int) -> None:
        for civ in self.civs.values():
            mobilisation = GARRISON
            threat = 0.0
            civ.march_target = None
            for other_id in self.others(civ.id):
                other = self.civs[other_id]
                mine, theirs = self.intents[(civ.id, other_id)], self.intents[(other_id, civ.id)]
                if self.relation(civ.id, other_id).status == "war":
                    threat = 1.0
                    if mine.stance is Stance.AGGRESSION:
                        mobilisation = max(mobilisation, mine.commitment * MAX_MOBILIZATION)
                    # Always raise enough to answer the army actually in the field.
                    mobilisation = max(mobilisation, min(MAX_MOBILIZATION, 0.05 + other.soldiers / civ.population))
                elif Stance.AGGRESSION in (mine.stance, theirs.stance):
                    threat = max(threat, 0.6)
                    mobilisation = max(mobilisation, rules.MUSTER * MAX_MOBILIZATION)
                    if (mine.stance is Stance.AGGRESSION and civ.march_target is None
                            and not self.in_reach(civ.id, other_id, tick)):
                        civ.march_target = other_id
            civ.soldier_target = mobilisation * civ.population
            civ.military_need = threat
            civ.exports = dict.fromkeys(RESOURCES, 0.0)
            civ.imports = dict.fromkeys(RESOURCES, 0.0)
        for deal in self.deals:
            for giver, receiver, res, rate in deal.flows():
                self.civs[giver].exports[res] += rate
                self.civs[receiver].imports[res] += rate

    def _log(self, tick: int, events: list, kind: str, civs: list, text: str) -> None:
        self.history.append({"tick": tick, "civs": [civ.id for civ in civs], "text": text})
        del self.history[:-HISTORY_LIMIT]
        events.append({"civ": civs[0].id, "kind": kind, "text": text})
