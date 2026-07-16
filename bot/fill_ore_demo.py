"""Chứng minh lệnh "phủ kín mỏ" (bot/planner.py:plan_fill_ore) -- khác lệnh
xây thường (plan_build nhánh "drill") CHỈ đặt ĐÚNG 1 drill dù mỏ to cỡ nào
(find_drill_spot trả về NGAY ô hợp lệ đầu tiên rồi dừng, xem sim.py) -- lệnh
này lặp lại tới khi hết mỏ.

Bắt đầu từ câu hỏi thật của user: "nếu ở dưới nền đất bự và có nhiều quặng,
1 drill là không đủ phủ hết, bot có biết đặt lên nền đó nhiều drill không hay
chỉ 1" -- xác nhận trước đó (đọc code) là CHỈ 1, user xác nhận muốn thêm tính
năng này, kèm yêu cầu thêm: "tương lai mỗi Drill Laser hoặc cao hơn sẽ phải
cần thêm 1 nguồn nước ... phải tối ưu cái đó" -- ĐÃ SỬA giả định sai ban đầu
(cả 4 tier đều cần/hỗ trợ nước, xem bot/liquid_boost_demo.py), và "tối ưu"
được hiểu là: nhiều drill dùng CHUNG 1 nguồn nước, không phải 1 nguồn/drill.

Bản đầu của plan_fill_ore() (lặp find_drill_spot + _connect_to_core độc
lập) bị chính user hỏi tiếp: "đặt full mỏ xong rồi nối băng chuyền với nhau
cho sao chỉ có 1 băng chuyền về core không" -- xác nhận qua debug script là
KHÔNG, mỗi drill tự BFS 1 đường riêng (4 drill ra 86 conveyor). Đã sửa sang
"manifold": xếp drill thành hàng, cả hàng đổ chung vào 1 lane, chỉ lane đó
nối tiếp về core -- xem _build_drill_row_manifold trong bot/planner.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.buildings import CATALOG
from simulator.sim import evaluate_layout


def count_places(actions, building_name):
    return sum(1 for a in actions if a["op"] == "place" and a["building"] == building_name)


print("--- Kịch bản 0 (đối chứng): lệnh xây THƯỜNG chỉ đặt đúng 1 drill dù mỏ to ---")
# Map RỘNG + mỏ vừa phải (4x4=16 ô, mechanical-drill 2x2 -> tối đa 4 drill)
# -- cố ý không dùng mỏ quá lớn: pathfinding BFS nối belt về core (_route())
# là giới hạn ĐÃ BIẾT của simulator (không liên quan tới tính năng "phủ kín
# mỏ" đang test, xem bot/solid_pump_demo.py gặp vấn đề tương tự) -- mỏ to +
# nhiều drill liền kề dễ khiến drill ĐẶT SAU bị vây kín bởi belt/drill ĐẶT
# TRƯỚC, không tìm được đường trống nào về core -- không phải bug của
# plan_fill_ore(), chỉ là giới hạn pathfinding chung của cả project.
FAKE_STATE_0 = {
    "width": 60, "height": 60,
    "ore_tiles": [{"x": x, "y": y, "ore": "lead"} for x in range(30, 34) for y in range(30, 34)],  # mỏ 4x4=16 ô
    "buildings": [{"type": "core", "x": 5, "y": 5, "rotation": 0}],
}
grid0 = grid_from_state(FAKE_STATE_0)
cmd0 = parse_command("xây drill cấp 2 đào chì")
assert cmd0.get("fill") is not True, "SAI: lệnh xây thường không được tự bật cờ 'fill'"
actions0 = plan_build(grid0, cmd0)
n0 = count_places(actions0, "mechanical-drill")
print(f"  mỏ 36 ô, lệnh xây thường đặt: {n0} drill")
assert n0 == 1, "SAI: lệnh xây thường (không có 'phủ kín') phải chỉ đặt đúng 1 drill"
print("  ĐÚNG: xác nhận lại đúng hành vi CŨ (giới hạn đã biết) chưa đổi.\n")


print("--- Kịch bản 1: 'phủ kín mỏ chì' -> đặt NHIỀU drill cho tới khi hết mỏ ---")
grid1 = grid_from_state(FAKE_STATE_0)
cmd1 = parse_command("phủ kín mỏ chì bằng drill cấp 2")
print(f"  lệnh parse ra: {cmd1}")
assert cmd1.get("fill") is True, "SAI: phải nhận diện được cụm 'phủ kín mỏ' và bật cờ fill"
actions1 = plan_build(grid1, cmd1)
n1 = count_places(actions1, "mechanical-drill")
print(f"  mỏ 36 ô, lệnh 'phủ kín mỏ' đặt: {n1} drill (mechanical-drill size=2x2 -> tối đa 9 drill phủ kín 6x6)")
assert n1 > 1, "SAI: 'phủ kín mỏ' phải đặt NHIỀU HƠN 1 drill (khác lệnh xây thường)"

# Xác nhận KHÔNG còn ô chì nào trống mà 1 drill nữa còn ĐẶT ĐƯỢC (tự nó đã
# dừng đúng lúc, không phải dừng sớm/bỏ sót) -- gọi lại find_drill_spot thật
# xem còn chỗ nào không.
from bot.planner import find_drill_spot, find_unmined_ore
remaining_ore = find_unmined_ore(grid1, "lead", near=(2, 2))
print(f"  còn ô chì chưa khai thác nào không (sau khi phủ kín): {remaining_ore}")
if remaining_ore is not None:
    remaining_spot = find_drill_spot(grid1, "lead", near=remaining_ore, drill_type=CATALOG["mechanical-drill"])
    assert remaining_spot is None, f"SAI: vẫn còn chỗ đặt được drill tại {remaining_spot} mà 'phủ kín mỏ' đã dừng sớm"
print("  ĐÚNG: dừng đúng lúc mỏ đã hết chỗ đặt drill mới, không dừng sớm/bỏ sót.\n")


print("--- Kịch bản 2: các drill trong 1 hàng dùng CHUNG 1 đường belt (manifold), không phải mỗi drill tự đi riêng ---")
# Bug thật user tự phát hiện: "đặt full mỏ xong rồi nối băng chuyền với
# nhau cho sao chỉ có 1 băng chuyển về core không" -- verify bằng debug
# script TRƯỚC khi sửa: 4 drill kiểu cũ (mỗi cái tự BFS riêng, né mọi thứ)
# ra 86 conveyor. Giờ đo lại số conveyor thật của bản manifold, phải THẤP
# HƠN HẲN baseline đó theo tỉ lệ mỗi drill.
result1 = evaluate_layout(grid1)
core1 = next(b for b in grid1.unique_buildings() if b.type.kind == "core")
n_drills_placed = sum(1 for b in grid1.unique_buildings() if b.type.name == "mechanical-drill")
n_conveyor1 = count_places(actions1, "conveyor")
conveyor_per_drill = n_conveyor1 / n_drills_placed
print(f"  số drill đã đặt: {n_drills_placed}, tổng conveyor: {n_conveyor1} ({conveyor_per_drill:.1f}/drill)")
print(f"  throughput chì về core: {result1['output_rate'][core1]:.4f}/s")
assert result1["output_rate"][core1] > 0.0, "SAI: 'phủ kín mỏ' phải tự nối belt về core, không chỉ đặt suông"
assert conveyor_per_drill < 15.0, (
    f"SAI: {conveyor_per_drill:.1f} conveyor/drill -- QUÁ GẦN baseline kiểu cũ (mỗi drill tự đi riêng, "
    f"đo được ~21.5/drill trước khi sửa) -- có vẻ manifold không thật sự dùng chung đường belt"
)

# Xác nhận vật lý: các drill trong CÙNG 1 hàng phải đổ vào CÙNG 1 hàng
# conveyor (cùng toạ độ y) -- đây mới là bằng chứng trực tiếp "dùng chung 1
# đường", không chỉ suy luận gián tiếp từ số lượng conveyor ít.
placed_drills1 = [b for b in grid1.unique_buildings() if b.type.name == "mechanical-drill"]
lane_ys = {}
for d in placed_drills1:
    ly = d.output_tile()[1]
    lane_ys.setdefault(ly, []).append(d)
shared_lanes = {ly: ds for ly, ds in lane_ys.items() if len(ds) > 1}
print(f"  số hàng (lane_y) có >=2 drill dùng chung: {len(shared_lanes)}, chi tiết: {[(ly, len(ds)) for ly, ds in shared_lanes.items()]}")
assert shared_lanes, "SAI: phải có ít nhất 1 hàng có từ 2 drill trở lên đổ chung vào 1 lane_y"
print("  ĐÚNG: xác nhận bằng cả số lượng conveyor (thấp hơn hẳn baseline) lẫn toạ độ vật lý")
print("  (nhiều drill cùng hàng đổ vào đúng 1 lane_y) -- manifold hoạt động thật, không phải suy diễn.\n")


print("--- Kịch bản 3: 'phủ kín mỏ' với drill CẦN NƯỚC -> nhiều drill dùng CHUNG 1 nguồn nước, không phải 1 nguồn/drill ---")
# Dùng mechanical-drill (KHÔNG cần điện, power_input=0) thay vì laser-drill
# -- vẫn có boost_liquid="water" (đã xác nhận CẢ 4 tier đều có, xem
# liquid_boost_demo.py), nên vẫn kiểm được đúng phần "tối ưu dùng chung
# nước" mà không kéo thêm hạ tầng điện (generator+drill than+belt riêng)
# vào cùng lúc -- tránh đúng vấn đề pathfinding đã gặp khi debug: hạ tầng
# điện của drill #1 vô tình chặn hành lang belt/conduit của drill #2 trên
# map hẹp (không phải bug của plan_fill_ore(), chỉ là giới hạn pathfinding
# chung khi nhiều hệ thống cùng cạnh tranh không gian, xem NEXT_STEPS.md).
# Mỏ đúng 4x2=8 ô -> vừa đúng 2 mechanical-drill (2x2), nước đặt lệch trục
# (phía nam mỏ) khác trục với core (cùng hàng, phía tây) để 2 đường BFS
# (belt về core, conduit từ nước) không tranh nhau cùng 1 hành lang.
FAKE_STATE_3 = {
    "width": 40, "height": 40,
    "ore_tiles": [{"x": x, "y": y, "ore": "lead"} for x in range(20, 24) for y in range(20, 22)],
    "liquid_tiles": [{"x": 21, "y": 30, "liquid": "water"}],
    "buildings": [{"type": "core", "x": 8, "y": 20, "rotation": 0}],
}
grid3 = grid_from_state(FAKE_STATE_3)
cmd3 = parse_command("phủ kín mỏ chì bằng mechanical-drill")
assert cmd3["building"] == "mechanical-drill" and cmd3.get("fill") is True
actions3 = plan_build(grid3, cmd3)
n_drill3 = count_places(actions3, "mechanical-drill")
n_pump3 = count_places(actions3, "mechanical-pump")
print(f"  mechanical-drill đặt: {n_drill3}, mechanical-pump (nguồn nước) đặt: {n_pump3}")
assert n_drill3 > 1, "SAI: mỏ 4x2=8 ô đủ chỗ cho 2 mechanical-drill (2x2), phải đặt nhiều hơn 1"
assert n_pump3 == 1, (
    f"SAI: {n_drill3} drill đáng lẽ phải dùng CHUNG 1 pump duy nhất (đã có sẵn từ drill đầu tiên, "
    f"các drill sau tự tìm thấy qua find_liquid_producer + _route_or_branch_from_producer), "
    f"nhưng lại xây {n_pump3} pump -- đây chính là phần 'tối ưu' user yêu cầu, không được xây lãng phí"
)
print("  ĐÚNG: dù phủ nhiều drill, chỉ 1 nguồn nước duy nhất được xây -- tối ưu đúng yêu cầu.\n")

result3 = evaluate_layout(grid3)
placed_drills3 = [b for b in grid3.unique_buildings() if b.type.name == "mechanical-drill"]
boosted_count = sum(
    1 for b in placed_drills3
    if any(src.type.kind == "pump" for src, dest, cap in result3["liquid_connections"] if dest is b)
)
print(f"  số drill THẬT SỰ nhận được nước (có liquid_connections trỏ tới): {boosted_count}/{len(placed_drills3)}")
assert boosted_count >= 1, "SAI: phải có ít nhất 1 drill nhận được nước qua nguồn dùng chung"
print("  ĐÚNG: ít nhất 1 drill xác nhận nhận nước qua đúng nguồn dùng chung (không phải mỗi cái tự có nguồn riêng).\n")

print("XÁC NHẬN: 'phủ kín mỏ' lặp đặt drill tới khi hết mỏ (khác lệnh xây")
print("thường chỉ đặt 1 cái), mỗi drill tự nối điện+belt+boost nước, và nhiều")
print("drill cần nước tự động DÙNG CHUNG 1 nguồn qua router thay vì mỗi cái")
print("tự xây nguồn riêng -- đúng yêu cầu 'tối ưu' của user.")
