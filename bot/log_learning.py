"""Tự động rút phản hồi (feedback) cho bot/scorer.py từ 1 LOG hành động chơi
thật, thay vì phải tự tay chê/khen từng lần (bot/feedback.py:record_feedback).

Log dùng ĐÚNG format `actions` mà bot/planner.py đã emit ra suốt cả dự án
(`{"op":"place"|"remove"|"configure"|"rotate", "building":..., "x":...,
"y":..., "rotation":..., ...}`) -- không cần định dạng riêng, không cần dịch.
Cách tạo log này từ game thật: mod bắt các sự kiện BlockBuildEndEvent/
ConfigEvent/BuildRotateEvent (xem NEXT_STEPS.md mục "Log gameplay").

Cơ chế 2 bước:
1. Với mỗi hành động "place" 1 FACTORY (loại DUY NHẤT có nhiều vị trí khả dĩ
   và dùng scorer để chọn trong plan_build() -- drill/pump chọn theo mỏ gần
   nhất, không qua scorer): hỏi plan_build() xem bot sẽ đề xuất đặt ở đâu NẾU
   chưa biết bạn chọn gì, ghi lại để so với vị trí bạn THỰC SỰ chọn.
2. LỌC bằng evaluate_layout(): sau khi phát lại HẾT log, kiểm building đó
   CUỐI CÙNG có thực sự sản xuất được gì không (`output_rate > 0`) -- chỉ
   building "sống" (thật sự nối được input+output, không phải xây tạm/xây
   nhầm rồi bỏ) mới tạo cặp so sánh cho record_feedback().

   LƯU Ý THIẾT KẾ (đã sửa sau khi test thật): lúc đầu lọc bằng cách so
   `evaluate_layout()["score"]` NGAY TRƯỚC/SAU đúng 1 dòng "place" -- SAI,
   vì đặt building và nối belt/điện cho nó thường là NHIỀU dòng log tách
   biệt (place building -> place belt input -> place belt output -> place
   generator điện...), dòng "place" một mình gần như luôn cho điểm 0->0 (vì
   chưa nối gì cả), không phản ánh được KẾT QUẢ CUỐI CÙNG của cả chuỗi hành
   động. Sửa: kiểm production tại thời điểm CUỐI log thay vì delta trên 1
   dòng riêng lẻ.

Giới hạn (ghi rõ, không giấu):
- Chỉ áp dụng cho factory (silicon-smelter, graphite-press...) -- drill/pump
  không đi qua đường chọn có scorer nên không tạo được cặp so sánh vị trí.
- Chỉ xét được nếu MỌI input item của factory đó đã có producer SẴN trên map
  tại thời điểm đó (không tự đoán/đặt thêm nguồn -- xem _factory_sources_readonly).
- Đây là suy luận NGẦM ("bạn xây ở đâu = bạn thích chỗ đó"), không phải phản
  hồi CHỦ ĐỘNG như record_feedback() vốn được thiết kế cho -- bước lọc theo
  "có sản xuất được không" ở trên giảm nhiễu (loại bỏ xây tạm/xây rồi phá)
  nhưng không loại bỏ hoàn toàn khả năng học nhầm từ 1 lựa chọn ngẫu nhiên
  lúc chơi mà vẫn tình cờ hoạt động được.
"""

from bot.feedback import record_feedback
from bot.planner import find_producer, plan_build
from bot.state import grid_from_state
from simulator.buildings import CATALOG
from simulator.sim import evaluate_layout


def _apply_action(grid, action):
    """Áp 1 dòng log vào Grid -- tương ứng đúng 4 loại op mà
    bot/mod_bridge.py:execute() cũng xử lý, chỉ khác là chạy trực tiếp trên
    Grid cục bộ thay vì gửi qua console server thật."""
    op = action.get("op")
    if op == "place":
        building_type = CATALOG[action["building"]]
        grid.place(
            building_type, action["x"], action["y"],
            rotation=action.get("rotation", 0),
            ore_target=action.get("ore_target"),
            liquid_target=action.get("liquid_target"),
            filter_item=action.get("filter_item"),
        )
    elif op == "remove":
        b = grid.building_at(action["x"], action["y"])
        if b is not None:
            grid.remove(b)
    elif op == "configure":
        b = grid.building_at(action["x"], action["y"])
        if b is not None:
            b.filter_item = action["value"]
    elif op == "rotate":
        b = grid.building_at(action["x"], action["y"])
        if b is not None:
            b.rotation = action["rotation"]


