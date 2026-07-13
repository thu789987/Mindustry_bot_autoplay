"""Auto-connect planner: given a build command and the current map state,
work out where to place the requested building and how to route belts from
existing (or newly-placed) resource sources to it, then emit an ordered list
of place actions ready to hand to the Mindustry mod (Giai đoạn 2).

Default behavior (no `scorer` passed to plan_build): picks the first workable
source and the nearest free spot -- "good enough" quickly, not optimal.

Pass a bot/scorer.py Scorer to plan_build() to rank several candidate spots
by learned preference instead (see bot/feedback.py for how weights update
from corrections). Optional and backward-compatible -- omit it and behavior
is unchanged.
"""

from collections import deque

from simulator.buildings import CATALOG, DIRECTIONS, ITEMS
from simulator.grid import Grid
from simulator.sim import produced_item, trace_belt_path


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


def find_free_area_candidates(grid: Grid, building_type, near, limit: int = 1, preferences: dict = None):
    """Expanding ring search around `near`, collecting up to `limit` spots
    where building_type fits. Candidates violating `preferences` (Cách 1
    hard rules, see bot/preferences.py) are skipped entirely -- the learned
    scorer (bot/scorer.py) never even sees them."""
    from bot.preferences import violates

    nx, ny = near
    max_radius = max(grid.width, grid.height)
    found = []
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(building_type, x, y):
                    continue
                if preferences is not None and violates(grid, (x, y), preferences):
                    continue
                found.append((x, y))
                if len(found) >= limit:
                    return found
    return found


def find_free_area(grid: Grid, building_type, near, preferences: dict = None):
    """Single-best-spot convenience wrapper around find_free_area_candidates."""
    candidates = find_free_area_candidates(grid, building_type, near, limit=1, preferences=preferences)
    return candidates[0] if candidates else None


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


def featurize_target_spot(grid: Grid, building_type, spot, sources, core_pos=None) -> dict:
    """Turns a candidate placement into numeric features for bot/scorer.py.
    Read-only: calls find_belt_path for length only, never places anything."""
    tx, ty = spot
    footprint = [(tx + fx, ty + fy) for fx in range(building_type.size) for fy in range(building_type.size)]

    total_belt_length = 0
    for _, output_tile in sources:
        path = find_belt_path(grid, output_tile, footprint)
        total_belt_length += len(path) if path is not None else 999  # unreachable: heavy penalty

    features = {"total_belt_length": float(total_belt_length)}
    if core_pos is not None:
        features["distance_to_core"] = float(abs(tx - core_pos[0]) + abs(ty - core_pos[1]))
    else:
        features["distance_to_core"] = 0.0
    return features


def plan_build(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
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
        new_drill = grid.place(building_type, x, y, rotation=0, ore_target=ore_target)

        # Tự nối belt về core nếu map đã có core -- trước đây build drill đơn
        # lẻ KHÔNG nối gì cả (bug thật, phát hiện khi trace thử lệnh "xây
        # drill... và dẫn tài nguyên về nhà chính": planner chỉ đặt drill rồi
        # dừng, im lặng bỏ qua phần "dẫn về nhà chính").
        core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
        if core is not None:
            path = find_belt_path(grid, new_drill.output_tile(), core.footprint())
            if path is None:
                raise RuntimeError(f"đã đặt drill '{ore_target}' nhưng không tìm được đường belt nối tới core")
            conveyor_type = CATALOG["conveyor"]
            for bx, by, rotation in path:
                grid.place(conveyor_type, bx, by, rotation=rotation)
                actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})

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

    if scorer is not None:
        candidates = find_free_area_candidates(grid, building_type, near=(cx, cy), limit=5, preferences=preferences)
        if not candidates:
            raise RuntimeError(f"không tìm được chỗ trống để đặt '{building_name}'")
        core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
        core_pos = (core.x, core.y) if core is not None else None
        scored = [
            (scorer.score(featurize_target_spot(grid, building_type, spot, sources, core_pos)), spot)
            for spot in candidates
        ]
        target_spot = max(scored, key=lambda pair: pair[0])[1]
    else:
        target_spot = find_free_area(grid, building_type, near=(cx, cy), preferences=preferences)
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


