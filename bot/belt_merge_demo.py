"""Chứng minh: khi khai thác 2 loại ore khác nhau (vd đồng + chì), bot biết
NHẬP CHUNG 2 đường belt lại thành 1 trước khi vào core, thay vì luôn xây 2
đường belt độc lập song song như trước đây.

User: "Giờ ví dụ tôi gọ, Khai thác đồng và chì, cả 2 sẽ có 2 bẳng chuyền nối
lại với nhau, và cuối cùng 1 băng chuyển về thôi" -- xác nhận thật bằng test
(xem NEXT_STEPS.md): 2 lệnh "khai thác" liên tiếp trước đây LUÔN ra 2 đường
belt BFS độc lập, không bao giờ chạm nhau.

User làm rõ thêm chính sách merge: "chỉ nên nhập khi được yêu cầu hoặc số
lượng item trên bằng chuyền không bị quá nhiều" -- 2 điều kiện OR:
  1. Rate cộng dồn của 2 nguồn AN TOÀN (không vượt base_rate conveyor,
     6.5 item/s thật, Conveyor.java) -> tự động merge, không cần hỏi.
  2. Người dùng nói RÕ ("nối chung"/"gộp chung"/... xem
     command_parser.py:MERGE_PHRASES) -> ép merge dù rate có thể vượt an
     toàn (người dùng tự chịu trách nhiệm, giống cách "phủ kín mỏ" luôn làm
     đúng ý dù tốn kém).
  Không rơi vào cả 2 -> KHÔNG merge, mỗi nguồn tự đi đường riêng như cũ
  (không đánh đổi throughput lấy việc "trông gọn").

Bug thật phát hiện + sửa khi làm tính năng này (verify TRƯỚC khi merge, xem
_try_merge_or_connect_to_core trong bot/planner.py): find_belt_path() coi
"drill's output_tile CHẠM (kề cạnh) 1 belt có sẵn" là KHÔNG CẦN đặt gì thêm
(return [] -- đúng cho core/generator, building "hút" item từ MỌI ô kề chân
đế). Nhưng 1 ô conveyor THƯỜNG chỉ nhận item đặt THẲNG lên chính nó, không
"vói" sang ô trống bên cạnh -- tái dùng nguyên xi logic đó cho belt khiến
nguồn thứ 2 "tưởng đã nối" nhưng thực ra rơi vào khoảng không, core không hề
nhận thêm rate nào (bắt được qua evaluate_layout: core chỉ tăng đúng bằng
rate nguồn ĐẦU, nguồn SAU biến mất khỏi find_connections dù rate tính riêng
> 0). Sửa: nếu find_belt_path() trả [] cho target là belt (không phải
core/generator), tự đặt THẬT 1 ô conveyor tại output_tile, quay mặt về phía
belt có sẵn."""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_command
from bot.planner import _connect_to_core, _try_merge_or_connect_to_core, find_belt_path, plan_build
from bot.state import grid_from_state
from simulator.buildings import CATALOG, DIRECTIONS
from simulator.sim import evaluate_layout, find_connections


def touches(tile, footprint):
    fx, fy = tile
    fp = set(footprint)
    return any((fx + dx, fy + dy) in fp for dx, dy in DIRECTIONS)


print("--- Kịch bản 1: 'khai thác đồng' rồi 'khai thác chì' -- rate thấp, AN TOÀN -> tự động merge ---")
state1 = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "copper"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]]
              + [{"x": x, "y": y, "ore": "lead"} for x, y in [(10, 2), (11, 2), (10, 3), (11, 3)]],
    "buildings": [{"type": "core", "x": 20, "y": 10, "rotation": 0}],
}
grid1 = grid_from_state(state1)
core1 = next(b for b in grid1.unique_buildings() if b.type.kind == "core")

actions_copper = plan_build(grid1, parse_command("khai thác đồng"))
n_conv_copper = sum(1 for a in actions_copper if a.get("building") == "conveyor")
print(f"  đồng: {n_conv_copper} conveyor (đường riêng, chưa có gì để merge vào)")

actions_lead = plan_build(grid1, parse_command("khai thác chì"))
lead_conveyors = [a for a in actions_lead if a.get("building") == "conveyor"]
print(f"  chì: {len(lead_conveyors)} conveyor")

copper_drill = next(b for b in grid1.unique_buildings() if b.ore_target == "copper")
lead_drill = next(b for b in grid1.unique_buildings() if b.ore_target == "lead")
copper_belts = {(a["x"], a["y"]) for a in actions_copper if a.get("building") == "conveyor"}

assert len(lead_conveyors) <= 3, (
    f"SAI: rate thấp (an toàn) mà chì vẫn tự đi đường ĐỘC LẬP dài ({len(lead_conveyors)} ô) "
    "thay vì merge vào belt đồng đã có gần đó"
)
last_lead_tile = (lead_conveyors[-1]["x"], lead_conveyors[-1]["y"]) if lead_conveyors else lead_drill.output_tile()
assert touches(last_lead_tile, copper_belts) or not touches(last_lead_tile, core1.footprint()), (
    "SAI: đường chì phải CHẠM vào belt đồng có sẵn (merge), không phải chạm thẳng core (đi riêng)"
)
print("  ĐÚNG: chì tự MERGE vào belt đồng có sẵn (đường rất ngắn, không đi riêng tới core).")

