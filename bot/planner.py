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

from simulator.buildings import CATALOG, DIRECTIONS, ITEMS, LIQUIDS
from simulator.grid import Grid
from simulator.sim import evaluate_layout, produced_item, produced_liquid, trace_belt_path


def find_producer(grid: Grid, item_name: str):
    for b in grid.unique_buildings():
        if produced_item(b) == item_name:
            return b
    return None


def _nearest_tile(candidates, near):
    """candidates: list toạ độ (x,y). near=None -> trả về cái đầu tiên quét
    được (không có điểm tham chiếu thì không có "gần" để so). near=(x,y) ->
    trả về ứng viên gần nhất theo khoảng cách Manhattan."""
    if not candidates:
        return None
    if near is None:
        return candidates[0]
    nx, ny = near
    return min(candidates, key=lambda p: abs(p[0] - nx) + abs(p[1] - ny))


def _direction_of(from_pos, to_pos):
    """Hướng chủ đạo từ from_pos tới to_pos, theo trục lệch nhiều hơn (xem
    simulator.buildings.DIRECTIONS: 0=Đông,1=Nam,2=Tây,3=Bắc)."""
    dx = to_pos[0] - from_pos[0]
    dy = to_pos[1] - from_pos[1]
    if abs(dx) >= abs(dy):
        return 0 if dx > 0 else 2
    return 1 if dy > 0 else 3


def _select_tile(candidates, near, hint):
    """Chọn 1 ô trong `candidates` theo `hint` (xem bot/command_parser.py
    _find_location_hint) -- cho phép người dùng chỉ định RÕ mỏ nào trong số
    nhiều mỏ cùng loại (vd "4 mỏ quanh core, xây ở mỏ phía bắc"), thay vì
    chỉ luôn tự động chọn gần nhất."""
    if not candidates:
        return None
    if hint is None:
        return _nearest_tile(candidates, near)

    kind, value = hint
    if kind == "coord":
        hx, hy = value
        return min(candidates, key=lambda p: abs(p[0] - hx) + abs(p[1] - hy))
    if kind == "direction" and near is not None:
        filtered = [p for p in candidates if _direction_of(near, p) == value]
        return _nearest_tile(filtered, near)  # [] -> None, đúng ý "không có mỏ hướng đó"
    if kind == "index":
        ordered = sorted(candidates, key=lambda p: (abs(p[0] - near[0]) + abs(p[1] - near[1])) if near else (p[1], p[0]))
        if 1 <= value <= len(ordered):
            return ordered[value - 1]
        return None
    return _nearest_tile(candidates, near)


