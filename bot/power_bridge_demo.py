"""Chứng minh _ensure_powered() giờ ưu tiên NỐI VÀO mạng lưới điện có sẵn
GẦN NHẤT (chỉ đặt 1 power-node bắc cầu) thay vì luôn tự xây combustion-
generator mới -- theo đúng yêu cầu người dùng "nối điện vào mạng lưới điện
gần nhất" (xem bot/planner.py: _find_power_bridge_spot + _ensure_powered).

Bug thật trước đó: nhánh "drill" gốc trong plan_build() (khác beam-drill/
wall-crafter/solid-pump) CHƯA BAO GIỜ gọi _ensure_powered() -- user tự phát
hiện khi test "drill cấp 4 đào chì" thật: laser-drill (power_input=66) được
đặt xuống nhưng không có điện (xem bot/drill_tier_number_demo.py cho bug
tier-number riêng). Giờ đã thêm _ensure_powered() vào nhánh "drill" VÀ
"pump", đồng thời đổi hẳn chiến lược cấp điện sang ưu tiên bắc cầu."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import _connect_to_core, _ensure_powered, _route, plan_build
from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout


def count_places(actions, building_name):
    return sum(1 for a in actions if a["op"] == "place" and a["building"] == building_name)


print("--- Kịch bản 1: map CHƯA có điện gì -> vẫn phải tự xây generator mới (hành vi cũ giữ nguyên) ---")
grid1 = Grid(width=40, height=40)
grid1.set_ore(10, 10, "lead")
grid1.set_ore(25, 25, "coal")
grid1.set_ore(26, 25, "coal")
grid1.set_ore(25, 26, "coal")
grid1.set_ore(26, 26, "coal")
grid1.place(CATALOG["core"], 5, 5, rotation=0)

cmd1 = parse_command("xây drill cấp 4 đào chì")
actions1 = plan_build(grid1, cmd1)
n_gen1 = count_places(actions1, "combustion-generator")
n_node1 = count_places(actions1, "power-node")
print(f"  combustion-generator đặt mới: {n_gen1}, power-node: {n_node1}")
assert n_gen1 == 1, "SAI: chưa có điện gì trên map thì PHẢI tự xây generator mới"
assert n_node1 == 1, "SAI: vẫn phải bắc 1 power-node cạnh drill để nối tới generator mới xây"
print("  ĐÚNG: không có mạng điện nào để bắc cầu, tự xây generator mới như cũ.\n")


print("--- Kịch bản 2: ĐÃ có sẵn mạng điện DƯ CÔNG SUẤT gần đó -> chỉ bắc cầu 1 power-node, KHÔNG xây generator mới ---")
grid2 = Grid(width=40, height=40)
grid2.place(CATALOG["core"], 5, 5, rotation=0)

# Tự dựng tay 2 combustion-generator (mỗi cái có drill than 2x2 phủ kín
# 4/4 ô than riêng, tự nối belt) -- KHÔNG dùng _ensure_powered() để dựng vì
# nó chỉ xây đúng 1 generator "đủ dùng cho 1 building" (xem docstring
# _ensure_powered), không chủ đích dư công suất -- ở đây cần chủ động dư ra
# để chứng minh đúng nhánh "bắc cầu là đủ, không cần xây thêm gì".
# Mỗi generator fully-fed 4/4 than (hardness=2) cho throughput than
# 60*4/700=0.343/s < 0.5/s cần để generator chạy 100% công suất -- đo thật
# qua evaluate_layout dưới đây thay vì đoán, ra ~41.14/s mỗi cái, 2 cái
# cộng lại ~82.3/s > 66/s nhu cầu của 1 laser-drill mới -- đủ dư.
grid2.set_ore(20, 10, "coal"); grid2.set_ore(21, 10, "coal")
grid2.set_ore(20, 11, "coal"); grid2.set_ore(21, 11, "coal")
gd1 = grid2.place(CATALOG["mechanical-drill"], 20, 10, rotation=0, ore_target="coal")
gg1 = grid2.place(CATALOG["combustion-generator"], 20, 13, rotation=0)
_route(grid2, [], gd1.output_tile(), gg1.footprint(), CATALOG["conveyor"], "setup gen1")

grid2.set_ore(25, 10, "coal"); grid2.set_ore(26, 10, "coal")
grid2.set_ore(25, 11, "coal"); grid2.set_ore(26, 11, "coal")
gd2 = grid2.place(CATALOG["mechanical-drill"], 25, 10, rotation=0, ore_target="coal")
gg2 = grid2.place(CATALOG["combustion-generator"], 25, 13, rotation=0)
_route(grid2, [], gd2.output_tile(), gg2.footprint(), CATALOG["conveyor"], "setup gen2")

setup_result = evaluate_layout(grid2)
total_capacity = setup_result["power_production"].get(gg1, 0.0) + setup_result["power_production"].get(gg2, 0.0)
print(f"  (setup) tổng công suất 2 generator dựng tay: {total_capacity:.2f}/s (cần > 66/s cho laser-drill mới)")
assert total_capacity > 66.0, "SAI kịch bản demo: cần dựng đủ dư công suất trước khi test bắc cầu"

# Mỏ chì thật để test đặt gần cụm generator trên nhưng ở vùng đất TRỐNG
# (dưới hàng generator, không đụng belt/drill than đã dựng) -- vẫn trong
# tầm bắc cầu (power_range=6 tính từ tâm generator/power-node).
grid2.set_ore(22, 18, "lead")

cmd2 = parse_command("xây drill cấp 4 đào chì")
actions2 = plan_build(grid2, cmd2)
n_gen2 = count_places(actions2, "combustion-generator")
n_node2 = count_places(actions2, "power-node")
print(f"  combustion-generator đặt mới: {n_gen2}, power-node: {n_node2}")
for a in actions2:
    print("   ", a)
assert n_gen2 == 0, "SAI: đã có sẵn mạng điện gần đó, KHÔNG được tự xây thêm generator mới"
assert n_node2 == 1, "SAI: phải bắc cầu ĐÚNG 1 power-node để nối vào mạng có sẵn"

result2 = evaluate_layout(grid2)
laser_drill = next(b for b in grid2.unique_buildings() if b.type.name == "laser-drill")
sat2 = result2["power_satisfaction"].get(laser_drill, 0.0)
print(f"  power_satisfaction laser-drill mới: {sat2:.4f}")
assert sat2 >= 1.0 - 1e-6, "SAI: sau khi bắc cầu vào mạng có sẵn (đã đủ công suất) drill mới phải nhận đủ điện"
print("  ĐÚNG: chỉ bắc cầu 1 power-node vào mạng điện có sẵn, không lãng phí xây generator mới.\n")


print("--- Kịch bản 3: mạng điện có sẵn NHƯNG ở quá xa (ngoài tầm bắc cầu) -> vẫn phải tự xây generator mới ---")
grid3 = Grid(width=80, height=80)
# Than dành cho _ensure_powered() tự đào cho dummy3 -- đặt CÁCH xa chân đế
# dummy3 (70,70)-(72,72) (laser-drill size=3), không được đè lên nó, nếu
# không grid.building_at() sẽ coi ô than đó "đã có building" và loại khỏi
# find_unmined_ore (bug thật gặp phải khi debug: than trùng đúng chân đế
# dummy khiến _ensure_powered của chính dummy3 báo "không có mỏ than").
grid3.set_ore(75, 75, "coal")
grid3.set_ore(76, 75, "coal")
grid3.place(CATALOG["core"], 5, 5, rotation=0)

dummy3 = grid3.place(CATALOG["laser-drill"], 70, 70, rotation=0, ore_target=None)
_ensure_powered(grid3, [], dummy3, near=(70, 70))

# Mỏ chì thật nằm CÁCH XA mạng điện trên (ngoài tầm power-node range=6) --
# _find_power_bridge_spot() phải trả về None, rơi về hành vi xây mới.
grid3.set_ore(10, 10, "lead")
grid3.set_ore(35, 35, "coal")
grid3.set_ore(36, 35, "coal")

cmd3 = parse_command("xây drill cấp 4 đào chì")
actions3 = plan_build(grid3, cmd3)
n_gen3 = count_places(actions3, "combustion-generator")
n_node3 = count_places(actions3, "power-node")
print(f"  combustion-generator đặt mới: {n_gen3}, power-node: {n_node3}")
assert n_gen3 == 1, "SAI: mạng điện có sẵn quá xa (ngoài tầm bắc cầu) thì PHẢI tự xây generator mới, không được bỏ cuộc"
print("  ĐÚNG: mạng điện có sẵn ngoài tầm bắc cầu, tự xây generator mới độc lập như cũ.\n")

print("XÁC NHẬN: _ensure_powered() giờ ưu tiên nối vào mạng lưới điện gần nhất")
print("đã có sẵn (trong tầm power-node), chỉ tự xây generator mới khi thật sự")
print("không có gì để bắc cầu tới hoặc mạng có sẵn ở ngoài tầm.")
