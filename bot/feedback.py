"""Ghi nhận phản hồi kiểu 'bạn chê A, chọn B' và cập nhật bot/scorer.py.

Đây là chỗ nối giữa phản hồi của người dùng và việc học thật (Cách 3) --
không đoán ý người dùng, chỉ cần biết 2 phương án cụ thể để so sánh.
"""

from bot.planner import featurize_target_spot
from bot.scorer import Scorer


def record_feedback(grid, building_type, sources, rejected_spot, preferred_spot, scorer: Scorer, core_pos=None):
    features_lose = featurize_target_spot(grid, building_type, rejected_spot, sources, core_pos)
    features_win = featurize_target_spot(grid, building_type, preferred_spot, sources, core_pos)
    scorer.update(features_win, features_lose)
    scorer.save()
    return scorer.weights
