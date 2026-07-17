"""Bộ nhớ NGÔN NGỮ TỰ NHIÊN cho bot/agent_loop.py -- khác hẳn bot/scorer.py
(1 vector trọng số số học tuyến tính): mỗi dòng ghi lại "lần trước thử làm
gì, kết quả ra sao" bằng câu chữ, đưa lại NGUYÊN VĂN vào system prompt của
lượt sau, để LLM tự đọc hiểu LÝ DO thất bại/thành công thay vì chỉ thấy 1
con số trọng số đã dịch chuyển.

User: "AI sẽ tự học lỗi trước đó" -> quyết định qua bàn bạc (xem
NEXT_STEPS.md mục vòng lặp agent): scorer.py phù hợp cho việc "chọn spot
nào trong nhiều spot hợp lệ" (bài toán liên tục, cần 1 con số so sánh) --
nhưng "lần trước xây power-node ở (40,40) bị lỗi 'không tìm được chỗ
trống'" là 1 SỰ KIỆN rời rạc có NGỮ CẢNH, hợp với ghi chú câu chữ hơn là ép
vào 1 đặc trưng số.

Lọc "liên quan" ở đây CHỈ so khớp TỪ KHOÁ (dict-based, đúng tinh thần toàn
dự án -- command_parser.py cũng chỉ tra từ khoá, không dùng embedding/model
ngữ nghĩa nào) -- không phải "học" thật theo nghĩa cập nhật mô hình, chỉ là
tra cứu lại ghi chú cũ khớp chủ đề. Xem NEXT_STEPS.md cho giới hạn đầy đủ."""

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MEMORY_PATH = Path(__file__).resolve().parent / "agent_memory_log.json"


def _load_entries(path: Path) -> list:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []  # file hỏng/không đọc được -- coi như chưa có ký ức, không crash


def record_memory(entry: dict, path: Path = DEFAULT_MEMORY_PATH, max_entries: int = 500) -> None:
    """Ghi thêm 1 dòng ký ức. entry cần có "goal"/"command"/"result"/"detail"
    (xem bot/agent_loop.py) -- tự thêm "timestamp". Cắt bớt dòng CŨ NHẤT nếu
    vượt max_entries (tránh file phình vô hạn qua nhiều phiên chạy)."""
    entries = _load_entries(path)
    entries.append({"timestamp": datetime.now(timezone.utc).isoformat(), **entry})
    if len(entries) > max_entries:
        entries = entries[-max_entries:]
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_relevant(goal_text: str, path: Path = DEFAULT_MEMORY_PATH, limit: int = 5) -> str:
    """Lọc các dòng ký ức có "goal" CHIA SẺ ít nhất 1 từ (tách theo khoảng
    trắng, không phân biệt hoa/thường) với goal_text hiện tại, lấy `limit`
    dòng GẦN ĐÂY NHẤT khớp, format bullet tiếng Việt để chèn vào system
    prompt. "" nếu không có gì khớp/file chưa tồn tại (không tạo noise rỗng
    trong prompt)."""
    entries = _load_entries(path)
    if not entries:
        return ""
    goal_words = set(goal_text.lower().split())
    relevant = [e for e in entries if goal_words & set(str(e.get("goal", "")).lower().split())]
    if not relevant:
        return ""
    recent = relevant[-limit:]
    lines = [f"Ký ức từ các lần thử mục tiêu tương tự trước đây ({len(recent)}/{len(relevant)} dòng khớp gần nhất):"]
    for e in recent:
        cmd = e.get("command")
        cmd_text = f"{cmd.get('action')} {cmd.get('building', '')}".strip() if isinstance(cmd, dict) else "(không có lệnh)"
        lines.append(f"  - [{e.get('result', '?')}] thử \"{cmd_text}\" -> {e.get('detail', '')}")
    return "\n".join(lines)
