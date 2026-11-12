"""The drawn maps. Each module's `blueprint()` draws one; `civsim.mapmaker bake` builds it into
civsim/data/maps, which is what games are played on."""

from importlib import import_module

DESIGNS = ["gilded_isle", "confluence", "highgate", "tidewalk_isles", "emberwaste", "the_divide", "five_gates", "long_march", "narrow_sea"]


def blueprint(map_id: str):
    if map_id not in DESIGNS:
        raise KeyError(f"no drawn map called {map_id!r}")
    return import_module(f"{__name__}.{map_id}").blueprint()
