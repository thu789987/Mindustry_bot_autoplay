from collections import Counter, defaultdict

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


def _direction_of(from_pos, to_pos):
    """Hướng di chuyển chủ đạo từ from_pos tới to_pos (0=Đông,1=Nam,2=Tây,
    3=Bắc, xem DIRECTIONS). Dùng để suy ra "đang đi hướng nào" khi tới 1
    sorter, vì Sorter.java tính dir từ vị trí tương đối của nguồn, không có
    rotation cố định như conveyor."""
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if abs(dx) >= abs(dy):
        return 0 if dx > 0 else 2
    return 1 if dy > 0 else 3


def _trace_branching(grid: Grid, pos, capacity, belt_kind: str, item_name=None, came_from=None):
    """Như trace_belt_path/trace_conduit_path nhưng hiểu router VÀ sorter:

    - router: tự CHIA capacity đều cho N nhánh còn nhận được (khớp cơ chế
      thật -- Router.java dùng round-robin qua các hướng còn trống).
    - sorter: item khớp `filter_item` thì đi THẲNG (tiếp tục đúng hướng đang
      di chuyển); không khớp thì rẽ sang 1 trong 2 hướng VUÔNG GÓC còn nhận
      được (chia đôi nếu cả 2 khả dụng) -- khớp đúng Sorter.java
      getTileTarget(): `nearby(dir)` nếu khớp, `nearby(dir±1)` nếu không.
      Cần biết `item_name` đang chảy (từ nguồn) để so khớp filter, và
      `came_from` để suy ra hướng đang di chuyển (không xác định được nếu
      sorter là tile đầu tiên chạm phải -- coi như điểm đến, an toàn).

    Trả về list [(dest, capacity), ...] -- nhiều hơn 1 phần tử nếu có
    router/sorter rẽ nhánh. `came_from`: toạ độ vừa đi qua."""
    x, y = pos
    if not grid.in_bounds(x, y):
        return []
    b = grid.building_at(x, y)
    if b is None:
        return []
    if b.type.kind == belt_kind:
        capacity = min(capacity, b.type.base_rate)
        dx, dy = DIRECTIONS[b.rotation]
        return _trace_branching(grid, (x + dx, y + dy), capacity, belt_kind, item_name, came_from=pos)
    if b.type.kind == "router":
        neighbors = [
            (x + dx, y + dy) for dx, dy in DIRECTIONS
            if (x + dx, y + dy) != came_from and grid.in_bounds(x + dx, y + dy)
            and grid.building_at(x + dx, y + dy) is not None
        ]
        n = len(neighbors) or 1
        results = []
        for nxt in neighbors:
            results.extend(_trace_branching(grid, nxt, capacity / n, belt_kind, item_name, came_from=pos))
        return results
    if b.type.kind == "sorter" and came_from is not None:
        dir_in = _direction_of(came_from, pos)
        # Sorter.java thật: `(item == sortItem) != invert`. Không đảo (sorter
        # thường): khớp filter đi thẳng. Đảo (inverted-sorter): khớp filter
        # lại RẼ, không khớp mới đi thẳng -- kể cả khi filter_item=None (chưa
        # cấu hình), inverted-sorter vẫn cho mọi thứ đi thẳng vì "không khớp
        # None" luôn đúng, đảo lại thành luôn thẳng.
        matched = (item_name == b.filter_item) != b.type.invert
        if matched:
            dx, dy = DIRECTIONS[dir_in]
            return _trace_branching(grid, (x + dx, y + dy), capacity, belt_kind, item_name, came_from=pos)
        side_positions = [
            (x + DIRECTIONS[(dir_in + 1) % 4][0], y + DIRECTIONS[(dir_in + 1) % 4][1]),
            (x + DIRECTIONS[(dir_in - 1) % 4][0], y + DIRECTIONS[(dir_in - 1) % 4][1]),
        ]
        valid_sides = [p for p in side_positions if grid.in_bounds(*p) and grid.building_at(*p) is not None]
        n = len(valid_sides) or 1
        results = []
        for nxt in valid_sides:
            results.extend(_trace_branching(grid, nxt, capacity / n, belt_kind, item_name, came_from=pos))
        return results
    if b.type.kind == "junction" and came_from is not None:
        # Junction.java thật: buffer riêng theo hướng vào, đi THẲNG qua theo
        # đúng hướng đang di chuyển (không dùng rotation của chính junction)
        # -- không rẽ, không trộn, cho phép 2 luồng vuông góc cắt nhau tại 1
        # ô mà không lẫn item (mỗi trace nguồn độc lập nên tự nhiên không
        # trộn, không cần mô hình buffer thật).
        dir_in = _direction_of(came_from, pos)
        dx, dy = DIRECTIONS[dir_in]
        return _trace_branching(grid, (x + dx, y + dy), capacity, belt_kind, item_name, came_from=pos)
    if b.type.kind == "overflow-gate" and came_from is not None:
        # OverflowGate.java thật: acceptItem() ĐỘNG, phụ thuộc mức đầy lúc
        # runtime -- simulator này tính throughput ổn định tĩnh nên xấp xỉ
        # TẤT ĐỊNH: overflow (invert=False) luôn ưu tiên đi thẳng, chỉ chia
        # sang 2 bên nếu KHÔNG có đường thẳng; underflow (invert=True) ngược
        # lại, ưu tiên rẽ, chỉ đi thẳng nếu không có bên nào. Không mô phỏng
        # trạng thái "đầy" thật (xem NEXT_STEPS.md).
        dir_in = _direction_of(came_from, pos)
        straight_pos = (x + DIRECTIONS[dir_in][0], y + DIRECTIONS[dir_in][1])
        side_positions = [
            (x + DIRECTIONS[(dir_in + 1) % 4][0], y + DIRECTIONS[(dir_in + 1) % 4][1]),
            (x + DIRECTIONS[(dir_in - 1) % 4][0], y + DIRECTIONS[(dir_in - 1) % 4][1]),
        ]
        has_straight = grid.in_bounds(*straight_pos) and grid.building_at(*straight_pos) is not None
        valid_sides = [p for p in side_positions if grid.in_bounds(*p) and grid.building_at(*p) is not None]
        if not b.type.invert:
            targets = [straight_pos] if has_straight else valid_sides
        else:
            targets = valid_sides if valid_sides else ([straight_pos] if has_straight else [])
        n = len(targets) or 1
        results = []
        for nxt in targets:
            results.extend(_trace_branching(grid, nxt, capacity / n, belt_kind, item_name, came_from=pos))
        return results
    if b.type.kind == "bridge":
        # ItemBridge.java/LiquidBridge.java/DuctBridge.java thật: bắc cầu qua
        # khoảng trống tới link_target (do planner gán, xem grid.py), rồi
        # item tiếp tục đi theo rotation của ĐẦU CẦU BÊN KIA như 1 tile bình
        # thường -- không giới hạn capacity (giống cách conduit đã xấp xỉ
        # base_rate=inf, nghẽn thật nằm ở nơi khác, không phải ở cầu).
        if b.link_target is None:
            return [(b, capacity)]  # cầu chưa link -- coi như điểm dừng
        # Dùng output_tile() (tính theo size thật) chứ không phải (x,y) gốc +
        # 1 bước -- bug thật đã gặp: với building size>1, x+dx vẫn còn nằm
        # TRONG chân đế của chính link_target, khiến trace quay lại đúng
        # building đó và đệ quy vô hạn (RecursionError).
        link_out = b.link_target.output_tile()
        ldx, ldy = DIRECTIONS[b.link_target.rotation]
        synthetic_came_from = (link_out[0] - ldx, link_out[1] - ldy)
        return _trace_branching(grid, link_out, capacity, belt_kind, item_name, came_from=synthetic_came_from)
    if b.type.kind == "mass-driver":
        # MassDriver.java thật: bắn cả cụm item tích luỹ mỗi khi hồi xong --
        # xấp xỉ tốc độ trung bình ổn định = 60*driver_capacity/driver_reload
        # (giống drill/pump), áp dụng như 1 giới hạn capacity tại điểm vào
        # driver NGUỒN, rồi teleport sang driver đích giống bridge.
        if b.link_target is None:
            return [(b, capacity)]  # chưa link tới driver khác -- điểm dừng
        avg_rate = (
            TICKS_PER_SECOND * b.type.driver_capacity / b.type.driver_reload
            if b.type.driver_reload else 0.0
        )
        capacity = min(capacity, avg_rate)
        link_out = b.link_target.output_tile()
        ldx, ldy = DIRECTIONS[b.link_target.rotation]
        synthetic_came_from = (link_out[0] - ldx, link_out[1] - ldy)
        return _trace_branching(grid, link_out, capacity, belt_kind, item_name, came_from=synthetic_came_from)
    return [(b, capacity)]


