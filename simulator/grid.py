from dataclasses import dataclass
from typing import Optional

from .buildings import DIRECTIONS, BuildingType


@dataclass
class Tile:
    # real Mindustry ore tiles are binary (present or not) -- no density/amount
    ore: Optional[str] = None
    buildable: bool = True


@dataclass(eq=False)
class PlacedBuilding:
    # eq=False keeps identity-based __hash__/__eq__: each placed building is
    # a distinct graph node even if another has identical field values, and
    # sim.py relies on hashing building instances as dict keys.
    type: BuildingType
    x: int
    y: int
    rotation: int = 0        # facing/output direction, see DIRECTIONS
    ore_target: Optional[str] = None  # for drills: which ore type to mine

    def footprint(self):
        s = self.type.size
        return [(self.x + dx, self.y + dy) for dx in range(s) for dy in range(s)]

    def _edge_tile(self, direction):
        dx, dy = DIRECTIONS[direction]
        s = self.type.size
        mid = s // 2
        if dx == 1:
            return self.x + s, self.y + mid
        if dx == -1:
            return self.x - 1, self.y + mid
        if dy == 1:
            return self.x + mid, self.y + s
        return self.x + mid, self.y - 1

    def output_tile(self):
        return self._edge_tile(self.rotation)


class Grid:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.tiles = [[Tile() for _ in range(width)] for _ in range(height)]
        self._by_tile: dict[tuple[int, int], PlacedBuilding] = {}

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def set_ore(self, x, y, ore):
        self.tiles[y][x].ore = ore

    def building_at(self, x, y):
        return self._by_tile.get((x, y))

    def unique_buildings(self):
        seen = set()
        result = []
        for b in self._by_tile.values():
            if id(b) not in seen:
                seen.add(id(b))
                result.append(b)
        return result

    def can_place(self, building_type: BuildingType, x, y):
        s = building_type.size
        for dx in range(s):
            for dy in range(s):
                tx, ty = x + dx, y + dy
                if not self.in_bounds(tx, ty):
                    return False
                if not self.tiles[ty][tx].buildable:
                    return False
                if (tx, ty) in self._by_tile:
                    return False
        return True

    def place(self, building_type: BuildingType, x, y, rotation=0, ore_target=None):
        if not self.can_place(building_type, x, y):
            raise ValueError(f"cannot place {building_type.name} at ({x},{y})")
        building = PlacedBuilding(building_type, x, y, rotation, ore_target)
        for tx, ty in building.footprint():
            self._by_tile[(tx, ty)] = building
        return building

    def remove(self, building: PlacedBuilding):
        for tx, ty in building.footprint():
            if self._by_tile.get((tx, ty)) is building:
                del self._by_tile[(tx, ty)]
