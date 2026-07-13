"""Reconstructs a simulator.grid.Grid from a JSON state snapshot.

This defines the data contract the Mindustry mod will eventually have to
produce (Giai đoạn 2 in NEXT_STEPS.md). Until the mod exists, callers pass
hand-written JSON (see bot/example_run.py) to exercise the rest of the
pipeline.

Expected shape:
{
  "width": 40, "height": 30,
  "ore_tiles": [{"x": 10, "y": 12, "ore": "coal"}, ...],
  "buildings": [
    {"type": "mechanical-drill", "x": 10, "y": 12, "rotation": 0, "ore_target": "coal"},
    {"type": "conveyor", "x": 12, "y": 12, "rotation": 0}
  ]
}
"""

from simulator.buildings import CATALOG
from simulator.grid import Grid


def grid_from_state(data: dict) -> Grid:
    grid = Grid(width=data["width"], height=data["height"])

    for tile in data.get("ore_tiles", []):
        grid.set_ore(tile["x"], tile["y"], tile["ore"])

    for b in data.get("buildings", []):
        building_type = CATALOG[b["type"]]
        grid.place(
            building_type,
            b["x"],
            b["y"],
            rotation=b.get("rotation", 0),
            ore_target=b.get("ore_target"),
        )

    return grid