SOURCE_KINDS = ("drill", "factory", "unloader")


def find_connections(grid: Grid):
    """Trace output-carrying edges from every drill/factory to whatever it
    leads into. Each source has 1 output tile, but that path can now FORK at
    a router or sorter (see _trace_branching) -- a source can reach several
    destinations, each getting a share of capacity. Rate conservation across
    branches is enforced in evaluate_layout (divides by branch count), not
    here -- this only returns the raw edges."""
    connections = []
    for b in grid.unique_buildings():
        if b.type.kind in SOURCE_KINDS:
            ox, oy = b.output_tile()
            # came_from giả định "1 ô phía sau, theo đúng hướng nguồn đang
            # quay mặt" -- cần cho _trace_branching biết hướng di chuyển
            # ngay từ bước đầu, kể cả khi 1 sorter/router nằm SÁT nguồn
            # (không có belt ở giữa). Thiếu cái này, gặp sorter ngay ô đầu
            # tiên sẽ không tính được dir_in, bị coi nhầm thành điểm dừng
            # (bug thật: sorter đặt sát drill, cả 2 nhánh ra 0, xem
            # NEXT_STEPS.md).
            dx, dy = DIRECTIONS[b.rotation]
            synthetic_came_from = (ox - dx, oy - dy)
            for dest, cap in _trace_branching(
                grid, (ox, oy), float("inf"), "belt", item_name=produced_item(b), came_from=synthetic_came_from
            ):
                if dest is not b:
                    connections.append((b, dest, cap))
    return connections


