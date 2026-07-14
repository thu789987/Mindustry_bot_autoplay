import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan
from bot.state import grid_from_state

# Core ở góc dưới-phải (25,25). Mỏ than "xa" đặt ở toạ độ NHỎ (0,0 -- quét
# trước). Mỏ than "gần" đặt sát core (23,23 -- quét sau, dù gần hơn hẳn).
FAKE_STATE = {
    "width": 30, "height": 30,
    "ore_tiles": [
        # mỏ THAN XA core (cách core ~35 ô), nhưng toạ độ nhỏ -> quét trước
        {"x": 0, "y": 0, "ore": "coal"}, {"x": 1, "y": 0, "ore": "coal"},
        {"x": 0, "y": 1, "ore": "coal"}, {"x": 1, "y": 1, "ore": "coal"},
        # mỏ THAN GẦN core (sát ngay, cách ~2 ô), toạ độ lớn -> quét sau
        {"x": 22, "y": 23, "ore": "coal"}, {"x": 23, "y": 23, "ore": "coal"},
        {"x": 22, "y": 24, "ore": "coal"}, {"x": 23, "y": 24, "ore": "coal"},
    ],
    "buildings": [
        {"type": "core", "x": 25, "y": 25, "rotation": 0},
    ],
}

command = parse_command("xây máy khoan khai thác than")
print(f"lệnh: {command}\n")
grid = grid_from_state(FAKE_STATE)
actions = plan(grid, command)
drill = next(a for a in actions if a["op"] == "place" and a["building"] != "conveyor")
print(f"bot đặt drill tại: ({drill['x']}, {drill['y']})")
print(f"  -> mỏ XA core (0,0..1,1), cách core ~35 ô: {'ĐÚNG, chọn cái này' if drill['x'] < 5 else 'không chọn'}")
print(f"  -> mỏ GẦN core (22,23..23,24), cách core ~2 ô: {'ĐÚNG, chọn cái này' if drill['x'] > 5 else 'không chọn'}")
