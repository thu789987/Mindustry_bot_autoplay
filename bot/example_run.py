import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

# Fake state: coal already has a drill on it (matches the user's own example
# of "drill than đã có"), sand is present but not mined yet -- exercises both
# the "reuse existing producer" and "place a new drill" branches of the planner.
FAKE_STATE = {
    "width": 30,
    "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
        {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
        # mỏ than thứ 2, riêng cho combustion-generator (silicon-smelter
        # thật cần điện, xem NEXT_STEPS.md -- _ensure_powered tự đặt drill
        # than MỚI cho generator thay vì tranh chấp router với drill than đã
        # có, nên cần đủ mỏ than cho CẢ 2 drill).
        {"x": 15, "y": 15, "ore": "coal"}, {"x": 16, "y": 15, "ore": "coal"},
        {"x": 15, "y": 16, "ore": "coal"}, {"x": 16, "y": 16, "ore": "coal"},
        {"x": 2, "y": 10, "ore": "sand"}, {"x": 3, "y": 10, "ore": "sand"},
        {"x": 2, "y": 11, "ore": "sand"}, {"x": 3, "y": 11, "ore": "sand"},
    ],
    "buildings": [
        {"type": "mechanical-drill", "x": 2, "y": 2, "rotation": 0, "ore_target": "coal"},
    ],
}


if __name__ == "__main__":
    text = "xây nhà máy silicon"
    command = parse_command(text)
    print(f"lệnh: {text!r}")
    print(f"  -> parse_command: {command}")

    grid = grid_from_state(FAKE_STATE)
    actions = plan_build(grid, command)

    print(f"\nkế hoạch xây ({len(actions)} hành động):")
    for a in actions:
        print(" ", a)

    # plan_build() already mutated `grid` with every placement above -- reuse
    # luồng A's evaluator to confirm silicon actually flows, not just that
    # coordinates look plausible.
    result = evaluate_layout(grid)
    print("\nxác nhận bằng evaluate_layout (luồng A):")
    for b, rate in result["output_rate"].items():
        print(f"  {b.type.name:>16} @ ({b.x},{b.y})  output={rate:.4f}/s")
