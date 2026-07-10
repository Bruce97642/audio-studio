"""白話指令解析器的單元測試。

跑法（擇一）：
  python tests/test_commands.py   ← 不用裝任何東西
  pytest tests/                   ← 有裝 pytest 的話
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from audio_studio.commands import parse_command  # noqa: E402

CASES = [
    ("剪掉 2:10-2:30", ("remove", ["2:10-2:30"])),
    ("幫我剪掉0:05到0:10", ("remove", ["0:05-0:10"])),
    ("剪掉 0:00-0:05 和 3:00-3:10", ("remove", ["0:00-0:05", "3:00-3:10"])),
    ("刪除 130~150", ("remove", ["130-150"])),
    ("只保留 1:00-2:00", ("keep", ["1:00-2:00"])),
    ("保留1:00至2:00就好", ("keep", ["1:00-2:00"])),
    ("刪掉『下星期三』", ("remove_text", "下星期三")),
    ("刪掉「呃那個」", ("remove_text", "呃那個")),
    ("刪掉 下星期三", ("remove_text", "下星期三")),
    ("找『市集活動』", ("find_text", "市集活動")),
    ("搜尋 有機蔬菜", ("find_text", "有機蔬菜")),
    ("去空白", ("trim", None)),
    ("把頭尾的靜音去掉", ("trim", None)),
    ("縮短停頓", ("gaps", None)),
    ("還原", ("undo", None)),
    ("回上一步", ("undo", None)),
    ("加快 1.5 倍", ("speed", 1.5)),
    ("加速", ("speed", 1.25)),
    ("放慢", ("speed", 0.85)),
    ("放慢 1.2 倍", ("speed", 0.833)),
    ("放慢 0.9", ("speed", 0.9)),
    ("加快 5 倍", ("speed", 2.0)),
    ("大聲一點", ("volume", 3.0)),
    ("小聲一點", ("volume", -3.0)),
    ("音量調大", ("volume", 3.0)),
    ("淡入淡出", ("fade", None)),
    ("結尾淡出", ("fade", None)),
    ("今天天氣如何", ("help", None)),
    ("", ("help", None)),
]


def test_parse_command():
    """pytest 進入點：所有白話指令案例。"""
    for text, expected in CASES:
        got = parse_command(text)
        assert got == expected, f"{text!r} -> {got}，預期 {expected}"


if __name__ == "__main__":
    failed = 0
    for text, expected in CASES:
        got = parse_command(text)
        status = "PASS" if got == expected else "FAIL"
        if got != expected:
            failed += 1
            print(f"  {status}  {text!r} -> {got}，預期 {expected}")
        else:
            print(f"  {status}  {text!r} -> {got}")

    print()
    if failed:
        print(f"{failed} 項失敗")
        sys.exit(1)
    print("全部通過！")
