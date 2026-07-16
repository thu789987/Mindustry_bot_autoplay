"""Chứng minh: khi bot tự xây generator (combustion-generator/steam-generator),
đường belt than vào generator giờ có "van an toàn" -- overflow-gate + nhánh
rẽ về core -- để than KHÔNG làm NGHẸT CỨNG belt trong game thật khi generator
đã đủ/đầy.

User: "không cần khi đầy mới rẽ, ý tôi là bot xây dựng thế nào mà khi băng
chuyền vào điện đầy thì tài nguyên tự động về core chứ không phải kẹt cứng"
-- KHÔNG cần simulator này mô phỏng đúng THỜI ĐIỂM "đầy" (đã xác nhận trước
đó: overflow-gate trong simulator là xấp xỉ TĨNH, luôn ưu tiên đường thẳng
100% -- xem NEXT_STEPS.md), chỉ cần bot XÂY SẴN hạ tầng vật lý đúng để game
thật tự xử lý đúng khi generator đầy.

Giới hạn đã biết + verify thật: CHỈ áp dụng cho nhánh "generator" TRỰC TIẾP
của plan_build() (lệnh "xây máy phát điện" rõ ràng) -- KHÔNG áp dụng trong
_ensure_powered() (dùng ở rất nhiều ngữ cảnh lồng nhau: drill/pump/factory/
generator-cluster/bên trong filter_split...) vì test thật phát hiện: thêm
overflow-gate ở đó có thể vô tình chiếm đúng hướng mà 1 lệnh KHÁC cần để tự
nối tới core, gây lỗi giả "không tìm được đường" cho lệnh đó (bug thật gặp ở
bot/split_command_demo.py + bot/llm_split_demo.py khi thử áp dụng rộng hơn)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout


def count_places(actions, building_name):
    return sum(1 for a in actions if a["op"] == "place" and a["building"] == building_name)


print("--- Kịch bản 1: 'xây máy phát điện' -> tự thêm overflow-gate + nhánh rẽ về core ---")
FAKE_STATE = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 4) for y in range(2, 4)],
    "buildings": [{"type": "core", "x": 15, "y": 15, "rotation": 0}],
}
grid = grid_from_state(FAKE_STATE)
cmd = parse_command("xây máy phát điện")
actions = plan_build(grid, cmd)
n_gate = count_places(actions, "overflow-gate")
n_gen = count_places(actions, "combustion-generator")
print(f"  generator đặt: {n_gen}, overflow-gate đặt: {n_gate}")
assert n_gen == 1
assert n_gate == 1, "SAI: đường than vào generator phải có 1 overflow-gate (van an toàn)"
print("  ĐÚNG: có đúng 1 overflow-gate trên đường than vào generator.\n")


print("--- Kịch bản 2: overflow-gate NẰM ĐÚNG chỗ chạm thẳng generator, quay mặt vào generator ---")
gate_action = next(a for a in actions if a["op"] == "place" and a["building"] == "overflow-gate")
gen = next(b for b in grid.unique_buildings() if b.type.name == "combustion-generator")
from simulator.buildings import DIRECTIONS
gx, gy = gate_action["x"], gate_action["y"]
rot = gate_action["rotation"]
dx, dy = DIRECTIONS[rot]
straight_tile = (gx + dx, gy + dy)
print(f"  overflow-gate tại ({gx},{gy}) rot={rot}, ô thẳng phía trước: {straight_tile}, generator footprint: {gen.footprint()}")
assert straight_tile in set(gen.footprint()), "SAI: hướng thẳng của overflow-gate phải chạm đúng generator"
print("  ĐÚNG: overflow-gate quay mặt thẳng vào generator (đường ưu tiên chính).\n")


print("--- Kịch bản 3: có 1 nhánh conveyor RẼ từ overflow-gate, chạm tới core (đường thoát dự phòng thật, không chỉ đặt suông) ---")
core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
# Duyet nguoc tu overflow-gate xem co duong belt nao (khac huong straight) dan toi core khong.
side_dirs = [(rot + 1) % 4, (rot - 1) % 4]
side_tiles = [(gx + DIRECTIONS[d][0], gy + DIRECTIONS[d][1]) for d in side_dirs]
found_side_belt = [t for t in side_tiles if grid.building_at(*t) is not None and grid.building_at(*t).type.kind == "belt"]
print(f"  ô cạnh (vuông góc) của overflow-gate: {side_tiles}, có belt: {found_side_belt}")
assert found_side_belt, "SAI: phải có ít nhất 1 nhánh conveyor rẽ từ overflow-gate (đường dự phòng)"

from bot.planner import find_belt_path
branch_start = found_side_belt[0]
# Tu chinh belt tai branch_start, xem no co thuc su dan toi CORE khong (theo dung huong rotation cua no, khong phai BFS moi).
visited = set()
cur = branch_start
reached_core = False
for _ in range(200):
    if cur in visited:
        break
    visited.add(cur)
    b = grid.building_at(*cur)
    if b is None:
        break
    if b.type.kind == "core" or cur in set(core.footprint()):
        reached_core = True
        break
    if b.type.kind != "belt":
        break
    ddx, ddy = DIRECTIONS[b.rotation]
    cur = (cur[0] + ddx, cur[1] + ddy)
    if cur in set(core.footprint()):
        reached_core = True
        break
print(f"  đi theo chuỗi belt từ nhánh rẽ -> {'CHẠM core' if reached_core else 'KHÔNG tới core'}")
assert reached_core, "SAI: nhánh rẽ của overflow-gate phải thực sự dẫn tới core, không phải belt cụt"
print("  ĐÚNG: nhánh dự phòng THẬT SỰ dẫn tới core, không phải đặt suông.\n")


print("--- Kịch bản 4: số liệu mô phỏng KHÔNG đổi so với không có overflow-gate (overflow-gate tĩnh luôn ưu tiên đường thẳng 100%) ---")
result = evaluate_layout(grid)
power = result["power_production"].get(gen, 0.0)
# Tinh tay: drill(3,3) chi cham dung 1/4 o than (footprint (3,3)-(4,4), than
# chi co tai (2,2),(2,3),(3,2),(3,3) -- chi (3,3) nam trong chan de).
drill = next(b for b in grid.unique_buildings() if b.type.name == "mechanical-drill")
from simulator.buildings import ITEMS
coal = ITEMS["coal"]
drill_time_eff = drill.type.drill_time + drill.type.hardness_multiplier * coal.hardness
rate = 60 * 1 / drill_time_eff  # 1 o than duy nhat trong chan de
max_cycle_rate = 60 / gen.type.item_duration
cycle_rate = min(max_cycle_rate, rate)
expected_power = 60 * gen.type.power_production * coal.flammability * (cycle_rate / max_cycle_rate)
print(f"  power_production đo được: {power:.6f}/s (kỳ vọng {expected_power:.6f}/s -- tính tay, KHÔNG liên quan gì overflow-gate)")
assert abs(power - expected_power) < 1e-6, "SAI: overflow-gate không được làm thay đổi số liệu mô phỏng (vẫn phải = công thức generator gốc)"
print("  ĐÚNG: overflow-gate chỉ thêm hạ tầng AN TOÀN cho game thật, không ảnh hưởng số liệu mô phỏng ở đây.\n")

print("XÁC NHẬN: lệnh xây generator giờ tự thêm overflow-gate + nhánh rẽ")
print("về core -- than không còn nguy cơ làm kẹt cứng belt khi generator đã")
print("đủ trong game thật, mà KHÔNG ảnh hưởng gì tới số liệu mô phỏng hiện có.")
print("Giới hạn: chỉ áp dụng cho lệnh xây generator TRỰC TIẾP, chưa áp dụng")
print("trong _ensure_powered() (nhiều ngữ cảnh lồng nhau, rủi ro tranh chấp")
print("không gian với lệnh khác -- xem NEXT_STEPS.md).")
