"""Cách 1 -- luật cứng do người dùng dạy dần, lưu bền, không phụ thuộc LLM
hay model học. Đóng vai trò BỘ LỌC: loại bỏ ứng viên vi phạm rõ ràng, trước
khi bot/scorer.py (Cách 3, học từ phản hồi) xếp hạng phần còn lại.
"""

import json
from pathlib import Path

PREFERENCES_PATH = Path(__file__).resolve().parent / "preferences.json"

DEFAULT_PREFERENCES = {
    "min_distance_from_core": 0,  # 0 = không giới hạn
}


def load_preferences(path: Path = PREFERENCES_PATH) -> dict:
    if path.exists():
        return {**DEFAULT_PREFERENCES, **json.loads(path.read_text(encoding="utf-8"))}
    return dict(DEFAULT_PREFERENCES)


def save_preferences(prefs: dict, path: Path = PREFERENCES_PATH):
    path.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")


def violates(grid, spot, prefs: dict) -> bool:
    """True nếu đặt building tại `spot` vi phạm 1 luật trong `prefs`."""
    min_dist = prefs.get("min_distance_from_core", 0)
    if min_dist > 0:
        core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
        if core is not None:
            tx, ty = spot
            distance = abs(tx - core.x) + abs(ty - core.y)
            if distance < min_dist:
                return True
    return False
