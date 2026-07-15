import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

# drill than -> bridge-conveyor (link tới bridge thứ 2 cách 3 ô, TRỐNG ở
# giữa, không đặt belt) -> tiếp tục đi thẳng ra core. ItemBridge.java thật:
# item "nhảy" qua khoảng trống bỏ qua vật cản, range=4 ô (bridge-conveyor).
grid = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid.set_ore(x, y, "coal")
drill = grid.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid.place(CATALOG["conveyor"], 4, 3, rotation=0)

bridge_a = grid.place(CATALOG["bridge-conveyor"], 5, 3, rotation=0)
# (6,3),(7,3),(8,3) CỐ Ý để trống -- vật cản/khoảng trống bridge phải nhảy qua
bridge_b = grid.place(CATALOG["bridge-conveyor"], 9, 3, rotation=0, link_target=bridge_a)
bridge_a.link_target = bridge_b  # link 2 chiều, giống config(Point2) thật

grid.place(CATALOG["conveyor"], 10, 3, rotation=0)
core = grid.place(CATALOG["core"], 11, 3)

result = evaluate_layout(grid)
print("=== Item Bridge: nhảy qua khoảng trống 3 ô không có belt ===")
print(f"  core nhận: {result['output_rate'][core]:.4f}/s")
assert result["output_rate"][core] > 0, "SAI: item phải nhảy qua bridge tới core dù giữa 2 bridge không có belt"
print("  ĐÚNG: item nhảy từ bridge_a qua bridge_b (bỏ qua khoảng trống giữa),")
print("  rồi tiếp tục ra core -- đúng cơ chế ItemBridge.java thật.\n")

print("=== Đối chứng 1: bridge CHƯA link, KHÔNG có ô kề nào khác ngoài đường vào -> 0/s ===")
grid2 = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid2.set_ore(x, y, "coal")
grid2.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid2.place(CATALOG["conveyor"], 4, 3, rotation=0)
grid2.place(CATALOG["bridge-conveyor"], 5, 3, rotation=0)  # không link, cô lập
core2 = grid2.place(CATALOG["core"], 11, 3)  # xa, không kề bridge
result2 = evaluate_layout(grid2)
print(f"  core nhận: {result2['output_rate'][core2]:.4f}/s")
assert result2["output_rate"][core2] == 0, "SAI: không có ô kề nào để dump ra thì core không thể nhận được gì"
print("  ĐÚNG: không có ô kề hợp lệ nào để dump -> core không nhận được gì (đúng, nhưng")
print("  KHÔNG phải vì bridge 'bị kẹt' -- xem đối chứng 2).\n")

print("=== Đối chứng 2: bridge CHƯA link nhưng CÓ ô kề khác -> tự dump ra đó (SỬA sau khi kiểm tra ItemBridge.java thật) ===")
grid3 = Grid(width=30, height=20)
for x, y in [(2, 2), (3, 2), (2, 3), (3, 3)]:
    grid3.set_ore(x, y, "coal")
grid3.place(CATALOG["mechanical-drill"], 2, 2, rotation=0, ore_target="coal")
grid3.place(CATALOG["conveyor"], 4, 3, rotation=0)
grid3.place(CATALOG["bridge-conveyor"], 5, 3, rotation=0)  # không link
# core đặt SÁT bridge (footprint core 3x3 chạm ô (5,4), ngay phía nam bridge)
core3 = grid3.place(CATALOG["core"], 4, 4)
result3 = evaluate_layout(grid3)
print(f"  core nhận: {result3['output_rate'][core3]:.4f}/s")
assert result3["output_rate"][core3] > 0, (
    "SAI: ItemBridge.java thật gọi doDump() khi chưa có link hợp lệ -- phải tự đẩy item "
    "ra ô kề vật lý (core) như 1 building bình thường, không phải kẹt lại tại chỗ"
)
print("  ĐÚNG: bridge chưa link vẫn tự dump ra ô kề vật lý (core), đúng doDump() thật --")
print("  KHÔNG bị kẹt như bản trước đây từng cài sai (xem NEXT_STEPS.md).")