def find_unmined_ore(grid: Grid, item_name: str, near=None, hint=None):
    """Trước đây trả về ô ore ĐẦU TIÊN quét được (trên-trái xuống dưới-phải),
    không so khoảng cách -- bug thật: có 2 mỏ cùng loại, bot có thể chọn mỏ
    XA hơn hẳn chỉ vì toạ độ nhỏ hơn (xem NEXT_STEPS.md, test
    bot/scan_order_demo.py). Giờ nếu có `near` (thường là core), chọn mỏ gần
    `near` nhất; có thêm `hint` thì người dùng tự chỉ định mỏ nào (toạ độ/
    hướng/thứ tự) thay vì để bot tự chọn."""
    candidates = [
        (x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if grid.tiles[y][x].ore == item_name and grid.building_at(x, y) is None
    ]
    return _select_tile(candidates, near, hint)


def find_liquid_producer(grid: Grid, liquid_name: str):
    for b in grid.unique_buildings():
        if produced_liquid(b) == liquid_name:
            return b
    return None


def find_untapped_liquid(grid: Grid, liquid_name: str, near=None, hint=None):
    """Cùng sửa như find_unmined_ore -- xem docstring ở đó."""
    candidates = [
        (x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if grid.tiles[y][x].liquid == liquid_name and grid.building_at(x, y) is None
    ]
    return _select_tile(candidates, near, hint)


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


def featurize_drill_choice(building_type) -> dict:
    """Turns a candidate drill type into features for bot/scorer.py.

    Hai loại đặc trưng cùng lúc, có chủ đích:
    - drill_tier (liên tục): mặc định âm (bot/scorer.py DEFAULT_WEIGHTS) nên
      tier rẻ nhất thắng khi chưa có phản hồi.
    - drill_is_<tên> (categorical, riêng từng loại): khi có phản hồi ưu tiên
      1 tier CỤ THỂ, trọng số của riêng tên đó tăng lên -- nếu chỉ có
      drill_tier (liên tục), phản hồi lặp lại sẽ đẩy trọng số tier vọt qua
      0 và làm tier CAO NHẤT luôn thắng (không dừng đúng ở tier được chọn),
      vì 1 trọng số tuyến tính không học được "thích riêng tier giữa" -- đã
      test thấy đúng vậy (xem NEXT_STEPS.md) trước khi thêm phần categorical
      này."""
    return {
        "drill_tier": float(building_type.tier),
        f"drill_is_{building_type.name}": 1.0,
    }


def select_drill_type(ore_hardness: int, scorer=None):
    """Trước đây MỌI nơi hardcode CATALOG["mechanical-drill"] (tier=2) --
    bug thật: ore cứng hơn tier 2 (titanium=3, thorium=4, tungsten=5) khiến
    drill đặt ra không mine được gì (_drill_output_rate trả về 0 lặng lẽ,
    xem sim.py). Giờ luôn chọn trong số drill có tier đủ dùng
    (tier >= ore_hardness); mặc định (scorer=None) chọn tier RẺ NHẤT đủ
    dùng, giữ đúng hành vi cũ cho ore hardness thấp (than/đồng vẫn ra
    mechanical-drill). Có scorer thì xếp hạng theo trọng số học được."""
    candidates = [b for b in CATALOG.values() if b.kind == "drill" and b.tier >= ore_hardness]
    if not candidates:
        return None
    if scorer is not None:
        scored = [(scorer.score(featurize_drill_choice(b)), b) for b in candidates]
        return max(scored, key=lambda pair: pair[0])[1]
    return min(candidates, key=lambda b: b.tier)


def find_drill_spot(grid: Grid, ore_item: str, near, drill_type=None):
    """Like find_free_area, but also requires at least one footprint tile to
    actually hold the target ore (an empty spot alone isn't useful for a drill)."""
    if drill_type is None:
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


def find_pump_spot(grid: Grid, liquid_name: str, near):
    """Like find_drill_spot, but for the default auto-placed pump type
    (mechanical-pump -- cheapest tier, same convention as always
    auto-placing mechanical-drill for ore, not the "best" pump)."""
    pump_type = CATALOG["mechanical-pump"]
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(pump_type, x, y):
                    continue
                footprint = [(x + fx, y + fy) for fx in range(pump_type.size) for fy in range(pump_type.size)]
                if any(grid.in_bounds(fx, fy) and grid.tiles[fy][fx].liquid == liquid_name for fx, fy in footprint):
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

    if grid.building_at(*start) is not None:
        # Điểm xuất phát đã bị building/belt khác chiếm và KHÔNG chạm target
        # -- không thể route từ đây (không phải BFS không tìm được đường,
        # mà là điểm xuất phát tự nó đã chặn mất). Case điển hình: 1 nguồn
        # đã có sẵn 1 đường belt ra chỗ khác rồi (vd tới core), giờ muốn nối
        # THÊM 1 đường khác từ CÙNG nguồn đó tới đích mới -- cần
        # junction/router để chia nhánh, hiện chưa hỗ trợ (xem
        # NEXT_STEPS.md). Trả None để tái dùng thông báo lỗi "không tìm
        # được đường belt" đã có sẵn ở nơi gọi, không giả vờ tìm được rồi
        # crash khi đặt (bug thật đã gặp: "cannot place conveyor at (5,4)").
        return None

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


def _route(grid: Grid, actions: list, start_tile, target_footprint, belt_type, error_context: str):
    """Tìm đường (BFS, xem find_belt_path) rồi đặt belt/conduit dọc đường đó,
    ghi vào `actions`. Dùng chung cho input item, input liquid, và output
    (drill/factory -> core) -- pathfinding không quan tâm loại belt, chỉ
    khác type đặt xuống (conveyor cho item, conduit cho liquid)."""
    path = find_belt_path(grid, start_tile, target_footprint)
    if path is None:
        raise RuntimeError(error_context)
    for bx, by, rotation in path:
        grid.place(belt_type, bx, by, rotation=rotation)
        actions.append({"op": "place", "building": belt_type.name, "x": bx, "y": by, "rotation": rotation})
    return path


def _clear_belt_chain(grid: Grid, actions: list, start_tile):
    """Xoá 1 chuỗi belt liên tiếp bắt đầu từ start_tile (nếu có) -- dùng khi
    cần giải phóng output_tile() của 1 nguồn ĐÃ có belt dẫn đi nơi khác, để
    đặt router/sorter mới ngay tại đó (xem plan_split/plan_filter_split,
    _route_or_branch_from_producer). Không làm gì nếu start_tile trống hoặc
    là building khác không phải belt (an toàn, không xoá nhầm)."""
    x, y = start_tile
    while True:
        b = grid.building_at(x, y)
        if b is None or b.type.kind != "belt":
            break
        actions.append({"op": "remove", "x": x, "y": y})
        grid.remove(b)
        dx, dy = DIRECTIONS[b.rotation]
        x, y = x + dx, y + dy


def _route_or_branch_from_producer(grid: Grid, actions: list, producer, target_footprint, belt_type, error_context: str):
    """Nối từ 1 producer (drill/factory) ĐÃ CÓ trên map tới target_footprint.

    Producer mới đặt luôn có output_tile() còn trống -- route thẳng bằng
    _route() như cũ. Nhưng producer TÁI SỬ DỤNG (tìm thấy qua find_producer,
    vd 1 factory khác cũng cần "cát" và đã có sẵn drill cát) có thể ĐÃ có
    belt dẫn đi nơi khác rồi (vd drill cát trước đó tự nối thẳng về core) --
    trước đây _route() sẽ báo lỗi "không tìm được đường" ngay tại output_tile
    bị chiếm (bug/giới hạn đã ghi trong NEXT_STEPS.md mục "Vá 2 lỗ hổng"),
    dù về logic hoàn toàn hợp lệ: 1 nguồn phục vụ NHIỀU đích thì cần router,
    không phải lỗi.

    Sửa: nếu output_tile() bị belt chiếm, TRACE xem belt đó dẫn tới đâu, xoá
    chuỗi belt cũ, rồi dùng plan_split() (router thật, xem
    simulator/sim.py:_trace_branching) để chia lại cho CẢ đích cũ lẫn đích
    mới -- đúng cơ chế thật khi 1 nguồn cần nuôi >1 nơi."""
    out_tile = producer.output_tile()
    if grid.building_at(*out_tile) is None:
        _route(grid, actions, out_tile, target_footprint, belt_type, error_context)
        return

    if list(target_footprint) and out_tile in set(target_footprint):
        return  # output_tile của producer chạm thẳng target rồi, không cần gì thêm

    existing = trace_belt_path(grid, *out_tile)
    if existing is None or existing[0] is None:
        raise RuntimeError(error_context)
    existing_dest = existing[0]
    if set(existing_dest.footprint()) == set(target_footprint):
        return  # đã nối sẵn đúng đích này rồi (vd 2 factory cùng cần 1 item, gọi 2 lần)

    # plan_split() tự giải phóng output_tile() (xem _clear_belt_chain bên
    # trong đó) nên không cần xoá belt cũ ở đây -- chỉ cần gọi với CẢ đích cũ
    # (existing_dest, giữ nguyên kết nối trước đó) lẫn đích mới.
    actions.extend(plan_split(grid, producer, [existing_dest.footprint(), list(target_footprint)]))


def plan_split(grid: Grid, source, destinations: list) -> list:
    """Chia đầu ra của 1 nguồn (drill/factory đã đặt) thành nhiều nhánh,
    dùng router thật (xem simulator/sim.py:_trace_branching -- chia đều
    capacity cho N nhánh, khớp cơ chế round-robin thật của Router.java).

    Đây là cách ĐÚNG để 1 nguồn nuôi nhiều đích -- gọi _route() nhiều lần
    thẳng từ CÙNG 1 output_tile sẽ đụng nhau ngay từ ô đầu tiên (bug thật đã
    gặp: "cannot place conveyor at (5,4)", xem NEXT_STEPS.md).

    destinations: list các target_footprint (list toạ độ) cần nối tới. Hàm
    cấp thấp -- nhận sẵn footprint đích. Xem plan_split_command() cho lệnh
    cấp cao (action='split', chỉ cần tên building/"core", tự resolve/tự đặt
    mới nếu cần) -- đó là hàm được bot/llm_parser.py + bot/live_run.py gọi
    qua plan() dispatcher.
    """
    actions = []
    router_type = CATALOG["router"]
    out_tile = source.output_tile()
    # source có thể ĐÃ có belt dẫn đi nơi khác rồi (vd tự nối về core từ 1
    # lệnh build trước đó) -- giải phóng output_tile trước khi đặt router,
    # nếu không find_belt_path sẽ coi output_tile "đã chạm đích" (do đứng
    # sát router_spot) mà KHÔNG kiểm tra chỗ đó có bị chiếm hay không, dẫn
    # tới coi như đã nối xong trong khi belt cũ vẫn trỏ hướng khác (bug thật
    # gặp khi split 1 nguồn đã tồn tại, xem NEXT_STEPS.md).
    _clear_belt_chain(grid, actions, out_tile)

    router_spot = find_free_area(grid, router_type, near=out_tile)
    if router_spot is None:
        raise RuntimeError(f"không tìm được chỗ đặt router gần '{source.type.name}'")
    rx, ry = router_spot

    conveyor_type = CATALOG["conveyor"]
    _route(grid, actions, out_tile, [(rx, ry)], conveyor_type,
           f"không nối được '{source.type.name}' tới router")
    grid.place(router_type, rx, ry, rotation=0)
    actions.append({"op": "place", "building": "router", "x": rx, "y": ry, "rotation": 0})

    neighbor_tiles = [(rx + dx, ry + dy) for dx, dy in DIRECTIONS]
    used = set()
    for i, target_footprint in enumerate(destinations):
        target_set = set(target_footprint)
        # Router đã CHẠM THẲNG đích (đích nằm ngay ô kề router) -- không cần
        # đặt belt gì cả, item chuyển thẳng qua adjacency (đúng cơ chế thật:
        # simulator/sim.py:_trace_branching coi bất kỳ building nào kề router
        # là 1 nhánh hợp lệ, không cần belt ở giữa). Bug thật đã gặp: nếu
        # KHÔNG kiểm tra riêng case này, vòng lặp dưới sẽ skip ô đó vì
        # "đã bị chiếm" (chính là đích!) rồi báo lỗi "không tìm được đường",
        # dù về mặt luồng vật lý đã nối đúng từ trước.
        if any((rx + dx, ry + dy) in target_set for dx, dy in DIRECTIONS):
            continue
        placed = False
        for nx, ny in neighbor_tiles:
            if (nx, ny) in used or grid.building_at(nx, ny) is not None:
                continue
            path = find_belt_path(grid, (nx, ny), target_footprint)
            if path is None:
                continue
            for bx, by, rotation in path:
                grid.place(conveyor_type, bx, by, rotation=rotation)
                actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})
            used.add((nx, ny))
            placed = True
            break
        if not placed:
            raise RuntimeError(f"không tìm được đường belt từ router tới đích thứ {i + 1}")

    return actions


