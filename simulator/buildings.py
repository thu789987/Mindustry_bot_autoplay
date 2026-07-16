from dataclasses import dataclass, field
from typing import Optional

# rotation: 0=East(+x), 1=South(+y), 2=West(-x), 3=North(-y)
DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

TICKS_PER_SECOND = 60  # Mindustry's logic update rate


@dataclass(frozen=True)
class Item:
    name: str
    hardness: int
    # ConsumeItemFlammable.java: lọc nhiên liệu cho generator (combustion-
    # generator/steam-generator) theo item.flammability >= minFlammability,
    # hiệu suất phát điện tỉ lệ thuận với flammability -- than (coal) = 1.0
    # (cao nhất), phần lớn item khác = 0.
    flammability: float = 0.0


@dataclass(frozen=True)
class Liquid:
    name: str


@dataclass(frozen=True)
class Recipe:
    craft_time: float                  # seconds per craft cycle
    inputs: dict                        # item name -> units consumed per cycle (may be >1 item)
    output_item: str
    output_amount: float               # units produced per cycle
    liquid_inputs: dict = field(default_factory=dict)  # liquid name -> units/sec needed


@dataclass(frozen=True)
class BuildingType:
    name: str
    size: int                  # footprint is size x size
    kind: str                   # "drill"|"belt"|"factory"|"core"|"sorter"|"pump"|"liquid-belt"|<real category string>
    base_rate: float = 0.0      # belt/liquid-belt: max flow/sec capacity
    drill_time: float = 0.0     # drill: base ticks per item, see Drill.getDrillTime()
    hardness_multiplier: float = 0.0  # drill: extra ticks per point of item hardness
    tier: int = 0                # drill: max hardness it can mine (tile.drop().hardness <= tier)
    recipe: Optional[Recipe] = None
    # None = not configurable via BuildingComp.configureAny(); "item" = takes
    # an Item as config value (see Sorter.java: config(Item.class, ...)).
    config_type: Optional[str] = None
    pump_amount: float = 0.0    # pump: see Pump.java pumpAmount, rate = 60*pump_amount*matching_liquid_tiles
    # sorter: đảo ngược thẳng/rẽ (Sorter.java: `(item==sortItem) != invert`,
    # vd inverted-sorter). overflow-gate: đảo ưu tiên thẳng/rẽ (OverflowGate.java
    # `invert == enabled`, vd underflow-gate rẽ trước, thẳng chỉ khi rẽ đầy).
    invert: bool = False
    # bridge (item/liquid): khoảng cách tối đa (số ô) 2 đầu cầu được link, xem
    # ItemBridge.java `range`. mass-driver: tầm bắn quy đổi ra số ô (range/8,
    # tilesize=8), xem MassDriver.java `range` (đơn vị pixel trong source).
    link_range: float = 0.0
    # mass-driver: xem MassDriver.java itemCapacity/reload -- bắn cả cụm item
    # tích luỹ mỗi khi hồi xong, tốc độ trung bình xấp xỉ = 60*capacity/reload
    # (giống cách drill/pump đã xấp xỉ 1 quá trình rời rạc thành tốc độ liên
    # tục ổn định, không phải số thật tức thời).
    driver_capacity: float = 0.0
    driver_reload: float = 0.0
    # Real Mindustry category (Category.production/distribution/liquid/power/
    # defense/logic/units/...) for buildings the planner has NO placement
    # logic for yet (kind == category string in that case) -- lets the bot
    # report "chưa hỗ trợ xây loại X" instead of guessing. See
    # NEXT_STEPS.md mục "Phạm vi chưa làm" for what each would need.
    category: Optional[str] = None
    # kind="generator" (ConsumeGenerator.java, vd combustion-generator/
    # steam-generator): đốt BẤT KỲ item nào đủ flammability >= min_flammability
    # (không phải 1 item cố định như factory thường -- xem sim.py
    # _generator_power_rate), power_production = công suất/tick ở hiệu suất
    # 100% (item flammability=1.0, xem PowerGenerator.java powerProduction),
    # item_duration = số tick đốt hết 1 item (ConsumeGenerator.java itemDuration).
    power_production: float = 0.0
    item_duration: float = 0.0
    min_flammability: float = 0.0
    # generator: liquid cần kèm nhiên liệu cháy (vd steam-generator cần cả
    # than lẫn nước) -- tách riêng khỏi `recipe` (Recipe dataclass giả định
    # có 1 output_item cố định, không khớp generator không xuất item nào cả).
    generator_liquid_inputs: dict = field(default_factory=dict)
    # power_input: công suất/giây building này CẦN khi hoạt động (drill tier
    # cao/nhiều factory thật cần điện, xem Blocks.java consumePower()) --
    # 0 nghĩa là không cần điện (hầu hết building tier thấp, vd
    # mechanical-drill/graphite-press).
    power_input: float = 0.0
    # kind="power-node" (PowerNode.java): bán kính (số ô) tự động link không
    # dây tới building có điện khác trong tầm -- xem PowerNode.java laserRange.
    power_range: float = 0.0
    # kind="beam-drill" (BeamDrill.java, vd plasma-bore/large-plasma-bore):
    # số ô bắn tia dò ore từ MỖI cạnh (không phải diện tích chân đế như
    # Drill thường) -- xem sim.py _beam_drill_output_rate. `tier` dùng lại
    # field có sẵn (drill thường) làm ngưỡng cứng hardness <= tier, KHÔNG có
    # hardness_multiplier (BeamDrill.java không hề có field này -- hardness
    # chỉ chặn/không chặn, không làm chậm tốc độ như Drill thường).
    beam_range: int = 0
    # kind="wall-crafter" (WallCrafter.java, vd cliff-crusher/large-cliff-crusher):
    # đọc attribute từ các ô đá/tường TỰ NHIÊN dọc cạnh đang xoay mặt tới
    # (Tile.attribute trong grid.py, xem sim.py _wall_crafter_output_rate).
    # KHÔNG dùng Recipe (không có input item cố định như factory thường).
    wall_attribute: Optional[str] = None
    wall_output: Optional[str] = None
    # kind="solid-pump" (SolidPump.java, vd water-extractor): giống Pump
    # nhưng KHÔNG cần tile.liquid khớp -- quét TOÀN BỘ diện tích chân đế
    # (giống Drill quét ore, khác WallCrafter chỉ 1 cạnh) đếm tile mang
    # đúng `solid_pump_attribute` (Tile.attribute), rate = pump_amount *
    # 60 * số_tile_khớp -- xem sim.py _solid_pump_output_rate. Liquid sinh
    # ra CỐ ĐỊNH theo catalog (`result` trong SolidPump.java thật), không
    # phải người dùng chỉ định như Pump thường.
    solid_pump_attribute: Optional[str] = None
    solid_pump_liquid: Optional[str] = None
    # kind="drill" (Drill.java): boost KHÔNG BẮT BUỘC -- consumeLiquid(...).boost()
    # thật, khác consumePower() bắt buộc. Không có nước vẫn đào ở tốc độ nền
    # bình thường (_drill_output_rate), có đủ nước thì NHÂN THÊM tốc độ theo
    # boost_intensity -- xem sim.py công thức
    # speed = lerp(1.0, boost_intensity, hiệu_suất_nước).
    # boost_amount là giá trị THÔ lấy thẳng từ consumeLiquid() thật (đơn vị
    # /tick, giống quy ước pump_amount) -- nhân 60 để ra lưu lượng cần/giây.
    boost_liquid: Optional[str] = None
    boost_amount: float = 0.0
    # Drill.java mặc định liquidBoostIntensity=1.6f (mechanical/pneumatic/laser
    # dùng nguyên mặc định này, không ghi đè); blast-drill ghi đè riêng thành
    # 1.8f (comment thật trong Blocks.java: "more than the laser drill").
    boost_intensity: float = 1.6


# core không phải Drill/Conveyor/GenericCrafter nên tools/generate_catalog.py
# không phủ tới -- vẫn khai báo tay, không có recipe/rate liên quan để lấy sai.
CORE = BuildingType("core", size=3, kind="core")

# ITEMS/LIQUIDS/CATALOG: phần lớn tự động sinh bởi tools/generate_catalog.py
# từ Anuken/Mindustry thật (xem simulator/generated_catalog.py và
# generated_catalog.SKIPPED cho danh sách bị bỏ qua kèm lý do). Import ở
# cuối file (sau khi Item/Liquid/Recipe/BuildingType đã định nghĩa) để tránh
# vòng lặp import với generated_catalog.py.
from .generated_catalog import (  # noqa: E402
    GENERATED_BUILDINGS,
    GENERATED_ITEMS,
    GENERATED_LIQUIDS,
    GENERATED_OTHER,
)

ITEMS = dict(GENERATED_ITEMS)
LIQUIDS = dict(GENERATED_LIQUIDS)
CATALOG = {**GENERATED_OTHER, **GENERATED_BUILDINGS, "core": CORE}
