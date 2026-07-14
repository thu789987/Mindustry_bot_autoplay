import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.planner import plan_split
from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

# 1 drill than, tách làm 2 nhánh tới 2 core khác nhau (thay vì core+nhà máy
# để phép đo bảo toàn khối lượng rõ ràng: core_a + core_b phải xấp xỉ đúng
# bằng sản lượng drill, KHÔNG được là 2x sản lượng drill).
grid = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid.set_ore(x, y, "coal")

drill = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
core_a = grid.place(CATALOG["core"], 20, 2, rotation=0)
core_b = grid.place(CATALOG["core"], 20, 15, rotation=0)

actions = plan_split(grid, drill, [core_a.footprint(), core_b.footprint()])
print(f"plan_split() -> {len(actions)} action(s):")
for a in actions:
    print(f"  {a}")

result = evaluate_layout(grid)
drill_rate = result["output_rate"][drill]
rate_a = result["output_rate"][core_a]
rate_b = result["output_rate"][core_b]
total = rate_a + rate_b

print(f"\ndrill sản xuất:     {drill_rate:.4f}/s")
print(f"core_a nhận:        {rate_a:.4f}/s")
print(f"core_b nhận:        {rate_b:.4f}/s")
print(f"tổng 2 nhánh:       {total:.4f}/s")

if abs(total - drill_rate) < 0.01 and rate_a > 0 and rate_b > 0:
    print("\nXÁC NHẬN: cả 2 nhánh đều nhận được hàng, tổng 2 nhánh khớp đúng sản")
    print("lượng drill (bảo toàn khối lượng) -- không tự nhân đôi.")
else:
    print("\nSAI: không bảo toàn khối lượng hoặc 1 nhánh không nhận được gì.")
