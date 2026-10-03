from ..economy.rules import SCIENCE_BANK_CAP
from .tree import TechTree


def advance_research(civ, tree: TechTree, events: list) -> None:
    """Pay the material cost once affordable, then pour science into the tech until it is done.

    Science is spent as it is produced. A civ with nothing to research (or still
    gathering materials) banks a little, up to SCIENCE_BANK_CAP, and no more.
    """
    research = civ.research
    if research is not None:
        tech = tree.techs[research.tech_id]
        if not research.paid and civ.can_afford(tech.materials):
            civ.pay(tech.materials)
            research.paid = True
        if research.paid:
            research.progress += civ.science
            civ.science = 0.0
            if research.progress >= tech.science_cost:
                civ.science = research.progress - tech.science_cost
                previous_era = tree.era_of(civ.known_techs)
                civ.known_techs.append(tech.id)
                civ.research = None
                events.append({"civ": civ.id, "kind": "tech", "text": f"{civ.name} discovered {tech.name}"})
                era = tree.era_of(civ.known_techs)
                if era > previous_era:
                    events.append({"civ": civ.id, "kind": "era",
                                   "text": f"{civ.name} entered the {tree.eras[era]} era"})
    civ.science = min(civ.science, SCIENCE_BANK_CAP)
