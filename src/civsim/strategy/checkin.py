"""Check-ins: the hand-off between the simulation and a strategy brain.

The simulation never calls a brain. On a fixed interval it emits a CheckinRequest
per civ describing the situation; whoever drives the sim (the server, the headless
runner, a test) gets an answer from a brain and hands it back with
Simulation.submit(). This module turns that answer, which may come from a language
model and so may be wrong in any way, into validated Intents.
"""

from dataclasses import dataclass

from ..diplomacy import Intent, Stance
from ..diplomacy.rules import MAX_RATE, MIN_RATE
from ..economy.rules import RESOURCES

CHECKIN_INTERVAL = 50
MAX_REASON_LENGTH = 200

STANCE_ALIASES = {
    "war": Stance.AGGRESSION, "attack": Stance.AGGRESSION, "aggressive": Stance.AGGRESSION,
    "hostile": Stance.AGGRESSION, "alliance": Stance.ALLY, "allied": Stance.ALLY,
    "peace": Stance.IGNORE, "neutral": Stance.IGNORE, "none": Stance.IGNORE,
}


@dataclass
class CheckinRequest:
    civ_id: int
    tick: int
    context: dict  # the situation, as plain JSON-able data


def parse_stances(reply: object, context: dict, tick: int) -> tuple[dict[int, Intent], str]:
    """Intents per neighbour id from a brain's reply, plus its stated reason.

    Anything missing or malformed falls back to something safe; neighbours the
    reply does not mention are left out, so their previous intent stands.
    """
    if not isinstance(reply, dict):
        return {}, ""
    by_name = {n["name"].lower(): n for n in context["neighbors"]}
    by_id = {n["id"]: n for n in context["neighbors"]}
    intents: dict[int, Intent] = {}
    entries = reply.get("stances")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        target = entry.get("civ")
        neighbor = by_name.get(target.strip().lower()) if isinstance(target, str) else by_id.get(target)
        if neighbor is None or neighbor["id"] in intents:
            continue
        stance = _stance(entry.get("stance"))
        intent = Intent(stance=stance, tick=tick)
        if stance in (Stance.TRADE, Stance.ALLY):
            intent.give = _resource(entry.get("give"))
            intent.want = _resource(entry.get("want"))
            intent.give_rate = _number(entry.get("give_per_tick"), 1.0, MIN_RATE, MAX_RATE)
            intent.want_rate = _number(entry.get("want_per_tick"), 1.0, MIN_RATE, MAX_RATE)
            if intent.give is None or intent.give == intent.want:
                # No usable offer: fall back to the obvious one.
                fallback = default_offer(context["you"], neighbor)
                intent.give, intent.give_rate = fallback["give"], fallback["give_per_tick"]
                intent.want = intent.want or fallback["want"]
            _apply_water_priority(intent, context["you"], neighbor)
        elif stance is Stance.AGGRESSION:
            intent.commitment = _number(entry.get("troop_commitment"), 0.5, 0.1, 1.0)
        intents[neighbor["id"]] = intent
    reason = reply.get("reason")
    return intents, " ".join(reason.split())[:MAX_REASON_LENGTH] if isinstance(reason, str) else ""


WATER_PRIORITY = 0.3  # urgency from which water is asked for ahead of anything else, and never given away
WATER_URGENT = 0.7  # urgency from which every trade must be for water: as pressing as food


def default_offer(you: dict, neighbor: dict | None = None) -> dict:
    """The plain trade a civ would propose: its fullest stockpile for what it most needs.

    Water takes over as it gets scarce. A civ short of it asks for water before
    anything else, for more the worse off it is, and stops offering its own; a
    civ with water to spare offers it to a neighbour who is asking for it.
    """
    fill = {res: you["resources"][res]["stock"] / max(you["storage"][res], 1) for res in RESOURCES}
    water = you["water"]
    lacking = [res for res in you["lacking"] if res in RESOURCES]
    want = lacking[0] if lacking else min(RESOURCES, key=lambda res: (fill[res], res))
    want_rate = 1.0
    if water["urgency"] >= WATER_PRIORITY:
        want = "water"
        shortfall = max(0.0, water["use_per_tick"] - water["supply_per_tick"])
        want_rate = max(MIN_RATE, min(MAX_RATE, round(max(0.5, 1.5 * shortfall) * (0.5 + water["urgency"]), 1)))
    can_spare = [res for res in RESOURCES if res != want
                 and not (res == "water" and (water["urgency"] >= 0.15 or not water["rich"]))]
    give = max(can_spare, key=lambda res: (fill[res], res))
    asked_for_water = neighbor is not None and (neighbor.get("their_trade_offer") or {}).get("wants") == "water"
    if asked_for_water and "water" in can_spare:
        give = "water"  # a neighbour is thirsty and there is plenty: sell it
    rate = max(MIN_RATE, min(MAX_RATE, round(you["resources"][give]["stock"] / 100, 1)))
    return {"give": give, "give_per_tick": rate, "want": want, "want_per_tick": want_rate}


def _apply_water_priority(intent: Intent, you: dict, neighbor: dict) -> None:
    """Hold any strategist, model or rules, to the water priorities above.

    A civ whose water is tightening does not trade its water away; one in real
    need turns every trade into a request for water.
    """
    urgency = you["water"]["urgency"]
    if urgency < WATER_PRIORITY:
        return
    fallback = default_offer(you, neighbor)
    if intent.give == "water":
        intent.give, intent.give_rate = fallback["give"], fallback["give_per_tick"]
    if urgency >= WATER_URGENT and intent.want != "water":
        intent.want, intent.want_rate = "water", fallback["want_per_tick"]


def _stance(value: object) -> Stance:
    text = str(value).strip().lower()
    try:
        return Stance(text)
    except ValueError:
        return STANCE_ALIASES.get(text, Stance.IGNORE)


def _resource(value: object) -> str | None:
    text = str(value).strip().lower()
    return text if text in RESOURCES else None


def _number(value: object, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(low, min(high, number))
