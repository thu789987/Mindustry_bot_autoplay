"""TỰ ĐỘNG SINH bởi tools/generate_catalog.py -- đừng sửa tay, chạy lại script.

Nguồn: Anuken/Mindustry (master, reference/Blocks.java + Items.java).
Bỏ qua 5 block không parse được (xem cuối file) -- không phải bug,
là do format Java không khớp pattern hỗ trợ (vd input là liquid/power thay vì item).
"""

from .buildings import BuildingType, Item, Recipe

GENERATED_ITEMS = {
    "beryllium": Item("beryllium", hardness=3),
    "blast-compound": Item("blast-compound", hardness=0),
    "carbide": Item("carbide", hardness=0),
    "coal": Item("coal", hardness=2),
    "copper": Item("copper", hardness=1),
    "dormant-cyst": Item("dormant-cyst", hardness=0),
    "fissile-matter": Item("fissile-matter", hardness=0),
    "graphite": Item("graphite", hardness=0),
    "lead": Item("lead", hardness=1),
    "metaglass": Item("metaglass", hardness=0),
    "oxide": Item("oxide", hardness=0),
    "phase-fabric": Item("phase-fabric", hardness=0),
    "plastanium": Item("plastanium", hardness=0),
    "pyratite": Item("pyratite", hardness=0),
    "sand": Item("sand", hardness=0),
    "scrap": Item("scrap", hardness=0),
    "silicon": Item("silicon", hardness=0),
    "spore-pod": Item("spore-pod", hardness=0),
    "surge-alloy": Item("surge-alloy", hardness=0),
    "thorium": Item("thorium", hardness=4),
    "titanium": Item("titanium", hardness=3),
    "tungsten": Item("tungsten", hardness=5),
}

GENERATED_BUILDINGS = {
    "blast-drill": BuildingType("blast-drill", size=4, kind="drill", drill_time=280.0, hardness_multiplier=50.0, tier=5),
    "laser-drill": BuildingType("laser-drill", size=3, kind="drill", drill_time=280.0, hardness_multiplier=50.0, tier=4),
    "mechanical-drill": BuildingType("mechanical-drill", size=2, kind="drill", drill_time=600.0, hardness_multiplier=50.0, tier=2),
    "pneumatic-drill": BuildingType("pneumatic-drill", size=2, kind="drill", drill_time=400.0, hardness_multiplier=50.0, tier=3),
    "conveyor": BuildingType("conveyor", size=1, kind="belt", base_rate=6.5),
    "titanium-conveyor": BuildingType("titanium-conveyor", size=1, kind="belt", base_rate=10.0),
    "blast-mixer": BuildingType("blast-mixer", size=2, kind="factory", recipe=Recipe(craft_time=1.3333333333333333, inputs={"pyratite": 1.0, "spore-pod": 1.0}, output_item="blast-compound", output_amount=1)),
    "graphite-press": BuildingType("graphite-press", size=2, kind="factory", recipe=Recipe(craft_time=1.5, inputs={"coal": 2.0}, output_item="graphite", output_amount=1)),
    "kiln": BuildingType("kiln", size=2, kind="factory", recipe=Recipe(craft_time=0.5, inputs={"lead": 1.0, "sand": 1.0}, output_item="metaglass", output_amount=1)),
    "multi-press": BuildingType("multi-press", size=3, kind="factory", recipe=Recipe(craft_time=0.5, inputs={"coal": 3.0}, output_item="graphite", output_amount=2)),
    "phase-weaver": BuildingType("phase-weaver", size=2, kind="factory", recipe=Recipe(craft_time=2.0, inputs={"thorium": 4.0, "sand": 10.0}, output_item="phase-fabric", output_amount=1)),
    "plastanium-compressor": BuildingType("plastanium-compressor", size=2, kind="factory", recipe=Recipe(craft_time=1.0, inputs={"titanium": 2.0}, output_item="plastanium", output_amount=1)),
    "pulverizer": BuildingType("pulverizer", size=1, kind="factory", recipe=Recipe(craft_time=0.6666666666666666, inputs={"scrap": 1.0}, output_item="sand", output_amount=1)),
    "pyratite-mixer": BuildingType("pyratite-mixer", size=2, kind="factory", recipe=Recipe(craft_time=1.3333333333333333, inputs={"coal": 1.0, "lead": 2.0, "sand": 2.0}, output_item="pyratite", output_amount=1)),
    "silicon-arc-furnace": BuildingType("silicon-arc-furnace", size=3, kind="factory", recipe=Recipe(craft_time=0.8333333333333334, inputs={"graphite": 1.0, "sand": 4.0}, output_item="silicon", output_amount=4)),
    "silicon-smelter": BuildingType("silicon-smelter", size=2, kind="factory", recipe=Recipe(craft_time=0.6666666666666666, inputs={"coal": 1.0, "sand": 2.0}, output_item="silicon", output_amount=1)),
    "slag-centrifuge": BuildingType("slag-centrifuge", size=3, kind="factory", recipe=Recipe(craft_time=1.0, inputs={"sand": 1.0}, output_item="scrap", output_amount=1)),
    "surge-smelter": BuildingType("surge-smelter", size=3, kind="factory", recipe=Recipe(craft_time=1.25, inputs={"copper": 3.0, "lead": 4.0, "titanium": 2.0, "silicon": 3.0}, output_item="surge-alloy", output_amount=1)),
    "inverted-sorter": BuildingType("inverted-sorter", size=1, kind="sorter", config_type="item"),
    "sorter": BuildingType("sorter", size=1, kind="sorter", config_type="item"),
}

# Bỏ qua khi sinh (không parse được), để tham khảo/khắc phục sau:
SKIPPED = [
    ("cryofluid-mixer", "GenericCrafter", "thiếu/không parse được outputItem"),
    ("melter", "GenericCrafter", "thiếu/không parse được outputItem"),
    ("spore-press", "GenericCrafter", "thiếu/không parse được outputItem"),
    ("coal-centrifuge", "GenericCrafter", "thiếu/không parse được input item (có thể chỉ dùng liquid/power)"),
    ("electrolyzer", "GenericCrafter", "thiếu/không parse được outputItem"),
]
