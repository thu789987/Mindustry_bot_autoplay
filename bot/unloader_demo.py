import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.buildings import CATALOG
from simulator.grid import Grid
from simulator.sim import evaluate_layout

# container (kho) -> unloader (rút "than" ra) -> belt -> core.
# Unloader.java/DirectionalUnloader.java thật: rút item từ building lưu trữ
# liền kề. simulator này KHÔNG track tồn kho thật -- giả định kho luôn còn
# hàng khi filter_item được đặt rõ (xem sim.py _unloader_output_rate).
grid = Grid(width=20, height=10)
container = grid.place(CATALOG["container"], 2, 2)  # size=2, footprint (2,2)-(3,3)
# unloader đặt NGAY SAU container theo hướng đẩy ra (rotation=0/đông): input_tile
# (phía sau, hướng tây) phải trúng container -- unloader tại (4,3), rotation=0:
# input_tile = edge tây = (4-1, 3+0) = (3,3), nằm trong container. Khớp.
unloader = grid.place(CATALOG["unloader"], 4, 3, rotation=0, filter_item="coal")
grid.place(CATALOG["conveyor"], 5, 3, rotation=0)
core = grid.place(CATALOG["core"], 6, 3)

result = evaluate_layout(grid)
# nút thắt = min(base_rate unloader, base_rate conveyor phía sau) -- giống hệt
# cách drill/pump đã bị belt giới hạn trong các demo khác, không phải riêng gì
# unloader.
expected = min(CATALOG["unloader"].base_rate, CATALOG["conveyor"].base_rate)
print("=== Unloader: rút 'coal' từ container liền kề, đẩy ra core ===")
print(f"  core nhận: {result['output_rate'][core]:.4f}/s (kỳ vọng = min(unloader={CATALOG['unloader'].base_rate}, belt={CATALOG['conveyor'].base_rate}) = {expected}/s)")
assert result["output_rate"][core] == expected, "SAI: core phải nhận đúng min(base_rate unloader, base_rate belt)"
print("  ĐÚNG: unloader rút coal từ container, nút thắt đúng ở belt phía sau (chậm hơn unloader).\n")

print("=== Đối chứng 1: unloader CHƯA cấu hình filter_item -> phải là 0/s ===")
grid2 = Grid(width=20, height=10)
grid2.place(CATALOG["container"], 2, 2)
grid2.place(CATALOG["unloader"], 4, 3, rotation=0)  # filter_item=None
grid2.place(CATALOG["conveyor"], 5, 3, rotation=0)
core2 = grid2.place(CATALOG["core"], 6, 3)
result2 = evaluate_layout(grid2)
print(f"  core nhận: {result2['output_rate'][core2]:.4f}/s")
assert result2["output_rate"][core2] == 0, "SAI: chưa cấu hình filter_item thì không được rút gì (không biết kho có gì thật)"
print("  ĐÚNG: chưa cấu hình filter_item -> 0/s (xem giới hạn mô hình trong sim.py).\n")

print("=== Đối chứng 2: phía sau unloader KHÔNG phải storage/core -> phải là 0/s ===")
grid3 = Grid(width=20, height=10)
grid3.place(CATALOG["conveyor"], 2, 3, rotation=0)  # không phải storage
grid3.place(CATALOG["unloader"], 4, 3, rotation=0, filter_item="coal")
grid3.place(CATALOG["conveyor"], 5, 3, rotation=0)
core3 = grid3.place(CATALOG["core"], 6, 3)
result3 = evaluate_layout(grid3)
print(f"  core nhận: {result3['output_rate'][core3]:.4f}/s")
assert result3["output_rate"][core3] == 0, "SAI: unloader chỉ rút được từ storage/core, không phải belt thường"
print("  ĐÚNG: phía sau không phải storage/core -> unloader không sản xuất gì (0/s).")
