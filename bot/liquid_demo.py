import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

# multi-press cần coal (item) + water (liquid) cùng lúc -- map có sẵn than
# nhưng CHƯA có pump nào, chỉ có tile nước chưa khai thác.
FAKE_STATE = {
    "width": 30,
    "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
        {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
    ],
    "liquid_tiles": [
        {"x": 2, "y": 12, "liquid": "water"}, {"x": 3, "y": 12, "liquid": "water"},
        {"x": 2, "y": 13, "liquid": "water"}, {"x": 3, "y": 13, "liquid": "water"},
    ],
    "buildings": [
        {"type": "mechanical-drill", "x": 2, "y": 2, "rotation": 0, "ore_target": "coal"},
        {"type": "core", "x": 20, "y": 7, "rotation": 0},
    ],
}


def run(grid, text):
    command = parse_command(text)
    print(f"\n> {text!r}\n  parse: {command}")
    if command.get("action") == "unknown":
        print("  không hiểu lệnh")
        return
    try:
        actions = plan(grid, command)
    except (ValueError, RuntimeError) as e:
        print(f"  LỖI: {e}")
        return
    print(f"  {len(actions)} action(s):")
    for a in actions:
        print(f"    {a}")


if __name__ == "__main__":
    grid = grid_from_state(FAKE_STATE)

    # 1) xây multi-press -- cần bot tự đặt pump mới (chưa có sẵn) và nối cả
    #    belt (than) lẫn ống dẫn (nước) tới cùng 1 building
    run(grid, "xây máy ép đa năng")

    print("\nevaluate_layout() -- nước có thực sự giới hạn sản lượng không?")
    result = evaluate_layout(grid)
    for b, rate in result["output_rate"].items():
        print(f"  {b.type.name:>16} @ ({b.x},{b.y})  item_output={rate:.4f}/s")
    for b, rate in result["liquid_output_rate"].items():
        if b.type.kind == "pump":
            print(f"  {b.type.name:>16} @ ({b.x},{b.y})  liquid_output={rate:.4f}/s")

    # 2) xây building không hỗ trợ (turret) -- phải báo lỗi rõ ràng, không đoán.
    #    command_parser chưa có phrase cho turret (cố ý, ngoài phạm vi hiện
    #    tại) nên ép command tay để test thẳng planner.plan().
    print("\n--- thử xây turret 'duo' (chưa hỗ trợ, ép command tay) ---")
    from bot.planner import plan as _plan
    try:
        _plan(grid, {"action": "build", "building": "duo"})
    except (ValueError, RuntimeError) as e:
        print(f"  LỖI (đúng như kỳ vọng): {e}")
