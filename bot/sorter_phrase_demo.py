import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_commands

tests = [
    "than đi thẳng vào máy X, mọi thứ khác rẽ sang máy Y",
    "cấu hình bộ lọc sorter thành than",
    "than đi thẳng, còn lại rẽ sang bên",
]

for text in tests:
    commands = parse_commands(text)
    print(f"> {text!r}")
    print(f"  -> {len(commands)} lệnh: {commands}\n")
