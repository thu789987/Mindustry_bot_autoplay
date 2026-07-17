"""Chứng minh bug thật user tự phát hiện + đã sửa: "máy phát điện rtg" (hay
bất kỳ generator KHÔNG được hỗ trợ nào khác trong audit "Power Blocks", xem
NEXT_STEPS.md) trước đây bị _find_building() âm thầm hiểu nhầm thành
combustion-generator -- vì "máy phát điện" (phrase generic) khớp trước khi
kịp xét "rtg" (marker cụ thể hơn nhưng NGẮN hơn, thua trong length-sort).

Sửa: _UNSUPPORTED_GENERATOR_MARKERS (rtg/thermal-generator/turbine-condenser/
flux-reactor/neoplasia-reactor/vent-condenser/diode) được check TRƯỚC vòng
lặp BUILDING_PHRASES thường, bất kể độ dài -- để plan_build() báo lỗi rõ
ràng thật sự CATALOG có building đó (SKIPPED, chưa có mechanic) thay vì âm
thầm xây nhầm."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state

print("--- Kịch bản 1: 'máy phát điện rtg' -- KHÔNG còn bị hiểu nhầm thành combustion-generator ---")
cmd = parse_command("máy phát điện rtg")
print(f"  {cmd}")
assert cmd["building"] == "rtg-generator", f"SAI: phải nhận ra 'rtg-generator', ra '{cmd['building']}'"
print("  ĐÚNG.\n")

print("--- Kịch bản 2: plan_build() báo lỗi RÕ RÀNG, không xây nhầm gì cả ---")
grid = grid_from_state({"width": 20, "height": 20, "buildings": [{"type": "core", "x": 10, "y": 10, "rotation": 0}]})
try:
    plan_build(grid, cmd)
    raise AssertionError("SAI: phải raise lỗi, không được xây thành công")
except ValueError as e:
    print(f"  lỗi: {e}")
    assert "rtg-generator" in str(e) and "chưa hỗ trợ" in str(e)
n_built = len(grid.unique_buildings())
print(f"  số building trên map: {n_built} (kỳ vọng 1 -- chỉ core, không xây nhầm gì)")
assert n_built == 1
print("  ĐÚNG.\n")

print("--- Kịch bản 3: các generator ĐÃ hỗ trợ không bị ảnh hưởng ---")
for phrase, expected in [
    ("nhà máy điện", "combustion-generator"),
    ("nhà máy điện hơi nước", "steam-generator"),
    ("nhà máy điện mặt trời", "solar-panel"),
    ("lò phản ứng thorium", "thorium-reactor"),
]:
    cmd2 = parse_command(phrase)
    print(f"  '{phrase}' -> {cmd2['building']}")
    assert cmd2["building"] == expected, f"SAI: '{phrase}' phải ra '{expected}', ra '{cmd2['building']}'"
print("  ĐÚNG: fix chỉ áp dụng cho 7 generator CHƯA hỗ trợ, không đụng gì tới cái đã hỗ trợ.\n")

print("--- Kịch bản 4: cả 7 marker đều nhận đúng tên CATALOG thật ---")
markers = {
    "rtg": "rtg-generator",
    "thermal-generator": "thermal-generator",
    "turbine-condenser": "turbine-condenser",
    "flux-reactor": "flux-reactor",
    "neoplasia": "neoplasia-reactor",
    "vent-condenser": "vent-condenser",
    "diode": "diode",
}
for marker, expected in markers.items():
    cmd3 = parse_command(f"xây {marker}")
    assert cmd3["building"] == expected, f"SAI: marker '{marker}' phải ra '{expected}', ra '{cmd3['building']}'"
print(f"  ĐÚNG: cả {len(markers)} marker đều nhận đúng.\n")

print("XÁC NHẬN: bot giờ KHÔNG BAO GIỜ âm thầm xây nhầm generator khi người dùng")
print("nói rõ tên 1 loại chưa được hỗ trợ -- luôn báo lỗi rõ ràng, không đoán bừa.")
