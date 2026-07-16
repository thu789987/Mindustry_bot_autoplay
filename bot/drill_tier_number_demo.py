"""Chứng minh bug thật (user tự phát hiện qua chạy lệnh thật): "drill cấp 4
đào chì" trước đây bị command_parser.py ÂM THẦM bỏ qua số tier, rớt về
sentinel "drill" chung -> select_drill_type() tự chọn tier RẺ NHẤT đủ dùng
(mechanical-drill, tier=2), phớt lờ hoàn toàn yêu cầu "cấp 4" của người
dùng. Đã sửa: TIER_RE bắt "cấp N"/"tier N", DRILL_TIER_NAMES map đúng tên
drill theo tier thật (xem simulator/generated_catalog.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command

print("--- Trước khi sửa: 'drill cấp 4 đào chì' sẽ ra sentinel 'drill' (SAI) ---")
print("--- Sau khi sửa: phải ra đúng 'laser-drill' (tier 4 thật) ---\n")

cases = [
    ("sử dụng drill cấp 4 đào chì cho tôi", "laser-drill", "lead"),
    ("xây drill tier 4 đào than", "laser-drill", "coal"),
    ("xây drill cấp 2 đào đồng", "mechanical-drill", "copper"),
    ("xây drill cấp 7 đào titan", "eruption-drill", "titanium"),
    # Xung đột: tên nói laser (tier 4), số nói rõ cấp 2 -- số phải THẮNG
    # (người dùng nói rõ số sau, coi là ý cuối cùng/chính xác hơn).
    ("máy khoan laser cấp 2 đào đồng", "mechanical-drill", "copper"),
    # Không có số -- hành vi CŨ (auto-select rẻ nhất đủ dùng) không đổi.
    ("xây máy khoan than", "drill", "coal"),
]

for text, expected_building, expected_ore in cases:
    cmd = parse_command(text)
    print(f"'{text}'\n  -> {cmd}")
    assert cmd["building"] == expected_building, f"SAI: kỳ vọng building='{expected_building}', ra '{cmd['building']}'"
    assert cmd["ore_target"] == expected_ore, f"SAI: kỳ vọng ore_target='{expected_ore}', ra '{cmd['ore_target']}'"
    print("  ĐÚNG.\n")

print("XÁC NHẬN: 'cấp N'/'tier N' giờ ép đúng tier drill thật, số nói rõ luôn")
print("thắng khi xung đột với tên, và không nói số thì vẫn auto-select như cũ.")
