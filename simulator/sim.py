from collections import Counter, defaultdict

from .buildings import DIRECTIONS, ITEMS, TICKS_PER_SECOND
from .grid import Grid, PlacedBuilding


def trace_belt_path(grid: Grid, x: int, y: int, belt_kind: str = "belt"):
    """Follow a chain of conveyor tiles starting at (x, y), each belt continuing
    in its own facing direction, until a non-belt building or a dead end is hit.

    `belt_kind` mặc định "belt" (conveyor -- giữ nguyên hành vi cũ cho mọi
    call site item hiện có). Truyền "liquid-belt" để trace CONDUIT thay vì
    conveyor (xem bot/planner.py:_route_or_branch_from_producer -- bug thật
    phát hiện khi thêm liquid boost cho drill: hàm này trước đây LUÔN
    hardcode "belt", khiến trace dừng SAI ngay tại ô conduit đầu tiên khi
    dùng cho liquid, vì conduit.kind="liquid-belt" != "belt").

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
        if b.type.kind != belt_kind:
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
            # SỬA: trước đây coi bridge chưa link là "điểm dừng hẳn" (kẹt tại
            # chỗ) -- SAI. ItemBridge.java thật (updateTile(), xem
            # NEXT_STEPS.md): khi hadValidLink=false, gọi doDump() -- hành vi
            # dump TIÊU CHUẨN ra Ô LIỀN KỀ vật lý, giống hệt mọi building
            # khác, KHÔNG bị kẹt. Xấp xỉ đúng bằng công thức y hệt router
            # (chia đều capacity cho các neighbor hợp lệ, không phải
            # round-robin theo thời gian thật như game, nhưng ở trạng thái ổn
            # định trung bình ra kết quả tương đương).
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


SOURCE_KINDS = ("drill", "factory", "unloader", "beam-drill", "wall-crafter")


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
                grid, (ox, oy), float("inf"), "belt", item_name=produced_item(grid, b), came_from=synthetic_came_from
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
        if b.type.kind in ("pump", "solid-pump"):
            ox, oy = b.output_tile()
            dx, dy = DIRECTIONS[b.rotation]
            synthetic_came_from = (ox - dx, oy - dy)
            for dest, cap in _trace_branching(grid, (ox, oy), float("inf"), "liquid-belt", came_from=synthetic_came_from):
                if dest is not b:
                    connections.append((b, dest, cap))
    return connections


def produced_item(grid: Grid, b: PlacedBuilding):
    """What item type a building's output belt carries -- needed so a
    multi-input factory can tell its incoming belts apart (e.g. coal vs
    sand feeding a silicon smelter) instead of summing unrelated items.
    Takes `grid` (not just `b`) because beam-drill auto-detects its item by
    scanning tiles, unlike a regular drill's pre-assigned `ore_target`."""
    if b.type.kind == "drill":
        return b.ore_target
    if b.type.kind == "beam-drill":
        return _beam_drill_target(grid, b)
    if b.type.kind == "wall-crafter":
        return b.type.wall_output
    if b.type.kind == "factory":
        return b.type.recipe.output_item
    if b.type.kind == "unloader":
        return b.filter_item
    return None


def produced_liquid(b: PlacedBuilding):
    """What liquid a pump's output conduit carries. No factory in our
    catalog has a modeled liquid output (see generated_catalog.py SKIPPED),
    so pumps/solid-pumps are the only liquid sources."""
    if b.type.kind == "pump":
        return b.liquid_target
    if b.type.kind == "solid-pump":
        return b.type.solid_pump_liquid
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


