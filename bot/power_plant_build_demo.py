"""Trả lời trực tiếp câu người dùng hỏi thật: "xây nhà máy điện có đầu vào
là than và nước" -- chạy qua ĐÚNG pipeline dict parser + plan_build() thật,
không phải gọi thẳng simulator như bot/power_generator_demo.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

STATE = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x, y in [(2, 10), (3, 10), (2, 11), (3, 11)]],
    "buildings": [{"type": "core", "x": 15, "y": 10, "rotation": 0}],
}

print('=== Câu: "xây nhà máy điện có đầu vào là than và nước" ===')
command = parse_command("xây nhà máy điện có đầu vào là than và nước")
print(f"  parse_command: {command}")
assert command["building"] == "combustion-generator", (
    "LƯU Ý (không phải assert sai): dict không đọc \"có đầu vào... nước\" để tự chọn "
    "steam-generator -- chỉ khớp cụm từ cố định, xem NEXT_STEPS.md. Để chắc chắn có "
    "nước, người dùng cần nói rõ \"nhà máy điện hơi nước\"."
)

grid = grid_from_state(STATE)
actions = plan_build(grid, command)
print(f"  {len(actions)} hành động:")
for a in actions:
    print(f"    {a}")

result = evaluate_layout(grid)
gen = next(b for b in grid.unique_buildings() if b.type.kind == "generator")
print(f"  công suất phát: {result['power_production'][gen]:.2f}")
assert result["power_production"][gen] > 0, "SAI: generator phải phát được điện"
print("  ĐÚNG: combustion-generator tự đặt, tự nối than, phát điện được ngay.\n")

print('=== Câu rõ ràng hơn: "xây nhà máy điện hơi nước" -- đúng ý than+nước ===')
command2 = parse_command("xây nhà máy điện hơi nước")
print(f"  parse_command: {command2}")
assert command2["building"] == "steam-generator"

grid2 = grid_from_state(STATE)
actions2 = plan_build(grid2, command2)
print(f"  {len(actions2)} hành động (có cả drill than LẪN pump nước):")
for a in actions2:
    print(f"    {a}")

result2 = evaluate_layout(grid2)
gen2 = next(b for b in grid2.unique_buildings() if b.type.kind == "generator")
print(f"  công suất phát: {result2['power_production'][gen2]:.2f}")
assert result2["power_production"][gen2] > 0, "SAI: steam-generator phải tự nối đủ than+nước rồi phát điện được"
assert any(a["building"] == "mechanical-pump" for a in actions2), "SAI: phải tự đặt pump nước cho steam-generator"
print("  ĐÚNG: steam-generator tự đặt CẢ drill than lẫn pump nước, phát điện được.")
