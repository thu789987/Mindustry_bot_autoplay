import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.planner import plan_filter_split
from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout


def build_scene(filter_item):
    """1 drill than, 1 sorter lọc `filter_item`, nhánh thẳng -> core_straight,
    nhánh rẽ -> core_side. Dựng lại từ đầu mỗi lần để 2 kịch bản độc lập."""
    grid = Grid(width=30, height=20)
    for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
        grid.set_ore(x, y, "coal")
    drill = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
    core_straight = grid.place(CATALOG["core"], 20, 2, rotation=0)
    core_side = grid.place(CATALOG["core"], 20, 15, rotation=0)

    plan_filter_split(grid, drill, filter_item, core_straight.footprint(), core_side.footprint())
    return grid, core_straight, core_side


print("=== Kịch bản 1: lọc 'coal' -- drill than SẼ khớp filter -> phải đi THẲNG ===")
grid1, straight1, side1 = build_scene("coal")
result1 = evaluate_layout(grid1)
print(f"  core_straight (nhánh thẳng) nhận: {result1['output_rate'][straight1]:.4f}/s")
print(f"  core_side (nhánh rẽ) nhận:        {result1['output_rate'][side1]:.4f}/s")
assert result1["output_rate"][straight1] > 0 and result1["output_rate"][side1] == 0, "SAI: lẽ ra than phải đi thẳng"
print("  ĐÚNG: than khớp filter -> đi thẳng, nhánh rẽ không nhận gì.\n")

print("=== Kịch bản 2: lọc 'sand' -- drill than KHÔNG khớp filter -> phải RẼ SANG BÊN ===")
grid2, straight2, side2 = build_scene("sand")
result2 = evaluate_layout(grid2)
print(f"  core_straight (nhánh thẳng) nhận: {result2['output_rate'][straight2]:.4f}/s")
print(f"  core_side (nhánh rẽ) nhận:        {result2['output_rate'][side2]:.4f}/s")
assert result2["output_rate"][straight2] == 0 and result2["output_rate"][side2] > 0, "SAI: lẽ ra than phải rẽ sang bên"
print("  ĐÚNG: than không khớp filter ('sand') -> rẽ sang bên, nhánh thẳng không nhận gì.\n")

print("XÁC NHẬN: Sorter hoạt động đúng cơ chế thật -- item khớp filter đi thẳng,")
print("item không khớp rẽ sang bên, không phải chia đều bất kể loại như Router.")

print("\n=== Kịch bản 3: inverted-sorter, lọc 'coal' -- ĐẢO NGƯỢC: khớp filter phải RẼ ===")
grid3 = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid3.set_ore(x, y, "coal")
drill3 = grid3.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid3.place(CATALOG["conveyor"], 4, 3, rotation=0)
grid3.place(CATALOG["inverted-sorter"], 5, 3, rotation=0, filter_item="coal")
grid3.place(CATALOG["conveyor"], 6, 3, rotation=0)
core_straight3 = grid3.place(CATALOG["core"], 7, 3)
core_side3 = grid3.place(CATALOG["core"], 3, 4)
result3 = evaluate_layout(grid3)
print(f"  core_straight nhận: {result3['output_rate'][core_straight3]:.4f}/s")
print(f"  core_side nhận:     {result3['output_rate'][core_side3]:.4f}/s")
assert result3["output_rate"][core_straight3] == 0 and result3["output_rate"][core_side3] > 0, (
    "SAI: inverted-sorter khớp filter phải RẼ (đảo ngược sorter thường), xem Sorter.java `invert`"
)
print("  ĐÚNG: inverted-sorter đảo ngược đúng -- than khớp filter 'coal' nhưng lại RẼ")
print("  thay vì đi thẳng, đúng field `invert` trong Sorter.java thật.")