def find_liquid_connections(grid: Grid):
    """Same as find_connections but sources are pumps (the only liquid
    producer our model supports -- see generated_catalog.py SKIPPED for
    liquid-output factories like cryofluid-mixer, not modeled). Cũng chia
    nhánh qua router như find_connections (dùng chung _trace_branching)."""
    connections = []
    for b in grid.unique_buildings():
        if b.type.kind == "pump":
            ox, oy = b.output_tile()
            dx, dy = DIRECTIONS[b.rotation]
            synthetic_came_from = (ox - dx, oy - dy)
            for dest, cap in _trace_branching(grid, (ox, oy), float("inf"), "liquid-belt", came_from=synthetic_came_from):
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
    if b.type.kind == "unloader":
        return b.filter_item
    return None


def produced_liquid(b: PlacedBuilding):
    """What liquid a pump's output conduit carries. No factory in our
    catalog has a modeled liquid output (see generated_catalog.py SKIPPED),
    so pumps are the only liquid source."""
    if b.type.kind == "pump":
        return b.liquid_target
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


def _pump_output_rate(grid: Grid, b: PlacedBuilding):
    """Matches Pump.java: stats.add(Stat.output, 60*pumpAmount*size*size,...),
    but counts matching liquid tiles under the footprint like the drill
    formula does for ore, rather than assuming full size*size coverage
    (liquidMultiplier per tile, e.g. deep-water=1.5, not modeled -- treated
    as 1.0, see NEXT_STEPS.md)."""
    if b.liquid_target is None:
        return 0.0
    count = sum(
        1
        for x, y in b.footprint()
        if grid.in_bounds(x, y) and grid.tiles[y][x].liquid == b.liquid_target
    )
    return TICKS_PER_SECOND * b.type.pump_amount * count


