import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.command_parser import parse_commands

tests = [
    "tách ra làm 2",
    "tách than ra làm 2",
    "tách drill than ra làm 2, 1 về core, 1 tạo silicon",
    "khai thác than, tách ra làm 2, 1 về core, 1 tạo silicon",
]

for text in tests:
    commands = parse_commands(text)
    print(f"> {text!r}")
    print(f"  -> {len(commands)} lệnh nhận diện được: {commands}\n")