def plan_filter_split(grid: Grid, source, filter_item_name: str, match_footprint, other_footprint) -> list:
    """Đặt 1 sorter ngay sau đầu ra nguồn, lọc theo `filter_item_name`, rồi
    nối 'nhánh thẳng' (item khớp filter -- tiếp tục đúng hướng đang di
    chuyển) tới `match_footprint` và 'nhánh rẽ' (item không khớp, rẽ vuông
    góc) tới `other_footprint` -- khớp đúng cơ chế Sorter.java thật
    (Sorter.getTileTarget(): nearby(dir) nếu khớp, nearby(dir±1) nếu không,
    xem simulator/sim.py:_trace_branching).

    Khác plan_split (router, N nhánh không điều kiện, bạn tự chọn hướng nào
    đi đâu): sorter chỉ có ĐÚNG 2 nhánh cố định theo filter -- không tự
    chọn thẳng/rẽ đi đâu, item quyết định.

    Hàm cấp thấp -- nhận sẵn footprint đích. Xem plan_filter_split_command()
    cho lệnh cấp cao (action='filter_split'), gọi qua plan() dispatcher.
    """
    actions = []
    sorter_type = CATALOG["sorter"]
    out_tile = source.output_tile()
    # Cùng lý do với plan_split() -- xem comment ở đó. filter_split là lệnh
    # định nghĩa LẠI đích của source (giống plan_reroute), nên bỏ qua kết nối
    # cũ (nếu có) là đúng ý, không phải mất dữ liệu ngầm.
    _clear_belt_chain(grid, actions, out_tile)

    sorter_spot = find_free_area(grid, sorter_type, near=out_tile)
    if sorter_spot is None:
        raise RuntimeError(f"không tìm được chỗ đặt sorter gần '{source.type.name}'")
    sx, sy = sorter_spot

    conveyor_type = CATALOG["conveyor"]
    path_in = _route(grid, actions, out_tile, [(sx, sy)], conveyor_type,
                      f"không nối được '{source.type.name}' tới sorter")
    dir_in = path_in[-1][2] if path_in else source.rotation

    grid.place(sorter_type, sx, sy, rotation=0, filter_item=filter_item_name)
    actions.append({"op": "place", "building": "sorter", "x": sx, "y": sy, "rotation": 0})
    actions.append({"op": "configure", "x": sx, "y": sy, "value": filter_item_name})

    straight_tile = (sx + DIRECTIONS[dir_in][0], sy + DIRECTIONS[dir_in][1])
    _route(grid, actions, straight_tile, match_footprint, conveyor_type,
           f"không tìm được đường belt (nhánh thẳng, item khớp '{filter_item_name}') từ sorter tới đích")

    other_set = set(other_footprint)
    placed_side = False
    for d in ((dir_in + 1) % 4, (dir_in - 1) % 4):
        side_tile = (sx + DIRECTIONS[d][0], sy + DIRECTIONS[d][1])
        # Cùng lý do với plan_split() -- đích rẽ có thể nằm NGAY ô kề sorter
        # (chạm thẳng, không cần belt), khác hẳn "ô kề bị building KHÁC chiếm
        # mất, không route qua được". Kiểm tra riêng trước khi coi occupied =
        # không dùng được.
        if side_tile in other_set:
            placed_side = True
            break
        if grid.building_at(*side_tile) is not None:
            continue
        path = find_belt_path(grid, side_tile, other_footprint)
        if path is None:
            continue
        for bx, by, rotation in path:
            grid.place(conveyor_type, bx, by, rotation=rotation)
            actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})
        placed_side = True
        break
    if not placed_side:
        raise RuntimeError(f"không tìm được đường belt (nhánh rẽ, item khác '{filter_item_name}') từ sorter tới đích")

    return actions


