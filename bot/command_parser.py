"""Dict-based Vietnamese command -> structured command dict.

Deliberately not an LLM: for a fixed, small vocabulary a lookup table is
faster, free, and 100% deterministic. Swap in an LM Studio call later only
if commands need to support more flexible phrasing (see NEXT_STEPS.md).

Hỗ trợ 5 loại action: build, delete, rotate, reroute, configure. Mặc định
là "build" nếu không khớp từ khoá hành động nào khác (giữ nguyên hành vi cũ).
"""

import re

from simulator.buildings import ITEMS as REAL_ITEMS

# phrase (lowercase) -> building name in simulator.buildings.CATALOG
BUILDING_PHRASES = {
    "nhà máy silicon": "silicon-smelter",
    "máy nén silicon": "silicon-smelter",
    "silicon": "silicon-smelter",
    "nhà máy graphite": "graphite-press",
    "máy ép than": "graphite-press",
    "graphite": "graphite-press",
    "máy khoan": "mechanical-drill",
    "drill": "mechanical-drill",
    "bộ lọc": "sorter",
    "sorter": "sorter",
}

# ore keyword (lowercase) -> item name in simulator.buildings.ITEMS, dùng khi
# cần chỉ rõ ore cho drill hoặc item để cấu hình sorter
ORE_PHRASES = {
    "than": "coal",
    "đồng": "copper",
    "cát": "sand",
    "chì": "lead",
    "titan": "titanium",
}

# phrase -> action, checked before assuming "build"
ACTION_PHRASES = {
    "xóa": "delete", "xoá": "delete", "phá": "delete", "dỡ": "delete", "gỡ": "delete",
    "đổi hướng": "rotate", "xoay": "rotate", "quay": "rotate",
    "nối lại": "reroute", "định tuyến lại": "reroute",
    "chỉnh lại đường ray": "reroute", "sửa đường ray": "reroute", "đổi đường ray": "reroute",
    "cấu hình": "configure", "đặt bộ lọc": "configure",
    "chỉnh bộ lọc": "configure", "chỉnh lọc": "configure",
}

# hướng xoay -> rotation index (xem simulator.buildings.DIRECTIONS: 0=Đông,1=Nam,2=Tây,3=Bắc)
DIRECTION_WORDS = {
    "đông": 0, "phải": 0,
    "nam": 1, "xuống": 1,
    "tây": 2, "trái": 2,
    "bắc": 3, "lên": 3,
}

ORDINAL_WORDS = {"nhất": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5}
COORD_RE = re.compile(r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?")
ORDINAL_RE = re.compile(r"thứ\s+(nhất|hai|ba|tư|bốn|năm|\d+)")
REROUTE_RE = re.compile(r"từ (.+?) (?:đến|tới) (.+)")


def _find_building(text: str):
    for phrase in sorted(BUILDING_PHRASES, key=len, reverse=True):
        if phrase in text:
            return BUILDING_PHRASES[phrase]
    return None


def _find_item(text: str):
    """Tên item bất kỳ (không chỉ ore) -- dùng cho configure (vd lọc sorter
    theo item nào). Thử tên tiếng Việt quen thuộc trước, rồi thử khớp thẳng
    tên tiếng Anh thật (nhiều item ít phổ biến người chơi hay gọi nguyên tên
    gốc, vd "titanium", "plastanium", "graphite")."""
    for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
        if phrase in text:
            return ORE_PHRASES[phrase]
    for name in sorted(REAL_ITEMS, key=len, reverse=True):
        if name in text:
            return name
    return None


def _find_hint(text: str, building: str = None):
    """Toạ độ, thứ tự, hoặc (với drill) loại ore để phân biệt khi có nhiều
    building cùng loại (xem bot/planner.py:resolve_target). Với drill, loại
    ore ("máy khoan than" vs "máy khoan cát") tự nhiên hơn hẳn toạ độ nên ưu
    tiên kiểm tra trước."""
    if building == "mechanical-drill":
        for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
            if phrase in text:
                return ("ore_target", ORE_PHRASES[phrase])

    m = COORD_RE.search(text)
    if m:
        return ("coord", (int(m.group(1)), int(m.group(2))))
    m = ORDINAL_RE.search(text)
    if m:
        raw = m.group(1)
        value = int(raw) if raw.isdigit() else ORDINAL_WORDS.get(raw)
        if value:
            return ("index", value)
    return None


def parse_command(text: str) -> dict:
    normalized = text.lower().strip()

    action = "build"
    for phrase in sorted(ACTION_PHRASES, key=len, reverse=True):
        if phrase in normalized:
            action = ACTION_PHRASES[phrase]
            break

    if action == "reroute":
        m = REROUTE_RE.search(normalized)
        if not m:
            return {"action": "unknown", "raw": text}
        from_building = _find_building(m.group(1))
        to_building = _find_building(m.group(2))
        if from_building is None or to_building is None:
            return {"action": "unknown", "raw": text}
        return {
            "action": "reroute",
            "from_building": from_building,
            "to_building": to_building,
            "from_hint": _find_hint(m.group(1), from_building),
            "to_hint": _find_hint(m.group(2), to_building),
        }

    building = _find_building(normalized)
    if building is None:
        return {"action": "unknown", "raw": text}

    command = {"action": action, "building": building}

    if action in ("delete", "rotate", "configure"):
        command["target_hint"] = _find_hint(normalized, building)

    if action == "rotate":
        rotation = None
        for word in sorted(DIRECTION_WORDS, key=len, reverse=True):
            if word in normalized:
                rotation = DIRECTION_WORDS[word]
                break
        if rotation is None:
            return {"action": "unknown", "raw": text}
        command["rotation"] = rotation

    if action == "configure":
        value = _find_item(normalized)
        if value is None:
            return {"action": "unknown", "raw": text}
        command["value"] = value

    if action == "build" and building == "mechanical-drill":
        for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
            if phrase in normalized:
                command["ore_target"] = ORE_PHRASES[phrase]
                break

    return command
