"""Auto-connect planner: given a build command and the current map state,
work out where to place the requested building and how to route belts from
existing (or newly-placed) resource sources to it, then emit an ordered list
of place actions ready to hand to the Mindustry mod (Giai đoạn 2).

Deliberately not a search/optimizer (that's luồng A's job) -- this picks the
first workable source and the nearest free spot, matching how a player would
build something "good enough" quickly rather than searching for optimal.
"""

from collections import deque

from simulator.buildings import CATALOG, DIRECTIONS
from simulator.grid import Grid
from simulator.sim import produced_item


def find_producer(grid: Grid, item_name: str):
    for b in grid.unique_buildings():
        if produced_item(b) == item_name:
            return b
    return None


def find_unmined_ore(grid: Grid, item_name: str):
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.tiles[y][x].ore == item_name and grid.building_at(x, y) is None:
                return (x, y)
    return None


def find_free_area(grid: Grid, building_type, near):
    """Expanding ring search around `near` for a spot where building_type fits."""
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if grid.can_place(building_type, x, y):
                    return (x, y)
    return None


def find_drill_spot(grid: Grid, ore_item: str, near):
    """Like find_free_area, but also requires at least one footprint tile to
    actually hold the target ore (an empty spot alone isn't useful for a drill)."""
    drill_type = CATALOG["mechanical-drill"]
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(drill_type, x, y):
                    continue
                footprint = [(x + fx, y + fy) for fx in range(drill_type.size) for fy in range(drill_type.size)]
                if any(grid.in_bounds(fx, fy) and grid.tiles[fy][fx].ore == ore_item for fx, fy in footprint):
                    return (x, y)
    return None


def find_belt_path(grid: Grid, start, target_footprint):
    """BFS over empty tiles from `start` to a tile touching target_footprint.

    Returns a list of (x, y, rotation) belt placements from start to the tile
    just outside the footprint, [] if start already touches the footprint
    directly (no belt needed), or None if unreachable.
    """
    target_set = set(target_footprint)

    def touches_target(pos):
        return any((pos[0] + dx, pos[1] + dy) in target_set for dx, dy in DIRECTIONS)

    if start in target_set or touches_target(start):
        return []

    queue = deque([start])
    came_from = {start: None}
    goal = None
    while queue:
        cur = queue.popleft()
        if touches_target(cur):
            goal = cur
            break
        for dx, dy in DIRECTIONS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in came_from or not grid.in_bounds(*nxt) or nxt in target_set:
                continue
            if grid.building_at(*nxt) is not None:
                continue
            came_from[nxt] = cur
            queue.append(nxt)

    if goal is None:
        return None

    tiles = []
    node = goal
    while node is not None:
        tiles.append(node)
        node = came_from[node]
    tiles.reverse()

    placements = []
    for i, (x, y) in enumerate(tiles):
        if i + 1 < len(tiles):
            nx, ny = tiles[i + 1]
        else:
            nx, ny = next((x + dx, y + dy) for dx, dy in DIRECTIONS if (x + dx, y + dy) in target_set)
        rotation = DIRECTIONS.index((nx - x, ny - y))
        placements.append((x, y, rotation))
    return placements


def plan_build(grid: Grid, command: dict) -> list:
    if command.get("action") != "build":
        raise ValueError(f"unsupported command: {command}")

    building_name = command["building"]
    building_type = CATALOG[building_name]
    actions = []

    if building_type.kind == "drill":
        ore_target = command.get("ore_target")
        if ore_target is None:
            raise ValueError("drill command needs an ore_target (e.g. 'khoan than')")
        ore_pos = find_unmined_ore(grid, ore_target)
        if ore_pos is None:
            raise RuntimeError(f"không tìm thấy mỏ '{ore_target}' chưa khai thác trên map")
        spot = find_drill_spot(grid, ore_target, near=ore_pos)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ trống để đặt drill khai thác '{ore_target}'")
        x, y = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": 0, "ore_target": ore_target})
        return actions

    if building_type.kind != "factory":
        raise ValueError(f"planner chỉ hỗ trợ xây drill/factory, không hỗ trợ '{building_type.kind}'")

    recipe = building_type.recipe
    sources = []  # (item_name, output_tile)

    for item_name in recipe.inputs:
        producer = find_producer(grid, item_name)
        if producer is not None:
            sources.append((item_name, producer.output_tile()))
            continue

        ore_pos = find_unmined_ore(grid, item_name)
        if ore_pos is None:
            raise RuntimeError(f"không có nguồn '{item_name}' nào (chưa có building sản xuất, cũng không có mỏ trên map)")

        spot = find_drill_spot(grid, item_name, near=ore_pos)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ đặt drill cho '{item_name}'")
        dx, dy = spot
        actions.append({"op": "place", "building": "mechanical-drill", "x": dx, "y": dy, "rotation": 0, "ore_target": item_name})
        new_drill = grid.place(CATALOG["mechanical-drill"], dx, dy, rotation=0, ore_target=item_name)
        sources.append((item_name, new_drill.output_tile()))

    cx = sum(pos[0] for _, pos in sources) // len(sources)
    cy = sum(pos[1] for _, pos in sources) // len(sources)
    target_spot = find_free_area(grid, building_type, near=(cx, cy))
    if target_spot is None:
        raise RuntimeError(f"không tìm được chỗ trống để đặt '{building_name}'")
    tx, ty = target_spot
    grid.place(building_type, tx, ty, rotation=0)
    actions.append({"op": "place", "building": building_name, "x": tx, "y": ty, "rotation": 0})
    target_footprint = [(tx + fx, ty + fy) for fx in range(building_type.size) for fy in range(building_type.size)]

    conveyor_type = CATALOG["conveyor"]
    for item_name, output_tile in sources:
        path = find_belt_path(grid, output_tile, target_footprint)
        if path is None:
            raise RuntimeError(f"không tìm được đường belt từ nguồn '{item_name}' tới '{building_name}'")
        for bx, by, rotation in path:
            grid.place(conveyor_type, bx, by, rotation=rotation)
            actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})

    return actions
