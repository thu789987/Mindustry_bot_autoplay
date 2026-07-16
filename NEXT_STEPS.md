# Việc cần làm tiếp — đọc file này khi quay lại

## Sorter (bộ lọc) -- nối vào flow tracing, KHÁC Router

Bạn chỉ đúng: "than đi thẳng vào X, còn lại rẽ sang Y" không phải việc của
Router (chia đều không điều kiện) mà là **Sorter** -- đã có sẵn trong hệ
thống từ phần "configure" làm trước đó, nhưng tôi **chưa từng nối nó vào
logic dò belt** (`_trace_branching`) -- trước đây gặp sorter là coi luôn là
điểm đến cuối, không biết dò tiếp.

### Cơ chế thật (tra `Sorter.java:getTileTarget()`)

```java
if (item == sortItem) to = nearby(dir);              // ĐI THẲNG (đúng hướng đang di chuyển)
else to = nearby(dir-1) hoặc nearby(dir+1);           // RẼ sang 1 trong 2 hướng VUÔNG GÓC
```

Khác Router (N nhánh, chia đều, không quan tâm loại item): Sorter **đúng 2
nhánh cố định**, đích nào nhận được quyết định bởi loại item khớp filter
hay không, không phải do bạn chọn "muốn thẳng đi đâu, muốn rẽ đi đâu".

### Đã làm

- `simulator/grid.py`: `PlacedBuilding.filter_item` (trước đây `configure`
  chỉ emit action, KHÔNG cập nhật state cục bộ -- khác `rotate` có set
  `target.rotation`, đã sửa `plan_configure` cho nhất quán).
- `simulator/sim.py`: `_trace_branching()` giờ nhận thêm `item_name` (loại
  item đang chảy, lấy từ nguồn qua `produced_item()`), xử lý `kind=="sorter"`:
  suy ra hướng đang di chuyển từ `came_from` (`_direction_of()`), so khớp
  filter, rẽ đúng nhánh.
- `bot/planner.py:plan_filter_split(grid, source, filter_item, match_footprint, other_footprint)`
  -- đặt sorter, cấu hình filter, nối nhánh thẳng + nhánh rẽ. Cùng giới hạn
  scope như `plan_split`: **chưa nối vào `parse_commands()`** (câu "X đi
  thẳng, còn lại rẽ sang Y" phức tạp hơn dict parser hiện tách được).

### Bug thật phát hiện khi tự test (không phải lý thuyết suông)

Test đầu tiên ra **cả 2 nhánh đều 0** dù code "nhìn đúng". Debug ra nguyên
nhân: `find_free_area` đặt sorter **NGAY SÁT** đầu ra drill (0 belt ở giữa,
radius=0 luôn là lựa chọn đầu tiên) -- khi dò lại từ đầu để tính
`evaluate_layout`, `_trace_branching` bắt đầu tại chính vị trí sorter với
`came_from=None` (chưa đi qua ô nào), nên **không tính được đang di chuyển
hướng nào**, rơi vào nhánh "coi là điểm đến", bỏ qua toàn bộ logic rẽ nhánh.

**Đã sửa**: `find_connections`/`find_liquid_connections` giờ truyền 1
`came_from` GIẢ ĐỊNH ngay từ đầu -- "1 ô phía sau, theo đúng hướng nguồn
đang quay mặt" (`(ox - dx, oy - dy)` với `dx,dy` = hướng quay của nguồn) --
đủ để `_direction_of` tính đúng dù sorter/router nằm sát nguồn không có
belt ở giữa. Áp dụng luôn cho router (bug tiềm ẩn tương tự chưa từng lộ ra
vì `router_demo.py` tình cờ không rơi vào trường hợp sát nguồn).

**Đã test bằng `bot/sorter_split_demo.py`** (2 kịch bản, cùng 1 drill than,
chỉ đổi filter): lọc "coal" (khớp) → 100% chảy nhánh thẳng, nhánh rẽ = 0;
lọc "sand" (không khớp) → 100% chảy nhánh rẽ, nhánh thẳng = 0. Chạy lại
toàn bộ 11 demo cũ (kể cả `router_demo.py` -- số liệu 0.1714/s mỗi nhánh
không đổi) — không hỏng gì.

## Sửa 3 lỗ hổng phát hiện từ câu lệnh ghép: "khai thác than, và cát... tách belt làm 2, 1 về core, 1 tạo silicon"

Trace câu này qua code thật lộ ra 3 vấn đề tách biệt. Đã sửa cả 3:

### 1. Bug thật: "làm 2, 1 nguồn" bị hiểu nhầm thành toạ độ (2,1)

`COORD_RE` trước đây có ngoặc TUỲ CHỌN (`\(?...\)?`), khớp cả cụm "số, số"
trần không ngoặc trong câu tự nhiên. **Đã sửa**: bắt buộc có ngoặc
(`\((\d+)\s*,\s*(\d+)\)`) — toạ độ thật luôn được gõ có ngoặc, câu nói
thường không tự nhiên viết vậy, nên gần như hết false positive mà không mất
khả năng nhận toạ độ thật (test lại toàn bộ demo dùng toạ độ có ngoặc vẫn
đúng).

### 2. Parser chỉ hiểu ĐÚNG 1 building/câu — thêm `parse_commands()`

`parse_command()` cũ chỉ trích được 1 building (dừng ngay khi khớp phrase
đầu tiên) nên câu ghép nhiều ý chỉ thực hiện được ý đầu, bỏ qua hết phần
còn lại — không báo lỗi, không báo thiếu, im lặng bỏ qua.

**Đã thêm** `bot/command_parser.py:parse_commands(text) -> list[dict]`: tách
câu theo dấu phẩy/"và" thành từng đoạn, chạy `parse_command()` riêng từng
đoạn. Có xử lý tỉnh lược động từ đơn giản (đoạn "cát cho tôi" không có động
từ riêng, tự kế thừa hành động "khai thác" từ đoạn liền trước nếu đoạn đó
là lệnh xây drill/pump). `bot/live_run.py` đã đổi sang gọi hàm này, chạy
tuần tự từng lệnh trên state đang cập nhật dần (đọc lại state sau mỗi lệnh).

**Giới hạn thật, không giấu**: dict-based nên chỉ tách được theo "và"/phẩy
nối các Ý ĐỘC LẬP — không hiểu được cấu trúc phức tạp hơn như "tách X làm 2,
nhánh A nối Y, nhánh B nối Z" (đoạn đó không map vào action/building nào cả,
bị bỏ qua thay vì đoán bừa). LM Studio (`bot/llm_parser.py`) vốn hợp việc
này hơn hẳn dict nhưng CHƯA nâng cấp để trả về nhiều lệnh — còn để dành.

**Đã test bằng `bot/multi_command_demo.py`**: câu gốc (lỗi chính tả
"slicion") ra đúng 2 lệnh (than, cát) — bỏ qua đúng đoạn "silicon" vì
"slicion" không khớp tên thật; sửa đúng chính tả thì ra đủ 3 lệnh (than,
cát, silicon-smelter), chạy tuần tự 2 lệnh đầu thành công.

### 3. Ngay cả parser đúng, planner cũng chưa "chia 1 nguồn thành nhiều nhánh"

Lệnh 3 (silicon-smelter) ở test trên gặp lỗi thật: cố nối THÊM 1 belt từ
CHÍNH điểm xuất phát của drill than (đã có 1 belt đi core từ lệnh 1) →
đụng ngay ô đầu tiên. Debug ra nguyên nhân chính xác (xem lịch sử) rồi sửa
theo 2 lớp:

