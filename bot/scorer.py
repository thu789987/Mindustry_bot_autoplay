"""Cách 3 -- preference learning thật: 1 bộ chấm điểm tuyến tính có trọng số
cập nhật dần từ các cặp so sánh (bạn chê A, chọn B), khác Cách 1 (luật cứng
cố định) ở chỗ nó tổng quát hoá sang tình huống chưa từng gặp thay vì chỉ áp
dụng đúng luật đã viết, và khác Cách 2 (LLM context) ở chỗ nó không phụ
thuộc cửa sổ ngữ cảnh hay mô hình ngôn ngữ -- chỉ là 1 vector số nhỏ.
"""

import json
from pathlib import Path

WEIGHTS_PATH = Path(__file__).resolve().parent / "scorer_weights.json"

# Mặc định: ưu tiên belt ngắn, không quan tâm khoảng cách core (dấu âm vì
# "lớn hơn" ở 2 đặc trưng này là xấu hơn -> điểm thấp hơn).
# drill_tier âm -> mặc định chọn tier RẺ NHẤT đủ dùng (khớp hành vi
# select_drill_type() khi scorer=None), user chê "rẻ quá" nhiều lần sẽ dịch
# trọng số này dương dần, tự nghiêng sang tier cao hơn cho tình huống tương tự.
DEFAULT_WEIGHTS = {
    "total_belt_length": -1.0,
    "distance_to_core": 0.0,
    "drill_tier": -1.0,
}


class Scorer:
    def __init__(self, weights: dict = None):
        self.weights = dict(weights) if weights is not None else dict(DEFAULT_WEIGHTS)

    @classmethod
    def load(cls, path: Path = WEIGHTS_PATH) -> "Scorer":
        if path.exists():
            return cls(json.loads(path.read_text(encoding="utf-8")))
        return cls()

    def save(self, path: Path = WEIGHTS_PATH):
        path.write_text(json.dumps(self.weights, indent=2), encoding="utf-8")

    def score(self, features: dict) -> float:
        return sum(self.weights.get(k, 0.0) * v for k, v in features.items())

    def update(self, features_win: dict, features_lose: dict, learning_rate: float = 0.5):
        """Cập nhật kiểu perceptron theo cặp so sánh: nếu score(win) chưa vượt
        score(lose) đủ 1 khoảng margin, dịch trọng số theo hướng
        features(win) - features(lose) để lần sau win được chấm cao hơn."""
        margin = self.score(features_win) - self.score(features_lose)
        if margin >= 1.0:
            return  # đã phân biệt đủ rõ, không cần cập nhật
        keys = set(features_win) | set(features_lose)
        for k in keys:
            delta = features_win.get(k, 0.0) - features_lose.get(k, 0.0)
            self.weights[k] = self.weights.get(k, 0.0) + learning_rate * delta
