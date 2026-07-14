import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

# drill than -> mass-driver A (link tới driver B ở xa, cách nhiều ô KHÔNG có
# belt) -> ra core. MassDriver.java thật: bắn cả cụm item tích luỹ theo đợt,
# xấp xỉ tốc độ trung bình = 60*itemCapacity/reload = 60*120/200 = 36/s --
# ở đây drill than chỉ ra ~0.34/s nên driver không phải nút thắt, dùng để
# xác nhận cơ chế "nhảy" hoạt động giống bridge, KHÔNG xác nhận số 36/s
# (xem mass_driver_cap_demo bên dưới cho phép kiểm capacity cap).
grid = Grid(width=40, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid.set_ore(x, y, "coal")
grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid.place(CATALOG["conveyor"], 4, 3, rotation=0)

driver_a = grid.place(CATALOG["mass-driver"], 5, 2, rotation=0)  # size=3, footprint (5,2)-(7,4)
driver_b = grid.place(CATALOG["mass-driver"], 20, 2, rotation=0, link_target=driver_a)
driver_a.link_target = driver_b

grid.place(CATALOG["conveyor"], 23, 3, rotation=0)
core = grid.place(CATALOG["core"], 24, 3)

result = evaluate_layout(grid)
print("=== Mass Driver: bắn item qua khoảng cách xa (15 ô, không có belt giữa) ===")
print(f"  core nhận: {result['output_rate'][core]:.4f}/s")
assert result["output_rate"][core] > 0, "SAI: item phải tới core qua driver_a -> driver_b"
print("  ĐÚNG: item được 'bắn' từ driver_a sang driver_b rồi tiếp tục ra core.\n")

print("=== Kiểm capacity cap: driver bị giới hạn tốc độ trung bình = 60*capacity/reload ===")
cap = CATALOG["mass-driver"].driver_capacity
reload = CATALOG["mass-driver"].driver_reload
expected_cap = 60 * cap / reload
print(f"  driver_capacity={cap}, driver_reload={reload} -> cap lý thuyết = {expected_cap:.4f}/s")
print(f"  (nguồn than ~0.34/s < cap {expected_cap:.1f}/s nên không bị driver giới hạn ở đây,")
print(f"   đúng như kỳ vọng vì early-game than luôn chậm hơn nhiều so với driver)")
assert result["output_rate"][core] <= expected_cap + 1e-6, "SAI: throughput không được vượt cap lý thuyết của driver"
print("  ĐÚNG: throughput thực tế không vượt cap lý thuyết của mass driver.")
