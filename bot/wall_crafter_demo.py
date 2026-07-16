"""Chứng minh WallCrafter (cliff-crusher/large-cliff-crusher) hoạt động
đúng: chỉ quét dọc CẠNH ĐANG XOAY MẶT TỚI (không phải 4 cạnh như BeamDrill,
không phải diện tích chân đế như Drill), cộng dồn hiệu suất từ ô đá/tường
tự nhiên mang đúng `wall_attribute` -- xem sim.py _wall_crafter_output_rate.

Bố cục: cliff-crusher (size=2) đặt tại (5,5), rotation=2 (xoay mặt hướng
TÂY, xem simulator.buildings DIRECTIONS: 0=Đông,1=Nam,2=Tây,3=Bắc) ->
output_tile() = (4,6) (xem grid.py _edge_tile). Core đặt sát ngay
output_tile để không cần belt trung gian.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

CC = CATALOG["cliff-crusher"]  # size=2, drill_time=110, wall_attribute="sand" -> "sand"

print(f"=== cliff-crusher: size={CC.size}, drill_time={CC.drill_time}, "
      f"attribute={CC.wall_attribute!r} -> output={CC.wall_output!r} ===\n")


def build(attr_a, attr_b, x_a=4, y_a=5, x_b=4, y_b=6):
    """Dựng layout chuẩn: cliff-crusher tại (5,5) rotation=2 (xoay mặt TÂY),
    2 ô cạnh TÂY (mặc định (4,5),(4,6)) mang attribute chỉ định, core sát
    output_tile()=(4,6)."""
    grid = Grid(width=20, height=20)
    if attr_a is not None:
        grid.set_attribute(x_a, y_a, attr_a)
    if attr_b is not None:
        grid.set_attribute(x_b, y_b, attr_b)
    crafter = grid.place(CC, 5, 5, rotation=2)
    grid.place(CATALOG["conveyor"], 4, 6, rotation=2)  # đúng output_tile(), tiếp tục hướng Tây
    core = grid.place(CATALOG["core"], 0, 5)  # footprint (0,5)-(2,7), chạm belt tại (3,6)
    grid.place(CATALOG["conveyor"], 3, 6, rotation=2)
    return grid, crafter, core


print("--- Kịch bản 1: cả 2 ô cạnh TÂY (hướng xoay mặt) đều có attribute sand -> hiệu suất=2 ---")
grid, crafter, core = build("sand", "sand")
result = evaluate_layout(grid)
expected = 60 / CC.drill_time * 2
print(f"  core nhận: {result['output_rate'][core]:.4f}/s (kỳ vọng {expected:.4f}/s = 60/{CC.drill_time}*2)")
assert abs(result["output_rate"][core] - expected) < 1e-6, "SAI: rate phải = (60/drill_time)*hiệu_suất"
print("  ĐÚNG.\n")

print("--- Kịch bản 2: attribute đặt SAI cạnh (cạnh Đông thay vì Tây đang xoay mặt) -> 0/s ---")
grid2, crafter2, core2 = build(None, None)
grid2.set_attribute(7, 5, "sand")  # cạnh ĐÔNG -- crafter xoay mặt TÂY, không quét tới
grid2.set_attribute(7, 6, "sand")
result2 = evaluate_layout(grid2)
print(f"  core nhận: {result2['output_rate'][core2]:.4f}/s (kỳ vọng 0.0 -- sai cạnh)")
assert result2["output_rate"][core2] == 0.0, "SAI: WallCrafter chỉ quét cạnh ĐANG XOAY MẶT TỚI, không phải mọi cạnh"
print("  ĐÚNG: khác BeamDrill (quét cả 4 cạnh), WallCrafter chỉ quét đúng 1 cạnh.\n")

print("--- Kịch bản 3: attribute SAI loại (oil thay vì sand) -> không tính ---")
grid3, crafter3, core3 = build("oil", "oil")
result3 = evaluate_layout(grid3)
print(f"  core nhận: {result3['output_rate'][core3]:.4f}/s (kỳ vọng 0.0 -- sai loại attribute)")
assert result3["output_rate"][core3] == 0.0, "SAI: attribute khác loại yêu cầu không được tính"
print("  ĐÚNG.\n")

print("--- Kịch bản 4: chỉ 1/2 ô cạnh Tây có attribute -> hiệu suất=1 (một nửa) ---")
grid4, crafter4, core4 = build("sand", None)
result4 = evaluate_layout(grid4)
expected4 = 60 / CC.drill_time * 1
print(f"  core nhận: {result4['output_rate'][core4]:.4f}/s (kỳ vọng {expected4:.4f}/s = 60/{CC.drill_time}*1)")
assert abs(result4["output_rate"][core4] - expected4) < 1e-6, "SAI: hiệu suất phải cộng dồn theo từng ô khớp, không phải tất-cả-hoặc-không"
print("  ĐÚNG.\n")

print("XÁC NHẬN: WallCrafter hoạt động đúng cơ chế thật -- CHỈ quét 1 cạnh (hướng xoay mặt),")
print("cộng dồn hiệu suất theo từng ô khớp attribute, khác hẳn Drill (diện tích chân đế)")
print("và BeamDrill (4 cạnh, ore theo item hardness).")
