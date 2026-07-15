"""Trả lời câu hỏi thật: "xây nhà máy điện có đầu vào là than và nước" =
steam-generator (ConsumeGenerator.java thật: đốt BẤT KỲ item flammability >=
0.2, than=1.0 cao nhất -- không phải input cố định như factory thường, xem
NEXT_STEPS.md). Kịch bản: than tới bằng belt, nước tới bằng conduit."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

print("=== Kịch bản 1: steam-generator, than + nước đều có, nhưng than KHÔNG đủ đốt hết công suất ===")
grid = Grid(width=20, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid.set_ore(x, y, "coal")
drill = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid.place(CATALOG["conveyor"], 4, 3, rotation=0)
steam = grid.place(CATALOG["steam-generator"], 6, 2, rotation=0)
grid.place(CATALOG["conveyor"], 5, 3, rotation=0)

for x in range(2, 5):
    grid.set_liquid(x, 8, "water")
pump = grid.place(CATALOG["mechanical-pump"], 2, 8, rotation=3, liquid_target="water")
grid.place(CATALOG["conduit"], 2, 7, rotation=3)
for cx in range(2, 7):
    grid.place(CATALOG["conduit"], cx, 6, rotation=0 if cx < 6 else 3)
grid.place(CATALOG["conduit"], 6, 5, rotation=3)
grid.place(CATALOG["conduit"], 6, 4, rotation=3)

result = evaluate_layout(grid)
coal_rate = result["output_rate"][drill]
water_rate = result["liquid_output_rate"][pump]
power = result["power_production"][steam]
max_cycle_rate = 60 / CATALOG["steam-generator"].item_duration
theoretical_full_power = 60 * CATALOG["steam-generator"].power_production * 1.0  # coal flammability=1.0

print(f"  than tới: {coal_rate:.4f}/s (drill 1 tier2, {sum(1 for x in range(2,5) for y in range(2,5))} ô than)")
print(f"  nước tới: {water_rate:.4f}/s (dư dả, không giới hạn)")
print(f"  công suất phát ra: {power:.2f} (đơn vị power/s thật của game)")
print(f"  công suất tối đa lý thuyết (đủ than+nước): {theoretical_full_power:.2f}")

expected = theoretical_full_power * min(1.0, coal_rate / max_cycle_rate)
assert abs(power - expected) < 0.01, f"SAI: công suất phải khớp công thức đốt cháy, kỳ vọng {expected:.2f}"
assert 0 < power < theoretical_full_power, "SAI: than không đủ đốt hết công suất -- phải THẤP HƠN tối đa, không phải 0 hay full"
print(f"  ĐÚNG: công suất tỉ lệ đúng với lượng than tới ({coal_rate:.3f}/{max_cycle_rate:.3f} = "
      f"{coal_rate/max_cycle_rate:.1%} công suất đốt tối đa) -- khớp ConsumeGenerator.java thật.\n")

print("=== Kịch bản 2: cắt nguồn nước -- steam-generator PHẢI ngừng phát điện hoàn toàn ===")
grid2 = Grid(width=20, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid2.set_ore(x, y, "coal")
grid2.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid2.place(CATALOG["conveyor"], 4, 3, rotation=0)
steam2 = grid2.place(CATALOG["steam-generator"], 6, 2, rotation=0)
grid2.place(CATALOG["conveyor"], 5, 3, rotation=0)
# KHÔNG đặt pump/conduit nước -- steam-generator có than nhưng thiếu nước

result2 = evaluate_layout(grid2)
power2 = result2["power_production"][steam2]
print(f"  công suất phát ra (không có nước): {power2:.4f}")
assert power2 == 0, "SAI: thiếu nước thì steam-generator không được phát điện gì cả"
print("  ĐÚNG: thiếu nước -- dù có than -- steam-generator phát 0 điện (đúng cơ chế cần")
print("  ĐỦ CẢ 2 input, không phải trung bình cộng hay bỏ qua input thiếu).\n")

print("=== Kịch bản 3: combustion-generator (không cần nước) -- chỉ cần than ===")
grid3 = Grid(width=20, height=20)
for x in range(2, 5):
    for y in range(2, 5):
        grid3.set_ore(x, y, "coal")
grid3.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid3.place(CATALOG["conveyor"], 4, 3, rotation=0)
combustion = grid3.place(CATALOG["combustion-generator"], 5, 3, rotation=0)

result3 = evaluate_layout(grid3)
power3 = result3["power_production"][combustion]
print(f"  công suất phát ra: {power3:.4f} (combustion-generator: powerProduction=1.0, itemDuration=120 tick)")
assert power3 > 0, "SAI: combustion-generator chỉ cần than, phải phát điện được ngay không cần nước"
print("  ĐÚNG: combustion-generator không cần liquid_inputs nào -- chỉ than là đủ, khác")
print("  hẳn steam-generator (bắt buộc CẢ than lẫn nước, xem ConsumeGenerator.java).")
