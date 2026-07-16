"""Test end-to-end: lệnh tiếng Việt (command_parser.py) -> plan_build() ->
đặt+nối beam-drill/wall-crafter tự động về core, đúng cách mọi mechanic
khác trong dự án đã được nối từ trước (xem NEXT_STEPS.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

FAKE_STATE = {
    "width": 30, "height": 20,
    "ore_tiles": [
        {"x": 12, "y": 10, "ore": "copper"},
        # mỏ than cho _ensure_powered() -- plasma-bore/cliff-crusher đều
        # cần điện thật (power_input > 0), giờ plan_build() tự gọi
        # _ensure_powered() cho cả 2 kind này (sửa cùng đợt SolidPump, xem
        # NEXT_STEPS.md) nên cần mỏ than sẵn trên map, cùng quy ước mọi
        # FAKE_STATE khác trong dự án.
        {"x": 20, "y": 15, "ore": "coal"}, {"x": 21, "y": 15, "ore": "coal"},
        {"x": 20, "y": 16, "ore": "coal"}, {"x": 21, "y": 16, "ore": "coal"},
    ],
    "attribute_tiles": [{"x": 12, "y": 6, "attribute": "sand"}],
    "buildings": [{"type": "core", "x": 5, "y": 5, "rotation": 0}],
}

print("--- Lệnh: 'xây máy khoan plasma đồng' ---")
cmd = parse_command("xây máy khoan plasma đồng")
print(f"  parse ra: {cmd}")
assert cmd == {
    "action": "build", "building": "plasma-bore", "ore_target": "copper", "ore_location_hint": None,
}, f"SAI: parse_command ra {cmd}"

grid = grid_from_state(FAKE_STATE)
actions = plan_build(grid, cmd)
print(f"  đã tạo {len(actions)} hành động")
result = evaluate_layout(grid)
core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
print(f"  core nhận: {result['output_rate'][core]:.4f}/s")
assert result["output_rate"][core] > 0, "SAI: plasma-bore đặt xong phải tự nối về core và ra sản lượng > 0"
print("  ĐÚNG: plasma-bore tự tìm chỗ sát mỏ đồng, tự nối belt về core.\n")

print("--- Lệnh: 'xây máy nghiền vách đá' ---")
cmd2 = parse_command("xây máy nghiền vách đá")
print(f"  parse ra: {cmd2}")
assert cmd2 == {"action": "build", "building": "cliff-crusher"}, f"SAI: parse_command ra {cmd2}"

grid2 = grid_from_state(FAKE_STATE)
actions2 = plan_build(grid2, cmd2)
print(f"  đã tạo {len(actions2)} hành động")
result2 = evaluate_layout(grid2)
core2 = next(b for b in grid2.unique_buildings() if b.type.kind == "core")
print(f"  core nhận: {result2['output_rate'][core2]:.4f}/s")
assert result2["output_rate"][core2] > 0, "SAI: cliff-crusher đặt xong phải tự nối về core và ra sản lượng > 0"
print("  ĐÚNG: cliff-crusher tự tìm chỗ sát attribute sand, tự chọn đúng rotation, tự nối belt về core.\n")

print("XÁC NHẬN: cả 2 mechanic mới dùng được qua lệnh chat tiếng Việt đầu-cuối,")
print("giống mọi mechanic khác trong dự án -- không chỉ là code chưa nối gì cả.")
