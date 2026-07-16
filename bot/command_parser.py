"""Dict-based Vietnamese command -> structured command dict.

Deliberately not an LLM: for a fixed, small vocabulary a lookup table is
faster, free, and 100% deterministic. Swap in an LM Studio call later only
if commands need to support more flexible phrasing (see NEXT_STEPS.md).

Hỗ trợ 5 loại action: build, delete, rotate, reroute, configure. Mặc định
là "build" nếu không khớp từ khoá hành động nào khác (giữ nguyên hành vi cũ).
"""

import re

from simulator.buildings import ITEMS as REAL_ITEMS
from simulator.buildings import LIQUIDS as REAL_LIQUIDS

# phrase (lowercase) -> building name in simulator.buildings.CATALOG
BUILDING_PHRASES = {
    "nhà máy silicon": "silicon-smelter",
    "máy nén silicon": "silicon-smelter",
    "silicon": "silicon-smelter",
    "nhà máy graphite": "graphite-press",
    "máy ép than": "graphite-press",
    "graphite": "graphite-press",
    "máy ép đa năng": "multi-press",
    "multi-press": "multi-press",
    # "drill" chung chung (không nói rõ tier) -> sentinel "drill", để
    # bot/planner.py:select_drill_type() tự chọn tier rẻ nhất đủ mạnh cho
    # ore được yêu cầu, thay vì luôn hardcode mechanical-drill (bug thật:
    # ore cứng hơn tier 2 sẽ không mine được gì nếu cứ ép mechanical-drill).
    "máy khoan": "drill",
    "khai thác": "drill",
    "drill": "drill",
    # nói rõ tier -> dùng đúng loại đó, không tự chọn
    "máy khoan cơ bản": "mechanical-drill",
    "mechanical-drill": "mechanical-drill",
    "máy khoan khí nén": "pneumatic-drill",
    "pneumatic-drill": "pneumatic-drill",
    "máy khoan laser": "laser-drill",
    "laser-drill": "laser-drill",
    "máy khoan nổ": "blast-drill",
    "blast-drill": "blast-drill",
    "máy khoan va đập": "impact-drill",
    "impact-drill": "impact-drill",
    "máy khoan phun trào": "eruption-drill",
    "eruption-drill": "eruption-drill",
    # BeamDrill.java (bắn tia dò ore từ mỗi cạnh, không phải diện tích chân
    # đế -- xem sim.py _beam_drill_output_rate). Phải nói RÕ "plasma" vì
    # cơ chế khác hẳn "máy khoan" thường, không dùng chung sentinel "drill".
    "máy khoan plasma lớn": "large-plasma-bore",
    "large-plasma-bore": "large-plasma-bore",
    "máy khoan plasma": "plasma-bore",
    "plasma-bore": "plasma-bore",
    # WallCrafter.java (đọc attribute từ đá/tường tự nhiên kề cạnh xoay mặt
    # tới, luôn ra cát -- xem sim.py _wall_crafter_output_rate). Không cần
    # nói rõ ore vì cố định sẵn (wall_attribute/wall_output của building).
    "máy nghiền vách đá lớn": "large-cliff-crusher",
    "large-cliff-crusher": "large-cliff-crusher",
    "máy nghiền vách đá": "cliff-crusher",
    "cliff-crusher": "cliff-crusher",
    # SolidPump.java (đọc attribute trên nền đất, quét cả chân đế -- xem
    # sim.py _solid_pump_output_rate). Cùng tinh thần wall-crafter: không
    # cần chỉ định liquid_target, cố định theo catalog (luôn ra nước).
    "máy hút nước": "water-extractor",
    "water-extractor": "water-extractor",
    "bộ lọc": "sorter",
    "sorter": "sorter",
    "bơm": "mechanical-pump",
    "pump": "mechanical-pump",
    # nhà máy điện (generator, đốt item cháy được -- xem ConsumeGenerator.java,
    # NEXT_STEPS.md mục "Mạng điện"). Không nói rõ loại -> mặc định
    # combustion-generator (rẻ nhất, chỉ cần than, không cần nước), giống
    # tinh thần "máy khoan" mặc định tier rẻ nhất. Nói rõ "hơi nước" -> đúng
    # steam-generator (cần thêm nước, công suất cao hơn).
    "nhà máy điện": "combustion-generator",
    "máy phát điện": "combustion-generator",
    "nhà máy đốt than": "combustion-generator",
    "combustion-generator": "combustion-generator",
    "nhà máy điện hơi nước": "steam-generator",
    "nhà máy hơi nước": "steam-generator",
    "máy phát điện hơi nước": "steam-generator",
    "steam-generator": "steam-generator",
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

# liquid keyword (lowercase) -> liquid name in simulator.buildings.LIQUIDS,
# dùng khi cần chỉ rõ liquid cho pump ("bơm nước")
LIQUID_PHRASES = {
    "nước": "water",
    "dầu": "oil",
    "xỉ": "slag",
}


def _find_liquid(text: str):
    for phrase in sorted(LIQUID_PHRASES, key=len, reverse=True):
        if phrase in text:
            return LIQUID_PHRASES[phrase]
    for name in sorted(REAL_LIQUIDS, key=len, reverse=True):
        if name in text:
            return name
    return None

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

# "phía X"/"hướng X" (2 từ) khi XÂY -- chỉ định mỏ/tile liquid nào trong số
# nhiều cái cùng loại quanh core, khác DIRECTION_WORDS (1 từ, dùng cho xoay)
# để tránh nhầm 2 việc khác nhau.
LOCATION_DIRECTION_WORDS = {
    "phía đông": 0, "hướng đông": 0,
    "phía nam": 1, "hướng nam": 1,
    "phía tây": 2, "hướng tây": 2,
    "phía bắc": 3, "hướng bắc": 3,
}

ORDINAL_WORDS = {"nhất": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5}
# Bắt buộc có ngoặc đơn -- trước đây ngoặc là tuỳ chọn (`\(?...\)?`), khiến
# câu tự nhiên kiểu "chia làm 2, 1 nguồn..." bị hiểu nhầm cụm "2, 1" thành
# toạ độ (2,1) (bug thật, xem NEXT_STEPS.md). Toạ độ thật luôn có ngoặc khi
# người dùng gõ ("(2,2)"), câu nói thường không tự nhiên viết số-phẩy-số có
# ngoặc, nên yêu cầu ngoặc gần như loại hết false positive mà không mất khả
# năng nhận toạ độ thật.
COORD_RE = re.compile(r"\((\d+)\s*,\s*(\d+)\)")
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


_DRILL_NAMES = {
    "drill", "mechanical-drill", "pneumatic-drill", "laser-drill",
    "blast-drill", "impact-drill", "eruption-drill",
    # BeamDrill: cũng cần ore_target người dùng chỉ định (khác wall-crafter
    # -- luôn ra cát cố định, không cần hỏi), xem bot/planner.py:
    # find_beam_drill_spot.
    "plasma-bore", "large-plasma-bore",
}

# Bug thật (user tự phát hiện): "drill cấp 4 đào chì" bị âm thầm rớt về
# sentinel "drill" -- không có phrase nào bắt SỐ tier, chỉ bắt được TÊN
# riêng ("máy khoan laser"). select_drill_type() (planner.py) sau đó tự
# chọn tier RẺ NHẤT đủ dùng, phớt lờ hoàn toàn ý người dùng. Map số tier
# thật (xem simulator/generated_catalog.py) -> tên drill đúng tier đó, để
# "cấp N"/"tier N" ép ĐÚNG tier thay vì bị bỏ qua.
DRILL_TIER_NAMES = {
    2: "mechanical-drill", 3: "pneumatic-drill", 4: "laser-drill",
    5: "blast-drill", 6: "impact-drill", 7: "eruption-drill",
}
TIER_RE = re.compile(r"(?:cấp|tier)\s*(\d+)")

# "phủ kín mỏ than" -- lặp đặt drill tới khi hết mỏ (bot/planner.py:
# plan_fill_ore), khác lệnh xây thường CHỈ đặt đúng 1 drill dù mỏ to cỡ
# nào. Chỉ áp dụng cho drill (có ore_target) -- xem docstring plan_fill_ore.
FILL_PHRASES = ("phủ kín mỏ", "phủ kín", "phủ hết mỏ", "phủ hết", "hết mỏ", "toàn bộ mỏ", "cả mỏ")

# ConsumeGenerator.java thật (combustion-generator/steam-generator) -- user
# hỏi "xây 21 máy phát điện siêu nhỏ" thì bot có tự cấp than + dùng chung 1
# nguồn qua router không (xem NEXT_STEPS.md mục "cụm generator") -- cần bắt
# được SỐ LƯỢNG để biết đây là lệnh xây CỤM (plan_build_generator_cluster),
# khác lệnh xây 1 generator thường.
_GENERATOR_NAMES = {"combustion-generator", "steam-generator"}
COUNT_RE = re.compile(r"\b(\d+)\b")


def _find_hint(text: str, building: str = None):
    """Toạ độ, thứ tự, hoặc (với drill) loại ore để phân biệt khi có nhiều
    building cùng loại (xem bot/planner.py:resolve_target). Với drill, loại
    ore ("máy khoan than" vs "máy khoan cát") tự nhiên hơn hẳn toạ độ nên ưu
    tiên kiểm tra trước -- áp dụng cho mọi tier drill, không chỉ
    mechanical-drill (khác tier vẫn có thể cùng đào 1 loại ore)."""
    if building in _DRILL_NAMES:
        for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
            if phrase in text:
                return ("ore_target", ORE_PHRASES[phrase])
    if building == "mechanical-pump":
        liquid = _find_liquid(text)
        if liquid is not None:
            return ("liquid_target", liquid)

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


def _find_location_hint(text: str):
    """Chỉ dùng khi XÂY -- người dùng chỉ định RÕ mỏ/tile liquid nào trong
    số nhiều cái cùng loại (vd "4 mỏ quanh core, xây ở mỏ phía bắc"), thay
    vì để planner tự động chọn gần core nhất (xem
    bot/planner.py:_select_tile). Toạ độ ưu tiên trước (rõ nhất), rồi hướng,
    rồi thứ tự."""
    m = COORD_RE.search(text)
    if m:
        return ("coord", (int(m.group(1)), int(m.group(2))))
    for phrase in sorted(LOCATION_DIRECTION_WORDS, key=len, reverse=True):
        if phrase in text:
            return ("direction", LOCATION_DIRECTION_WORDS[phrase])
    m = ORDINAL_RE.search(text)
    if m:
        raw = m.group(1)
        value = int(raw) if raw.isdigit() else ORDINAL_WORDS.get(raw)
        if value:
            return ("index", value)
    return None


def parse_command(text: str) -> dict:
    normalized = text.lower().strip()

    # Bug thật phát hiện khi test lệnh cụm generator: "phá" (ACTION_PHRASES
    # -> delete) là SUBSTRING của "phát" trong "máy phát điện" -- match kiểu
    # `phrase in normalized` (dùng suốt file này cho hầu hết phrase khác,
    # thường an toàn vì building/ore name đủ dài/đặc trưng) khiến "xây máy
    # phát điện" bị hiểu nhầm hoàn toàn thành action="delete". Riêng
    # ACTION_PHRASES cần ranh giới từ thật (\b) vì có phrase quá ngắn/dễ
    # trùng biên chữ tiếng Việt như thế này.
    action = "build"
    for phrase in sorted(ACTION_PHRASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
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

    if action == "build" and building in _DRILL_NAMES:
        m = TIER_RE.search(normalized)
        if m:
            tier_name = DRILL_TIER_NAMES.get(int(m.group(1)))
            if tier_name is not None:
                # Số tier nói RÕ luôn thắng, kể cả khi _find_building() đã
                # khớp 1 tên riêng khác (vd "máy khoan laser cấp 2" -- ưu
                # tiên số 2 nói rõ hơn là suy luận từ tên).
                building = tier_name

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

    if action == "build" and building in _DRILL_NAMES:
        for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
            if phrase in normalized:
                command["ore_target"] = ORE_PHRASES[phrase]
                break
        command["ore_location_hint"] = _find_location_hint(normalized)
        if any(phrase in normalized for phrase in FILL_PHRASES):
            command["fill"] = True

    if action == "build" and building == "mechanical-pump":
        liquid = _find_liquid(normalized)
        if liquid is not None:
            command["liquid_target"] = liquid

    if action == "build" and building in _GENERATOR_NAMES:
        m = COUNT_RE.search(normalized)
        if m:
            command["count"] = int(m.group(1))
        command["liquid_location_hint"] = _find_location_hint(normalized)

    return command


SEGMENT_SPLIT_RE = re.compile(r",|\bvà\b")


def parse_commands(text: str) -> list:
    """Tách 1 câu ghép nhiều ý thành danh sách lệnh riêng, vd "khai thác
    than, và cát cho tôi" -> 2 lệnh xây drill (than, cát) thay vì chỉ 1 lệnh
    rồi bỏ qua phần còn lại (bug thật -- parse_command() chỉ trích được
    ĐÚNG 1 building/câu vì _find_building() dừng ngay khi khớp phrase đầu
    tiên, xem NEXT_STEPS.md).

    Dict-based nên chỉ tách được theo dấu phẩy/"và" -- không hiểu được ý
    ghép phức tạp hơn không map vào action/building nào cả (vd "tách belt ra
    làm 2 nhánh" không có đại diện trong schema lệnh hiện tại, đoạn đó bị bỏ
    qua thay vì đoán bừa thành hành động gì đó).

    Có xử lý tỉnh lược động từ đơn giản: "khai thác than, và cát" -- đoạn
    "cát" không tự có động từ riêng, kế thừa hành động (xây drill/pump) từ
    đoạn liền trước nếu đoạn đó khớp đúng dạng đó.
    """
    segments = [s.strip() for s in SEGMENT_SPLIT_RE.split(text) if s.strip()]
    commands = []
    last_building = None  # để kế thừa khi đoạn sau chỉ có tên ore/liquid

    for seg in segments:
        command = parse_command(seg)

        if command["action"] == "unknown":
            normalized = seg.lower()
            if last_building in _DRILL_NAMES:
                for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
                    if phrase in normalized:
                        command = {
                            "action": "build", "building": "drill", "ore_target": ORE_PHRASES[phrase],
                            "ore_location_hint": _find_location_hint(normalized),
                        }
                        break
            elif last_building == "mechanical-pump":
                liquid = _find_liquid(normalized)
                if liquid is not None:
                    command = {
                        "action": "build", "building": "mechanical-pump", "liquid_target": liquid,
                        "liquid_location_hint": _find_location_hint(normalized),
                    }

        if command["action"] == "unknown":
            continue  # không hiểu được đoạn này -- bỏ qua, không đoán bừa

        if command["action"] == "build":
            last_building = command.get("building")

        commands.append(command)

    return commands
