"""Test tự sinh ra khi tự đóng vai model LM Studio (đọc đúng system prompt
thật của bot/llm_parser.py, tự suy luận JSON như 1 model thật sẽ làm) cho
câu người dùng đã hỏi thật: "Khai thác than, và cát cho tôi, tách băng
chuyền ra làm 2, 1 nguồn dẫn về core, 1 nguồn tạo slicion".

Phát hiện 1 bug thật khác với bug đã vá trong plan_split_command (xem mục
"tự trace/xoá belt cũ" trong NEXT_STEPS.md): khi router đặt SÁT NGAY đích
(silicon-smelter mới xây nằm kề router, không cần belt ở giữa),
plan_split()/plan_filter_split() cũ SKIP ô đó vì coi "đã bị chiếm" (chính
LÀ đích!) rồi báo lỗi "không tìm được đường", dù simulator/sim.py's
_trace_branching coi bất kỳ building nào kề router là 1 nhánh hợp lệ (không
cần belt) -- 2 tầng code hiểu "occupied" khác nhau. Đã vá bằng cách kiểm tra
riêng case "đích nằm ngay ô kề" TRƯỚC khi coi ô đó là chướng ngại vật."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.llm_parser import _validate
from bot.planner import plan
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

TEXT = "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2 , 1 nguồn dẫn về core , 1 nguồn tạo slicion"

# JSON tôi (đóng vai model) tự sinh cho câu này -- không phải response viết
# sẵn cho khớp code. Dùng "split" (router, chia đều KHÔNG điều kiện) thay vì
# "filter_split" -- vì câu nói "tách BĂNG CHUYỀN ra làm 2" là chia đôi luồng,
# không phải lọc theo loại item (nguồn chỉ ra than, không có gì để "lọc").
MY_LLM_RESPONSE = [
    {"action": "build", "building": "drill", "ore_target": "coal"},
    {"action": "build", "building": "drill", "ore_target": "sand"},
    {
        "action": "split",
        "source": {"building": "drill", "hint": {"kind": "ore_target", "value": "coal"}},
        "destinations": [{"kind": "core"}, {"kind": "build", "building": "silicon-smelter"}],
    },
]

print("=== JSON tôi (đóng vai model) tự sinh cho câu này ===")
for c in MY_LLM_RESPONSE:
    print(f"  {c}")

commands = _validate(MY_LLM_RESPONSE, TEXT)
assert len(commands) == 3, f"SAI: cả 3 lệnh phải qua được validate, ra {len(commands)}"

state = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]]
              + [{"x": x, "y": y, "ore": "sand"} for x, y in [(10, 2), (11, 2), (10, 3), (11, 3)]]
              # mỏ than thứ 2 cho combustion-generator (silicon-smelter cần
              # điện, xem NEXT_STEPS.md).
              + [{"x": x, "y": y, "ore": "coal"} for x, y in [(15, 15), (16, 15), (15, 16), (16, 16)]],
    "buildings": [{"type": "core", "x": 20, "y": 10, "rotation": 0}],
}
grid = grid_from_state(state)

print("\n=== Chạy từng lệnh qua plan() thật ===")
for i, c in enumerate(commands):
    actions = plan(grid, c)
    print(f"  lệnh {i + 1} ({c['action']}): OK, {len(actions)} action")

result = evaluate_layout(grid)
core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
silicon = next(b for b in grid.unique_buildings() if b.type.name == "silicon-smelter")
print("\n=== Kết quả cuối ===")
print(f"  core:            {result['output_rate'][core]:.4f}/s")
print(f"  silicon-smelter: {result['output_rate'][silicon]:.4f}/s")

assert result["output_rate"][core] > 0, "SAI: core phải nhận được cát (nhánh 'other' tự nối)"
assert result["output_rate"][silicon] > 0, "SAI: silicon-smelter phải chạy được (router đặt sát đích vẫn phải nối được)"
print("\nĐÚNG: split hoạt động cả khi router đặt SÁT NGAY đích (không cần belt ở")
print("giữa) -- trường hợp thật xảy ra khi silicon-smelter được auto-đặt gần nguồn.")

# Bug thật thứ 3 (phát hiện khi người dùng hỏi thẳng "có tự nối silicon về
# core không?"): _resolve_split_destination trước đây chỉ lo INPUT của
# factory tự đặt mới (qua _find_or_build_factory_sources), quên nối luôn
# ĐẦU RA của nó về core -- factory craft được nhưng silicon không đi đâu cả,
# về mặt game thật sẽ chất đầy nội bộ rồi ngừng craft. Đã vá bằng cách gọi
# _connect_to_core() ngay sau khi factory đích được đặt mới, giống hệt cách
# plan_build's drill/factory branch đã làm từ trước.
silicon_to_core = any(src is silicon and dest is core for src, dest, cap in result["connections"])
assert silicon_to_core, "SAI: silicon-smelter (đích tự đặt mới của split) phải tự nối đầu ra về core"
print("\nĐÚNG: silicon-smelter (đích tự đặt mới của lệnh split) cũng tự nối đầu ra")
print("về core, không chỉ tự lo input -- khớp connections: silicon-smelter -> core.")
