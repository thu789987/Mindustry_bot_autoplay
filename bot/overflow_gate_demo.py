import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout


def build_scene(gate_name):
    """1 drill than -> gate -> (thẳng: core_straight, rẽ: core_side)."""
    grid = Grid(width=30, height=20)
    for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
        grid.set_ore(x, y, "coal")
    drill = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
    grid.place(CATALOG["conveyor"], 4, 3, rotation=0)
    grid.place(CATALOG[gate_name], 5, 3)
    grid.place(CATALOG["conveyor"], 6, 3, rotation=0)
    core_straight = grid.place(CATALOG["core"], 7, 3)
    # cạnh bên NGAY SÁT gate (dir_in=đông -> 2 bên là nam/bắc): overflow-gate
    # chỉ nhìn hàng xóm trực tiếp lúc quyết định rẽ, không truy theo cả
    # đường dài như nhánh thẳng (khớp OverflowGate.java getTileTarget()
    # dùng nearby(), chỉ xét 1 ô kề).
    core_side = grid.place(CATALOG["core"], 3, 4)  # footprint (3,4)-(5,6): chứa ô (5,4) kề gate
    return grid, core_straight, core_side


print("=== Kịch bản 1: overflow-gate -- có đường thẳng -> phải đi THẲNG (xấp xỉ tất định) ===")
grid1, straight1, side1 = build_scene("overflow-gate")
r1 = evaluate_layout(grid1)
print(f"  core_straight nhận: {r1['output_rate'][straight1]:.4f}/s")
print(f"  core_side nhận:     {r1['output_rate'][side1]:.4f}/s")
assert r1["output_rate"][straight1] > 0 and r1["output_rate"][side1] == 0, "SAI: overflow-gate có đường thẳng phải ưu tiên đi thẳng"
print("  ĐÚNG: overflow-gate ưu tiên đường thẳng khi có sẵn.\n")

print("=== Kịch bản 2: underflow-gate (invert=True) -- có đường thẳng nhưng vẫn RẼ trước ===")
grid2, straight2, side2 = build_scene("underflow-gate")
r2 = evaluate_layout(grid2)
print(f"  core_straight nhận: {r2['output_rate'][straight2]:.4f}/s")
print(f"  core_side nhận:     {r2['output_rate'][side2]:.4f}/s")
assert r2["output_rate"][straight2] == 0 and r2["output_rate"][side2] > 0, "SAI: underflow-gate phải ưu tiên rẽ trước khi có đường bên"
print("  ĐÚNG: underflow-gate (invert=True) ưu tiên rẽ trước, đúng ngược overflow-gate.")
print("\nGhi chú: OverflowGate.java thật quyết định ĐỘNG lúc runtime (dựa vào")
print("mức đầy của đích), simulator này xấp xỉ TẤT ĐỊNH tại thời điểm lập kế")
print("hoạch (luôn ưu tiên 1 phía cố định) -- xem NEXT_STEPS.md.")
