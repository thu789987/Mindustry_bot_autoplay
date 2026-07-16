"""Chứng minh Duct.java (duct/armored-duct -- băng chuyền item riêng Erekir)
đã được nhận diện đúng cơ chế -- bug thật phát hiện khi user hỏi "bot có
nhận diện hết Transport chưa": Duct KHÔNG có field `displayedSpeed` như
Conveyor (BELT_CLASSES cũ chỉ đọc field đó), field thật là `speed` (số
tick/lần chuyển, đơn vị khác hẳn) -- tải Duct.java thật xác nhận công thức
game hiển thị cho người chơi: `stats.add(Stat.itemsMoved, 60f/speed, ...)`.
duct/armored-duct đều speed=4f -> rate=60/4=15 items/s.

Giới hạn thật (ghi rõ, không giấu): planner (bot/planner.py) hiện KHÔNG có
đường nào tự CHỌN đặt duct thay vì conveyor khi tự động nối route -- mọi
_route()/plan_split() đều hardcode CATALOG["conveyor"]. Việc thêm Duct vào
catalog chỉ khiến evaluate_layout() tính ĐÚNG throughput nếu duct đã có sẵn
trong state đầu vào (vd đọc từ map .msav thật/mod dump), không phải bot tự
xây duct qua chat command -- giống hệt vị trí của "conveyor" (cũng không
phải 1 building được CHỌN, chỉ là mặc định duy nhất khi cần route item)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

DUCT = CATALOG["duct"]
ADUCT = CATALOG["armored-duct"]
print(f"duct: kind={DUCT.kind}, base_rate={DUCT.base_rate}/s (kỳ vọng 60/4=15.0)")
print(f"armored-duct: kind={ADUCT.kind}, base_rate={ADUCT.base_rate}/s (armored chỉ khác máu/giáp, cùng speed=4f)")
assert DUCT.kind == "belt" and ADUCT.kind == "belt", "SAI: duct/armored-duct phải nhận kind='belt' như conveyor"
assert abs(DUCT.base_rate - 15.0) < 1e-9, "SAI: duct base_rate phải đúng 60/speed = 60/4 = 15.0"
assert abs(ADUCT.base_rate - 15.0) < 1e-9, "SAI: armored-duct cùng speed=4f nên base_rate cũng phải 15.0"
print("  ĐÚNG.\n")

print("--- Kịch bản: drill -> chuỗi duct -> core, throughput đi qua ĐÚNG bằng rate nền của drill (duct không làm mất/sai luồng) ---")
grid = Grid(width=20, height=10)
for x, y in [(2, 5), (3, 5), (2, 6), (3, 6)]:
    grid.set_ore(x, y, "lead")
core = grid.place(CATALOG["core"], 15, 5, rotation=0)
drill = grid.place(CATALOG["mechanical-drill"], 2, 5, rotation=0, ore_target="lead")
out_x, out_y = drill.output_tile()
for dx in range(out_x, 15):
    grid.place(DUCT, dx, out_y, rotation=0)
result = evaluate_layout(grid)
expected_rate = 60 * 4 / (600 + 50 * 1)  # mechanical-drill drill_time=600, hardness_mult=50, lead hardness=1
print(f"  rate nền drill (mọi tile ore khớp, không bị chặn -- {expected_rate:.4f}/s < base_rate duct={DUCT.base_rate}/s nên không bị cap)")
print(f"  throughput thật về core (qua duct): {result['output_rate'][core]:.4f}/s")
assert abs(result["output_rate"][core] - expected_rate) < 1e-6, (
    f"SAI: duct phải cho luồng đi qua ĐÚNG rate thật của drill, kỳ vọng {expected_rate:.4f}, ra {result['output_rate'][core]}"
)
print("  ĐÚNG: duct hoạt động như 1 belt thật -- luồng item đi qua chính xác, không mất mát/sai lệch.")
print(f"  (Không có drill nào trong catalog hiện có rate nền vượt {DUCT.base_rate}/s để test riêng phần CHẶN")
print(f"  ở cap -- cơ chế min(rate, base_rate) dùng chung với conveyor, đã kiểm chứng riêng ở chỗ khác.)\n")

print("XÁC NHẬN: Duct.java giờ được nhận diện đúng công thức thật (60/speed,")
print("khác hẳn Conveyor.displayedSpeed) -- lỗ hổng thật (không cố ý loại trừ,")
print("chỉ đơn giản bị bỏ sót) tới khi user hỏi trực tiếp mới phát hiện ra.")