- **Sửa lỗi crash trước**: `find_belt_path()` giờ phát hiện điểm xuất phát
  đã bị chiếm (và không chạm đích) thì trả `None` (báo "không tìm được
  đường belt") thay vì để BFS âm thầm coi ô đó là đi được rồi crash lúc đặt
  thật (`ValueError: cannot place conveyor at (5,4)` -- lỗi nội bộ rò rỉ ra
  ngoài, giờ thành `RuntimeError` tiếng Việt rõ ràng).
- **Làm đúng cơ chế chia nhánh thật**: tra `Router.java` xác nhận cơ chế
  thật là round-robin chia đều item cho các hướng còn nhận được. Đã thêm:
  - `tools/generate_catalog.py`: phủ thêm class `Router` (trước chỉ có
    tên+category, giờ hiểu cơ chế) -- sinh ra `router` và `distributor`.
  - `simulator/sim.py`: `_trace_branching()` (thay `trace_belt_path`/
    `trace_conduit_path` khi tìm connections) — đệ quy qua router, TỰ CHIA
    capacity đều cho N nhánh hợp lệ. `evaluate_layout()` chia
    `compute(src)` cho số nhánh thật của nguồn đó (`Counter` đếm nhánh) để
    **bảo toàn khối lượng** — nếu không chia, mỗi nhánh sẽ tưởng nhầm mình
    nhận TOÀN BỘ sản lượng nguồn (vi phạm bảo toàn khối lượng, vì
    `compute()` được nhớ đệm theo nguồn chứ không theo từng nhánh).
  - `bot/planner.py:plan_split(grid, source, destinations)` — đặt 1 router
    ngay sau đầu ra nguồn, nối belt từ router tới TỪNG đích riêng. **Đây là
    cách ĐÚNG để 1 nguồn nuôi nhiều đích**, khác hẳn gọi route 2 lần từ
    CÙNG 1 tile (sẽ đụng nhau, xem lỗi ở trên).
  - **CHƯA nối vào `parse_commands()`** (xem giới hạn ở mục 2) -- gọi trực
    tiếp qua API, test bằng `bot/router_demo.py`.

**Đã test bằng `bot/router_demo.py`**: 1 drill than (sản xuất 0.3429/s) tách
qua router thành 2 core khác nhau — mỗi core nhận đúng **0.1714/s**
(= 0.3429/2), tổng 2 nhánh khớp CHÍNH XÁC sản lượng drill, không tự nhân
đôi. Chạy lại toàn bộ 10 demo cũ (kể cả số liệu `evaluate_layout` không có
router) — không đổi 1 số nào, xác nhận việc chia cho `branch_count` không
ảnh hưởng trường hợp không có router (chia cho 1 = không đổi).

## Chỉ định RÕ mỏ nào khi có nhiều mỏ cùng loại (không chỉ để bot tự chọn)

Câu hỏi tiếp theo sau khi sửa bug "chọn theo thứ tự quét": có 4 mỏ quanh
core, muốn chỉ định đúng 1 mỏ cụ thể thì nói sao? Trước đó bot chỉ tự động
chọn gần core nhất, không có cách nào để người dùng ghi đè. Đã thêm 3 cách:

- **Theo hướng**: "xây máy khoan than **phía đông**" (cũng nhận "phía
  tây/nam/bắc", "hướng đông"...). Phân loại theo trục lệch nhiều hơn so với
  core (`bot/planner.py:_direction_of`), rồi trong số mỏ khớp hướng đó chọn
  cái gần core nhất.
- **Theo toạ độ**: "xây máy khoan than **tại (6,15)**" -- chọn ô ore gần
  toạ độ đó nhất.
- **Theo thứ tự**: "xây máy khoan than **thứ nhất**" -- sắp theo khoảng
  cách tới core rồi lấy thứ n.

Cách hoạt động: `command_parser.py:_find_location_hint()` (dùng chung
`COORD_RE`/`ORDINAL_RE` đã có, thêm `LOCATION_DIRECTION_WORDS` là cụm 2 từ
"phía X"/"hướng X" -- tách biệt với `DIRECTION_WORDS` 1 từ dùng cho lệnh
xoay, tránh nhầm 2 việc khác nhau) → `command["ore_location_hint"]` (hoặc
`liquid_location_hint` cho pump) → `planner.py:_select_tile()` áp dụng hint
trước khi rơi về mặc định "gần core nhất". Chỉ áp dụng cho nhánh xây drill/
pump **độc lập** — nhánh factory tự đặt drill/pump nội bộ cho nguyên liệu
vẫn luôn tự động (không có chỗ trong 1 câu lệnh để chỉ định vị trí riêng
cho từng input).

**Đã test bằng `bot/location_hint_demo.py`**: dựng map có đúng 4 mỏ than,
mỗi mỏ 1 hướng quanh core, cách đều nhau (để "gần nhất mặc định" không tự
nhiên thiên vị hướng nào) — xác nhận cả 4 lệnh theo hướng đều ra đúng mỏ
hướng đó, lệnh theo toạ độ và theo thứ tự cũng đúng. Chạy lại toàn bộ demo
cũ — không hỏng gì.

## Bug thật: bot chọn mỏ theo thứ tự quét toạ độ, không theo khoảng cách

Câu hỏi "bot không phải AI thông minh nhỉ, có 2 mỏ 1 gần 1 xa thì chọn cái
nào" lộ ra bug thật (không phải lý thuyết). `find_unmined_ore()`/
`find_untapped_liquid()` trước đây chỉ quét map từ **trên-trái xuống
dưới-phải**, trả về ô đầu tiên khớp -- không so khoảng cách với bất cứ gì.

**Đã chứng minh bằng test cụ thể** (`bot/scan_order_demo.py`): dựng map có
2 mỏ than -- 1 mỏ XA core (~35 ô, đặt ở toạ độ nhỏ (0,0)) và 1 mỏ GẦN core
(~2 ô, đặt ở toạ độ lớn (23,24)). Trước khi sửa: bot chọn mỏ **XA** (0,0)
vì toạ độ nhỏ được quét trước -- đúng như nghi ngờ trong câu hỏi.

**Đã sửa**: cả 2 hàm giờ nhận thêm tham số `near` (mặc định = vị trí core
nếu map có core), quét **toàn bộ** ứng viên rồi chọn ứng viên gần `near`
nhất (khoảng cách Manhattan), không còn phụ thuộc thứ tự quét toạ độ. Áp
dụng cho cả 4 chỗ gọi trong `plan_build()` (drill đơn lẻ, pump đơn lẻ, drill
tự đặt cho factory, pump tự đặt cho factory). Không có core trên map thì
vẫn quét-lấy-cái-đầu như cũ (không có gì để so "gần" cả).

Chạy lại test sau khi sửa: bot chọn đúng mỏ **GẦN** (23,24). Chạy lại toàn
bộ demo cũ (`example_run.py`, `actions_demo.py`, `learn_demo.py`,
`liquid_demo.py`, `tier_demo.py`) -- không hỏng gì.

**Lưu ý quan trọng vẫn đúng như đã nói**: đây vẫn KHÔNG phải AI hiểu ngữ
cảnh -- chỉ là thuật toán "so khoảng cách tới core" đơn giản, không biết
đường đi thật (belt phải vòng tránh vật cản) hay các yếu tố khác (an toàn,
tốc độ khai thác...). Cải thiện thêm (nếu cần): so khoảng cách belt THẬT
(qua BFS) thay vì đường chim bay Manhattan, hoặc dùng scorer đã có để học
ưu tiên "gần core" vs "mỏ nhiều ô hơn" v.v. -- chưa làm, không phải phạm vi
lần sửa này.

## Bot tự chọn tier drill (A+B+C) — sửa bug thật + cho phép ghi đè + học ưu tiên

Phát hiện từ câu hỏi "bot chọn drill tier mấy" — trước đây MỌI nơi hardcode
`mechanical-drill` (tier 2), kể cả khi ore cứng hơn tier đó (titanium=3,
thorium=4, tungsten=5) khiến drill đặt ra **không mine được gì**
(`_drill_output_rate` trả về 0 lặng lẽ, không báo lỗi). Đã sửa cả 3 hướng:

- **A (bắt buộc, sửa lỗi thật)**: `bot/planner.py:select_drill_type(hardness,
  scorer=None)` — chọn drill **rẻ nhất đủ tier** (`tier >= hardness`) thay
  vì hardcode. Mặc định (không scorer) giữ đúng hành vi cũ cho than/đồng
  (vẫn ra mechanical-drill), nhưng titan/thorium/tungsten giờ tự nhảy lên
  tier cao hơn thay vì đặt drill hỏng. Nếu người dùng chỉ định tier cụ thể
  nhưng không đủ mạnh, báo lỗi rõ ngay lúc lập kế hoạch thay vì để hỏng âm
  thầm dưới game.
- **B (ghi đè thủ công)**: `bot/command_parser.py` — nói chung chung ("máy
  khoan"/"khai thác") → sentinel `"drill"`, planner tự chọn (mục A). Nói rõ
  tier ("máy khoan khí nén", "pneumatic-drill"...) → dùng đúng loại đó,
  planner không tự đổi. `resolve_target()` cũng hiểu sentinel `"drill"` khi
  xoá/xoay drill mà không nói rõ tier nào (khớp mọi tier, vẫn hỏi lại nếu
  có nhiều loại khác nhau trên map).
- **C (học ưu tiên)**: `bot/scorer.py`/`bot/feedback.py:record_drill_tier_feedback()`.
  **Phát hiện quan trọng khi tự test**: ban đầu chỉ dùng 1 đặc trưng liên
  tục `drill_tier` — phản hồi lặp lại làm trọng số vọt qua 0 và luôn chọn
  tier **cao nhất có** (eruption-drill) thay vì dừng đúng tier được chọn
  (pneumatic-drill), vì 1 trọng số tuyến tính chỉ học được "thích cao/thấp
  nói chung", không học được "thích riêng 1 tier giữa". **Đã sửa** bằng
  cách thêm đặc trưng categorical `drill_is_<tên>` riêng từng loại, kết hợp
  với `drill_tier` liên tục làm nền mặc định — giờ 1 lần phản hồi đổi đúng
  sang tier được chọn, không vọt quá.
- **Đã test end-to-end** (`bot/tier_demo.py`, 4 kịch bản): (A) khai thác
  titan tự nhảy lên pneumatic-drill, `evaluate_layout` xác nhận ra
  0.4364/s thật (không phải 0 như bug cũ); (B1) chỉ định "pneumatic drill"
  cho than thì dùng đúng loại đó dù không bắt buộc; (B2) chỉ định
  "mechanical-drill" cho titan thì báo lỗi rõ, không đặt lặng lẽ; (C) sau
  đúng 1 lần phản hồi, đổi từ mechanical-drill sang pneumatic-drill cho lệnh
  "khai thác đồng" (ore mà cả 2 tier đều đủ dùng).

## Mở rộng lớn: phủ toàn bộ building thật (không chỉ 5 cái gõ tay)

Bạn hỏi "phủ hết tất cả được không" (đường ray, item, nhà máy, bơm nước, máy
khoan... kể cả turret/power/logic/unit). Đã làm theo 3 lớp rõ ràng, không
làm nửa vời:

### Lớp 1 — Hiểu đầy đủ cơ chế, planner đặt+nối được thật

| Kind | Trước | Sau |
|---|---|---|
| drill | 4 loại | **6 loại** (thêm BurstDrill: eruption-drill, impact-drill) |
| belt | 2 loại | **3 loại** (thêm armored-conveyor) |
| factory | 12 loại | 12 loại, nhưng **multi-press/plastanium-compressor giờ có đúng liquid_inputs** (nước/dầu) |
| sorter | 2 loại | 2 loại (không đổi) |
| pump | 0 | **3 loại mới** (mechanical/rotary/impulse-pump) |
| liquid-belt (conduit) | 0 | **4 loại mới** (conduit, plated/pulse/reinforced-conduit) |
| item | 22 | 22 (không đổi) |
| **liquid** | 0 | **11 loại mới** (water, oil, slag, cryofluid...) |

Cơ chế mới thêm — **liquid là 1 mạng lưới song song với item**, gặp nhau ở
recipe của factory:
- `simulator/buildings.py`: `Liquid` dataclass, `Recipe.liquid_inputs`,
  `BuildingType.pump_amount`.
- `simulator/grid.py`: `Tile.liquid`, `Grid.set_liquid()`,
  `PlacedBuilding.liquid_target` (song song `ore`/`ore_target`).
- `simulator/sim.py`: `trace_conduit_path`/`find_liquid_connections` (song
  song `trace_belt_path`/`find_connections`), `_pump_output_rate()` (công
  thức thật từ `Pump.java`), factory compute giờ throttle theo **cả** item
  lẫn liquid input (`min()` qua cả 2 loại).
- `bot/planner.py`: `plan_build()` có nhánh `kind=="pump"` mới (đặt bơm gần
  tile liquid, KHÔNG tự nối về core -- liquid không phải thứ "giao thẳng về
  core" như item); nhánh factory giờ tự tìm/đặt pump cho liquid_inputs y hệt
  cách tìm/đặt drill cho item inputs, tự route conduit y hệt route belt.
- **Đã test end-to-end** (`bot/liquid_demo.py`): lệnh "xây máy ép đa năng"
  trên map có than nhưng CHƯA có pump nước → bot tự đặt pump mới + nối cả
  belt (than) lẫn conduit (nước) tới multi-press. `evaluate_layout` xác
  nhận: than là nút thắt cổ chai thật (0.343/s than → giới hạn 0.229/s
  output), không phải số bịa.

**Bug thật phát hiện khi test số liệu pump**: `pumpAmount = 7f / 60f` trong
source là biểu thức chia, nhưng regex cũ chỉ lấy số `7` trước dấu `/`, bỏ
qua phần chia → pump ra 420 liquid/s (sai **60 lần**, vô lý ngay khi nhìn
số). Đã sửa `tools/generate_catalog.py:field_float()` để tính đúng biểu
thức nhân/chia (`_eval_expr()`), áp dụng cho cả `pumpAmount`, `craftTime`,
`consumeLiquid`. Sau khi sửa: pump ra đúng 7.0/s. Bài học: **mọi số lấy từ
source cần verify bằng cách tính tay hoặc chạy evaluate_layout, không chỉ
tin generator chạy không lỗi là số đúng.**

### Lớp 2 — Biết cơ chế nhưng cố ý không model (có lý do, không phải bỏ sót)

Ghi trong `generated_catalog.py:SKIPPED`, 11 mục:
- `plastanium-conveyor`, `surge-conveyor` (class `StackConveyor` — xếp
  chồng nhiều item/ô, khác hẳn Conveyor thường).
- `plasma-bore`, `large-plasma-bore` (class `BeamDrill` — đào theo tia dọc
  1 hướng có range, không phải diện tích chân đế).
- `water-extractor` (class `SolidPump` — rút 1 liquid cố định bất kể tile
  bên dưới, khác Pump thường cần tile liquid khớp).
- `reinforced-pump` (tự tiêu thụ liquid khác để bơm — case lồng nhau chưa
  model).
- `melter`, `electrolyzer`, `cryofluid-mixer`, `spore-press`,
  `coal-centrifuge` (output là liquid hoặc input pattern lạ, không khớp
  `outputItem`/`consumeItem` chuẩn).

### Lớp 3 — Chỉ có tên, CHƯA có logic đặt (turret/power/logic/unit/...)

**230 building** được liệt kê tên+category thật (`GENERATED_OTHER`) nhưng
**không có recipe/rate** — `plan_build()` từ chối đặt loại này với lỗi rõ
ràng (`"chưa hỗ trợ xây '<tên>' (thuộc nhóm '<category>')"`) thay vì đoán
bừa hay crash. Đã test: `plan(grid, {"action":"build","building":"duo"})`
(turret) → báo lỗi đúng như kỳ vọng.

## Phạm vi chưa làm — mỗi loại cần gì để làm thật (không phải "sắp xong")

Đây là 4 hệ thống hoàn toàn khác về thuật toán so với "auto-connect chuỗi
tài nguyên" đã có — không phải thêm vài dòng, mỗi cái là 1 project riêng:

- **Turret/defense** (category `turret`, `defense`) — đặt theo **vùng phủ
  hoả lực** (tầm bắn, hướng địch tới), không phải "gần nguyên liệu nhất".
  Cần: dữ liệu hướng spawn địch trên map (chưa có trong state schema hiện
  tại), thuật toán tối ưu vùng phủ (khác hẳn BFS/ring-search đang dùng).
  Đạn dược (ammo) thì CÓ THỂ tái dùng auto-connect belt sau khi đã đặt.
- ~~**Power**~~ — **ĐÃ LÀM** (generator + mạng điện phạm vi không dây), xem
  mục "Mạng điện" bên dưới. `battery`/`power-node`/`power-node-large`/
  `surge-tower` vẫn còn 230 building khác trong `GENERATED_OTHER` chưa có
  logic đặt riêng (turret/logic/unit dưới đây vẫn y nguyên).
- **Logic** (category `logic`) — configure() của logic-processor nhận
  **code MLOG** (ngôn ngữ lập trình riêng của game) làm value, không phải
  Item như sorter. Đây là bài toán "sinh chương trình", khác hẳn "chọn 1
  item lọc".
- **Units** (category `units`) — nhà máy unit không tạo ra building, mà
  tạo **đơn vị di động liên tục**, rồi cần lệnh riêng (tuần tra/khai thác/hỗ
  trợ) qua hệ thống unit-command khác hẳn (`UnitCommand.java`,
  `CommandAI.java`) — action vocabulary hiện tại (build/delete/rotate/
  reroute/configure) không có chỗ cho "sản xuất N đơn vị rồi ra lệnh Y".

## Mục tiêu thực sự (đã làm rõ lại — đọc trước)

Trước đó tôi hiểu nhầm sang hướng RL (agent tự học chơi qua thử-sai). Mục
tiêu thật của bạn khác:

> Chat ra lệnh bằng tiếng Việt (vd "xây nhà máy silicon") → bot tự tìm chỗ
> đặt building đó trên map đang chơi, tự nối belt từ nguyên liệu có sẵn gần
> nhất (vd drill than) đến building mới, và **thực thi luôn trong game đang
> chạy** (real-time).

RL cần thiết khi bot phải **tự quyết định phải làm gì** mà không ai ra lệnh.
Bot bạn muốn thì **luôn được ra lệnh rõ ràng** — nó chỉ cần thực thi lệnh một
cách tối ưu, không cần học gì. Đây là bài toán **lập kế hoạch + tối ưu hoá**,
đúng thứ luồng A (simulator) đã làm — chỉ khác là tính live trên map thật và
thực thi thật, thay vì tính offline rồi in ra giấy.

=> Bỏ hẳn hướng RL (`gymnasium`/`stable-baselines3`/PPO).

## Kiến trúc / quy trình tổng thể

Bot gồm 2 tiến trình chạy song song, nói chuyện với nhau qua socket/HTTP nội
bộ (cùng máy):

- **Tiến trình Python** (ngoài game): nhận chat, hiểu lệnh, tính toán kế
  hoạch xây dựng.
- **Mod chạy bên trong Mindustry**: đọc state thật của map, và là nơi duy
  nhất có quyền đặt building thật vào game (Python không thể tự vẽ vào game
  — phải nhờ mod làm hộ).

```
[Bạn gõ chat: "xây nhà máy silicon"]
        |
        v
[1. Command Parser]  (dict tra bảng, hoặc LM Studio nếu câu phức tạp)
   input:  "xây nhà máy silicon"
   output: {"action": "build", "building": "silicon-smelter"}
        |
        v
[2. Lấy state hiện tại]  (Python hỏi mod qua socket)
   mod trả về: {"buildings": [...đã đặt...], "ore_tiles": [...], "map_size": {...}}
        |
        v
[3. Planner]  (luồng A simulator, mở rộng để nhận state thật thay vì map dựng tay)
   input:  lệnh (bước 1) + state (bước 2)
   output: danh sách hành động cụ thể, vd:
     [{"op":"place","building":"silicon-smelter","x":34,"y":20,"rotation":0},
      {"op":"place","building":"conveyor","x":32,"y":20,"rotation":0}, ...]
        |
        v
[4. Executor]  (Python gửi danh sách hành động cho mod qua socket)
        |
        v
[5. Mod thực thi]  (đặt building thật vào game đang chạy, trả kết quả OK/lỗi)
        |
        v
[Bot phản hồi trong chat: "Đã xây xong nhà máy silicon, nối với drill than ở (10,12)"]
```

Điểm quan trọng: **mỗi lệnh chat là một lần chạy trọn vòng 1→5**, không có
vòng lặp liên tục kiểu RL (không cần chạy 60 lần/giây, không cần reward).
Chỉ khi có lệnh mới thì mới hỏi state mới nhất và tính lại.

## Vì sao làm theo thứ tự dưới đây

Bước 1 và 3 (parser, planner) **không đụng tới Mindustry/Java** — làm được
ngay, không bị chặn bởi việc chưa cài Java. Bước 2, 4, 5 (mod) mới cần Java.
Nên chia làm 2 giai đoạn độc lập, giai đoạn 1 làm trước trong lúc chưa có
Java, ghép lại ở giai đoạn 3.

## Giai đoạn 1 — làm được ngay, không cần Java

### Phát hiện quan trọng trước khi code

Tra `reference/Blocks.java` lấy tên block "silicon" thật thì ra
**`silicon-smelter`** (không phải tên bịa lúc trước) — và nó cần **2 nguyên
liệu cùng lúc**: than (`coal` x1) + cát (`sand` x2), cộng thêm cần điện
(`consumePower`). `Recipe` hiện tại (`buildings.py`) chỉ hỗ trợ 1 input, nên
ví dụ chính bạn đưa ra ("nối than với nhà máy silicon") sẽ chạy sai/thiếu
nếu không sửa trước. Việc này làm trong giai đoạn 1, không để nợ.

### Việc cụ thể

1. **Mở rộng `Recipe` sang nhiều input** (`simulator/buildings.py`,
   `simulator/sim.py`) — đổi `input_item/input_amount` (1 giá trị) thành
   `inputs: dict[item, amount]`. Sửa lại phần tính factory trong `sim.py` để
   nhóm các belt đến theo loại item nguồn cung cấp (drill cung cấp
   `ore_target`, factory cung cấp `recipe.output_item`) — hiện tại code coi
   mọi belt đến là cùng 1 loại, sẽ tính sai khi có 2 nguyên liệu khác nhau
   cùng đổ vào 1 building. Thêm `silicon-smelter` + item `sand` (số liệu
   thật lấy từ source) vào catalog.
2. **Command parser** (`bot/command_parser.py`): dict tra tên building tiếng
   Việt → tên block thật (`"nhà máy silicon"` → `"silicon-smelter"`). Việc
   dùng LM Studio để hiểu câu tự nhiên linh hoạt hơn là bước nâng cấp sau.
3. **State loader** (`bot/state.py`): định nghĩa schema JSON mô tả state map
   (buildings đã đặt, ore ở đâu, kích thước map) và hàm `grid_from_state()`
   dựng lại `Grid` từ đó — đây là hợp đồng dữ liệu mod sẽ phải xuất ra đúng
   format này ở giai đoạn 2.
4. **Auto-connect planner** (`bot/planner.py` — thuật toán mới, chưa có):
   - Tra recipe của building cần xây ra danh sách input cần (vd coal, sand).
   - Với mỗi input: tìm building đã sản xuất sẵn item đó gần nhất; nếu chưa
     có thì tìm ore tile loại đó chưa khai thác gần nhất và lên kế hoạch đặt
     drill mới tại đó trước.
   - Tìm khoảng trống đủ chỗ gần các nguồn để đặt building mới.
   - Định tuyến belt bằng **BFS pathfinding** trên grid (né building/địa
     hình cấm) từ mỗi nguồn tới building mới — khác ví dụ cũ (đường thẳng
     dựng tay), vì map thật không đảm bảo có đường thẳng trống.
   - Xuất danh sách hành động `place` theo đúng thứ tự cần đặt.
5. **Test end-to-end bằng state giả**: viết 1 file JSON mô tả map giả (có
   sẵn drill than + ore than + ore cát), chạy `text → parse → planner → in
   ra action list` — xác nhận logic đúng trước khi có mod/game thật.

Sau giai đoạn này: toàn bộ 1→5 chạy được bằng state giả, chưa đặt được vào
game thật (đó là Giai đoạn 2).

## Giai đoạn 2 — cần Java, làm khi có điều kiện

### 1. Cài Java (JDK 17)

- Cách nhanh (Windows, PowerShell): `winget install EclipseAdoptium.Temurin.17.JDK`
- Hoặc tải tay: https://adoptium.net/temurin/releases/?version=17
- Kiểm tra sau khi cài: `java -version`

### 2. Tải Mindustry

- Trang release chính thức: https://github.com/Anuken/Mindustry/releases
- Muốn tự gõ lệnh và xem building được đặt trực quan thì cần bản full game
  (desktop), không chỉ `server-release.jar` headless.

### 3. Cầu nối với game — KHÔNG cần viết mod riêng

Phát hiện quan trọng khi tra `reference/ServerControl.java` (source thật,
dòng 666): server headless có sẵn lệnh console

```
js <script...>
```

chạy JavaScript tuỳ ý ngay trong tiến trình game, có toàn quyền truy cập
Java API của Mindustry (`Vars.world`, `Vars.content`, v.v.) —**không cần viết
mod, không cần Gradle/compile**. Bot chỉ cần gửi lệnh `js ...` vào stdin của
server qua `subprocess` Python, đọc kết quả từ stdout.

#### Các hàm API đã xác nhận thật (tra trực tiếp source, không đoán)

| Việc cần | API thật | Nguồn |
|---|---|---|
| Kích thước map | `Vars.world.width()`, `Vars.world.height()` | `core/World.java:90,94` |
| Lấy 1 tile | `Vars.world.tile(x, y)` | `core/World.java:122` |
| Ore tại tile | `tile.drop()` → trả về `Item` hoặc `null` | `world/Tile.java:571` |
| Loại block tại tile | `tile.block()`, `tile.build` (instance đang đặt) | `world/Tile.java` |
| **Đặt building thật** | `tile.setBlock(Block type, Team team, int rotation)` | `world/Tile.java:231` |
| Tra Block theo tên string | `Vars.content.block("mechanical-drill")` | `core/ContentLoader.java:292` |

Điểm may mắn: tên block thật trong game (`"mechanical-drill"`,
`"silicon-smelter"`, `"conveyor"`...) **khớp chính xác** với tên đã dùng làm
key trong `CATALOG` ở `simulator/buildings.py` — vì đó chính là tên tôi lấy
từ constructor thật trong `Blocks.java` (vd `new Drill("mechanical-drill")`).
=> Không cần bảng dịch tên building nào cả, dùng thẳng string đã có.

#### Thiết kế cầu nối (subprocess, không cần socket)

```
Python                              Server headless (subprocess)
  |--- stdin: "js <đoạn code>" ----------> chạy JS, có full quyền game API
  |<-- stdout: dòng có marker riêng ------ đọc, parse JSON
```

- Đọc state: gửi 1 dòng JS quét toàn bộ tile, gom `ore_tiles` + `buildings`
  thành JSON, in ra kèm marker cố định để Python lọc ra khỏi log lẫn lộn của
  server, ví dụ:
  ```
  js var o={buildings:[],ore_tiles:[],width:Vars.world.width(),height:Vars.world.height()};for(var x=0;x<o.width;x++)for(var y=0;y<o.height;y++){var t=Vars.world.tile(x,y);if(t.drop()!=null)o.ore_tiles.push({x:x,y:y,ore:t.drop().name});if(t.build!=null&&t.build.tile==t)o.buildings.push({type:t.block().name,x:x,y:y,rotation:t.build.rotation})}print("BOT_STATE:"+JSON.stringify(o))
  ```
  → JSON này đúng khớp schema `bot/state.py` đã định nghĩa sẵn ở Giai đoạn 1,
  không cần sửa gì bên Python.
- Thực thi action: mỗi hành động trong action list (từ `bot/planner.py`)
  dịch trực tiếp thành 1 dòng lệnh:
  ```
  js Vars.world.tile(34,20).setBlock(Vars.content.block("silicon-smelter"), Team.sharded, 0);print("BOT_OK")
  ```

#### Việc cần làm cụ thể (theo thứ tự)

1. Cài Java, tải `server-release.jar` (mục 1-2 ở trên), chạy thử
   `java -jar server-release.jar`, gõ tay `host` rồi gõ tay 1 lệnh `js
   print(Vars.world.width())` để xác nhận lệnh `js` hoạt động và world đã
   load — **đây là bước xác nhận đầu tiên, làm trước mọi thứ khác**.
2. Gõ tay thử 1 lệnh `js ...setBlock(...)` xem building có xuất hiện thật
   trong game không (nếu chạy bản có đồ hoạ/join vào server bằng client thì
   thấy trực quan; headless thuần thì chỉ xác nhận qua state JSON đọc lại).
3. **`bot/mod_bridge.py` — đã viết, CHƯA TEST.** `MindustryServer` class:
   `start()` mở server qua `subprocess`, `host()` gửi lệnh host, `read_state()`
   gửi JS quét state trả về đúng schema `bot/state.py`, `execute(actions)`
   dịch action list của `plan_build()` thành lệnh `js setBlock(...)`. Đọc kết
   quả bằng cách tìm marker cố định (`BOT_STATE:`, `BOT_OK:`) làm chuỗi con
   trong dòng log — cách này né được việc chưa biết chính xác định dạng mã
   màu ANSI server in ra (xem "còn chưa chắc chắn" bên dưới).
4. **`bot/live_run.py` — đã viết, CHƯA TEST.** Vòng lặp chat thật, ghép toàn
   bộ: `input()` → `parse_command()` → `read_state()` →
   `grid_from_state()` → `plan_build()` → `execute()`. Đây chính là kịch bản
   "chat rồi bot tự xây" bạn mô tả từ đầu — chỉ còn thiếu bước chạy thật.

**Việc đầu tiên cần làm khi có Java**: sửa `JAR_PATH` trong
`bot/live_run.py` thành đường dẫn thật tới `server-release.jar` đã tải, rồi
chạy `python bot/live_run.py`, gõ thử `"xây nhà máy silicon"`. Nếu lỗi
timeout ở `_wait_for_marker` (`bot/mod_bridge.py`), copy nguyên log server in
ra lúc đó gửi lại — vì đó đúng là điều "chưa chắc chắn" ở mục dưới, cần log
thật mới sửa đúng được.

#### Còn chưa chắc chắn, cần test thật mới biết (không đoán bừa)

- Định dạng chính xác dòng log server in ra khi dùng `info()` (có mã màu ANSI
  kiểu `&fi&lw&fb` — cần thử để biết cách strip khi parse từ Python).
- `runConsole()` chạy trên thread nào — có an toàn khi gọi liên tục nhiều
  lệnh `js` liên tiếp không, hay cần đợi giữa các lệnh.
- Quét toàn bộ tile mỗi lần đọc state (`width × height` tiles) có đủ nhanh
  trên map lớn không — nếu chậm thì thu hẹp vùng quét quanh vị trí liên quan
  thay vì quét cả map.

#### Phương án dự phòng nếu cách trên không ổn

Nếu lệnh `js` bị giới hạn quyền hoặc không đủ linh hoạt khi test thật, quay
lại phương án mod riêng (JS mod file trong thư mục `mods/`, xem
https://github.com/Anuken/Mindustry/wiki/Modding) — phức tạp hơn (cần
`mod.json` + quản lý vòng đời mod) nhưng cùng dùng lại đúng các API đã xác
nhận ở bảng trên.

## Giai đoạn 3 — ghép toàn bộ

Nối Python (giai đoạn 1) với mod (giai đoạn 2) qua socket, chạy thử lệnh
chat thật trên map thật, kiểm tra building xuất hiện đúng vị trí và nối
đúng belt.

## Vá 2 lỗ hổng phát hiện khi trace thử 1 lệnh cụ thể

Câu lệnh thử: *"xây nhà máy khai thác đồng tối ưu nhất và dẫn tài nguyên về
nhà chính"*. Chạy thật (không đoán) thì lộ ra:

1. **Parser không hiểu "khai thác"** — `BUILDING_PHRASES` chỉ có "máy
   khoan"/"drill" cho mechanical-drill, không có "khai thác". **Đã thêm**
   `"khai thác": "mechanical-drill"`.
2. **Bug thật: build drill đơn lẻ không nối gì tới core cả.**
   `plan_build()` nhánh `kind=="drill"` trước đây chỉ đặt drill rồi
   `return actions` ngay — không hề gọi `find_belt_path` tới core, dù
   nhánh `kind=="factory"` ngay bên dưới đã có sẵn logic tự nối belt tới
   nguồn. Nghĩa là *"dẫn tài nguyên về nhà chính"* — đúng phần quan trọng
   nhất câu lệnh — trước đây **không làm gì cả**, không báo lỗi, chỉ âm
   thầm bỏ qua. **Đã sửa**: sau khi đặt drill, nếu map có core thì tự BFS
   route belt tới core (giống hệt cách nhánh factory làm), báo lỗi rõ nếu
   không tìm được đường thay vì im lặng bỏ qua.
3. **Chưa sửa (nằm ngoài phạm vi 2 lỗi trên, cố ý để lại)**: "tối ưu nhất"
   hiện là chữ vô nghĩa với hệ thống — `find_unmined_ore()` chỉ quét map
   theo thứ tự trên-trái xuống, chọn mỏ **đầu tiên gặp**, không so sánh
   nhiều mỏ để chọn tốt nhất. Lớp học/scorer (`bot/scorer.py`) hiện chỉ nối
   vào nhánh đặt building factory, chưa nối vào việc chọn mỏ cho drill.

Đã chạy lại `evaluate_layout` (luồng A) xác nhận đồng **thực sự chảy** từ
drill về core (0.3692/s) sau khi vá, không chỉ action list trông hợp lý.
Đã chạy lại toàn bộ demo cũ (`example_run.py`, `actions_demo.py`,
`learn_demo.py`) — không hỏng gì.

### Bug thứ 2 (cùng loại, phát hiện ngay sau khi vá bug 1)

Câu lệnh thử tiếp: *"lắp nhà máy silicon và nối từ drill đã có trước đó vào
cho tôi. Dẫn đầu ra của nhà máy silicon về core"*. Chạy thật thì:

- **Phần "nối từ drill có sẵn" tự động đúng** — không phải vì bot hiểu yêu
  cầu đó (parser thực ra bỏ qua toàn bộ câu phụ, chỉ đọc ra
  `{"action":"build","building":"silicon-smelter"}`), mà vì hành vi mặc
  định của `plan_build()` vốn đã luôn ưu tiên dùng producer có sẵn
  (`find_producer`) trước khi đặt drill mới — tình cờ khớp ý muốn.
- **Phần "dẫn đầu ra về core" bị bug y hệt bug 1, chỉ khác nhánh code**:
  nhánh `kind=="factory"` chỉ nối belt **nguồn → factory** (input), không
  hề nối **factory → core** (output). `evaluate_layout` xác nhận core nhận
  đúng `0.0000/s` dù silicon-smelter sản xuất `0.2/s` — mất hoàn toàn giữa
  đường, không báo lỗi.
- **Đã sửa**: sau khi nối input xong, nếu map có core thì tự BFS route belt
  từ đầu ra factory tới core (cùng pattern với bug 1), báo lỗi rõ nếu không
  tìm được đường. Xác nhận lại: core nhận đúng `0.2000/s` sau khi vá. Chạy
  lại toàn bộ demo cũ — không hỏng gì (map giả trong các demo không có core
  nên nhánh mới tự bỏ qua đúng như thiết kế, không lỗi).

**Bài học chung từ cả 2 bug**: `plan_build()` có 2 nhánh riêng (drill,
factory), mỗi nhánh tự lo phần "nối input", nhưng **không nhánh nào tự nối
output tới đích cuối (core)** cho tới khi bị phát hiện qua trace thực tế
2 lần liên tiếp. Nếu sau này thêm building kind mới, cần nhớ kiểm tra lại
điều này thay vì giả định "auto-connect" đã tự động phủ hết.

## Sự thật về "danh sách hành động": chỉ có 2 API gốc, không phải 4-5 lệnh riêng

Tra `core/src/mindustry/entities/comp/BuildingComp.java` (định nghĩa thật
building instance làm được gì) thì game **chỉ có đúng 2 API thay đổi
trạng thái**:

1. `tile.setBlock(block, team, rotation)` — xây/xóa (= đặt block "air")/xoay
   (= đặt lại cùng block, rotation khác) **thực ra là cùng 1 lệnh**. Tôi
   tách thành 3 action riêng ở tầng bot cho dễ hiểu, không phải game có 3
   lệnh khác nhau.
2. **`building.configureAny(value)`** — API thật, tách biệt hoàn toàn,
   dùng để chỉnh **cấu hình bên trong** building (lọc item cho sorter, text
   cho message block, on/off cho switch...). Bot lúc đầu **bỏ sót hoàn
   toàn** action này cho tới khi bị hỏi "action có đúng danh sách thật
   không" mới tra lại và phát hiện ra.

"Nối lại đường ray" (reroute) không phải lệnh gốc của game — là bot tự ghép
(xoá belt cũ bằng setBlock(air) + định tuyến lại bằng setBlock), dùng đúng
API thật (1) nhưng hành vi ghép nằm ở tầng bot.

## Hỗ trợ đủ 5 loại lệnh: xây, xóa, xoay, nối lại đường ray, cấu hình

Trước đó `command_parser.py` chỉ nhận diện lệnh xây. Đã mở rộng:

- **`bot/command_parser.py`**: thêm `ACTION_PHRASES` (xóa/phá/dỡ/gỡ → delete,
  xoay/quay/đổi hướng → rotate, nối lại/chỉnh lại đường ray → reroute),
  `DIRECTION_WORDS` (đông/tây/nam/bắc, phải/trái/lên/xuống → rotation index).
- **Vấn đề mơ hồ khi có nhiều building cùng loại** (vd 2 máy khoan): bot
  **không tự đoán** — báo lỗi liệt kê toạ độ từng cái, yêu cầu người dùng nói
  rõ. 3 cách chỉ rõ, ưu tiên theo thứ tự tự nhiên nhất trước:
  1. Với drill: nói loại ore ("máy khoan **than**") — tự nhiên nhất.
  2. Toạ độ: "máy khoan (2,2)".
  3. Thứ tự: "máy khoan **thứ 2**".
- **`bot/planner.py`**: `resolve_target(grid, building_name, hint)` xử lý cả
  3 cách trên; `plan_delete`/`plan_rotate`/`plan_reroute` mới; `plan_reroute`
  dò đường belt cũ bằng `trace_belt_path` (luồng A), xoá, rồi định tuyến lại
  bằng BFS y hệt lúc xây mới; `plan(grid, command, ...)` — dispatcher chung
  theo `command["action"]`, `bot/live_run.py` đã đổi sang gọi hàm này.
- **`simulator/grid.py`**: thêm `Grid.remove(building)`.
- **`bot/mod_bridge.py`**: `execute()` giờ xử lý `op="remove"` — về bản chất
  vẫn là `setBlock`, chỉ đổi tên block sang `"air"` (xác nhận thật:
  `Blocks.java` có `air = new AirBlock("air")`, khớp cách bridge tra block
  theo string tên đã dùng cho các action khác).
- **`bot/actions_demo.py`** — đã chạy và xác nhận cả 4 loại lệnh trên map
  giả, gồm cả 2 trường hợp mơ hồ (báo lỗi đúng, không tự đoán) và 1 trường
  hợp chỉ rõ ore để hết mơ hồ.

### Lệnh thứ 5: cấu hình (`configureAny`)

- **`tools/generate_catalog.py`** — thêm phủ class `Sorter` (block đơn giản
  nhất dùng configure: lọc theo 1 Item, xem `Sorter.java:
  config(Item.class, (tile,item)->tile.sortItem=item)`). Sinh ra
  `sorter`/`inverted-sorter`, `config_type="item"`.
- **`simulator/buildings.py`**: `BuildingType` thêm field `config_type`
  (`None` = không cấu hình được, `"item"` = nhận 1 Item làm giá trị).
- **`bot/command_parser.py`**: thêm phrase `cấu hình`/`đặt bộ lọc`/`chỉnh
  bộ lọc` → action `configure`; `_find_item()` — tra tên item **bất kỳ**
  (không chỉ ore như trước), thử tên tiếng Việt quen thuộc trước
  (than/đồng/cát/chì/titan), fallback khớp thẳng tên tiếng Anh thật (nhiều
  item như "silicon", "graphite", "plastanium" người chơi hay gọi nguyên
  tên gốc, không có tên Việt riêng).
- **`bot/planner.py`**: `plan_configure()` — dùng lại `resolve_target()` y
  hệt delete/rotate, kiểm tra `config_type` trước khi cho cấu hình (báo lỗi
  rõ nếu building không cấu hình được thay vì cứ gửi lệnh), validate value
  phải là tên item thật trong `ITEMS`.
- **`bot/mod_bridge.py`**: `execute()` tách hẳn nhánh xử lý `op="configure"`
  — gọi `building.configureAny(Vars.content.item("..."))`, **khác hẳn**
  `setBlock` dùng cho place/remove (xem mục trên — đây đúng là 2 API gốc
  khác nhau của game, không phải cùng 1 lệnh biến tấu).
- Đã test trên map giả: cấu hình sorter lọc theo đồng ra đúng
  `{"op":"configure","x":6,"y":6,"value":"copper"}`; thiếu item thì báo
  `unknown` thay vì đoán bừa.

## Tự động sinh danh mục building từ source thật (không gõ tay từng cái nữa)

Trả lời đúng bức xúc "chẳng lẽ tôi phải cập nhật từng lệnh như thế này" —
đúng là gõ tay từng building (5 cái) không scale. Đã sửa tận gốc:

- **`tools/generate_catalog.py`** — đọc `reference/Blocks.java` +
  `reference/Items.java` thật, tự cắt đúng thân từng block definition (kỹ
  thuật brace-matching, không phải parser Java đầy đủ), regex lấy field cần
  cho 3 loại `Drill`/`Conveyor`/`GenericCrafter` (khớp 3 kind mà
  `simulator/sim.py` biết tính throughput). Chạy: `python
  tools/generate_catalog.py`.
- **Kết quả thật** (chạy 2026-07-13): **22 item, 4 drill, 2 belt, 12 nhà
  máy** tự sinh — so với 5 building gõ tay trước đây. Đối chiếu số liệu
  `graphite-press`/`silicon-smelter` sinh ra khớp 100% với số đã tính tay và
  test trước đó, xác nhận script đúng chứ không phải chỉ "chạy không lỗi".
- **5 block bị bỏ qua có lý do rõ ràng** (in ra khi chạy script, cũng lưu ở
  `simulator/generated_catalog.py:SKIPPED`): `melter`, `electrolyzer`,
  `cryofluid-mixer`, `spore-press`, `coal-centrifuge` — các block này dùng
  input/output là **liquid**, không phải item, nên không khớp pattern
  script hỗ trợ. Không phải bug — đến khi nào simulator mô hình hoá liquid
  (đang là giới hạn v1 đã ghi trong README) thì mới sinh được các block này.
- **`simulator/buildings.py`** — bỏ hết `MECHANICAL_DRILL`/`CONVEYOR`/... gõ
  tay, giờ import `GENERATED_ITEMS`/`GENERATED_BUILDINGS` từ
  `simulator/generated_catalog.py`, chỉ giữ tay `CORE` (không phải
  Drill/Conveyor/GenericCrafter nên script không phủ tới). Đã chạy lại
  **toàn bộ** demo cũ (`run_example.py`, `example_run.py`,
  `actions_demo.py`, `learn_demo.py`) — ra đúng số y hệt trước, xác nhận
  không phá gì.
- **Khi Mindustry ra bản mới / bạn thêm mod**: tải lại `reference/Blocks.java`
  mới nhất, chạy lại `tools/generate_catalog.py`, xong — không cần sửa tay
  `buildings.py`.

## Bộ dịch lệnh bằng LM Studio (thay dict, tổng quát hoá được) -- ĐÃ NÂNG CẤP

### Vì sao nâng cấp (bối cảnh thật)

Test thật câu "Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2, 1
nguồn dẫn về core, 1 nguồn tạo silicon" qua `bot/command_parser.py:parse_commands()`
(dict-based) cho thấy **3/5 đoạn bị bỏ qua silently**: "tách...làm 2", "1
nguồn dẫn về core", "1 nguồn tạo slicion" (kể cả không có lỗi chính tả) đều
không có đại diện trong ngữ pháp dict (tách câu chỉ theo dấu phẩy/"và" thành
Ý ĐỘC LẬP, không hiểu cấu trúc PHÂN NHÁNH). Được yêu cầu rõ: không vá thêm
ngữ pháp dict cho từng trường hợp cụ thể (không scale), mà nâng LM Studio
lên làm bộ dịch CHÍNH, đủ schema để tự hiểu ngữ nghĩa nhiều cách diễn đạt.

### Đã làm (thiết kế lại hoàn toàn `bot/llm_parser.py`)

- **Trả về DANH SÁCH lệnh** (JSON array), không còn 1 lệnh đơn -- model tự
  tách câu ghép nhiều ý (thay hẳn vai trò `parse_commands()` dict cho việc
  này), hiểu được NGỮ NGHĨA thay vì chỉ tách theo dấu câu.
- **2 action mới**: `split` (router, N nhánh không điều kiện) và
  `filter_split` (sorter, chia theo item khớp/không khớp filter) -- map
  thẳng tới `bot/planner.py:plan_split_command()`/`plan_filter_split_command()`
  (mới thêm, xem dưới). Đích (`destination`) là `{"kind":"core"}` hoặc
  `{"kind":"build","building":"<tên factory>"}` -- nếu building đích chưa có
  trên map, planner TỰ ĐẶT MỚI và tự nối luôn input CÒN THIẾU khác của nó
  (vd silicon-smelter cần cả than lẫn cát, chỉ cần khai 1 trong 2 qua nhánh
  split, cát bot tự tìm nguồn có sẵn).
- **`SUPPORTED_KINDS` mở rộng** thêm pump/sorter/router (trước chỉ
  drill/belt/factory) -- khớp đúng khả năng thật của planner, không thiếu.
- **Sentinel `"drill"`**: model có thể dùng "drill" (thay vì tên tier cụ
  thể) khi người dùng không nói rõ tier -- planner tự chọn tier rẻ nhất đủ
  mạnh, khớp cơ chế `select_drill_type()` đã có.
- **`_validate()` khoan dung từng phần tử**: 1 action sai/thiếu field chỉ bị
  loại khỏi mảng kết quả (giống dict parser bỏ qua đoạn không hiểu được),
  không làm hỏng cả response.
- **`parse_commands_auto(text)`** — hàm chính nên dùng: thử LM Studio trước,
  lỗi kết nối/JSON sai thì tự rơi về dict parser
  (`bot/command_parser.py:parse_commands`), không crash cả bot.
- **`bot/live_run.py`** đã đổi sang gọi `parse_commands_auto` (số nhiều).

### `bot/planner.py` -- các hàm mới để hỗ trợ split/filter_split từ lệnh chat

- **`_find_or_build_factory_sources()`** -- tách ra từ `plan_build()`'s
  factory branch (refactor không đổi hành vi), dùng chung cho cả build
  factory bình thường LẪN khi 1 factory là ĐÍCH của split (chỉ thiếu input
  KHÁC input đã có qua nhánh split, xem `exclude_item`).
- **`_resolve_split_destination()`** -- quy `{"kind":"core"|"build",...}` từ
  lệnh chat thành 1 footprint cụ thể, tự đặt mới + tự nối input còn thiếu
  nếu là factory chưa có trên map.
- **`plan_split_command()`/`plan_filter_split_command()`** -- lệnh cấp cao,
  nối vào `plan()` dispatcher qua action `"split"`/`"filter_split"`.
- **`_route_or_branch_from_producer()`** + **`_clear_belt_chain()`** -- **vá
  1 bug thật phát hiện khi test end-to-end kịch bản trên**: nguồn (drill
  than/cát) THƯỜNG ĐÃ có belt dẫn đi nơi khác rồi (vd tự nối về core từ 1
  lệnh build trước đó) trước khi lệnh split/filter_split hay 1 factory mới
  cần dùng lại nguồn đó chạy tới -- code cũ (`_route()`) báo lỗi "không tìm
  được đường" ngay tại `output_tile()` bị chiếm, hoặc tệ hơn: coi nhầm
  "output_tile kề đích mới" là ĐÃ NỐI XONG dù belt hiện có trỏ hướng khác
  hẳn (`find_belt_path()`'s early-return theo `touches_target` không kiểm
  tra `start` có bị chiếm hay không). Sửa: trace xem belt cũ dẫn tới đâu,
  xoá chuỗi belt đó, dùng lại `plan_split()` (router thật) để chia cho CẢ
  đích cũ lẫn đích mới -- đúng cơ chế thật khi 1 nguồn cần nuôi >1 nơi.
  `plan_split()`/`plan_filter_split()` giờ cũng tự gọi `_clear_belt_chain()`
  ngay từ đầu (source có thể đã có belt trước khi lệnh split chạy tới).
- **Đổi contract**: `sources`/`liquid_sources` trong `_find_or_build_factory_sources()`
  giờ trả về `(item_name, producer_building)` thay vì `(item_name,
  output_tile)` -- cần building THẬT để trace/xoá belt cũ, không chỉ toạ
  độ. `featurize_target_spot()` (dùng bởi `bot/feedback.py`/`bot/learn_demo.py`)
  cũng đổi theo, gọi `producer.output_tile()` nội bộ.

### Bug thật thứ 2 -- phát hiện bằng cách TỰ ĐÓNG VAI model (không phải response viết sẵn)

Được yêu cầu tự đọc đúng system prompt thật của `bot/llm_parser.py`, tự suy
luận JSON như 1 model thật sẽ trả cho đúng câu người dùng đã hỏi, rồi chạy
JSON đó qua `_validate()` + `plan()` thật -- khác `bot/llm_split_demo.py`
(response viết tay khớp sẵn với code), lần này JSON là suy luận độc lập,
lộ ra ngay 1 bug mới: chọn `"split"` (router) thay vì `"filter_split"` (vì
câu nói "tách BĂNG CHUYỀN ra làm 2" là chia đôi luồng chung, không phải lọc
theo loại item) -- `plan_split()` báo lỗi "không tìm được đường belt từ
router tới đích thứ 2" dù về logic hoàn toàn hợp lệ.

Nguyên nhân: silicon-smelter (đích thứ 2) được `_resolve_split_destination`
tự đặt NGAY SÁT router (0 ô cách, không cần belt ở giữa) -- nhưng vòng lặp
tìm đường của `plan_split()`/`plan_filter_split()` (nhánh rẽ) coi MỌI ô kề
router bị chiếm là "chướng ngại vật, bỏ qua", kể cả khi ô đó CHÍNH LÀ đích
cần tới! Trong khi đó `simulator/sim.py:_trace_branching` (tầng tính
throughput) coi bất kỳ building nào kề router là 1 nhánh hợp lệ, không cần
belt -- 2 tầng code hiểu "occupied" theo 2 nghĩa khác nhau. Vá bằng cách
kiểm tra riêng "đích nằm ngay ô kề" TRƯỚC khi coi ô đó là chướng ngại (áp
dụng cho cả nhánh router của `plan_split()` lẫn nhánh rẽ của
`plan_filter_split()`). Xem `bot/split_router_adjacent_demo.py`.

### Bug thật thứ 3 -- phát hiện bằng cách người dùng hỏi thẳng "có tự nối X về core không?"

`_resolve_split_destination` (khi tự đặt MỚI 1 factory làm đích split, vd
silicon-smelter) trước đó chỉ lo INPUT của factory đó (qua
`_find_or_build_factory_sources`) -- QUÊN nối luôn ĐẦU RA của nó về core.
Factory craft được bình thường (input đủ, `output_rate` > 0 trong
`evaluate_layout`), nhưng silicon nó tạo ra không đi đâu cả (`output_tile()`
bỏ trống, không connection nào XUẤT PHÁT từ nó) -- về mặt game thật sẽ chất
đầy nội bộ rồi ngừng craft, không phải lỗi tính toán mà là thiếu 1 bước lập
kế hoạch. Cùng loại bug (và cùng cách vá bằng `_connect_to_core()`) như
`plan_build`'s drill/factory branch đã gặp và vá trước đó (xem mục "Vá 2 lỗ
hổng..." ở trên) -- chỉ là lần XUẤT HIỆN THỨ 3, ở 1 đường code MỚI
(`_resolve_split_destination`) không được nhớ áp dụng cùng pattern. Đã vá:
gọi `_connect_to_core(grid, actions, target, ...)` ngay sau khi factory đích
được đặt mới. Xem assertion mới trong `bot/split_router_adjacent_demo.py`
(kiểm tra connection `silicon-smelter -> core` tồn tại thật, không chỉ
`output_rate > 0`).

### Đã test (không cần LM Studio thật)

- `bot/split_command_demo.py` -- gọi trực tiếp `plan()` với lệnh
  `filter_split` cấu trúc y hệt câu người dùng hỏi thật (than tách 2 nhánh,
  1 core 1 silicon-smelter), xác nhận silicon-smelter CHẠY ĐƯỢC (bot tự nối
  cát còn thiếu). Đây là test PHÁT HIỆN RA bug `_route_or_branch_from_producer`
  ở trên (lần chạy đầu tiên FAIL với lỗi "không tìm được đường belt", debug
  bằng `_debug_split.py`/`_debug_split2.py` (đã xoá sau khi dùng) mới lộ ra
  nguyên nhân thật).
- `bot/llm_split_demo.py` -- **KHÔNG gọi LM Studio thật** (không có server
  chạy sẵn), thay vào đó giả lập đúng response JSON model NÊN trả cho đúng
  câu người dùng đã hỏi, chạy qua `_validate()` rồi `plan()`, xác nhận toàn
  bộ pipeline logic đúng. **KHÔNG chứng minh model thật sẽ tự sinh đúng JSON
  này** -- cần bạn bật LM Studio thật để xác nhận bước cuối cùng đó.

### Việc cần làm khi có LM Studio thật (bổ sung vào checklist Giai đoạn 2)

1. Mở LM Studio, tải 1 model, bật **Local Server** (mặc định cổng 1234).
2. Model đề xuất (xem thêm docstring đầu `bot/llm_parser.py`):
   - **Qwen2.5-7B-Instruct** — khuyên dùng trước, tuân thủ JSON schema tốt,
     tiếng Việt ổn. Đây chỉ là gợi ý, đổi tay được.
   - Máy yếu hơn: Qwen2.5-3B-Instruct hoặc Phi-3.5-mini-instruct.
   - Không cần model quá lớn — đây là tác vụ trích xuất JSON theo schema cố
     định, không cần suy luận sâu. Schema giờ PHỨC TẠP HƠN (mảng nhiều lệnh
     + split/filter_split lồng nhau) so với bản cũ -- nếu Qwen2.5-7B không
     tuân thủ tốt, thử model lớn hơn hoặc rút gọn system prompt.
3. Sửa `DEFAULT_MODEL` trong `bot/llm_parser.py` cho khớp đúng tên model bạn
   load (LM Studio đặt tên theo file model, không phải "Qwen2.5-7B-Instruct"
   suông — kiểm tra tên chính xác trong tab "My Models" của LM Studio).
4. Chạy thử trực tiếp (không cần Java/Mindustry, chỉ cần LM Studio đang
   chạy):
   ```
   python -c "from bot.llm_parser import parse_commands_llm; print(parse_commands_llm('Khai thác than, và cát cho tôi, tách băng chuyền ra làm 2, 1 nguồn dẫn về core, 1 nguồn tạo silicon'))"
   ```
   So kết quả với `bot/llm_split_demo.py`'s `FAKE_LLM_RESPONSE` -- nếu model
   trả gần đúng dạng đó thì pipeline chạy được ngay; nếu lệch nhiều, gửi lại
   output thật để chỉnh system prompt dựa trên phản hồi thật của model (có
   thể cần thêm ví dụ cụ thể vào prompt nếu model không tự suy ra được cấu
   trúc split/filter_split từ mô tả suông).

## Học từ phản hồi (Cách 1 + Cách 3, không phải RL, không phải LLM context)

Trả lời câu hỏi "bot đặt sai, tôi chê, lần sau bot có nhớ không?" — mặc định
KHÔNG (planner là hàm thuần, không có bộ nhớ). Đã thêm 1 lớp tuỳ chọn để giải
quyết việc này, **không cần train model lớn, không phụ thuộc cửa sổ ngữ cảnh
LLM**:

- **`bot/preferences.py` (Cách 1 — luật cứng)**: file `preferences.json`
  (không commit, xem `.gitignore`) lưu luật kiểu `min_distance_from_core`.
  Ứng viên vi phạm bị loại thẳng trước khi xếp hạng.
- **`bot/scorer.py` (Cách 3 — preference learning thật)**: `Scorer` giữ 1
  vector trọng số tuyến tính (`total_belt_length`, `distance_to_core`...),
  lưu ở `scorer_weights.json` (không commit). `update(features_win,
  features_lose)` dịch trọng số theo cặp so sánh kiểu perceptron — đây là
  "học" thật (tham số thay đổi từ dữ liệu, tổng quát hoá được), khác Cách 1
  (chỉ đúng luật đã viết) và Cách 2 (không lệ thuộc model/ngữ cảnh).
- **`bot/planner.py`**: `find_free_area_candidates()` sinh nhiều ứng viên
  thay vì dừng ở cái đầu tiên; `featurize_target_spot()` biến 1 ứng viên
  thành vector đặc trưng; `plan_build(grid, command, scorer=..., 
  preferences=...)` — 2 tham số này **tuỳ chọn**, không truyền thì hành vi y
  hệt bản gốc (đã test lại, không phá code cũ).
- **`bot/feedback.py`**: `record_feedback(...)` — bạn cung cấp đúng 2 toạ độ
  (chê spot nào, thích spot nào), hàm này tính đặc trưng 2 bên rồi gọi
  `scorer.update()` + lưu đĩa. Bot **không tự đoán** lý do sai nếu bạn chỉ
  nói "sai" chung chung — luôn cần 1 phương án cụ thể để so sánh.
- **`bot/learn_demo.py`** — đã chạy và xác nhận vòng học hoạt động thật: map
  giả có nhiều ứng viên đặt `silicon-smelter`, mặc định chọn `(4,7)`; mô
  phỏng phản hồi chê `(4,7)` thích `(3,6)` (xa core hơn, cùng độ dài belt);
  sau 1 lần cập nhật, **replan cùng lệnh trên map sạch (chưa từng thấy state
  đã sửa) ra đúng `(3,6)`** — chứng minh không phải nhớ cứng 1 tình huống mà
  trọng số đã thật sự đổi (`distance_to_core` từ 0.0 → 1.0), ảnh hưởng tới
  toàn bộ ứng viên tương lai có đặc trưng tương tự.

## Trạng thái hiện tại (đã làm xong)

- **Giai đoạn 1 — XONG, đã chạy và xác nhận.** Xem `bot/`:
  - `command_parser.py` — dict tiếng Việt → tên building.
  - `state.py` — dựng `Grid` từ JSON state (hợp đồng dữ liệu cho mod ở
    Giai đoạn 2).
  - `planner.py` — auto-connect thật: tìm nguồn nguyên liệu (ưu tiên building
    có sẵn, không có thì tự đặt drill mới), tìm chỗ trống, định tuyến belt
    bằng BFS, xuất danh sách hành động `place`. Nay có thêm lớp học tuỳ chọn
    (xem mục trên).
  - `example_run.py` — chạy thử `"xây nhà máy silicon"` trên state giả (có
    sẵn drill than, có mỏ cát chưa khai thác) → tự đặt drill cát mới + nối
    2 đường belt (than, cát) tới silicon-smelter. Đã dùng `evaluate_layout`
    của luồng A để xác nhận silicon thực sự chảy ra (0.2/s, bị giới hạn bởi
    tốc độ cung cát) — không chỉ tọa độ hợp lệ mà dòng vật liệu đúng thật.
  - `simulator/buildings.py`, `simulator/sim.py` đã mở rộng để hỗ trợ recipe
    nhiều input (silicon-smelter cần cả than lẫn cát cùng lúc).
- **Giai đoạn 2 (cầu nối `js` console) — code xong, CHƯA TEST** (chưa có
  Java). Xem `bot/mod_bridge.py`, `bot/live_run.py`.
- **Giai đoạn 3 (ghép nối)** — đã ghép code trong `bot/live_run.py`, còn lại
  là chạy thử thật + sửa lỗi khi có Java (xem mục Giai đoạn 2 ở trên).
- **Học từ phản hồi** — xong, đã test bằng `bot/learn_demo.py` (xem mục trên).
  Chưa nối vào `bot/live_run.py` (vòng lặp chat thật chưa gọi `scorer`/
  `record_feedback` — còn là việc thủ công qua script riêng).
- **Danh mục building tự sinh từ source** — xong, đã chạy
  (`tools/generate_catalog.py`), 22 item + 18 building thật (trước đó chỉ 5
  cái gõ tay). Xem mục "Tự động sinh danh mục building" ở trên.
- **Bộ dịch lệnh LM Studio** — code xong (`bot/llm_parser.py`), **CHƯA TEST
  gọi model thật** (chỉ test được phần fallback). `bot/live_run.py` đã đổi
  sang dùng `parse_command_auto`. Việc cần làm khi có LM Studio: xem mục
  "Bộ dịch lệnh bằng LM Studio" ở trên.

## Toàn bộ hệ thống trong package `distribution` của Mindustry (tra source thật)

Trước đây bot chỉ xử lý Router + Sorter. Người dùng hỏi "có bao nhiêu hệ
thống" — đã tải và đọc toàn bộ 20 file trong
`core/src/mindustry/world/blocks/distribution/` (repo Anuken/Mindustry,
nhánh master) để liệt kê đầy đủ, không đoán. Kết quả: **9 cơ chế khác nhau**
(không tính biến thể tier), cộng 1 interface hỗ trợ UI không phải cơ chế vận
chuyển.

| # | Cơ chế | File nguồn | Mô tả (tra method thật) | Trạng thái trong bot |
|---|---|---|---|---|
| 1 | Belt thẳng | `Conveyor`, `ArmoredConveyor`, `StackConveyor` | Di chuyển item theo 1 hướng cố định (`rotation`). `StackConveyor` gom nhiều item rồi xả hàng loạt — cơ chế stacking không model. | Conveyor: **đã có**. StackConveyor: cố ý bỏ qua (`KNOWN_UNMODELED`). |
| 2 | Conduit (chất lỏng) | `Conduit`, `ArmoredConduit` | Tương đương belt nhưng cho liquid. | **Đã có.** |
| 3 | Router | `Router.java` | `acceptItem`/`handleItem` chia đều round-robin cho tất cả hướng hợp lệ trừ hướng vào. | **Đã implement** (`plan_split`). |
| 4 | Sorter | `Sorter.java` | Item khớp `filter_item` → đi thẳng; không khớp → rẽ 2 bên. | **Đã implement** (`plan_filter_split`). |
| 5 | Junction (giao lộ) | `Junction.java` | `DirectionalItemBuffer` 4 ngăn riêng theo hướng vào; mỗi hướng đi thẳng qua `nearby(i)`, KHÔNG rẽ, KHÔNG trộn — cho 2 luồng belt vuông góc cắt nhau tại 1 ô mà không lẫn item. | **Đã implement** (`bot/junction_demo.py`). |
| 6 | Overflow/Underflow Gate | `OverflowGate.java` (field `invert` phân biệt 2 biến thể) | `getTileTarget()`: ưu tiên đi thẳng, chỉ rẽ sang 1 trong 2 bên khi đường thẳng không nhận (đầy) — hoặc ngược lại nếu `invert=true` (ưu tiên rẽ, thẳng chỉ khi cả 2 bên đầy). Khác Router (luôn chia đều) và Sorter (lọc theo loại item) — đây là rẽ **theo tình trạng đầy/rỗng**, không theo loại item. | **Đã implement, xấp xỉ tất định** (xem ghi chú bên dưới; `bot/overflow_gate_demo.py`). |
| 7 | Item Bridge (cầu nối) | `ItemBridge.java`, `BufferedItemBridge.java` (extends ItemBridge, thêm buffer nội bộ = "phase conveyor") | `config(Point2...)` link 2 building bridge cách nhau tối đa `range` ô, item "nhảy" qua khoảng trống bỏ qua chướng ngại ở giữa. | **Đã implement** (`bot/bridge_demo.py`). |
| 8 | Mass Driver | `MassDriver.java` | `fire(target)` bắn nguyên khối item tới driver khác trong tầm `range`, có đạn thật + thời gian nạp lại — vận chuyển theo đợt tầm xa, không phải luồng liên tục. | **Đã implement, xấp xỉ tốc độ trung bình** (`bot/mass_driver_demo.py`). |
| 9 | (Directional) Unloader | `Unloader.java` (world/blocks/**storage**, KHÔNG phải distribution), `DirectionalUnloader.java` | Rút item từ building lưu trữ (vd. container/core) liền kề rồi đẩy ra. `Unloader.java` thật dùng thuật toán ưu tiên ĐỘNG so khớp mọi hàng xóm (không cố định hướng); xấp xỉ bằng mô hình hướng cố định của `DirectionalUnloader` cho cả 2 (xem ghi chú). | **Đã implement, xấp xỉ** (`bot/unloader_demo.py`). |
| — | Interface hỗ trợ UI | `ChainedBuilding.java` | Chỉ là interface đánh dấu building "nối chuỗi được" khi kéo chuột đặt hàng loạt — không phải cơ chế vận chuyển. | Không áp dụng. |

**Hệ Duct — mạng vận chuyển song song hoàn toàn tách biệt (chỉ dùng trên map
Erekir), không nối trực tiếp được với hệ Conveyor:**

| File | Vai trò tương đương bên hệ Conveyor | Trạng thái |
|---|---|---|
| `Duct.java` | = Conveyor (autotiling) | **Đã có** (kind="belt" dùng chung code) |
| `DuctRouter.java`, `StackRouter.java` | = Router (Stack dồn item trước khi bắn hàng loạt) | **Đã có** (kind="router" dùng chung code, không model riêng phần "dồn rồi bắn" của StackRouter) |
| `DuctJunction.java`, `LiquidJunction.java` | = Junction | **Đã có** (kind="junction" dùng chung code) |
| `DuctBridge.java`, `DirectionLiquidBridge.java`, `LiquidBridge.java` | = Item Bridge (bản Duct và bản liquid) | **Đã có** (kind="bridge" dùng chung code) |
| `OverflowDuct.java` | = Overflow Gate | **Đã có** (kind="overflow-gate" dùng chung code) |

→ Vì `tools/generate_catalog.py` phân loại theo **kind cơ chế thật**, không
theo tên class Duct-vs-Conveyor, toàn bộ hệ Duct tự động hoạt động ĐÚNG khi
Junction/Router/Bridge/OverflowGate được implement — không cần code riêng
(xác nhận bằng cách chạy `duct-router` qua cùng bài test round-robin của
`router` thường, ra kết quả giống hệt). Map Erekir (2 loại tài nguyên mới:
beryllium/tungsten, luật xây khác) vẫn NGOÀI scope — chỉ hệ vận chuyển Duct
là dùng được, không phải toàn bộ gameplay Erekir.

**Xấp xỉ đã áp dụng (ghi rõ, không phải số/hành vi thật 100%):**
- **Overflow/Underflow Gate**: cơ chế thật quyết định ĐỘNG lúc runtime dựa
  vào mức đầy hiện tại của đích; simulator này tính throughput ổn định TĨNH
  nên xấp xỉ tất định (overflow luôn ưu tiên thẳng, underflow luôn ưu tiên
  rẽ) — không mô phỏng trạng thái "đầy" thật.
- **Mass Driver**: bắn theo đợt (tích luỹ rồi bắn cả cụm mỗi khi hồi xong);
  xấp xỉ bằng tốc độ trung bình ổn định = `60*driver_capacity/driver_reload`
  (mass-driver mặc định = 36/s), cùng kiểu xấp xỉ đã dùng cho drill/pump.
- **Unloader**: simulator không track tồn kho thật (core/container không có
  số lượng item cụ thể) nên giả định kho liền kề LUÔN còn hàng khi
  `filter_item` được cấu hình rõ; không hỗ trợ "rút bất kỳ thứ gì có trong
  kho" (`filter_item=None` luôn ra 0/s). `Unloader.java` thật (building
  "unloader" phổ biến nhất) dùng thuật toán ưu tiên động so khớp TẤT CẢ hàng
  xóm cùng lúc, không cố định 1 hướng vào/1 hướng ra — xấp xỉ bằng mô hình
  hướng cố định đơn giản hơn của `DirectionalUnloader` cho cả 2 loại.
- **Bridge/Mass Driver linking**: `link_target` do người gọi gán trực tiếp
  (`grid.place(..., link_target=...)` hoặc `link_to` trong JSON state, xem
  `bot/state.py`) — không mô phỏng lại thuật toán tự-tìm-link lúc runtime
  của game thật (`findLink()`), planner luôn quyết định link tại thời điểm
  lập kế hoạch.

### Bug thật thứ 4 -- phát hiện khi người dùng phản biện đúng 1 kết luận trước đó

Đang giải mã 1 schematic thật (`.msch`, xem mục dưới) và tìm thấy 1 vài
`bridge-conveyor` có link config trỏ ra ngoài phạm vi hợp lệ (rác/lỗi thời,
xem mục dưới) — tôi kết luận "bridge chưa link = kẹt tại chỗ, item không đi
đâu cả" và code `sim.py` lúc đó ĐÚNG LÀ làm vậy (`if b.link_target is None:
return [(b, capacity)]` — coi bridge là điểm dừng). Người dùng phản biện:
"Bridge có 1 tính năng, nếu không nối với bất cứ bridge khác nào thì sẽ tự
động chia item ra các đầu còn lại" — tra lại `ItemBridge.java` xác nhận
người dùng ĐÚNG, code cũ SAI:

```java
// updateTile()
hadValidLink = linkValid(tile, other);
if(!hadValidLink){
    doDump();   // <-- dump ra Ô LIỀN KỀ vật lý như building bình thường!
    warmup = 0f;
}
```

`doDump()`/`dumpAccumulate()` là cơ chế dump chuẩn mọi building không có
hướng cố định đều dùng — bridge chưa link (hoặc link hỏng) KHÔNG kẹt, nó chỉ
đơn giản cư xử như 1 building bình thường, đẩy item ra ô kề cạnh vật lý. Đã
sửa `sim.py`: `kind=="bridge"` khi `link_target is None` giờ dùng ĐÚNG công
thức chia đều capacity cho các neighbor hợp lệ (giống hệt `router`), thay vì
coi là điểm dừng. Xem `bot/bridge_demo.py` "Đối chứng 2" — bridge chưa link
nhưng có core kề bên vẫn tự dump ra core thành công.

**Bài học quy trình:** đây là lần đầu trong phiên mà NGƯỜI DÙNG phát hiện ra
lỗi trong 1 cơ chế mà tôi tự tin đã "tra source xong" — vì tôi tra đúng phần
config/link nhưng KHÔNG tra phần xử lý khi thiếu link (`updateTile()`'s
`!hadValidLink` branch). Nhắc lại nguyên tắc: tra source phải bao trùm hết
NHÁNH LOGIC liên quan, không chỉ nhánh "happy path" (có link hợp lệ).

**Chưa nối vào command_parser.py/plan_build** (giống hệt tình trạng ban đầu
của Router/Sorter trước khi có `plan_split`/`plan_filter_split` — gọi trực
tiếp qua `grid.place()`/test script, không qua câu chat): "than đi thẳng vào
X, còn lại rẽ Y" hay "bắc cầu từ A tới B" là câu có cấu trúc phức tạp hơn
`parse_commands()` hiện tách được (cần ngữ pháp lệnh mới cho quan hệ 2 building
+ khoảng cách, chưa được yêu cầu). `plan_build()` hiện chỉ nhận
drill/pump/factory qua lệnh chat; junction/overflow-gate/bridge/mass-driver/
unloader dùng được đầy đủ ở tầng simulator (đặt qua `grid.place()`, tính
throughput đúng) nhưng NLU tiếng Việt cho chúng là việc kế tiếp nếu cần.

**Tóm lại:** 9/9 cơ chế thật trong package `distribution` (+ storage-based
Unloader) đã implement ở tầng simulator, kiểm chứng bằng test riêng cho từng
cái (`bot/junction_demo.py`, `bot/overflow_gate_demo.py`, `bot/bridge_demo.py`,
`bot/mass_driver_demo.py`, `bot/unloader_demo.py`, cộng phần bổ sung
inverted-sorter trong `bot/sorter_split_demo.py` — phát hiện thêm 1 lỗ hổng
thật: Sorter trước đó CHƯA xử lý field `invert`). Hệ Duct hoạt động miễn phí
nhờ kiến trúc phân loại theo kind. 1 bug đệ quy vô hạn thật (RecursionError)
được phát hiện và sửa trong lúc viết `bridge_demo.py`/`mass_driver_demo.py`:
dùng `output_tile()` thay vì `(x,y)` gốc + 1 bước khi teleport qua link, vì
building size>1 khiến bước nhảy cũ vẫn còn nằm trong chân đế chính nó.

## Mạng điện (generator + power-node) -- trả lời câu hỏi "xây nhà máy điện có đầu vào than+nước"

Trước đây: `steam-generator` (đúng loại nhà máy điện dùng than+nước người
dùng hỏi) đã có tên trong catalog nhưng `plan_build()` từ chối đặt ("chưa hỗ
trợ xây... thuộc nhóm 'power'") vì 2 lý do riêng biệt: (1) cơ chế tiêu thụ
"bất kỳ item cháy được" (`ConsumeItemFlammable.java`) không khớp `Recipe`
dataclass (giả định input CỐ ĐỊNH), (2) hoàn toàn chưa có mô hình mạng điện
(cân bằng cung/cầu công suất). Cả 2 đã làm.

### Đã làm

- **`simulator/buildings.py`**: `Item.flammability` (mới), `BuildingType`
  thêm `power_production`/`item_duration`/`min_flammability`/
  `generator_liquid_inputs` (generator), `power_input` (building cần điện),
  `power_range` (power-node).
- **`tools/generate_catalog.py`**: parse `flammability` từ `Items.java`
  (than=1.0, cao nhất). `GENERATOR_CLASSES={"ConsumeGenerator"}` -- CHỈ nhận
  block dùng đúng `ConsumeItemFlammable` (combustion-generator,
  steam-generator); generator khác cơ chế (thermal-generator dựa nhiệt độ
  tile, differential-generator dựa chênh lệch nhiệt 2 liquid,
  chemical-combustion-chamber, pyrolysis-generator, rtg-generator) bị SKIP
  rõ ràng, không đoán. `POWER_NODE_CLASSES={"PowerNode"}` (power-node,
  power-node-large, surge-tower) -- parse `laserRange`. Thêm parse
  `consumePower(X)` cho drill/factory/pump đã hiểu cơ chế từ trước (phát
  hiện: **hầu hết factory thật cần điện** -- silicon-smelter, multi-press,
  pulverizer, plastanium-compressor, phase-weaver, slag-centrifuge,
  surge-smelter, kiln, blast-mixer, pyratite-mixer đều có `consumePower()`
  trong source thật, chỉ graphite-press/silicon-arc-furnace không cần; và
  laser-drill/blast-drill tier 4-5 cũng cần điện, mechanical-drill/
  pneumatic-drill thì không).
- **`simulator/sim.py`**:
  - `_generator_power_rate()`: chọn nhiên liệu flammability CAO NHẤT trong
    số item belt dẫn tới (đủ `min_flammability`), giới hạn bởi tốc độ đốt
    tối đa (`60/item_duration`) và nguồn cung thật + liquid đi kèm nếu có
    (steam-generator cần nước) -- công thức tái dùng nguyên `cycle_rate`
    pattern của factory thường.
  - `_power_capable()`/`_power_linked()`/`_build_power_networks()`: Union-
    Find dựng mạng điện -- 2 building có điện nối nhau nếu CHẠM TRỰC TIẾP
    (chân đế kề nhau, không cần belt) hoặc 1 trong 2 là power-node và cái
    kia nằm trong bán kính `power_range` (xấp xỉ hình tròn Euclidean, không
    phải tia laser/hình chữ nhật chính xác như game thật -- xem
    `PowerNode.java overlaps()`).
  - `_power_satisfaction()`: `satisfaction = min(1, production/needed)` mỗi
    mạng (đúng công thức `PowerGraph.java getSatisfaction()` thật). Nhân lại
    vào `output_rate`/`liquid_output_rate` của building cần điện SAU KHI đã
    tính xong throughput item/liquid bình thường (hậu xử lý 1 lần, KHÔNG lặp
    hội tụ nhiều tick như game thật, KHÔNG lan ngược ảnh hưởng lên building
    khác phụ thuộc -- xấp xỉ đơn giản hoá, xem "Xấp xỉ" bên dưới).
  - `evaluate_layout()` trả thêm `"power_satisfaction"` và
    `"power_production"` trong kết quả.
- **`bot/planner.py`**: `_ensure_powered()` -- nếu building cần điện
  (`power_input>0`) nhưng mạng điện chưa đủ (kiểm bằng `evaluate_layout()`
  thật, không đoán), tự đặt 1 `combustion-generator` (đốt than, rẻ nhất) +
  drill than MỚI RIÊNG (không tái dùng producer có sẵn -- xem "Bug thật"
  bên dưới) + 1 `power-node` cạnh building. Gọi tự động trong `plan_build`'s
  factory branch và `_resolve_split_destination` (khi 1 factory được tự đặt
  làm đích split/filter_split).

### Xấp xỉ đã áp dụng (ghi rõ, không phải hành vi 100% thật)

- Mạng điện tính **1 lần duy nhất** dựa trên throughput item/liquid ổn định
  đã có, KHÔNG lặp hội tụ nhiều tick như game thật (battery làm mượt biến
  động ngắn hạn -- không ảnh hưởng trung bình dài hạn nên bỏ qua, khớp triết
  lý "tính trạng thái ổn định" xuyên suốt simulator này).
  - Hệ quả cụ thể: nếu building A thiếu điện chạy dưới công suất, building B
    nhận input TỪ A sẽ KHÔNG tự động thấy input giảm theo (chỉ A bị giảm
    output, B vẫn tính dựa trên throughput "danh nghĩa" của A trước khi bị
    điện làm giảm). Game thật hội tụ qua nhiều tick nên B cũng bị ảnh hưởng
    dây chuyền; đây là giới hạn 1-pass, chưa lặp lại.
- `_power_linked()` xấp xỉ vùng phủ power-node bằng hình tròn Euclidean từ
  TÂM node, không phải thuật toán chính xác của `PowerNode.overlaps()`
  (circle-vs-rect thật). Đủ chính xác cho việc lập kế hoạch (đặt node có
  trong tầm hay không), có thể sai lệch ở biên rất sát ranh giới tầm.
  Không mô phỏng `maxNodes` (giới hạn số link/1 node).
- `_ensure_powered()` LUÔN tự đặt drill than MỚI cho generator, không tái sử
  dụng nguồn than có sẵn trên map dù có -- **bug thật phát hiện khi test**:
  tái dùng producer có sẵn (`find_producer(grid,"coal")`) có thể trả về
  ĐÚNG drill đang là NGUỒN của lệnh split/build hiện tại, router của nó đã
  dùng hết 4 ô kề cho các nhánh khác, dẫn tới lỗi "không tìm được đường belt
  từ router tới đích thứ 2" (tranh chấp router). Đánh đổi: có thể dư 1 drill
  than nếu bản đồ đã có sẵn nguồn than khác, chấp nhận được để tránh độ phức
  tạp tranh chấp router.
- `_ensure_powered()` chỉ cấp đủ điện cho **1 building vừa xây**, KHÔNG tự
  suy luận/tối ưu lưới điện cho toàn bộ map nhiều building cùng lúc (vd
  không tự "thấy" 1 generator đã dư công suất ở nơi khác trên map và bắc
  cầu tới đó thay vì xây generator mới) -- việc đó là bài toán tối ưu lưới
  điện toàn cục, ngoài phạm vi 1 lượt thêm tính năng.
- KHÔNG mô phỏng `maxNodes`, `battery` (lưu trữ), hay việc generator/building
  có thể bị NỔ khi quá nhiệt/thiếu điện kéo dài (`explosionDamage` trong
  `PowerGenerator.java`) -- chỉ quan tâm throughput trung bình ổn định.

### `plan_build()` hỗ trợ xây generator TRỰC TIẾP (không chỉ tự động qua `_ensure_powered`)

Câu hỏi gốc "xây nhà máy điện có đầu vào là than và nước" là lệnh xây
generator LÀM CHÍNH, không phải 1 factory khác cần điện -- cần nhánh riêng
trong `plan_build()` (khác `_ensure_powered()`, vốn chỉ tự động chèn generator
khi 1 building KHÁC cần điện). Đã thêm nhánh `kind=="generator"`: tự đặt
generator, tự đặt drill than (mặc định, flammability cao nhất) + belt, tự
đặt pump cho MỌI liquid trong `generator_liquid_inputs` (steam-generator cần
nước) + conduit. `bot/command_parser.py` thêm phrase: "nhà máy điện"/"máy
phát điện" → `combustion-generator` (mặc định rẻ nhất, giống "máy khoan"
mặc định tier rẻ), "nhà máy điện hơi nước"/"nhà máy hơi nước" →
`steam-generator` (cần nói RÕ "hơi nước" mới chọn đúng loại cần nước --
dict KHÔNG đọc được "có đầu vào là than và nước" trong câu để tự suy luận,
xem `bot/power_plant_build_demo.py` chứng minh cả 2 trường hợp).
`bot/llm_parser.py` SUPPORTED_KINDS thêm "generator"/"power-node" (LLM
không bị giới hạn cách nói cố định như dict, có thể tự suy luận đúng loại
generator từ mô tả input).

### Đã test (`bot/power_generator_demo.py`, `bot/power_network_demo.py`, `bot/power_plant_build_demo.py`)

- steam-generator: than đủ nhưng KHÔNG đủ đốt hết công suất → công suất tỉ
  lệ đúng phần trăm (không phải bật/tắt nhị phân); cắt nước → 0 điện dù có
  than (cần ĐỦ CẢ 2, không phải trung bình cộng); combustion-generator
  (không cần nước) → chạy được chỉ với than.
- laser-drill (cần điện) không có generator nào → 0/s dù ore/tier đủ điều
  kiện (khác hẳn hành vi TRƯỚC khi có power model — luôn chạy miễn phí).
  Generator CHẠM TRỰC TIẾP → chạy được không cần node. Generator XA (không
  chạm), power-node bắc cầu đúng bán kính laserRange → chạy được; chưa có
  node → vẫn 0/s (chứng minh mạng điện thật sự cần trong tầm, không phải
  "có generator ở đâu đó trên map là đủ").
- `bot/example_run.py`/`bot/learn_demo.py` (silicon-smelter, câu hỏi gốc từ
  đầu dự án) cập nhật lại để có đủ 2 mỏ than (1 cho drill chính, 1 cho
  combustion-generator tự động) -- silicon-smelter giờ output đúng bằng số
  cũ trước khi có power model (0.2/s), xác nhận satisfaction=1.0 (đủ điện
  hoàn toàn) khi `_ensure_powered()` tự cấp đúng.

### Chạy thử lại (không cần Java)

```
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/example_run.py
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/learn_demo.py
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/power_generator_demo.py
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/power_network_demo.py
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/log_learning_demo.py
```
(set `PYTHONIOENCODING` vì console Windows mặc định không phải UTF-8, tiếng
Việt sẽ báo lỗi encoding nếu không set trước.)

## Học từ log gameplay thật (`bot/log_learning.py`)

Trả lời câu hỏi: "nếu tôi chơi, ghi log lại, bot có tự học được không" — CÓ,
nhưng chỉ tự động hoá đúng phần `bot/scorer.py` đã có (chọn VỊ TRÍ đặt
factory), không phải "học chơi game" theo nghĩa lớn (đã bàn kỹ trong hội
thoại, cố ý không xây theo hướng train model riêng).

### Format log

Dùng LẠI đúng format `actions` mà `plan()`/`plan_build()` đã emit từ đầu dự
án (`{"op":"place"|"remove"|"configure"|"rotate", "building":..., "x":...,
"y":..., ...}`) — không có format riêng. Cách tạo log này từ game thật: mod
bắt sự kiện `BlockBuildEndEvent`/`ConfigEvent`/`BuildRotateEvent` (tra thật
từ `EventType.java`, xem đoạn hội thoại về "cách tạo log trong Mindustry") —
CHƯA viết mod này (cần Java, cùng điều kiện chưa đáp ứng như
`bot/mod_bridge.py` từ đầu dự án).

### Cơ chế `extract_feedback_from_log()`

1. Với mỗi hành động "place" 1 **factory** (loại DUY NHẤT plan_build() dùng
   scorer để chọn vị trí trong nhiều candidate — drill/pump chọn theo mỏ
   gần nhất, không qua scorer nên không tạo được cặp so sánh): hỏi
   `plan_build()` xem bot sẽ đề xuất đặt ở đâu NẾU chưa biết bạn chọn gì,
   ghi lại để so với vị trí bạn THỰC SỰ chọn.
2. Phát lại HẾT log xong, kiểm building đó **cuối cùng có thực sự sản xuất
   được gì không** (`evaluate_layout()["output_rate"] > 0`) — chỉ building
   "sống" (nối đủ input+output) mới tạo cặp so sánh cho
   `bot/feedback.py:record_feedback()`.

### Bug thiết kế thật -- phát hiện ngay khi tự test (trước khi báo cho người dùng)

Bản đầu tiên lọc bằng cách so `evaluate_layout()["score"]` NGAY TRƯỚC/SAU
đúng 1 dòng "place" — chạy demo thật thì LUÔN ra 0 cặp feedback, dù rõ ràng
bot đề xuất khác vị trí người chơi chọn. Nguyên nhân: đặt building + nối
belt/điện cho nó thật ra là **NHIỀU dòng log tách biệt** (place building ->
place belt input -> place belt output -> place generator điện...) — dòng
"place" một mình gần như luôn cho điểm 0->0 vì CHƯA nối gì cả, không phản
ánh được kết quả CUỐI CÙNG của cả chuỗi hành động. Sửa: đổi sang kiểm
production tại thời điểm **cuối log** (sau khi mọi belt/điện đã nối xong)
thay vì so lệch trên 1 dòng riêng lẻ — xem `_apply_action`/vòng lặp 2 giai
đoạn trong `extract_feedback_from_log()`.

### Đã test (`bot/log_learning_demo.py`)

Dùng LẠI chính kịch bản đã xác nhận đúng trong `bot/learn_demo.py` (chê
(4,7), thích (3,6)) làm "đáp án đúng" để kiểm tra, thay vì đoán kết quả mới:
dựng 1 log giả lập (chưa có mod ghi log thật) bằng cách tái dùng nguyên các
hàm nội bộ đã kiểm chứng của `planner.py` (`_route`/`_connect_to_core`/
`_ensure_powered`) để tự nối belt+điện cho silicon-smelter tại (3,6), mô
phỏng đúng 1 người chơi đặt xong rồi tự nối tiếp. Kết quả: `extract_feedback_from_log()`
tự tạo đúng 1 cặp feedback, sau khi áp dụng thì `plan_build()` đề xuất lại
CHÍNH XÁC (3,6) — khớp trọng số `distance_to_core: 0.0 -> 1.0` y hệt
`learn_demo.py` (học thủ công), chứng minh pipeline tự động cho ra đúng kết
quả như phản hồi tự tay.

### Giới hạn (ghi rõ)

- Chỉ áp dụng cho factory — drill/pump/generator không đi qua đường chọn có
  scorer.
- Chỉ xét được nếu MỌI input item của factory đó đã có producer SẴN trên map
  tại thời điểm đó trong log (không tự đoán/đặt thêm nguồn).
- Suy luận NGẦM ("bạn xây ở đâu = bạn thích chỗ đó"), không phải phản hồi
  CHỦ ĐỘNG như `record_feedback()` vốn thiết kế cho — bộ lọc "có sản xuất
  được không" giảm nhiễu (loại xây tạm/xây rồi phá) nhưng không loại bỏ hết
  khả năng học nhầm từ 1 lựa chọn ngẫu nhiên lúc chơi mà vẫn tình cờ hoạt
  động được.

## Mod Java ghi log gameplay thật (`mod/`)

Đóng nốt phần "chưa có Java trên máy" ghi từ đầu dự án ở `bot/mod_bridge.py`.
Viết `mod/src/loglearning/LogLearningMod.java` — bắt 3 sự kiện thật
`BlockBuildEndEvent`/`ConfigEvent`/`BuildRotateEvent`, ghi ra
`actions.jsonl` + `initial_state.json` đúng format `bot/log_learning.py` +
`bot/state.py` đã hỗ trợ sẵn (xem `mod/README.md` để biết build/cài/format
đầy đủ, và bảng đối chiếu field với source thật).

Không có Java/Gradle trên máy này nên **chưa build/chưa chạy thật lần nào**
— giống hệt tình trạng `bot/mod_bridge.py` từ Milestone Phase 2. Bù lại, mọi
API dùng trong code (event field, `Tile`/`Building`/`Floor`/`Block` field,
`Jval` — lớp JSON builder có sẵn trong Arc mà Mindustry phụ thuộc, tránh
phải tự viết JSON serializer) đều đã tải trực tiếp từ
`github.com/Anuken/Mindustry`/`github.com/Anuken/Arc` (nhánh `master`) để
đối chiếu từng dòng trước khi viết — kể cả 1 lỗi thật bắt được giữa chừng:
`player.team()` (đoán nhầm là method) → sửa lại `player.team` (field, xác
nhận qua `PlayerComp.java` thật: `@ReadOnly Team team = Team.sharded;`).

Giới hạn đã biết (xem đầy đủ ở `mod/README.md`): chỉ ghi hành động của team
người chơi cục bộ; chỉ hoạt động khi máy này mô phỏng thế giới thật (map
đơn hoặc host server, không phải client vào server người khác); `ConfigEvent
.value` chỉ map đúng cho Item/Liquid/boolean/số (đủ cho sorter, chưa map
Point2 cho bridge/mass-driver link); `initial_state.json` không suy luận lại
`ore_target` cho drill có sẵn từ trước phiên log.

## 3 hệ thống drill còn thiếu (BurstDrill/BeamDrill/WallCrafter)

Bắt đầu từ câu hỏi "trong game Drill có bao nhiêu hệ thống" -- tra ra 5 class
Java khác nhau (`Drill`, `BurstDrill` kế thừa `Drill`, `BeamDrill`,
`WallCrafter`, `Fracker` kế thừa `SolidPump` -- không tính vì ra liquid chứ
không phải ore rắn). Trước phiên này chỉ `Drill`/`BurstDrill` được model
(gộp chung 1 công thức), `BeamDrill`/`WallCrafter` nằm trong danh sách "biết
nhưng cố ý chưa làm". Đã làm cả 3:

### Bug thật thứ 5 -- BurstDrill.java tính sai hardness_multiplier

Tải `BurstDrill.java` thật: field `hardnessDrillMultiplier = 0f` được set ở
CẤP CLASS (comment thật: "does not drill in the traditional sense"), khác
hẳn `Drill` (default 50.0 mỗi tier tự set riêng). `impact-drill`/
`eruption-drill` (2 block dùng `BurstDrill`) KHÔNG set lại field này trong
thân `{{ }}` riêng (đã grep `Blocks.java` xác nhận) -- `tools/
generate_catalog.py` trước đây fallback về default CHUNG 50.0 cho cả 2
class, khiến `impact-drill`/`eruption-drill` bị tính SAI (hardness của item
ảnh hưởng tới tốc độ đào trong khi thật ra không hề ảnh hưởng, vì
multiplier=0 làm hạng tử đó triệt tiêu). Cũng phát hiện thêm (chưa xử lý,
xem Giới hạn): `BurstDrill`/`Drill` thật có `drillMultipliers.put(Item, X)`
-- hệ số tốc độ RIÊNG từng loại item, catalog hiện tại không model (dùng 1
`drill_time` chung cho mọi item drill đó đào được).

Sửa: `tools/generate_catalog.py` giờ default `hardnessDrillMultiplier=0.0`
riêng cho class `BurstDrill`, `50.0` cho `Drill` thường. Regenerate catalog,
`impact-drill`/`eruption-drill` giờ `hardness_multiplier=0.0` đúng thật.

### BeamDrill (plasma-bore/large-plasma-bore)

Cơ chế thật (`BeamDrill.java`): bắn tia dò ore từ **MỖI cạnh** (không phải
diện tích chân đế) -- size=1 có 4 tia, size=s có 4*s tia (s tia/cạnh). Mỗi
tia quét tối đa `range` ô (mặc định 5), dừng ở ore ĐẦU TIÊN gặp (đơn giản
hoá: game thật dừng ở "first SOLID tile", simulator không có wall-ore riêng
nên dùng luôn `ore_tiles` floor overlay có sẵn). Rate = `60 * facingAmount /
drillTime`, KHÔNG có hardness_multiplier (chỉ `tier` làm ngưỡng cứng
`item.hardness <= tier`, không làm chậm tốc độ). Nhiều tia trúng NHIỀU LOẠI
ore khác nhau -> HUỶ TOÀN BỘ sản lượng (game thật: "khi có nhiều hơn 1 loại
item, coi như không có item nào" -- không phải lấy đa số).

Đã làm: `BuildingType.beam_range`, `sim.py _beam_drill_scan/_beam_drill_
target/_beam_drill_output_rate`, `tools/generate_catalog.py` parse
`BeamDrill` (trước đây trong `KNOWN_UNMODELED`, giờ chuyển sang
`HANDLED_CLASSES`), `produced_item()` đổi chữ ký nhận thêm `grid` (beam-drill
tự nhận diện item lúc đánh giá, không gán `ore_target` cố định như drill
thường -- kéo theo sửa `_generator_power_rate`/`_power_satisfaction` cũng
nhận `grid` vì gọi `produced_item` bên trong). `bot/planner.py`:
`find_beam_drill_spot` (chỗ đặt hợp lệ = ore NGAY SÁT footprint, đơn giản
hoá chưa tận dụng hết tầm bắn xa -- xem Giới hạn), nhánh `plan_build` kind
`"beam-drill"`. `command_parser.py`: "máy khoan plasma"/"máy khoan plasma
lớn" + thêm vào `_DRILL_NAMES` (vẫn cần ore_target như drill thường).

Test: `bot/beam_drill_demo.py` (4 kịch bản: rate đúng công thức, huỷ khi lẫn
loại ore, ore ngoài tầm không tính, ore quá cứng không tính) +
`bot/beam_wall_command_demo.py` (end-to-end lệnh chat -> đặt -> nối core).

### WallCrafter (cliff-crusher/large-cliff-crusher)

Cơ chế thật (`WallCrafter.java`): CHỈ quét dọc CẠNH ĐANG XOAY MẶT TỚI (khác
BeamDrill quét cả 4 cạnh) -- đọc `attribute` (weight số thực từ
`Block.attributes`, đơn giản hoá nhị phân ở đây) từ đá/tường TỰ NHIÊN kề
cạnh đó, cộng dồn thành hiệu suất, ra 1 item CỐ ĐỊNH (`output`, gắn liền
`attribute` -- cả 2 block thật hiện có đều dùng `Attribute.sand ->
Items.sand`). Rate = `(60/drillTime) * hiệu_suất`.

Đã làm: `simulator/grid.py` thêm hẳn khái niệm MỚI `Tile.attribute` +
`Grid.set_attribute()` (trước đây Grid chỉ có `ore`/`liquid`, không có gì
tương đương attribute Erekir). `BuildingType.wall_attribute`/`wall_output`.
`sim.py _wall_crafter_output_rate`. `tools/generate_catalog.py` parse
`WallCrafter` (field `attribute = Attribute.X`/`output = Items.X`, khác hẳn
pattern `outputItem = new ItemStack(...)` của `GenericCrafter`, viết hàm
`parse_wall_crafter_fields` riêng). `bot/state.py` thêm `attribute_tiles`
vào state JSON contract (song song `ore_tiles`/`liquid_tiles`). `bot/
planner.py`: `find_unmined_attribute` (như `find_unmined_ore`),
`find_wall_crafter_spot` (khác `find_beam_drill_spot`: phải chọn ĐÚNG
rotation, trả về `(x,y,rotation)` thay vì chỉ `(x,y)`), nhánh `plan_build`
kind `"wall-crafter"` (không cần hỏi ore_target -- output cố định theo
catalog). `command_parser.py`: "máy nghiền vách đá"/"máy nghiền vách đá lớn".

Test: `bot/wall_crafter_demo.py` (4 kịch bản: rate đúng công thức, sai cạnh
không tính dù đúng loại attribute, sai loại attribute không tính, hiệu suất
cộng dồn theo từng ô chứ không phải tất-cả-hoặc-không) +
`bot/beam_wall_command_demo.py`.

### Giới hạn (ghi rõ, chưa xử lý)

- **`drillMultipliers` (hệ số tốc độ riêng từng item)** chưa model cho BẤT
  KỲ loại drill nào (kể cả `Drill` thường) -- catalog dùng 1 `drill_time`
  chung, trong khi game thật vd `impact-drill` đào beryllium nhanh gấp đôi
  so với item khác (`drillMultipliers.put(Items.beryllium, 2f)`).
- **BeamDrill**: chỗ đặt chỉ tìm ore NGAY SÁT footprint (khoảng cách 1),
  chưa tận dụng hết tầm bắn xa thật (`range` 5-6 ô) -- đơn giản hoá, không
  sai (khoảng cách 1 luôn hợp lệ), chỉ chưa tối ưu diện tích tận dụng được.
  Cũng không mô hình "first SOLID tile" thật (dùng ore_tiles floor overlay
  thay vì wall-ore riêng, xem phần trên).
- **WallCrafter**: `Tile.attribute` nhị phân (có/không), không phải weight
  số thực như game thật -- 1 ô khớp luôn tính đúng 1.0 hiệu suất bất kể độ
  "đậm đặc" thật. Không model item/liquid booster optional (`large-cliff-
  crusher` thật có thể tiêu graphite để tăng tốc, bỏ qua -- cùng quy ước với
  liquidBoostIntensity của Drill/Pump không model từ trước).

## SolidPump (water-extractor) -- trả lời "map không có nước thì đào gì"

Bắt đầu từ câu hỏi ngược lại của user ("water-extractor nằm trong mục drill
mà, sao lúc đầu không làm luôn") -- đúng ra KHÔNG cùng class: dòng liệt kê
`mechanicalDrill, ..., waterExtractor, ...` trong `Blocks.java` chỉ là mảng
nội dung/UI, không phải bằng chứng cùng cơ chế. Grep dòng khởi tạo thật xác
nhận `waterExtractor = new SolidPump(...)`. Lý do bỏ sót thật: lúc trả lời
"Drill có bao nhiêu hệ thống" có kiểm cả `Fracker.java` (loại ra vì ra
liquid, không phải ore rắn) nhưng KHÔNG mở `SolidPump.java` ra kiểm dù nó
cũng có trong cùng thư mục `production/` -- ngầm loại vì tên "Pump" mà không
nói rõ, không nhất quán so với cách xử lý `Fracker`.

### Cơ chế thật (`SolidPump extends Pump`)

Khác `WallCrafter` (chỉ quét 1 cạnh): quét **TOÀN BỘ diện tích chân đế**
(giống `Drill` quét ore) -- công thức thật `fraction = validTiles + boost +
attribute.env()` (validTiles=số tile nền hợp lệ chung, boost=tổng trọng số
attribute thực, attribute.env()=hằng số môi trường riêng loại attribute).
Quá nhiều thành phần không rõ ràng đầy đủ từ source (cơ chế cache
`onProximityUpdate()` incremental, không tính lại mỗi tick) để model chính
xác 100% -- đơn giản hoá NHỊ PHÂN giống mọi chỗ khác trong simulator: `rate
= 60 * pump_amount * số_tile_khớp_attribute_dưới_chân_đế`. `water-extractor`
thật: `pumpAmount=0.11`, `attribute=Attribute.water`, `result=Liquids.water`,
`consumePower(1.5f)` (=90/s).

### Đã làm

`buildings.py`: `solid_pump_attribute`/`solid_pump_liquid`. `sim.py`:
`_solid_pump_output_rate`, `produced_liquid()` thêm nhánh, `find_liquid_
connections`/`_power_satisfaction` thêm `"solid-pump"` vào danh sách kind
liquid. `tools/generate_catalog.py`: bỏ `SolidPump` khỏi `KNOWN_UNMODELED`
(đã nằm đó từ 1 milestone RẤT sớm của dự án), parser mới `parse_solid_pump_
fields` (đọc `attribute = Attribute.X` + `result = Liquids.X`, khác
`parse_wall_crafter_fields` dùng `item_field_to_name` -- cái này cần
`liquid_field_to_name`). `bot/planner.py`: `find_solid_pump_spot` (như
`find_pump_spot` nhưng đọc `Tile.attribute`), nhánh `plan_build` kind
`"solid-pump"` -- **không** gọi `_connect_to_core` (đã ghi rõ trong code:
liquid không "giao thẳng về core" như item, giống hệt pump thường).
`command_parser.py`: "máy hút nước"/"water-extractor".

### Bug thật thứ 6 -- phát hiện khi viết demo: `plan_build()` không tự cấp điện cho 3 kind mới

Viết test cho `water-extractor` (power_input=90) phát hiện: `plan_build()`
KHÔNG gọi `_ensure_powered()` cho bất kỳ kind nào trong `drill`/`beam-drill`/
`wall-crafter`/`pump`/`solid-pump` -- chỉ nhánh `"factory"` có gọi. Đây là
lỗ hổng CÓ TỪ TRƯỚC (nhánh `"drill"` gốc cũng thiếu, không phải do
beam-drill/wall-crafter/solid-pump mới gây ra), nhưng vì 3 kind mới đều có
`power_input > 0` thật (plasma-bore=9, large-plasma-bore=48, cliff-
crusher=11, large-cliff-crusher=60, water-extractor=90) nên lộ ra ngay khi
test. Đã sửa: thêm `_ensure_powered()` vào cả 3 nhánh mới (`beam-drill`,
`wall-crafter`, `solid-pump`). **Chưa sửa** nhánh `"drill"`/`"pump"` gốc
(ngoài phạm vi việc đang làm, cần fix riêng -- có thể nhiều demo cũ đang
"qua được" test chỉ nhờ 1 hiệu ứng phụ của kiến trúc: `_power_satisfaction`
là hậu xử lý 1 lần SAU khi `output_rate`/`liquid_output_rate` đã cache, nên
building ĐÍCH (vd core) đọc được giá trị CHƯA điều chỉnh điện của nguồn
phía trên nếu core được `compute()` trước -- không phải lan truyền đúng,
xem ghi chú `_ensure_powered` cũ trong code).

### Test

`bot/solid_pump_demo.py` (4 kịch bản, có gọi `_ensure_powered()` thật để
cấp điện trước khi kiểm rate -- nếu không sẽ luôn ra 0 dù công thức đúng,
xem Bug thật thứ 6): rate tỉ lệ đúng số tile khớp × power_satisfaction đo
được, không có tile khớp thì 0, sai loại attribute thì 0, và
`find_liquid_producer()` nhận diện đúng solid-pump là nguồn liquid hợp lệ
cho factory khác cần (vd multi-press cần nước). Kịch bản 4 KHÔNG chain đủ 2
building-cần-điện liên tiếp (water-extractor + multi-press cùng lúc) vì
vướng giới hạn pathfinding không liên quan (map quá chật khi có 3 nguồn
than + 2 generator + nhiều belt cùng lúc) -- kiểm `find_liquid_producer()`
trực tiếp thay thế, đủ chứng minh cơ chế nối đúng mà không cần chiến đấu với
1 giới hạn pathfinding có sẵn không phải trọng tâm của việc đang làm.

## Bug thật thứ 7 -- "cấp N"/"tier N" bị command_parser.py âm thầm bỏ qua

User tự phát hiện bằng cách chạy thật: gõ "sử dụng drill cấp 4 đào chì cho
tôi" -- kỳ vọng `laser-drill` (tier 4 thật, xem `simulator/generated_
catalog.py`), nhưng `command_parser.py` không có phrase nào bắt SỐ tier
(`BUILDING_PHRASES` chỉ bắt TÊN riêng như "máy khoan laser"), nên câu chỉ
khớp đúng 1 từ: `"drill"` -> sentinel chung. Số "cấp 4" biến mất hoàn toàn,
không để lại dấu vết trong command dict. `plan_build()` sau đó gọi
`select_drill_type()` tự chọn tier RẺ NHẤT đủ dùng cho chì (hardness=1) ->
đặt nhầm `mechanical-drill` (tier 2), phớt lờ hoàn toàn yêu cầu người dùng
-- lỗi ÂM THẦM, không báo gì cả.

Test tiếp câu "drilllaser đào chì" (viết liền không dấu cách) -- cũng rớt về
sentinel `"drill"` vì `BUILDING_PHRASES` chỉ khớp chuỗi con CHÍNH XÁC, không
xử lý lỗi chính tả/viết liền (giới hạn đã biết trước, không sửa lần này --
xem "Giới hạn" bên dưới).

Sửa: thêm `TIER_RE = re.compile(r"(?:cấp|tier)\s*(\d+)")` +
`DRILL_TIER_NAMES` (map số tier thật -> tên drill đúng tier, đối chiếu
`generated_catalog.py`: 2=mechanical, 3=pneumatic, 4=laser, 5=blast,
6=impact, 7=eruption). Trong `parse_command()`, nếu `action=="build"` và
`building in _DRILL_NAMES` (đã khớp trước đó, sentinel hoặc tên riêng), số
tier nói rõ LUÔN THẮNG -- kể cả khi xung đột với tên (vd "máy khoan laser
cấp 2" -> ép về `mechanical-drill` tier 2, không phải laser tier 4, vì số
nói sau/rõ hơn được ưu tiên). Không nói số thì hành vi CŨ (auto-select rẻ
nhất đủ dùng) giữ nguyên, không đổi.

Test: `bot/drill_tier_number_demo.py` (6 kịch bản: "cấp N"/"tier N" cho
nhiều tier khác nhau, xung đột tên-vs-số, và trường hợp không nói số vẫn
auto-select như cũ).

### Giới hạn (chưa sửa, ghi rõ)

- Không xử lý lỗi chính tả/viết liền ("drilllaser" không nhận ra
  "laser-drill") -- `BUILDING_PHRASES` chỉ khớp chuỗi con chính xác, không
  có fuzzy-match. Cùng giới hạn đã biết từ đầu dự án (dict-based parser,
  không phải LLM -- xem đầu file `command_parser.py`).
- `TIER_RE` chỉ áp dụng cho họ `Drill`/`BurstDrill` thường (`_DRILL_NAMES`
  bao gồm cả `plasma-bore`/`large-plasma-bore` nhưng 2 building này chỉ có
  1 tier CỐ ĐỊNH mỗi cái -- nói "plasma-bore cấp 5" không có ý nghĩa vì
  không có "tier khác" của beam-drill để chọn, khác họ Drill thường có 6
  tier độc lập).

## Power-bridging -- ưu tiên nối vào mạng điện gần nhất thay vì luôn xây generator mới

User re-test lại "drill cấp 4 đào chì" (sau khi Bug thật thứ 7 đã sửa xong
phần tier-number) và phát hiện tiếp: `laser-drill` (power_input=66) được đặt
xuống nhưng KHÔNG có điện -- vì nhánh `"drill"` gốc trong `plan_build()`
(khác beam-drill/wall-crafter/solid-pump đã sửa ở Bug thật thứ 6) vẫn CHƯA
BAO GIỜ gọi `_ensure_powered()`. User yêu cầu rõ: "cần, nhưng fix vụ điện
trước, nối điện vào mạng lưới điện gần nhất" -- tức trước khi tự xây
generator mới, phải thử BẮC CẦU vào mạng điện đã có sẵn trên map trước.

### Đã làm

`bot/planner.py`: `_find_power_bridge_spot(grid, near, preferences)` -- tìm
chỗ đặt 1 power-node gần `near` mà khi đặt xong sẽ `_power_linked` (xem
`simulator/sim.py`) tới ít nhất 1 building có điện ĐÃ CÓ SẴN trên map
(generator hoặc power-node khác), trả về `None` nếu map chưa có điện gì
hoặc không tìm được chỗ trong tầm bất kỳ cái nào. Viết lại toàn bộ
`_ensure_powered()`: (1) sớm return nếu `power_input<=0` hoặc đã đủ điện;
(2) thử bắc cầu TRƯỚC, đo lại satisfaction sau khi bắc cầu, return sớm nếu
đã đủ -- KHÔNG xây gì thêm; (3) chỉ khi (1) không bắc cầu được HAY (2) bắc
cầu xong vẫn thiếu công suất, mới tự đặt 1 combustion-generator MỚI (đặt
gần chính power-node vừa bắc cầu nếu có, để nối chung 1 mạng thay vì tách
riêng) + drill than dành riêng; (4) bỏ qua bước đặt power-node cuối nếu đã
bắc cầu ở bước 2 (tránh đặt trùng). Thêm gọi `_ensure_powered()` vào ĐÚNG
nhánh `"drill"` gốc (gap mà user vừa phát hiện) và nhánh `"pump"` (hiện là
no-op vì `mechanical-pump.power_input=0`, thêm cho nhất quán/tương lai).

### Test

`bot/power_bridge_demo.py` (3 kịch bản, dùng số đo THẬT qua
`evaluate_layout()` chứ không giả định): (1) map chưa có điện gì -> vẫn tự
xây generator mới như hành vi cũ (không đổi); (2) đã có sẵn mạng điện DƯ
công suất gần đó (2 combustion-generator dựng tay, đo được ~82.3/s > 66/s
cần) -> chỉ bắc cầu ĐÚNG 1 power-node, generator mới đặt = 0,
`power_satisfaction` đo được = 1.0; (3) mạng điện có sẵn nhưng NGOÀI tầm bắc
cầu (power_range=6) -> vẫn tự xây generator mới độc lập, không "bỏ cuộc" vì
thấy có điện ở đâu đó trên map. Regression: 32/32 script pass sau khi thêm.

### Giới hạn (chưa xử lý, ghi rõ)

- Vẫn KHÔNG tự tính chính xác công suất cần cho lưới điện phức tạp nhiều
  building -- fallback chỉ xây ĐÚNG 1 generator "đủ dùng khiêm tốn" mỗi lần
  gọi, có thể vẫn thiếu nếu 1 building đơn lẻ cần quá nhiều điện (vd
  laser-drill 66/s > 1 combustion-generator fully-fed tối đa ~41-60/s tuỳ
  độ phủ than) -- xem `bot/liquid_boost_demo.py` kịch bản 3 gặp đúng trường
  hợp này (đo được `power_satisfaction≈0.62`, không phải 1.0, dù đã fallback
  xây generator).
- Bán kính bắc cầu (`power_range`) tính theo khoảng cách Euclidean tròn gần
  đúng, không phải tia laser hình chữ nhật chính xác như `PowerNode.java`
  thật (đã ghi từ trước, xem `_power_linked` docstring).

## Liquid boost (Drill.java consumeLiquid(...).boost()) + lệnh "phủ kín mỏ"

Bắt đầu từ câu hỏi "nếu ở dưới nền đất bự và có nhiều quặng, 1 drill là
không đủ phủ hết, bot có biết đặt lên nền đó nhiều drill không hay chỉ 1" --
xác nhận (đọc code) là CHỈ 1 (mỗi lệnh xây chỉ đặt đúng 1 drill dù mỏ to cỡ
nào, `find_drill_spot()` trả về ngay ô hợp lệ ĐẦU TIÊN rồi dừng). User xác
nhận muốn thêm, kèm yêu cầu: "tương lai mỗi Drill Laser hoặc cao hơn sẽ phải
cần thêm 1 nguồn nước từ drill water hoặc từ 1 đường ống, phải tối ưu cái
đó".

### Sửa giả định sai ban đầu của user (đã tra `Blocks.java` thật trước khi code)

User giả định chỉ "Laser trở lên" mới cần nước -- SAI. Tải thật
`core/src/mindustry/content/Blocks.java`, xác nhận CẢ 4 tier
(mechanical/pneumatic/laser/blast-drill) đều có
`consumeLiquid(Liquids.water, X).boost()`:

```java
mechanicalDrill: consumeLiquid(Liquids.water, 0.05f).boost();       // 1.6x (mặc định Drill.liquidBoostIntensity)
pneumaticDrill:  consumeLiquid(Liquids.water, 3.5f/60f).boost();    // 1.6x
laserDrill:      consumeLiquid(Liquids.water, 0.08f).boost();       // 1.6x
blastDrill:      consumeLiquid(Liquids.water, 0.1f).boost();        // 1.8x (ghi đè -- comment thật: "more than the laser drill")
```

`.boost()` nghĩa là OPTIONAL (khác `consumePower()` bắt buộc) -- công thức
thật `speed = lerp(1.0, liquidBoostIntensity, optionalEfficiency)`, không có
nước drill vẫn chạy tốc độ nền, có nước thì nhân thêm.

Phát hiện thêm (ngoài phạm vi sửa lần này, ghi rõ để không quên):
`impact-drill` (BurstDrill) thật có 1 `consumeLiquid(Liquids.water,
10f/60f)` KHÔNG có `.boost()` -- tức BẮT BUỘC, khác hẳn booster tuỳ chọn của
nó (`consumeLiquid(Liquids.ozone, 3f/60f).boost()`, đã parse đúng vì có
`.boost()`). Parser hiện tại (đúng chủ đích) CHỈ bắt các `consumeLiquid(...)
.boost()` -- consumeLiquid bắt buộc riêng này của impact-drill/eruption-
drill CHƯA được model, khiến rate 2 block đó có thể bị tính CAO HƠN thật nếu
không cấp nước (vì thiếu 1 điều kiện chặn cứng). Không sửa lần này (nằm
ngoài yêu cầu ban đầu của user, cần thêm field/cơ chế "required liquid cho
drill" riêng, khác hẳn field boost hiện có).

### Đã làm

`simulator/buildings.py`: `BuildingType.boost_liquid`/`boost_amount`
(thô/tick, giống quy ước `pump_amount`)/`boost_intensity` (default 1.6).
`tools/generate_catalog.py`: `parse_drill_boost()` (regex bắt đúng
`consumeLiquid(Liquids.X, Y).boost()`, bỏ qua consumeLiquid KHÔNG có
`.boost()`), field `liquidBoostIntensity` override. `simulator/sim.py`:
`compute()` nhánh `"drill"` nhân thêm `1 + (boost_intensity-1)*hiệu_suất`
sau rate nền, hiệu_suất tính từ `liquid_in_edges` giống hệt cách factory
tính `recipe.liquid_inputs` (không phải nhị phân, lerp liên tục theo tỉ lệ
nước THẬT nhận được).

`bot/planner.py`: `_try_boost_with_water(grid, actions, drill, preferences)`
-- KHÔNG BẮT BUỘC (khác `_ensure_powered`), không tìm/nối được nước thì bỏ
qua ÊM, không raise lỗi. Thứ tự ưu tiên: (1) producer ĐÃ CÓ trên map (dùng
`_route_or_branch_from_producer`, khiến NHIỀU drill gọi hàm này lần lượt tự
động DÙNG CHUNG 1 nguồn qua router thay vì mỗi cái 1 nguồn riêng -- đây
chính là phần "tối ưu" user yêu cầu, không cần code riêng); (2) tile liquid
thật chưa khai thác gần đó -- xây `mechanical-pump` mới; (3) không có liquid
tile thật -- thử `water-extractor` (SolidPump, đọc attribute) nếu catalog
có loại solid-pump nào sinh đúng liquid cần; (4) không có gì cả -- bỏ qua.
Gọi từ nhánh `"drill"` của `plan_build()` ngay sau `_ensure_powered`.

`plan_fill_ore(grid, command, scorer, preferences)` -- lệnh "phủ kín mỏ":
lặp lại đúng logic chọn-chỗ-đặt của nhánh `"drill"` (tìm ore chưa khai thác
-> tìm chỗ đặt -> đặt + cấp điện + boost nước + nối core) cho tới khi
`find_drill_spot()` không còn chỗ nào -- số ứng viên "chưa khai thác" giảm
chặt mỗi vòng lặp (building vừa đặt chiếm `_by_tile`) nên chắc chắn dừng,
không cần giới hạn số vòng lặp thủ công. `plan_build()` tự dispatch sang
hàm này nếu `command.get("fill")` là `True` -- mọi call site hiện có (kể cả
`bot/log_learning.py`, demo cũ) không cần sửa gì, tự động tương thích.
`bot/command_parser.py`: `FILL_PHRASES` ("phủ kín mỏ", "phủ kín", "hết mỏ",
"toàn bộ mỏ"...) -- chỉ áp dụng cho drill (có `ore_target`), đặt cờ
`command["fill"]=True`.

### Bug thật thứ 8 -- `_route_or_branch_from_producer()`/`plan_split()` hardcode "belt" (item), dùng cho liquid ra sai kết quả

Phát hiện khi viết demo cho `_try_boost_with_water()`: gọi hàm 2 lần liên
tiếp cho 2 drill (drill #2 lẽ ra phải TÌM THẤY pump của drill #1 rồi bắc
cầu) -- kết quả drill #2 không nhận được nước gì cả, dù không có lỗi nào
raise. Truy ra: `trace_belt_path()` (dùng trong
`_route_or_branch_from_producer` để kiểm "output_tile của producer đã dẫn
đi đâu chưa") hardcode kiểm `b.type.kind != "belt"` -- ĐÚNG cho conveyor
(kind="belt"), nhưng conduit thật có `kind="liquid-belt"` (khác hẳn), nên
hàm dừng SAI ngay tại Ô CONDUIT ĐẦU TIÊN, tưởng nhầm nó là "đích", rồi gọi
`plan_split()` chia nhánh với router+conveyor SAI LOẠI (item, không phải
liquid) -- item router không hiểu conduit, kết quả: đường nước bị âm thầm
cắt đứt, không báo lỗi gì (vì `_try_boost_with_water` cố tình bọc try/except
RuntimeError để không chặn drill chính -- nuốt luôn cả lỗi ngầm này).

Sửa: `trace_belt_path()` (`simulator/sim.py`) thêm tham số `belt_kind:
str = "belt"` (mặc định giữ nguyên hành vi cũ cho mọi call site item hiện
có), so `b.type.kind != belt_kind` thay vì hardcode. `_clear_belt_chain()`/
`plan_split()` (`bot/planner.py`) cũng thêm tham số tương tự
(`belt_kind`/`belt_type`+`router_type`, default `None` -> conveyor+router,
giữ nguyên hành vi cũ). `_route_or_branch_from_producer()` giờ tự suy ra
`belt_kind` từ chính `belt_type` được truyền vào, và chọn `router_type`
đúng (`CATALOG["liquid-router"]` nếu `belt_kind=="liquid-belt"`, `CATALOG
["router"]` nếu không) -- `_trace_branching()` (nơi thật sự tính throughput)
KHÔNG phân biệt `router`/`liquid-router` (cả 2 đều `kind="router"`, chỉ khác
tên hiển thị đúng loại building thật), nên không cần sửa gì ở đó.

### Test

`bot/liquid_boost_demo.py` (4 kịch bản): không nước -> đúng rate nền, không
lỗi; đủ nước (1 pump riêng, nối qua `_route()` thật) -> nhân đúng
`boost_intensity`; 2 drill gọi `_try_boost_with_water()` lần lượt -> TỰ ĐỘNG
dùng chung 1 pump (không xây pump thứ 2), mỗi drill nhận phần nước THEO ĐÚNG
số cạnh chạm router (không phải luôn chia đều 50/50 -- 1 building lớn có
thể chạm router ở nhiều cạnh cùng lúc), boost lerp đúng tỉ lệ; `blast-drill`
có `boost_intensity=1.8` ghi đè đúng, 3 tier còn lại dùng default 1.6.

`bot/fill_ore_demo.py` (4 kịch bản): đối chứng lệnh xây thường vẫn chỉ đặt
1 drill (chưa đổi); "phủ kín mỏ" đặt NHIỀU drill, dừng đúng lúc hết chỗ
(verify lại bằng `find_drill_spot()` thật, không còn chỗ nào bị bỏ sót);
mỗi drill đã tự nối belt hoạt động thật (throughput > 0, không chỉ đặt
suông); nhiều drill cần nước qua "phủ kín mỏ" tự động dùng CHUNG 1 nguồn
(2 drill, 1 pump, cả 2 xác nhận có `liquid_connections` trỏ tới).

Regression: 33/33 script pass sau khi thêm (32 cũ + 2 demo mới, trừ 1 script
`power_bridge_demo.py` đã tính vào 32 cũ).

### Giới hạn (chưa xử lý, ghi rõ)

- `impact-drill`/`eruption-drill` (BurstDrill) có `consumeLiquid` BẮT BUỘC
  riêng (không có `.boost()`) CHƯA model -- xem mục "Sửa giả định sai" ở
  trên.
- `plan_fill_ore()` (phần belt item) đã sửa sang manifold -- xem mục riêng
  "plan_fill_ore() dùng manifold" bên dưới, KHÔNG còn đúng như mô tả cũ ở
  đây nữa (giữ dòng này để mai sau đọc lịch sử không hiểu nhầm là chưa từng
  ghi nhận).
- Trên map/mỏ lớn + nhiều drill cần điện+nước đồng thời, dễ gặp giới hạn
  pathfinding đã biết từ trước (hạ tầng điện/nước của drill đặt trước có
  thể vô tình chặn hành lang belt của drill đặt sau nếu không gian hẹp) --
  không phải bug riêng của tính năng này, xem các "giới hạn pathfinding"
  đã ghi ở nhiều mục khác trong file này (`solid_pump_demo.py`,
  `power_bridge_demo.py`...). `bot/fill_ore_demo.py` né bằng cách chọn map
  đủ rộng/mỏ vừa phải, không phải bằng chứng nó không xảy ra trên map lớn
  hơn/dày đặc hơn thật.
- Không tính `drillMultipliers` (hệ số tốc độ riêng từng item) -- giới hạn
  đã ghi từ mục BeamDrill/WallCrafter, vẫn áp dụng.

## `plan_fill_ore()` dùng manifold -- gộp cả hàng drill vào 1 đường belt

User hỏi tiếp ngay sau khi "phủ kín mỏ" xong: *"vậy giờ có 1 mỏ, bot có biết
đặt full mỏ xong rồi nối băng chuyền với nhau cho sao chỉ có 1 băng chuyển
về core không?"* -- verify bằng debug script TRƯỚC khi trả lời (không đoán):
bản `plan_fill_ore()` ban đầu (lặp `find_drill_spot` + `_connect_to_core`
độc lập cho từng drill) cho ra **4 drill = 4 đường belt riêng, 86
conveyor** trên 1 mỏ 4x4 -- xác nhận đúng câu hỏi, mỗi drill tự BFS 1 đường
không hề gộp. User xác nhận muốn sửa.

### Cơ chế thật muốn mô phỏng -- "manifold"

Cách người chơi Mindustry thật hay làm: xếp NHIỀU drill thành 1 HÀNG, tất cả
quay mặt đổ thẳng vào 1 đường conveyor chạy dọc ngay cạnh cả hàng (mỗi drill
đổ vào ĐÚNG 1 ô conveyor riêng của nó trên cùng đường đó, không cần
router/junction) -- rồi chỉ đúng 1 đường conveyor đó chạy tiếp về core.

### Đã làm

`bot/planner.py`: `_build_drill_row_manifold(grid, actions, building_type,
ore_target, min_x, max_x, row_y, lane_dir)` -- quét dọc trục X tại 1 hàng Y
cố định, đặt drill (rotation=1, quay mặt xuống Nam) tại mọi vị trí hợp lệ
chạm ore, bước `size` ô mỗi lần đặt được (dò từng ô 1 nếu vướng, không bỏ
sót do mỏ không đều), rồi lấp ĐẦY 1 hàng conveyor liên tục ngay bên dưới
(`row_y + size`) từ cột đầu tới cột cuối trong số các `output_tile()` của
drill vừa đặt -- các cột đó tự nhiên KHÔNG trùng nhau (drill cách nhau đúng
`size`, `output_tile()` luôn ở cột giữa chân đế mỗi drill).

`plan_fill_ore()` viết lại: quét bounding box của MỌI ô ore cùng loại trên
map (không phân biệt nhiều mỏ rời rạc -- xem Giới hạn), chọn hướng lane
(`lane_dir`) theo phía core gần hơn (Tây/Đông), rồi lặp qua từng HÀNG (bước
`size + 1` -- chừa đúng 1 hàng cho lane) gọi `_build_drill_row_manifold`.
Mỗi hàng có drill thì nối lane của nó về đích: **KHÔNG** luôn BFS thẳng về
core -- đích là `core.footprint() + toàn bộ tile lane của các hàng TRƯỚC ĐÓ`
(`existing_lane_tiles`, tích luỹ qua từng vòng lặp), để hàng sau MERGE thẳng
vào lane hàng trước nếu gần hơn, thay vì phải BFS vòng qua nguyên khối hạ
tầng hàng trước để tới core riêng.

### Bug thật tự phát hiện khi đo số liệu -- multi-hàng độc lập còn TỆ HƠN cách cũ

Bản đầu (mỗi hàng tự BFS thẳng về core, không biết tới lane hàng khác) đo
được: 4 drill / 2 hàng / **106 conveyor** -- TỆ HƠN CẢ con số 86 của cách cũ
(mỗi drill tự đi riêng)! Lý do: hàng 2 phải đi VÒNG QUANH nguyên khối hạ
tầng hàng 1 (drill + lane hàng 1 chắn ngang) để tới core, tốn hơn cả việc
từng drill tự né nhau lẻ tẻ. Sửa bằng cơ chế merge-vào-lane-trước ở trên,
đo lại: cùng 1 mỏ 4x4, ra 4 drill / **58 conveyor** (14.5/drill, thấp hơn
hẳn baseline 21.5/drill của cách cũ).

### Test

`bot/fill_ore_demo.py` (cập nhật lại kịch bản 2): đo trực tiếp
`conveyor/drill` phải dưới ngưỡng 15.0 (baseline cũ ~21.5, bản manifold lỗi
đo được 26.5 -- ngưỡng này bắt được cả 2 loại hồi quy); xác nhận VẬT LÝ bằng
cách nhóm các drill theo `output_tile()[1]` (toạ độ Y của lane) -- phải có
ít nhất 1 nhóm ≥2 drill cùng đổ vào 1 `lane_y`, không chỉ suy luận gián tiếp
từ số lượng conveyor ít.

### Giới hạn (chưa xử lý, ghi rõ)

- Chỉ hỗ trợ lane NGANG (hàng theo trục X, drill quay mặt Nam) -- mỏ dài
  theo trục Y (cần lane DỌC) vẫn hoạt động đúng (vẫn quét được nhiều "hàng"
  dọc theo Y, mỗi hàng 1 lane ngang riêng) nhưng không tối ưu bằng nếu tự
  mỏ đó vốn hợp với layout dọc hơn.
- `lane_dir` chọn 1 LẦN cho toàn bộ mỏ dựa theo vị trí core so với TÂM mỏ --
  không xét lại cho từng hàng riêng, có thể không tối ưu nếu core nằm chéo
  góc so với mỏ dài.
- Việc "merge vào lane hàng trước" chỉ xét lane của các hàng đã xử lý TRƯỚC
  ĐÓ trong CÙNG lệnh gọi -- không tái sử dụng belt có sẵn từ TRƯỚC lệnh này
  (vd core đã có 1 đường belt khác từ lệnh cũ) trừ khi nó tình cờ nằm trên
  đường BFS.
- `evaluate_layout()`/`find_connections()` vẫn ghi nhận MỖI DRILL là 1
  "edge" riêng vào core trong đồ thị tính throughput (dù vật lý dùng chung 1
  lane) -- không sai (mỗi drill vẫn được tính đúng rate + tới đúng core),
  chỉ là số "edges" không phản ánh trực tiếp số ĐƯỜNG BELT VẬT LÝ -- đã đổi
  cách verify trong demo sang đếm conveyor thật + toạ độ lane_y thay vì đếm
  edges (xem mục Test).
- Không mô hình hoá tranh chấp CAPACITY thật khi nhiều drill dùng chung 1
  lane (mỗi nguồn vẫn được tính như thể có toàn bộ `base_rate` của belt cho
  riêng nó, không chia sẻ) -- cùng kiểu đơn giản hoá "steady-state xấp xỉ"
  đã áp dụng ở mọi nơi khác trong simulator, không phải bug riêng của
  manifold.

## water-extractor: ưu tiên đặt SÁT drill (chạm thẳng, bỏ hẳn conduit) thay vì near+conduit

User hỏi "water drill để làm gì... thường water drill sẽ đặt sát bên máy
drill để khỏi đặt ống nước hay gì hết". Lúc đầu tôi hiểu nhầm thành ý muốn
đổi sang `steam-generator` (đốt nước làm điện) -- user chỉnh lại: không
liên quan gì tới điện phát ra từ nước, chỉ đơn giản là muốn đặt SÁT drill để
khỏi tốn conduit, và nếu đặt nhiều cái (cụm) thì từng cái vẫn phải tự có
điện (đã có sẵn, xem `_ensure_powered` gọi trong `_try_boost_with_water`
-- không phải gap mới).

### Đã xác nhận qua code thật (trước khi sửa)

`plan_build()` nhánh `solid-pump` (lệnh trực tiếp "xây water-extractor")
search `near=core_pos` -- tìm gần CORE, không hề biết drill nào cần nước.
`_try_boost_with_water()` (tự động khi drill cần boost) đã search
`near=(drill.x, drill.y)` đúng hướng, nhưng vẫn chỉ là "gần" rồi tự nối
`conduit` qua `_route()`, chưa từng thử đặt CHẠM THẲNG để bỏ hẳn conduit.

### Cơ chế thật cho phép "chạm thẳng không cần belt/conduit"

`simulator/sim.py:_trace_branching()` case fallthrough (khi building đích
không phải belt/router/sorter/junction/bridge/mass-driver): `return [(b,
capacity)]` -- nghĩa là nếu `output_tile()` của 1 building rơi ĐÚNG vào ô
footprint của building khác, 2 bên tự động coi là đã nối, KHÔNG cần
belt/conduit gì ở giữa (đúng cơ chế thật Mindustry: 2 building kề nhau tự
chuyển hàng/liquid trực tiếp).

### Đã làm

`bot/planner.py`: `_find_touching_solid_pump_spot(grid, drill,
attribute_name, solid_pump_type)` -- duyệt 4 cạnh (Đông/Tây/Nam/Bắc) của
`drill`, với mỗi cạnh tính TOÁN NGƯỢC (dựa công thức `_edge_tile()` thật
trong `grid.py`) vị trí + rotation đặt solid_pump sao cho `output_tile()`
rơi đúng vào 1 ô trong footprint drill, kiểm `can_place` + có đủ attribute
dưới chân đế, verify lại bằng cách tạo `PlacedBuilding` thử (`probe`) và so
`output_tile()` thật với footprint drill (double-check công thức, không tin
suông). `_try_boost_with_water()` nhánh solid-pump giờ thử hàm này TRƯỚC,
chỉ lùi về `find_solid_pump_spot` (near) + `_route()` (conduit) như cũ nếu
không cạnh nào của drill có đủ attribute.

### Test

`bot/liquid_boost_demo.py` kịch bản 5 (mới): drill có attribute nước ngay
sát cạnh Đông -- xác nhận đặt được water-extractor, **0 conduit**, và rate
đo được = full boost (`base_rate * boost_intensity`), chứng minh nước THẬT
sự nối tới (không chỉ đặt suông cạnh nhau mà không hoạt động).

### Giới hạn (chưa xử lý, ghi rõ)

- Chỉ áp dụng cho `_try_boost_with_water()` (tự động khi 1 drill CỤ THỂ cần
  boost) -- lệnh trực tiếp "xây water-extractor" (`plan_build` nhánh
  `solid-pump`) VẪN search `near=core_pos` như cũ, chưa có khái niệm "đặt
  sát drill nào" vì lệnh đó không có tham số chỉ định drill đích.
- Không tự động đặt THÊM water-extractor thứ 2 nếu 1 cái không đủ hiệu suất
  boost (vd attribute yếu, chỉ 1 ô chạm) -- "đặt theo cụm" user nhắc tới
  hiện chỉ đúng khi TỰ user gọi lệnh nhiều lần hoặc nhiều drill riêng biệt
  tự tìm thấy điểm chạm khác nhau, không phải bot tự quyết "1 cái chưa đủ,
  thêm cái nữa" cho cùng 1 drill.
- 4 cạnh duyệt theo thứ tự cố định (Đông trước, rồi Tây, Nam, Bắc, xem code)
  -- không chọn cạnh "tốt nhất" (vd cạnh có nhiều tile attribute nhất), chỉ
  lấy cạnh ĐẦU TIÊN thoả điều kiện.

## Duct/armored-duct -- lỗ hổng thật phát hiện khi user hỏi "bot nhận diện hết Transport chưa"

User hỏi tổng quát: *"Rồi có bao nhiêu Transport Transportation trong game,
bot có nhận diện hết cách dùng chưa?"* -- kiểm đếm trực tiếp catalog: 47
building thuộc Category.distribution, 39 đã có cơ chế thật, 8 chưa. Trong
8 cái chưa, `plastanium-conveyor`/`surge-conveyor` (class `StackConveyor`)
và `unit-cargo-*`/`item-source`/`item-void` đều có LÝ DO rõ ràng (cơ chế
khác hẳn/không phải building thật chơi được) -- riêng `duct`/`armored-duct`
**không nằm trong bất kỳ danh sách loại trừ nào cả**, đơn giản là bị bỏ sót
từ đầu dự án (không ai từng hỏi/đụng tới).

### Vì sao không gộp chung được với Conveyor

Tải `Duct.java` thật xác nhận: KHÔNG có field `displayedSpeed` (thứ
`BELT_CLASSES` cũ luôn đọc cho Conveyor) -- field thật là `speed` (số
tick/lần chuyển 1 item, đơn vị khác hẳn). Công thức quy đổi lấy ĐÚNG từ
chính cách game hiển thị chỉ số cho người chơi (`Duct.java` dòng 61):
`stats.add(Stat.itemsMoved, 60f / speed, StatUnit.itemsSecond)`. Cả
`duct` lẫn `armored-duct` đều `speed = 4f` -> `base_rate = 60/4 = 15.0`
items/s (armored chỉ khác máu/giáp, không khác tốc độ).

### Đã làm

`tools/generate_catalog.py`: `DUCT_CLASSES = {"Duct"}` (tách riêng khỏi
`BELT_CLASSES` vì field khác nhau), nhánh parse riêng đọc `field_float(body,
"speed", default=5.0)` rồi tính `TICKS_PER_SECOND / raw_speed`, ghi chung
vào list `belts` (cùng `kind="belt"` với Conveyor -- cơ chế belt-tracing
trong `sim.py` không phân biệt theo class nguồn, chỉ cần đúng `base_rate`).
Regenerate catalog: `duct`/`armored-duct` giờ `kind="belt", base_rate=15.0`.

### Test

`bot/duct_demo.py`: xác nhận `base_rate=15.0` đúng công thức cho cả 2
building, và 1 kịch bản drill→chuỗi duct→core đo throughput thật khớp
chính xác rate nền của drill (duct không làm mất/sai luồng, hoạt động đúng
như 1 belt thật).

### Giới hạn (chưa xử lý, ghi rõ)

- `bot/planner.py` **không có đường nào tự CHỌN đặt duct thay vì conveyor**
  khi tự động nối route -- mọi `_route()`/`plan_split()`/`_connect_to_core`
  đều hardcode `CATALOG["conveyor"]`. Thêm Duct vào catalog chỉ giúp
  `evaluate_layout()` tính ĐÚNG throughput nếu duct đã có sẵn trong state
  đầu vào (đọc từ map thật/mod dump có duct), KHÔNG phải bot tự xây duct qua
  lệnh chat -- giống hệt vị trí của bản thân "conveyor" (cũng không phải 1
  building được planner CHỌN, chỉ là loại belt duy nhất nó biết tự đặt).
  Muốn bot TỰ CHỌN duct (vd trên map Erekir, ưu tiên duct hơn conveyor) cần
  thêm logic chọn belt_type theo ngữ cảnh map, chưa làm.
- Không xử lý `plastanium-conveyor`/`surge-conveyor` (`StackConveyor`) hay
  `unit-cargo-loader`/`unit-cargo-unload-point` -- vẫn cố ý bỏ qua như cũ,
  không nằm trong phạm vi câu hỏi này.

## "Xây N máy phát điện" -- cụm generator dùng chung 1 nguồn than qua router (lấy ý từ schematic thật)

User hỏi trực tiếp: *"ví dụ tôi nói bot tạo 21 máy phát điện siêu nhỏ thì
bot có thể làm giống vậy không? Bot biết được tự thiết lập đầu vào là than
không? Hay bot sẽ xây dựng 21 cái máy phát điện random và không biết đầu
vào?"* -- kèm 1 schematic `.msch` THẬT (base64, user tự export từ game) để
làm mẫu thiết kế đúng.

### Giải mã schematic thật user cung cấp (byte-khớp 722/722)

Dùng lại decoder `.msch` đã verify từ phiên trước (đối chiếu byte-perfect
với 5 file thật, xem mục "Phase E" lịch sử dự án). Kết quả: **"Basic power
plant V.1"** -- 18 combustion-generator (3 hàng × 6), 13 router, 2
power-node, 3 message hướng dẫn. Message thật trong schematic: *"Input
coal"* (điểm nhập than), *"Coal gets combusted and turned into energy
through these routers"* (xác nhận cơ chế: router phân phối than, không phải
mỗi generator tự đào riêng), *"Use these 2 power nodes as connectors to
other blocks that require power"* (power-node để TAP điện ra ngoài, không
phải để chính cụm dùng). Layout: mỗi hàng router nằm GIỮA 2 hàng generator
(router 1 lane phục vụ CẢ 2 hàng trên/dưới cùng lúc) -- tối ưu hơn bản đã
làm ở đây (xem Giới hạn).

### Trước khi có tính năng này

`plan_build()` nhánh `"generator"` (lệnh xây generator thường) CHỈ hỗ trợ 1
generator/lệnh -- đã tự cấp than đúng (tự đào drill than riêng, tự nối
belt), nhưng gọi lệnh đó N=21 lần sẽ ra **21 mỏ than khác nhau** (tự nó dễ
hết than trên map giữa chừng, raise lỗi) và bố cục rải rác, không giống
schematic thật.

### Bug thật phát hiện khi test bằng đúng câu lệnh user gợi ý ("máy phát điện")

`parse_command("xây máy phát điện")` bị hiểu SAI thành `action="delete"`!
Nguyên nhân: `ACTION_PHRASES["phá"]` (xoá) match kiểu `phrase in normalized`
(substring, không có ranh giới từ) -- "phá" là substring THẬT SỰ của "phát"
trong "máy phát điện" (p-h-á + t = p-h-á-t). Lỗi này CÓ TỪ ĐẦU DỰ ÁN, chưa
ai từng phát hiện vì mọi demo cũ đều gọi `plan_build()` trực tiếp với
command dict tự tạo, KHÔNG đi qua `parse_command()` với đúng cụm từ "máy
phát điện" thật. Sửa: đổi riêng vòng lặp match `ACTION_PHRASES` sang dùng
`\b` (ranh giới từ, Python `re` Unicode-aware nên hoạt động đúng với dấu
tiếng Việt) thay vì substring thô -- các phrase khác trong file (building
name, ore name...) vẫn giữ nguyên kiểu match substring cũ (đủ dài/đặc trưng
để an toàn, không đổi để tránh phá vỡ hành vi khác).

### Đã làm

`bot/command_parser.py`: `_GENERATOR_NAMES = {"combustion-generator",
"steam-generator"}`, `COUNT_RE = re.compile(r"\b(\d+)\b")` -- bắt số ngay
trong câu khi building là generator, gán `command["count"]`.

`bot/planner.py`: `_find_generator_row_spot()`/`_generator_row_fits()` --
quét vòng tròn mở rộng (như `find_free_area_candidates`) tìm chỗ đủ rộng
cho CẢ hàng N generator LẪN hàng N router ngay dưới, liên tục không vướng.
`plan_build_generator_cluster()`: đặt N generator thành 1 hàng, MỖI generator
chạm THẲNG (không cần belt, xem `sim.py _trace_branching` fallthrough case)
1 router riêng ngay dưới nó -- N router liền kề nhau tự tạo thành 1 LANE
liên tục (Router.java thật: round-robin chia đều cho mọi hướng còn nhận
được). Chỉ đào **1 drill than DUY NHẤT**, nối belt vào ĐÚNG 1 đầu lane --
than tự chảy dọc lane, mỗi router rẽ 1 phần vào đúng generator phía trên nó
(cơ chế y hệt `_trace_branching` router đã dùng khắp dự án, không cần code
mới). Cuối cùng đặt 1 power-node chạm cụm để tap điện ra ngoài, đúng ý
message thật trong schematic user cung cấp. `plan_build()` tự dispatch sang
hàm này nếu `command.get("count")` khác `None`.

### Test

`bot/generator_cluster_demo.py` (3 kịch bản): đối chứng lệnh thường (không
số) vẫn ra đúng 1 generator, hành vi cũ không đổi; "xây 21 máy phát điện"
ra ĐÚNG 21 generator + 21 router + **CHỈ 1** coal-drill (không phải 21) + 1
power-node, đo `evaluate_layout()` thật xác nhận CẢ 21 generator đều sản
xuất điện > 0; xác nhận vật lý 21 router liền mạch tạo đúng 1 lane liên
tục (không rời rạc).

### Trả lời trực tiếp câu hỏi user (đo được, không đoán)

21 generator dùng CHUNG 1 mechanical-drill than khiêm tốn: tổng
`power_production` cả cụm đo được chỉ ~7.76/s (mỗi generator trung bình
~0.37/s, bị router chia rất mỏng). **Không phải cứ thêm generator là điện
tăng theo tỉ lệ** -- tổng điện vẫn bị giới hạn bởi tổng than CUNG CẤP ĐƯỢC,
không phải bởi số generator. Muốn 21 generator thật sự phát huy hết công
suất (tối đa lý thuyết ~21×60=1260/s nếu mỗi cái no than), cần than nhiều
hơn hẳn (drill tier cao hơn, hoặc nhiều điểm nhập than) -- **chưa tự động
hoá phần này**.

### Giới hạn (chưa xử lý, ghi rõ) -- bản đầu (1 hàng, 1 router/generator)

- Chỉ xếp được **1 hàng thẳng** -- không tự wrap sang nhiều hàng nếu N quá
  lớn/map không đủ rộng theo 1 trục.
  Không "double-side" router lane (1 router phục vụ 2 hàng generator trên
  VÀ dưới cùng lúc) như schematic thật user cung cấp -- bản này đơn giản
  hơn: 1 router chỉ phục vụ đúng 1 generator phía trên nó.
- Chỉ dùng **1 drill than duy nhất** bất kể N lớn cỡ nào -- không tự scale
  số lượng/tier drill than theo N để tận dụng hết công suất lý thuyết của
  cụm (xem mục "Trả lời trực tiếp" ở trên) -- **vẫn CHƯA sửa ở bản double-
  sided bên dưới, giới hạn này còn nguyên**.
- `steam-generator` (cần cả than lẫn nước) trong cụm: phần nối `conduit`
  cho nước hiện route THẲNG vào tile router của lane than -- router là
  building ITEM, không tương thích conduit -- **bản double-sided bên dưới
  đã CHẶN HẲN steam-generator cho cụm (raise lỗi rõ ràng), không còn silently
  sai nữa.**

## "Xây N máy phát điện" nâng cấp lên LƯỚI double-sided -- đúng thiết kế schematic thật

User hỏi thẳng sau khi thấy bản 1-hàng: *"Xếp thành 1 hàng thẳng? bot không
thể giống thế này được à"* -- kèm gửi LẠI đúng schematic `.msch` cũ để đối
chiếu. Đúng: bản 1-hàng KHÔNG giống thiết kế thật (schematic dùng lưới 3
hàng generator × 2 hàng router, mỗi router NẰM GIỮA phục vụ CẢ 2 hàng
generator trên-dưới cùng lúc -- double-sided, tiết kiệm hơn "1
router/generator"). Đã làm lại cho đúng.

### Bug thật tự phát hiện + fix trong lúc làm (cả 2 đều nghiêm trọng, verify bằng debug script trước khi merge)

**Bug 1 -- chu trình vô hạn trong đồ thị router (RecursionError)**: khi
double-sided cần 1 CỘT DỌC (spine) nối nhiều hàng router lại với nhau, và
đường belt dẫn than (tìm bằng BFS tổng quát `_route()`/`find_belt_path()`)
tình cờ chạy SÁT CẠNH 1 hàng router KHÁC (không phải hàng đang định nối
tới) -- vì `_trace_branching()` (sim.py) coi BẤT KỲ building nào kề 1
router là hàng xóm hợp lệ (kể cả 1 đoạn belt hoàn toàn không liên quan),
điều này tạo ra 1 CHU TRÌNH thật trong đồ thị: belt → hàng router A → spine
→ hàng router B → (chạm lại đúng đoạn belt ban đầu) → lặp vô hạn. Debug
bằng cách tự viết lại `_trace_branching` rút gọn có đếm depth, in từng lời
gọi ra để soi chính xác vị trí lặp (không đoán) -- xác nhận: router
(10,8) có hàng xóm TÂY là chính đoạn belt dẫn than đi ngang qua, đóng vòng
lặp.

**Bug 2 -- `find_belt_path()` không kiểm cờ `Tile.buildable`**: để sửa Bug
1, cần "chặn tạm" 1 vùng biên (margin) quanh cụm generator trước khi định
tuyến than, ép BFS đi vòng ra ngoài an toàn. Nhưng phát hiện `find_belt_path()`
(dùng CHUNG cho toàn bộ dự án, mọi lệnh nối belt) **trước giờ CHỈ kiểm ô có
building hay chưa, KHÔNG kiểm `grid.tiles[y][x].buildable`** -- field này
tồn tại từ trước (thêm khi bàn về nước/địa hình không xây được) nhưng CHƯA
building nào từng set `False` nên gap này chưa từng lộ ra. Sửa: thêm điều
kiện `buildable` vào vòng lặp mở rộng BFS của `find_belt_path()`
(`bot/planner.py`) -- sửa 1 chỗ, tự động đúng cho MỌI nơi gọi hàm này, kể
cả gap "map có nước không xây được" đã ghi nhận trước đó (dù chưa có building
nào đọc water-tile từ state JSON, engine giờ đã sẵn sàng đúng).

### Đã làm

`_generator_cluster_layout(count, width)`: chia N thành các hàng rộng tối
đa `width` (mặc định 6, khớp schematic thật), hàng cuối có thể ít hơn.
`_generator_cluster_fits()`/`_find_generator_cluster_spot()`: quét vòng
tròn mở rộng tìm chỗ đủ cho TOÀN BỘ lưới (mọi hàng generator + mọi hàng
router + cột spine), thay `_generator_row_fits`/`_find_generator_row_spot`
(bản 1-hàng, đã xoá).

`plan_build_generator_cluster()` viết lại: đặt R hàng generator (rộng tối
đa 6), xen giữa là `max(R-1,1)` hàng router -- mỗi hàng router (trừ trường
hợp R=1) NẰM GIỮA 2 hàng generator liên tiếp, chạm CẢ 2 BÊN cùng lúc (đúng
double-sided). Router thêm 1 cột tại `conn_x` (ngay bên phải hàng rộng
nhất) mỗi hàng, các cột này nối dọc với nhau bằng conveyor lấp khoảng trống
-- tạo thành 1 CỘT SPINE DUY NHẤT xuyên suốt mọi hàng router. Than chỉ nạp
vào ĐÚNG 1 điểm ở ĐỈNH spine. Trước khi định tuyến than: chặn tạm 1 vòng
biên quanh TOÀN BỘ cụm (`grid.tiles[y][x].buildable=False`), chỉ chừa đúng
1 lỗ ở đỉnh spine -- ép BFS không thể lách vào sát bất kỳ hàng router nào
(sửa Bug 1), mở lại `buildable=True` ngay sau khi đặt xong belt (dùng
`try/finally`, đảm bảo mở lại dù `_route()` raise lỗi). `steam-generator`
(hay bất kỳ generator nào có `generator_liquid_inputs`) bị CHẶN HẲN ngay
đầu hàm với lỗi rõ ràng, không còn silently sai như bản trước.

### Test

`bot/generator_cluster_demo.py` kịch bản 2 viết lại: xác nhận số hàng
generator > 1 (với N=21, width mặc định 6 -> 4 hàng), số hàng router =
`max(R-1,1)` (double-sided thật, không phải R), VÀ xác nhận VẬT LÝ mỗi hàng
router chạm CẢ hàng generator TRÊN (`y-1`) lẫn DƯỚI (`y+1`) -- không chỉ
suy luận gián tiếp. Test thêm biên: N=1,5,6,7,12,13,50 (đúng ranh giới
`width=6`, nhiều hàng, N rất lớn) đều đặt đúng N generator, toàn bộ có sản
xuất điện > 0 (không có cái nào "chết" vì gap trong spine).

Kết quả đo được (N=21, layout mới): tổng `power_production` **12.87/s**
(so với 7.76/s của bản 1-hàng cũ, dùng CÙNG 1 mỏ than) -- double-sided
không chỉ tiết kiệm router mà còn cho throughput cao hơn hẳn nhờ đường
phân phối ngắn hơn (ít hop router hơn = ít bị router chia nhỏ dần theo
chuỗi dài).

Regression: 35/35 script pass sau khi sửa (bao gồm cả thay đổi
`find_belt_path()` -- rủi ro cao nhất vì dùng chung toàn dự án, đã chạy lại
FULL bộ test để xác nhận không ảnh hưởng gì tới các tính năng khác).

### Giới hạn còn lại (chưa xử lý, ghi rõ)

- Vẫn chỉ dùng **1 drill than duy nhất** bất kể N -- chưa tự scale nguồn
  than theo số lượng generator (như đã ghi ở bản 1-hàng, chưa sửa).
- `width` mặc định CỐ ĐỊNH = 6, không tự tính toán bố cục tối ưu theo N
  (vd hình vuông hơn cho N lớn, hoặc hẹp hơn nếu map chật theo 1 trục).
- Margin an toàn (chặn `buildable` quanh cụm) tốn thêm 1 vòng ô trống xung
  quanh -- nếu map đã chật sẵn quanh vị trí định đặt, có thể khiến
  `_find_generator_cluster_spot()` khó tìm chỗ hơn cần thiết (chưa
  tối ưu độ rộng margin, luôn cố định 1 ô).
- `_find_generator_cluster_spot()` vẫn chi phí O(N) mỗi ứng viên vị trí --
  N rất lớn (hàng trăm) có thể chậm, chưa benchmark thời gian thật.

## Overflow-gate an toàn cho đường than vào generator -- tránh belt kẹt cứng

User hỏi tiếp về overflow-gate: lúc đầu tưởng user muốn mô phỏng ĐÚNG thời
điểm "đầy" (đã giải thích: simulator này KHÔNG mô phỏng được, chỉ xấp xỉ
tĩnh) -- user chỉnh lại 3 lần liền cho rõ: *"không cần khi đầy mới rẽ, ý
tôi là bot xây dựng thế nào mà khi băng chuyền vào điện đầy thì tài nguyên
tự động về core chứ không phải kẹt cứng"* -- tức chỉ cần bot XÂY SẴN hạ
tầng vật lý đúng (van an toàn), không cần simulator mô phỏng đúng thời
điểm. Việc này khả thi và KHÔNG ảnh hưởng số liệu mô phỏng hiện có.

### Đã làm

`_add_overflow_to_core(grid, actions, path, core)` (`bot/planner.py`): sau
khi `_route()` nối xong producer (drill than) -> consumer (generator) bằng
conveyor thường, "nâng cấp" Ô CUỐI (chạm thẳng consumer) thành
`overflow-gate` (giữ nguyên rotation, vẫn ưu tiên đường thẳng 100% như
trước -- xem `_trace_branching` case `overflow-gate`), rồi thử rẽ thêm 1
nhánh từ 1 trong 2 cạnh VUÔNG GÓC của nó về core. KHÔNG BẮT BUỘC -- nếu
`path` rỗng (producer đã chạm thẳng consumer, không có ô belt nào để nâng
cấp) hoặc không tìm được chỗ rẽ/đường tới core, bỏ qua ÊM, không raise lỗi.

Wire vào nhánh `"generator"` TRỰC TIẾP của `plan_build()` (lệnh "xây máy
phát điện" rõ ràng).

### Bug thật phát hiện khi thử áp dụng RỘNG hơn (verify bằng debug script trước khi quyết định phạm vi)

Lúc đầu wire CẢ vào `_ensure_powered()` (hàm dùng chung cho RẤT NHIỀU ngữ
cảnh: drill/pump/factory/generator-cluster/cả bên trong `filter_split` khi
tự xây factory cần điện) -- chạy full regression phát hiện **3 demo cũ vỡ**
(`bot/split_command_demo.py`, `bot/llm_split_demo.py` báo lỗi "không tìm
được đường belt (nhánh rẽ)"; `bot/power_plant_build_demo.py` lỗi KeyError
do assertion cũ giả định MỌI action đều có key `"building"`, không đúng
nữa vì giờ có thêm action `"remove"`). Debug kỹ (in toàn bộ building trên
map, truy vết từng bước `plan_filter_split`) xác nhận: overflow-gate +
nhánh rẽ về core được `_ensure_powered()` tự thêm cho generator PHỤ (xây
để cấp điện cho silicon-smelter bên trong `filter_split`) đã VÔ TÌNH chiếm
đúng hướng mà sorter của `filter_split` cần để tự nối nhánh RIÊNG của nó
tới core -- 2 lệnh khác nhau tranh chấp cùng 1 "cửa" vào core. Thử mở rộng
map (30x20 -> 45x30) KHÔNG giải quyết được (không phải vấn đề thiếu chỗ
đơn thuần, mà là 2 nhánh cùng nhắm đúng 1 hướng tiếp cận).

Quyết định: **thu hẹp phạm vi lại, KHÔNG wire vào `_ensure_powered()`**,
chỉ giữ ở nhánh `"generator"` trực tiếp (ít lồng ghép, rủi ro tranh chấp
thấp hơn hẳn) -- an toàn hơn triển khai rộng mà gây lỗi ở nơi khác. Sửa
riêng `power_plant_build_demo.py`'s assertion dùng `a.get("building")`
thay vì `a["building"]` (đúng, không phụ thuộc scope overflow-gate).

### Test

`bot/overflow_to_core_demo.py` (4 kịch bản): overflow-gate được thêm đúng 1
cái cho lệnh xây generator; overflow-gate quay mặt thẳng ĐÚNG vào generator
(verify tính toán từ rotation, không chỉ tin suông); nhánh rẽ THẬT SỰ dẫn
tới core (tự đi theo chuỗi belt từ nhánh rẽ, xác nhận chạm footprint core,
không phải belt cụt); số liệu mô phỏng (`power_production`) KHÔNG đổi so
với tính tay theo công thức generator gốc (xác nhận overflow-gate không
làm sai lệch gì, chỉ thêm hạ tầng an toàn cho gameplay thật).

Regression: 36/36 script pass (32 cũ + `bot/overflow_to_core_demo.py` mới,
sau khi thu hẹp phạm vi và sửa `power_plant_build_demo.py`).

### Giới hạn (chưa xử lý, ghi rõ)

- **CHỈ áp dụng cho nhánh `"generator"` trực tiếp** của `plan_build()` --
  generator được tự xây làm PHỤ (bên trong `_ensure_powered()`, vd để cấp
  điện cho 1 drill/factory/cụm khác) KHÔNG có overflow-gate/nhánh an toàn
  này, do rủi ro tranh chấp không gian với lệnh khác đã verify thật ở
  trên. Đây là phần lớn các trường hợp generator được xây trong thực tế sử
  dụng (hầu hết generator được tạo TỰ ĐỘNG qua `_ensure_powered`, không
  phải qua lệnh "xây máy phát điện" trực tiếp).
- Chỉ rẽ về **core** -- không hỗ trợ rẽ về building khác (vd container lưu
  trữ) như user có thể muốn trong tương lai.
- `plan_build_generator_cluster()` (cụm N generator) CHƯA có overflow-gate
  an toàn cho lane than dùng chung -- khác kiến trúc hẳn (router lane, không
  phải conveyor thẳng vào 1 generator), cần thiết kế riêng nếu muốn thêm.
