import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.feedback import record_drill_tier_feedback
from bot.planner import plan
from bot.scorer import Scorer
from bot.state import grid_from_state
from simulator.buildings import CATALOG
from simulator.sim import evaluate_layout

TITANIUM_STATE = {
    "width": 20, "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "titanium"}, {"x": 3, "y": 2, "ore": "titanium"},
        {"x": 2, "y": 3, "ore": "titanium"}, {"x": 3, "y": 3, "ore": "titanium"},
    ],
    "buildings": [{"type": "core", "x": 10, "y": 10, "rotation": 0}],
}

COPPER_STATE = {
    "width": 20, "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "copper"}, {"x": 3, "y": 2, "ore": "copper"},
        {"x": 2, "y": 3, "ore": "copper"}, {"x": 3, "y": 3, "ore": "copper"},
    ],
    "buildings": [{"type": "core", "x": 10, "y": 10, "rotation": 0}],
}


def drill_action(actions):
    return next(a for a in actions if a["op"] == "place" and CATALOG[a["building"]].kind == "drill")


print("=== A: tự chọn tier -- khai thác titan (hardness=3, mechanical-drill tier=2 KHÔNG đủ) ===")
grid = grid_from_state(TITANIUM_STATE)
command = parse_command("xây máy khoan khai thác titan")
print(f"parse: {command}")
actions = plan(grid, command)
placed = drill_action(actions)
print(f"bot đặt: {placed['building']}")
result = evaluate_layout(grid)
drill_rate = next(rate for b, rate in result["output_rate"].items() if b.type.kind == "drill")
print(f"output thật (evaluate_layout): {drill_rate:.4f}/s -- {'ĐÚNG, mine được' if drill_rate > 0 else 'HỎNG, vẫn ra 0'}")

print("\n=== B1: chỉ định tier cụ thể -- 'pneumatic drill' cho than (hardness=2, không bắt buộc phải tier cao) ===")
grid2 = grid_from_state({**COPPER_STATE, "ore_tiles": [
    {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
    {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
]})
command_b1 = parse_command("xây máy khoan khí nén than")
print(f"parse: {command_b1}")
actions_b1 = plan(grid2, command_b1)
print(f"bot đặt: {drill_action(actions_b1)['building']} (đúng như chỉ định, dù mechanical-drill cũng đủ dùng)")

print("\n=== B2: chỉ định tier KHÔNG đủ -- 'máy khoan cơ bản' cho titan (phải báo lỗi, không đặt lặng lẽ) ===")
grid3 = grid_from_state(TITANIUM_STATE)
command_b2 = parse_command("xây máy khoan cơ bản khai thác titan")
print(f"parse: {command_b2}")
try:
    plan(grid3, command_b2)
    print("KHÔNG báo lỗi -- SAI, lẽ ra phải chặn")
except RuntimeError as e:
    print(f"LỖI (đúng như kỳ vọng): {e}")

print("\n=== C: học ưu tiên tier từ phản hồi -- khai thác đồng (hardness=1, mọi tier đều đủ) ===")
print("Đây là so sánh qua 6 tier cùng lúc (khác demo học vị trí trước chỉ so 2 ứng viên gần")
print("nhau) -- 1 lần phản hồi có thể CHƯA đủ lật thứ hạng, phải lặp lại tới khi thật sự đổi.")
print("Đây là hành vi ĐÚNG của học dần (không phải 'nhớ chết 1 lần'), không phải bug.\n")

scorer = Scorer()
command_c = parse_command("xây máy khoan khai thác đồng")
chosen = drill_action(plan(grid_from_state(COPPER_STATE), command_c, scorer=scorer))["building"]
print(f"[vòng 0, chưa phản hồi] trọng số drill_tier={scorer.weights['drill_tier']:.2f} -> chọn {chosen}")

round_n = 0
while chosen != "pneumatic-drill" and round_n < 10:
    round_n += 1
    record_drill_tier_feedback(CATALOG["mechanical-drill"], CATALOG["pneumatic-drill"], scorer)
    chosen = drill_action(plan(grid_from_state(COPPER_STATE), command_c, scorer=scorer))["building"]
    print(f"[sau phản hồi lần {round_n}] trọng số drill_tier={scorer.weights['drill_tier']:.2f} -> chọn {chosen}")

if chosen == "pneumatic-drill":
    print(f"\nXÁC NHẬN: sau {round_n} lần phản hồi liên tiếp, bot đổi hẳn sang pneumatic-drill,")
    print("và trọng số thật sự thay đổi (không phải nhớ cứng riêng lệnh 'khai thác đồng').")
else:
    print(f"\nCHƯA đổi sau {round_n} lần -- cần xem lại learning_rate hoặc thiết kế feature.")
