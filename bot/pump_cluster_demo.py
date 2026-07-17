"""Chứng minh: "xây N máy bơm nước" giờ đặt ĐÚNG N pump, xếp SÁT NHAU thành
hàng (không rải rác), dùng CHUNG 1 đường ống (conduit merge tự do từ bất kỳ
cạnh nào -- không cần liquid-router chỉ để GOM nhiều nguồn vào 1 đích, khác
hẳn việc CHIA 1 nguồn ra nhiều đích mới cần router, xem
_route_or_branch_from_producer) -- thay vì luôn chỉ đặt đúng 1 pump bất kể
số người dùng nói ra bao nhiêu (bug thật đã verify: "xây 5 máy bơm nước"
trước đây bỏ qua hẳn số "5", xem NEXT_STEPS.md mục audit Liquid Blocks).

User: "bot có biết tự đặt pump sát nhau và tối ưu đường dẫn nước không" ->
"Tôi muốn" (xác nhận làm cơ chế cụm pump, giống generator cluster).

Bug thật phát hiện + sửa khi làm tính năng này (verify TRƯỚC khi merge):
_route_or_branch_from_producer() trước đây coi "producer đã có belt/conduit
dẫn đi nơi khác" và "chuỗi đó dẫn tới ô TRỐNG (dangling, chưa nối đâu cả)"
là CÙNG 1 trường hợp lỗi -- nhưng lane chung của cụm pump vừa xây CỐ Ý
dangling (như "bơm nước" 1-pump vốn không tự nối đi đâu, chỉ chờ nơi khác
tới dùng). Sửa bằng _dangling_belt_end() (mới, phân biệt rõ "dẫn tới building
thật" vs "dẫn tới ô trống") -- dangling thì NỐI TIẾP từ đó, không phải lỗi."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout


print("--- Kịch bản 1: 'xây 5 máy bơm nước' -- 5 pump SÁT NHAU, dùng chung 1 lane conduit ---")
FAKE_STATE_1 = {
    "width": 40, "height": 30,
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 20) for y in range(2, 6)],
    "buildings": [{"type": "core", "x": 35, "y": 15, "rotation": 0}],
}
grid1 = grid_from_state(FAKE_STATE_1)
cmd1 = parse_command("xây 5 máy bơm nước")
print(f"  parsed: {cmd1}")
actions1 = plan_build(grid1, cmd1)
n_pump_1 = sum(1 for a in actions1 if a.get("building") == "mechanical-pump")
assert n_pump_1 == 5, f"SAI: phải đặt đúng 5 pump, ra {n_pump_1}"

pumps_1 = [b for b in grid1.unique_buildings() if b.type.kind == "pump"]
ys = {p.y for p in pumps_1}
print(f"  toạ độ: {sorted((p.x, p.y) for p in pumps_1)}")
assert len(ys) == 1, "SAI: 5 pump phải xếp sát nhau cùng 1 hàng khi bồn đủ rộng"

conduit_tiles_1 = {(a["x"], a["y"]) for a in actions1 if a.get("building") == "conduit"}
for p in pumps_1:
    assert p.output_tile() in conduit_tiles_1, f"SAI: pump @({p.x},{p.y}) không đổ vào lane chung"
print("  ĐÚNG: 5 pump xếp thành 1 hàng sát nhau, tất cả đổ vào cùng 1 lane conduit chung.\n")


print("--- Kịch bản 2: cụm pump vừa xây được TÁI SỬ DỤNG (steam-generator không xây pump thứ 6) ---")
FAKE_STATE_2 = {
    "width": 40, "height": 30,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 8) for y in range(20, 26)],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 20) for y in range(2, 6)],
    "buildings": [{"type": "core", "x": 35, "y": 15, "rotation": 0}],
}
grid2 = grid_from_state(FAKE_STATE_2)
plan_build(grid2, parse_command("xây 5 máy bơm nước"))
n_pump_before = sum(1 for b in grid2.unique_buildings() if b.type.kind == "pump")
plan_build(grid2, parse_command("nhà máy điện hơi nước"))
n_pump_after = sum(1 for b in grid2.unique_buildings() if b.type.kind == "pump")
print(f"  pump trước/sau: {n_pump_before}/{n_pump_after}")
assert n_pump_before == n_pump_after == 5, "SAI: steam-generator phải tái sử dụng cụm có sẵn, không xây thêm"
gen2 = next(b for b in grid2.unique_buildings() if b.type.name == "steam-generator")
result2 = evaluate_layout(grid2)
assert result2["power_production"].get(gen2, 0) > 0
print("  ĐÚNG: tái sử dụng cụm 5 pump có sẵn qua lane chung, không xây pump thứ 6, vẫn chạy được.\n")


print("--- Kịch bản 3: bồn hẹp -- cụm pump WRAP qua NHIỀU hàng, vẫn gộp thành 1 đường LIÊN TỤC ---")
FAKE_STATE_3 = {
    "width": 40, "height": 40,
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 6) for y in range(2, 20)],
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(15, 21) for y in range(25, 31)],
    "buildings": [{"type": "core", "x": 30, "y": 15, "rotation": 0}],
}
grid3 = grid_from_state(FAKE_STATE_3)
actions3 = plan_build(grid3, parse_command("xây 5 máy bơm nước"))
n_pump_3 = sum(1 for a in actions3 if a.get("building") == "mechanical-pump")
pumps_3 = [b for b in grid3.unique_buildings() if b.type.kind == "pump"]
rows_3 = sorted({p.y for p in pumps_3})
print(f"  pump đặt: {n_pump_3}, số hàng: {len(rows_3)} ({rows_3})")
assert n_pump_3 == 5
assert len(rows_3) > 1, "SAI: bồn hẹp phải buộc wrap qua nhiều hàng"

# Xac nhan CA CUM (du wrap nhieu hang) van la 1 duong LIEN TUC -- xay tiep
# steam-generator, phai tai su dung DUNG 5 pump nay (khong xay them), va
# thuc su nhan duoc nuoc (chung minh cac hang da noi lien nhau, khong phai
# nhieu cum tach roi khong lien quan).
actions_gen3 = plan_build(grid3, parse_command("nhà máy điện hơi nước"))
n_pump_after_3 = sum(1 for b in grid3.unique_buildings() if b.type.kind == "pump")
gen3 = next(b for b in grid3.unique_buildings() if b.type.name == "steam-generator")
result3 = evaluate_layout(grid3)
print(f"  pump sau khi xây steam-generator: {n_pump_after_3} (kỳ vọng vẫn {n_pump_3})")
print(f"  power_production: {result3['power_production'].get(gen3)}")
assert n_pump_after_3 == n_pump_3, "SAI: không được xây thêm pump dù cụm wrap nhiều hàng"
assert result3["power_production"].get(gen3, 0) > 0, "SAI: cụm nhiều hàng phải là 1 đường LIÊN TỤC, không phải nhiều cụm tách rời"
print("  ĐÚNG: cụm 5 pump wrap qua nhiều hàng vẫn gộp thành 1 đường ống liên tục, dùng được.\n")


print("--- Kịch bản 4: cụm pump tier mạnh hơn ('xây 2 bơm ly tâm nước') -- mỗi cái tự cấp điện ---")
FAKE_STATE_4 = {
    "width": 100, "height": 100,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(50, 90) for y in range(50, 90)],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "water"} for x in range(2, 30) for y in range(2, 10)],
    "buildings": [{"type": "core", "x": 65, "y": 30, "rotation": 0}],
}
grid4 = grid_from_state(FAKE_STATE_4)
actions4 = plan_build(grid4, parse_command("xây 2 bơm ly tâm nước"))
n_rotary = sum(1 for a in actions4 if a.get("building") == "rotary-pump")
print(f"  rotary-pump đặt: {n_rotary}")
assert n_rotary == 2
result4 = evaluate_layout(grid4)
for r in (b for b in grid4.unique_buildings() if b.type.name == "rotary-pump"):
    sat = result4["power_satisfaction"].get(r)
    print(f"  rotary-pump @({r.x},{r.y}) power_satisfaction={sat}")
    assert sat == 1.0, f"SAI: rotary-pump @({r.x},{r.y}) phải được cấp điện đủ"
print("  ĐÚNG: cụm pump tier mạnh hơn cũng đặt đúng số lượng + tự cấp điện đủ.\n")


print("XÁC NHẬN: 'xây N máy bơm nước' giờ đặt đúng N pump, xếp sát nhau thành")
print("hàng (wrap nhiều hàng nếu bồn hẹp), TẤT CẢ dùng chung 1 đường ống duy")
print("nhất -- sẵn sàng để mọi nơi khác (generator/factory/drill boost) tái")
print("sử dụng qua find_liquid_producer, không xây thêm pump thừa.")
print()
print("Giới hạn đã biết: cụm pump dùng tier TỐN ĐIỆN (rotary/impulse) với số")
print("lượng LỚN có thể chạm giới hạn sẵn có của _ensure_powered() -- mỗi lần")
print("gọi tự xây 1 combustion-generator+coal-drill RIÊNG nếu lưới hiện có")
print("chưa đủ công suất, có thể va chạm không gian khi gọi liên tiếp nhiều")
print("lần trong 1 cụm chật hẹp (đã verify: 3 rotary-pump/1 hàng có thể lỗi,")
print("2 thì luôn ổn) -- xem NEXT_STEPS.md.")