def _unloader_output_rate(grid: Grid, b: PlacedBuilding):
    """Xấp xỉ Unloader.java/DirectionalUnloader.java: rút item từ 1 building
    lưu trữ (kind="storage") hoặc core liền kề phía SAU (hướng ngược
    `rotation`), đẩy ra phía trước ở `base_rate` = 60/speed. Cần
    `filter_item` (config Item) được đặt rõ -- không mô phỏng "rút bất kỳ
    thứ gì có trong kho" vì simulator này không track tồn kho thật (giả định
    kho luôn còn hàng khi có filter_item, xem NEXT_STEPS.md)."""
    if b.filter_item is None:
        return 0.0
    back_x, back_y = b.input_tile()
    if not grid.in_bounds(back_x, back_y):
        return 0.0
    source = grid.building_at(back_x, back_y)
    if source is None or source.type.kind not in ("storage", "core"):
        return 0.0
    return b.type.base_rate


def evaluate_layout(grid: Grid):
    """Compute steady-state material throughput reaching the core.

    Model: each building's output rate is a pure function of its incoming
    rate(s), computed via memoized recursion over the connection graph
    (drills/pumps are sources, core is the sink). Assumes no cycles. Items
    and liquids are two parallel networks (separate belt vs conduit tiles,
    separate connection graphs) that only meet at a factory's recipe.
    """
    connections = find_connections(grid)
    in_edges = defaultdict(list)   # building -> [(source, belt_capacity)]
    for src, dest, cap in connections:
        in_edges[dest].append((src, cap))
    # 1 nguồn có thể ra nhiều đích nếu qua router (xem _trace_branching) --
    # compute() được nhớ đệm (memoized) theo NGUỒN, không theo từng nhánh, nên
    # nếu không chia lại ở đây, mỗi đích sẽ tưởng nhầm mình nhận được TOÀN BỘ
    # sản lượng nguồn thay vì phần chia của mình -- vi phạm bảo toàn khối
    # lượng (sản lượng đích cộng lại có thể vượt sản lượng nguồn thật).
    branch_count = Counter(src for src, dest, cap in connections)

    liquid_connections = find_liquid_connections(grid)
    liquid_in_edges = defaultdict(list)
    for src, dest, cap in liquid_connections:
        liquid_in_edges[dest].append((src, cap))
    liquid_branch_count = Counter(src for src, dest, cap in liquid_connections)

    output_rate: dict[int, float] = {}
    liquid_output_rate: dict[int, float] = {}

    def compute_liquid(b: PlacedBuilding):
        key = id(b)
        if key in liquid_output_rate:
            return liquid_output_rate[key]
        rate = _pump_output_rate(grid, b) if b.type.kind == "pump" else 0.0
        liquid_output_rate[key] = rate
        return rate

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
        elif b.type.kind == "unloader":
            rate = _unloader_output_rate(grid, b)
        elif b.type.kind == "factory":
            recipe = b.type.recipe
            cycle_rate = 1.0 / recipe.craft_time
            for item_name, amount_per_cycle in recipe.inputs.items():
                available = sum(
                    min(compute(src, visiting) / branch_count[src], cap)
                    for src, cap in in_edges[b]
                    if produced_item(src) == item_name
                )
                cycle_rate = min(cycle_rate, available / amount_per_cycle)
            for liquid_name, amount_per_cycle in recipe.liquid_inputs.items():
                available = sum(
                    min(compute_liquid(src) / liquid_branch_count[src], cap)
                    for src, cap in liquid_in_edges[b]
                    if produced_liquid(src) == liquid_name
                )
                cycle_rate = min(cycle_rate, available / amount_per_cycle)
            rate = max(cycle_rate, 0.0) * recipe.output_amount
        elif b.type.kind == "core":
            rate = sum(min(compute(src, visiting) / branch_count[src], cap) for src, cap in in_edges[b])
        else:
            rate = 0.0

        visiting.discard(key)
        output_rate[key] = rate
        return rate

    buildings = grid.unique_buildings()
    for b in buildings:
        compute(b, set())
        compute_liquid(b)

    core = next((b for b in buildings if b.type.kind == "core"), None)
    score = output_rate.get(id(core), 0.0) if core else 0.0

    return {
        "score": score,
        "connections": connections,
        "liquid_connections": liquid_connections,
        "output_rate": {b: output_rate[id(b)] for b in buildings},
        "liquid_output_rate": {b: liquid_output_rate[id(b)] for b in buildings},
    }
