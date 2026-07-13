"""Bridge to a live Mindustry headless server -- CHUA TEST THAT (chưa có Java
trên máy lúc viết file này). Dựa trên API đã xác nhận qua source thật
(xem NEXT_STEPS.md, mục "Các hàm API đã xác nhận thật"), nhưng 3 điều sau
CHỈ xác nhận được khi chạy thật, xem NEXT_STEPS.md để biết chi tiết:
  - định dạng chính xác của dòng log server in ra (mã màu ANSI kiểu &fi&lw&fb)
  - thread nào chạy runConsole(), gửi lệnh liên tiếp có an toàn không
  - quét state trên map lớn có đủ nhanh không

Cách đối phó với 2 điều chưa chắc đầu tiên: không cố parse/strip mã màu, chỉ
tìm marker cố định (vd "BOT_STATE:") làm chuỗi con trong dòng log và lấy phần
sau nó -- mã màu nằm ở phần server tự thêm trước chuỗi mình in ra, không ảnh
hưởng tới nội dung sau marker.
"""

import json
import queue
import subprocess
import threading
import time

STATE_MARKER = "BOT_STATE:"
OK_MARKER = "BOT_OK:"
ERR_MARKER = "BOT_ERR:"

# single-line JS: scans every tile once, matches the schema bot/state.py expects
_READ_STATE_JS = (
    'var o={{buildings:[],ore_tiles:[],width:Vars.world.width(),height:Vars.world.height()}};'
    'for(var x=0;x<o.width;x++)for(var y=0;y<o.height;y++){{'
    'var t=Vars.world.tile(x,y);'
    'if(t.drop()!=null)o.ore_tiles.push({{x:x,y:y,ore:t.drop().name}});'
    'if(t.build!=null&&t.build.tile==t)o.buildings.push({{type:t.block().name,x:x,y:y,rotation:t.build.rotation}})'
    '}}'
    'print("{marker}"+JSON.stringify(o));'
).format(marker=STATE_MARKER)


class MindustryServer:
    def __init__(self, jar_path: str, response_timeout: float = 10.0):
        self.jar_path = jar_path
        self.response_timeout = response_timeout
        self._process = None
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._reader_thread = None

    def start(self):
        self._process = subprocess.Popen(
            ["java", "-jar", self.jar_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        time.sleep(2)  # let the JVM boot before sending anything

    def _read_loop(self):
        for line in self._process.stdout:
            self._lines.put(line.rstrip("\n"))

    def _send_line(self, text: str):
        self._process.stdin.write(text + "\n")
        self._process.stdin.flush()

    def _wait_for_marker(self, marker: str):
        """Reads lines until one contains `marker`, ignoring unrelated server
        log spam in between. Returns the substring after the marker."""
        deadline = time.monotonic() + self.response_timeout
        while time.monotonic() < deadline:
            try:
                line = self._lines.get(timeout=deadline - time.monotonic())
            except queue.Empty:
                break
            if marker in line:
                return line.split(marker, 1)[1]
        raise TimeoutError(
            f"không thấy marker {marker!r} trong {self.response_timeout}s -- "
            "định dạng log thật có thể khác dự đoán, xem NEXT_STEPS.md"
        )

    def host(self, map_name: str = None):
        self._send_line(f"host {map_name}" if map_name else "host")
        time.sleep(3)  # world loading isn't synchronous with the console

    def run_js(self, code: str) -> str:
        if "\n" in code:
            raise ValueError("js console command phải là 1 dòng")
        self._send_line(f"js {code}")

    def read_state(self) -> dict:
        self.run_js(_READ_STATE_JS)
        payload = self._wait_for_marker(STATE_MARKER)
        return json.loads(payload)

    def execute(self, actions: list) -> list:
        """Runs each planner action (see bot/planner.py) against the live
        server. ore_target in an action is only used locally by our own
        simulator (drill_output_rate) -- the real game infers what a drill
        mines from the ore actually under it, so it's not sent here."""
        results = []
        for action in actions:
            code = (
                f'Vars.world.tile({action["x"]},{action["y"]})'
                f'.setBlock(Vars.content.block("{action["building"]}"), Team.sharded, {action["rotation"]});'
                f'print("{OK_MARKER}"+"{action["building"]}@{action["x"]},{action["y"]}")'
            )
            self.run_js(code)
            try:
                result = self._wait_for_marker(OK_MARKER)
                results.append({"action": action, "ok": True, "detail": result})
            except TimeoutError as e:
                results.append({"action": action, "ok": False, "detail": str(e)})
        return results

    def stop(self):
        if self._process is not None:
            self._send_line("stop")
            self._process.terminate()
