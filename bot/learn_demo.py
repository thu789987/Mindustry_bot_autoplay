import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.feedback import record_feedback
from bot.planner import find_free_area_candidates, find_producer, featurize_target_spot, plan_build
from bot.scorer import Scorer
from bot.state import grid_from_state
from simulator.buildings import CATALOG

FAKE_STATE = {
    "width": 30,
    "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
        {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
        {"x": 2, "y": 10, "ore": "sand"}, {"x": 3, "y": 10, "ore": "sand"},
        {"x": 2, "y": 11, "ore": "sand"}, {"x": 3, "y": 11, "ore": "sand"},
    ],
    "buildings": [
        {"type": "mechanical-drill", "x": 2, "y": 2, "rotation": 0, "ore_target": "coal"},
        {"type": "mechanical-drill", "x": 2, "y": 10, "rotation": 0, "ore_target": "sand"},
        {"type": "core", "x": 10, "y": 7, "rotation": 0},
    ],
}


def resolve_context(grid, building_type):
    # sources: (item_name, producer_building) -- featurize_target_spot() gọi
    # producer.output_tile() nội bộ (xem bot/planner.py), khớp contract dùng
    # chung với _find_or_build_factory_sources().
    sources = [(item, find_producer(grid, item)) for item in building_type.recipe.inputs]
    core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
    return sources, (core.x, core.y)


if __name__ == "__main__":
    command = parse_command("xây nhà máy silicon")
    building_type = CATALOG["silicon-smelter"]

    # 1) chưa học gì -- plan_build với trọng số mặc định chọn đâu?
    scorer = Scorer()  # không load từ đĩa, demo sạch từ đầu
    grid1 = grid_from_state(FAKE_STATE)
    actions1 = plan_build(grid1, command, scorer=scorer)
    default_spot = next((a["x"], a["y"]) for a in actions1 if a["building"] == "silicon-smelter")
    print(f"[trước phản hồi]  trọng số={scorer.weights}  -> chọn {default_spot}")

    # 2) bạn chê chỗ đó, thích 1 chỗ xa core hơn (cùng độ dài belt) hơn
    grid2 = grid_from_state(FAKE_STATE)
    sources, core_pos = resolve_context(grid2, building_type)
    rejected_spot = default_spot
    preferred_spot = (3, 6)  # xa core hơn (8 so với 6), cùng độ dài belt (7)
    record_feedback(grid2, building_type, sources, rejected_spot, preferred_spot, scorer, core_pos)
    print(f"[sau phản hồi]    trọng số={scorer.weights}")

    # 3) replan CÙNG lệnh, CÙNG map (grid mới tinh) -- có đổi lựa chọn không?
    grid3 = grid_from_state(FAKE_STATE)
    actions3 = plan_build(grid3, command, scorer=scorer)
    new_spot = next((a["x"], a["y"]) for a in actions3 if a["building"] == "silicon-smelter")
    print(f"[replan cùng lệnh] -> chọn {new_spot}")

    print()
    if new_spot == preferred_spot:
        print(f"XÁC NHẬN: sau 1 lần phản hồi, bot đổi từ {rejected_spot} sang đúng {preferred_spot} như bạn muốn.")
    else:
        print(f"CHƯA đổi đúng như kỳ vọng (muốn {preferred_spot}, ra {new_spot}) -- cần xem lại features/learning rate.")
