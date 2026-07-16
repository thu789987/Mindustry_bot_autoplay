"""Reconstructs a simulator.grid.Grid from a JSON state snapshot.

This defines the data contract the Mindustry mod will eventually have to
produce (Giai đoạn 2 in NEXT_STEPS.md). Until the mod exists, callers pass
hand-written JSON (see bot/example_run.py) to exercise the rest of the
pipeline.

Expected shape:
{
  "width": 40, "height": 30,
  "ore_tiles": [{"x": 10, "y": 12, "ore": "coal"}, ...],
  "liquid_tiles": [{"x": 5, "y": 5, "liquid": "water"}, ...],
  "attribute_tiles": [{"x": 3, "y": 3, "attribute": "sand"}, ...],
  "buildings": [
    {"type": "mechanical-drill", "x": 10, "y": 12, "rotation": 0, "ore_target": "coal"},
    {"type": "mechanical-pump", "x": 5, "y": 5, "rotation": 0, "liquid_target": "water"},
    {"type": "sorter", "x": 8, "y": 8, "rotation": 0, "filter_item": "coal"},
    {"type": "conveyor", "x": 12, "y": 12, "rotation": 0},
    {"type": "bridge-conveyor", "x": 20, "y": 12, "rotation": 0, "link_to": {"x": 25, "y": 12}}
  ]
}

`link_to` (bridge/mass-driver only): toạ độ góc dưới-trái của building đích
đã đặt trước đó trong cùng mảng `buildings` -- xử lý ở lượt 2 sau khi mọi
building đã được `place()`, vì cần building đích đã tồn tại để trỏ tới
(xem ItemBridge.java/MassDriver.java `link`, đây là 1 tham chiếu 2 chiều
giữa 2 building, không phải hướng belt thường)."""

from simulator.buildings import CATALOG
from simulator.grid import Grid


def grid_from_state(data: dict) -> Grid:
    grid = Grid(width=data["width"], height=data["height"])

    for tile in data.get("ore_tiles", []):
        grid.set_ore(tile["x"], tile["y"], tile["ore"])

    for tile in data.get("liquid_tiles", []):
        grid.set_liquid(tile["x"], tile["y"], tile["liquid"])

    for tile in data.get("attribute_tiles", []):
        grid.set_attribute(tile["x"], tile["y"], tile["attribute"])

    placed = []
    for b in data.get("buildings", []):
        building_type = CATALOG[b["type"]]
        building = grid.place(
            building_type,
            b["x"],
            b["y"],
            rotation=b.get("rotation", 0),
            ore_target=b.get("ore_target"),
            liquid_target=b.get("liquid_target"),
            filter_item=b.get("filter_item"),
        )
        placed.append((building, b.get("link_to")))

    # Lượt 2: resolve link_to sau khi mọi building đã place() xong (bridge có
    # thể trỏ tới 1 building đứng SAU nó trong mảng JSON).
    for building, link_to in placed:
        if link_to is not None:
            building.link_target = grid.building_at(link_to["x"], link_to["y"])

    return grid
