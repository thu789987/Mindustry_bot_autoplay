"""Chứng minh: người dùng giờ có thể gọi rõ tên rotary-pump/impulse-pump
(2 tier bơm mạnh hơn mechanical-pump, xem reference/Blocks.java) thay vì
chỉ có "bơm"/"pump" luôn ra đúng mechanical-pump như trước.

Bối cảnh: audit "Liquid Blocks" (đọc hết reference/Blocks.java:129-133, đối
chiếu simulator/generated_catalog.py) phát hiện 18/19 block liquid đã có cơ
chế mô phỏng đầy đủ, nhưng command_parser.py chỉ có phrase cho MỘT loại pump
(mechanical-pump) -- rotary-pump/impulse-pump hoàn toàn không gọi được qua
lệnh, dù planner.py:1715 (nhánh kind=="pump") vốn đã tổng quát, không hardcode
riêng cho mechanical-pump nào (comment sẵn trong code: "thêm để nhất quán và
không sai nếu sau này có tier pump khác cần điện thật").

Quyết định thiết kế: Pump.java KHÔNG có field "tier"/ngưỡng năng lực như
Drill.java (drill yếu quá thì KHÔNG mine được -- xem select_drill_type()),
pump nào cũng bơm được mọi liquid, chỉ khác pump_amount/power_input. Vì vậy
áp dụng tinh thần "nhà máy điện" (mặc định RẺ NHẤT, nói rõ tên mới đổi loại)
thay vì tinh thần "máy khoan" (sentinel + auto-chọn theo năng lực) -- không
thêm sentinel tự chọn tier theo nhu cầu liquid vì không có cơ sở thật nào
trong Pump.java để dựa vào, tránh bịa ra ngưỡng "tier" không có trong game.

Bug thật phát hiện + sửa khi thêm phrase: mọi chỗ xử lý liquid_target trong
command_parser.py (parse_command, _find_hint, parse_commands) đều hardcode
so sánh building=="mechanical-pump" -- nếu chỉ thêm phrase mà không sửa
3 chỗ này, "bơm ly tâm nước" sẽ ra đúng building=rotary-pump nhưng
liquid_target=None (planner.py raise lỗi "pump command needs a
liquid_target"). Sửa: dùng chung 1 set _PUMP_NAMES ở cả 3 chỗ."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command, parse_commands
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

print("--- Kịch bản 1: 'bơm' trần vẫn mặc định mechanical-pump (rẻ nhất, không đổi hành vi cũ) ---")
cmd_default = parse_command("bơm nước")
print(f"  {cmd_default}")
assert cmd_default == {"action": "build", "building": "mechanical-pump", "liquid_target": "water"}
print("  ĐÚNG: hành vi cũ không đổi.\n")

print("--- Kịch bản 2: 'bơm ly tâm'/'bơm xung lực' ra đúng rotary-pump/impulse-pump ---")
cmd_rotary = parse_command("bơm ly tâm nước")
cmd_impulse = parse_command("bơm xung lực dầu")
print(f"  {cmd_rotary}")
print(f"  {cmd_impulse}")
assert cmd_rotary == {"action": "build", "building": "rotary-pump", "liquid_target": "water"}
assert cmd_impulse == {"action": "build", "building": "impulse-pump", "liquid_target": "oil"}
print("  ĐÚNG: cả building lẫn liquid_target đều bắt đúng (không rớt None).\n")

print("--- Kịch bản 3: tên tiếng Anh literal cũng nhận được (giống drill/generator) ---")
assert parse_command("rotary-pump nước")["building"] == "rotary-pump"
assert parse_command("impulse-pump dầu")["building"] == "impulse-pump"
print("  ĐÚNG.\n")

print("--- Kịch bản 4: câu ghép kế thừa ĐÚNG tier pump của đoạn trước, không rớt về mechanical-pump ---")
commands = parse_commands("bơm ly tâm nước, và dầu")
print(f"  {commands}")
assert len(commands) == 2
assert commands[0]["building"] == "rotary-pump" and commands[0]["liquid_target"] == "water"
assert commands[1]["building"] == "rotary-pump" and commands[1]["liquid_target"] == "oil", (
    "SAI: đoạn 'dầu' kế thừa hành động phải giữ ĐÚNG tier rotary-pump, không tự đổi về mechanical-pump"
)
print("  ĐÚNG: kế thừa đúng tier pump qua các đoạn câu ghép.\n")

print("--- Kịch bản 5: build thật rotary-pump qua plan_build() -- auto-power đúng power_input=18 ---")
FAKE_STATE = {
    "width": 30, "height": 20,
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 6) for y in range(2, 6)],
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(20, 24) for y in range(2, 6)],
    "buildings": [{"type": "core", "x": 15, "y": 10, "rotation": 0}],
}
grid = grid_from_state(FAKE_STATE)
actions = plan_build(grid, parse_command("bơm ly tâm nước"))
pump = next(b for b in grid.unique_buildings() if b.type.name == "rotary-pump")
assert any(a.get("building") == "combustion-generator" for a in actions), (
    "SAI: rotary-pump có power_input=18 (khác mechanical-pump=0) -- phải tự cấp điện"
)
result = evaluate_layout(grid)
print(f"  power_satisfaction: {result['power_satisfaction'].get(pump)}")
print(f"  liquid_output_rate: {result['liquid_output_rate'].get(pump)} (kỳ vọng = pump_amount*60 = {pump.type.pump_amount * 60:.4f})")
assert result["power_satisfaction"].get(pump) == 1.0
assert abs(result["liquid_output_rate"].get(pump, 0) - pump.type.pump_amount * 60) < 1e-9
print("  ĐÚNG: rotary-pump build được, tự cấp điện, rate đúng công thức Pump.java thật.\n")

print("XÁC NHẬN: rotary-pump/impulse-pump giờ gọi được qua lệnh chat, đúng liquid_target,")
print("kế thừa đúng tier qua câu ghép, và build/cấp điện/tính rate đúng như mechanical-pump")
print("(planner.py vốn đã tổng quát cho MỌI kind=='pump', chỉ thiếu phrase ở command_parser.py).")
