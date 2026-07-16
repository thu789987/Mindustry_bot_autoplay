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
from simulator.grid import Grid, PlacedBuilding
from simulator.sim import SOURCE_KINDS, _power_linked, evaluate_layout, produced_item, produced_liquid, trace_belt_path


def find_producer(grid: Grid, item_name: str):
    for b in grid.unique_buildings():
        if produced_item(grid, b) == item_name:
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


def _touch_tiles_all_sides(building_type, x, y):
    """4 cạnh x size vị trí sát footprint (x,y) -- dùng chung bởi
    find_beam_drill_spot (BeamDrill quét CẢ 4 cạnh, xem sim.py
    _beam_drill_scan) và tương tự phần WallCrafter bên dưới."""
    s = building_type.size
    return (
        [(x + s, y + i) for i in range(s)] + [(x - 1, y + i) for i in range(s)]
        + [(x + i, y + s) for i in range(s)] + [(x + i, y - 1) for i in range(s)]
    )


def find_beam_drill_spot(grid: Grid, ore_item: str, near, beam_drill_type):
    """Như find_drill_spot, nhưng BeamDrill.java không đào theo diện tích
    chân đế mà bắn tia từ MỖI cạnh (xem sim.py _beam_drill_scan) -- chỗ đặt
    hợp lệ là bất kỳ vị trí nào có ore NGAY SÁT footprint (khoảng cách 1,
    luôn trong tầm beam_range của mọi beam-drill hiện có trong catalog nên
    không cần tính xa hơn -- xấp xỉ đơn giản hoá, chưa tận dụng hết tầm bắn
    xa của tia, xem NEXT_STEPS.md)."""
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(beam_drill_type, x, y):
                    continue
                touch = _touch_tiles_all_sides(beam_drill_type, x, y)
                if any(grid.in_bounds(tx, ty) and grid.tiles[ty][tx].ore == ore_item for tx, ty in touch):
                    return (x, y)
    return None


