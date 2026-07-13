# Việc cần làm tiếp — đọc file này khi quay lại

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

## Bộ dịch lệnh bằng LM Studio (thay dict, tổng quát hoá được)

Trả lời phần còn lại: "model AI sẽ biên dịch hành động chứ" — đã thêm
`bot/llm_parser.py`, dùng model chạy trong LM Studio để dịch câu chat thay
cho dict tra từ khoá. **CHƯA TEST** (không có LM Studio chạy trên máy lúc
viết) — nhưng phần **fallback đã test thật và chạy đúng**.

- **Cách hoạt động**: gọi LM Studio qua API tương thích OpenAI
  (`http://localhost:1234/v1/chat/completions` mặc định). System prompt cấp
  cho model **toàn bộ danh sách building thật** (từ mục trên, lọc còn loại
  planner hỗ trợ: drill/belt/factory) để model không bịa tên — đúng tinh
  thần bạn muốn: model tự tổng quát hoá cách nói, không cần tôi thêm dict
  mỗi khi có building/cách diễn đạt mới.
- **Không tin mù quáng output model**: `_validate()` kiểm tra `building`
  phải nằm trong `CATALOG` thật, `action`/`rotation` phải hợp lệ — sai gì
  cũng coi là `unknown` thay vì để lỗi rơi xuống `planner.py`.
- **`parse_command_auto(text)`** — hàm chính nên dùng: thử LM Studio trước,
  lỗi kết nối/JSON sai thì tự rơi về dict parser (`bot/command_parser.py`),
  không crash cả bot. **Đã test riêng phần này** (LM Studio chưa chạy →
  đúng như kỳ vọng, rơi về dict parser, kết quả đúng).
- **`bot/live_run.py`** đã đổi sang gọi `parse_command_auto` thay vì dict
  parser trực tiếp.

### Việc cần làm khi có LM Studio (bổ sung vào checklist Giai đoạn 2)

1. Mở LM Studio, tải 1 model, bật **Local Server** (mặc định cổng 1234).
2. Model đề xuất (xem thêm docstring đầu `bot/llm_parser.py`):
   - **Qwen2.5-7B-Instruct** — khuyên dùng trước, tuân thủ JSON schema tốt,
     tiếng Việt ổn. Đây chỉ là gợi ý, đổi tay được.
   - Máy yếu hơn: Qwen2.5-3B-Instruct hoặc Phi-3.5-mini-instruct.
   - Không cần model quá lớn — đây là tác vụ trích xuất JSON theo schema cố
     định, không cần suy luận sâu.
3. Sửa `DEFAULT_MODEL` trong `bot/llm_parser.py` cho khớp đúng tên model bạn
   load (LM Studio đặt tên theo file model, không phải "Qwen2.5-7B-Instruct"
   suông — kiểm tra tên chính xác trong tab "My Models" của LM Studio).
4. Chạy thử trực tiếp (không cần Java/Mindustry, chỉ cần LM Studio đang
   chạy):
   ```
   python -c "from bot.llm_parser import parse_command_llm; print(parse_command_llm('xây nhà máy silicon'))"
   ```
   Nếu lỗi, đó là lần đầu code này chạy thật — gửi lại lỗi để sửa dựa trên
   phản hồi thật của model (có thể cần chỉnh lại system prompt nếu model
   không tuân thủ JSON schema tốt).

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

### Chạy thử lại (không cần Java)

```
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/example_run.py
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/learn_demo.py
```
(set `PYTHONIOENCODING` vì console Windows mặc định không phải UTF-8, tiếng
Việt sẽ báo lỗi encoding nếu không set trước.)