def _factory_sources_readonly(grid, building_type):
    """Giống phần đầu plan_build()'s factory branch, nhưng CHỈ ĐỌC -- không
    tự đặt drill/pump mới nếu thiếu input nào (không đoán nguồn cho 1 hành
    động đã xảy ra trong quá khứ). Trả về (sources, core_pos), hoặc None nếu
    thiếu bất kỳ input item nào (bỏ qua hành động đó, không suy diễn)."""
    core = next((b for b in grid.unique_buildings() if b.type.kind == "core"), None)
    core_pos = (core.x, core.y) if core is not None else None

    sources = []
    for item_name in building_type.recipe.inputs:
        producer = find_producer(grid, item_name)
        if producer is None:
            return None
        sources.append((item_name, producer))
    return sources, core_pos


def extract_feedback_from_log(initial_state: dict, log_actions: list, scorer, verbose: bool = True) -> int:
    """Phát lại `log_actions` từng dòng trên state khởi đầu `initial_state`,
    tự tạo + áp record_feedback() cho những chỗ hợp lệ (xem docstring module).
    Trả về số cặp feedback đã tạo."""
    grid = grid_from_state(initial_state)
    replayed: list = []
    # (log_index, building_name, building_type, sources, bot_spot, player_spot, core_pos)
    candidates = []

    for i, action in enumerate(log_actions):
        if action.get("op") == "place":
            building_type = CATALOG.get(action.get("building"))
            if building_type is not None and building_type.kind == "factory":
                ctx = _factory_sources_readonly(grid, building_type)
                if ctx is not None:
                    sources, core_pos = ctx
                    # Hỏi bot sẽ đề xuất đặt ở đâu NẾU chưa biết bạn chọn gì --
                    # dựng grid THỬ riêng (không đụng grid thật đang phát lại).
                    trial_grid = grid_from_state(initial_state)
                    for a in replayed:
                        _apply_action(trial_grid, a)
                    try:
                        bot_actions = plan_build(trial_grid, {"action": "build", "building": action["building"]}, scorer=scorer)
                        bot_spot = next(
                            ((a["x"], a["y"]) for a in bot_actions if a["building"] == action["building"]),
                            None,
                        )
                    except (ValueError, RuntimeError):
                        bot_spot = None

                    player_spot = (action["x"], action["y"])
                    if bot_spot is not None and bot_spot != player_spot:
                        candidates.append((i, action["building"], building_type, sources, bot_spot, player_spot, core_pos))

        _apply_action(grid, action)
        replayed.append(action)

    # Phát lại xong toàn bộ log -- giờ mới biết building nào THẬT SỰ sống sót
    # và sản xuất được gì (xem "LƯU Ý THIẾT KẾ" trong docstring module).
    final_result = evaluate_layout(grid)
    pairs_found = 0
    for i, building_name, building_type, sources, bot_spot, player_spot, core_pos in candidates:
        placed = grid.building_at(*player_spot)
        productive = placed is not None and final_result["output_rate"].get(placed, 0.0) > 1e-9
        if productive:
            record_feedback(grid, building_type, sources, rejected_spot=bot_spot, preferred_spot=player_spot, scorer=scorer, core_pos=core_pos)
            pairs_found += 1
            if verbose:
                print(
                    f"  [feedback #{pairs_found}] dòng log {i} ({building_name}): "
                    f"bot đề xuất {bot_spot}, bạn chọn {player_spot} -- cuối log sản xuất "
                    f"{final_result['output_rate'][placed]:.4f}/s -- đã cập nhật scorer"
                )
        elif verbose:
            print(f"  [bỏ qua] dòng log {i} ({building_name}) tại {player_spot}: cuối log không sản xuất được gì (0/s)")

    return pairs_found
