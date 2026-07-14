"""Giai đoạn 3 -- vòng lặp chat thật, ghép toàn bộ pipeline lại.
CHƯA TEST ĐƯỢC (chưa có Java/server thật lúc viết file này). Đây là script
sẽ chạy khi bạn có Java + server-release.jar (xem NEXT_STEPS.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.llm_parser import parse_commands_auto
from bot.mod_bridge import MindustryServer
from bot.planner import plan
from bot.state import grid_from_state

JAR_PATH = "server-release.jar"  # sửa thành đường dẫn thật sau khi tải về

# parse_commands_auto (bot/llm_parser.py): ưu tiên LM Studio, tự rơi về dict
# parser (bot/command_parser.py) nếu LM Studio không chạy/không phản hồi
# đúng định dạng. LM Studio hiểu được cấu trúc phân nhánh ("tách than ra làm
# 2, 1 về core 1 tạo silicon") mà dict KHÔNG tách nổi (dict chỉ chia câu
# theo dấu phẩy/"và" thành các Ý ĐỘC LẬP, không hiểu quan hệ phân nhánh --
# xem NEXT_STEPS.md).


def run_command(server: MindustryServer, text: str):
    commands = parse_commands_auto(text)
    if not commands:
        print(f"không hiểu lệnh: {text!r}")
        return

    for command in commands:
        state = server.read_state()  # đọc lại sau mỗi lệnh vì state vừa đổi
        grid = grid_from_state(state)
        try:
            actions = plan(grid, command)
        except (ValueError, RuntimeError) as e:
            print(f"  [{command.get('building', command.get('action'))}] không lập được kế hoạch: {e}")
            continue

        results = server.execute(actions)
        for r in results:
            status = "OK" if r["ok"] else "LỖI"
            print(f"  [{status}] {r['action']}  {r['detail']}")


if __name__ == "__main__":
    server = MindustryServer(JAR_PATH)
    server.start()
    server.host()

    try:
        while True:
            text = input("chat> ").strip()
            if text in ("exit", "quit"):
                break
            run_command(server, text)
    finally:
        server.stop()
