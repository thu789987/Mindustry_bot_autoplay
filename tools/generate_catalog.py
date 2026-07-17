"""Tự động sinh danh mục building/item/liquid đầy đủ từ mã nguồn thật
Mindustry (reference/*.java), thay vì gõ tay từng cái.

KHÔNG phải trình dịch Java đầy đủ -- dùng brace-matching để cắt đúng thân
mỗi block definition (`new ClassName("name"){{ ... }};`), rồi regex trên
phần thân đó để lấy field cần. Đủ tin cậy với code style nhất quán của
Mindustry, nhưng không phải giải pháp tổng quát cho Java bất kỳ.

3 lớp phủ:
1. Cơ chế hiểu đầy đủ (rate/recipe tính được, planner đặt+nối được):
   Drill/BurstDrill, BeamDrill (bắn tia dò ore từ mỗi cạnh, xem sim.py
   _beam_drill_output_rate), WallCrafter (đọc attribute từ đá/tường tự
   nhiên kề cạnh xoay mặt tới, xem sim.py _wall_crafter_output_rate),
   SolidPump (giống WallCrafter nhưng quét CẢ chân đế thay vì 1 cạnh, xem
   sim.py _solid_pump_output_rate), Conveyor/ArmoredConveyor, GenericCrafter
   (cả item lẫn liquid input), Sorter, Pump, Conduit/ArmoredConduit.
2. Cơ chế biết nhưng KHÔNG model (lý do ghi rõ trong SKIPPED, không phải bỏ
   sót âm thầm): StackConveyor (cơ chế xếp chồng khác hẳn), Pump tự tiêu
   thụ liquid (reinforced-pump).
3. Mọi block khác (turret/power/logic/unit/storage/defense/payload...):
   chỉ lưu tên+category+size vào GENERATED_OTHER, KHÔNG có recipe/rate --
   planner từ chối đặt loại này với lỗi rõ ràng thay vì đoán bừa. Xem
   NEXT_STEPS.md mục "Phạm vi chưa làm" cho việc mỗi loại cần gì để làm thật.

Chạy: python tools/generate_catalog.py
Ghi ra: simulator/generated_catalog.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "reference"
OUT_PATH = ROOT / "simulator" / "generated_catalog.py"
TICKS_PER_SECOND = 60  # phải khớp simulator/buildings.py TICKS_PER_SECOND

DRILL_CLASSES = {"Drill", "BurstDrill"}
# BeamDrill.java: bắn tia dò ore từ mỗi cạnh (range ô), không phải diện tích
# chân đế như Drill -- công thức khác hẳn nên tách riêng, xem sim.py
# _beam_drill_output_rate. Không có hardnessDrillMultiplier (chỉ có `tier`
# làm ngưỡng cứng), nên KHÔNG gộp vào DRILL_CLASSES.
BEAM_DRILL_CLASSES = {"BeamDrill"}
# WallCrafter.java (vd cliff-crusher/large-cliff-crusher): đọc `attribute`
# (weight số thực, đơn giản hoá nhị phân ở đây) từ đá/tường tự nhiên kề
# cạnh đang xoay mặt tới, ra 1 item cố định (`output`) -- khác Drill/
# BeamDrill (không dựa vào Item.hardness/ore_tiles), xem sim.py
# _wall_crafter_output_rate.
WALL_CRAFTER_CLASSES = {"WallCrafter"}
# SolidPump.java (kế thừa Pump, vd water-extractor): giống Pump nhưng KHÔNG
# cần tile.liquid khớp -- quét diện tích chân đế đếm tile mang đúng
# attribute (Tile.attribute, giống WallCrafter nhưng quét CẢ CHÂN ĐẾ thay
# vì 1 cạnh), ra 1 liquid CỐ ĐỊNH (`result`). Xem sim.py
# _solid_pump_output_rate.
SOLID_PUMP_CLASSES = {"SolidPump"}
BELT_CLASSES = {"Conveyor", "ArmoredConveyor"}
# Duct.java (duct/armored-duct, băng chuyền item riêng Erekir): KHÁC hẳn
# Conveyor.displayedSpeed (đã sẵn đơn vị items/giây) -- field thật là
# `speed` (số tick/lần chuyển), quy đổi ra items/giây bằng CHÍNH công thức
# game hiển thị cho người chơi: `stats.add(Stat.itemsMoved, 60f / speed,
# StatUnit.itemsSecond)` (xem Duct.java thật, dòng 61). Từng bị bỏ sót
# hoàn toàn (không nằm trong BELT_CLASSES lẫn KNOWN_UNMODELED) tới khi user
# hỏi "bot có nhận diện hết Transport chưa" mới phát hiện ra.
DUCT_CLASSES = {"Duct"}
CRAFTER_CLASSES = {"GenericCrafter"}
SORTER_CLASSES = {"Sorter"}
PUMP_CLASSES = {"Pump"}
CONDUIT_CLASSES = {"Conduit", "ArmoredConduit"}
# Router.java thật: round-robin chia đều item cho các hướng còn nhận được
# (xem RouterBuild.getTileTarget) -- simulator/sim.py mô phỏng bằng chia đều
# capacity cho N nhánh hợp lệ, không phải 1-nguồn-nhiều-đích như belt thường.
# LiquidRouter/DuctRouter/StackRouter: cơ chế tương đương (round-robin/dump
# đều ra các hướng hợp lệ) trên hệ liquid hoặc hệ Duct (Erekir) -- xếp chung
# kind="router", sim.py không phân biệt theo belt_kind nên tự động hoạt động
# cho cả 2 mạng (xem NEXT_STEPS.md mục "hệ thống distribution").
ROUTER_CLASSES = {"Router", "LiquidRouter", "DuctRouter", "StackRouter"}
# Junction.java/DuctJunction.java/LiquidJunction.java: giao lộ, mỗi hướng vào
# có buffer riêng, ĐI THẲNG qua theo đúng hướng đang di chuyển (không dùng
# rotation của chính nó), KHÔNG rẽ, KHÔNG trộn -- cho 2 luồng vuông góc cắt
# nhau tại 1 ô mà không lẫn item. sim.py: kind="junction" dùng chung
# _direction_of() với sorter để suy ra hướng đang đi.
JUNCTION_CLASSES = {"Junction", "DuctJunction", "LiquidJunction"}
# OverflowGate.java/OverflowDuct.java: field `invert` phân biệt overflow (ưu
# tiên đi THẲNG, chỉ rẽ khi thẳng không nhận -- tức đầy) và underflow (ngược
# lại, ưu tiên rẽ). Cơ chế thật là ĐỘNG (dựa vào acceptItem lúc runtime, phụ
# thuộc mức đầy hiện tại), simulator này tính throughput ổn định tĩnh nên xấp
# xỉ tất định: overflow luôn ưu tiên thẳng, underflow luôn ưu tiên rẽ (xem
# sim.py _trace_branching kind=="overflow-gate", NEXT_STEPS.md).
OVERFLOW_CLASSES = {"OverflowGate", "OverflowDuct"}
# ItemBridge.java/BufferedItemBridge.java (item) + LiquidBridge.java (kế thừa
# ItemBridge)/DirectionLiquidBridge.java/DuctBridge.java (liquid + Duct): bắc
# cầu 2 building cách nhau tối đa `range` ô, item/liquid "nhảy" qua khoảng
# trống bỏ qua vật cản ở giữa -- khác hẳn belt nối liền vật lý. sim.py dùng
# `link_target` (xem grid.py PlacedBuilding) do planner gán khi đặt, không mô
# phỏng lại cơ chế auto-tìm-link lúc runtime của game thật.
BRIDGE_CLASSES = {"ItemBridge", "BufferedItemBridge", "LiquidBridge", "DirectionLiquidBridge", "DuctBridge"}
# MassDriver.java: bắn cả cụm item tích luỹ (itemCapacity) tới driver khác
# trong tầm `range` (đơn vị pixel, tilesize=8) mỗi khi hồi xong (`reload`
# tick) -- vận chuyển tầm xa theo đợt, không phải luồng liên tục. Xấp xỉ
# thành tốc độ trung bình ổn định = 60*capacity/reload (cùng kiểu xấp xỉ đã
# dùng cho drill/pump, xem _mass_driver_output_rate trong sim.py).
MASS_DRIVER_CLASSES = {"MassDriver"}
# Unloader.java (rút hàng, so khớp phức tạp giữa MỌI hàng xóm không cố định
# hướng)/DirectionalUnloader.java (rút theo hướng cố định `rotation`, back()
# -> front()): cả 2 RÚT item từ 1 building lưu trữ liền kề (thường là
# core/container) rồi đẩy ra, khác hẳn 1 nguồn sản xuất mới. simulator này
# không có mô hình tồn kho (core/container không track số lượng item thật),
# nên xấp xỉ TẤT ĐỊNH theo hướng cố định như DirectionalUnloader cho cả 2
# class (bỏ qua cơ chế ưu tiên động phức tạp của Unloader.java thật) và giả
# định kho liền kề luôn còn hàng -- xem sim.py kind=="unloader", cần
# filter_item (config Item) được đặt rõ, không hỗ trợ "rút bất kỳ" vì không
# biết kho thật có gì.
UNLOADER_CLASSES = {"Unloader", "DirectionalUnloader"}
# StorageBlock.java (container/vault/...): unloader chỉ rút được từ 1 building
# lưu trữ (hoặc core) liền kề -- cần đánh dấu kind="storage" riêng (không phải
# category thật của các block này, vd container/vault dùng Category.effect
# trong source, xem Blocks.java) để sim.py nhận diện đúng lúc kiểm tra hàng
# xóm của unloader.
STORAGE_CLASSES = {"StorageBlock"}
# ConsumeGenerator.java (vd combustion-generator/steam-generator): đốt BẤT KỲ
# item nào đủ flammability (ConsumeItemFlammable.java: filter theo
# item.flammability >= minFlammability, hiệu suất phát điện = flammability
# của item đó) -- khác hẳn factory thường (tiêu thụ 1 item CỐ ĐỊNH, số lượng
# cố định). NuclearReactor.java (thorium-reactor)/ImpactReactor.java
# (impact-reactor) cũng dùng consumeItem(X) CỐ ĐỊNH (không phải
# ConsumeItemFlammable) -- gộp chung nhánh xử lý (đọc thêm tại nhánh elif
# trong extract_blocks, phân biệt fixed_item/liquid_only ngay trong thân xử
# lý thay vì tách class riêng). ThermalGenerator.java (thermal-generator/
# turbine-condenser, dựa Attribute.heat -- CHƯA có "heat" trong Tile/state
# schema, xem NEXT_STEPS.md) và VariableReactor/HeaterGenerator.java
# (flux-reactor/neoplasia-reactor, cơ chế heat-instability/biến thiên phức
# tạp hơn hẳn) vẫn rơi vào GENERATED_OTHER, không đoán bừa.
GENERATOR_CLASSES = {"ConsumeGenerator", "NuclearReactor", "ImpactReactor"}
# SolarGenerator.java (solar-panel/solar-panel-large): ra điện THỤ ĐỘNG,
# không consume gì -- tách riêng khỏi GENERATOR_CLASSES vì không có bất kỳ
# consumeItem/consumeLiquid nào để dò (nhánh xử lý hoàn toàn khác).
SOLAR_GENERATOR_CLASSES = {"SolarGenerator"}
# PowerNode.java: không sản xuất/tiêu thụ điện, chỉ TRUYỀN không dây trong
# bán kính laserRange (số ô, hình tròn) -- xem sim.py phần dựng mạng điện.
# LongPowerNode.java kế thừa THẲNG PowerNode (chỉ khác cosmetic, field
# laserRange dùng y hệt) -- gộp chung, xem beam-link.
POWER_NODE_CLASSES = {"PowerNode", "LongPowerNode"}
# BeamNode.java (beam-node/beam-tower): khác PowerNode -- chỉ nối THẲNG
# HÀNG theo 4 hướng Đông/Tây/Nam/Bắc trong tầm `range`, không toả tròn --
# xem sim.py _power_linked nhánh beam-node.
BEAM_NODE_CLASSES = {"BeamNode"}
# Battery.java (battery/battery-large): lưu trữ điện, không sản xuất/tiêu
# thụ ròng liên tục -- xem buildings.py battery_capacity.
BATTERY_CLASSES = {"Battery"}
HANDLED_CLASSES = (
    DRILL_CLASSES | BEAM_DRILL_CLASSES | WALL_CRAFTER_CLASSES | SOLID_PUMP_CLASSES | BELT_CLASSES | DUCT_CLASSES | CRAFTER_CLASSES | SORTER_CLASSES
    | PUMP_CLASSES | CONDUIT_CLASSES | ROUTER_CLASSES | JUNCTION_CLASSES
    | OVERFLOW_CLASSES | BRIDGE_CLASSES | MASS_DRIVER_CLASSES | UNLOADER_CLASSES
    | STORAGE_CLASSES | GENERATOR_CLASSES | SOLAR_GENERATOR_CLASSES | POWER_NODE_CLASSES
    | BEAM_NODE_CLASSES | BATTERY_CLASSES
)

# Class biết tồn tại, cố ý không model -- lý do cụ thể ghi trong SKIPPED khi gặp
KNOWN_UNMODELED = {
    "StackConveyor": "cơ chế xếp chồng nhiều item/ô, khác hẳn Conveyor thường",
}

_CTOR_RE = re.compile(r'(\w+)\s*=\s*new\s+(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)\s*\{\{')


def extract_blocks(java_text: str, class_names=None) -> list:
    """Tìm mọi `var = new ClassName(...args...){{`, trong đó ...args... luôn
    có 1 chuỗi tên block. brace-match thân tới `}}` khớp. class_names=None
    nghĩa là lấy MỌI class (dùng cho lượt quét "còn lại"). Trả về
    [(varname, classname, blockname, body_text), ...]."""
    results = []
    for m in _CTOR_RE.finditer(java_text):
        varname, classname, args = m.group(1), m.group(2), m.group(3)
        if class_names is not None and classname not in class_names:
            continue
        name_match = re.search(r'"([\w-]+)"', args)
        if not name_match:
            continue
        blockname = name_match.group(1)
        i = m.end()
        depth = 2  # đã ăn "{{" ở cuối match
        start = i
        while i < len(java_text) and depth > 0:
            if java_text[i] == "{":
                depth += 1
            elif java_text[i] == "}":
                depth -= 1
            i += 1
        results.append((varname, classname, blockname, java_text[start : i - 2]))
    return results


def parse_named_values(java_text: str, class_names: set) -> dict:
    """field-name Java (vd Items.xxx/Liquids.xxx) -> (content-name-string, hardness, flammability)."""
    result = {}
    for varname, _, blockname, body in extract_blocks(java_text, class_names):
        m = re.search(r"\bhardness\s*=\s*(\d+)", body)
        hardness = int(m.group(1)) if m else 0
        m = re.search(rf"\bflammability\s*=\s*({_EXPR})", body)
        flammability = _eval_expr(m.group(1)) if m else 0.0
        result[varname] = (blockname, hardness, flammability)
    return result


# Nhiều field/tham số trong source là biểu thức nhân/chia (vd `pumpAmount =
# 7f / 60f`, `craftTime = 60f * 2f / 4f`, `consumeLiquid(Liquids.slag, 40f /
# 60f)`), không phải số literal đơn -- phải tính ra giá trị thật, không chỉ
# lấy số đầu tiên trước dấu `/` (bug thật đã gặp: pumpAmount ra 7.0 thay vì
# 7/60=0.1167, sai 60 lần).
_EXPR = r"[\d.]+f?(?:\s*[*/]\s*[\d.]+f?)*"


def _eval_expr(expr: str) -> float:
    expr = expr.replace("f", "").replace(" ", "")
    tokens = re.split(r"([*/])", expr)
    value = float(tokens[0])
    i = 1
    while i < len(tokens):
        op, num = tokens[i], float(tokens[i + 1])
        value = value * num if op == "*" else value / num
        i += 2
    return value


def field_float(body, name, default=None):
    m = re.search(rf"\b{name}\s*=\s*({_EXPR})", body)
    return _eval_expr(m.group(1)) if m else default


def field_int(body, name, default=None):
    m = re.search(rf"\b{name}\s*=\s*(\d+)", body)
    return int(m.group(1)) if m else default


def field_bool(body, name, default=False):
    m = re.search(rf"\b{name}\s*=\s*(true|false)", body)
    return m.group(1) == "true" if m else default


def parse_power_input(body):
    """consumePower(X) là lệnh gọi (không phải field = expr) nên cần regex
    riêng khác field_float. X là công suất/TICK ở hiệu suất 100% -- quy đổi
    ra công suất/giây bằng *60 (giống mọi rate/tick khác trong codebase này)."""
    m = re.search(rf"consumePower\(({_EXPR})\)", body)
    return _eval_expr(m.group(1)) * TICKS_PER_SECOND if m else 0.0


def field_category(body):
    m = re.search(r"requirements\(Category\.(\w+)", body)
    return m.group(1) if m else None


def parse_consume(body, item_field_to_name):
    """Trả về dict {content_item_name: amount}, hoặc None nếu không parse
    được (block dùng cơ chế input khác, vd chỉ tiêu thụ liquid/power)."""
    m = re.search(r"consumeItems\(with\(([^)]*)\)\)", body)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        result = {}
        for i in range(0, len(parts) - 1, 2):
            item_ref = parts[i].removeprefix("Items.")
            amount = parts[i + 1]
            if item_ref not in item_field_to_name or not amount.replace(".", "").isdigit():
                return None
            result[item_field_to_name[item_ref][0]] = float(amount)
        return result if result else None

    m = re.search(r"consumeItem\(Items\.(\w+),\s*([\d.]+)\)", body)
    if m:
        item_ref, amount = m.group(1), m.group(2)
        if item_ref not in item_field_to_name:
            return None
        return {item_field_to_name[item_ref][0]: float(amount)}

    return None


def parse_consume_liquid(body, liquid_field_to_name, craft_time_ticks):
    """consumeLiquid()/consumeLiquids() là tốc độ LIÊN TỤC (amount/tick),
    khác consumeItem (amount/1 chu kỳ craft). Quy đổi sang "amount/chu kỳ"
    bằng amount_per_tick * craft_time_ticks để dùng chung công thức min()
    với item input trong sim.py -- tương đương nhau ở trạng thái ổn định
    (đây là thứ simulator tính), không phải xấp xỉ.

    Nhận CẢ 2 dạng thật: consumeLiquid(Liquids.X, rate) (1 liquid, vd
    steam-generator/thorium-reactor/differential-generator) VÀ
    consumeLiquids(LiquidStack.with(Liquids.X, r1, Liquids.Y, r2)) (nhiều
    liquid CÙNG LÚC, vd chemical-combustion-chamber/pyrolysis-generator) --
    trước đây chỉ nhận dạng đầu, bỏ sót hẳn dạng nhiều liquid."""
    result = {}
    m = re.search(rf"consumeLiquid\(Liquids\.(\w+),\s*({_EXPR})\)", body)
    if m:
        liquid_ref, amount_per_tick = m.group(1), _eval_expr(m.group(2))
        if liquid_ref in liquid_field_to_name:
            result[liquid_field_to_name[liquid_ref][0]] = amount_per_tick * craft_time_ticks

    m = re.search(r"consumeLiquids\(LiquidStack\.with\(([^)]*)\)\)", body)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        for i in range(0, len(parts) - 1, 2):
            liquid_ref = parts[i].removeprefix("Liquids.")
            amount = parts[i + 1]
            if liquid_ref in liquid_field_to_name:
                result[liquid_field_to_name[liquid_ref][0]] = _eval_expr(amount) * craft_time_ticks

    return result


def parse_output(body, item_field_to_name):
    m = re.search(r"outputItem\s*=\s*new ItemStack\(Items\.(\w+),\s*(\d+)\)", body)
    if not m:
        return None
    item_ref, amount = m.group(1), int(m.group(2))
    if item_ref not in item_field_to_name:
        return None
    return item_field_to_name[item_ref][0], amount


def parse_solid_pump_fields(body, liquid_field_to_name):
    """SolidPump.java: `attribute = Attribute.X;` (như WallCrafter) và
    `result = Liquids.X;` (liquid cố định sinh ra, cần tra
    liquid_field_to_name khác parse_wall_crafter_fields dùng item)."""
    m_attr = re.search(r"\battribute\s*=\s*Attribute\.(\w+)", body)
    m_result = re.search(r"\bresult\s*=\s*Liquids\.(\w+)", body)
    if not m_attr or not m_result:
        return None
    liquid_ref = m_result.group(1)
    if liquid_ref not in liquid_field_to_name:
        return None
    return m_attr.group(1), liquid_field_to_name[liquid_ref][0]


def parse_drill_boost(body, liquid_field_to_name):
    """Drill.java: consumeLiquid(Liquids.X, Y).boost() -- booster KHÔNG BẮT
    BUỘC (khác consumeLiquid thường dùng cho recipe.liquid_inputs bắt buộc
    của factory, không có .boost() theo sau). Y là /tick (giống quy ước
    consumePower/pump_amount thô) -- KHÔNG nhân 60 ở đây, sim.py tự nhân khi
    cần lưu lượng/giây. Trả về (None, 0.0) nếu block này không có booster
    (vd BurstDrill -- impact-drill/eruption-drill không hề gọi consumeLiquid)."""
    m = re.search(rf"consumeLiquid\(Liquids\.(\w+),\s*({_EXPR})\)\.boost\(\)", body)
    if not m:
        return None, 0.0
    liquid_ref = m.group(1)
    if liquid_ref not in liquid_field_to_name:
        return None, 0.0
    return liquid_field_to_name[liquid_ref][0], _eval_expr(m.group(2))


def parse_wall_crafter_fields(body, item_field_to_name):
    """WallCrafter.java: `attribute = Attribute.X;` (tên attribute -- enum
    RIÊNG của game, không phải Item, nhưng ở 2 block thật hiện có
    (cliff-crusher/large-cliff-crusher) trùng tên với item sand nên giữ
    nguyên chuỗi) và `output = Items.X;` (item thật, cần tra
    item_field_to_name như parse_output)."""
    m_attr = re.search(r"\battribute\s*=\s*Attribute\.(\w+)", body)
    m_out = re.search(r"\boutput\s*=\s*Items\.(\w+)", body)
    if not m_attr or not m_out:
        return None
    item_ref = m_out.group(1)
    if item_ref not in item_field_to_name:
        return None
    return m_attr.group(1), item_field_to_name[item_ref][0]


def main():
    items_java = (REFERENCE / "Items.java").read_text(encoding="utf-8")
    liquids_java = (REFERENCE / "Liquids.java").read_text(encoding="utf-8")
    blocks_java = (REFERENCE / "Blocks.java").read_text(encoding="utf-8")

    item_field_to_name = parse_named_values(items_java, {"Item"})
    liquid_field_to_name = parse_named_values(liquids_java, {"Liquid", "CellLiquid"})
    print(f"items: {len(item_field_to_name)}, liquids: {len(liquid_field_to_name)}")

    handled_blocks = extract_blocks(blocks_java, HANDLED_CLASSES)
    print(f"blocks (đã hiểu cơ chế): {len(handled_blocks)} thuộc {sorted(HANDLED_CLASSES)}")

    drills, belts, factories, sorters, pumps, conduits, routers, skipped = [], [], [], [], [], [], [], []
    junctions, overflow_gates, bridges, mass_drivers, unloaders, storages = [], [], [], [], [], []
    generators, power_nodes, beam_drills, wall_crafters, solid_pumps = [], [], [], [], []
    batteries = []
    handled_names = set()

    for varname, classname, blockname, body in handled_blocks:
        size = field_int(body, "size", default=1)

        if classname in DRILL_CLASSES:
            tier = field_int(body, "tier")
            drill_time = field_float(body, "drillTime", default=300.0)
            # BurstDrill.java tự đặt hardnessDrillMultiplier = 0f ở CẤP CLASS
            # (đã xác nhận bằng cách tải source thật) -- impact-drill/
            # eruption-drill không set lại field này trong thân {{ }} riêng
            # (đã grep Blocks.java xác nhận), nên default phải là 0.0 cho
            # BurstDrill, KHÁC với Drill thường (default thật là 50.0). Nếu
            # dùng chung 1 default cho cả 2 class, impact-drill/eruption-drill
            # sẽ bị tính sai công thức (hardness của item ảnh hưởng tới tốc
            # độ đào trong khi thật ra không hề ảnh hưởng).
            hardness_default = 0.0 if classname == "BurstDrill" else 50.0
            hardness_mult = field_float(body, "hardnessDrillMultiplier", default=hardness_default)
            if tier is None:
                skipped.append((blockname, classname, "thiếu tier"))
                continue
            power_input = parse_power_input(body)
            # Drill.java liquidBoostIntensity mặc định 1.6f (mechanical/
            # pneumatic/laser dùng nguyên default, không ghi đè trong thân
            # {{ }} riêng) -- blast-drill ghi đè thành 1.8f (đã grep xác nhận
            # thật). BurstDrill (impact/eruption-drill) không hề gọi
            # consumeLiquid() nên parse_drill_boost trả (None, 0.0) đúng.
            boost_liquid, boost_amount = parse_drill_boost(body, liquid_field_to_name)
            boost_intensity = field_float(body, "liquidBoostIntensity", default=1.6)
            drills.append({
                "name": blockname, "size": size, "tier": tier, "drill_time": drill_time,
                "hardness_multiplier": hardness_mult, "power_input": power_input,
                "boost_liquid": boost_liquid, "boost_amount": boost_amount,
                "boost_intensity": boost_intensity,
            })
            handled_names.add(blockname)

        elif classname in BEAM_DRILL_CLASSES:
            tier = field_int(body, "tier")
            drill_time = field_float(body, "drillTime", default=200.0)  # default thật BeamDrill.java
            beam_range = field_int(body, "range", default=5)  # default thật BeamDrill.java
            if tier is None:
                skipped.append((blockname, classname, "thiếu tier"))
                continue
            power_input = parse_power_input(body)
            beam_drills.append({
                "name": blockname, "size": size, "tier": tier, "drill_time": drill_time,
                "beam_range": beam_range, "power_input": power_input,
            })
            handled_names.add(blockname)

        elif classname in WALL_CRAFTER_CLASSES:
            drill_time = field_float(body, "drillTime", default=150.0)  # default thật WallCrafter.java
            wall_fields = parse_wall_crafter_fields(body, item_field_to_name)
            if wall_fields is None:
                skipped.append((blockname, classname, "thiếu attribute/output"))
                continue
            attribute, output_item = wall_fields
            power_input = parse_power_input(body)
            wall_crafters.append({
                "name": blockname, "size": size, "drill_time": drill_time,
                "attribute": attribute, "output_item": output_item, "power_input": power_input,
            })
            handled_names.add(blockname)

        elif classname in SOLID_PUMP_CLASSES:
            pump_amount = field_float(body, "pumpAmount", default=0.1)  # default thật Pump.java (cha)
            solid_fields = parse_solid_pump_fields(body, liquid_field_to_name)
            if solid_fields is None:
                skipped.append((blockname, classname, "thiếu attribute/result"))
                continue
            attribute, liquid = solid_fields
            power_input = parse_power_input(body)
            solid_pumps.append({
                "name": blockname, "size": size, "pump_amount": pump_amount,
                "attribute": attribute, "liquid": liquid, "power_input": power_input,
            })
            handled_names.add(blockname)

        elif classname in BELT_CLASSES:
            speed = field_float(body, "displayedSpeed")
            if speed is None:
                skipped.append((blockname, classname, "thiếu displayedSpeed"))
                continue
            belts.append({"name": blockname, "size": size, "base_rate": speed})
            handled_names.add(blockname)

        elif classname in DUCT_CLASSES:
            # Duct.java KHÔNG có displayedSpeed -- field thật là `speed` (số
            # tick/lần chuyển, default class 5f), quy đổi ra items/giây bằng
            # ĐÚNG công thức game hiển thị cho người chơi (Duct.java thật,
            # Stat.itemsMoved): rate = 60/speed. Gộp chung list `belts`
            # (kind="belt") vì cơ chế belt-tracing trong sim.py không phân
            # biệt nguồn gốc class, chỉ cần đúng base_rate.
            raw_speed = field_float(body, "speed", default=5.0)
            if raw_speed is None or raw_speed <= 0:
                skipped.append((blockname, classname, "thiếu/sai field speed"))
                continue
            belts.append({"name": blockname, "size": size, "base_rate": TICKS_PER_SECOND / raw_speed})
            handled_names.add(blockname)

        elif classname in CRAFTER_CLASSES:
            craft_time_ticks = field_float(body, "craftTime", default=80.0)
            output = parse_output(body, item_field_to_name)
            inputs = parse_consume(body, item_field_to_name)
            if output is None:
                skipped.append((blockname, classname, "thiếu/không parse được outputItem"))
                continue
            if inputs is None:
                skipped.append((blockname, classname, "thiếu/không parse được input item (có thể chỉ dùng liquid/power)"))
                continue
            liquid_inputs = parse_consume_liquid(body, liquid_field_to_name, craft_time_ticks)
            power_input = parse_power_input(body)
            factories.append({
                "name": blockname, "size": size,
                "craft_time_ticks": craft_time_ticks,
                "inputs": inputs, "liquid_inputs": liquid_inputs,
                "output_item": output[0], "output_amount": output[1],
                "power_input": power_input,
            })
            handled_names.add(blockname)

        elif classname in SORTER_CLASSES:
            invert = field_bool(body, "invert")
            sorters.append({"name": blockname, "size": size, "invert": invert})
            handled_names.add(blockname)

        elif classname in PUMP_CLASSES:
            if "consumeLiquid" in body:
                skipped.append((blockname, classname, "pump tự tiêu thụ liquid (vd reinforced-pump) -- chưa model"))
                continue
            pump_amount = field_float(body, "pumpAmount")
            if pump_amount is None:
                skipped.append((blockname, classname, "thiếu pumpAmount"))
                continue
            power_input = parse_power_input(body)
            pumps.append({"name": blockname, "size": size, "pump_amount": pump_amount, "power_input": power_input})
            handled_names.add(blockname)

        elif classname in CONDUIT_CLASSES:
            conduits.append({"name": blockname, "size": size})
            handled_names.add(blockname)

        elif classname in ROUTER_CLASSES:
            routers.append({"name": blockname, "size": size})
            handled_names.add(blockname)

        elif classname in JUNCTION_CLASSES:
            junctions.append({"name": blockname, "size": size})
            handled_names.add(blockname)

        elif classname in OVERFLOW_CLASSES:
            invert = field_bool(body, "invert")
            overflow_gates.append({"name": blockname, "size": size, "invert": invert})
            handled_names.add(blockname)

        elif classname in BRIDGE_CLASSES:
            link_range = field_int(body, "range", default=4)
            bridges.append({"name": blockname, "size": size, "link_range": link_range})
            handled_names.add(blockname)

        elif classname in MASS_DRIVER_CLASSES:
            capacity = field_float(body, "itemCapacity", default=120.0)
            reload = field_float(body, "reload", default=200.0)
            range_px = field_float(body, "range", default=440.0)
            mass_drivers.append({
                "name": blockname, "size": size, "driver_capacity": capacity,
                "driver_reload": reload, "link_range": range_px / 8.0,
            })
            handled_names.add(blockname)

        elif classname in UNLOADER_CLASSES:
            speed = field_float(body, "speed", default=1.0)
            unloaders.append({"name": blockname, "size": size, "base_rate": TICKS_PER_SECOND / speed})
            handled_names.add(blockname)

        elif classname in STORAGE_CLASSES:
            storages.append({"name": blockname, "size": size})
            handled_names.add(blockname)

        elif classname in SOLAR_GENERATOR_CLASSES:
            # SolarGenerator.java (solar-panel/solar-panel-large): ra điện
            # THỤ ĐỘNG, không consume gì cả -- xem sim.py _generator_power_rate
            # nhánh generator_passive (xấp xỉ LUÔN đủ nắng, không mô phỏng
            # ngày/đêm, xem NEXT_STEPS.md).
            power_production = field_float(body, "powerProduction", default=0.0)
            generators.append({
                "name": blockname, "size": size, "power_production": power_production,
                "item_duration": 0.0, "min_flammability": 0.0, "liquid_inputs": {},
                "passive": True, "fixed_item": None, "fixed_item_amount": 1.0,
                "liquid_only": False, "power_input": 0.0,
            })
            handled_names.add(blockname)

        elif classname in GENERATOR_CLASSES:
            power_production = field_float(body, "powerProduction", default=0.0)
            item_duration = field_float(body, "itemDuration", default=120.0)
            # ImpactReactor.java: consumePower(25f) -- VỪA sản xuất VỪA tiêu
            # thụ điện (net dương, powerProduction > power_input thật) --
            # sim.py's _power_capable/_power_satisfaction đã tổng quát sẵn
            # cho trường hợp 1 building vừa "generator" vừa power_input>0,
            # không cần đổi gì thêm ở đó.
            power_input = parse_power_input(body)

            if "ConsumeItemFlammable" in body:
                # Cơ chế CŨ (combustion-generator/steam-generator): đốt BẤT
                # KỲ item đủ flammability -- không đổi hành vi.
                m = re.search(rf"new ConsumeItemFlammable\(({_EXPR})\)", body)
                min_flammability = _eval_expr(m.group(1)) if m else 0.2  # 0.2 = default ctor
                liquid_inputs = parse_consume_liquid(body, liquid_field_to_name, item_duration)
                generators.append({
                    "name": blockname, "size": size, "power_production": power_production,
                    "item_duration": item_duration, "min_flammability": min_flammability,
                    "liquid_inputs": liquid_inputs, "passive": False, "fixed_item": None,
                    "fixed_item_amount": 1.0, "liquid_only": False, "power_input": power_input,
                })
                handled_names.add(blockname)
                continue

            # consumeItem(Items.X) KHÔNG có amount đi kèm (ngầm định 1) --
            # khác parse_consume() (đòi hỏi consumeItems(with(...)) hoặc
            # consumeItem(Items.X, amount) CÓ amount rõ) -- vd
            # differential-generator (pyratite), thorium-reactor (thorium),
            # impact-reactor (blast-compound). Coi đây là item CỐ ĐỊNH DUY
            # NHẤT, khác hẳn "bất kỳ item đủ flammability" ở trên -- xem
            # sim.py _generator_power_rate nhánh generator_item.
            m_item = re.search(r"consumeItem\(Items\.(\w+)\)(?!\s*,)", body)
            fixed_item = None
            if m_item and m_item.group(1) in item_field_to_name:
                fixed_item = item_field_to_name[m_item.group(1)][0]

            if fixed_item is not None:
                liquid_inputs = parse_consume_liquid(body, liquid_field_to_name, item_duration)
                generators.append({
                    "name": blockname, "size": size, "power_production": power_production,
                    "item_duration": item_duration, "min_flammability": 0.0,
                    "liquid_inputs": liquid_inputs, "passive": False, "fixed_item": fixed_item,
                    "fixed_item_amount": 1.0, "liquid_only": False, "power_input": power_input,
                })
                handled_names.add(blockname)
                continue

            # Không item nào cả, CHỈ consumeLiquid(s) -- vd
            # chemical-combustion-chamber/pyrolysis-generator. Không có "chu
            # kỳ" item để quy đổi theo -- generator_liquid_inputs lưu trực
            # tiếp đơn vị "cần/giây" (truyền TICKS_PER_SECOND thay vì
            # item_duration làm hệ số quy đổi, xem sim.py
            # _generator_power_rate nhánh generator_liquid_only).
            liquid_inputs = parse_consume_liquid(body, liquid_field_to_name, TICKS_PER_SECOND)
            if liquid_inputs:
                generators.append({
                    "name": blockname, "size": size, "power_production": power_production,
                    "item_duration": 0.0, "min_flammability": 0.0,
                    "liquid_inputs": liquid_inputs, "passive": False, "fixed_item": None,
                    "fixed_item_amount": 1.0, "liquid_only": True, "power_input": power_input,
                })
                handled_names.add(blockname)
                continue

            skipped.append((blockname, classname, "không dùng ConsumeItemFlammable, không tìm được consumeItem/consumeLiquid nhận diện được -- cơ chế khác, chưa model"))

        elif classname in POWER_NODE_CLASSES:
            laser_range = field_float(body, "laserRange", default=6.0)
            power_nodes.append({"name": blockname, "size": size, "power_range": laser_range, "kind": "power-node"})
            handled_names.add(blockname)

        elif classname in BEAM_NODE_CLASSES:
            # BeamNode.java (beam-node/beam-tower): nối THẲNG HÀNG (4 hướng
            # Đông/Tây/Nam/Bắc), KHÁC power-node (toả tròn laserRange) -- xem
            # sim.py _power_linked nhánh beam-node. Lưu vào field power_range
            # (dùng chung tên với power-node cho gọn, chỉ khác Ý NGHĨA hình
            # học tuỳ kind).
            beam_range = field_int(body, "range", default=5)  # default thật BeamNode.java
            power_nodes.append({"name": blockname, "size": size, "power_range": float(beam_range), "kind": "beam-node"})
            handled_names.add(blockname)

        elif classname in BATTERY_CLASSES:
            # Battery.java: LƯU TRỮ điện, không sản xuất/tiêu thụ ròng liên
            # tục -- simulator này tính thông lượng TRUNG BÌNH ổn định,
            # battery không đổi kết quả đó (xem buildings.py battery_capacity
            # + sim.py _build_power_networks docstring). Chỉ cần nhận diện
            # để tham gia mạng điện (kind="battery", _power_capable), không
            # có rate nào để tính.
            capacity = _eval_expr(re.search(rf"consumePowerBuffered\(({_EXPR})\)", body).group(1)) if re.search(rf"consumePowerBuffered\(({_EXPR})\)", body) else 0.0
            batteries.append({"name": blockname, "size": size, "battery_capacity": capacity})
            handled_names.add(blockname)

    print(f"  -> drill: {len(drills)}, beam-drill: {len(beam_drills)}, wall-crafter: {len(wall_crafters)}, "
          f"solid-pump: {len(solid_pumps)}, "
          f"belt: {len(belts)}, "
          f"factory: {len(factories)}, "
          f"sorter: {len(sorters)}, pump: {len(pumps)}, conduit: {len(conduits)}, "
          f"router: {len(routers)}, junction: {len(junctions)}, overflow-gate: "
          f"{len(overflow_gates)}, bridge: {len(bridges)}, mass-driver: {len(mass_drivers)}, "
          f"unloader: {len(unloaders)}, generator: {len(generators)}, power-node: {len(power_nodes)}, "
          f"battery: {len(batteries)}, "
          f"bỏ qua: {len(skipped)}")

    # Lượt 2: MỌI block còn lại (bất kể class), chỉ lấy tên+category+size,
    # không có recipe/rate. Bỏ qua block không có requirements(Category...)
    # (không phải building thật sự đặt được, vd block hệ thống/floor).
    all_blocks = extract_blocks(blocks_java, class_names=None)
    other = {}
    for varname, classname, blockname, body in all_blocks:
        if blockname in handled_names or blockname in other:
            continue
        category = field_category(body)
        if category is None:
            continue
        if classname in KNOWN_UNMODELED:
            skipped.append((blockname, classname, KNOWN_UNMODELED[classname]))
        size = field_int(body, "size", default=1)
        other[blockname] = {"name": blockname, "size": size, "category": category}

    print(f"  -> other (chỉ lưu tên, chưa có logic đặt): {len(other)}")

    write_output(
        item_field_to_name, liquid_field_to_name, drills, belts, factories, sorters, pumps,
        conduits, routers, junctions, overflow_gates, bridges, mass_drivers, unloaders, storages,
        generators, power_nodes, beam_drills, wall_crafters, solid_pumps, batteries, other, skipped,
    )
    print(f"đã ghi {OUT_PATH}")


def write_output(
    item_field_to_name, liquid_field_to_name, drills, belts, factories, sorters, pumps,
    conduits, routers, junctions, overflow_gates, bridges, mass_drivers, unloaders, storages,
    generators, power_nodes, beam_drills, wall_crafters, solid_pumps, batteries, other, skipped,
):
    lines = [
        '"""TỰ ĐỘNG SINH bởi tools/generate_catalog.py -- đừng sửa tay, chạy lại script.',
        "",
        "Nguồn: Anuken/Mindustry (master, reference/*.java).",
        f"Bỏ qua {len(skipped)} block không parse được (xem SKIPPED cuối file) -- không",
        "phải bug, do cơ chế không khớp pattern hỗ trợ hoặc cố ý chưa model.",
        f"{len(other)} block khác chỉ lưu tên+category (GENERATED_OTHER) -- chưa có",
        "recipe/rate, planner từ chối đặt thay vì đoán. Xem NEXT_STEPS.md.",
        '"""',
        "",
        "from .buildings import BuildingType, Item, Liquid, Recipe",
        "",
        "GENERATED_ITEMS = {",
    ]
    for name, (hardness, flammability) in sorted({v[0]: (v[1], v[2]) for v in item_field_to_name.values()}.items()):
        lines.append(f'    "{name}": Item("{name}", hardness={hardness}, flammability={flammability}),')
    lines.append("}")
    lines.append("")
    lines.append("GENERATED_LIQUIDS = {")
    for name, _ in sorted({v[0]: v[1] for v in liquid_field_to_name.values()}.items()):
        lines.append(f'    "{name}": Liquid("{name}"),')
    lines.append("}")
    lines.append("")
    lines.append("GENERATED_BUILDINGS = {")

    for d in sorted(drills, key=lambda b: b["name"]):
        boost_part = ""
        if d["boost_liquid"] is not None:
            boost_part = (
                f', boost_liquid="{d["boost_liquid"]}", boost_amount={d["boost_amount"]}, '
                f'boost_intensity={d["boost_intensity"]}'
            )
        lines.append(
            f'    "{d["name"]}": BuildingType("{d["name"]}", size={d["size"]}, kind="drill", '
            f'drill_time={d["drill_time"]}, hardness_multiplier={d["hardness_multiplier"]}, tier={d["tier"]}, '
            f'power_input={d["power_input"]}{boost_part}),'
        )
    for bd in sorted(beam_drills, key=lambda b: b["name"]):
        lines.append(
            f'    "{bd["name"]}": BuildingType("{bd["name"]}", size={bd["size"]}, kind="beam-drill", '
            f'drill_time={bd["drill_time"]}, tier={bd["tier"]}, beam_range={bd["beam_range"]}, '
            f'power_input={bd["power_input"]}),'
        )
    for wc in sorted(wall_crafters, key=lambda b: b["name"]):
        lines.append(
            f'    "{wc["name"]}": BuildingType("{wc["name"]}", size={wc["size"]}, kind="wall-crafter", '
            f'drill_time={wc["drill_time"]}, wall_attribute="{wc["attribute"]}", '
            f'wall_output="{wc["output_item"]}", power_input={wc["power_input"]}),'
        )
    for sp in sorted(solid_pumps, key=lambda b: b["name"]):
        lines.append(
            f'    "{sp["name"]}": BuildingType("{sp["name"]}", size={sp["size"]}, kind="solid-pump", '
            f'pump_amount={sp["pump_amount"]}, solid_pump_attribute="{sp["attribute"]}", '
            f'solid_pump_liquid="{sp["liquid"]}", power_input={sp["power_input"]}),'
        )
    for b in sorted(belts, key=lambda b: b["name"]):
        lines.append(f'    "{b["name"]}": BuildingType("{b["name"]}", size={b["size"]}, kind="belt", base_rate={b["base_rate"]}),')
    for f in sorted(factories, key=lambda b: b["name"]):
        inputs_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in f["inputs"].items()) + "}"
        liquid_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in f["liquid_inputs"].items()) + "}"
        craft_time_s = f["craft_time_ticks"] / 60.0
        lines.append(
            f'    "{f["name"]}": BuildingType("{f["name"]}", size={f["size"]}, kind="factory", recipe=Recipe('
            f'craft_time={craft_time_s!r}, inputs={inputs_repr}, liquid_inputs={liquid_repr}, '
            f'output_item="{f["output_item"]}", output_amount={f["output_amount"]}), '
            f'power_input={f["power_input"]}),'
        )
    for s in sorted(sorters, key=lambda b: b["name"]):
        lines.append(
            f'    "{s["name"]}": BuildingType("{s["name"]}", size={s["size"]}, kind="sorter", '
            f'config_type="item", invert={s["invert"]}),'
        )
    for p in sorted(pumps, key=lambda b: b["name"]):
        lines.append(
            f'    "{p["name"]}": BuildingType("{p["name"]}", size={p["size"]}, kind="pump", '
            f'pump_amount={p["pump_amount"]}, power_input={p["power_input"]}),'
        )
    for c in sorted(conduits, key=lambda b: b["name"]):
        # v1: conduit coi như không giới hạn thông lượng (nghẽn thật luôn ở
        # pump/nhà máy, không phải ống) -- dòng liquid thật của Mindustry
        # dựa trên áp suất, không phải tốc độ cố định như belt item, chưa
        # model chính xác được. Ghi rõ đây là đơn giản hoá, không phải số thật.
        lines.append(f'    "{c["name"]}": BuildingType("{c["name"]}", size={c["size"]}, kind="liquid-belt", base_rate=float("inf")),')
    for r in sorted(routers, key=lambda b: b["name"]):
        lines.append(f'    "{r["name"]}": BuildingType("{r["name"]}", size={r["size"]}, kind="router"),')
    for j in sorted(junctions, key=lambda b: b["name"]):
        lines.append(f'    "{j["name"]}": BuildingType("{j["name"]}", size={j["size"]}, kind="junction"),')
    for g in sorted(overflow_gates, key=lambda b: b["name"]):
        lines.append(
            f'    "{g["name"]}": BuildingType("{g["name"]}", size={g["size"]}, kind="overflow-gate", '
            f'invert={g["invert"]}),'
        )
    for br in sorted(bridges, key=lambda b: b["name"]):
        lines.append(
            f'    "{br["name"]}": BuildingType("{br["name"]}", size={br["size"]}, kind="bridge", '
            f'link_range={br["link_range"]}),'
        )
    for md in sorted(mass_drivers, key=lambda b: b["name"]):
        lines.append(
            f'    "{md["name"]}": BuildingType("{md["name"]}", size={md["size"]}, kind="mass-driver", '
            f'driver_capacity={md["driver_capacity"]}, driver_reload={md["driver_reload"]}, '
            f'link_range={md["link_range"]}),'
        )
    for u in sorted(unloaders, key=lambda b: b["name"]):
        lines.append(
            f'    "{u["name"]}": BuildingType("{u["name"]}", size={u["size"]}, kind="unloader", '
            f'base_rate={u["base_rate"]}, config_type="item"),'
        )
    for st in sorted(storages, key=lambda b: b["name"]):
        lines.append(f'    "{st["name"]}": BuildingType("{st["name"]}", size={st["size"]}, kind="storage"),')
    for g in sorted(generators, key=lambda b: b["name"]):
        liquid_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in g["liquid_inputs"].items()) + "}"
        fixed_item_repr = f'"{g["fixed_item"]}"' if g["fixed_item"] is not None else "None"
        lines.append(
            f'    "{g["name"]}": BuildingType("{g["name"]}", size={g["size"]}, kind="generator", '
            f'power_production={g["power_production"]}, item_duration={g["item_duration"]}, '
            f'min_flammability={g["min_flammability"]}, generator_liquid_inputs={liquid_repr}, '
            f'generator_item={fixed_item_repr}, generator_item_amount={g["fixed_item_amount"]}, '
            f'generator_passive={g["passive"]}, generator_liquid_only={g["liquid_only"]}, '
            f'power_input={g["power_input"]}),'
        )
    for pn in sorted(power_nodes, key=lambda b: b["name"]):
        lines.append(f'    "{pn["name"]}": BuildingType("{pn["name"]}", size={pn["size"]}, kind="{pn["kind"]}", power_range={pn["power_range"]}),')
    for bt in sorted(batteries, key=lambda b: b["name"]):
        lines.append(f'    "{bt["name"]}": BuildingType("{bt["name"]}", size={bt["size"]}, kind="battery", battery_capacity={bt["battery_capacity"]}),')
    lines.append("}")
    lines.append("")
    lines.append("# Chỉ có tên+category+size, CHƯA có recipe/rate -- planner từ chối đặt")
    lines.append("# loại này thay vì đoán. Xem NEXT_STEPS.md mục \"Phạm vi chưa làm\".")
    lines.append("GENERATED_OTHER = {")
    for o in sorted(other.values(), key=lambda b: b["name"]):
        lines.append(f'    "{o["name"]}": BuildingType("{o["name"]}", size={o["size"]}, kind="{o["category"]}", category="{o["category"]}"),')
    lines.append("}")
    lines.append("")
    lines.append("SKIPPED = [")
    for name, cls, reason in skipped:
        reason_escaped = reason.replace('"', '\\"')
        lines.append(f'    ("{name}", "{cls}", "{reason_escaped}"),')
    lines.append("]")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
