"""KHÔNG gọi LM Studio thật (không có server chạy sẵn để test) -- giả lập
đúng response JSON mà model NÊN trả về cho câu người dùng đã hỏi thật:
"Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2, 1 nguồn dẫn về
core, 1 nguồn tạo silicon" (câu này bot/command_parser.py dict-based bỏ qua
mất 3/5 đoạn, xem NEXT_STEPS.md).

Mục đích: chứng minh pipeline (_validate() -> plan() dispatcher ->
plan_split_command/plan_filter_split_command) hoạt động ĐÚNG khi model trả
về đúng schema -- KHÔNG chứng minh model thật (Qwen2.5 hay bất kỳ model nào
chạy trong LM Studio) sẽ tự sinh ra đúng JSON này, việc đó cần LM Studio
thật để xác nhận (xem bot/llm_parser.py docstring)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.llm_parser import _validate
from bot.planner import plan
from bot.state import grid_from_state
from simulator.sim import evaluate_layout

TEXT = "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2, 1 nguồn dẫn về core, 1 nguồn tạo silicon"

# Response JSON GIẢ LẬP -- đúng dạng model sẽ trả nếu tuân thủ schema trong
# bot/llm_parser.py:_system_prompt(). Khác hẳn dict parser: LLM tự hiểu được
# "tách... làm 2, 1 nguồn... 1 nguồn..." là 1 lệnh filter_split có cấu trúc,
# không phải chuỗi đoạn rời rạc.
FAKE_LLM_RESPONSE = [
    {"action": "build", "building": "drill", "ore_target": "coal"},
    {"action": "build", "building": "drill", "ore_target": "sand"},
    {
        "action": "filter_split",
        "source": {"building": "drill", "hint": {"kind": "ore_target", "value": "coal"}},
        "filter_item": "coal",
        "match": {"kind": "build", "building": "silicon-smelter"},
        "other": {"kind": "core"},
    },
]

print(f'=== Câu người dùng: "{TEXT}" ===\n')

print("=== Bước 1: _validate() kiểm tra response JSON giả lập ===")
commands = _validate(FAKE_LLM_RESPONSE, TEXT)
assert len(commands) == 3, f"SAI: phải giữ lại đủ 3 lệnh hợp lệ, ra {len(commands)}"
for c in commands:
    print(f"  {c}")
print("  ĐÚNG: cả 3 lệnh qua được validate (building/action/dest đều hợp lệ).\n")

print("=== Bước 2: chạy từng lệnh qua plan(), state cập nhật dần (giống bot/live_run.py) ===")
state = {
    "width": 30, "height": 20,
    "ore_tiles": [{"x": x, "y": y, "ore": "coal"} for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]]
              + [{"x": x, "y": y, "ore": "sand"} for x, y in [(10, 2), (11, 2), (10, 3), (11, 3)]],
    "buildings": [{"type": "core", "x": 20, "y": 10, "rotation": 0}],
}
grid = grid_from_state(state)

for i, command in enumerate(commands):
    print(f"\n--- lệnh {i + 1}: {command} ---")
    actions = plan(grid, command)
    for a in actions:
        print(f"    {a}")

print("\n=== Bước 3: evaluate_layout -- silicon-smelter phải chạy được ===")
result = evaluate_layout(grid)
silicon = next(b for b in grid.unique_buildings() if b.type.name == "silicon-smelter")
core = next(b for b in grid.unique_buildings() if b.type.kind == "core")
print(f"  silicon-smelter: {result['output_rate'][silicon]:.4f}/s")
print(f"  core:            {result['output_rate'][core]:.4f}/s")

assert result["output_rate"][silicon] > 0, "SAI: silicon-smelter phải chạy được"
assert result["output_rate"][core] > 0, "SAI: core vẫn phải nhận được gì đó (nhánh 'other' của sand)"
print("\nXÁC NHẬN: pipeline LLM (schema mới, nhiều lệnh + split/filter_split) xử lý")
print("ĐÚNG chính xác câu người dùng đã hỏi -- điều mà dict parser (parse_commands)")
print("KHÔNG làm được (3/5 đoạn bị bỏ qua, xem lại lịch sử hội thoại/NEXT_STEPS.md).")
print("\nLƯU Ý: đây là test với response GIẢ LẬP, chưa xác nhận model thật trong")
print("LM Studio sẽ tự sinh đúng JSON này -- cần bạn bật LM Studio và thử thật.")
