import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan
from bot.state import grid_from_state

# Core ở giữa map (15,15). 4 mỏ than -- mỗi mỏ 1 hướng, cách đều nhau, để
# "gần nhất" (mặc định) không tự nhiên ưu tiên cái nào.
CORE_POS = (15, 15)
FAKE_STATE = {
    "width": 30, "height": 30,
    "ore_tiles": [
        # Đông (x lớn hơn core)
        {"x": 22, "y": 15, "ore": "coal"}, {"x": 23, "y": 15, "ore": "coal"},
        {"x": 22, "y": 16, "ore": "coal"}, {"x": 23, "y": 16, "ore": "coal"},
        # Nam (y lớn hơn core)
        {"x": 15, "y": 22, "ore": "coal"}, {"x": 16, "y": 22, "ore": "coal"},
        {"x": 15, "y": 23, "ore": "coal"}, {"x": 16, "y": 23, "ore": "coal"},
        # Tây (x nhỏ hơn core)
        {"x": 6, "y": 15, "ore": "coal"}, {"x": 7, "y": 15, "ore": "coal"},
        {"x": 6, "y": 16, "ore": "coal"}, {"x": 7, "y": 16, "ore": "coal"},
        # Bắc (y nhỏ hơn core)
        {"x": 15, "y": 6, "ore": "coal"}, {"x": 16, "y": 6, "ore": "coal"},
        {"x": 15, "y": 7, "ore": "coal"}, {"x": 16, "y": 7, "ore": "coal"},
    ],
    "buildings": [{"type": "core", "x": CORE_POS[0], "y": CORE_POS[1], "rotation": 0}],
}


def classify(x, y):
    dx, dy = x - CORE_POS[0], y - CORE_POS[1]
    if abs(dx) >= abs(dy):
        return "Đông" if dx > 0 else "Tây"
    return "Nam" if dy > 0 else "Bắc"


def run(text):
    grid = grid_from_state(FAKE_STATE)
    command = parse_command(text)
    actions = plan(grid, command)
    drill = next(a for a in actions if a["op"] == "place" and "drill" in a["building"])
    hướng = classify(drill["x"], drill["y"])
    print(f"> {text!r}\n  parse hint: {command.get('ore_location_hint')}\n  đặt tại ({drill['x']},{drill['y']}) -> phía {hướng}\n")


print("=== Không chỉ định (mặc định) -- 4 mỏ cách đều, sẽ chọn theo thứ tự quét trong số các mỏ gần nhau ===")
run("xây máy khoan khai thác than")

print("=== Chỉ định theo hướng -- phải ra đúng mỏ hướng đó ===")
run("xây máy khoan than phía đông")
run("xây máy khoan than phía nam")
run("xây máy khoan than phía tây")
run("xây máy khoan than phía bắc")

print("=== Chỉ định theo toạ độ cụ thể ===")
run("xây máy khoan than tại (6,15)")

print("=== Chỉ định theo thứ tự (gần core nhất theo Manhattan) ===")
run("xây máy khoan than thứ nhất")
