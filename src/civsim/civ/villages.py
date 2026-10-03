"""Villages and towns: named groups of one civ's buildings.

Every capital a civ holds is the centre of its own town. A building joins the
nearest village or town of its civ within VILLAGE_RANGE tiles; if there is none
it founds a new village on its own tile. A town or village that has reached its
size limit takes no more, so growth beyond it founds new villages round about
rather than one settlement swallowing a whole region. A village belongs to whoever holds its
centre tile, so it changes hands whole when that tile is captured; buildings left
behind on either side rejoin the nearest village of the civ that now has them.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

from ..map import WorldMap

VILLAGE_RANGE = 4  # tiles, in any direction
TOWN_CAP = 60  # buildings in the town around a capital
VILLAGE_CAP = 40  # ... and in an ordinary village

VILLAGE_NAMES = (
    "Ashby", "Barrowmere", "Birchholt", "Blackwater", "Bramblewick", "Brackenfold", "Calder", "Chalkpit",
    "Clayford", "Coldharbour", "Copperdown", "Crowmarsh", "Dunmoor", "Eastcombe", "Elderwick", "Fallowfield",
    "Fernhollow", "Foxley", "Gorsefield", "Greenhithe", "Harrowgate", "Hawksworth", "Hazelmere", "Heathrow End",
    "Hollowbeck", "Kestrel Rise", "Larkhill", "Lowmead", "Marlpit", "Mossgate", "Netherby", "Oakhampton",
    "Oldmill", "Otterburn", "Pennywell", "Quarry Bank", "Redcliff", "Reedham", "Rushford", "Saltmarsh",
    "Sandwick", "Sedgebrook", "Shepherd's Lea", "Stonebeck", "Swallowdale", "Thistledown", "Thornwick",
    "Three Oaks", "Tolland", "Upper Wold", "Wainfleet", "Westerleigh", "Whitford", "Willowbank", "Windrush",
    "Wolfscar", "Wrenfield", "Yarrow", "Yewdale", "Longbarrow", "Millbrook", "Highfold", "Deepdene", "Kingsmead",
)


@dataclass
class Village:
    id: int
    name: str
    tile: int  # its centre
    civ: int  # whoever holds the centre tile
    capital: bool = False  # the town around a region capital


class Villages:
    def __init__(self, world: WorldMap, civs: list, next_id: Callable[[], int], seed: int):
        self.world = world
        self.civs = {civ.id: civ for civ in civs}
        self.next_id = next_id
        self.villages: dict[int, Village] = {}
        taken = {region.capital_name for region in world.regions}
        self._names = [name for name in VILLAGE_NAMES if name not in taken]
        random.Random(seed + 4801).shuffle(self._names)
        self._founded = 0

    def of(self, civ_id: int) -> list[Village]:
        return [village for village in self.villages.values() if village.civ == civ_id]

    def size(self, village_id: int) -> int:
        """Buildings in the village, finished or not."""
        village = self.villages[village_id]
        return sum(1 for building in self.civs[village.civ].buildings if building.village == village_id)

    def cap(self, village: Village) -> int:
        return TOWN_CAP if village.capital else VILLAGE_CAP

    def update(self, tick: int, events: list) -> None:
        world = self.world
        living = [civ for civ in self.civs.values() if civ.alive]
        # Every capital a civ holds has a town around it.
        centres = {village.tile for village in self.villages.values()}
        for civ in living:
            for settlement in civ.settlements:
                if settlement.tile not in centres:
                    self._add(Village(self.next_id(), settlement.name, settlement.tile, civ.id, capital=True))

        # A village goes with its centre tile.
        for village in list(self.villages.values()):
            holder = self.civs.get(world.owner[village.tile])
            if holder is None or not holder.alive:
                del self.villages[village.id]
            elif holder.id != village.civ:
                previous = self.civs[village.civ]
                village.civ = holder.id
                if not village.capital:  # a capital changing hands is already announced
                    events.append({"civ": holder.id, "kind": "village",
                                   "text": f"{holder.name} takes the village of {village.name} from {previous.name}"})

        # Every building belongs to a village of its own civ.
        for civ in living:
            mine = self.of(civ.id)
            sizes: dict[int, int] = {}
            for building in civ.buildings:
                current = self.villages.get(building.village)
                if current is not None and current.civ == civ.id:
                    sizes[current.id] = sizes.get(current.id, 0) + 1
            for building in civ.buildings:
                if building.id == 0:
                    building.id = self.next_id()
                current = self.villages.get(building.village)
                if current is not None and current.civ == civ.id:
                    continue
                near = [village for village in mine
                        if self._reach(village.tile, building.tile) <= VILLAGE_RANGE
                        and sizes.get(village.id, 0) < self.cap(village)]
                if near:
                    home = min(near, key=lambda village: (self._reach(village.tile, building.tile), village.id))
                else:
                    home = self._add(Village(self.next_id(), self._new_name(), building.tile, civ.id))
                    mine.append(home)
                    events.append({"civ": civ.id, "kind": "village",
                                   "text": f"{civ.name} founds the village of {home.name}"})
                building.village = home.id
                sizes[home.id] = sizes.get(home.id, 0) + 1

        # A village with nothing left standing is gone; a capital's town remains.
        used = {building.village for civ in living for building in civ.buildings}
        for village in list(self.villages.values()):
            if not village.capital and village.id not in used:
                del self.villages[village.id]

    def _add(self, village: Village) -> Village:
        self.villages[village.id] = village
        return village

    def _new_name(self) -> str:
        index = self._founded
        self._founded += 1
        name = self._names[index % len(self._names)]
        round_ = index // len(self._names)
        return name if round_ == 0 else f"{name} {round_ + 1}"

    def _reach(self, a: int, b: int) -> int:
        ax, ay = self.world.xy(a)
        bx, by = self.world.xy(b)
        return max(abs(ax - bx), abs(ay - by))
