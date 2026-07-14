import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.planner import plan
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

# Đúng kịch bản người dùng hỏi: "khai thác than và cát, tách than ra làm 2,
# 1 nguồn dẫn về core, 1 nguồn tạo silicon" -- silicon-smelter cần CẢ than
# lẫn cát, nhánh split chỉ lo than, cát phải được TỰ nối từ drill cát có sẵn.
state = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]]
              + [{"x": x, "y": y, "ore": "sand"} for x, y in [(10, 2), (11, 2), (10, 3), (11, 3)]],
    "buildings": [{"type": "core", "x": 20, "y": 10, "rotation": 0}],
}
grid = grid_from_state(state)

print("=== Bước 1: khai thác than ===")
actions1 = plan(grid, {"action": "build", "building": "drill", "ore_target": "coal", "ore_location_hint": None})
for a in actions1:
    print(f"  {a}")

print("\n=== Bước 2: khai thác cát ===")
actions2 = plan(grid, {"action": "build", "building": "drill", "ore_target": "sand", "ore_location_hint": None})
for a in actions2:
    print(f"  {a}")

print("\n=== Bước 3: tách than ra làm 2 -- 1 về core, 1 tạo silicon (filter_split) ===")
command3 = {
    "action": "filter_split",
    "source": {"building": "drill", "hint": ("ore_target", "coal")},
    "filter_item": "coal",
    "match": {"kind": "build", "building": "silicon-smelter"},  # khớp filter (than) -> đi thẳng vào silicon-smelter
    "other": {"kind": "core"},                                   # không khớp -> rẽ về core (thực tế nhánh này sẽ 0/s vì nguồn chỉ ra than)
}
actions3 = plan(grid, command3)
for a in actions3:
    print(f"  {a}")

print("\n=== Bước 4: evaluate_layout ===")
result = evaluate_layout(grid)
silicon = next(b for b in grid.unique_buildings() if b.type.name == "silicon-smelter")
core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
print(f"  silicon-smelter output: {result['output_rate'][silicon]:.4f}/s")
print(f"  core output:            {result['output_rate'][core]:.4f}/s")

assert result["output_rate"][silicon] > 0, "SAI: silicon-smelter phải chạy được (bot phải tự nối cát còn thiếu)"
print("\n  ĐÚNG: silicon-smelter chạy được -- bot tự nhận ra cần cả than (qua nhánh")
print("  filter_split) LẪN cát (tự tìm nguồn có sẵn, không ai yêu cầu rõ), đúng ý")
print("  đồ thị recipe thật của silicon-smelter (input: than + cát).")