def resolve_target(grid: Grid, building_name: str, hint=None):
    """Tìm đúng 1 building cụ thể theo tên loại + gợi ý phân biệt (nếu có
    nhiều building cùng loại trên map). `hint`:
      - ("coord", (x, y)) -- toạ độ bất kỳ nằm trong footprint building đó
      - ("index", n)       -- building thứ n (1-based), sắp theo (y, x)
      - None                -- chỉ chấp nhận nếu có đúng 1 building loại đó

    Không tự đoán khi mơ hồ -- báo lỗi liệt kê toạ độ từng ứng viên để người
    dùng tự chỉ rõ, đúng tinh thần "bot không tự suy luận lý do" đã thống
    nhất khi bàn về học từ phản hồi.
    """
    matches = [b for b in grid.unique_buildings() if b.type.name == building_name]
    if not matches:
        raise RuntimeError(f"không tìm thấy building loại '{building_name}' nào trên map")

    if hint is not None:
        kind, value = hint
        if kind == "coord":
            hx, hy = value
            for b in matches:
                if (hx, hy) in b.footprint():
                    return b
            raise RuntimeError(f"không có building '{building_name}' nào ở toạ độ ({hx},{hy})")
        if kind == "index":
            matches.sort(key=lambda b: (b.y, b.x))
            if 1 <= value <= len(matches):
                return matches[value - 1]
            raise RuntimeError(f"chỉ có {len(matches)} building loại '{building_name}', không có cái thứ {value}")
        if kind == "ore_target":
            for b in matches:
                if b.ore_target == value:
                    return b
            raise RuntimeError(f"không có building '{building_name}' nào đang khai thác '{value}'")

    if len(matches) == 1:
        return matches[0]

    listing = ", ".join(f"({b.x},{b.y})" for b in matches)
    raise RuntimeError(
        f"có {len(matches)} building loại '{building_name}' trên map: {listing} -- "
        "nói rõ toạ độ (vd '(10,5)') hoặc thứ tự (vd 'thứ 2') để biết bạn muốn cái nào"
    )


def plan_delete(grid: Grid, command: dict) -> list:
    target = resolve_target(grid, command["building"], command.get("target_hint"))
    action = {"op": "remove", "x": target.x, "y": target.y}
    grid.remove(target)
    return [action]


def plan_rotate(grid: Grid, command: dict) -> list:
    target = resolve_target(grid, command["building"], command.get("target_hint"))
    new_rotation = command.get("rotation")
    if new_rotation is None:
        raise ValueError("lệnh xoay cần biết xoay theo hướng nào")
    target.rotation = new_rotation
    return [{"op": "place", "building": target.type.name, "x": target.x, "y": target.y, "rotation": new_rotation}]


def plan_configure(grid: Grid, command: dict) -> list:
    """Cấu hình building qua BuildingComp.configureAny() thật -- KHÁC hẳn
    setBlock (đặt/xoá/xoay) mà plan_build/plan_delete/plan_rotate dùng. Xem
    NEXT_STEPS.md mục "configure" cho nguồn xác nhận từ BuildingComp.java."""
    target = resolve_target(grid, command["building"], command.get("target_hint"))
    if target.type.config_type is None:
        raise ValueError(f"'{target.type.name}' không cấu hình được (không có configType)")

    value = command.get("value")
    if target.type.config_type == "item":
        if value not in ITEMS:
            raise ValueError(f"'{value}' không phải tên item hợp lệ")
    else:
        raise ValueError(f"chưa hỗ trợ config_type='{target.type.config_type}'")

    return [{"op": "configure", "x": target.x, "y": target.y, "value": value}]


def plan_reroute(grid: Grid, command: dict) -> list:
    """Xoá đường belt hiện tại nối 2 building rồi định tuyến lại bằng BFS
    (giống plan_build, chỉ khác là có đường cũ cần dọn trước)."""
    from_building = resolve_target(grid, command["from_building"], command.get("from_hint"))
    to_building = resolve_target(grid, command["to_building"], command.get("to_hint"))

    ox, oy = from_building.output_tile()
    result = trace_belt_path(grid, ox, oy)
    if result is None or result[0] is not to_building:
        raise RuntimeError(
            f"không tìm thấy đường belt hiện tại nối '{from_building.type.name}' "
            f"({from_building.x},{from_building.y}) tới '{to_building.type.name}' "
            f"({to_building.x},{to_building.y})"
        )

    actions = []
    x, y = ox, oy
    while True:
        b = grid.building_at(x, y)
        if b is None or b.type.kind != "belt":
            break
        actions.append({"op": "remove", "x": x, "y": y})
        grid.remove(b)
        dx, dy = DIRECTIONS[b.rotation]
        x, y = x + dx, y + dy

    new_path = find_belt_path(grid, (ox, oy), to_building.footprint())
    if new_path is None:
        raise RuntimeError(
            f"đã xoá đường cũ nhưng không tìm được đường belt mới nối "
            f"'{from_building.type.name}' tới '{to_building.type.name}'"
        )

    conveyor_type = CATALOG["conveyor"]
    for bx, by, rotation in new_path:
        grid.place(conveyor_type, bx, by, rotation=rotation)
        actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})

    return actions


def plan(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    """Dispatcher theo command['action']. plan_build vẫn gọi được trực tiếp
    như cũ (tương thích ngược) -- đây chỉ là điểm vào chung cho live_run.py."""
    action = command.get("action")
    if action == "build":
        return plan_build(grid, command, scorer=scorer, preferences=preferences)
    if action == "delete":
        return plan_delete(grid, command)
    if action == "configure":
        return plan_configure(grid, command)
    if action == "rotate":
        return plan_rotate(grid, command)
    if action == "reroute":
        return plan_reroute(grid, command)
    raise ValueError(f"không hỗ trợ action '{action}'")
