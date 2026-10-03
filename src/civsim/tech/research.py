from .tree import TechTree


def advance_research(civ, tree: TechTree, events: list) -> None:
    """Pay the material cost once affordable, then complete when enough science is banked."""
    research = civ.research
    if research is None:
        return
    tech = tree.techs[research.tech_id]
    if not research.paid:
        if not civ.can_afford(tech.materials):
            return
        civ.pay(tech.materials)
        research.paid = True
    if civ.science >= tech.science_cost:
        civ.science -= tech.science_cost
        previous_era = tree.era_of(civ.known_techs)
        civ.known_techs.append(tech.id)
        civ.research = None
        events.append({"civ": civ.id, "kind": "tech", "text": f"{civ.name} discovered {tech.name}"})
        era = tree.era_of(civ.known_techs)
        if era > previous_era:
            events.append({"civ": civ.id, "kind": "era", "text": f"{civ.name} entered the {tree.eras[era]} era"})
