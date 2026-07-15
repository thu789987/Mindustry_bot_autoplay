"""Xác nhận mạng điện thật: building cần điện (power_input>0, vd laser-drill
tier 4) chạy được 0/s nếu KHÔNG có generator trong tầm, và chạy đúng theo
satisfaction=min(1, production/needed) khi có -- xem PowerGraph.java
getSatisfaction() thật, mô phỏng bằng Union-Find range-based trong sim.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

print("=== Kịch bản 1: laser-drill (cần điện) KHÔNG có generator nào trên map -- phải 0/s ===")
grid = Grid(width=20, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid.set_ore(x, y, "titanium")
laser = grid.place(CATALOG["laser-drill"], 2, 2, rotation=0, ore_target="titanium")
result = evaluate_layout(grid)
print(f"  laser-drill output: {result['output_rate'][laser]:.4f}/s (power_input={CATALOG['laser-drill'].power_input}/s)")
assert result["output_rate"][laser] == 0, "SAI: laser-drill không có điện phải cho ra 0/s, không phải chạy như bình thường"
assert result["power_satisfaction"][laser] == 0.0, "SAI: satisfaction phải là 0 khi không có mạng điện nào"
print("  ĐÚNG: laser-drill cần điện thật (Blocks.java consumePower) -- không có nguồn thì KHÔNG chạy,")
print("  dù ore/tier hoàn toàn đủ điều kiện mine -- khác hẳn trước khi có power model (luôn chạy free).\n")

print("=== Kịch bản 2: đặt combustion-generator SÁT laser-drill (chạm trực tiếp) -- phải chạy ===")
grid2 = Grid(width=20, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid2.set_ore(x, y, "titanium")
laser2 = grid2.place(CATALOG["laser-drill"], 2, 2, rotation=0, ore_target="titanium")  # footprint (2,2)-(4,4), size=3
gen2 = grid2.place(CATALOG["combustion-generator"], 5, 3, rotation=0)  # chạm ngay cạnh đông của laser-drill
for x in range(10, 13):
    for y in range(2, 5):
        grid2.set_ore(x, y, "coal")
coal_drill2 = grid2.place(CATALOG["mechanical-drill"], 10, 2, rotation=2, ore_target="coal")
for cx in range(9, 5, -1):
    grid2.place(CATALOG["conveyor"], cx, 3, rotation=2)

result2 = evaluate_layout(grid2)
sat2 = result2["power_satisfaction"].get(laser2, 0.0)
print(f"  laser-drill output: {result2['output_rate'][laser2]:.4f}/s, satisfaction={sat2:.4f}")
print(f"  combustion-generator power_production: {result2['power_production'][gen2]:.2f}")
assert result2["output_rate"][laser2] > 0, "SAI: có generator chạm trực tiếp phải cấp được điện"
print("  ĐÚNG: generator chạm trực tiếp (không cần power-node) vẫn cấp điện được -- khớp")
print("  cơ chế 2 building có điện kề nhau tự bắt tay không dây, không cần node ở giữa.\n")

print("=== Kịch bản 3: generator XA (ngoài tầm, không chạm), có power-node bắc cầu -- phải chạy ===")
grid3 = Grid(width=30, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid3.set_ore(x, y, "titanium")
laser3 = grid3.place(CATALOG["laser-drill"], 2, 2, rotation=0, ore_target="titanium")  # footprint (2,2)-(4,4)
for x in range(14, 17):
    for y in range(2, 5):
        grid3.set_ore(x, y, "coal")
coal_drill3 = grid3.place(CATALOG["mechanical-drill"], 14, 2, rotation=2, ore_target="coal")
gen3 = grid3.place(CATALOG["combustion-generator"], 12, 3, rotation=0)  # cách laser-drill 8 ô, KHÔNG chạm
grid3.place(CATALOG["conveyor"], 13, 3, rotation=2)

result_no_node = evaluate_layout(grid3)
print(f"  CHƯA có power-node: laser-drill output = {result_no_node['output_rate'][laser3]:.4f}/s")
assert result_no_node["output_rate"][laser3] == 0, "SAI: generator ngoài tầm, chưa có node, phải chưa cấp được điện"

# power-node laserRange=6 ô -- đặt tại (8,3): cách mép laser-drill (4,4) ~4.1 ô,
# cách generator (12,3) 4.0 ô, cả 2 đều trong tầm -- kiểm bằng code (assert dưới),
# không đoán khoảng cách.
node3 = grid3.place(CATALOG["power-node"], 8, 3, rotation=0)
result_with_node = evaluate_layout(grid3)
print(f"  CÓ power-node ở (8,3), laserRange={CATALOG['power-node'].power_range}: laser-drill output = {result_with_node['output_rate'][laser3]:.4f}/s")
assert result_with_node["output_rate"][laser3] > 0, "SAI: power-node bắc cầu trong tầm phải cấp được điện"
print("  ĐÚNG: power-node thật sự bắc cầu mạng điện qua khoảng cách xa (không cần belt/")
print("  đường vật lý liên tục như item -- điện là không dây, chỉ cần trong bán kính laserRange).")
