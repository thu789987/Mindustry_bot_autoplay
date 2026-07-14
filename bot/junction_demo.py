import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

# 2 luồng belt VUÔNG GÓC cắt nhau tại đúng 1 ô junction (5,3):
#   drill than  -> belt đông -> JUNCTION -> belt đông -> core_east
#   drill cát   -> belt nam  -> JUNCTION -> belt nam  -> core_south
# Junction.java thật: mỗi hướng vào có buffer riêng, đi THẲNG qua, KHÔNG rẽ,
# KHÔNG trộn -- than phải chỉ tới core_east, cát phải chỉ tới core_south,
# dù cùng đi qua 1 ô junction.
grid = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid.set_ore(x, y, "coal")
for x, y in [(4, 0), (5, 0), (4, 1), (5, 1)]:
    grid.set_ore(x, y, "sand")

drill_coal = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid.place(CATALOG["conveyor"], 4, 3, rotation=0)
junction = grid.place(CATALOG["junction"], 5, 3)
grid.place(CATALOG["conveyor"], 6, 3, rotation=0)
core_east = grid.place(CATALOG["core"], 7, 3)

drill_sand = grid.place(CATALOG["mechanical-drill"], 4, 0, rotation=1, ore_target="sand")
grid.place(CATALOG["conveyor"], 5, 2, rotation=1)
grid.place(CATALOG["conveyor"], 5, 4, rotation=1)
grid.place(CATALOG["conveyor"], 5, 5, rotation=1)
core_south = grid.place(CATALOG["core"], 5, 6)

result = evaluate_layout(grid)

print("=== Junction: 2 luồng vuông góc cắt nhau, không trộn ===")
print(f"  core_east  nhận: {result['output_rate'][core_east]:.4f}/s (phải > 0, chỉ có than)")
print(f"  core_south nhận: {result['output_rate'][core_south]:.4f}/s (phải > 0, chỉ có cát)")

edges = {(src.type.name, dest.type.name if dest.type.kind == "core" else id(dest)) for src, dest, cap in result["connections"]}
print(f"  connections: {[(s.type.name, d.type.name) for s, d, c in result['connections']]}")

assert result["output_rate"][core_east] > 0, "SAI: core_east phải nhận được than"
assert result["output_rate"][core_south] > 0, "SAI: core_south phải nhận được cát"
# Xác nhận đúng NGUỒN nào nối tới ĐÍCH nào (không trộn/lẫn qua junction)
coal_to_east = any(s is drill_coal and d is core_east for s, d, c in result["connections"])
coal_to_south = any(s is drill_coal and d is core_south for s, d, c in result["connections"])
sand_to_south = any(s is drill_sand and d is core_south for s, d, c in result["connections"])
sand_to_east = any(s is drill_sand and d is core_east for s, d, c in result["connections"])
assert coal_to_east and not coal_to_south, "SAI: than phải chỉ nối tới core_east, không được rẽ sang core_south"
assert sand_to_south and not sand_to_east, "SAI: cát phải chỉ nối tới core_south, không được rẽ sang core_east"
print("  ĐÚNG: than chỉ tới core_east, cát chỉ tới core_south -- junction cho 2 luồng")
print("  cắt nhau tại (5,3) mà không trộn, đúng cơ chế Junction.java thật.")
