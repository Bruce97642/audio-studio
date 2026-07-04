"""音檔健檢：響度、峰值、噪音底層。"""

from __future__ import annotations

import re
from pathlib import Path

from .ffmpeg_utils import fmt_time, probe_duration, run_ffmpeg


def analyze(input_path: str | Path) -> dict:
    """量測音檔並印出報告，回傳量測值。"""
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到檔案：{src}")

    duration = probe_duration(src)
    stderr = run_ffmpeg([
        "-i", str(src),
        "-af", "ebur128=peak=true,volumedetect,"
               "astats=measure_overall=RMS_trough:measure_perchannel=none",
        "-f", "null", "-"])

    # ebur128 的總結數據在最後的 Summary 區塊（前面是逐秒進度，不能拿）
    summary = stderr[stderr.rfind("Summary:"):]

    def grab(pattern: str, text: str = stderr) -> str:
        m = re.search(pattern, text)
        return m.group(1) if m else "?"

    report = {
        "長度": fmt_time(duration),
        "整體響度 (LUFS)": grab(r"I:\s+(-?[\d.]+) LUFS", summary),
        "響度範圍 LRA": grab(r"LRA:\s+([\d.]+) LU", summary),
        "真實峰值 (dBTP)": grab(r"Peak:\s+(-?[\d.]+) dBFS", summary),
        "平均音量 (dB)": grab(r"mean_volume:\s+(-?[\d.]+) dB"),
        "最大音量 (dB)": grab(r"max_volume:\s+(-?[\d.]+) dB"),
        "最安靜片段 RMS (dB)": grab(r"RMS th?rough dB:\s+(-?[\d.]+|-?inf)"),
    }
    width = max(len(k) for k in report)
    for key, value in report.items():
        print(f"  {key:<{width}}  {value}")
    return report
