"""Bộ dịch lệnh chat -> danh sách hành động JSON, dùng model chạy trong LM
Studio thay cho dict tra từ khoá (bot/command_parser.py). Lý do đổi hẳn sang
LLM làm bộ dịch CHÍNH (không chỉ fallback): dict CHỈ tách được câu ghép theo
dấu phẩy/"và" thành nhiều lệnh ĐỘC LẬP -- không hiểu nổi cấu trúc phân nhánh
kiểu "tách than ra làm 2, 1 nguồn về core, 1 nguồn tạo silicon" (thử thật
bằng bot/command_parser.py:parse_commands(), 3/5 đoạn bị bỏ qua vì không có
đại diện trong ngữ pháp dict, xem NEXT_STEPS.md). Thêm ngữ pháp dict mới cho
từng kiểu câu chỉ vá được TỪNG TRƯỜNG HỢP CỤ THỂ, không tổng quát -- LLM hiểu
NGỮ NGHĨA nên tự suy ra được nhiều cách diễn đạt khác nhau cho cùng 1 ý,
miễn được cấp đủ schema + danh sách tên building thật.

Model vẫn CHỈ làm việc NLU (trích xuất Ý ĐỊNH thành JSON có cấu trúc) --
KHÔNG tự tính toạ độ/đường belt. Toàn bộ việc đặt-ở-đâu/nối-thế-nào vẫn do
bot/planner.py (thuật toán tất định: BFS, bảo toàn khối lượng, v.v.) quyết
định, giữ đúng triết lý xuyên suốt dự án: "bot không tự suy luận/đoán, chỉ
làm đúng cái được yêu cầu, từ chối rõ ràng khi không chắc".

CHƯA TEST VỚI MODEL THẬT -- không có LM Studio chạy trên máy lúc viết file
này. Logic _validate()/parse_commands_llm() đã test bằng response JSON GIẢ
LẬP (không gọi HTTP thật) trong bot/llm_split_demo.py, chứng minh pipeline
đúng NẾU model trả đúng schema -- không chứng minh model thật sẽ tuân thủ
schema tốt tới đâu, cần bạn xác nhận khi có LM Studio thật.

Đề xuất model (chỉ là gợi ý, đổi tay trong LM Studio + biến MODEL bên dưới):
  - Đủ mạnh, khuyên dùng trước: Qwen2.5-7B-Instruct
  - Máy yếu hơn: Qwen2.5-3B-Instruct hoặc Phi-3.5-mini-instruct
  Lý do: đây là tác vụ trích xuất JSON có schema cố định, không cần model
  lớn -- ưu tiên model tuân thủ instruction tốt hơn là model "thông minh".
"""

import json
import urllib.error
import urllib.request

from bot.command_parser import parse_commands as parse_commands_dict
from simulator.buildings import CATALOG

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen2.5-7b-instruct"  # sửa cho khớp tên model bạn load trong LM Studio

# planner.py hiện biết lập kế hoạch cho các kind này (xem plan_build/
# plan_split_command/plan_filter_split_command trong bot/planner.py) --
# không cấp tên turret/power/logic/unit/... vào ngữ cảnh model để tránh nó
# "vẽ" ra lệnh bot không thực thi được.
#
# Bug thật user tự phát hiện: set này HARDCODE tay, không tự đồng bộ theo
# CATALOG -- audit "Power Blocks" thêm kind="battery"/"beam-node" (build
# trực tiếp được qua plan_build(), xem NEXT_STEPS.md) nhưng quên cập nhật
# set này, khiến model LM Studio KHÔNG BAO GIỜ biết 2 loại đó tồn tại (dù
# dict parser -- bot/command_parser.py -- đã nhận diện được) dù kiến trúc
# hoàn toàn cho phép, chỉ là thiếu 1 dòng.
SUPPORTED_KINDS = {"drill", "belt", "factory", "pump", "sorter", "router", "generator", "power-node", "battery", "beam-node"}