def _beam_drill_scan(grid: Grid, b: PlacedBuilding):
    """Xấp xỉ BeamDrill.java: bắn 1 tia dò ore từ MỖI vị trí dọc theo cả 4
    cạnh (không phải diện tích chân đế) -- size=1 (plasma-bore) có 4 tia,
    size=2 (large-plasma-bore) có 8 tia (2 tia/cạnh x 4 cạnh). Mỗi tia quét
    tối đa `beam_range` ô, dừng ở Ô ORE ĐẦU TIÊN gặp được.

    Đơn giản hoá đã ghi rõ: BeamDrill.java thật dừng ở "first SOLID tile"
    (tường/vách đá Erekir mang ore), simulator này không mô hình wall-ore
    riêng (chỉ có ore_tiles kiểu floor overlay Serpulo, xem grid.py) nên
    dùng luôn ore_tiles hiện có làm xấp xỉ mục tiêu tia bắn tới.

    Trả về list tên item (1 phần tử/tia có bắn trúng ore hợp lệ theo tier,
    tia không trúng gì hoặc ore quá cứng thì bỏ qua, không phải "0 item")."""
    s = b.type.size
    hits = []
    for direction, (dx, dy) in enumerate(DIRECTIONS):
        if dx == 1:
            starts = [(b.x + s, b.y + i) for i in range(s)]
        elif dx == -1:
            starts = [(b.x - 1, b.y + i) for i in range(s)]
        elif dy == 1:
            starts = [(b.x + i, b.y + s) for i in range(s)]
        else:
            starts = [(b.x + i, b.y - 1) for i in range(s)]

        for sx, sy in starts:
            x, y = sx, sy
            for _ in range(b.type.beam_range):
                if not grid.in_bounds(x, y):
                    break
                ore = grid.tiles[y][x].ore
                if ore is not None:
                    item = ITEMS.get(ore)
                    if item is not None and item.hardness <= b.type.tier:
                        hits.append(ore)
                    break  # dừng ở ore ĐẦU TIÊN gặp, dù có hợp tier hay không
                x, y = x + dx, y + dy
    return hits


def _beam_drill_target(grid: Grid, b: PlacedBuilding):
    """Item mà toàn bộ tia đang bắn trúng, hoặc None nếu 0 tia trúng hoặc
    trúng LẪN LỘN nhiều loại (BeamDrill.java: "khi có nhiều hơn 1 loại item,
    coi như không có item nào" -- toàn bộ building ngừng sản xuất, không
    phải lấy loại chiếm đa số)."""
    hits = _beam_drill_scan(grid, b)
    if not hits:
        return None
    distinct = set(hits)
    if len(distinct) > 1:
        return None
    return hits[0]


def _beam_drill_output_rate(grid: Grid, b: PlacedBuilding):
    """rate = facingAmount / drillTime (không có hardness_multiplier -- xem
    ghi chú beam_range trong buildings.py). facingAmount = số tia đang bắn
    trúng ĐÚNG loại item thống nhất."""
    item_name = _beam_drill_target(grid, b)
    if item_name is None:
        return 0.0
    facing_amount = _beam_drill_scan(grid, b).count(item_name)
    if b.type.drill_time <= 0:
        return 0.0
    return TICKS_PER_SECOND * facing_amount / b.type.drill_time


def _wall_crafter_output_rate(grid: Grid, b: PlacedBuilding):
    """Xấp xỉ WallCrafter.java (vd cliff-crusher/large-cliff-crusher): CHỈ
    quét dọc cạnh đang xoay mặt tới (KHÔNG phải 4 cạnh như BeamDrill), cộng
    dồn hiệu suất từ các ô đá/tường tự nhiên mang đúng `wall_attribute`
    (Tile.attribute, xem grid.py) -- game thật cộng dồn WEIGHT thực, ở đây
    đơn giản hoá +1.0/ô khớp (nhị phân, giống ore/liquid, xem README giới
    hạn). rate = (60/drill_time) * hiệu_suất, không có booster (item/liquid
    boost optional trong game thật, không model -- giống drill/pump khác)."""
    if b.type.wall_attribute is None or b.type.wall_output is None:
        return 0.0
    dx, dy = DIRECTIONS[b.rotation]
    s = b.type.size
    if dx == 1:
        checked = [(b.x + s, b.y + i) for i in range(s)]
    elif dx == -1:
        checked = [(b.x - 1, b.y + i) for i in range(s)]
    elif dy == 1:
        checked = [(b.x + i, b.y + s) for i in range(s)]
    else:
        checked = [(b.x + i, b.y - 1) for i in range(s)]

    efficiency = sum(
        1.0
        for x, y in checked
        if grid.in_bounds(x, y) and grid.tiles[y][x].attribute == b.type.wall_attribute
    )
    if efficiency <= 0 or b.type.drill_time <= 0:
        return 0.0
    return TICKS_PER_SECOND / b.type.drill_time * efficiency


