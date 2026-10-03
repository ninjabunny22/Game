"""Turns a proposed tech (from a civ's strategic layer) into a real, bounded Tech.

The proposer only chooses a name, up to two effects from the shared effects
vocabulary and which materials the tech consumes. This module clamps every
effect to the caps in data/invention.json and sets the price itself, so a
proposal can never be stronger or cheaper than the rules allow.
"""

import re
from dataclasses import dataclass

from ..datafiles import load_json
from ..economy.rules import RESOURCES
from .tree import Tech, TechTree

# Effect types a proposal may use -> how they read in a description.
EFFECT_LABELS = {
    "yield_mult": "{amount:+.0%} {resource}",
    "income": "{amount:+.2f} {resource} per tick",
    "housing": "{amount:+.0f} housing",
    "storage": "{amount:+.0f} storage for every resource",
    "science_mult": "{amount:+.0%} science",
    "build_speed": "{amount:+.0%} construction speed",
    "growth": "{amount:+.0%} population growth",
    "expand_cost": "{amount:+.0%} territory expansion cost",
    "military": "{amount:+.0%} army strength",
    "defense": "{amount:+.0%} defence",
}
NEEDS_RESOURCE = ("yield_mult", "income")
DEFAULT_MATERIALS = ("wood", "stone")
MAX_NAME_LENGTH = 40
MAX_FLAVOUR_LENGTH = 120


@dataclass(frozen=True)
class InventionRules:
    era_name: str
    max_effects: int
    min_fraction: float  # an effect is at least this share of its cap, so it is never a no-op
    base_science: float
    base_material: float
    cost_growth: float  # each tech a civ has already invented makes the next this much dearer
    caps: dict[str, float]

    @classmethod
    def load(cls) -> "InventionRules":
        raw = load_json("invention.json")
        return cls(**{key: value for key, value in raw.items() if not key.startswith("_")})

    def cap(self, effect_type: str, resource: str | None) -> float:
        if effect_type == "yield_mult" and resource == "all":
            return self.caps["yield_mult_all"]
        return self.caps[effect_type]

    def science_cost(self, already_invented: int, points: float = 1.0) -> int:
        scale = self.cost_growth**already_invented * (0.6 + 0.4 * points)
        return int(round(self.base_science * scale, -1))


def build_invented_tech(proposal: object, civ, tree: TechTree, rules: InventionRules,
                        storage: dict[str, float]) -> Tech | None:
    """Validate, clamp and price a proposal. None if nothing usable is left of it."""
    if not isinstance(proposal, dict):
        return None
    effects, points, summary = _clamp_effects(proposal.get("effects"), rules)
    if not effects:
        return None

    already = len(tree.invented_by(civ.id))
    growth = rules.cost_growth**already
    materials = _valid_materials(proposal.get("materials"), civ)
    per_material = round(rules.base_material * growth * points / len(materials))
    cost: dict[str, float] = {"science": rules.science_cost(already, points)}
    for res in materials:
        cost[res] = min(per_material, int(0.8 * storage[res]))  # must fit in what the civ can hold

    name = _unique_name(_clean(proposal.get("name"), MAX_NAME_LENGTH) or "Untitled Discovery", tree)
    flavour = _clean(proposal.get("description"), MAX_FLAVOUR_LENGTH)
    description = "; ".join(summary) + (f". {flavour}" if flavour else "")
    # Builds on the most advanced things the civ knows.
    top_era = max((tree.techs[t].era for t in civ.known_techs), default=0)
    prereqs = tuple(t for t in civ.known_techs if tree.techs[t].era == top_era)[-2:]
    return Tech(
        id=f"inv_{civ.id}_{already + 1}",
        name=name,
        era=_invention_era(tree, rules),
        prereqs=prereqs,
        cost=cost,
        effects=effects,
        description=description,
        owner=civ.id,
    )


def _invention_era(tree: TechTree, rules: InventionRules) -> int:
    return tree.eras.index(rules.era_name) if rules.era_name in tree.eras else len(tree.eras)


def _clamp_effects(raw: object, rules: InventionRules) -> tuple[dict, float, list[str]]:
    """Effects dict in the shared vocabulary, their total size in 'points' (1 = one capped effect), labels."""
    effects: dict = {}
    points = 0.0
    summary: list[str] = []
    seen: set[tuple[str, str | None]] = set()
    for item in raw if isinstance(raw, list) else []:
        if len(seen) >= rules.max_effects or not isinstance(item, dict):
            continue
        effect_type = str(item.get("type", "")).strip().lower()
        if effect_type not in EFFECT_LABELS:
            continue
        resource = None
        if effect_type in NEEDS_RESOURCE:
            resource = str(item.get("resource", "")).strip().lower()
            if resource not in RESOURCES and not (effect_type == "yield_mult" and resource == "all"):
                continue
        if (effect_type, resource) in seen:
            continue
        try:
            amount = abs(float(item.get("amount")))
        except (TypeError, ValueError):
            continue
        if amount != amount:  # NaN
            continue
        cap = rules.cap(effect_type, resource)
        amount = round(max(rules.min_fraction * cap, min(cap, amount)), 3)
        seen.add((effect_type, resource))
        points += amount / cap
        signed = -amount if effect_type == "expand_cost" else amount
        if resource:
            effects.setdefault(effect_type, {})[resource] = signed
        else:
            effects[effect_type] = signed
        summary.append(EFFECT_LABELS[effect_type].format(
            amount=signed, resource="all yields" if resource == "all" else resource))
    return effects, points, summary


def _valid_materials(raw: object, civ) -> list[str]:
    """Up to two distinct resources the civ can actually obtain."""
    def obtainable(res: str) -> bool:
        return civ.capacity[res] > 0 or civ.imports[res] > 0 or civ.resources[res] > 0 or res == "gold"

    chosen: list[str] = []
    for res in list(raw if isinstance(raw, list) else []) + list(DEFAULT_MATERIALS):
        res = str(res).strip().lower()
        if res in RESOURCES and res != "food" and res not in chosen and obtainable(res):
            chosen.append(res)
        if len(chosen) == 2:
            break
    return chosen or ["gold"]


def _clean(text: object, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[^\w\s\-',.:!?()]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:limit].strip()


def _unique_name(name: str, tree: TechTree) -> str:
    taken = {tech.name.lower() for tech in tree.techs.values()}
    candidate, suffix = name, 2
    while candidate.lower() in taken:
        candidate = f"{name} {suffix}"
        suffix += 1
    return candidate
