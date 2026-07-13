"""Giai đoạn 3 -- vòng lặp chat thật, ghép toàn bộ pipeline lại.
CHƯA TEST ĐƯỢC (chưa có Java/server thật lúc viết file này). Đây là script
sẽ chạy khi bạn có Java + server-release.jar (xem NEXT_STEPS.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.llm_parser import parse_command_auto
from bot.mod_bridge import MindustryServer
from bot.planner import plan
from bot.state import grid_from_state

JAR_PATH = "server-release.jar"  # sửa thành đường dẫn thật sau khi tải về

# parse_command_auto ưu tiên LM Studio (bot/llm_parser.py), tự rơi về dict
# parser (bot/command_parser.py) nếu LM Studio chưa bật/không kết nối được
# -- xem NEXT_STEPS.md mục "Bộ dịch lệnh bằng LM Studio" để đổi model/base_url.


def run_command(server: MindustryServer, text: str):
    command = parse_command_auto(text)
    if command.get("action") == "unknown":
        print(f"không hiểu lệnh: {text!r}")
        return

    state = server.read_state()
    grid = grid_from_state(state)
    try:
        actions = plan(grid, command)
    except (ValueError, RuntimeError) as e:
        print(f"không lập được kế hoạch: {e}")
        return

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