def _solid_pump_output_rate(grid: Grid, b: PlacedBuilding):
    """Xấp xỉ SolidPump.java (vd water-extractor): công thức thật là
    `fraction = validTiles + boost + (attribute?.env() ?: 0)` (validTiles =
    số tile nền hợp lệ CHUNG, boost = tổng trọng số attribute thực trên các
    tile đó, attribute.env() = hằng số môi trường riêng loại attribute) --
    quá nhiều thành phần không rõ ràng đầy đủ từ source để model chính xác.
    Đơn giản hoá NHỊ PHÂN giống hệt _pump_output_rate/_drill_output_rate
    (đếm tile khớp, không phải trọng số thực): rate = 60 * pump_amount *
    số_tile_khớp_attribute_dưới_chân_đế. Bỏ qua hẳn phần "validTiles nền
    hợp lệ không cần khớp attribute" của công thức thật -- xem
    NEXT_STEPS.md."""
    if b.type.solid_pump_attribute is None:
        return 0.0
    count = sum(
        1
        for x, y in b.footprint()
        if grid.in_bounds(x, y) and grid.tiles[y][x].attribute == b.type.solid_pump_attribute
    )
    return TICKS_PER_SECOND * b.type.pump_amount * count


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


def _power_capable(b: PlacedBuilding) -> bool:
    """Building tham gia mạng điện: generator (sản xuất), power-node/
    beam-node (chỉ truyền, không tự sản xuất/tiêu thụ -- xem
    _generator_power_rate/_power_satisfaction, cả 2 đều không cộng dồn gì
    cho kind này), battery (lưu trữ, cũng không sản xuất/tiêu thụ ròng
    trong mô hình trung bình ổn định -- xem battery_capacity ở
    buildings.py), hoặc bất kỳ building nào cần điện (power_input > 0, vd
    laser-drill/blast-drill/silicon-smelter/impact-reactor thật -- xem
    Blocks.java consumePower())."""
    return b.type.kind in ("generator", "power-node", "beam-node", "battery") or b.type.power_input > 0


def _power_linked(a: PlacedBuilding, b: PlacedBuilding) -> bool:
    """Xấp xỉ PowerNode.overlaps(): 2 building có điện được nối KHÔNG DÂY nếu
    (1) chân đế chạm nhau trực tiếp (giống cách building thường "bắt tay"
    không cần belt ở giữa, xem output_tile()/touches_target), (2) 1 trong 2
    là power-node và building kia nằm trong bán kính `power_range` (số ô,
    xem PowerNode.java laserRange) tính từ tâm node -- dùng khoảng cách
    Euclidean gần đúng hình tròn thật, không phải hình chữ nhật/tia laser
    chính xác như game gốc, hoặc (3) 1 trong 2 là beam-node và building kia
    nằm THẲNG HÀNG (cùng x hoặc cùng y -- BeamNode.java chỉ nối đúng 4
    hướng Đông/Tây/Nam/Bắc, không phải toả tròn như power-node) trong tầm
    `power_range` (BeamNode.java field `range`, cùng đơn vị ô). Xấp xỉ:
    KHÔNG mô phỏng occlusion thật (BeamNode.java chỉ nối tới vật CHẮN GẦN
    NHẤT theo mỗi hướng, dừng lại nếu có building khác chắn giữa đường) --
    coi mọi cặp thẳng hàng trong tầm là nối được, có thể lạc quan hơn thật
    nếu có building khác chắn giữa 2 đầu (xem NEXT_STEPS.md)."""
    a_tiles = a.footprint()
    b_set = set(b.footprint())
    for ax, ay in a_tiles:
        for ddx, ddy in DIRECTIONS:
            if (ax + ddx, ay + ddy) in b_set:
                return True

    for node, other in ((a, b), (b, a)):
        if node.type.kind != "power-node":
            continue
        ncx = node.x + node.type.size / 2.0
        ncy = node.y + node.type.size / 2.0
        for ox, oy in other.footprint():
            dist = ((ox + 0.5 - ncx) ** 2 + (oy + 0.5 - ncy) ** 2) ** 0.5
            if dist <= node.type.power_range:
                return True

    for node, other in ((a, b), (b, a)):
        if node.type.kind != "beam-node":
            continue
        for nx, ny in node.footprint():
            for ox, oy in other.footprint():
                if nx == ox and abs(ny - oy) <= node.type.power_range:
                    return True
                if ny == oy and abs(nx - ox) <= node.type.power_range:
                    return True
    return False


