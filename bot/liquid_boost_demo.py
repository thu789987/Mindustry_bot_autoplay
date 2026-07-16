"""Chứng minh liquid boost của Drill.java (consumeLiquid(...).boost() thật)
đã được model đúng: KHÔNG BẮT BUỘC (khác power_input) -- không có nước vẫn ra
đúng rate nền, có nước thì NHÂN THÊM theo boost_intensity, lerp dần theo tỉ lệ
nước cấp được (không phải nhị phân đủ/không đủ).

Sửa giả định SAI ban đầu của người dùng ("chỉ Laser trở lên mới cần nước") --
đã tra Blocks.java thật, xác nhận CẢ 4 tier (mechanical/pneumatic/laser/blast)
đều có consumeLiquid(Liquids.water, X).boost(), chỉ khác lượng cần + intensity
(1.6x cho 3 tier đầu, 1.8x riêng blast-drill -- comment thật: "more than the
laser drill"). Xem simulator/generated_catalog.py + NEXT_STEPS.md."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG, ITEMS
from simulator.grid import Grid
from simulator.sim import evaluate_layout

TICKS = 60


def base_rate(drill_type, item_name, tile_count):
    item = ITEMS[item_name]
    drill_time_eff = drill_type.drill_time + drill_type.hardness_multiplier * item.hardness
    return TICKS * tile_count / drill_time_eff


print("--- Kịch bản 1: mechanical-drill KHÔNG có nước -> đúng rate nền, không lỗi, không bị chặn ---")
MD = CATALOG["mechanical-drill"]
print(f"  mechanical-drill: boost_liquid={MD.boost_liquid!r}, boost_amount={MD.boost_amount}, boost_intensity={MD.boost_intensity}")
grid1 = Grid(width=15, height=15)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid1.set_ore(x, y, "lead")
d1 = grid1.place(MD, 2, 2, rotation=0, ore_target="lead")
result1 = evaluate_layout(grid1)
expected1 = base_rate(MD, "lead", 4)
print(f"  rate: {result1['output_rate'][d1]:.6f}/s (kỳ vọng {expected1:.6f}/s = rate nền, KHÔNG nhân gì)")
assert abs(result1["output_rate"][d1] - expected1) < 1e-9, "SAI: không có nước phải ra đúng rate nền"
print("  ĐÚNG.\n")

print("--- Kịch bản 2: mechanical-drill có ĐỦ nước (mechanical-pump riêng, nối qua _route() thật) -> nhân đúng 1.6x ---")
grid2b = Grid(width=15, height=15)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid2b.set_ore(x, y, "lead")
grid2b.set_liquid(10, 2, "water")
d2b = grid2b.place(MD, 2, 2, rotation=0, ore_target="lead")
pump2b = grid2b.place(CATALOG["mechanical-pump"], 10, 2, rotation=0, liquid_target="water")
from bot.planner import _route
_route(grid2b, [], pump2b.output_tile(), d2b.footprint(), CATALOG["conduit"], "không nối được nước")
result2 = evaluate_layout(grid2b)
expected_base2 = base_rate(MD, "lead", 4)
expected2 = expected_base2 * MD.boost_intensity  # pump 1 ô nước = 60*0.116667=7.0/s >> 3.0/s cần -> full boost
print(f"  rate: {result2['output_rate'][d2b]:.6f}/s (kỳ vọng {expected2:.6f}/s = rate nền * {MD.boost_intensity})")
assert abs(result2["output_rate"][d2b] - expected2) < 1e-6, "SAI: đủ nước phải nhân đúng boost_intensity"
print("  ĐÚNG.\n")

print("--- Kịch bản 3: 2 drill gọi _try_boost_with_water() lần lượt -> TỰ ĐỘNG dùng chung 1 pump qua router, mỗi drill chỉ được 1 PHẦN (lerp đúng tỉ lệ, không nhị phân) ---")
LD = CATALOG["laser-drill"]
grid3 = Grid(width=20, height=20)
for x, y in [(2, 2), (3, 2), (4, 2), (2, 3), (3, 3), (4, 3), (2, 4), (3, 4), (4, 4)]:
    grid3.set_ore(x, y, "lead")
for x, y in [(10, 2), (11, 2), (12, 2), (10, 3), (11, 3), (12, 3), (10, 4), (11, 4), (12, 4)]:
    grid3.set_ore(x, y, "lead")
grid3.set_liquid(6, 10, "water")
grid3.set_ore(2, 15, "coal"); grid3.set_ore(3, 15, "coal")
grid3.set_ore(2, 16, "coal"); grid3.set_ore(3, 16, "coal")
grid3.set_ore(10, 15, "coal"); grid3.set_ore(11, 15, "coal")
grid3.set_ore(10, 16, "coal"); grid3.set_ore(11, 16, "coal")
d3a = grid3.place(LD, 2, 2, rotation=0, ore_target="lead")
d3b = grid3.place(LD, 10, 2, rotation=0, ore_target="lead")
from bot.planner import _ensure_powered, _try_boost_with_water, find_liquid_producer
# Gọi ĐÚNG hàm thật planner.py dùng (task #73) -- không tự dựng router bằng
# tay để tránh lỗi loại belt sai (conveyor thay vì conduit, xem plan_split()
# chỉ dành cho item). Gọi lần lượt cho d3a rồi d3b -- lần đầu KHÔNG có pump
# nào trên map nên tự xây mới; lần 2 phải TÌM THẤY pump vừa xây ở lần đầu
# qua find_liquid_producer() và NỐI CHUNG vào (không xây pump thứ 2).
_try_boost_with_water(grid3, [], d3a)
n_pumps_after_a = sum(1 for b in grid3.unique_buildings() if b.type.kind == "pump")
_try_boost_with_water(grid3, [], d3b)
n_pumps_after_b = sum(1 for b in grid3.unique_buildings() if b.type.kind == "pump")
print(f"  số mechanical-pump sau d3a: {n_pumps_after_a}, sau d3b: {n_pumps_after_b}")
assert n_pumps_after_a == 1, "SAI: d3a phải tự xây ĐÚNG 1 pump mới (chưa có gì trên map)"
assert n_pumps_after_b == 1, "SAI: d3b phải TÁI SỬ DỤNG pump của d3a, không xây thêm pump thứ 2 -- đây là phần 'tối ưu' người dùng yêu cầu"
pump3 = find_liquid_producer(grid3, "water")
assert pump3 is not None

# laser-drill cần điện thật (power_input=66) -- _ensure_powered tự xây
# generator+drill than riêng cho mỗi cái, không liên quan tới boost nước
# đang test (2 mạng độc lập, item vs power, không chung tài nguyên).
_ensure_powered(grid3, [], d3a, near=(2, 2))
_ensure_powered(grid3, [], d3b, near=(10, 2))
result3 = evaluate_layout(grid3)
pump_rate = result3["liquid_output_rate"][pump3]
# branch_count[pump3] = TỔNG số connection tuple xuất phát từ pump3 (dùng
# CHIA CHUNG cho mọi đích, đúng công thức compute() thật trong sim.py) --
# 1 building lớn (laser-drill 3x3) có thể chạm router ở NHIỀU cạnh cùng lúc
# nên có thể xuất hiện >1 tuple cho CÙNG 1 đích (không phải bug, đúng cơ chế
# _trace_branching chia theo số cạnh tiếp xúc router -- xem sim.py). Đếm
# đúng số tuple RIÊNG cho từng đích thay vì giả định chia đều 50/50.
branch_count = sum(1 for src, dest, cap in result3["liquid_connections"] if src is pump3)
edges_to_a = sum(1 for src, dest, cap in result3["liquid_connections"] if src is pump3 and dest is d3a)
edges_to_b = sum(1 for src, dest, cap in result3["liquid_connections"] if src is pump3 and dest is d3b)
per_edge_rate = pump_rate / branch_count if branch_count else 0.0
available_a = edges_to_a * per_edge_rate
available_b = edges_to_b * per_edge_rate
needed = TICKS * LD.boost_amount
efficiency_a = min(available_a / needed, 1.0)
efficiency_b = min(available_b / needed, 1.0)
expected_base3 = base_rate(LD, "lead", 9)
sat_a = result3["power_satisfaction"].get(d3a, 0.0)
sat_b = result3["power_satisfaction"].get(d3b, 0.0)
# _ensure_powered() (xem NEXT_STEPS.md) chỉ xây 1 combustion-generator "đủ
# dùng khiêm tốn", không đảm bảo power_satisfaction=1.0 tuyệt đối -- nhân
# thêm sat ĐO ĐƯỢC thay vì giả định đủ điện 100%, giống quy ước
# solid_pump_demo.py -- vẫn kiểm ĐÚNG công thức boost nước, độc lập với
# việc mạng điện có đủ 100% hay không.
expected3 = expected_base3 * (1.0 + (LD.boost_intensity - 1.0) * efficiency_a) * sat_a
expected3b = expected_base3 * (1.0 + (LD.boost_intensity - 1.0) * efficiency_b) * sat_b
print(f"  pump_rate={pump_rate:.4f}/s, {edges_to_a} cạnh chạm d3a ({available_a:.4f}/s), {edges_to_b} cạnh chạm d3b ({available_b:.4f}/s), cần {needed:.4f}/s")
print(f"  hiệu suất nước: d3a={efficiency_a:.4f}, d3b={efficiency_b:.4f}, power_satisfaction: d3a={sat_a:.4f}, d3b={sat_b:.4f}")
print(f"  rate d3a: {result3['output_rate'][d3a]:.6f}/s (kỳ vọng {expected3:.6f}/s)")
print(f"  rate d3b: {result3['output_rate'][d3b]:.6f}/s (kỳ vọng {expected3b:.6f}/s)")
assert 0.0 < efficiency_a < 1.0 and 0.0 < efficiency_b < 1.0, \
    "SAI kịch bản demo: cần chọn số sao cho hiệu suất RA PARTIAL (không phải 0 hay 1) để chứng minh lerp"
assert sat_a > 0.0 and sat_b > 0.0, "SAI: _ensure_powered() phải cấp được ít nhất 1 phần điện cho cả 2 drill"
assert abs(result3["output_rate"][d3a] - expected3) < 1e-6
assert abs(result3["output_rate"][d3b] - expected3b) < 1e-6
print("  ĐÚNG: cả 2 drill chia sẻ ĐÚNG 1 nguồn nước duy nhất (không xây pump thứ 2),")
print("  boost lerp đúng tỉ lệ nước THẬT nhận được qua router (không phải 0 hay full).\n")

print("--- Kịch bản 4: blast-drill có boost_intensity RIÊNG (1.8x, không phải 1.6x mặc định) ---")
BD = CATALOG["blast-drill"]
print(f"  blast-drill: boost_intensity={BD.boost_intensity} (ghi đè, khác default 1.6 của Drill.java)")
assert BD.boost_intensity == 1.8, "SAI: blast-drill phải ghi đè liquidBoostIntensity=1.8f (xem Blocks.java thật)"
assert MD.boost_intensity == 1.6 and CATALOG["pneumatic-drill"].boost_intensity == 1.6 and LD.boost_intensity == 1.6, \
    "SAI: mechanical/pneumatic/laser phải dùng default 1.6 (không ghi đè)"
print("  ĐÚNG.\n")

print("XÁC NHẬN: liquid boost hoạt động đúng thật -- optional (không nước vẫn")
print("chạy rate nền), lerp liên tục theo tỉ lệ nước cấp được (không nhị phân),")
print("và boost_intensity đúng riêng từng tier (1.6x hầu hết, 1.8x blast-drill).")
print("Sửa đúng giả định sai ban đầu: CẢ 4 tier drill đều hỗ trợ boost nước,")
print("không chỉ riêng laser-drill trở lên.")
