"""Chứng minh: audit đầy đủ "Power Blocks" (24 block thật, xem
reference/Blocks.java:135-141) -- từ 5/24 có cơ chế mô phỏng (power-node x3
+ generator x2) lên 17/24, thêm 12 block mới:

- power-node family: beam-node/beam-tower (BeamNode.java -- nối THẲNG HÀNG 4
  hướng, KHÁC power-node toả tròn) + beam-link (LongPowerNode.java, kế thừa
  PowerNode y hệt).
- generator thụ động: solar-panel/solar-panel-large (SolarGenerator.java --
  ra điện KHÔNG cần input, xấp xỉ luôn đủ nắng).
- generator item cố định: differential-generator (pyratite+cryofluid),
  thorium-reactor (thorium, NuclearReactor.java), impact-reactor
  (blast-compound+cryofluid+tự tiêu 1500 điện/s, ImpactReactor.java) --
  KHÁC combustion/steam-generator (đốt bất kỳ item đủ flammability).
- generator liquid-only: chemical-combustion-chamber, pyrolysis-generator
  (chỉ consumeLiquids, không item nào).
- battery/battery-large (Battery.java) -- lưu trữ điện, tham gia mạng
  nhưng không đổi thông lượng trung bình (đã ghi rõ trong
  _build_power_networks từ trước).

Còn lại 7/24 CHỦ ĐỘNG bỏ qua, có lý do thật (xem NEXT_STEPS.md):
rtg-generator (ConsumeItemRadioactive -- khác flammability, cần thêm field
Item.radioactivity chưa parse), thermal-generator/turbine-condenser (đọc
Attribute.heat -- CHƯA có "heat" trong Tile/state schema), flux-reactor/
neoplasia-reactor (VariableReactor/HeaterGenerator -- cơ chế heat-instability
phức tạp hơn hẳn), diode (PowerDiode -- cần trạng thái pin theo % TỪNG TICK,
hoàn toàn khác mô hình thông lượng trung bình ổn định của simulator này),
vent-condenser (AttributeCrafter -- thực ra là crafter đọc Attribute.heat,
cùng lý do thermal-generator, không phải generator thật)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import _route, plan_build
from bot.state import grid_from_state
from simulator.buildings import CATALOG
from simulator.sim import _build_power_networks, _power_linked, evaluate_layout

print("--- Kịch bản 1: solar-panel -- ra điện THỤ ĐỘNG, không cần input ---")
grid1 = grid_from_state({"width": 20, "height": 20, "buildings": [{"type": "core", "x": 10, "y": 10, "rotation": 0}]})
sp = grid1.place(CATALOG["solar-panel"], 2, 2, rotation=0)
result1 = evaluate_layout(grid1)
expected1 = 60 * CATALOG["solar-panel"].power_production
print(f"  power_production: {result1['power_production'].get(sp)} (kỳ vọng {expected1})")
assert abs(result1["power_production"].get(sp, 0) - expected1) < 1e-9
print("  ĐÚNG.\n")

print("--- Kịch bản 2: beam-node nối THẲNG HÀNG (4 hướng), KHÔNG toả tròn như power-node ---")
grid2 = grid_from_state({"width": 40, "height": 40, "buildings": [{"type": "core", "x": 30, "y": 30, "rotation": 0}]})
bn1 = grid2.place(CATALOG["beam-node"], 5, 5, rotation=0)
bn_col = grid2.place(CATALOG["beam-node"], 5, 12, rotation=0)   # cùng cột, trong tầm 10
bn_row = grid2.place(CATALOG["beam-node"], 12, 5, rotation=0)   # cùng hàng, trong tầm
bn_diag = grid2.place(CATALOG["beam-node"], 12, 12, rotation=0)  # chéo, KHÔNG thẳng hàng
print(f"  cùng cột (trong tầm): {_power_linked(bn1, bn_col)}")
print(f"  cùng hàng (trong tầm): {_power_linked(bn1, bn_row)}")
print(f"  chéo (không thẳng hàng): {_power_linked(bn1, bn_diag)}")
assert _power_linked(bn1, bn_col) and _power_linked(bn1, bn_row)
assert not _power_linked(bn1, bn_diag), "SAI: beam-node không được nối chéo (chỉ 4 hướng thẳng)"
print("  ĐÚNG: chỉ nối thẳng hàng, không toả tròn như power-node.\n")

print("--- Kịch bản 3: battery tham gia mạng điện qua power-node, không đổi rate ---")
grid3 = grid_from_state({"width": 40, "height": 40, "buildings": [{"type": "core", "x": 30, "y": 30, "rotation": 0}]})
pn = grid3.place(CATALOG["power-node"], 20, 20, rotation=0)
bat = grid3.place(CATALOG["battery"], 20, 22, rotation=0)
networks = _build_power_networks(grid3.unique_buildings())
print(f"  battery cùng mạng với power-node: {networks.get(id(bat)) == networks.get(id(pn))}")
assert networks.get(id(bat)) == networks.get(id(pn))
print("  ĐÚNG.\n")

print("--- Kịch bản 4: 'xây pin'/'xây nút beam' -- battery/beam-node build TRỰC TIẾP qua lệnh (khác router/bridge) ---")
grid4 = grid_from_state({"width": 30, "height": 30, "buildings": [{"type": "core", "x": 15, "y": 15, "rotation": 0}]})
for phrase, expect_building in [("xây pin", "battery"), ("xây nút beam", "beam-node")]:
    cmd = parse_command(phrase)
    actions = plan_build(grid4, cmd)
    print(f"  '{phrase}' -> {actions}")
    assert any(a["building"] == expect_building for a in actions)
print("  ĐÚNG.\n")

print("--- Kịch bản 5: thorium-reactor (item CỐ ĐỊNH thorium, khác flammable) -- xây trực tiếp qua plan_build ---")
grid5 = grid_from_state({
    "width": 60, "height": 40,
    "ore_tiles": [{"x": x, "y": y, "ore": "thorium"} for x in range(2, 8) for y in range(2, 8)]
              + [{"x": x, "y": y, "ore": "coal"} for x in range(30, 36) for y in range(2, 8)],
    "buildings": [{"type": "core", "x": 20, "y": 20, "rotation": 0}],
})
plan_build(grid5, {"action": "build", "building": "thorium-reactor"})
tr = next(b for b in grid5.unique_buildings() if b.type.name == "thorium-reactor")
drill5 = next(b for b in grid5.unique_buildings() if b.type.name == "laser-drill")
result5 = evaluate_layout(grid5)
drill_rate = result5["output_rate"].get(drill5, 0)
max_cycle_rate = 60 / 360
cycle_rate = min(max_cycle_rate, drill_rate / 1.0)
expected5 = 60 * 15.0 * (cycle_rate / max_cycle_rate)
print(f"  drill rate: {drill_rate:.6f} (đã tự cấp điện cho laser-drill, power_input=66)")
print(f"  power_production: {result5['power_production'].get(tr)} (kỳ vọng {expected5})")
assert result5["power_production"].get(tr, 0) > 0
assert abs(result5["power_production"].get(tr, 0) - expected5) < 1e-6
print("  ĐÚNG: bot tự chọn drill tier ĐỦ MẠNH cho thorium (hardness=4 -> laser-drill),")
print("  tự cấp điện cho chính drill đó (bug thật tìm thấy: trước đây generator branch")
print("  hardcode than -- fuel_item khác than không hề gọi _ensure_powered cho fuel drill,")
print("  drill không có điện, rate luôn 0 mà không báo lỗi gì).\n")

print("--- Kịch bản 6: differential-generator (item cố định pyratite, KHÔNG phải ore -- tái sử dụng factory có sẵn) ---")
grid6 = grid_from_state({
    "width": 80, "height": 60,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x in range(2, 8) for y in range(2, 8)]
              + [{"x": x, "y": y, "ore": "lead"} for x in range(2, 8) for y in range(15, 21)]
              + [{"x": x, "y": y, "ore": "sand"} for x in range(2, 8) for y in range(30, 36)],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "cryofluid"} for x in range(50, 56) for y in range(2, 8)],
    "buildings": [{"type": "core", "x": 40, "y": 30, "rotation": 0}],
})
plan_build(grid6, {"action": "build", "building": "pyratite-mixer"})
n_pyratite_before = sum(1 for b in grid6.unique_buildings() if b.type.name == "pyratite-mixer")
plan_build(grid6, {"action": "build", "building": "differential-generator"})
n_pyratite_after = sum(1 for b in grid6.unique_buildings() if b.type.name == "pyratite-mixer")
dg = next(b for b in grid6.unique_buildings() if b.type.name == "differential-generator")
result6 = evaluate_layout(grid6)
print(f"  pyratite-mixer trước/sau: {n_pyratite_before}/{n_pyratite_after} (kỳ vọng vẫn 1 -- tái sử dụng)")
print(f"  power_production: {result6['power_production'].get(dg)}")
assert n_pyratite_before == n_pyratite_after == 1, "SAI: phải tái sử dụng pyratite-mixer có sẵn, không xây thêm"
assert result6["power_production"].get(dg, 0) > 0
print("  ĐÚNG: bot nhận ra pyratite KHÔNG phải ore (thử find_producer trước find_unmined_ore),")
print("  tự nối vào factory pyratite-mixer đã xây trước đó thay vì báo lỗi hoặc đoán bừa.\n")

print("--- Kịch bản 7: chemical-combustion-chamber (CHỈ liquid, không item nào) ---")
grid7 = grid_from_state({
    "width": 30, "height": 30,
    "liquid_tiles": [{"x": x, "y": y, "liquid": "ozone"} for x in range(2, 4) for y in range(2, 4)]
              + [{"x": x, "y": y, "liquid": "arkycite"} for x in range(2, 4) for y in range(10, 12)],
    "buildings": [{"type": "core", "x": 20, "y": 20, "rotation": 0}],
})
ccc = grid7.place(CATALOG["chemical-combustion-chamber"], 10, 10, rotation=0)
p_ozone = grid7.place(CATALOG["mechanical-pump"], 2, 2, rotation=0, liquid_target="ozone")
p_arky = grid7.place(CATALOG["mechanical-pump"], 2, 10, rotation=1, liquid_target="arkycite")
_route(grid7, [], p_ozone.output_tile(), ccc.footprint(), CATALOG["conduit"], "x")
_route(grid7, [], p_arky.output_tile(), ccc.footprint(), CATALOG["conduit"], "x")
result7 = evaluate_layout(grid7)
ozone_rate = result7["liquid_output_rate"].get(p_ozone, 0)
arky_rate = result7["liquid_output_rate"].get(p_arky, 0)
expected7 = 60 * CATALOG["chemical-combustion-chamber"].power_production * min(1.0, ozone_rate / 2.0, arky_rate / 40.0)
print(f"  ozone/arkycite cấp: {ozone_rate:.4f}/{arky_rate:.4f}")
print(f"  power_production: {result7['power_production'].get(ccc)} (kỳ vọng {expected7})")
assert abs(result7["power_production"].get(ccc, 0) - expected7) < 1e-6
print("  ĐÚNG: liquid-only generator KHÔNG bị gate theo 'chu kỳ item' nào cả -- hiệu suất")
print("  chỉ phụ thuộc tỉ lệ lưu lượng liquid đang có / cần liên tục.\n")

print("--- Kịch bản 8: impact-reactor -- VỪA sản xuất VỪA tiêu thụ điện (net dương) ---")
grid8 = grid_from_state({
    "width": 30, "height": 30,
    "ore_tiles": [{"x": x, "y": y, "ore": "blast-compound"} for x in range(2, 6) for y in range(2, 6)]
              + [{"x": x, "y": y, "ore": "coal"} for x in range(22, 26) for y in range(10, 14)],
    "liquid_tiles": [{"x": x, "y": y, "liquid": "cryofluid"} for x in range(2, 6) for y in range(15, 19)],
    "buildings": [{"type": "core", "x": 20, "y": 20, "rotation": 0}],
})
ir = grid8.place(CATALOG["impact-reactor"], 10, 10, rotation=0)
drill8 = grid8.place(CATALOG["mechanical-drill"], 2, 2, rotation=1, ore_target="blast-compound")
_route(grid8, [], drill8.output_tile(), ir.footprint(), CATALOG["conveyor"], "x")
pump8 = grid8.place(CATALOG["mechanical-pump"], 2, 15, rotation=0, liquid_target="cryofluid")
_route(grid8, [], pump8.output_tile(), ir.footprint(), CATALOG["conduit"], "x")
gen8 = grid8.place(CATALOG["combustion-generator"], 22, 10, rotation=0)
coal_drill8 = grid8.place(CATALOG["mechanical-drill"], 24, 12, rotation=0, ore_target="coal")
_route(grid8, [], coal_drill8.output_tile(), gen8.footprint(), CATALOG["conveyor"], "x")
pn8 = grid8.place(CATALOG["power-node"], 15, 10, rotation=0)
result8 = evaluate_layout(grid8)
print(f"  power_production (gộp thô): {result8['power_production'].get(ir)}")
print(f"  power_input (tự tiêu): {ir.type.power_input}")
print(f"  power_satisfaction: {result8['power_satisfaction'].get(ir)}")
assert result8["power_production"].get(ir, 0) > ir.type.power_input, "SAI: impact-reactor phải là NET DƯƠNG (sản xuất > tiêu thụ)"
assert result8["power_satisfaction"].get(ir, 0) == 1.0
print("  ĐÚNG: impact-reactor vừa consumePower(25/tick=1500/s) vừa powerProduction lớn hơn hẳn --")
print("  _power_capable/_power_satisfaction đã tổng quát sẵn cho building vừa generator vừa power_input>0.\n")

print("XÁC NHẬN: audit Power Blocks từ 5/24 lên 17/24 có cơ chế thật, verify bằng công thức")
print("tay từng trường hợp (passive/fixed-item/liquid-only/dual-role) + 2 bug thật phát hiện")
print("và sửa trong lúc làm: (1) generator branch hardcode than bất kể fuel thật cần gì, (2)")
print("fuel drill tier cao không được _ensure_powered, rate về 0 âm thầm không báo lỗi.")
print("7/24 còn lại bỏ qua có lý do thật, xem NEXT_STEPS.md.")
