"""Bộ dịch lệnh chat -> JSON hành động, dùng model chạy trong LM Studio thay
cho dict tra từ khoá (bot/command_parser.py). Lý do đổi: dict phải thêm tay
từng building/cách nói mới, không scale nổi khi danh mục building lên tới
hàng chục cái (xem simulator/generated_catalog.py). Model tự tổng quát hoá
cách diễn đạt, chỉ cần được cấp đúng danh sách tên building thật.

CHƯA TEST -- không có LM Studio chạy trên máy lúc viết file này. Cần bạn
xác nhận khi có LM Studio thật (xem NEXT_STEPS.md, mục "Bộ dịch lệnh bằng
LM Studio").

Đề xuất model (chỉ là gợi ý, đổi tay trong LM Studio + biến MODEL bên dưới):
  - Đủ mạnh, khuyên dùng trước: Qwen2.5-7B-Instruct
  - Máy yếu hơn: Qwen2.5-3B-Instruct hoặc Phi-3.5-mini-instruct
  Lý do: đây là tác vụ trích xuất JSON có schema cố định, không cần model
  lớn -- ưu tiên model tuân thủ instruction tốt hơn là model "thông minh".
"""

import json
import urllib.error
import urllib.request

from bot.command_parser import parse_command as parse_command_dict
from simulator.buildings import CATALOG

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen2.5-7b-instruct"  # sửa cho khớp tên model bạn load trong LM Studio

# planner.py hiện chỉ biết lập kế hoạch cho 3 kind này -- không cấp tên
# turret/power/liquid... vào ngữ cảnh model để tránh nó "vẽ" ra lệnh bot
# không thực thi được.
SUPPORTED_KINDS = {"drill", "belt", "factory"}


def _valid_building_names():
    return sorted(name for name, b in CATALOG.items() if b.kind in SUPPORTED_KINDS)


def _system_prompt() -> str:
    names = ", ".join(_valid_building_names())
    return (
        "Bạn là bộ dịch lệnh cho 1 bot tự động xây dựng trong game Mindustry.\n"
        "Đọc 1 câu tiếng Việt của người dùng, trả lời DUY NHẤT 1 JSON object đúng "
        "schema dưới đây -- không thêm chữ giải thích, không thêm markdown code fence.\n\n"
        "Schema theo action:\n"
        '- build:   {"action":"build","building":"<tên>","ore_target":"<tên item, chỉ khi building là drill>"}\n'
        '- delete:  {"action":"delete","building":"<tên>","target_hint":<hint hoặc null>}\n'
        '- rotate:  {"action":"rotate","building":"<tên>","target_hint":<hint hoặc null>,"rotation":0|1|2|3}\n'
        '- reroute: {"action":"reroute","from_building":"<tên>","to_building":"<tên>","from_hint":<hint>,"to_hint":<hint>}\n'
        '- không hiểu câu:  {"action":"unknown"}\n\n'
        "rotation: 0=Đông, 1=Nam, 2=Tây, 3=Bắc.\n\n"
        '"building"/"from_building"/"to_building" PHẢI là 1 trong danh sách tên thật sau, '
        f"không được bịa tên khác:\n{names}\n\n"
        "hint (chỉ rõ building nào khi có nhiều cái cùng loại trên map) là 1 trong:\n"
        '  {"kind":"coord","value":[x,y]}\n'
        '  {"kind":"index","value":n}   (n = thứ tự, 1 = cái đầu tiên)\n'
        '  {"kind":"ore_target","value":"<tên item>"}   (chỉ dùng được cho drill)\n'
        "  hoặc null nếu người dùng không nói gì để phân biệt.\n"
    )


def _extract_json(content: str) -> dict:
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
    return None


def _validate(command: dict, original_text: str) -> dict:
    """Không tin tưởng mù quáng output của model -- building phải nằm trong
    CATALOG thật, action phải hợp lệ, rotation phải đúng khoảng. Sai gì cũng
    coi là 'unknown' thay vì để lỗi lan xuống planner."""
    if not isinstance(command, dict):
        return {"action": "unknown", "raw": original_text}

    action = command.get("action")
    if action not in ("build", "delete", "rotate", "reroute", "unknown"):
        return {"action": "unknown", "raw": original_text}
    if action == "unknown":
        return {"action": "unknown", "raw": original_text}

    valid_names = set(_valid_building_names())

    if action == "reroute":
        if command.get("from_building") not in valid_names or command.get("to_building") not in valid_names:
            return {"action": "unknown", "raw": original_text}
        return {
            "action": "reroute",
            "from_building": command["from_building"],
            "to_building": command["to_building"],
            "from_hint": _normalize_hint(command.get("from_hint")),
            "to_hint": _normalize_hint(command.get("to_hint")),
        }

    if command.get("building") not in valid_names:
        return {"action": "unknown", "raw": original_text}

    result = {"action": action, "building": command["building"]}

    if action == "build" and "ore_target" in command:
        result["ore_target"] = command["ore_target"]

    if action in ("delete", "rotate"):
        result["target_hint"] = _normalize_hint(command.get("target_hint"))

    if action == "rotate":
        rotation = command.get("rotation")
        if rotation not in (0, 1, 2, 3):
            return {"action": "unknown", "raw": original_text}
        result["rotation"] = rotation

    return result


def parse_command_llm(text: str, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: float = 15.0) -> dict:
    """Gọi LM Studio qua API tương thích OpenAI. Ném lỗi (không tự bắt) nếu
    LM Studio không chạy/không phản hồi -- dùng parse_command_auto() nếu
    muốn tự động rơi về dict parser khi lỗi."""
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
    raw_command = _extract_json(content)
    return _validate(raw_command, text)


def parse_command_auto(text: str, **kwargs) -> dict:
    """Ưu tiên LM Studio; nếu không kết nối được / model trả sai định dạng,
    tự rơi về dict parser (bot/command_parser.py) thay vì crash cả bot."""
    try:
        return parse_command_llm(text, **kwargs)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
        return parse_command_dict(text)
