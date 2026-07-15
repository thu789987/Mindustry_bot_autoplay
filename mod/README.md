# log-learning — mod Java ghi log gameplay thật

Đóng phần "chưa có Java trên máy để build/test" đã ghi từ đầu dự án ở
`bot/mod_bridge.py`. Mod này KHÔNG tự động chơi hộ, KHÔNG gửi lệnh vào game —
nó chỉ NGHE 3 sự kiện xây dựng thật của Mindustry và ghi ra file, để
`bot/log_learning.py` (đã viết và test xong ở phía Python từ trước, xem
`bot/log_learning_demo.py`) đọc lại và tự rút phản hồi cho `bot/scorer.py`.

## Build

Cần JDK 17 (khớp `sourceCompatibility` trong `build.gradle`, xem template gốc
`Anuken/MindustryJavaModTemplate`) và Gradle (dùng Gradle hệ thống, thư mục
này không kèm sẵn `gradlew` wrapper):

```
cd mod
gradle jar
```

Ra file `build/libs/log-learningDesktop.jar`.

## Cài vào game

Đổi tên `log-learningDesktop.jar` thành `log-learning.jar` (hoặc giữ nguyên,
Mindustry không bắt buộc tên file), copy vào thư mục mods của Mindustry:

- Windows: `%appdata%\Mindustry\mods\`
- Linux: `~/.local/share/Mindustry/mods/`

Bật mod trong game: Settings → Mods → tick "Log Learning".

## Log ghi ra đâu, format thế nào

Mỗi lần bắt đầu chơi (map đơn hoặc host server), mod tạo 1 thư mục mới:

```
<thư mục data Mindustry>/log-learning/<yyyy-MM-dd_HH-mm-ss>/
  initial_state.json   -- trạng thái map lúc bắt đầu (ore/liquid/building có sẵn)
  actions.jsonl         -- mỗi dòng 1 hành động, JSON, theo đúng thứ tự xảy ra
```

`initial_state.json` đúng format `bot/state.py` kỳ vọng:

```json
{"width": 200, "height": 200,
 "ore_tiles": [{"x": 10, "y": 12, "ore": "coal"}, ...],
 "liquid_tiles": [{"x": 5, "y": 5, "liquid": "water"}, ...],
 "buildings": [{"type": "core-shard", "x": 100, "y": 100, "rotation": 0}, ...]}
```

`actions.jsonl` đúng format `bot/log_learning.py` kỳ vọng (mỗi dòng độc lập,
không phải 1 mảng JSON):

```json
{"op": "place", "building": "conveyor", "x": 10, "y": 5, "rotation": 0}
{"op": "remove", "x": 10, "y": 5}
{"op": "configure", "x": 10, "y": 5, "value": "coal"}
{"op": "rotate", "x": 10, "y": 5, "rotation": 2}
```

## Dùng log đã ghi để học (phía Python)

```python
import json
from bot.log_learning import extract_feedback_from_log
from bot.scorer import Scorer

session_dir = "..."  # thư mục 1 phiên, xem đường dẫn ở trên
with open(f"{session_dir}/initial_state.json", encoding="utf-8") as f:
    initial_state = json.load(f)
with open(f"{session_dir}/actions.jsonl", encoding="utf-8") as f:
    log_actions = [json.loads(line) for line in f if line.strip()]

scorer = Scorer()  # hoặc Scorer() load lại trọng số cũ đã lưu, xem scorer.py
n_pairs = extract_feedback_from_log(initial_state, log_actions, scorer)
print(f"đã tự tạo {n_pairs} cặp feedback")
```

## Sự kiện bắt, field lấy từ đâu (đối chiếu với source thật)

Đã tải `EventType.java`, `Tile.java`, `Block.java`, `Floor.java`,
`OreBlock.java`, `PlayerComp.java` từ `github.com/Anuken/Mindustry` (nhánh
`master`) để xác nhận từng field trước khi viết, không đoán:

| Sự kiện | Field dùng | Ghi thành |
|---|---|---|
| `BlockBuildEndEvent` (`breaking=false`) | `tile.build.block.name`, `.tileX()/.tileY()`, `.rotation` | `op: place` |
| `BlockBuildEndEvent` (`breaking=true`) | `tile.x`, `tile.y` | `op: remove` |
| `ConfigEvent` | `tile.tileX()/.tileY()`, `value` (Item/Liquid/boolean/số → map đúng; kiểu khác → string) | `op: configure` |
| `BuildRotateEvent` | `build.tileX()/.tileY()`, `build.rotation` (rotation SAU khi xoay, không phải `previous`) | `op: rotate` |

## Giới hạn (biết trước, chưa xử lý)

- **Chỉ ghi hành động của TEAM người chơi cục bộ** (`player.team`) — không
  phân biệt chính người chơi hay drone tự xây theo blueprint của người chơi
  (cả 2 đều tính là "ý định của người chơi").
- **Chỉ hoạt động khi mod này chạy ở phía mô phỏng thế giới thật** — map đơn,
  hoặc máy đang là host của server. Vào server người khác mà họ không cài mod
  này thì các sự kiện trên không phát sinh ở máy mình (đặc thù kiến trúc
  client/server của Mindustry, không phải giới hạn riêng của mod này).
- **`ConfigEvent.value` chỉ ánh xạ đúng cho Item/Liquid/boolean/số** (đủ dùng
  cho sorter lọc item — trường hợp `bot/log_learning.py` hiện đọc). Các kiểu
  khác (`Point2`/`Point2[]` dùng cho link bridge/mass-driver) ghi tạm thành
  chuỗi để không mất dữ liệu, nhưng phía Python hiện chưa đọc field này cho
  các loại building đó.
- **`initial_state.json` không suy luận lại `ore_target`** cho drill đã có
  sẵn từ trước khi phiên log bắt đầu (Drill thật không configurable ore —
  game tự chọn ore chiếm đa số trong footprint). Không ảnh hưởng simulator vì
  `bot/state.py` coi `ore_target` là optional.
- **Chưa build/test thật** — máy hiện tại không có Java, giống điều kiện
  chưa đáp ứng của `bot/mod_bridge.py` từ đầu dự án. Code viết đối chiếu kỹ
  từng field với source thật (bảng trên), nhưng chưa chạy qua compiler thật
  hay in-game thật lần nào.
