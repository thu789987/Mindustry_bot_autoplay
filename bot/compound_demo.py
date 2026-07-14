import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan
from bot.state import grid_from_state

text = "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2 , 1 nguồn dẫn về core , 1 nguồn tạo slicion"
command = parse_command(text)
print(f"Câu lệnh: {text!r}\n")
print(f"parse_command() -> {command}\n")

FAKE_STATE = {
    "width": 30, "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
        {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
        {"x": 2, "y": 10, "ore": "sand"}, {"x": 3, "y": 10, "ore": "sand"},
        {"x": 2, "y": 11, "ore": "sand"}, {"x": 3, "y": 11, "ore": "sand"},
    ],
    "buildings": [{"type": "core", "x": 20, "y": 7, "rotation": 0}],
}
grid = grid_from_state(FAKE_STATE)
actions = plan(grid, command)
print(f"plan() -> {len(actions)} action(s):")
for a in actions:
    print(f"  {a}")
