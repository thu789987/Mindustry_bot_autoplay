import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout


def scenario_direct_to_core():
    """drill -> belt -> belt -> belt -> core, no processing."""
    grid = Grid(width=10, height=5)
    for x, y in [(0, 1), (1, 1), (0, 2), (1, 2)]:
        grid.set_ore(x, y, "copper")

    grid.place(CATALOG["mechanical-drill"], 0, 1, rotation=0, ore_target="copper")
    for x in (2, 3, 4):
        grid.place(CATALOG["conveyor"], x, 2, rotation=0)
    grid.place(CATALOG["core"], 5, 1, rotation=0)

    return grid


def scenario_with_smelter():
    """drill -> belt -> graphite press -> belt -> core."""
    grid = Grid(width=14, height=5)
    for x, y in [(0, 1), (1, 1), (0, 2), (1, 2)]:
        grid.set_ore(x, y, "coal")

    grid.place(CATALOG["mechanical-drill"], 0, 1, rotation=0, ore_target="coal")
    grid.place(CATALOG["conveyor"], 2, 2, rotation=0)
    grid.place(CATALOG["graphite-press"], 3, 1, rotation=0)
    for x in (5, 6, 7):
        grid.place(CATALOG["conveyor"], x, 2, rotation=0)
    grid.place(CATALOG["core"], 8, 1, rotation=0)

    return grid


def report(name, grid):
    result = evaluate_layout(grid)
    print(f"\n=== {name} ===")
    print(f"score (items/sec reaching core): {result['score']:.3f}")
    for b, rate in result["output_rate"].items():
        print(f"  {b.type.name:>16} @ ({b.x},{b.y}) rot={b.rotation}  output={rate:.3f}/s")


if __name__ == "__main__":
    report("direct to core", scenario_direct_to_core())
    report("drill -> smelter -> core", scenario_with_smelter())