def _build_power_networks(buildings):
    """Union-Find over building có điện -- trả về {id(building): network_id}.
    Không mô phỏng maxNodes (giới hạn số link/node thật) hay battery (lưu
    trữ làm mượt biến động ngắn hạn) -- simulator này tính TRUNG BÌNH ổn
    định, battery không đổi kết quả trung bình dài hạn, chỉ đổi biến động
    tức thời (xem NEXT_STEPS.md)."""
    capable = [b for b in buildings if _power_capable(b)]
    parent = {id(b): id(b) for b in capable}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(capable)):
        for j in range(i + 1, len(capable)):
            if _power_linked(capable[i], capable[j]):
                union(id(capable[i]), id(capable[j]))

    return {id(b): find(id(b)) for b in capable}


def _generator_power_rate(grid: Grid, b: PlacedBuilding, in_edges, branch_count, output_rate, liquid_in_edges, liquid_branch_count, liquid_output_rate):
    """Xấp xỉ PowerGenerator.java getPowerProduction() = powerProduction *
    productionEfficiency (đã nhân TICKS_PER_SECOND để ra công suất/giây).
    4 cách tính `productionEfficiency`, khớp 4 nhóm class Java thật (audit
    "Power Blocks", xem NEXT_STEPS.md):

    1. generator_passive=True (SolarGenerator.java, solar-panel/-large): ra
       điện THỤ ĐỘNG, không cần input -- hiệu suất thật phụ thuộc ánh sáng
       môi trường + state.rules.solarMultiplier, KHÔNG mô phỏng ngày/đêm --
       xấp xỉ LUÔN đủ nắng (hiệu suất=1.0 cố định).
    2. generator_liquid_only=True (chemical-combustion-chamber/pyrolysis-generator:
       CHỈ consumeLiquids(...), không có consumeItem() nào -- khác hẳn case
       3/4, không có "chu kỳ" item nào để giới hạn tốc độ): hiệu suất =
       tỉ lệ lưu lượng liquid ĐANG CÓ / lưu lượng CẦN LIÊN TỤC (không quy
       đổi theo item_duration), trần 1.0.
    3. generator_item != None (ConsumeGenerator.java dùng consumeItem(X) CỐ
       ĐỊNH thay vì ConsumeItemFlammable -- vd differential-generator; hoặc
       NuclearReactor.java/ImpactReactor.java, cùng dạng "cần đúng 1 item cố
       định"): SUM rate của ĐÚNG item đó (không so flammability), cycle_rate
       giới hạn bởi available/generator_item_amount.
    4. Mặc định (ConsumeItemFlammable.java thật, combustion-generator/
       steam-generator): chọn nhiên liệu cháy tốt nhất (flammability cao
       nhất) trong số item được belt dẫn tới -- hành vi CŨ, không đổi.

    Cả 4 đều áp dụng CHUNG bước giới hạn liquid đi kèm (generator_liquid_inputs,
    vd nước cho steam-generator/thorium-reactor) sau đó -- riêng case 2,
    generator_liquid_inputs lưu trực tiếp đơn vị "cần/giây" (không nhân
    item_duration vì không có chu kỳ item nào), nên bước giới hạn liquid
    dùng chung code nhưng max_cycle_rate/cycle_rate ban đầu = 1.0 khớp đúng
    đơn vị đó."""
    if b.type.generator_passive:
        return TICKS_PER_SECOND * b.type.power_production

    if b.type.generator_liquid_only:
        max_cycle_rate = 1.0
        cycle_rate = 1.0
        flammability_scale = 1.0
    elif b.type.generator_item is not None:
        available = sum(
            min(output_rate.get(id(src), 0.0) / branch_count[src], cap)
            for src, cap in in_edges.get(b, [])
            if produced_item(grid, src) == b.type.generator_item
        )
        if b.type.item_duration <= 0 or b.type.generator_item_amount <= 0:
            return 0.0
        max_cycle_rate = TICKS_PER_SECOND / b.type.item_duration
        cycle_rate = min(max_cycle_rate, available / b.type.generator_item_amount)
        flammability_scale = 1.0  # item cố định -- không có khái niệm "cháy tốt tới đâu"
    else:
        best_flammability = 0.0
        best_rate = 0.0
        for src, cap in in_edges.get(b, []):
            item = ITEMS.get(produced_item(grid, src))
            if item is None or item.flammability < b.type.min_flammability:
                continue
            rate = min(output_rate.get(id(src), 0.0) / branch_count[src], cap)
            if rate > 0 and item.flammability > best_flammability:
                best_flammability = item.flammability
                best_rate = rate

        if best_flammability <= 0 or b.type.item_duration <= 0:
            return 0.0

        max_cycle_rate = TICKS_PER_SECOND / b.type.item_duration
        cycle_rate = min(max_cycle_rate, best_rate)
        flammability_scale = best_flammability

    for liquid_name, amount_per_cycle in b.type.generator_liquid_inputs.items():
        available = sum(
            min(liquid_output_rate.get(id(src), 0.0) / liquid_branch_count[src], cap)
            for src, cap in liquid_in_edges.get(b, [])
            if produced_liquid(src) == liquid_name
        )
        if amount_per_cycle > 0:
            cycle_rate = min(cycle_rate, available / amount_per_cycle)

    if cycle_rate <= 0:
        return 0.0
    return TICKS_PER_SECOND * b.type.power_production * flammability_scale * (cycle_rate / max_cycle_rate)


