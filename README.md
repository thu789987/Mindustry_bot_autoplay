# mindustry-factory-ai

Mục tiêu dài hạn: tối ưu bố cục nhà máy (drill/belt/factory) cho một map
Mindustry cụ thể, tối đa hoá throughput trên diện tích xây dựng.

## Trạng thái hiện tại — Milestone 1

Simulator Python thuần, độc lập với game thật. Cho một layout (grid + vị trí
building), tính throughput ổn định (items/sec) đổ về core.

```
simulator/
  buildings.py   # BuildingType, Recipe, Item, catalog (drill/belt/smelter/core)
  grid.py        # Tile, Grid, PlacedBuilding (footprint, output_tile)
  sim.py         # trace_belt_path, find_connections, evaluate_layout
examples/
  run_example.py # 2 layout mẫu dựng tay, in throughput
reference/       # snapshot file .java gốc dùng để lấy số liệu (xem bên dưới)
```

Chạy thử:

```
python examples/run_example.py
```

Kỳ vọng: scenario "direct to core" ra ~0.369 items/sec, scenario
"drill -> smelter -> core" ra ~0.171 items/sec (giới hạn bởi tốc độ craft của
graphite press). Số thấp vì đây là số thật của mechanical drill (tier 1),
không phải số bịa như bản đầu.

## Nguồn số liệu

Các hằng số trong `buildings.py` (drill_time, hardness_multiplier, tier,
craft_time, item hardness, tốc độ belt) lấy trực tiếp từ mã nguồn thật của
Mindustry, không phải tự đặt:

- Repo: https://github.com/Anuken/Mindustry (nhánh `master`, tải về
  2026-07-13, snapshot lưu ở `reference/*.java`)
- `content/Blocks.java` → field của `mechanicalDrill`, `conveyor`,
  `graphitePress`
- `content/Items.java` → `hardness` của từng item
- `world/blocks/production/Drill.java` → công thức tốc độ khai thác thật:
  `rate = 60 * số_tile_ore_khớp / (drillTime + hardnessDrillMultiplier * item.hardness)`
  (chính là công thức game dùng để hiển thị chỉ số "drill speed" cho người chơi)

Vì lấy từ nhánh `master` hiện tại trên GitHub, số liệu có thể lệch nhẹ so với
bản game bạn đang chơi nếu version khác xa. Cách chính xác nhất là dump trực
tiếp từ game đang chạy qua mod (xem Milestone 4).

## Giới hạn của v1 (biết trước, chưa xử lý)

- **Không có junction/splitter/router** — mỗi building chỉ có 1 tile output,
  không merge/split được dòng chảy. Layout thật với nhiều nhánh chưa mô
  phỏng đúng.
- **Recipe chỉ hỗ trợ 1 input / 1 output** — nhiều công thức thật trong
  Mindustry cần ≥2 nguyên liệu (chưa hỗ trợ).
- **Không có power** — chưa tính giới hạn điện năng.
- **Không mô hình hoá liquid boost** — mechanical drill có thể được cấp nước
  để tăng tốc, simulator bỏ qua, luôn tính ở tốc độ nền.
- **Drill chỉ đào 1 loại ore chỉ định trước** (`ore_target`) — game thật tự
  chọn ore chiếm đa số trong footprint, simulator để người dùng chỉ định
  thay vì tự suy luận.
- **Chỉ có mechanical-drill (tier 1)** trong catalog — chưa thêm pneumatic
  drill trở lên (cần power, chưa mô hình hoá).
- Kết nối "chạm tile là nhận" — building nhận input từ bất kỳ cạnh nào chạm
  belt, không phân biệt hướng input như game thật có thể yêu cầu.

Đã chạy và xác nhận `examples/run_example.py` ra đúng số như mô tả ở trên.

## Tiếp theo

- **Milestone 2**: đọc map thật (`.msav`) để lấy vị trí ore/địa hình thay vì
  dựng tay.
- **Milestone 3**: Simulated Annealing dùng `evaluate_layout` làm fitness để
  tự đề xuất layout cho một map.
- **Milestone 4**: đối chiếu layout thắng với game thật (headless server hoặc
  mod dump content trực tiếp), hiệu chỉnh lại số liệu nếu version lệch, xuất
  layout ra schematic Mindustry.
- **Milestone 5 (đang làm)**: mod Java ghi log gameplay thật, bắt 3 sự kiện
  `BlockBuildEndEvent`/`ConfigEvent`/`BuildRotateEvent` (xem `mod/`) ra
  đúng format `actions` mà `bot/log_learning.py` đã hỗ trợ từ trước —
  đóng nốt phần "chưa có Java trên máy để build/test" đã ghi từ đầu dự án ở
  `bot/mod_bridge.py`. Chi tiết build/cài đặt: `mod/README.md`.
