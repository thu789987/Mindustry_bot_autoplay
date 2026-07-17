"""Chứng minh 2 sửa lỗi pump này, đúng theo yêu cầu user:

1. "find_pump_spot() dò chỗ trống theo ĐÚNG kích thước pump thật sắp đặt"
   -- trước đây HARDCODE mechanical-pump (1x1) để dò, bất kể building THẬT
   SỰ sắp đặt là gì. Lệnh xây trực tiếp "bơm ly tâm nước" (rotary-pump,
   2x2) hay "bơm xung lực nước" (impulse-pump, 3x3) ở chỗ chật có thể tìm
   ra chỗ tưởng vừa (đủ cho 1x1) nhưng đặt thật lại lỗi "cannot place"
   (footprint to hơn thật).

2. User: "Logic đó không đúng, nếu như đã có 1 nguồn nước thì dùng bộ phân
   chia nguồn nước đã có ra làm 2, rồi 1 dẫn về steam-generator là được,
   không phải lúc nào cũng tạo nguồn nước mới" -- steam-generator trước đây
   LUÔN tìm tile nước CHƯA khai thác + xây pump MỚI, dù map đã có sẵn pump
   nào đó bơm đúng liquid cần. Sửa: ưu tiên TÁI SỬ DỤNG producer liquid có
   sẵn (find_liquid_producer), dùng _route_or_branch_from_producer() để tự
   đặt liquid-router CHIA nhánh nếu nguồn đó đã bận nối đi nơi khác -- đúng
   y hệt cơ chế đã có sẵn cho _try_boost_with_water (nước boost drill) và
   _find_or_build_factory_sources (liquid cho factory), chỉ là nhánh
   generator trước đây bỏ sót bước tái sử dụng này."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import find_pump_spot, plan_build
from bot.state import grid_from_state
from simulator.buildings import CATALOG, DIRECTIONS
from simulator.sim import evaluate_layout


print("--- Kịch bản 1: find_pump_spot dò ĐÚNG kích thước từng loại pump ---")
FAKE_STATE_1 = {
    "width": 20, "height": 20,
    "liquid_tiles": [{"x": 5, "y": 5, "liquid": "water"}],
    "buildings": [
        {"type": "core", "x": 15, "y": 15, "rotation": 0},
        # Bao quanh ô (5,5): chỉ vừa 1x1, KHÔNG vừa 2x2 (rotary-pump).
        {"type": "conveyor", "x": 4, "y": 5, "rotation": 0}, {"type": "conveyor", "x": 6, "y": 5, "rotation": 0},
        {"type": "conveyor", "x": 5, "y": 4, "rotation": 0}, {"type": "conveyor", "x": 4, "y": 4, "rotation": 0},
        {"type": "conveyor", "x": 6, "y": 4, "rotation": 0}, {"type": "conveyor", "x": 4, "y": 6, "rotation": 0},
        {"type": "conveyor", "x": 6, "y": 6, "rotation": 0},
    ],
}
grid1 = grid_from_state(FAKE_STATE_1)
spot_mech = find_pump_spot(grid1, "water", near=(5, 5), pump_type=CATALOG["mechanical-pump"])
spot_rotary = find_pump_spot(grid1, "water", near=(5, 5), pump_type=CATALOG["rotary-pump"])
print(f"  mechanical-pump (1x1): {spot_mech}")
print(f"  rotary-pump (2x2):     {spot_rotary}")
assert spot_mech == (5, 5), "SAI: mechanical-pump phải vừa đúng ô (5,5)"
assert spot_rotary != (5, 5), "SAI: rotary-pump (2x2) không được báo vừa ô đã bị bao vây chỉ đủ 1x1"
if spot_rotary is not None:
    assert grid1.can_place(CATALOG["rotary-pump"], *spot_rotary), "SAI: chỗ trả về phải THẬT SỰ đặt được"
print("  ĐÚNG: dò đúng size từng loại, không còn báo nhầm 1x1 đủ cho pump to hơn.\n")


print("--- Kịch bản 2: steam-generator tái sử dụng pump nước có sẵn (chưa bận) ---")
FAKE_STATE_2 = {
    "width": 40, "height": 30,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 8) for y in range(2, 8)],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(20, 26) for y in range(2, 8)],
    "buildings": [{"type": "core", "x": 30, "y": 15, "rotation": 0}],
}
grid2 = grid_from_state(FAKE_STATE_2)
plan_build(grid2, parse_command("bơm nước"))
existing_pump = next(b for b in grid2.unique_buildings() if b.type.kind == "pump")
actions2 = plan_build(grid2, parse_command("nhà máy điện hơi nước"))

n_pump_2 = sum(1 for b in grid2.unique_buildings() if b.type.kind == "pump")
conduit_tiles_2 = {(a["x"], a["y"]) for a in actions2 if a.get("building") == "conduit"}
out_tile_2 = existing_pump.output_tile()
touches_existing = out_tile_2 in conduit_tiles_2 or any(
    (out_tile_2[0] + dx, out_tile_2[1] + dy) in conduit_tiles_2 for dx, dy in DIRECTIONS
)
print(f"  pump sau khi xây steam-generator: {n_pump_2} (kỳ vọng vẫn 1, không xây thêm)")
print(f"  đường ống mới có xuất phát từ pump ĐÃ CÓ: {touches_existing}")
assert n_pump_2 == 1, f"SAI: phải tái sử dụng, có {n_pump_2} pump"
assert touches_existing, "SAI: đường ống phải xuất phát từ pump đã có, không phải pump khác"

gen2 = next(b for b in grid2.unique_buildings() if b.type.name == "steam-generator")
result2 = evaluate_layout(grid2)
assert result2["power_production"].get(gen2, 0) > 0
print("  ĐÚNG: dùng chung pump có sẵn, không xây pump mới, steam-generator vẫn chạy.\n")


print("--- Kịch bản 3: pump có sẵn ĐANG BẬN (đã nối 1 drill khác) -- phải CHIA qua liquid-router ---")
FAKE_STATE_3 = {
    "width": 60, "height": 40,
    "ore_tiles": [{"x": x, "y": y, "ore": "copper"} for x in range(2, 4) for y in range(2, 4)]
              + [{"x": x, "y": y, "ore": "coal"} for x in range(2, 8) for y in range(30, 36)],
    # Nước đặt phía NAM drill (khác hướng Đông drill đang quay mặt/output_tile
    # -- tránh xung đột vị trí với belt item cũng đi về core ở phía Đông).
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 4) for y in range(15, 17)],
    "buildings": [{"type": "core", "x": 45, "y": 20, "rotation": 0}],
}
grid3 = grid_from_state(FAKE_STATE_3)
plan_build(grid3, parse_command("khai thác đồng"))  # mechanical-drill boost_liquid=water -- tự xây pump + nối
n_pump_3a = sum(1 for b in grid3.unique_buildings() if b.type.kind == "pump")
assert n_pump_3a == 1

actions3 = plan_build(grid3, parse_command("nhà máy điện hơi nước"))
n_pump_3b = sum(1 for b in grid3.unique_buildings() if b.type.kind == "pump")
n_router_3 = sum(1 for a in actions3 if a.get("building") == "liquid-router")
print(f"  pump sau bước 2: {n_pump_3b} (kỳ vọng vẫn 1)")
print(f"  liquid-router đặt: {n_router_3} (kỳ vọng >= 1 -- pump cũ đã bận nối drill, phải CHIA)")
assert n_pump_3b == 1, f"SAI: không được xây pump thứ 2, có {n_pump_3b}"
assert n_router_3 >= 1, "SAI: pump đã bận -- phải có liquid-router chia nhánh cho steam-generator"

gen3 = next(b for b in grid3.unique_buildings() if b.type.name == "steam-generator")
drill3 = next(b for b in grid3.unique_buildings() if b.type.name == "mechanical-drill")
result3 = evaluate_layout(grid3)
print(f"  power_production steam-generator: {result3['power_production'].get(gen3):.4f}")
print(f"  drill rate (không bị 'cướp' hết nước): {result3['output_rate'].get(drill3):.4f}")
assert result3["power_production"].get(gen3, 0) > 0, "SAI: steam-generator phải chạy được"
assert result3["output_rate"].get(drill3, 0) > 0, "SAI: drill vẫn phải nhận được nước boost, không bị mất hẳn"
print("  ĐÚNG: 1 nguồn nước duy nhất CHIA cho cả drill lẫn steam-generator qua liquid-router,")
print("  không xây thêm pump nào, cả 2 đích đều hoạt động.\n")

print("XÁC NHẬN: cả 2 sửa đều đúng -- find_pump_spot dò đúng size building thật,")
print("và mọi nơi cần liquid giờ ưu tiên TÁI SỬ DỤNG + CHIA nguồn có sẵn qua")
print("liquid-router, chỉ xây pump mới khi map chưa có nguồn nào bơm đúng liquid đó.")
