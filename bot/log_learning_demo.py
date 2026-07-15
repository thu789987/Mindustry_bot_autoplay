"""Chứng minh bot/log_learning.py hoạt động đúng -- dùng LẠI chính kịch bản
đã xác nhận đúng trong bot/learn_demo.py (chê (4,7), thích (3,6), cùng độ dài
belt nhưng xa core hơn) làm "đáp án đúng" để so sánh, thay vì phải đoán kết
quả mới.

KHÔNG có log thật (chưa có mod ghi log, xem NEXT_STEPS.md) -- log ở đây được
DỰNG bằng cách tái dùng đúng các hàm nội bộ của bot/planner.py
(_route/_connect_to_core/_ensure_powered) để tự nối belt + điện cho
silicon-smelter tại (3,6), mô phỏng 1 người chơi thật đặt xong rồi tự nối
tiếp -- không phải chỉ 1 hành động "place" rời rạc (thử trước, chỉ "place"
suông không đủ để evaluate_layout() thấy điểm tăng, vì chưa có belt nối tới
core -- lộ đúng vấn đề thật của log chơi thật: quyết định placement và việc
nối dây thường là NHIỀU hành động rời nhau, không phải 1 hành động duy nhất)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.planner import CATALOG, _connect_to_core, _ensure_powered, _route, find_producer
from bot.log_learning import extract_feedback_from_log
from bot.planner import plan_build
from bot.scorer import Scorer
from bot.state import grid_from_state

FAKE_STATE = {
    "width": 30, "height": 20,
    "ore_tiles": [
        {"x": 2, "y": 2, "ore": "coal"}, {"x": 3, "y": 2, "ore": "coal"},
        {"x": 2, "y": 3, "ore": "coal"}, {"x": 3, "y": 3, "ore": "coal"},
        # mỏ than thứ 2 riêng cho combustion-generator (silicon-smelter thật
        # cần điện, xem NEXT_STEPS.md -- _ensure_powered tự đặt drill than
        # MỚI, không tranh chấp router với drill than có sẵn).
        {"x": 20, "y": 15, "ore": "coal"}, {"x": 21, "y": 15, "ore": "coal"},
        {"x": 20, "y": 16, "ore": "coal"}, {"x": 21, "y": 16, "ore": "coal"},
        {"x": 2, "y": 10, "ore": "sand"}, {"x": 3, "y": 10, "ore": "sand"},
        {"x": 2, "y": 11, "ore": "sand"}, {"x": 3, "y": 11, "ore": "sand"},
    ],
    "buildings": [
        {"type": "mechanical-drill", "x": 2, "y": 2, "rotation": 0, "ore_target": "coal"},
        {"type": "mechanical-drill", "x": 2, "y": 10, "rotation": 0, "ore_target": "sand"},
        {"type": "core", "x": 10, "y": 7, "rotation": 0},
    ],
}


def build_player_log(spot):
    """Dựng log HOÀN CHỈNH (place + belt input + belt output + điện) cho việc
    tự tay đặt silicon-smelter tại `spot`, tái dùng nguyên các hàm nội bộ
    planner.py đã kiểm chứng -- mô phỏng đúng 1 người chơi đặt xong rồi tự
    nối belt/điện, không phải chỉ đoán toạ độ suông."""
    grid = grid_from_state(FAKE_STATE)
    actions = []
    building_type = CATALOG["silicon-smelter"]
    tx, ty = spot
    new_b = grid.place(building_type, tx, ty, rotation=0)
    actions.append({"op": "place", "building": "silicon-smelter", "x": tx, "y": ty, "rotation": 0})
    footprint = new_b.footprint()
    for item_name in building_type.recipe.inputs:
        producer = find_producer(grid, item_name)
        _route(grid, actions, producer.output_tile(), footprint, CATALOG["conveyor"], f"không nối được {item_name}")
    _connect_to_core(grid, actions, new_b, "đã xây silicon-smelter")
    _ensure_powered(grid, actions, new_b, near=spot)
    return actions


LOG = build_player_log((3, 6))

print("=== Bước 1: chưa học gì -- plan_build() sẽ đề xuất đâu? ===")
scorer = Scorer()  # sạch từ đầu, không load từ đĩa
grid_before = grid_from_state(FAKE_STATE)
actions_before = plan_build(grid_before, {"action": "build", "building": "silicon-smelter"}, scorer=scorer)
default_spot = next((a["x"], a["y"]) for a in actions_before if a["building"] == "silicon-smelter")
print(f"  trọng số: {scorer.weights}")
print(f"  bot đề xuất: {default_spot}")

print(f"\n=== Bước 2: phát lại log ({len(LOG)} dòng, mô phỏng bạn tự đặt + tự nối tại (3,6)) ===")
n_pairs = extract_feedback_from_log(FAKE_STATE, LOG, scorer)
print(f"  đã tự tạo {n_pairs} cặp feedback")
print(f"  trọng số sau: {scorer.weights}")

assert n_pairs == 1, f"SAI: phải tự tạo đúng 1 cặp feedback (bot đề xuất khác vị trí bạn chọn), ra {n_pairs}"

print("\n=== Bước 3: replan CÙNG lệnh, CÙNG state gốc -- có đổi theo log không? ===")
grid_after = grid_from_state(FAKE_STATE)
actions_after = plan_build(grid_after, {"action": "build", "building": "silicon-smelter"}, scorer=scorer)
new_spot = next((a["x"], a["y"]) for a in actions_after if a["building"] == "silicon-smelter")
print(f"  bot đề xuất sau khi học từ log: {new_spot}")

assert new_spot == (3, 6), f"SAI: sau khi học từ log, bot phải đề xuất đúng vị trí bạn từng chọn trong log (3,6), ra {new_spot}"
print("\nXÁC NHẬN: bot tự rút ra đúng 1 cặp so sánh từ log (không cần bạn tự tay")
print("chê/khen), và sau khi học, đề xuất tiếp theo khớp ĐÚNG bằng chính lựa chọn")
print("thật của bạn trong log -- kết quả khớp y hệt bot/learn_demo.py (học thủ công),")
print("chỉ khác là lần này bot TỰ rút ra được cặp so sánh từ log, không cần bạn tự chê/khen.")
