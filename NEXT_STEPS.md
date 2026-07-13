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

## Trạng thái hiện tại (đã làm xong)

- **Giai đoạn 1 — XONG, đã chạy và xác nhận.** Xem `bot/`:
  - `command_parser.py` — dict tiếng Việt → tên building.
  - `state.py` — dựng `Grid` từ JSON state (hợp đồng dữ liệu cho mod ở
    Giai đoạn 2).
  - `planner.py` — auto-connect thật: tìm nguồn nguyên liệu (ưu tiên building
    có sẵn, không có thì tự đặt drill mới), tìm chỗ trống, định tuyến belt
    bằng BFS, xuất danh sách hành động `place`.
  - `example_run.py` — chạy thử `"xây nhà máy silicon"` trên state giả (có
    sẵn drill than, có mỏ cát chưa khai thác) → tự đặt drill cát mới + nối
    2 đường belt (than, cát) tới silicon-smelter. Đã dùng `evaluate_layout`
    của luồng A để xác nhận silicon thực sự chảy ra (0.2/s, bị giới hạn bởi
    tốc độ cung cát) — không chỉ tọa độ hợp lệ mà dòng vật liệu đúng thật.
  - `simulator/buildings.py`, `simulator/sim.py` đã mở rộng để hỗ trợ recipe
    nhiều input (silicon-smelter cần cả than lẫn cát cùng lúc).
- **Giai đoạn 2 (mod Java/JS trong game)** — chưa code gì, đang chờ cài Java.
- **Giai đoạn 3 (ghép nối)** — chưa làm, phụ thuộc Giai đoạn 2.

### Chạy thử lại Giai đoạn 1 (không cần Java)

```
$env:PYTHONIOENCODING="utf-8"; python mindustry-factory-ai/bot/example_run.py
```
(set `PYTHONIOENCODING` vì console Windows mặc định không phải UTF-8, tiếng
Việt sẽ báo lỗi encoding nếu không set trước.)