def _valid_building_names():
    # "drill" là sentinel (KHÔNG phải tên catalog thật) -- nghĩa là "máy
    # khoan chung chung, chưa chỉ rõ tier", để bot/planner.py:select_drill_type()
    # tự chọn tier rẻ nhất đủ mạnh cho ore. Khớp đúng cơ chế đã dùng trong
    # bot/command_parser.py (xem BUILDING_PHRASES "máy khoan"->"drill").
    return sorted({name for name, b in CATALOG.items() if b.kind in SUPPORTED_KINDS} | {"drill"})


def _valid_factory_names():
    """Riêng factory -- dùng cho destination {"kind":"build",...} trong
    split/filter_split, chỉ factory mới "nhận" input hợp lý làm đích (xem
    bot/planner.py:_resolve_split_destination)."""
    return sorted(name for name, b in CATALOG.items() if b.kind == "factory")


def _system_prompt() -> str:
    names = ", ".join(_valid_building_names())
    factory_names = ", ".join(_valid_factory_names())
    return (
        "Bạn là bộ dịch lệnh cho 1 bot tự động xây dựng trong game Mindustry.\n"
        "Đọc 1 câu tiếng Việt của người dùng (có thể ghép nhiều ý cùng lúc), "
        "trả lời DUY NHẤT 1 JSON ARRAY các hành động theo đúng thứ tự người "
        "dùng muốn thực hiện -- không thêm chữ giải thích, không thêm markdown "
        "code fence. Câu chỉ có 1 ý thì trả mảng 1 phần tử.\n\n"
        "Mỗi phần tử trong mảng là 1 object theo action:\n\n"
        '- build:   {"action":"build","building":"<tên>","ore_target":"<item>"|null,"liquid_target":"<liquid>"|null}\n'
        "  (ore_target chỉ dùng khi building là drill; liquid_target chỉ dùng khi building là pump)\n\n"
        '- delete:  {"action":"delete","building":"<tên>","target_hint":<hint>|null}\n\n'
        '- rotate:  {"action":"rotate","building":"<tên>","target_hint":<hint>|null,"rotation":0|1|2|3}\n\n'
        '- reroute: {"action":"reroute","from_building":"<tên>","to_building":"<tên>","from_hint":<hint>|null,"to_hint":<hint>|null}\n\n'
        '- configure: {"action":"configure","building":"<tên>","target_hint":<hint>|null,"value":"<tên item>"}\n'
        "  (dùng khi cấu hình filter cho sorter, vd \"đặt bộ lọc sorter là than\")\n\n"
        '- split:   {"action":"split","source":{"building":"<tên>","hint":<hint>|null},"destinations":[<dest>,<dest>,...]}\n'
        "  Dùng khi người dùng muốn CHIA đầu ra 1 nguồn (drill/factory) ĐÃ CÓ hoặc SẮP xây thành "
        "NHIỀU nhánh không điều kiện (router thật -- chia đều cho các nhánh, không quan tâm loại item), "
        'vd "tách than ra làm 2, 1 về core 1 tạo silicon".\n\n'
        '- filter_split: {"action":"filter_split","source":{"building":"<tên>","hint":<hint>|null},'
        '"filter_item":"<tên item>","match":<dest>,"other":<dest>}\n'
        "  Dùng khi người dùng muốn CHIA THEO ĐIỀU KIỆN item khớp/không khớp (sorter thật): "
        '"match" là đích cho item KHỚP filter_item (đi thẳng), "other" là đích cho item KHÔNG khớp (rẽ). '
        'Vd "than đi thẳng vào máy X, còn lại rẽ sang máy Y" -- filter_item="coal", match=X, other=Y.\n\n'
        "<dest> (đích cho split/filter_split) là 1 trong:\n"
        '  {"kind":"core"}                          -- dẫn về core\n'
        '  {"kind":"build","building":"<tên factory>"}  -- dẫn tới 1 factory (dùng lại nếu đã có trên map, '
        "không thì bot tự đặt mới VÀ tự nối luôn input còn thiếu khác của nó, "
        "vd silicon-smelter cần cả than lẫn cát -- chỉ cần khai báo 1 trong 2 qua nhánh split, "
        "input còn lại bot tự tìm nguồn có sẵn)\n"
        f"  Tên factory hợp lệ cho \"kind\":\"build\": {factory_names}\n\n"
        "rotation: 0=Đông, 1=Nam, 2=Tây, 3=Bắc.\n\n"
        '"building"/"from_building"/"to_building"/source.building PHẢI là 1 trong danh sách tên thật sau, '
        f"không được bịa tên khác:\n{names}\n\n"
        'Riêng khi XÂY drill: nếu người dùng KHÔNG nói rõ loại/tier ("khai thác than", "máy khoan cát"...), '
        'dùng "building":"drill" (không phải tên tier cụ thể) -- bot sẽ tự chọn tier rẻ nhất đủ mạnh cho ore đó. '
        "Chỉ dùng tên tier cụ thể (mechanical-drill, pneumatic-drill, ...) khi người dùng NÓI RÕ tier.\n\n"
        "hint/target_hint/from_hint/to_hint/source.hint (chỉ rõ building nào khi có nhiều cái cùng loại trên "
        "map, hoặc chỉ rõ vị trí xây) là 1 trong:\n"
        '  {"kind":"coord","value":[x,y]}\n'
        '  {"kind":"index","value":n}   (n = thứ tự, 1 = cái đầu tiên)\n'
        '  {"kind":"ore_target","value":"<tên item>"}   (chỉ dùng được cho drill)\n'
        '  {"kind":"liquid_target","value":"<tên liquid>"}   (chỉ dùng được cho pump)\n'
        "  hoặc null nếu người dùng không nói gì để phân biệt.\n\n"
        "Nếu 1 phần câu không hiểu được / không map vào action nào ở trên, BỎ QUA phần đó "
        "(không thêm phần tử nào cho nó vào mảng), không đoán bừa. Nếu KHÔNG hiểu được câu nào cả, trả mảng rỗng [].\n"
    )