def _resolve_split_destination(grid: Grid, actions: list, dest: dict, near, exclude_item=None, scorer=None, preferences: dict = None):
    """Quy đích của split/filter_split (xem plan_split_command bên dưới) về
    1 footprint cụ thể trên map:
      {"kind":"core"}                       -- core đã có sẵn trên map
      {"kind":"build","building":<tên>}     -- building loại đó, dùng lại
                                                nếu đã có trên map, không thì
                                                TỰ ĐẶT MỚI gần `near`

    Khi tự đặt mới 1 factory: tự nối luôn các input KHÁC của recipe (trừ
    `exclude_item`, thứ sẽ được nối bằng router/sorter ở nơi gọi) --
    vd lệnh "1 nguồn [than] tạo silicon" chỉ tự lo mỗi than qua nhánh split,
    còn cát (input còn lại của silicon-smelter) bot vẫn phải tự tìm nguồn
    có sẵn, giống hệt logic plan_build's factory branch (xem
    _find_or_build_factory_sources)."""
    kind = dest.get("kind")

    if kind == "core":
        core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
        if core is None:
            raise RuntimeError("map chưa có core -- không thể chọn đích 'core'")
        return core.footprint()

    if kind == "build":
        building_name = dest.get("building")
        building_type = CATALOG.get(building_name)
        if building_type is None:
            raise RuntimeError(f"'{building_name}' không phải tên building hợp lệ")

        existing = next((b for b in grid.unique_buildings() if b.type.name == building_name), None)
        if existing is not None:
            return existing.footprint()

        if building_type.kind != "factory":
            raise RuntimeError(
                f"'{building_name}' (kind='{building_type.kind}') không hợp lý làm đích split -- "
                "chỉ hỗ trợ tự đặt MỚI factory (drill/pump tự sản xuất, không 'nhận' input)"
            )

        spot = find_free_area(grid, building_type, near=near, preferences=preferences)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ đặt '{building_name}'")
        tx, ty = spot
        target = grid.place(building_type, tx, ty, rotation=0)
        actions.append({"op": "place", "building": building_name, "x": tx, "y": ty, "rotation": 0})

        core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
        core_pos = (core.x, core.y) if core is not None else None
        sources, liquid_sources = _find_or_build_factory_sources(
            grid, actions, building_type.recipe, core_pos, scorer=scorer, exclude_item=exclude_item,
        )
        target_footprint = target.footprint()
        conveyor_type = CATALOG["conveyor"]
        for item_name, producer in sources:
            _route_or_branch_from_producer(grid, actions, producer, target_footprint, conveyor_type,
                                            f"không tìm được đường belt từ nguồn '{item_name}' tới '{building_name}'")
        conduit_type = CATALOG["conduit"]
        for liquid_name, producer in liquid_sources:
            _route_or_branch_from_producer(grid, actions, producer, target_footprint, conduit_type,
                                            f"không tìm được đường ống từ nguồn '{liquid_name}' tới '{building_name}'")

        # Tự nối đầu RA (item factory tạo ra, vd silicon) về core -- thiếu
        # bước này là bug thật đã gặp: factory vẫn craft được (input đủ) vì
        # _find_or_build_factory_sources chỉ lo INPUT, nhưng output không đi
        # đâu cả (output_tile() bỏ trống), về mặt game thật sẽ chất đầy nội
        # bộ rồi ngừng craft do không ai lấy đi. Cùng loại bug (và cùng cách
        # vá bằng _connect_to_core) như plan_build's drill/factory branch đã
        # gặp trước đó, xem NEXT_STEPS.md.
        _connect_to_core(grid, actions, target, f"đã tự đặt '{building_name}' làm đích split")
        _ensure_powered(grid, actions, target, near=(tx, ty), scorer=scorer, preferences=preferences)
        return target_footprint

    raise RuntimeError(f"destination không hợp lệ: {dest}")


