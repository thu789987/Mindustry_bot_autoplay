"""Tự động sinh danh mục building/item đầy đủ từ mã nguồn thật Mindustry
(reference/Blocks.java, reference/Items.java), thay vì gõ tay từng cái.

KHÔNG phải trình dịch Java đầy đủ -- dùng brace-matching để cắt đúng thân
mỗi block definition (`new ClassName("name"){{ ... }};`), rồi regex trên
phần thân đó để lấy field cần. Đủ tin cậy với code style nhất quán của
Mindustry, nhưng không phải giải pháp tổng quát cho Java bất kỳ.

Phủ 4 loại: Drill, Conveyor, GenericCrafter (khớp 3 "kind" mà
simulator/sim.py biết tính throughput: drill, belt, factory), và Sorter
(kind="sorter", configureAny(Item) -- xem BuildingComp.java:configureAny,
Sorter.java:config(Item.class,...)). Các loại khác (turret, power, liquid,
unit factory...) bị bỏ qua có chủ đích -- planner hiện chưa có logic cho
chúng.

Chạy: python tools/generate_catalog.py
Ghi ra: simulator/generated_catalog.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "reference"
OUT_PATH = ROOT / "simulator" / "generated_catalog.py"

SUPPORTED_CLASSES = {"Drill", "Conveyor", "GenericCrafter", "Sorter"}


_CTOR_RE = re.compile(r'(\w+)\s*=\s*new\s+(\w+)\s*\(((?:[^()]|\([^()]*\))*)\)\s*\{\{')


def extract_blocks(java_text: str, class_names: set) -> list:
    """Tìm mọi `var = new ClassName(...args...){{`, trong đó ...args... luôn
    có 1 chuỗi tên block (vd `"copper"` hoặc `"copper", Color.valueOf(...)`),
    brace-match thân tới `}}` khớp. Trả về
    [(varname, classname, blockname, body_text), ...]."""
    results = []
    for m in _CTOR_RE.finditer(java_text):
        varname, classname, args = m.group(1), m.group(2), m.group(3)
        if classname not in class_names:
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


def parse_items(java_text: str) -> dict:
    """field-name Java (Items.xxx) -> (content-name-string, hardness)."""
    items = {}
    for varname, _, blockname, body in extract_blocks(java_text, {"Item"}):
        m = re.search(r"\bhardness\s*=\s*(\d+)", body)
        hardness = int(m.group(1)) if m else 0
        items[varname] = (blockname, hardness)
    return items


def field_float(body, name, default=None):
    m = re.search(rf"\b{name}\s*=\s*([\d.]+)f?", body)
    return float(m.group(1)) if m else default


def field_int(body, name, default=None):
    m = re.search(rf"\b{name}\s*=\s*(\d+)", body)
    return int(m.group(1)) if m else default


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


def parse_output(body, item_field_to_name):
    m = re.search(r"outputItem\s*=\s*new ItemStack\(Items\.(\w+),\s*(\d+)\)", body)
    if not m:
        return None
    item_ref, amount = m.group(1), int(m.group(2))
    if item_ref not in item_field_to_name:
        return None
    return item_field_to_name[item_ref][0], amount


def main():
    items_java = (REFERENCE / "Items.java").read_text(encoding="utf-8")
    blocks_java = (REFERENCE / "Blocks.java").read_text(encoding="utf-8")

    item_field_to_name = parse_items(items_java)
    print(f"items: parse được {len(item_field_to_name)}")

    blocks = extract_blocks(blocks_java, SUPPORTED_CLASSES)
    print(f"blocks: tìm thấy {len(blocks)} block thuộc {sorted(SUPPORTED_CLASSES)}")

    drills, belts, factories, sorters, skipped = [], [], [], [], []

    for varname, classname, blockname, body in blocks:
        size = field_int(body, "size", default=1)

        if classname == "Drill":
            tier = field_int(body, "tier")
            drill_time = field_float(body, "drillTime", default=300.0)
            hardness_mult = field_float(body, "hardnessDrillMultiplier", default=50.0)
            if tier is None:
                skipped.append((blockname, "Drill", "thiếu tier"))
                continue
            drills.append({"name": blockname, "size": size, "tier": tier, "drill_time": drill_time, "hardness_multiplier": hardness_mult})

        elif classname == "Conveyor":
            speed = field_float(body, "displayedSpeed")
            if speed is None:
                skipped.append((blockname, "Conveyor", "thiếu displayedSpeed"))
                continue
            belts.append({"name": blockname, "size": size, "base_rate": speed})

        elif classname == "GenericCrafter":
            craft_time_ticks = field_float(body, "craftTime", default=80.0)
            output = parse_output(body, item_field_to_name)
            inputs = parse_consume(body, item_field_to_name)
            if output is None:
                skipped.append((blockname, "GenericCrafter", "thiếu/không parse được outputItem"))
                continue
            if inputs is None:
                skipped.append((blockname, "GenericCrafter", "thiếu/không parse được input item (có thể chỉ dùng liquid/power)"))
                continue
            factories.append({
                "name": blockname, "size": size,
                "craft_time_ticks": craft_time_ticks,
                "inputs": inputs,
                "output_item": output[0], "output_amount": output[1],
            })

        elif classname == "Sorter":
            sorters.append({"name": blockname, "size": size})

    print(f"  -> drill: {len(drills)}, belt: {len(belts)}, factory: {len(factories)}, sorter: {len(sorters)}, bỏ qua: {len(skipped)}")

    write_output(item_field_to_name, drills, belts, factories, sorters, skipped)
    print(f"đã ghi {OUT_PATH}")


def write_output(item_field_to_name, drills, belts, factories, sorters, skipped):
    lines = [
        '"""TỰ ĐỘNG SINH bởi tools/generate_catalog.py -- đừng sửa tay, chạy lại script.',
        "",
        "Nguồn: Anuken/Mindustry (master, reference/Blocks.java + Items.java).",
        f"Bỏ qua {len(skipped)} block không parse được (xem cuối file) -- không phải bug,",
        "là do format Java không khớp pattern hỗ trợ (vd input là liquid/power thay vì item).",
        '"""',
        "",
        "from .buildings import BuildingType, Item, Recipe",
        "",
        "GENERATED_ITEMS = {",
    ]
    for name, hardness in sorted({v[0]: v[1] for v in item_field_to_name.values()}.items()):
        lines.append(f'    "{name}": Item("{name}", hardness={hardness}),')
    lines.append("}")
    lines.append("")
    lines.append("GENERATED_BUILDINGS = {")

    for d in sorted(drills, key=lambda b: b["name"]):
        lines.append(
            f'    "{d["name"]}": BuildingType("{d["name"]}", size={d["size"]}, kind="drill", '
            f'drill_time={d["drill_time"]}, hardness_multiplier={d["hardness_multiplier"]}, tier={d["tier"]}),'
        )
    for b in sorted(belts, key=lambda b: b["name"]):
        lines.append(f'    "{b["name"]}": BuildingType("{b["name"]}", size={b["size"]}, kind="belt", base_rate={b["base_rate"]}),')
    for f in sorted(factories, key=lambda b: b["name"]):
        inputs_repr = "{" + ", ".join(f'"{k}": {v}' for k, v in f["inputs"].items()) + "}"
        craft_time_s = f["craft_time_ticks"] / 60.0
        lines.append(
            f'    "{f["name"]}": BuildingType("{f["name"]}", size={f["size"]}, kind="factory", recipe=Recipe('
            f'craft_time={craft_time_s!r}, inputs={inputs_repr}, output_item="{f["output_item"]}", output_amount={f["output_amount"]})),'
        )
    for s in sorted(sorters, key=lambda b: b["name"]):
        lines.append(f'    "{s["name"]}": BuildingType("{s["name"]}", size={s["size"]}, kind="sorter", config_type="item"),')
    lines.append("}")
    lines.append("")
    lines.append("# Bỏ qua khi sinh (không parse được), để tham khảo/khắc phục sau:")
    lines.append("SKIPPED = [")
    for name, cls, reason in skipped:
        lines.append(f'    ("{name}", "{cls}", "{reason}"),')
    lines.append("]")

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
