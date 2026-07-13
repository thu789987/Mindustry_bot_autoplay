from dataclasses import dataclass
from typing import Optional

# rotation: 0=East(+x), 1=South(+y), 2=West(-x), 3=North(-y)
DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

TICKS_PER_SECOND = 60  # Mindustry's logic update rate


@dataclass(frozen=True)
class Item:
    name: str
    hardness: int


@dataclass(frozen=True)
class Recipe:
    craft_time: float       # seconds per craft cycle
    inputs: dict             # item name -> units consumed per cycle (may be >1 item)
    output_item: str
    output_amount: float    # units produced per cycle


@dataclass(frozen=True)
class BuildingType:
    name: str
    size: int                  # footprint is size x size
    kind: str                   # "drill" | "belt" | "factory" | "core" | "sorter"
    base_rate: float = 0.0      # belt: max items/sec capacity
    drill_time: float = 0.0     # drill: base ticks per item, see Drill.getDrillTime()
    hardness_multiplier: float = 0.0  # drill: extra ticks per point of item hardness
    tier: int = 0                # drill: max hardness it can mine (tile.drop().hardness <= tier)
    recipe: Optional[Recipe] = None
    # None = not configurable via BuildingComp.configureAny(); "item" = takes
    # an Item as config value (see Sorter.java: config(Item.class, ...)).
    config_type: Optional[str] = None


# core không phải Drill/Conveyor/GenericCrafter nên tools/generate_catalog.py
# không phủ tới -- vẫn khai báo tay, không có recipe/rate liên quan để lấy sai.
CORE = BuildingType("core", size=3, kind="core")

# ITEMS/CATALOG: phần lớn tự động sinh bởi tools/generate_catalog.py từ
# Anuken/Mindustry thật (xem simulator/generated_catalog.py và
# generated_catalog.SKIPPED cho danh sách bị bỏ qua kèm lý do). Import ở
# cuối file (sau khi Item/Recipe/BuildingType đã định nghĩa) để tránh vòng
# lặp import với generated_catalog.py.
from .generated_catalog import GENERATED_BUILDINGS, GENERATED_ITEMS  # noqa: E402

ITEMS = dict(GENERATED_ITEMS)
CATALOG = {**GENERATED_BUILDINGS, "core": CORE}
