"""純函式的單元測試：時間解析、範圍合併、檔名消毒。

跑法（擇一）：
  python tests/test_utils.py   ← 不用裝任何東西
  pytest tests/                ← 有裝 pytest 的話
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from audio_studio.edit import _keep_segments, _merge_ranges  # noqa: E402
from audio_studio.ffmpeg_utils import (fmt_time, parse_range,  # noqa: E402
                                       parse_time, safe_filename)


def test_parse_time():
    assert parse_time("150") == 150.0
    assert parse_time("2:30") == 150.0
    assert parse_time("1:02:03.5") == 3723.5
    assert parse_time("0:00") == 0.0
    for bad in ("", ":", "1:2:3:4", "abc", "1::2"):
        try:
            parse_time(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 應該要報錯")


def test_parse_range():
    assert parse_range("2:10-2:30") == (130.0, 150.0)
    assert parse_range("130~150") == (130.0, 150.0)
    assert parse_range("1:00到2:00") == (60.0, 120.0)
    for bad in ("2:30-2:10", "5-5", "abc-def", "10"):
        try:
            parse_range(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 應該要報錯")


def test_fmt_time():
    assert fmt_time(0) == "0:00.00"
    assert fmt_time(75.5) == "1:15.50"
    assert fmt_time(-3) == "0:00.00"          # 負數夾成 0
    assert fmt_time(3661.25) == "1:01:01.25"  # 超過一小時要顯示小時
    assert fmt_time(4500) == "1:15:00.00"


def test_merge_ranges():
    # 重疊與相鄰的範圍要合併，超界的要夾回 [0, duration]
    assert _merge_ranges(10, [(2, 5), (4, 7)]) == [(2, 7)]
    assert _merge_ranges(10, [(6, 8), (1, 3)]) == [(1, 3), (6, 8)]
    assert _merge_ranges(10, [(-5, 3), (8, 99)]) == [(0, 3), (8, 10)]
    assert _merge_ranges(10, [(11, 12)]) == []  # 完全超界 → 空


def test_keep_segments():
    # 剪掉中段 → 留頭尾
    assert _keep_segments(10, [(3, 5)]) == [(0, 3), (5, 10)]
    # 剪掉重疊的兩段 → 合併後再取補集
    assert _keep_segments(10, [(2, 5), (4, 7)]) == [(0, 2), (7, 10)]
    # 全剪光 → 什麼都不剩
    assert _keep_segments(10, [(0, 10)]) == []
    # 太短的碎片（< 0.05 秒）要丟棄
    assert _keep_segments(10, [(0.02, 10)]) == []


def test_safe_filename():
    assert safe_filename("我的錄音", "後備") == "我的錄音"
    assert safe_filename("../../etc/passwd", "後備") == "_.._etc_passwd"
    assert safe_filename('a/b\\c:d*e?f"g<h>i|j', "後備") == "a_b_c_d_e_f_g_h_i_j"
    assert safe_filename("   ", "後備") == "後備"
    assert safe_filename("...", "後備") == "後備"


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
    print()
    if failed:
        print(f"{failed} 項失敗")
        sys.exit(1)
    print("全部通過！")