def _extract_json(content: str):
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


def _normalize_hint(raw):
    if not isinstance(raw, dict):
        return None
    kind, value = raw.get("kind"), raw.get("value")
    if kind == "coord" and isinstance(value, list) and len(value) == 2:
        return ("coord", (int(value[0]), int(value[1])))
    if kind == "index" and isinstance(value, (int, float)):
        return ("index", int(value))
    if kind == "ore_target" and isinstance(value, str):
        return ("ore_target", value)
    if kind == "liquid_target" and isinstance(value, str):
        return ("liquid_target", value)
    return None


def _normalize_dest(raw, valid_factory_names):
    """<dest> cho split/filter_split -- xem _system_prompt(). Trả None nếu
    không hợp lệ (nơi gọi sẽ bỏ qua action chứa dest này, không đoán)."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if kind == "core":
        return {"kind": "core"}
    if kind == "build":
        building = raw.get("building")
        if building not in valid_factory_names:
            return None
        return {"kind": "build", "building": building}
    return None


def _validate_one(command: dict, valid_names, valid_factory_names) -> dict:
    """Validate 1 action -- KHÔNG tin tưởng mù quáng output của model: building
    phải nằm trong CATALOG thật, action/dest phải đúng dạng. Sai gì cũng coi
    là 'unknown' (nơi gọi sẽ loại bỏ khỏi mảng kết quả), không để lỗi lan
    xuống planner."""
    if not isinstance(command, dict):
        return {"action": "unknown"}

    action = command.get("action")
    if action not in ("build", "delete", "rotate", "reroute", "configure", "split", "filter_split"):
        return {"action": "unknown"}

    if action == "reroute":
        if command.get("from_building") not in valid_names or command.get("to_building") not in valid_names:
            return {"action": "unknown"}
        return {
            "action": "reroute",
            "from_building": command["from_building"],
            "to_building": command["to_building"],
            "from_hint": _normalize_hint(command.get("from_hint")),
            "to_hint": _normalize_hint(command.get("to_hint")),
        }

    if action in ("split", "filter_split"):
        source_raw = command.get("source")
        if not isinstance(source_raw, dict) or source_raw.get("building") not in valid_names:
            return {"action": "unknown"}
        source = {"building": source_raw["building"], "hint": _normalize_hint(source_raw.get("hint"))}

        if action == "split":
            dest_specs = command.get("destinations")
            if not isinstance(dest_specs, list) or len(dest_specs) < 2:
                return {"action": "unknown"}
            destinations = [_normalize_dest(d, valid_factory_names) for d in dest_specs]
            if any(d is None for d in destinations):
                return {"action": "unknown"}
            return {"action": "split", "source": source, "destinations": destinations}

        filter_item = command.get("filter_item")
        if not isinstance(filter_item, str):
            return {"action": "unknown"}
        match = _normalize_dest(command.get("match"), valid_factory_names)
        other = _normalize_dest(command.get("other"), valid_factory_names)
        if match is None or other is None:
            return {"action": "unknown"}
        return {"action": "filter_split", "source": source, "filter_item": filter_item, "match": match, "other": other}

    if command.get("building") not in valid_names:
        return {"action": "unknown"}

    result = {"action": action, "building": command["building"]}

    if action == "build":
        if isinstance(command.get("ore_target"), str):
            result["ore_target"] = command["ore_target"]
        if isinstance(command.get("liquid_target"), str):
            result["liquid_target"] = command["liquid_target"]

    if action in ("delete", "rotate", "configure"):
        result["target_hint"] = _normalize_hint(command.get("target_hint"))

    if action == "rotate":
        rotation = command.get("rotation")
        if rotation not in (0, 1, 2, 3):
            return {"action": "unknown"}
        result["rotation"] = rotation

    if action == "configure":
        value = command.get("value")
        if not isinstance(value, str):
            return {"action": "unknown"}
        result["value"] = value

    return result


def _validate(raw, original_text: str) -> list:
    if not isinstance(raw, list):
        raw = [raw]  # model trả 1 object đơn thay vì mảng -- vẫn chấp nhận, coi như mảng 1 phần tử

    valid_names = set(_valid_building_names())
    valid_factory_names = set(_valid_factory_names())

    commands = []
    for item in raw:
        validated = _validate_one(item, valid_names, valid_factory_names)
        if validated["action"] != "unknown":
            commands.append(validated)
    return commands


def parse_commands_llm(text: str, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: float = 15.0) -> list:
    """Gọi LM Studio qua API tương thích OpenAI, trả về DANH SÁCH lệnh (có
    thể rỗng nếu model không hiểu gì, hoặc câu không chứa ý nào map được).
    Ném lỗi (không tự bắt) nếu LM Studio không chạy/không phản hồi -- dùng
    parse_commands_auto() nếu muốn tự động rơi về dict parser khi lỗi."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    content = result["choices"][0]["message"]["content"]
    raw_commands = _extract_json(content)
    return _validate(raw_commands, text)


def parse_commands_auto(text: str, **kwargs) -> list:
    """Ưu tiên LM Studio; nếu không kết nối được / model trả sai định dạng,
    tự rơi về dict parser (bot/command_parser.py:parse_commands) thay vì
    crash cả bot -- dict parser không hiểu split/filter_split nhưng vẫn xử
    lý được build/delete/rotate/reroute/configue đơn giản, đủ để bot không
    "câm" hoàn toàn khi LM Studio tắt."""
    try:
        return parse_commands_llm(text, **kwargs)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
        return parse_commands_dict(text)
