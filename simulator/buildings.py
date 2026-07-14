from dataclasses import dataclass, field
from typing import Optional

# rotation: 0=East(+x), 1=South(+y), 2=West(-x), 3=North(-y)
DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

TICKS_PER_SECOND = 60  # Mindustry's logic update rate


@dataclass(frozen=True)
class Item:
    name: str
    hardness: int


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