def _power_satisfaction(grid: Grid, buildings, in_edges, branch_count, output_rate, liquid_in_edges, liquid_branch_count, liquid_output_rate):
    """Xem PowerGraph.java getSatisfaction(): satisfaction = clamp(production/needed).
    Trả về (networks, satisfaction) -- networks: {id(building): network_id},
    satisfaction: {network_id: 0..1}. KHÔNG lặp lại (không giống game thật
    hội tụ qua nhiều tick): production/consumption tính 1 lần từ throughput
    ổn định đã có, đủ cho mục đích lập kế hoạch (xem NEXT_STEPS.md)."""
    networks = _build_power_networks(buildings)
    production = defaultdict(float)
    consumption = defaultdict(float)
    for b in buildings:
        net = networks.get(id(b))
        if net is None:
            continue
        if b.type.kind == "generator":
            production[net] += _generator_power_rate(
                grid, b, in_edges, branch_count, output_rate, liquid_in_edges, liquid_branch_count, liquid_output_rate
            )
        if b.type.power_input > 0:
            consumption[net] += b.type.power_input

    satisfaction = {}
    for net in set(networks.values()):
        need = consumption.get(net, 0.0)
        prod = production.get(net, 0.0)
        if need <= 0:
            satisfaction[net] = 1.0
        elif prod <= 0:
            satisfaction[net] = 0.0
        else:
            satisfaction[net] = min(1.0, prod / need)
    return networks, satisfaction


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
        if b.type.kind == "pump":
            rate = _pump_output_rate(grid, b)
        elif b.type.kind == "solid-pump":
            rate = _solid_pump_output_rate(grid, b)
        else:
            rate = 0.0
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
            # Drill.java consumeLiquid(...).boost() -- KHÔNG bắt buộc (khác
            # power_input/consumePower ở dưới, xử lý riêng trong
            # _power_satisfaction). Không có/thiếu boost_liquid vẫn ra đúng
            # rate nền phía trên -- chỉ NHÂN THÊM nếu có nước, không bao giờ
            # làm rate thấp hơn rate nền. Giới hạn: impact-drill/eruption-drill
            # (BurstDrill) thật có 1 consumeLiquid(nước) BẮT BUỘC riêng
            # (không có .boost(), không parse ở đây -- chỉ 2 consumeLiquid có
            # .boost() mới được coi là booster) CHƯA model -- rate 2 block đó
            # có thể bị TÍNH CAO HƠN thật nếu không cấp nước, xem NEXT_STEPS.md.
            if b.type.boost_liquid is not None:
                needed = TICKS_PER_SECOND * b.type.boost_amount
                available = sum(
                    min(compute_liquid(src) / liquid_branch_count[src], cap)
                    for src, cap in liquid_in_edges[b]
                    if produced_liquid(src) == b.type.boost_liquid
                )
                efficiency = min(available / needed, 1.0) if needed > 0 else 0.0
                rate *= 1.0 + (b.type.boost_intensity - 1.0) * efficiency
        elif b.type.kind == "beam-drill":
            rate = _beam_drill_output_rate(grid, b)
        elif b.type.kind == "wall-crafter":
            rate = _wall_crafter_output_rate(grid, b)
        elif b.type.kind == "unloader":
            rate = _unloader_output_rate(grid, b)
        elif b.type.kind == "factory":
            recipe = b.type.recipe
            cycle_rate = 1.0 / recipe.craft_time
            for item_name, amount_per_cycle in recipe.inputs.items():
                available = sum(
                    min(compute(src, visiting) / branch_count[src], cap)
                    for src, cap in in_edges[b]
                    if produced_item(grid, src) == item_name
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

    # Mạng điện: tính SAU khi mọi throughput item/liquid ổn định đã có (không
    # lặp lại nhiều vòng như game thật hội tụ theo tick -- xem
    # _power_satisfaction), rồi NHÂN LẠI vào output_rate/liquid_output_rate
    # của building cần điện (power_input > 0). Đây là hậu xử lý 1 lần, KHÔNG
    # lan ngược lại cho các building khác phụ thuộc vào building bị thiếu
    # điện đó (vd factory B nhận input từ drill A đang thiếu điện sẽ không tự
    # động thấy input giảm theo) -- xấp xỉ đơn giản hoá, ghi rõ trong
    # NEXT_STEPS.md, đủ dùng để phát hiện "building X sẽ chạy dưới công suất
    # vì thiếu điện" mà không cần mô phỏng lặp hội tụ đầy đủ.
    power_networks, power_sat_by_network = _power_satisfaction(
        grid, buildings, in_edges, branch_count, output_rate, liquid_in_edges, liquid_branch_count, liquid_output_rate
    )
    power_satisfaction: dict[int, float] = {}
    for b in buildings:
        if b.type.power_input <= 0:
            continue
        net = power_networks.get(id(b))
        sat = power_sat_by_network.get(net, 0.0) if net is not None else 0.0
        power_satisfaction[id(b)] = sat
        if b.type.kind in ("pump", "solid-pump"):
            liquid_output_rate[id(b)] *= sat
        else:
            output_rate[id(b)] *= sat

    power_production = {
        b: _generator_power_rate(grid, b, in_edges, branch_count, output_rate, liquid_in_edges, liquid_branch_count, liquid_output_rate)
        for b in buildings if b.type.kind == "generator"
    }

    core = next((b for b in buildings if b.type.kind == "core"), None)
    score = output_rate.get(id(core), 0.0) if core else 0.0

    return {
        "score": score,
        "connections": connections,
        "liquid_connections": liquid_connections,
        "output_rate": {b: output_rate[id(b)] for b in buildings},
        "liquid_output_rate": {b: liquid_output_rate[id(b)] for b in buildings},
        "power_satisfaction": {b: power_satisfaction[id(b)] for b in buildings if id(b) in power_satisfaction},
        "power_production": power_production,
    }
