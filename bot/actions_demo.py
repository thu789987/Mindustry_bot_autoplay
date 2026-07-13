import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan
from bot.state import grid_from_state

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
        {"type": "sorter", "x": 6, "y": 6, "rotation": 0},
    ],
}


def run(grid, text):
    command = parse_command(text)
    print(f"\n> {text!r}\n  parse: {command}")
    if command.get("action") == "unknown":
        print("  không hiểu lệnh")
        return command
    try:
        actions = plan(grid, command)
    except (ValueError, RuntimeError) as e:
        print(f"  LỖI: {e}")
        return command
    for a in actions:
        print(f"  action: {a}")
    return command


if __name__ == "__main__":
    grid = grid_from_state(FAKE_STATE)

    # 1) xây -- baseline, đã test kỹ ở example_run.py, chạy lại cho liền mạch
    run(grid, "xây nhà máy silicon")

    # 2) xoay -- đổi hướng nhà máy silicon vừa xây sang hướng bắc
    run(grid, "xoay nhà máy silicon hướng bắc")

    # 3) nối lại đường ray -- định tuyến lại belt từ drill than tới nhà máy silicon
    run(grid, "chỉnh lại đường ray từ máy khoan than đến nhà máy silicon")

    # 4) xóa -- xoá nhà máy silicon
    #    Bây giờ có 2 building loại "mechanical-drill" (than, cát) -> lệnh xoá
    #    "máy khoan" một mình sẽ mơ hồ, phải test cả 2 trường hợp:
    print("\n--- test lỗi mơ hồ (nhiều máy khoan, không chỉ rõ cái nào) ---")
    run(grid, "xóa máy khoan")

    print("\n--- chỉ rõ toạ độ thì hết mơ hồ ---")
    run(grid, "xóa máy khoan (2,2)")

    print("\n--- xóa nhà máy silicon (chỉ có 1 cái, không mơ hồ) ---")
    run(grid, "xóa nhà máy silicon")

    # 5) configure -- lọc sorter theo item
    print("\n--- cấu hình bộ lọc sorter ---")
    run(grid, "cấu hình bộ lọc sorter thành đồng")

    print("\n--- lệnh cấu hình thiếu item -> unknown ---")
    run(grid, "cấu hình bộ lọc sorter")
