from collections import defaultdict

from .buildings import DIRECTIONS, ITEMS, TICKS_PER_SECOND
from .grid import Grid, PlacedBuilding


def trace_belt_path(grid: Grid, x: int, y: int):
    """Follow a chain of conveyor tiles starting at (x, y), each belt continuing
    in its own facing direction, until a non-belt building or a dead end is hit.

    Returns (destination_building, bottleneck_capacity) or None if the path
    runs off the map or into empty space.
    """
    capacity = float("inf")
    visited = set()
    while grid.in_bounds(x, y):
        if (x, y) in visited:
            return None  # loop
        visited.add((x, y))
        b = grid.building_at(x, y)
        if b is None:
            return None  # dead end
        if b.type.kind != "belt":
            return b, capacity
        capacity = min(capacity, b.type.base_rate)
        dx, dy = DIRECTIONS[b.rotation]
        x, y = x + dx, y + dy
    return None


def find_connections(grid: Grid):
    """Trace an output-carrying edge from every drill/factory to whatever
    building its belt path leads into. Each source has a single outgoing
    path (from its one output tile); a destination can receive from several
    sources. v1 has no junctions/splitters that merge or split a single
    belt's contents."""
    connections = []
    for b in grid.unique_buildings():
        if b.type.kind in ("drill", "factory"):
            ox, oy = b.output_tile()
            result = trace_belt_path(grid, ox, oy)
            if result:
                dest, cap = result
                if dest is not b:
                    connections.append((b, dest, cap))
    return connections


def produced_item(b: PlacedBuilding):
    """What item type a building's output belt carries -- needed so a
    multi-input factory can tell its incoming belts apart (e.g. coal vs
    sand feeding a silicon smelter) instead of summing unrelated items."""
    if b.type.kind == "drill":
        return b.ore_target
    if b.type.kind == "factory":
        return b.type.recipe.output_item
    return None


def _drill_output_rate(grid: Grid, b: PlacedBuilding):
    """Matches Drill.getDrillTime()/updateTile() in the real game: a drill
    picks one ore type under its footprint (here: the caller-assigned
    ore_target) and mines it at a rate set by tile count and item hardness."""
    item = ITEMS.get(b.ore_target)
    if item is None or item.hardness > b.type.tier:
        return 0.0  # unknown item, or too hard for this drill's tier

    count = sum(
        1
        for x, y in b.footprint()
        if grid.in_bounds(x, y) and grid.tiles[y][x].ore == b.ore_target
    )
    drill_time = b.type.drill_time + b.type.hardness_multiplier * item.hardness
    if drill_time <= 0:
        return 0.0
    return TICKS_PER_SECOND * count / drill_time


def evaluate_layout(grid: Grid):
    """Compute steady-state material throughput reaching the core.

    Model: each building's output rate is a pure function of its incoming
    rate(s), computed via memoized recursion over the connection graph
    (drills are sources, core is the sink). Assumes no cycles.
    """
    connections = find_connections(grid)
    in_edges = defaultdict(list)   # building -> [(source, belt_capacity)]
    for src, dest, cap in connections:
        in_edges[dest].append((src, cap))

    output_rate: dict[int, float] = {}

    def compute(b: PlacedBuilding, visiting: set):
        key = id(b)
        if key in output_rate:
            return output_rate[key]
        if key in visiting:
            output_rate[key] = 0.0  # cycle guard
            return 0.0
        visiting.add(key)

        if b.type.kind == "drill":
            rate = _drill_output_rate(grid, b)
        elif b.type.kind == "factory":
            recipe = b.type.recipe
            cycle_rate = 1.0 / recipe.craft_time
            for item_name, amount_per_cycle in recipe.inputs.items():
                available = sum(
                    min(compute(src, visiting), cap)
                    for src, cap in in_edges[b]
                    if produced_item(src) == item_name
                )
                cycle_rate = min(cycle_rate, available / amount_per_cycle)
            rate = max(cycle_rate, 0.0) * recipe.output_amount
        elif b.type.kind == "core":
            rate = sum(min(compute(src, visiting), cap) for src, cap in in_edges[b])
        else:
            rate = 0.0

        visiting.discard(key)
        output_rate[key] = rate
        return rate

    buildings = grid.unique_buildings()
    for b in buildings:
        compute(b, set())

    core = next((b for b in buildings if b.type.kind == "core"), None)
    score = output_rate.get(id(core), 0.0) if core else 0.0

    return {
        "score": score,
        "connections": connections,
        "output_rate": {b: output_rate[id(b)] for b in buildings},
    }