def plan_split_command(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    """Lệnh cấp cao từ bot/llm_parser.py (action='split'): chia đầu ra 1
    nguồn ĐÃ CÓ trên map thành N nhánh không điều kiện qua router (xem
    plan_split). command:
      {"action":"split","source":{"building":<tên>,"hint":<hint>|null},
       "destinations":[<dest>, <dest>, ...]}   (>= 2 đích, xem _resolve_split_destination)

    Đây là cầu nối giữa mô hình cấp thấp (plan_split nhận sẵn footprint) và
    lệnh chat cấp cao (chỉ có tên building/"core") -- tự resolve/tự đặt mới
    đích nếu cần, xem _resolve_split_destination."""
    source_spec = command.get("source") or {}
    source = resolve_target(grid, source_spec.get("building"), source_spec.get("hint"))
    item_name = produced_item(source)
    if item_name is None:
        raise RuntimeError(f"'{source.type.name}' không sản xuất item nào để chia nhánh (chỉ drill/factory mới có)")

    dest_specs = command.get("destinations") or []
    if len(dest_specs) < 2:
        raise ValueError("lệnh split cần ít nhất 2 đích (destinations)")

    actions = []
    near = source.output_tile()
    destinations = [
        _resolve_split_destination(grid, actions, dest, near, exclude_item=item_name, scorer=scorer, preferences=preferences)
        for dest in dest_specs
    ]
    actions.extend(plan_split(grid, source, destinations))
    return actions


def plan_filter_split_command(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    """Lệnh cấp cao (action='filter_split'): chia theo filter qua sorter
    (xem plan_filter_split). command:
      {"action":"filter_split","source":{"building":<tên>,"hint":<hint>|null},
       "filter_item":<tên item>,"match":<dest>,"other":<dest>}

    `match` = đích cho item KHỚP filter_item (đi thẳng), `other` = đích cho
    item KHÔNG khớp (rẽ) -- xem _resolve_split_destination cho dạng <dest>."""
    source_spec = command.get("source") or {}
    source = resolve_target(grid, source_spec.get("building"), source_spec.get("hint"))
    filter_item_name = command.get("filter_item")
    if filter_item_name is None:
        raise ValueError("lệnh filter_split cần 'filter_item' (item nào đi thẳng)")
    item_name = produced_item(source)

    actions = []
    near = source.output_tile()
    match_footprint = _resolve_split_destination(
        grid, actions, command.get("match") or {}, near, exclude_item=filter_item_name, scorer=scorer, preferences=preferences
    )
    other_footprint = _resolve_split_destination(
        grid, actions, command.get("other") or {}, near, exclude_item=item_name, scorer=scorer, preferences=preferences
    )
    actions.extend(plan_filter_split(grid, source, filter_item_name, match_footprint, other_footprint))
    return actions


def featurize_target_spot(grid: Grid, building_type, spot, sources, core_pos=None) -> dict:
    """Turns a candidate placement into numeric features for bot/scorer.py.
    Read-only: calls find_belt_path for length only, never places anything."""
    tx, ty = spot
    footprint = [(tx + fx, ty + fy) for fx in range(building_type.size) for fy in range(building_type.size)]

    total_belt_length = 0
    for _, producer in sources:
        path = find_belt_path(grid, producer.output_tile(), footprint)
        total_belt_length += len(path) if path is not None else 999  # unreachable: heavy penalty

    features = {"total_belt_length": float(total_belt_length)}
    if core_pos is not None:
        features["distance_to_core"] = float(abs(tx - core_pos[0]) + abs(ty - core_pos[1]))
    else:
        features["distance_to_core"] = 0.0
    return features


def _connect_to_core(grid: Grid, actions: list, source, error_prefix: str):
    """Tự nối belt từ đầu ra 1 building về core, nếu map có core -- dùng cho
    drill/factory (đều xuất item). KHÔNG dùng cho pump: liquid không phải
    thứ "giao thẳng về core" như item trong lối chơi thông thường."""
    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    if core is None:
        return
    _route(grid, actions, source.output_tile(), core.footprint(), CATALOG["conveyor"],
           f"{error_prefix} nhưng không tìm được đường belt nối tới core")


def _ensure_powered(grid: Grid, actions: list, building, near, scorer=None, preferences: dict = None):
    """Nếu `building` cần điện (power_input > 0, xem Blocks.java
    consumePower() -- laser-drill/blast-drill/silicon-smelter/multi-press...
    hầu hết factory thật đều cần) nhưng mạng điện hiện tại chưa đủ công suất
    (kiểm tra bằng evaluate_layout() thật, không đoán), tự đặt 1
    combustion-generator (đốt than -- flammability=1.0, cao nhất, lựa chọn
    mặc định rẻ nhất, giống cách bot luôn mặc định mechanical-drill/
    mechanical-pump cho input thường), tự nối than cho nó, và đặt 1
    power-node cạnh building để bắc cầu vào tầm (laserRange=6 ô) -- KHÔNG tự
    suy luận loại generator/lượng cần chính xác cho lưới điện phức tạp
    nhiều building, chỉ đủ cấp cho 1 building đơn lẻ vừa xây. Xem
    NEXT_STEPS.md mục mạng điện cho giới hạn đầy đủ."""
    if building.type.power_input <= 0:
        return

    result = evaluate_layout(grid)
    if result["power_satisfaction"].get(building, 0.0) >= 1.0 - 1e-6:
        return

    generator_type = CATALOG["combustion-generator"]
    gen_spot = find_free_area(grid, generator_type, near=near, preferences=preferences)
    if gen_spot is None:
        raise RuntimeError(f"'{building.type.name}' cần điện nhưng không tìm được chỗ đặt combustion-generator")
    gx, gy = gen_spot
    new_gen = grid.place(generator_type, gx, gy, rotation=0)
    actions.append({"op": "place", "building": "combustion-generator", "x": gx, "y": gy, "rotation": 0})

    # Luôn tự đặt drill than MỚI riêng cho generator, không tái dùng
    # find_producer(grid,"coal") -- nếu có -- vì drill than có sẵn trên map
    # rất có thể ĐANG là nguồn của chính lệnh split/build hiện tại (router
    # của nó đã dùng hết 4 ô kề cho các nhánh khác), tái dùng sẽ tranh chấp
    # chỗ trên cùng 1 router và gây lỗi "không tìm được đường" giả (bug thật
    # gặp khi test: source=drill than của lệnh split, generator lại cũng đi
    # xin nối vào ĐÚNG drill than đó). Đánh đổi: có thể dư 1 drill than nếu
    # đã có sẵn, chấp nhận được để tránh tranh chấp router phức tạp hơn.
    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    core_pos = (core.x, core.y) if core is not None else None
    ore_pos = find_unmined_ore(grid, "coal", near=core_pos)
    if ore_pos is None:
        raise RuntimeError(f"'{building.type.name}' cần điện (combustion-generator cần than làm nhiên liệu) nhưng không có mỏ than nào chưa khai thác trên map")
    drill_type = select_drill_type(ITEMS["coal"].hardness, scorer=scorer)
    drill_spot = find_drill_spot(grid, "coal", near=ore_pos, drill_type=drill_type)
    if drill_spot is None:
        raise RuntimeError("không tìm được chỗ đặt drill than cho combustion-generator")
    dx, dy = drill_spot
    actions.append({"op": "place", "building": drill_type.name, "x": dx, "y": dy, "rotation": 0, "ore_target": "coal"})
    coal_producer = grid.place(drill_type, dx, dy, rotation=0, ore_target="coal")

    _route(grid, actions, coal_producer.output_tile(), new_gen.footprint(), CATALOG["conveyor"],
           f"'{building.type.name}' cần điện nhưng không nối được than tới combustion-generator")

    node_type = CATALOG["power-node"]
    node_spot = find_free_area(grid, node_type, near=(building.x, building.y), preferences=preferences)
    if node_spot is not None:
        nx, ny = node_spot
        grid.place(node_type, nx, ny, rotation=0)
        actions.append({"op": "place", "building": "power-node", "x": nx, "y": ny, "rotation": 0})


def _find_or_build_factory_sources(grid: Grid, actions: list, recipe, core_pos, scorer=None, exclude_item=None, exclude_liquid=None):
    """Với mỗi item/liquid recipe cần: dùng producer có sẵn nếu có, không thì
    tự đặt drill/pump mới -- tách ra từ plan_build() để dùng chung được cho
    cả build factory bình thường LẪN khi 1 factory được dựng làm ĐÍCH của
    split/filter_split (xem plan_split_command bên dưới): nhánh split đã tự
    lo 1 input rồi (exclude_item/exclude_liquid), chỉ còn thiếu các input
    KHÁC của recipe -- vd "1 nguồn tạo silicon" (nhánh than) vẫn cần bot tự
    nối luôn cát (input còn lại của silicon-smelter) từ drill cát có sẵn.

    Trả về (sources, liquid_sources): list (item_name, producer_building) --
    building THẬT chứ không phải output_tile() sẵn, vì producer có sẵn có
    thể đã có belt dẫn đi nơi khác rồi (vd core) -- xem
    _route_or_branch_from_producer(), cần building để trace/branch, không
    chỉ toạ độ."""
    sources = []
    liquid_sources = []

    for item_name in recipe.inputs:
        if item_name == exclude_item:
            continue
        producer = find_producer(grid, item_name)
        if producer is not None:
            sources.append((item_name, producer))
            continue

        ore_pos = find_unmined_ore(grid, item_name, near=core_pos)
        if ore_pos is None:
            raise RuntimeError(f"không có nguồn '{item_name}' nào (chưa có building sản xuất, cũng không có mỏ trên map)")

        item = ITEMS.get(item_name)
        drill_type = select_drill_type(item.hardness if item is not None else 0, scorer=scorer)
        if drill_type is None:
            raise RuntimeError(f"không có loại drill nào đủ mạnh để khai thác '{item_name}'")

        spot = find_drill_spot(grid, item_name, near=ore_pos, drill_type=drill_type)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ đặt drill cho '{item_name}'")
        dx, dy = spot
        actions.append({"op": "place", "building": drill_type.name, "x": dx, "y": dy, "rotation": 0, "ore_target": item_name})
        new_drill = grid.place(drill_type, dx, dy, rotation=0, ore_target=item_name)
        sources.append((item_name, new_drill))

    for liquid_name in recipe.liquid_inputs:
        if liquid_name == exclude_liquid:
            continue
        producer = find_liquid_producer(grid, liquid_name)
        if producer is not None:
            liquid_sources.append((liquid_name, producer))
            continue

        liquid_pos = find_untapped_liquid(grid, liquid_name, near=core_pos)
        if liquid_pos is None:
            raise RuntimeError(f"không có nguồn '{liquid_name}' nào (chưa có pump, cũng không có tile liquid trên map)")

        spot = find_pump_spot(grid, liquid_name, near=liquid_pos)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ đặt pump cho '{liquid_name}'")
        px, py = spot
        actions.append({"op": "place", "building": "mechanical-pump", "x": px, "y": py, "rotation": 0, "liquid_target": liquid_name})
        new_pump = grid.place(CATALOG["mechanical-pump"], px, py, rotation=0, liquid_target=liquid_name)
        liquid_sources.append((liquid_name, new_pump))

    return sources, liquid_sources


def plan_build(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    if command.get("action") != "build":
        raise ValueError(f"unsupported command: {command}")

    building_name = command["building"]

    if building_name == "drill":
        # Sentinel từ command_parser.py: người dùng không chỉ định tier cụ
        # thể ("máy khoan than" thay vì "pneumatic drill than") -- tự chọn
        # tier rẻ nhất đủ mạnh cho ore này (xem select_drill_type).
        ore_target = command.get("ore_target")
        if ore_target is None:
            raise ValueError("drill command needs an ore_target (e.g. 'khoan than')")
        item = ITEMS.get(ore_target)
        if item is None:
            raise ValueError(f"'{ore_target}' không phải tên item hợp lệ")
        building_type = select_drill_type(item.hardness, scorer=scorer)
        if building_type is None:
            raise RuntimeError(f"không có loại drill nào đủ mạnh để khai thác '{ore_target}' (hardness={item.hardness})")
        building_name = building_type.name
    else:
        building_type = CATALOG[building_name]

    actions = []
    # Điểm tham chiếu "gần" cho việc chọn mỏ/tile liquid -- core, nếu có
    # (xem find_unmined_ore/find_untapped_liquid: trước đây không có điểm
    # tham chiếu nào, luôn chọn ô quét ĐẦU TIÊN theo toạ độ (trên-trái) bất
    # kể xa gần thật, bug thật đã test bằng bot/scan_order_demo.py).
    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    core_pos = (core.x, core.y) if core is not None else None

    if building_type.category is not None:
        # Tới từ GENERATED_OTHER (tools/generate_catalog.py) -- chỉ có
        # tên+category, chưa có cơ chế/recipe. Từ chối rõ ràng thay vì đoán.
        # Xem NEXT_STEPS.md mục "Phạm vi chưa làm".
        raise ValueError(
            f"chưa hỗ trợ xây '{building_name}' (thuộc nhóm '{building_type.category}') -- "
            "planner hiện chỉ biết xây chuỗi tài nguyên (drill/pump/factory), xem NEXT_STEPS.md"
        )

    if building_type.kind == "drill":
        ore_target = command.get("ore_target")
        if ore_target is None:
            raise ValueError("drill command needs an ore_target (e.g. 'khoan than')")
        item = ITEMS.get(ore_target)
        if item is not None and building_type.tier < item.hardness:
            # Trước đây bug này ÂM THẦM đặt drill không mine được gì
            # (_drill_output_rate trả 0, không báo lỗi) -- giờ chặn ngay từ
            # lúc lập kế hoạch, không để lan xuống game thật.
            raise RuntimeError(
                f"'{building_name}' (tier {building_type.tier}) không đủ mạnh để khai thác "
                f"'{ore_target}' (cần tier >= {item.hardness}) -- chọn drill tier cao hơn"
            )
        ore_pos = find_unmined_ore(grid, ore_target, near=core_pos, hint=command.get("ore_location_hint"))
        if ore_pos is None:
            raise RuntimeError(f"không tìm thấy mỏ '{ore_target}' chưa khai thác trên map (hoặc không có mỏ nào khớp vị trí bạn chỉ định)")
        spot = find_drill_spot(grid, ore_target, near=ore_pos, drill_type=building_type)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ trống để đặt drill khai thác '{ore_target}'")
        x, y = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": 0, "ore_target": ore_target})
        new_drill = grid.place(building_type, x, y, rotation=0, ore_target=ore_target)
        _connect_to_core(grid, actions, new_drill, f"đã đặt drill '{ore_target}'")
        return actions

    if building_type.kind == "pump":
        liquid_target = command.get("liquid_target")
        if liquid_target is None:
            raise ValueError("pump command needs a liquid_target (e.g. 'bơm nước')")
        liquid_pos = find_untapped_liquid(grid, liquid_target, near=core_pos, hint=command.get("liquid_location_hint"))
        if liquid_pos is None:
            raise RuntimeError(f"không tìm thấy nguồn '{liquid_target}' chưa khai thác trên map (hoặc không có tile nào khớp vị trí bạn chỉ định)")
        spot = find_pump_spot(grid, liquid_target, near=liquid_pos)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ trống để đặt pump bơm '{liquid_target}'")
        x, y = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": 0, "liquid_target": liquid_target})
        grid.place(building_type, x, y, rotation=0, liquid_target=liquid_target)
        return actions

    if building_type.kind == "generator":
        # ConsumeGenerator.java thật: đốt BẤT KỲ item cháy được, không phải
        # input cố định như factory -- mặc định luôn dùng than (flammability
        # cao nhất, lựa chọn rẻ/phổ biến nhất, cùng tinh thần "máy khoan"
        # mặc định tier rẻ nhất khi không nói rõ). steam-generator còn cần
        # thêm nước (generator_liquid_inputs) -- tự đặt pump nếu recipe có.
        near = core_pos if core_pos is not None else (0, 0)
        gen_spot = find_free_area(grid, building_type, near=near, preferences=preferences)
        if gen_spot is None:
            raise RuntimeError(f"không tìm được chỗ trống để đặt '{building_name}'")
        gx, gy = gen_spot
        new_gen = grid.place(building_type, gx, gy, rotation=0)
        actions.append({"op": "place", "building": building_name, "x": gx, "y": gy, "rotation": 0})

        ore_pos = find_unmined_ore(grid, "coal", near=near)
        if ore_pos is None:
            raise RuntimeError(f"'{building_name}' cần than làm nhiên liệu nhưng không có mỏ than nào chưa khai thác trên map")
        drill_type = select_drill_type(ITEMS["coal"].hardness, scorer=scorer)
        drill_spot = find_drill_spot(grid, "coal", near=ore_pos, drill_type=drill_type)
        if drill_spot is None:
            raise RuntimeError(f"không tìm được chỗ đặt drill than cho '{building_name}'")
        dx, dy = drill_spot
        actions.append({"op": "place", "building": drill_type.name, "x": dx, "y": dy, "rotation": 0, "ore_target": "coal"})
        coal_producer = grid.place(drill_type, dx, dy, rotation=0, ore_target="coal")
        _route(grid, actions, coal_producer.output_tile(), new_gen.footprint(), CATALOG["conveyor"],
               f"'{building_name}' cần than nhưng không nối được đường belt")

        for liquid_name, amount_per_cycle in building_type.generator_liquid_inputs.items():
            liquid_pos = find_untapped_liquid(grid, liquid_name, near=near)
            if liquid_pos is None:
                raise RuntimeError(f"'{building_name}' cần '{liquid_name}' nhưng không có nguồn nào chưa khai thác trên map")
            pump_spot = find_pump_spot(grid, liquid_name, near=liquid_pos)
            if pump_spot is None:
                raise RuntimeError(f"không tìm được chỗ đặt pump bơm '{liquid_name}' cho '{building_name}'")
            px, py = pump_spot
            actions.append({"op": "place", "building": "mechanical-pump", "x": px, "y": py, "rotation": 0, "liquid_target": liquid_name})
            new_pump = grid.place(CATALOG["mechanical-pump"], px, py, rotation=0, liquid_target=liquid_name)
            _route(grid, actions, new_pump.output_tile(), new_gen.footprint(), CATALOG["conduit"],
                   f"'{building_name}' cần '{liquid_name}' nhưng không nối được đường ống")

        return actions

    if building_type.kind != "factory":
        raise ValueError(f"planner chỉ hỗ trợ xây drill/pump/factory/generator, không hỗ trợ '{building_type.kind}'")

    sources, liquid_sources = _find_or_build_factory_sources(
        grid, actions, building_type.recipe, core_pos, scorer=scorer
    )

    all_positions = [p.output_tile() for _, p in sources] + [p.output_tile() for _, p in liquid_sources]
    cx = sum(p[0] for p in all_positions) // len(all_positions)
    cy = sum(p[1] for p in all_positions) // len(all_positions)

    if scorer is not None:
        candidates = find_free_area_candidates(grid, building_type, near=(cx, cy), limit=5, preferences=preferences)
        if not candidates:
            raise RuntimeError(f"không tìm được chỗ trống để đặt '{building_name}'")
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
    new_factory = grid.place(building_type, tx, ty, rotation=0)
    actions.append({"op": "place", "building": building_name, "x": tx, "y": ty, "rotation": 0})
    target_footprint = [(tx + fx, ty + fy) for fx in range(building_type.size) for fy in range(building_type.size)]

    conveyor_type = CATALOG["conveyor"]
    for item_name, producer in sources:
        _route_or_branch_from_producer(grid, actions, producer, target_footprint, conveyor_type,
                                        f"không tìm được đường belt từ nguồn '{item_name}' tới '{building_name}'")

    conduit_type = CATALOG["conduit"]
    for liquid_name, producer in liquid_sources:
        _route_or_branch_from_producer(grid, actions, producer, target_footprint, conduit_type,
                                        f"không tìm được đường ống từ nguồn '{liquid_name}' tới '{building_name}'")

    # Tự nối belt đầu RA của factory về core, nếu map có core (xem mục "Vá
    # 2 lỗ hổng..." trong NEXT_STEPS.md).
    _connect_to_core(grid, actions, new_factory, f"đã xây '{building_name}'")

    # Tự cấp điện nếu factory cần (hầu hết factory thật đều cần, xem
    # _ensure_powered) -- không làm gì nếu power_input=0.
    _ensure_powered(grid, actions, new_factory, near=(tx, ty), scorer=scorer, preferences=preferences)

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

    building_name == "drill" là sentinel từ command_parser.py (người dùng
    nói "máy khoan" chung chung, không chỉ rõ tier) -- khớp MỌI tier drill
    trên map thay vì đòi tên literal "drill" (không building nào có tên đó).
    """
    if building_name == "drill":
        matches = [b for b in grid.unique_buildings() if b.type.kind == "drill"]
        display_name = "máy khoan"
    else:
        matches = [b for b in grid.unique_buildings() if b.type.name == building_name]
        display_name = building_name
    if not matches:
        raise RuntimeError(f"không tìm thấy building loại '{display_name}' nào trên map")

    if hint is not None:
        kind, value = hint
        if kind == "coord":
            hx, hy = value
            for b in matches:
                if (hx, hy) in b.footprint():
                    return b
            raise RuntimeError(f"không có building '{display_name}' nào ở toạ độ ({hx},{hy})")
        if kind == "index":
            matches.sort(key=lambda b: (b.y, b.x))
            if 1 <= value <= len(matches):
                return matches[value - 1]
            raise RuntimeError(f"chỉ có {len(matches)} building loại '{display_name}', không có cái thứ {value}")
        if kind == "ore_target":
            for b in matches:
                if b.ore_target == value:
                    return b
            raise RuntimeError(f"không có building '{display_name}' nào đang khai thác '{value}'")
        if kind == "liquid_target":
            for b in matches:
                if b.liquid_target == value:
                    return b
            raise RuntimeError(f"không có building '{display_name}' nào đang bơm '{value}'")

    if len(matches) == 1:
        return matches[0]

    listing = ", ".join(f"({b.x},{b.y})" for b in matches)
    raise RuntimeError(
        f"có {len(matches)} building loại '{display_name}' trên map: {listing} -- "
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
        # Trước đây chỉ emit action, KHÔNG cập nhật state cục bộ -- khác hẳn
        # plan_rotate (có set target.rotation) -- nghĩa là evaluate_layout
        # gọi ngay sau configure sẽ không biết filter vừa đổi. Sửa cho nhất
        # quán: cập nhật luôn PlacedBuilding.filter_item.
        target.filter_item = value
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
    if action == "split":
        return plan_split_command(grid, command, scorer=scorer, preferences=preferences)
    if action == "filter_split":
        return plan_filter_split_command(grid, command, scorer=scorer, preferences=preferences)
    raise ValueError(f"không hỗ trợ action '{action}'")
