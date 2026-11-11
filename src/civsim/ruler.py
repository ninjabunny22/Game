"""A human ruler for one civ.

The ruler sets policy and the civ carries it out: who to trade with, befriend or attack
and how hard, what the realm concentrates on, what to research next and what to build
next. Everything the ruler leaves alone is still decided by the civ's own AI and the
strategist, so a civ can be ruled as closely or as loosely as wanted, or handed back.
"""

from dataclasses import replace

from .civ.personality import Personality
from .strategy import parse_stances, stance_context

# What each focus does to the weights the civ's AI plans by.
FOCUSES = {
    "balanced": {},
    "growth": {"growth": 1.6, "food": 1.4},
    "economy": {"wealth": 1.6, "industry": 1.4, "infrastructure": 1.2},
    "military": {"military": 1.8},
    "science": {"science": 1.8},
    "expansion": {"expansion": 1.8},
}
STANCES = ("trade", "ally", "aggression", "ignore")
COMMANDS = ("take_control", "release_control", "set_stance", "set_focus", "set_research", "set_build")


class Ruler:
    def __init__(self, sim):
        self.sim = sim
        self.civ_id: int | None = None
        self.focus = "balanced"
        self.stances: dict[int, dict] = {}  # other civ id -> {"stance", "commitment"}; absent = left to the strategist
        self._born: Personality | None = None  # the civ's own personality, to give back

    @property
    def civ(self):
        return self.sim.civs[self.civ_id] if self.civ_id is not None else None

    # -- commands ------------------------------------------------------------

    def command(self, action: str, value) -> str | None:
        """Carry out one command from the player. Returns what was wrong with it, or None."""
        value = value if isinstance(value, dict) else {}
        if action == "take_control":
            return self._take(value.get("civ"))
        if action == "release_control":
            self._release()
            return None
        civ = self.civ
        if civ is None or not civ.alive:
            return "no civ is being ruled"
        if action == "set_focus":
            if value.get("focus") not in FOCUSES:
                return f"focus must be one of {', '.join(FOCUSES)}"
            self._set_focus(value["focus"])
        elif action == "set_stance":
            other = value.get("civ")
            if not isinstance(other, int) or other == civ.id or not 0 <= other < len(self.sim.civs):
                return "no such civ"
            stance = value.get("stance")
            if stance == "auto":
                self.stances.pop(other, None)
            elif stance in STANCES:
                commitment = value.get("commitment", 0.7)
                commitment = commitment if isinstance(commitment, (int, float)) and not isinstance(commitment, bool) else 0.7
                self.stances[other] = {"stance": stance, "commitment": max(0.1, min(1.0, float(commitment)))}
                self._apply_stances()
            else:
                return f"stance must be auto or one of {', '.join(STANCES)}"
        elif action == "set_research":
            tech = value.get("tech")
            if tech is not None and tech not in {t.id for t in self.sim.tech_tree.available(civ.known_techs)}:
                return "that cannot be researched yet"
            civ.research_order = tech
        elif action == "set_build":
            building = value.get("building")
            if building is not None and building not in self._buildable(civ):
                return "that cannot be built"
            civ.build_order = building
        return None

    def _take(self, civ_id) -> str | None:
        if not isinstance(civ_id, int) or isinstance(civ_id, bool) or not 0 <= civ_id < len(self.sim.civs):
            return "no such civ"
        if not self.sim.civs[civ_id].alive:
            return "that civ is no more"
        self._release()
        self.civ_id = civ_id
        self._born = self.sim.civs[civ_id].personality
        return None

    def _release(self) -> None:
        civ = self.civ
        if civ is not None:
            civ.personality = self._born
            civ.research_order = civ.build_order = None
        self.civ_id, self._born, self.focus, self.stances = None, None, "balanced", {}

    def _set_focus(self, focus: str) -> None:
        self.focus = focus
        weights = {key: round(value * FOCUSES[focus].get(key, 1.0), 3) for key, value in self._born.weights.items()}
        self.civ.personality = replace(self._born, weights=weights)

    # -- stances -------------------------------------------------------------

    def overrule(self, civ_id: int, context: dict, intents: dict) -> dict:
        """The strategist's intents for a civ, with the ruler's own stances put over them."""
        if civ_id != self.civ_id or not self.stances:
            return intents
        ordered, _ = parse_stances(self._reply(context), context, self.sim.tick)
        return {**intents, **ordered}

    def _apply_stances(self) -> None:
        """Put the ruler's stances in force now, without waiting for the next check-in."""
        context = stance_context(self.sim, self.civ)
        ordered, _ = parse_stances(self._reply(context), context, self.sim.tick)
        self.sim.diplomacy.set_intents(self.civ_id, ordered)
        self.civ.last_reason = "By the ruler's order."

    def _reply(self, context: dict) -> dict:
        names = {n["id"]: n["name"] for n in context["neighbors"]}
        return {"stances": [
            {"civ": names[other], "stance": order["stance"], "troop_commitment": order["commitment"]}
            for other, order in self.stances.items() if other in names
        ]}

    # -- what the player is shown ----------------------------------------------

    def _buildable(self, civ) -> list[str]:
        return [bdef.id for bdef in self.sim.building_defs.values()
                if (not bdef.requires_tech or bdef.requires_tech in civ.known_techs)
                and (bdef.max_count is None or civ.count(bdef.id) < bdef.max_count)]

    def state(self) -> dict | None:
        civ = self.civ
        if civ is None:
            return None
        if not civ.alive:
            return {"civ": civ.id, "alive": False}
        tree = self.sim.tech_tree
        return {
            "civ": civ.id, "alive": True, "focus": self.focus, "focuses": list(FOCUSES),
            "stances": {str(other): order for other, order in self.stances.items()},
            "research_order": civ.research_order,
            "research_options": [{"id": t.id, "name": t.name} for t in tree.available(civ.known_techs)],
            "build_order": civ.build_order,
            "build_options": [{"id": b, "name": self.sim.building_defs[b].name} for b in self._buildable(civ)],
        }