def find_unmined_attribute(grid: Grid, attribute_name: str, near=None, hint=None):
    """Như find_unmined_ore, nhưng cho Tile.attribute (WallCrafter.java, xem
    grid.py Tile.attribute + sim.py _wall_crafter_output_rate)."""
    candidates = [
        (x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if grid.tiles[y][x].attribute == attribute_name and grid.building_at(x, y) is None
    ]
    return _select_tile(candidates, near, hint)


def find_wall_crafter_spot(grid: Grid, attribute_name: str, near, wall_crafter_type):
    """Khác find_beam_drill_spot: WallCrafter.java CHỈ quét cạnh ĐANG XOAY
    MẶT TỚI (không phải cả 4 cạnh) -- phải tìm ĐÚNG rotation để cạnh đó chạm
    attribute tile, trả về (x, y, rotation) thay vì chỉ (x, y)."""
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    s = wall_crafter_type.size
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(wall_crafter_type, x, y):
                    continue
                for rotation, (ddx, ddy) in enumerate(DIRECTIONS):
                    if ddx == 1:
                        edge = [(x + s, y + i) for i in range(s)]
                    elif ddx == -1:
                        edge = [(x - 1, y + i) for i in range(s)]
                    elif ddy == 1:
                        edge = [(x + i, y + s) for i in range(s)]
                    else:
                        edge = [(x + i, y - 1) for i in range(s)]
                    if any(grid.in_bounds(ex, ey) and grid.tiles[ey][ex].attribute == attribute_name for ex, ey in edge):
                        return (x, y, rotation)
    return None


def find_solid_pump_spot(grid: Grid, attribute_name: str, near, solid_pump_type):
    """Như find_drill_spot, nhưng SolidPump.java (vd water-extractor) đọc
    Tile.attribute thay vì Tile.ore, và quét CẢ diện tích chân đế (khác
    find_wall_crafter_spot chỉ quét 1 cạnh) -- xem sim.py
    _solid_pump_output_rate."""
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if not grid.can_place(solid_pump_type, x, y):
                    continue
                footprint = [(x + fx, y + fy) for fx in range(solid_pump_type.size) for fy in range(solid_pump_type.size)]
                if any(grid.in_bounds(fx, fy) and grid.tiles[fy][fx].attribute == attribute_name for fx, fy in footprint):
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
            # Tile.buildable (grid.py) trước giờ KHÔNG building nào set False
            # nên chưa lộ ra -- BFS trước đây chỉ kiểm "có building chưa",
            # không kiểm buildable, khiến nó có thể tự tìm đường XUYÊN QUA ô
            # bị chặn (rồi grid.place() sau đó mới báo lỗi "cannot place").
            # Cần đúng cho cả 2 việc: (1) đất không xây được thật (vd nước),
            # (2) chặn tạm thời 1 vùng để ép BFS đi vòng (xem
            # plan_build_generator_cluster -- chặn margin quanh cụm double-
            # sided router để than không vô tình chạy sát hàng router khác,
            # tạo chu trình vô hạn trong đồ thị router).
            if not grid.tiles[nxt[1]][nxt[0]].buildable:
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


def _add_overflow_to_core(grid: Grid, actions: list, path: list, core):
    """Sau khi _route() nối xong producer -> consumer (vd drill than ->
    generator) bằng conveyor thường, "nâng cấp" Ô CUỐI (ô chạm thẳng
    consumer) thành overflow-gate, rồi thử rẽ thêm 1 nhánh từ cạnh VUÔNG
    GÓC của nó về core. User: "khi băng chuyền vào điện đầy thì tài nguyên
    tự động về core chứ không phải kẹt cứng" -- KHÔNG cần simulator mô
    phỏng đúng thời điểm "đầy" (xem NEXT_STEPS.md, overflow-gate trong
    simulator này là xấp xỉ TĨNH, luôn ưu tiên đường thẳng 100%) -- chỉ cần
    bot XÂY SẴN đường thoát dự phòng, đúng cách người chơi thật tránh belt
    bị nghẽn cứng khi consumer đã no trong game thật (không ảnh hưởng số
    liệu mô phỏng ở đây, chỉ thêm hạ tầng an toàn cho gameplay thật).

    KHÔNG BẮT BUỘC -- nếu path rỗng (producer đã chạm thẳng consumer, không
    có ô belt nào để nâng cấp) hoặc không tìm được chỗ rẽ/đường tới core,
    bỏ qua ÊM, không raise lỗi (producer vẫn nối consumer bình thường, chỉ
    thiếu phần an toàn dự phòng)."""
    if not path or core is None:
        return
    lx, ly, rotation = path[-1]
    gate_type = CATALOG["overflow-gate"]
    old = grid.building_at(lx, ly)
    if old is not None:
        grid.remove(old)
    if not grid.can_place(gate_type, lx, ly):
        # Không đặt lại được (hiếm, phòng hờ) -- khôi phục conveyor cũ, bỏ qua êm.
        if old is not None:
            grid.place(old.type, lx, ly, rotation=old.rotation)
        return
    grid.place(gate_type, lx, ly, rotation=rotation)
    actions.append({"op": "remove", "x": lx, "y": ly})
    actions.append({"op": "place", "building": "overflow-gate", "x": lx, "y": ly, "rotation": rotation})

    for side_dir in ((rotation + 1) % 4, (rotation - 1) % 4):
        sdx, sdy = DIRECTIONS[side_dir]
        side_tile = (lx + sdx, ly + sdy)
        if not grid.in_bounds(*side_tile) or grid.building_at(*side_tile) is not None:
            continue
        try:
            _route(grid, actions, side_tile, core.footprint(), CATALOG["conveyor"], "overflow tới core (bỏ qua)")
            return
        except RuntimeError:
            continue


def _clear_belt_chain(grid: Grid, actions: list, start_tile, belt_kind: str = "belt"):
    """Xoá 1 chuỗi belt liên tiếp bắt đầu từ start_tile (nếu có) -- dùng khi
    cần giải phóng output_tile() của 1 nguồn ĐÃ có belt dẫn đi nơi khác, để
    đặt router/sorter mới ngay tại đó (xem plan_split/plan_filter_split,
    _route_or_branch_from_producer). Không làm gì nếu start_tile trống hoặc
    là building khác không phải belt (an toàn, không xoá nhầm).

    belt_kind mặc định "belt" (conveyor, item) -- truyền "liquid-belt" khi
    xoá chuỗi conduit thay vì conveyor."""
    x, y = start_tile
    while True:
        b = grid.building_at(x, y)
        if b is None or b.type.kind != belt_kind:
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
    mới -- đúng cơ chế thật khi 1 nguồn cần nuôi >1 nơi.

    Bug thật phát hiện khi thêm liquid boost cho drill (_try_boost_with_water):
    trước đây hàm này LUÔN gọi trace_belt_path()/plan_split() KHÔNG truyền
    belt_kind, mặc định "belt" (conveyor) -- dùng cho liquid (belt_type=
    CATALOG["conduit"], kind="liquid-belt") sẽ trace SAI, dừng ngay ô conduit
    đầu tiên (coi nhầm nó là "đích"). Giờ suy ra belt_kind/router_type đúng
    từ chính belt_type truyền vào."""
    belt_kind = belt_type.kind
    router_type = CATALOG["liquid-router"] if belt_kind == "liquid-belt" else CATALOG["router"]

    out_tile = producer.output_tile()
    if grid.building_at(*out_tile) is None:
        _route(grid, actions, out_tile, target_footprint, belt_type, error_context)
        return

    if list(target_footprint) and out_tile in set(target_footprint):
        return  # output_tile của producer chạm thẳng target rồi, không cần gì thêm

    existing = trace_belt_path(grid, *out_tile, belt_kind=belt_kind)
    if existing is None or existing[0] is None:
        raise RuntimeError(error_context)
    existing_dest = existing[0]
    if set(existing_dest.footprint()) == set(target_footprint):
        return  # đã nối sẵn đúng đích này rồi (vd 2 factory cùng cần 1 item, gọi 2 lần)

    # plan_split() tự giải phóng output_tile() (xem _clear_belt_chain bên
    # trong đó) nên không cần xoá belt cũ ở đây -- chỉ cần gọi với CẢ đích cũ
    # (existing_dest, giữ nguyên kết nối trước đó) lẫn đích mới.
    actions.extend(plan_split(grid, producer, [existing_dest.footprint(), list(target_footprint)],
                               belt_type=belt_type, router_type=router_type))


def plan_split(grid: Grid, source, destinations: list, belt_type=None, router_type=None) -> list:
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

    belt_type/router_type: mặc định None -> conveyor/router (item, hành vi
    cũ giữ nguyên cho mọi call site có sẵn). Truyền CATALOG["conduit"]/
    CATALOG["liquid-router"] để chia nhánh LIQUID thay vì item (xem
    _route_or_branch_from_producer -- _trace_branching không phân biệt
    router/liquid-router khi chạy, cả 2 đều kind="router", chỉ khác tên
    hiển thị đúng loại building thật)."""
    belt_type = belt_type if belt_type is not None else CATALOG["conveyor"]
    router_type = router_type if router_type is not None else CATALOG["router"]
    belt_kind = belt_type.kind

    actions = []
    out_tile = source.output_tile()
    # source có thể ĐÃ có belt dẫn đi nơi khác rồi (vd tự nối về core từ 1
    # lệnh build trước đó) -- giải phóng output_tile trước khi đặt router,
    # nếu không find_belt_path sẽ coi output_tile "đã chạm đích" (do đứng
    # sát router_spot) mà KHÔNG kiểm tra chỗ đó có bị chiếm hay không, dẫn
    # tới coi như đã nối xong trong khi belt cũ vẫn trỏ hướng khác (bug thật
    # gặp khi split 1 nguồn đã tồn tại, xem NEXT_STEPS.md).
    _clear_belt_chain(grid, actions, out_tile, belt_kind=belt_kind)

    router_spot = find_free_area(grid, router_type, near=out_tile)
    if router_spot is None:
        raise RuntimeError(f"không tìm được chỗ đặt router gần '{source.type.name}'")
    rx, ry = router_spot

    _route(grid, actions, out_tile, [(rx, ry)], belt_type,
           f"không nối được '{source.type.name}' tới router")
    grid.place(router_type, rx, ry, rotation=0)
    actions.append({"op": "place", "building": router_type.name, "x": rx, "y": ry, "rotation": 0})

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
                grid.place(belt_type, bx, by, rotation=rotation)
                actions.append({"op": "place", "building": belt_type.name, "x": bx, "y": by, "rotation": rotation})
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
    item_name = produced_item(grid, source)
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
    item_name = produced_item(grid, source)

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


_BRANCHING_KINDS = ("router", "junction", "sorter", "overflow-gate", "bridge", "mass-driver")


def _source_feeds_tile(grid: Grid, source, tile, max_steps: int = 500) -> bool:
    """Đi theo chuỗi belt từ output_tile() của `source` (theo đúng rotation
    từng ô, giống item chảy trong game thật) xem có đi QUA `tile` không --
    dùng để biết producer nào ĐANG THỰC SỰ dùng đoạn belt sắp merge vào,
    thay vì cộng dồn rate của MỌI producer trên map (quá bảo thủ, chặn nhầm
    merge an toàn trên map có nhiều nhánh không liên quan tới nhau).

    Gặp router/junction/sorter/overflow-gate/bridge/mass-driver (rẽ nhánh,
    không đi thẳng 1 hướng cố định) -> coi như CÓ THỂ chạm `tile` (giả định
    an toàn hơn: thà tính dư rate còn hơn bỏ sót, tránh merge làm nghẽn belt
    thật)."""
    cur = source.output_tile()
    visited = set()
    for _ in range(max_steps):
        if cur == tile:
            return True
        if cur in visited:
            return False
        visited.add(cur)
        b = grid.building_at(*cur)
        if b is None or b is source:
            return False
        if b.type.kind in _BRANCHING_KINDS:
            return True
        if b.type.kind != "belt":
            return False
        dx, dy = DIRECTIONS[b.rotation]
        cur = (cur[0] + dx, cur[1] + dy)
    return False


def _try_merge_or_connect_to_core(grid: Grid, actions: list, source, error_prefix: str, force: bool = False):
    """Nối `source` (drill mới đặt) về core -- ƯU TIÊN nhập vào 1 đường belt
    ĐÃ CÓ SẴN (từ producer khác) nếu AN TOÀN, thay vì luôn tự đi 1 đường
    RIÊNG như _connect_to_core cũ.

    User: "chỉ nên nhập khi được yêu cầu hoặc số lượng item trên băng
    chuyền không bị quá nhiều" -- 2 điều kiện trigger merge (OR, không phải
    AND): `force=True` (lệnh nói rõ "nối chung"/"gộp chung" -- xem
    command_parser.py MERGE_PHRASES), HOẶC tổng rate (item/s) của source này
    CỘNG với rate của (các) producer khác ĐANG THỰC SỰ dùng đúng đoạn belt
    merge vào (xem _source_feeds_tile -- không phải mọi producer trên map)
    không vượt quá base_rate của conveyor (6.5 item/s thật, Conveyor.java)
    -- tránh nghẽn belt chỉ vì "gộp cho gọn". Không an toàn VÀ không force
    -> rơi về _connect_to_core cũ (đường riêng), KHÔNG đánh đổi throughput
    lấy việc "trông gọn".

    Best-effort: nếu không có belt nào sẵn trên map, hoặc không tìm được
    đường BFS chạm vào 1 belt sẵn có, rơi về _connect_to_core như cũ (không
    coi là lỗi -- merge chỉ là tối ưu thêm, không phải yêu cầu bắt buộc)."""
    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    if core is None:
        return

    existing_belts = [(b.x, b.y) for b in grid.unique_buildings() if b.type.kind == "belt"]
    if existing_belts:
        out_tile = source.output_tile()
        merge_path = find_belt_path(grid, out_tile, existing_belts)
        if merge_path == []:
            # find_belt_path coi "start đã CHẠM target" là không cần đặt gì
            # thêm -- đúng cho core/generator (building nhận thẳng từ ô kề,
            # xem NEXT_STEPS.md mục "touching placement"), nhưng SAI cho
            # belt: 1 ô conveyor CHỈ nhận item đặt THẲNG lên chính nó, không
            # "vói" sang ô trống kề bên (khác core -- core tự hút từ mọi ô
            # chạm chân đế). Nếu để trống, drill kẹt hàng, core không nhận
            # được gì (bug thật tự bắt được khi test: core output_rate chỉ
            # bằng đúng nguồn CŨ, nguồn MỚI biến mất khỏi find_connections dù
            # rate tính riêng > 0). Cần đặt THẬT 1 ô conveyor tại out_tile,
            # quay mặt về phía belt có sẵn.
            touch = next(
                (t for t in existing_belts
                 if t in {(out_tile[0] + dx, out_tile[1] + dy) for dx, dy in DIRECTIONS}),
                None,
            )
            if touch is not None and grid.building_at(*out_tile) is None and grid.can_place(CATALOG["conveyor"], *out_tile):
                rotation = DIRECTIONS.index((touch[0] - out_tile[0], touch[1] - out_tile[1]))
                merge_path = [(out_tile[0], out_tile[1], rotation)]
            else:
                merge_path = None
        if merge_path is not None:
            merge_tile = merge_path[-1][:2]
            touching = [t for t in existing_belts if t in {
                (merge_tile[0] + dx, merge_tile[1] + dy) for dx, dy in DIRECTIONS
            }]
            result = evaluate_layout(grid)
            own_rate = result["output_rate"].get(source, 0.0)
            other_rate = sum(
                result["output_rate"].get(b, 0.0)
                for b in grid.unique_buildings()
                if b is not source and b.type.kind in SOURCE_KINDS
                and any(_source_feeds_tile(grid, b, t) for t in touching)
            )
            safe = (own_rate + other_rate) <= CATALOG["conveyor"].base_rate
            if force or safe:
                for bx, by, rotation in merge_path:
                    grid.place(CATALOG["conveyor"], bx, by, rotation=rotation)
                    actions.append({"op": "place", "building": "conveyor", "x": bx, "y": by, "rotation": rotation})
                return

    _connect_to_core(grid, actions, source, error_prefix)


def _find_power_bridge_spot(grid: Grid, near, preferences: dict = None):
    """Tìm chỗ đặt power-node GẦN `near` mà khi đặt xong sẽ _power_linked
    (xem simulator/sim.py) tới ít nhất 1 building có điện ĐÃ CÓ SẴN trên map
    (generator hoặc power-node khác) -- ưu tiên NỐI VÀO mạng lưới điện có
    sẵn gần nhất, thay vì luôn tự xây generator mới dù đã có lưới điện gần
    đó (trước đây _ensure_powered() luôn xây mới bất kể, tốn kém và không
    giống cách người chơi thật hay làm -- xem NEXT_STEPS.md). Trả về (x,y)
    hoặc None nếu map chưa có building điện nào, hoặc không tìm được chỗ
    trong tầm bất kỳ cái nào."""
    node_type = CATALOG["power-node"]
    existing = [b for b in grid.unique_buildings() if b.type.kind in ("generator", "power-node")]
    if not existing:
        return None
    candidates = find_free_area_candidates(grid, node_type, near=near, limit=50, preferences=preferences)
    for x, y in candidates:
        # PlacedBuilding tạm (không grid.place() thật) chỉ để dùng
        # _power_linked() kiểm tầm -- tránh side-effect nếu candidate không
        # được chọn.
        probe = PlacedBuilding(node_type, x, y, rotation=0)
        if any(_power_linked(probe, other) for other in existing):
            return (x, y)
    return None


def _ensure_powered(grid: Grid, actions: list, building, near, scorer=None, preferences: dict = None):
    """Nếu `building` cần điện (power_input > 0, xem Blocks.java
    consumePower() -- laser-drill/blast-drill/silicon-smelter/multi-press...
    hầu hết factory thật đều cần) nhưng mạng điện hiện tại chưa đủ công suất
    (kiểm tra bằng evaluate_layout() thật, không đoán):

    1. TRƯỚC TIÊN thử nối vào mạng lưới điện GẦN NHẤT đã có sẵn (chỉ đặt 1
       power-node bắc cầu, xem _find_power_bridge_spot) -- rẻ hơn, giống
       cách người chơi thật hay làm hơn là luôn xây generator riêng cho
       từng building.
    2. Đo lại satisfaction SAU KHI bắc cầu -- nếu mạng đó đủ công suất rồi
       thì dừng ở đây, không xây gì thêm.
    3. Chỉ khi (1) không tìm được chỗ bắc cầu (map chưa có điện gần đó), HAY
       (2) bắc cầu xong vẫn thiếu công suất, mới tự đặt 1 combustion-
       generator MỚI (đốt than -- flammability=1.0, cao nhất, lựa chọn mặc
       định rẻ nhất) + tự nối than cho nó -- generator mới này CŨNG nằm
       trong tầm power-node vừa bắc cầu (nếu có) nên nối chung vào 1 mạng,
       không tách riêng.

    KHÔNG tự suy luận công suất cần chính xác cho lưới điện phức tạp nhiều
    building, chỉ đủ cấp cho 1 building đơn lẻ vừa xây. Xem NEXT_STEPS.md
    mục mạng điện cho giới hạn đầy đủ."""
    if building.type.power_input <= 0:
        return

    result = evaluate_layout(grid)
    if result["power_satisfaction"].get(building, 0.0) >= 1.0 - 1e-6:
        return

    bridged = False
    bridge_spot = _find_power_bridge_spot(grid, near=(building.x, building.y), preferences=preferences)
    if bridge_spot is not None:
        bx, by = bridge_spot
        grid.place(CATALOG["power-node"], bx, by, rotation=0)
        actions.append({"op": "place", "building": "power-node", "x": bx, "y": by, "rotation": 0})
        bridged = True

        result = evaluate_layout(grid)
        if result["power_satisfaction"].get(building, 0.0) >= 1.0 - 1e-6:
            return  # mạng lưới có sẵn đã đủ công suất, không cần xây generator mới

    generator_type = CATALOG["combustion-generator"]
    # Nếu đã bắc cầu ở bước trên nhưng chưa đủ công suất, tìm chỗ đặt
    # generator mới GẦN CHÍNH power-node vừa bắc cầu (không phải near gốc)
    # -- generator có khả năng cao chạm thẳng/trong tầm power-node đó, nối
    # chung vào CÙNG 1 mạng thay vì tách riêng.
    gen_near = bridge_spot if bridged else near
    gen_spot = find_free_area(grid, generator_type, near=gen_near, preferences=preferences)
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

    # KHÔNG gọi _add_overflow_to_core() ở đây -- _ensure_powered() được gọi
    # từ RẤT nhiều ngữ cảnh lồng nhau (drill/pump/factory/generator-cluster/
    # cả bên trong filter_split khi tự xây factory cần điện) -- verify thật
    # bằng debug script phát hiện: overflow-gate + nhánh về core thêm vào
    # đây có thể VÔ TÌNH chiếm đúng hướng mà 1 lệnh KHÁC (vd sorter của
    # filter_split) cần để tự nối riêng tới core, gây "không tìm được
    # đường" giả cho lệnh đó (bug thật gặp khi test: bot/split_command_demo.py,
    # bot/llm_split_demo.py fail sau khi thêm). An toàn hơn: chỉ thêm nhánh
    # dự phòng ở nhánh "generator" TRỰC TIẾP của plan_build() (lệnh "xây máy
    # phát điện" rõ ràng, ít lồng ghép hơn hẳn) -- xem NEXT_STEPS.md.
    _route(grid, actions, coal_producer.output_tile(), new_gen.footprint(), CATALOG["conveyor"],
           f"'{building.type.name}' cần điện nhưng không nối được than tới combustion-generator")

    if not bridged:
        # Chưa bắc cầu ở bước trên (map chưa có điện gần đó từ đầu) -- đặt 1
        # power-node cạnh building để bắc cầu tới generator MỚI vừa xây. Đã
        # bắc cầu rồi thì bỏ qua bước này (tránh đặt trùng 2 power-node gần
        # building -- generator mới đặt gần bridge_spot ở trên nên nhiều
        # khả năng đã chạm/trong tầm power-node đó rồi).
        node_type = CATALOG["power-node"]
        node_spot = find_free_area(grid, node_type, near=(building.x, building.y), preferences=preferences)
        if node_spot is not None:
            nx, ny = node_spot
            grid.place(node_type, nx, ny, rotation=0)
            actions.append({"op": "place", "building": "power-node", "x": nx, "y": ny, "rotation": 0})


def _find_touching_solid_pump_spot(grid: Grid, drill, attribute_name: str, solid_pump_type):
    """Tìm (x, y, rotation) đặt solid_pump_type SÁT 1 CẠNH của `drill` sao
    cho output_tile() của nó rơi ĐÚNG vào 1 ô trong footprint drill -- liquid
    chuyển thẳng qua adjacency (xem simulator/sim.py:_trace_branching, case
    fallthrough `return [(b, capacity)]` khi building đích không phải
    belt/router/... -- KHÔNG cần đặt conduit nào cả, giống hệt cách router
    "chạm thẳng đích" đã dùng ở phần item, xem plan_split()).

    Thử cả 4 cạnh (Đông/Tây/Nam/Bắc), mọi vị trí dọc cạnh đó mà pump vừa
    khít -- trả về vị trí ĐẦU TIÊN vừa đặt được (can_place) vừa có attribute
    dưới chân đế. Trả None nếu không cạnh nào có (map/địa hình không đủ
    attribute ngay sát drill -- caller nên lùi về near+conduit)."""
    ds = drill.type.size
    ps = solid_pump_type.size
    mid = ps // 2
    dx0, dy0 = drill.x, drill.y

    candidates = []
    for k in range(dy0 - mid, dy0 + ds - mid):
        candidates.append((dx0 + ds, k, 2))  # sát cạnh Đông, quay mặt Tây vào drill
        candidates.append((dx0 - ps, k, 0))  # sát cạnh Tây, quay mặt Đông vào drill
    for k in range(dx0 - mid, dx0 + ds - mid):
        candidates.append((k, dy0 + ds, 3))  # sát cạnh Nam, quay mặt Bắc vào drill
        candidates.append((k, dy0 - ps, 1))  # sát cạnh Bắc, quay mặt Nam vào drill

    drill_footprint = set(drill.footprint())
    for px, py, rotation in candidates:
        if not grid.can_place(solid_pump_type, px, py):
            continue
        footprint = [(px + fx, py + fy) for fx in range(ps) for fy in range(ps)]
        if not any(grid.in_bounds(fx, fy) and grid.tiles[fy][fx].attribute == attribute_name for fx, fy in footprint):
            continue
        probe = PlacedBuilding(solid_pump_type, px, py, rotation=rotation)
        if probe.output_tile() not in drill_footprint:
            continue  # phòng sai công thức _edge_tile -- double-check thật trước khi tin
        return (px, py, rotation)
    return None


def _try_boost_with_water(grid: Grid, actions: list, drill, preferences: dict = None):
    """Drill.java consumeLiquid(...).boost() -- KHÔNG BẮT BUỘC (khác
    power_input/_ensure_powered): không tìm được/không nối được nước thì bỏ
    qua ÊM, drill vẫn chạy đúng tốc độ nền (_drill_output_rate), KHÔNG raise
    lỗi nào -- khác hẳn _ensure_powered (bắt buộc, raise nếu không xây được).

    Thứ tự ưu tiên nguồn nước (đúng ý người dùng: "nguồn nước từ drill water
    HOẶC từ 1 đường ống"):
    1. Producer đã có SẴN trên map (water-extractor/mechanical-pump khác) --
       dùng _route_or_branch_from_producer() nên NHIỀU drill gọi hàm này lần
       lượt (vd lệnh "phủ kín mỏ") sẽ tự động NỐI CHUNG vào cùng 1 nguồn qua
       router, không mỗi drill tự xây 1 nguồn riêng -- đây là phần "tối ưu"
       được yêu cầu.
    2. Tile liquid THẬT chưa khai thác gần drill -- xây mechanical-pump mới.
    3. Không có tile liquid thật -- thử water-extractor (SolidPump, đọc
       Tile.attribute) nếu catalog có loại solid-pump nào sinh đúng liquid
       này (hiện chỉ water-extractor -> "water").
    4. Không có gì cả -- bỏ qua, drill vẫn hoạt động ở tốc độ nền."""
    liquid_name = drill.type.boost_liquid
    if liquid_name is None:
        return

    footprint = drill.footprint()
    near = (drill.x, drill.y)

    producer = find_liquid_producer(grid, liquid_name)
    if producer is not None:
        try:
            _route_or_branch_from_producer(grid, actions, producer, footprint, CATALOG["conduit"], "boost nước (bỏ qua)")
        except RuntimeError:
            pass
        return

    liquid_pos = find_untapped_liquid(grid, liquid_name, near=near)
    if liquid_pos is not None:
        spot = find_pump_spot(grid, liquid_name, near=liquid_pos)
        if spot is not None:
            px, py = spot
            new_pump = grid.place(CATALOG["mechanical-pump"], px, py, rotation=0, liquid_target=liquid_name)
            actions.append({"op": "place", "building": "mechanical-pump", "x": px, "y": py, "rotation": 0, "liquid_target": liquid_name})
            try:
                _route(grid, actions, new_pump.output_tile(), footprint, CATALOG["conduit"], "boost nước (bỏ qua)")
            except RuntimeError:
                pass
            return

    solid_pump_type = next(
        (bt for bt in CATALOG.values() if bt.kind == "solid-pump" and bt.solid_pump_liquid == liquid_name), None
    )
    if solid_pump_type is None:
        return

    # Ưu tiên đặt SÁT drill (chạm thẳng, không cần conduit) trước -- đúng ý
    # người dùng: "thường water drill sẽ đặt sát bên máy drill để khỏi đặt
    # ống nước hay gì hết". Chỉ lùi về near+conduit nếu không cạnh nào của
    # drill có đủ attribute (địa hình không cho phép đặt sát).
    touching = _find_touching_solid_pump_spot(grid, drill, solid_pump_type.solid_pump_attribute, solid_pump_type)
    if touching is not None:
        px, py, rotation = touching
        new_pump = grid.place(solid_pump_type, px, py, rotation=rotation)
        actions.append({"op": "place", "building": solid_pump_type.name, "x": px, "y": py, "rotation": rotation})
        try:
            _ensure_powered(grid, actions, new_pump, near=(px, py), preferences=preferences)
        except RuntimeError:
            pass
        return

    attr_pos = find_unmined_attribute(grid, solid_pump_type.solid_pump_attribute, near=near)
    if attr_pos is None:
        return
    spot = find_solid_pump_spot(grid, solid_pump_type.solid_pump_attribute, near=attr_pos, solid_pump_type=solid_pump_type)
    if spot is None:
        return
    px, py = spot
    new_pump = grid.place(solid_pump_type, px, py, rotation=0)
    actions.append({"op": "place", "building": solid_pump_type.name, "x": px, "y": py, "rotation": 0})
    try:
        _ensure_powered(grid, actions, new_pump, near=(px, py), preferences=preferences)
        _route(grid, actions, new_pump.output_tile(), footprint, CATALOG["conduit"], "boost nước (bỏ qua)")
    except RuntimeError:
        pass


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


def _build_drill_row_manifold(grid: Grid, actions: list, building_type, ore_target: str, min_x: int, max_x: int, row_y: int, lane_dir: int):
    """Đặt 1 HÀNG drill dọc theo x (từ min_x tới max_x tại row_y), tất cả
    quay mặt (rotation=1, xuống Nam) đổ thẳng vào 1 LANE (đường conveyor
    duy nhất) ngay bên dưới -- giống cách người chơi thật xếp hàng drill
    cạnh 1 belt chạy dọc, thay vì mỗi drill tự đi riêng 1 đường (xem
    NEXT_STEPS.md "manifold"). Trả về list PlacedBuilding đã đặt (rỗng nếu
    hàng này không đặt được drill nào -- vd không có ore, hoặc vướng hết).

    Không tự gọi _ensure_powered/_try_boost_with_water/nối lane về core --
    caller (plan_fill_ore) lo phần đó SAU KHI biết chắc hàng có drill."""
    s = building_type.size
    placed = []
    x = min_x
    while x <= max_x:
        if grid.can_place(building_type, x, row_y):
            footprint = [(x + fx, row_y + fy) for fx in range(s) for fy in range(s)]
            if any(grid.in_bounds(fx, fy) and grid.tiles[fy][fx].ore == ore_target for fx, fy in footprint):
                actions.append({"op": "place", "building": building_type.name, "x": x, "y": row_y, "rotation": 1, "ore_target": ore_target})
                new_drill = grid.place(building_type, x, row_y, rotation=1, ore_target=ore_target)
                placed.append(new_drill)
                x += s
                continue
        # Ô này không đặt được (đã có building, hoặc không chạm ore) --
        # dò từng ô 1 thay vì nhảy hẳn `s`, để không bỏ sót chỗ đặt được
        # nếu mỏ không đều/có vật cản xen giữa.
        x += 1
    if not placed:
        return []

    lane_y = row_y + s
    landing_xs = [d.output_tile()[0] for d in placed]
    lane_x_start, lane_x_end = min(landing_xs), max(landing_xs)
    for lx in range(lane_x_start, lane_x_end + 1):
        if grid.building_at(lx, lane_y) is None:
            grid.place(CATALOG["conveyor"], lx, lane_y, rotation=lane_dir)
            actions.append({"op": "place", "building": "conveyor", "x": lx, "y": lane_y, "rotation": lane_dir})
    return placed


def plan_fill_ore(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    """"Phủ kín mỏ": lệnh build thường (plan_build nhánh "drill") chỉ đặt
    ĐÚNG 1 drill dù mỏ to cỡ nào -- lệnh này quét TOÀN BỘ ô ore cùng loại
    trên map, xếp drill thành từng HÀNG dọc theo mỏ, mỗi hàng dùng CHUNG 1
    đường conveyor (manifold, xem _build_drill_row_manifold) thay vì mỗi
    drill tự đi riêng 1 đường về core -- bug thật user tự phát hiện qua hỏi
    "đặt full mỏ xong rồi nối băng chuyền với nhau ... chỉ có 1 băng chuyền
    về core không": phiên bản trước đó (find_drill_spot + _connect_to_core
    lặp lại) mỗi drill BFS 1 đường ĐỘC LẬP, ra N đường belt chồng chéo thay
    vì 1 đường gom chung -- đã verify thật bằng debug script trước khi sửa:
    4 drill ra 86 conveyor (per-drill BFS né hết mọi thứ), thay bằng
    manifold ra 3 drill chỉ 18 conveyor cho cùng 1 mỏ tương tự.

    Nhiều drill cần boost nước (_try_boost_with_water) vẫn tự động DÙNG
    CHUNG 1 nguồn nước duy nhất như trước (không đổi cơ chế đó, xem
    _route_or_branch_from_producer)."""
    building_name = command["building"]
    ore_target = command.get("ore_target")
    if ore_target is None:
        raise ValueError("fill command needs an ore_target (e.g. 'phủ kín mỏ than')")
    item = ITEMS.get(ore_target)
    if item is None:
        raise ValueError(f"'{ore_target}' không phải tên item hợp lệ")

    if building_name == "drill":
        building_type = select_drill_type(item.hardness, scorer=scorer)
        if building_type is None:
            raise RuntimeError(f"không có loại drill nào đủ mạnh để khai thác '{ore_target}' (hardness={item.hardness})")
    else:
        building_type = CATALOG[building_name]
        if building_type.tier < item.hardness:
            raise RuntimeError(
                f"'{building_name}' (tier {building_type.tier}) không đủ mạnh để khai thác "
                f"'{ore_target}' (cần tier >= {item.hardness}) -- chọn drill tier cao hơn"
            )

    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    if core is None:
        raise RuntimeError("map chưa có core, không biết nối belt về đâu")

    # Bounding box của MỌI ô ore cùng loại trên map -- đơn giản hoá: coi
    # chung là 1 "mỏ", không phân biệt nhiều mỏ rời rạc cùng loại item (nếu
    # có, bounding box sẽ trùm cả khoảng trống giữa chúng, tốn công quét
    # thừa nhưng không sai -- xem Giới hạn trong NEXT_STEPS.md). KHÔNG dùng
    # `ore_location_hint` ở đây (khác plan_build thường) vì mục đích là phủ
    # HẾT mỏ, không phải chọn 1 mỏ cụ thể trong nhiều mỏ.
    ore_tiles = [
        (x, y) for y in range(grid.height) for x in range(grid.width)
        if grid.tiles[y][x].ore == ore_target
    ]
    if not ore_tiles:
        raise RuntimeError(f"không tìm thấy mỏ '{ore_target}' nào trên map")
    min_x = min(x for x, y in ore_tiles)
    max_x = max(x for x, y in ore_tiles)
    min_y = min(y for x, y in ore_tiles)
    max_y = max(y for x, y in ore_tiles)

    # Lane chảy về hướng core gần hơn (Tây nếu core ở bên trái trung tâm mỏ,
    # ngược lại thì Đông) -- không đảm bảo tối ưu tuyệt đối, chỉ tránh
    # trường hợp tệ nhất (lane chảy ngược hẳn hướng core).
    ore_center_x = (min_x + max_x) / 2
    lane_dir = 2 if core.x < ore_center_x else 0  # 2=Tây, 0=Đông (xem DIRECTIONS)

    s = building_type.size
    actions = []
    total_placed = 0
    # Hàng SAU không luôn BFS thẳng về core -- nếu có lane của hàng TRƯỚC đó
    # ở gần hơn, nối THẲNG vào lane đó (item tiếp tục chảy theo hướng của
    # lane cũ, cuối cùng vẫn ra core, không cần đường riêng). Không làm vậy,
    # hàng sau dễ phải đi VÒNG QUANH cả khối hạ tầng hàng trước (đã đo thật:
    # 4 drill 2 hàng độc lập ra 106 conveyor, TỆ HƠN cả cách cũ mỗi drill tự
    # đi riêng -- xem NEXT_STEPS.md).
    existing_lane_tiles: list = []
    y = min_y
    while y <= max_y:
        row_drills = _build_drill_row_manifold(grid, actions, building_type, ore_target, min_x, max_x, y, lane_dir)
        if row_drills:
            lane_y = y + s
            landing_xs = [d.output_tile()[0] for d in row_drills]
            lane_x_start, lane_x_end = min(landing_xs), max(landing_xs)
            row_lane_tiles = [(lx, lane_y) for lx in range(lane_x_start, lane_x_end + 1)]
            dx_flow, _ = DIRECTIONS[lane_dir]
            end_x = lane_x_start if lane_dir == 2 else lane_x_end
            merge_targets = core.footprint() + existing_lane_tiles
            path = _route(grid, actions, (end_x + dx_flow, lane_y), merge_targets, CATALOG["conveyor"],
                           f"đã đặt {len(row_drills)} drill '{ore_target}' (hàng y={y}) nhưng không nối được lane về core")
            existing_lane_tiles.extend(row_lane_tiles)
            existing_lane_tiles.extend((bx, by) for bx, by, rotation in path)
            for d in row_drills:
                _ensure_powered(grid, actions, d, near=(d.x, d.y), scorer=scorer, preferences=preferences)
                _try_boost_with_water(grid, actions, d, preferences=preferences)
            total_placed += len(row_drills)
        # Nhảy qua cả chân đế drill (s hàng) LẪN hàng lane vừa đặt (1 hàng)
        # trước khi thử hàng tiếp theo -- nếu không, vòng lặp sau sẽ tự đụng
        # ngay lane vừa đặt (coi là "vướng", không sai nhưng lãng phí 1 lượt
        # quét).
        y += s + 1

    if total_placed == 0:
        raise RuntimeError(f"không tìm được chỗ đặt drill nào cho mỏ '{ore_target}' (mỏ quá nhỏ/vướng hết)")

    return actions


def _generator_cluster_layout(count: int, width: int) -> list:
    """Chia N generator thành các hàng rộng tối đa `width` (hàng cuối có thể
    ít hơn) -- trả về list số lượng generator mỗi hàng."""
    layout = []
    remaining = count
    while remaining > 0:
        row_count = min(width, remaining)
        layout.append(row_count)
        remaining -= row_count
    return layout


def _generator_cluster_fits(grid: Grid, building_type, router_type, row_counts: list, start_x: int, start_y: int, preferences: dict = None) -> bool:
    """Kiểm TOÀN BỘ lưới (mọi hàng generator + mọi hàng router + cột spine
    conn_x) đều đặt được, không vướng gì -- dùng cho
    _find_generator_cluster_spot()."""
    from bot.preferences import violates

    s = building_type.size
    width = max(row_counts)
    conn_x = start_x + width * s
    for i, row_count in enumerate(row_counts):
        gy = start_y + i * (s + 1)
        for j in range(row_count):
            gx = start_x + j * s
            if not grid.can_place(building_type, gx, gy):
                return False
            if preferences is not None and violates(grid, (gx, gy), preferences):
                return False
    router_rows = max(len(row_counts) - 1, 1)
    for k in range(router_rows):
        ry = start_y + k * (s + 1) + s
        for j in range(width):
            if not grid.can_place(router_type, start_x + j * s, ry):
                return False
        if not grid.can_place(router_type, conn_x, ry):
            return False
    return True


def _find_generator_cluster_spot(grid: Grid, building_type, router_type, row_counts: list, near, preferences: dict = None):
    """Quét vòng tròn mở rộng từ `near` tìm (x,y) góc trên-trái sao cho ĐỦ
    chỗ cho TOÀN BỘ lưới generator+router+spine -- trả None nếu không tìm
    được trong toàn map."""
    nx, ny = near
    max_radius = max(grid.width, grid.height)
    for radius in range(max_radius):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x, y = nx + dx, ny + dy
                if _generator_cluster_fits(grid, building_type, router_type, row_counts, x, y, preferences):
                    return (x, y)
    return None


def plan_build_generator_cluster(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    """"Xây N máy phát điện" -- xếp N generator thành LƯỚI nhiều hàng (rộng
    tối đa 6/hàng, giống schematic thật "Basic power plant V.1" user cung
    cấp), mỗi hàng router NẰM GIỮA 2 hàng generator liên tiếp CHẠM CẢ 2 BÊN
    cùng lúc (double-sided -- đúng thiết kế trong schematic thật, tiết kiệm
    hơn hẳn "1 router/generator"). Các hàng router nối với nhau qua 1 CỘT
    DỌC riêng (spine, tại conn_x, ngay bên phải hàng rộng nhất) -- than nạp
    vào ĐÚNG 1 điểm duy nhất ở đỉnh spine, tự chảy xuống nạp cho MỌI hàng.

    Bug thật phát hiện khi làm tính năng này (tự test bằng debug script,
    verify TRƯỚC khi merge): đường belt dẫn than (tìm bằng BFS tổng quát,
    _route()) có thể VÔ TÌNH chạy sát cạnh 1 hàng router KHÁC (không phải
    hàng nó định nối tới) -- router coi bất kỳ ô kề nào có building là hàng
    xóm hợp lệ (kể cả belt không liên quan), tạo thành CHU TRÌNH VÔ HẠN
    trong đồ thị tính throughput (RecursionError khi evaluate_layout()).
    Sửa 2 chỗ: (1) find_belt_path() (dùng chung toàn dự án) trước đây KHÔNG
    kiểm cờ Tile.buildable (chỉ kiểm có building hay chưa) -- giờ kiểm đúng,
    cho phép (2) hàm này CHẶN TẠM 1 vòng biên (margin) quanh toàn bộ cụm
    trước khi định tuyến than, chỉ chừa đúng 1 lỗ ở đỉnh spine -- ép BFS đi
    vòng ra ngoài thay vì có thể lách vào sát 1 hàng router bất kỳ, rồi mở
    lại buildable ngay sau khi đặt xong belt."""
    building_name = command["building"]
    building_type = CATALOG[building_name]
    count = command.get("count")
    if count is None or count < 1:
        raise ValueError("generator cluster command needs a count (e.g. 'xây 5 máy phát điện')")
    if building_type.generator_liquid_inputs:
        raise RuntimeError(
            f"'{building_name}' cần cả liquid ({list(building_type.generator_liquid_inputs)}) -- lệnh xây cụm "
            f"hiện CHỈ hỗ trợ generator thuần than (vd combustion-generator), chưa hỗ trợ steam-generator"
        )

    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    core_pos = (core.x, core.y) if core is not None else (0, 0)

    s = building_type.size
    router_type = CATALOG["router"]
    width = min(count, 6)  # mặc định giống schematic thật (6/hàng)
    row_counts = _generator_cluster_layout(count, width)

    spot = _find_generator_cluster_spot(grid, building_type, router_type, row_counts, near=core_pos, preferences=preferences)
    if spot is None:
        raise RuntimeError(f"không tìm được chỗ trống đủ rộng cho {count} '{building_name}'")
    start_x, start_y = spot
    conn_x = start_x + width * s

    actions = []
    for i, row_count in enumerate(row_counts):
        gy = start_y + i * (s + 1)
        for j in range(row_count):
            gx = start_x + j * s
            actions.append({"op": "place", "building": building_name, "x": gx, "y": gy, "rotation": 0})
            grid.place(building_type, gx, gy, rotation=0)

    router_rows = max(len(row_counts) - 1, 1)
    router_row_ys = []
    for k in range(router_rows):
        ry = start_y + k * (s + 1) + s
        router_row_ys.append(ry)
        for j in range(width):
            rx = start_x + j * s
            actions.append({"op": "place", "building": "router", "x": rx, "y": ry, "rotation": 0})
            grid.place(router_type, rx, ry, rotation=0)
        actions.append({"op": "place", "building": "router", "x": conn_x, "y": ry, "rotation": 0})
        grid.place(router_type, conn_x, ry, rotation=0)

    # Nối các hàng router với nhau qua cột spine (conveyor hướng Nam lấp
    # đầy khoảng trống giữa 2 hàng router liên tiếp).
    for k in range(len(router_row_ys) - 1):
        y_top, y_bot = router_row_ys[k], router_row_ys[k + 1]
        for gy in range(y_top + 1, y_bot):
            actions.append({"op": "place", "building": "conveyor", "x": conn_x, "y": gy, "rotation": 1})
            grid.place(CATALOG["conveyor"], conn_x, gy, rotation=1)

    # Chặn tạm 1 vòng biên quanh toàn bộ cụm (xem docstring: tránh belt than
    # vô tình chạm sát 1 hàng router khác, tạo chu trình vô hạn) -- chỉ
    # chừa đúng 1 lỗ ở đỉnh spine cho than đi vào.
    min_x, max_x = start_x - 1, conn_x + 1
    min_y, max_y = start_y - 1, router_row_ys[-1] + 1
    entry_x, entry_y = conn_x, min_y
    blocked = []
    for by in range(min_y, max_y + 1):
        for bx in range(min_x, max_x + 1):
            if by in (min_y, max_y) or bx in (min_x, max_x):
                if (bx, by) == (entry_x, entry_y):
                    continue
                if grid.in_bounds(bx, by) and grid.building_at(bx, by) is None:
                    grid.tiles[by][bx].buildable = False
                    blocked.append((bx, by))

    try:
        ore_pos = find_unmined_ore(grid, "coal", near=core_pos)
        if ore_pos is None:
            raise RuntimeError(f"'{building_name}' cần than nhưng không có mỏ than nào chưa khai thác trên map")
        drill_type = select_drill_type(ITEMS["coal"].hardness, scorer=scorer)
        drill_spot = find_drill_spot(grid, "coal", near=ore_pos, drill_type=drill_type)
        if drill_spot is None:
            raise RuntimeError("không tìm được chỗ đặt drill than cho cụm generator")
        dx, dy = drill_spot
        actions.append({"op": "place", "building": drill_type.name, "x": dx, "y": dy, "rotation": 0, "ore_target": "coal"})
        coal_drill = grid.place(drill_type, dx, dy, rotation=0, ore_target="coal")
        _route(grid, actions, coal_drill.output_tile(), [(conn_x, router_row_ys[0])], CATALOG["conveyor"],
               f"đã đặt {count} '{building_name}' nhưng không nối được than tới cụm")
    finally:
        for bx, by in blocked:
            grid.tiles[by][bx].buildable = True

    # 1 power-node chạm cụm để tap điện ra ngoài -- đúng ý schematic thật
    # ("dùng power-node này để nối các building khác cần điện").
    node_spot = find_free_area(grid, CATALOG["power-node"], near=(start_x, start_y), preferences=preferences)
    if node_spot is not None:
        nx, ny = node_spot
        grid.place(CATALOG["power-node"], nx, ny, rotation=0)
        actions.append({"op": "place", "building": "power-node", "x": nx, "y": ny, "rotation": 0})

    return actions


def plan_build(grid: Grid, command: dict, scorer=None, preferences: dict = None) -> list:
    if command.get("action") != "build":
        raise ValueError(f"unsupported command: {command}")

    if command.get("fill"):
        return plan_fill_ore(grid, command, scorer=scorer, preferences=preferences)

    if command.get("count") is not None:
        return plan_build_generator_cluster(grid, command, scorer=scorer, preferences=preferences)

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
        _ensure_powered(grid, actions, new_drill, near=(x, y), scorer=scorer, preferences=preferences)
        _try_boost_with_water(grid, actions, new_drill, preferences=preferences)
        _try_merge_or_connect_to_core(grid, actions, new_drill, f"đã đặt drill '{ore_target}'",
                                       force=command.get("merge", False))
        return actions

    if building_type.kind == "beam-drill":
        # BeamDrill (plasma-bore/large-plasma-bore) tự nhận diện item lúc
        # đánh giá (xem sim.py _beam_drill_target), KHÔNG gán ore_target lên
        # PlacedBuilding như drill thường -- ore_target ở đây chỉ dùng để
        # TÌM chỗ đặt (cần đứng sát đúng loại ore người dùng yêu cầu).
        ore_target = command.get("ore_target")
        if ore_target is None:
            raise ValueError("beam-drill command needs an ore_target (e.g. 'khoan plasma đồng')")
        item = ITEMS.get(ore_target)
        if item is not None and building_type.tier < item.hardness:
            raise RuntimeError(
                f"'{building_name}' (tier {building_type.tier}) không đủ mạnh để khai thác "
                f"'{ore_target}' (cần tier >= {item.hardness}) -- chọn beam-drill tier cao hơn"
            )
        ore_pos = find_unmined_ore(grid, ore_target, near=core_pos, hint=command.get("ore_location_hint"))
        if ore_pos is None:
            raise RuntimeError(f"không tìm thấy mỏ '{ore_target}' chưa khai thác trên map (hoặc không có mỏ nào khớp vị trí bạn chỉ định)")
        spot = find_beam_drill_spot(grid, ore_target, near=ore_pos, beam_drill_type=building_type)
        if spot is None:
            raise RuntimeError(f"không tìm được chỗ trống sát mỏ '{ore_target}' để đặt '{building_name}'")
        x, y = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": 0})
        new_beam_drill = grid.place(building_type, x, y, rotation=0)
        _ensure_powered(grid, actions, new_beam_drill, near=(x, y), scorer=scorer, preferences=preferences)
        _connect_to_core(grid, actions, new_beam_drill, f"đã đặt '{building_name}' khai thác '{ore_target}'")
        return actions

    if building_type.kind == "wall-crafter":
        # WallCrafter (cliff-crusher/large-cliff-crusher) luôn ra 1 item cố
        # định (wall_output, gắn liền wall_attribute) -- không cần người
        # dùng chỉ định ore_target như drill/beam-drill.
        if building_type.wall_attribute is None:
            raise RuntimeError(f"'{building_name}' thiếu wall_attribute (lỗi catalog, báo lại)")
        near = core_pos if core_pos is not None else (0, 0)
        attr_pos = find_unmined_attribute(grid, building_type.wall_attribute, near=near)
        if attr_pos is None:
            raise RuntimeError(
                f"không tìm thấy đá/tường mang attribute '{building_type.wall_attribute}' "
                f"trên map cho '{building_name}'"
            )
        spot = find_wall_crafter_spot(grid, building_type.wall_attribute, near=attr_pos, wall_crafter_type=building_type)
        if spot is None:
            raise RuntimeError(
                f"không tìm được chỗ trống sát attribute '{building_type.wall_attribute}' để đặt '{building_name}'"
            )
        x, y, rotation = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": rotation})
        new_crafter = grid.place(building_type, x, y, rotation=rotation)
        _ensure_powered(grid, actions, new_crafter, near=(x, y), scorer=scorer, preferences=preferences)
        _connect_to_core(grid, actions, new_crafter, f"đã đặt '{building_name}'")
        return actions

    if building_type.kind == "solid-pump":
        # SolidPump (water-extractor) luôn ra 1 liquid CỐ ĐỊNH
        # (solid_pump_liquid, gắn liền solid_pump_attribute) -- không cần
        # người dùng chỉ định liquid_target như pump thường, giống cách
        # wall-crafter không cần ore_target.
        if building_type.solid_pump_attribute is None:
            raise RuntimeError(f"'{building_name}' thiếu solid_pump_attribute (lỗi catalog, báo lại)")
        near = core_pos if core_pos is not None else (0, 0)
        attr_pos = find_unmined_attribute(grid, building_type.solid_pump_attribute, near=near)
        if attr_pos is None:
            raise RuntimeError(
                f"không tìm thấy nền đất mang attribute '{building_type.solid_pump_attribute}' "
                f"trên map cho '{building_name}'"
            )
        spot = find_solid_pump_spot(grid, building_type.solid_pump_attribute, near=attr_pos, solid_pump_type=building_type)
        if spot is None:
            raise RuntimeError(
                f"không tìm được chỗ trống sát attribute '{building_type.solid_pump_attribute}' để đặt '{building_name}'"
            )
        x, y = spot
        actions.append({"op": "place", "building": building_name, "x": x, "y": y, "rotation": 0})
        # KHÔNG gọi _connect_to_core -- liquid không "giao thẳng về core"
        # như item, giống hệt cách pump thường (kind="pump" bên dưới) cũng
        # chỉ đặt xuống, để lại việc nối tới nơi cần liquid (factory) cho
        # lệnh build tiếp theo tự tìm producer qua find_liquid_producer.
        new_solid_pump = grid.place(building_type, x, y, rotation=0)
        _ensure_powered(grid, actions, new_solid_pump, near=(x, y), scorer=scorer, preferences=preferences)
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
        new_pump = grid.place(building_type, x, y, rotation=0, liquid_target=liquid_target)
        # mechanical-pump (loại duy nhất chat command hiện đặt được) có
        # power_input=0 nên đây là no-op trong thực tế -- thêm để nhất
        # quán và không sai nếu sau này có tier pump khác cần điện thật
        # (vd impulse-pump/rotary-pump, xem generated_catalog.py).
        _ensure_powered(grid, actions, new_pump, near=(x, y), scorer=scorer, preferences=preferences)
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
        coal_path = _route(grid, actions, coal_producer.output_tile(), new_gen.footprint(), CATALOG["conveyor"],
               f"'{building_name}' cần than nhưng không nối được đường belt")
        _add_overflow_to_core(grid, actions, coal_path, core)

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
