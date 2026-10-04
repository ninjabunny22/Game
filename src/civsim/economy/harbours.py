"""Where a civ can take ship: open water is only ever entered from land near a working harbour."""

from ..map import WorldMap

HARBOUR_REACH = 3  # ships can be boarded from land within this many tiles of a working harbour


def ports(civ, world: WorldMap) -> set[int]:
    """Land tiles from which the civ's armies and villagers can take ship: those within HARBOUR_REACH
    tiles of one of its working harbours."""
    tiles: set[int] = set()
    for building in civ.buildings:
        if building.type != "harbour" or not building.complete or not building.active:
            continue
        hx, hy = world.xy(building.tile)
        for y in range(max(0, hy - HARBOUR_REACH), min(world.height, hy + HARBOUR_REACH + 1)):
            for x in range(max(0, hx - HARBOUR_REACH), min(world.width, hx + HARBOUR_REACH + 1)):
                tile = world.idx(x, y)
                if not world.is_open_water(tile):
                    tiles.add(tile)
    return tiles
