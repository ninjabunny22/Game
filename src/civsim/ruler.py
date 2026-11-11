"""A human ruler for one civ.

The ruler sets policy and the civ carries it out: who to trade with, befriend or attack
and how hard, what the realm concentrates on, what to research next and what to build
next. Everything the ruler leaves alone is still decided by the civ's own AI and the
strategist, so a civ can be ruled as closely or as loosely as wanted, or handed back.
"""

from .civ.personality import FOCUSES, with_focus
from .diplomacy import rules
from .diplomacy.model import FRIENDLY, Stance
from .strategy import parse_stances, stance_context

STANCES = ("trade", "ally", "aggression", "ignore")
COMMANDS = ("take_control", "release_control", "set_stance", "set_focus", "set_research", "set_build",
            "answer_proposal")
PROPOSALS = {"alliance": "ally", "trade": "trade", "peace": "ignore"}  # what saying yes to each means
PROPOSAL_REST = 300  # ticks before a civ that was refused asks the same thing again


class Ruler:
    def __init__(self, sim):
        self.sim = sim
        self.civ_id: int | None = None
        self.focus = "balanced"
        self.stances: dict[int, dict] = {}  # other civ id -> {"stance", "commitment"}; absent = left to the strategist
        self.refused: dict[tuple[int, str], int] = {}  # (civ, kind of proposal) -> tick until which it is not put again
        self._put: set[tuple[int, str]] = set()  # proposals already announced

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
        elif action == "answer_proposal":
            offer = next((p for p in self.proposals()
                          if p["civ"] == value.get("civ") and p["kind"] == value.get("kind")), None)
            if offer is None:
                return "no such proposal is on the table"
            if value.get("accept") is True:
                self.stances[offer["civ"]] = {"stance": PROPOSALS[offer["kind"]], "commitment": 0.7}
                self._apply_stances()
            else:
                self.refused[(offer["civ"], offer["kind"])] = self.sim.tick + PROPOSAL_REST
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
        self.sim.diplomacy.player = civ_id
        self._set_focus("balanced")  # whatever the strategist had it concentrating on, the ruler starts afresh
        return None

    def _release(self) -> None:
        civ = self.civ
        if civ is not None:
            self._set_focus("balanced")
            civ.research_order = civ.build_order = None
        self.civ_id, self.focus, self.stances = None, "balanced", {}
        self.refused, self._put = {}, set()
        self.sim.diplomacy.player = None

    def _set_focus(self, focus: str) -> None:
        self.focus = focus
        civ = self.civ
        civ.born = civ.born or civ.personality
        civ.focus = focus
        civ.personality = with_focus(civ.born, focus)

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

    # -- what the other civs ask of the player ---------------------------------

    def proposals(self) -> list[dict]:
        """What other civs are asking of the ruled civ right now: an alliance, a trade, or peace.
        Each stands until the player answers it or the other civ changes its mind."""
        civ = self.civ
        if civ is None or not civ.alive:
            return []
        sim, diplomacy = self.sim, self.sim.diplomacy
        out = []
        for other_id in diplomacy.others(civ.id):
            other = sim.civs[other_id]
            if not other.alive:
                continue
            relation = diplomacy.relation(civ.id, other_id)
            theirs, mine = diplomacy.intent(other_id, civ.id), diplomacy.intent(civ.id, other_id)
            kind = text = None
            if relation.status == "war":
                war = relation.war
                if (sim.tick - war.start >= rules.MIN_WAR and war.guardian is None
                        and theirs.stance is not Stance.AGGRESSION and mine.stance is Stance.AGGRESSION):
                    kind, text = "peace", f"{other.name} sues for peace"
                    if diplomacy.ahead(war) == civ.id:
                        text += " and will pay tribute"
                    elif diplomacy.ahead(war) == other_id:
                        text += ", but you would pay tribute"
            elif relation.status == "peace" and sim.tick >= relation.truce_until:
                if theirs.stance is Stance.ALLY and mine.stance is not Stance.ALLY:
                    kind, text = "alliance", f"{other.name} proposes an alliance"
                elif (theirs.stance is Stance.TRADE and theirs.give and mine.stance not in FRIENDLY
                      and other_id not in self.stances  # an order already given is not second-guessed
                      and diplomacy.deal_between(civ.id, other_id) is None):
                    kind = "trade"
                    text = f"{other.name} offers {theirs.give}" + (f" for {theirs.want}" if theirs.want else "")
            if kind and sim.tick >= self.refused.get((other_id, kind), 0):
                out.append({"civ": other_id, "kind": kind, "text": text})
        return out

    def notices(self) -> list[dict]:
        """Events for proposals that have just been put, so the player hears of them."""
        standing = {(p["civ"], p["kind"]): p for p in self.proposals()}
        fresh = [p for key, p in standing.items() if key not in self._put]
        self._put = set(standing)
        return [{"civ": p["civ"], "kind": "diplomacy", "text": p["text"] + " (answer in the ruler's panel)"}
                for p in fresh]

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
            "proposals": self.proposals(),
            "research_order": civ.research_order,
            "research_options": [{"id": t.id, "name": t.name} for t in tree.available(civ.known_techs)],
            "build_order": civ.build_order,
            "build_options": [{"id": b, "name": self.sim.building_defs[b].name} for b in self._buildable(civ)],
        }
