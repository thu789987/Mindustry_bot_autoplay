"""Chứng minh lệnh "xây N máy phát điện" (bot/planner.py:
plan_build_generator_cluster) -- bắt đầu từ câu hỏi thật của user: "ví dụ
tôi nói bot tạo 21 máy phát điện siêu nhỏ thì bot có thể làm giống vậy
không? Bot biết được tự thiết lập đầu vào là than không? Hay bot sẽ xây
dựng 21 cái máy phát điện random và không biết đầu vào?" -- kèm 1
schematic .msch THẬT (user cung cấp base64, giải mã byte-khớp 722/722):
"Basic power plant V.1" -- 18 combustion-generator xếp 3 hàng, dùng CHUNG
1 điểm nhập than qua router, 2 power-node để tap điện ra ngoài.

Trước khi có tính năng này: lệnh xây generator thường (plan_build nhánh
"generator") CHỈ hỗ trợ 1 generator/lệnh, mỗi lệnh tự đào than RIÊNG -- gọi
21 lần sẽ ra 21 mỏ than khác nhau (dễ hết than giữa chừng) và bố cục rải
rác, không giống schematic thật."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import plan_build
from bot.state import grid_from_state
from simulator.sim import evaluate_layout


def count_places(actions, building_name):
    return sum(1 for a in actions if a["op"] == "place" and a["building"] == building_name)


print("--- Kịch bản 0 (đối chứng): lệnh xây generator THƯỜNG (không có số) vẫn chỉ đặt đúng 1 cái ---")
FAKE_STATE_0 = {
    "width": 40, "height": 40,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 4) for y in range(2, 4)],
    "buildings": [{"type": "core", "x": 10, "y": 10, "rotation": 0}],
}
grid0 = grid_from_state(FAKE_STATE_0)
cmd0 = parse_command("xây máy phát điện")
print(f"  lệnh parse ra: {cmd0}")
assert cmd0["action"] == "build", "SAI: bug thật vừa sửa -- 'phá' (delete) là substring của 'phát', phải KHÔNG còn bị nhầm nữa"
assert cmd0.get("count") is None, "SAI: không nói số thì không được tự bật cụm"
actions0 = plan_build(grid0, cmd0)
n0 = count_places(actions0, "combustion-generator")
print(f"  đặt: {n0} generator")
assert n0 == 1
print("  ĐÚNG: hành vi cũ (1 generator/lệnh) không đổi khi không nói số.\n")


print("--- Kịch bản 1: 'xây 21 máy phát điện' -> đặt ĐÚNG 21, dùng CHUNG 1 nguồn than (không phải 21 mỏ riêng) ---")
FAKE_STATE_1 = {
    "width": 60, "height": 60,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 5) for y in range(40, 43)],
    "buildings": [{"type": "core", "x": 5, "y": 5, "rotation": 0}],
}
grid1 = grid_from_state(FAKE_STATE_1)
cmd1 = parse_command("xây 21 máy phát điện")
print(f"  lệnh parse ra: {cmd1}")
assert cmd1.get("count") == 21, "SAI: phải bắt được số 21"
actions1 = plan_build(grid1, cmd1)
n_gen1 = count_places(actions1, "combustion-generator")
n_router1 = count_places(actions1, "router")
n_drill1 = count_places(actions1, "mechanical-drill")
n_node1 = count_places(actions1, "power-node")
print(f"  generator={n_gen1}, router={n_router1}, coal-drill={n_drill1}, power-node={n_node1}")
assert n_gen1 == 21, "SAI: phải đặt ĐÚNG 21 generator theo số đã nói"
assert n_router1 == 21, "SAI: mỗi generator phải có 1 router riêng chạm thẳng (lane phân phối)"
assert n_drill1 == 1, (
    f"SAI: 21 generator đáng lẽ phải dùng CHUNG ĐÚNG 1 nguồn than duy nhất (qua router lane), "
    f"nhưng lại đào {n_drill1} mỏ than -- đây chính là phần user hỏi 'bot có biết tự thiết lập đầu vào than không'"
)
assert n_node1 == 1, "SAI: phải có 1 power-node để tap điện ra ngoài, giống schematic thật user cung cấp"
print("  ĐÚNG: 21 generator, chỉ 1 mỏ than DUY NHẤT được đào (không phải 21 mỏ riêng).\n")

result1 = evaluate_layout(grid1)
gens1 = [b for b in grid1.unique_buildings() if b.type.name == "combustion-generator"]
total_power1 = sum(result1["power_production"].get(g, 0.0) for g in gens1)
n_producing = sum(1 for g in gens1 if result1["power_production"].get(g, 0.0) > 1e-9)
print(f"  tổng power_production cả cụm: {total_power1:.4f}/s ({n_producing}/{len(gens1)} generator có sản xuất > 0)")
assert total_power1 > 0.0, "SAI: cụm phải thật sự sản xuất được điện, không chỉ đặt suông"
print("  ĐÚNG: cả cụm thật sự sản xuất điện (đo qua evaluate_layout, không chỉ đặt xuống rồi bỏ đó).")
print("  LƯU Ý THẬT (trả lời đúng câu hỏi user): vì chỉ 1 mechanical-drill KHIÊM TỐN nuôi chung 21")
print("  generator, mỗi generator chỉ nhận 1 PHẦN NHỎ than (router chia đều) -- KHÔNG phải cứ thêm")
print("  generator là điện tăng theo, tổng điện vẫn bị giới hạn bởi tổng than cung cấp được. Muốn 21")
print("  generator thật sự MẠNH hơn 1 generator, cần thêm than (nhiều/mạnh hơn), chưa tự động hoá.\n")


print("--- Kịch bản 2: LƯỚI NHIỀU HÀNG double-sided (đúng thiết kế schematic thật) -- 1 hàng router phục vụ 2 hàng generator cùng lúc ---")
# User hỏi thẳng: "xếp thành 1 hàng thẳng? bot không thể giống thế này được
# à" kèm chính schematic .msch đã giải mã (3 hàng x 6 generator, router NẰM
# GIỮA phục vụ cả hàng trên lẫn hàng dưới) -- sửa từ bản "1 hàng dài, mỗi
# router 1 generator" sang đúng lưới nhiều hàng double-sided như bản gốc.
gen_rows = sorted(set(a["y"] for a in actions1 if a["op"] == "place" and a["building"] == "combustion-generator"))
router_rows = sorted(set(a["y"] for a in actions1 if a["op"] == "place" and a["building"] == "router"))
print(f"  hàng generator tại y={gen_rows}, hàng router tại y={router_rows}")
assert len(gen_rows) > 1, "SAI: 21 generator với width mặc định 6/hàng phải xếp NHIỀU HƠN 1 hàng"
assert len(router_rows) == max(len(gen_rows) - 1, 1), (
    f"SAI: số hàng router phải là max(số_hàng_generator - 1, 1) (double-sided, mỗi router phục vụ 2 hàng) -- "
    f"ra {len(router_rows)} hàng router cho {len(gen_rows)} hàng generator"
)
# Xác nhận router row THẬT SỰ nằm GIỮA 2 hàng generator liên tiếp (chạm cả
# 2 bên -- không phải chỉ chạm 1 bên như bản đơn giản cũ).
for ry in router_rows:
    assert (ry - 1) in gen_rows and (ry + 1) in gen_rows, (
        f"SAI: hàng router y={ry} phải NẰM GIỮA và chạm cả hàng generator TRÊN (y={ry-1}) lẫn DƯỚI (y={ry+1})"
    )
print("  ĐÚNG: mỗi hàng router (trừ trường hợp chỉ 1 hàng) chạm CẢ 2 hàng generator trên-dưới cùng lúc,")
print("  khớp đúng thiết kế double-sided trong schematic thật user cung cấp -- không phải 1 hàng dài đơn giản.\n")

print("XÁC NHẬN: 'xây N máy phát điện' đặt đúng N generator xếp hàng, dùng")
print("CHUNG 1 nguồn than qua router lane (không phải N nguồn riêng, không phải")
print("random không biết input) -- đúng ý tưởng lấy từ schematic thật 'Basic")
print("power plant V.1' user cung cấp. Giới hạn thật: tổng điện vẫn bị giới hạn")
print("bởi 1 nguồn than khiêm tốn, chưa tự scale than theo số lượng generator.")
