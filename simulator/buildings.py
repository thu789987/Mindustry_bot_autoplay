from dataclasses import dataclass
from typing import Optional

# rotation: 0=East(+x), 1=South(+y), 2=West(-x), 3=North(-y)
DIRECTIONS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

TICKS_PER_SECOND = 60  # Mindustry's logic update rate


@dataclass(frozen=True)
class Item:
    name: str
    hardness: int


# Source: core/src/mindustry/content/Items.java (Anuken/Mindustry, fetched 2026-07-13)
ITEMS = {
    "copper": Item("copper", hardness=1),
    "coal": Item("coal", hardness=2),
    "sand": Item("sand", hardness=0),  # hardness not overridden in source -> default 0
}


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
    kind: str                   # "drill" | "belt" | "factory" | "core"
    base_rate: float = 0.0      # belt: max items/sec capacity
    drill_time: float = 0.0     # drill: base ticks per item, see Drill.getDrillTime()
    hardness_multiplier: float = 0.0  # drill: extra ticks per point of item hardness
    tier: int = 0                # drill: max hardness it can mine (tile.drop().hardness <= tier)
    recipe: Optional[Recipe] = None


# Real values pulled from Anuken/Mindustry source (master branch, fetched 2026-07-13):
#   Blocks.java   -> mechanicalDrill, conveyor, graphitePress, siliconSmelter field values
#   Drill.java    -> getDrillTime(item) = (drillTime + hardnessDrillMultiplier * item.hardness)
#                     drill rate (items/sec) = 60 * matching_ore_tile_count / getDrillTime(item)
#                     (this is exactly the "drillspeed" stat the game itself displays)
#   Items.java    -> item hardness values
# Not modeled (see README limitations): mechanicalDrill's optional water boost,
# power requirements (siliconSmelter needs power in the real game -- ignored
# here), tier-3+ drills, non-default drillMultipliers per item.
MECHANICAL_DRILL = BuildingType(
    "mechanical-drill", size=2, kind="drill",
    drill_time=600, hardness_multiplier=50, tier=2,
)
CONVEYOR = BuildingType("conveyor", size=1, kind="belt", base_rate=6.5)  # Blocks.java displayedSpeed
GRAPHITE_PRESS = BuildingType(
    "graphite-press",
    size=2,
    kind="factory",
    recipe=Recipe(craft_time=1.5, inputs={"coal": 2}, output_item="graphite", output_amount=1),
)
SILICON_SMELTER = BuildingType(
    "silicon-smelter",
    size=2,
    kind="factory",
    recipe=Recipe(craft_time=40 / TICKS_PER_SECOND, inputs={"coal": 1, "sand": 2}, output_item="silicon", output_amount=1),
)
CORE = BuildingType("core", size=3, kind="core")

CATALOG = {b.name: b for b in [MECHANICAL_DRILL, CONVEYOR, GRAPHITE_PRESS, SILICON_SMELTER, CORE]}
