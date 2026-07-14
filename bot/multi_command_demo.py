import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_commands
from bot.planner import plan
from bot.state import grid_from_state

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

text1 = "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2 , 1 nguồn dẫn về core , 1 nguồn tạo slicion"
print(f"=== Câu gốc (có lỗi chính tả 'slicion') ===\n{text1!r}\n")
commands1 = parse_commands(text1)
for c in commands1:
    print(f"  lệnh: {c}")

print("\n=== Cùng câu nhưng viết đúng chính tả 'silicon' ===")
text2 = "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2 , 1 nguồn dẫn về core , 1 nguồn tạo silicon"
commands2 = parse_commands(text2)
for c in commands2:
    print(f"  lệnh: {c}")

print(f"\n=== Thực thi {len(commands2)} lệnh (bản chính tả đúng) tuần tự trên cùng 1 map ===")
grid = grid_from_state(FAKE_STATE)
for i, c in enumerate(commands2, 1):
    try:
        actions = plan(grid, c)
        built = [a["building"] for a in actions if a["op"] == "place"]
        print(f"  lệnh {i} ({c.get('building')}): {len(actions)} action(s), đặt: {built}")
    except (ValueError, RuntimeError) as e:
        print(f"  lệnh {i} ({c.get('building')}): LỖI: {e}")
