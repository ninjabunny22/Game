from dataclasses import dataclass, field

from ..datafiles import load_json


@dataclass(frozen=True)
class Tech:
    id: str
    name: str
    era: int
    prereqs: tuple[str, ...]
    cost: dict[str, float]  # "science" plus material resources
    effects: dict = field(default_factory=dict)
    description: str = ""

    @property
    def science_cost(self) -> float:
        return self.cost.get("science", 0)

    @property
    def materials(self) -> dict[str, float]:
        return {res: amount for res, amount in self.cost.items() if res != "science"}


class TechTree:
    def __init__(self, eras: list[str], techs: list[Tech]):
        self.eras = eras
        self.techs = {tech.id: tech for tech in techs}
        self._validate()

    @classmethod
    def load(cls) -> "TechTree":
        raw = load_json("techs.json")
        techs = [Tech(**{**entry, "prereqs": tuple(entry["prereqs"])}) for entry in raw["techs"]]
        return cls(raw["eras"], techs)

    def available(self, known: list[str]) -> list[Tech]:
        """Techs not yet known whose prerequisites are all known."""
        have = set(known)
        return [t for t in self.techs.values() if t.id not in have and have.issuperset(t.prereqs)]

    def era_of(self, known: list[str]) -> int:
        return max((self.techs[tech_id].era for tech_id in known), default=0)

    def _validate(self) -> None:
        for tech in self.techs.values():
            if not 0 <= tech.era < len(self.eras):
                raise ValueError(f"{tech.id}: era {tech.era} out of range")
            for prereq in tech.prereqs:
                if prereq not in self.techs:
                    raise ValueError(f"{tech.id}: unknown prerequisite {prereq}")
                # Prereqs never come from a later era, which also rules out cycles
                # across eras; same-era cycles are caught by the walk below.
                if self.techs[prereq].era > tech.era:
                    raise ValueError(f"{tech.id}: prerequisite {prereq} is from a later era")
        resolved: set[str] = set()
        while len(resolved) < len(self.techs):
            ready = [t.id for t in self.techs.values() if t.id not in resolved and resolved.issuperset(t.prereqs)]
            if not ready:
                raise ValueError("tech tree contains a prerequisite cycle")
            resolved.update(ready)