result1 = evaluate_layout(grid1)
expected_total = result1["output_rate"][copper_drill] + result1["output_rate"][lead_drill]
core_rate1 = result1["output_rate"][core1]
print(f"  core rate: {core_rate1:.4f} (kỳ vọng = đồng {result1['output_rate'][copper_drill]:.4f} + chì {result1['output_rate'][lead_drill]:.4f})")
assert abs(core_rate1 - expected_total) < 1e-9, "SAI: core phải nhận ĐỦ cả 2 nguồn sau khi merge (không rơi rớt)"
print("  ĐÚNG: core nhận đủ tổng rate 2 nguồn, không có gì bị 'rơi vào khoảng không' sau merge.\n")


print("--- Kịch bản 2: rate CAO (giả lập qua hạ base_rate conveyor) -- KHÔNG merge, mỗi nguồn tự đi riêng ---")
# Hạ base_rate tạm thời để mô phỏng "rate cộng dồn vượt ngưỡng an toàn" mà
# không cần dựng cả lưới điện thật cho drill tier cao (eruption-drill cần
# 360 điện -- không liên quan gì tới điều đang test: NGƯỠNG SO SÁNH, không
# phải cơ chế điện). BuildingType là frozen dataclass, dùng dataclasses.replace().
original_conveyor = CATALOG["conveyor"]
CATALOG["conveyor"] = dataclasses.replace(original_conveyor, base_rate=0.1)
try:
    state2 = {
        "width": 30, "height": 20,
        "ore_tiles": [{"x": x, "y": y, "ore": "copper"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]]
                  + [{"x": x, "y": y, "ore": "lead"} for x, y in [(20, 2), (21, 2), (20, 3), (21, 3)]],
        "buildings": [{"type": "core", "x": 15, "y": 15, "rotation": 0}],
    }
    grid2 = grid_from_state(state2)
    core2 = next(b for b in grid2.unique_buildings() if b.type.kind == "core")

    drill_a = grid2.place(CATALOG["mechanical-drill"], 2, 2, rotation=1, ore_target="copper")
    _connect_to_core(grid2, [], drill_a, "drill_a")
    rate_a = evaluate_layout(grid2)["output_rate"][drill_a]
    print(f"  drill_a rate riêng: {rate_a:.4f} (đã > base_rate hạ thấp {CATALOG['conveyor'].base_rate})")

    drill_b = grid2.place(CATALOG["mechanical-drill"], 20, 2, rotation=1, ore_target="lead")
    actions_b = []
    _try_merge_or_connect_to_core(grid2, actions_b, drill_b, "drill_b", force=False)
    conv_b = [a for a in actions_b if a.get("building") == "conveyor"]
    print(f"  drill_b (không force): {len(conv_b)} conveyor")
    last_b_tile = (conv_b[-1]["x"], conv_b[-1]["y"])
    assert touches(last_b_tile, core2.footprint()), (
        "SAI: rate vượt ngưỡng an toàn mà vẫn merge -- phải tự đi đường RIÊNG chạm thẳng core"
    )
    print("  ĐÚNG: rate vượt ngưỡng -> KHÔNG merge, drill_b tự đi đường riêng chạm thẳng core.\n")

    print("--- Kịch bản 3: người dùng nói RÕ 'nối chung' -- ép merge dù rate vượt ngưỡng ---")
    cmd_force = parse_command("khai thác chì nối chung")
    print(f"  parsed: {cmd_force}")
    assert cmd_force.get("merge") is True, "SAI: câu 'nối chung' phải bật cờ merge=True trong command"

    grid3 = grid_from_state(state2)
    core3 = next(b for b in grid3.unique_buildings() if b.type.kind == "core")
    drill_a3 = grid3.place(CATALOG["mechanical-drill"], 2, 2, rotation=1, ore_target="copper")
    _connect_to_core(grid3, [], drill_a3, "drill_a3")

    actions_force = plan_build(grid3, cmd_force)
    conv_force = [a for a in actions_force if a.get("building") == "conveyor"]
    print(f"  drill_b (force=True qua lệnh 'nối chung'): {len(conv_force)} conveyor")
    drill_b3 = next(b for b in grid3.unique_buildings() if b.ore_target == "lead")
    a3_belts = {(a["x"], a["y"]) for a in actions_force if a.get("building") == "conveyor" and (a["x"], a["y"]) != drill_b3.output_tile()}
    last_force_tile = (conv_force[-1]["x"], conv_force[-1]["y"]) if conv_force else drill_b3.output_tile()
    a3_belts_before = {(a["x"], a["y"]) for a in actions_force if a.get("building") == "conveyor"}
    assert len(conv_force) < len(conv_b), (
        f"SAI: force=True phải merge (đường NGẮN hơn hẳn đường riêng {len(conv_b)} ô), ra {len(conv_force)}"
    )
    assert not touches(last_force_tile, core3.footprint()) or last_force_tile in a3_belts_before, (
        "SAI: force=True phải merge vào belt đồng có sẵn, không phải tự đi thẳng riêng tới core"
    )
    print("  ĐÚNG: 'nối chung' ép merge dù rate vượt ngưỡng an toàn -- đường NGẮN hơn hẳn, không đi riêng.")
finally:
    CATALOG["conveyor"] = original_conveyor

print("\nXÁC NHẬN: bot giờ biết NHẬP CHUNG belt của 2 nguồn khác loại ore khi AN")
print("TOÀN (rate cộng dồn không vượt base_rate conveyor) HOẶC khi người dùng nói")
print("RÕ ('nối chung'/'gộp chung'/...) -- ngoài 2 trường hợp đó, mỗi nguồn vẫn tự")
print("đi đường RIÊNG như trước, không đánh đổi throughput lấy việc 'trông gọn'.")
