"""Villagers: the visible, non-combatant workers of a civ.

A building only advances while a villager is standing on its site building it
(one villager to a building, even where several go up on one tile), so building
far from where the villagers are takes longer. Villagers with no building to do
walk out to work the land (that part is for show: the amounts gathered still
come from the worker allocation). They are never killed; capture converts them.
"""

from collections.abc import Callable

from ..map import WorldMap, find_path
from ..military.army import Villager

POP_PER_VILLAGER = 25
MIN_VILLAGERS = 2
MAX_VILLAGERS = 12


def manage_villagers(civ, world: WorldMap, mods, next_id: Callable[[], int]) -> None:
    """Raise new villagers as the population grows, hand out tasks, and walk everyone one step."""
    wanted = max(MIN_VILLAGERS, min(MAX_VILLAGERS, round(civ.population / POP_PER_VILLAGER)))
    while len(civ.villagers) < wanted:
        civ.villagers.append(Villager(next_id(), civ.capital.tile))

    for building in civ.buildings:
        if building.id == 0:
            building.id = next_id()

    # Builders whose building is finished (or lost) are free again.
    sites = {b.id for b in civ.buildings if not b.complete}
    for villager in civ.villagers:
        if villager.task == "build" and villager.building not in sites:
            _release(villager)

    # Every building under way needs a builder: send the nearest villager not already building.
    under_way = [b for b in civ.buildings if not b.complete][: mods.build_slots]
    for building in under_way:
        if any(v.task == "build" and v.building == building.id for v in civ.villagers):
            continue
        free = [v for v in civ.villagers if v.task != "build"]
        if not free:
            break
        nearest = min(free, key=lambda v: (_distance(world, v.tile, building.tile), v.id))
        _send(nearest, world, mods, "build", building.tile)
        nearest.building = building.id

    # Anyone with nothing to do goes out to work the land.
    for villager in civ.villagers:
        if villager.task == "idle":
            site = _work_site(civ, world, villager)
            if site is not None:
                _send(villager, world, mods, "gather", site)
                villager.gathers = max(civ.workers, key=lambda res: (civ.workers[res], res))

    for villager in civ.villagers:
        for _ in range(1 + mods.villager_speed):
            if villager.path:
                villager.tile = villager.path.pop(0)


def builders_on_site(civ) -> set[int]:
    """Ids of the buildings that have a villager in place and building them."""
    return {v.building for v in civ.villagers if v.task == "build" and v.tile == v.target}


def convert_villagers(tile: int, loser, captor) -> int:
    """Villagers on a captured tile change sides and wait for orders. Returns how many."""
    taken = [v for v in loser.villagers if v.tile == tile]
    for villager in taken:
        loser.villagers.remove(villager)
        _release(villager)
        villager.mounted = False  # the horse is lost; the villager, as ever, is not
        captor.villagers.append(villager)
    return len(taken)


def _release(villager: Villager) -> None:
    villager.task = "idle"
    villager.target = None
    villager.building = 0
    villager.gathers = None
    villager.path = []


def _send(villager: Villager, world: WorldMap, mods, task: str, target: int) -> None:
    path = find_path(world, villager.tile, target, bool(mods.bridges), bool(mods.boats), max_nodes=3000)
    if path is None:
        path = _straight_line(world, villager.tile, target)  # cut off by water: get there anyway, never stuck
    villager.task = task
    villager.target = target
    villager.path = path


def _work_site(civ, world: WorldMap, villager: Villager) -> int | None:
    """A tile worth working for whatever most of the civ's workers are gathering."""
    resource = max(civ.workers, key=lambda res: (civ.workers[res], res))
    taken = {v.target for v in civ.villagers if v.task == "gather"}
    cx, cy = world.xy(civ.capital.tile)
    best, best_key = None, None
    for tile in civ.territory:
        amount = world.yields[tile].get(resource, 0)
        if amount <= 0 or tile in taken:
            continue
        x, y = world.xy(tile)
        key = (-amount, abs(x - cx) + abs(y - cy), tile)
        if best_key is None or key < best_key:
            best, best_key = tile, key
    return best


def _distance(world: WorldMap, a: int, b: int) -> int:
    ax, ay = world.xy(a)
    bx, by = world.xy(b)
    return abs(ax - bx) + abs(ay - by)


def _straight_line(world: WorldMap, start: int, goal: int) -> list[int]:
    x, y = world.xy(start)
    gx, gy = world.xy(goal)
    path = []
    while (x, y) != (gx, gy):
        if abs(gx - x) >= abs(gy - y):
            x += 1 if gx > x else -1
        else:
            y += 1 if gy > y else -1
        path.append(world.idx(x, y))
    return path
