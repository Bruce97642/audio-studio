"""FFmpeg / ffprobe 共用工具。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RNNOISE_MODEL = REPO_ROOT / "models" / "bd.rnnn"

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
              ".wma", ".mp4", ".mov", ".mkv", ".webm", ".amr", ".3gp"}


class FFmpegError(RuntimeError):
    pass


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> str:
    """執行 ffmpeg，回傳 stderr 文字（ffmpeg 的統計都印在 stderr）。"""
    cmd = ["ffmpeg", "-hide_banner", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg 執行失敗：\n{proc.stderr[-2000:]}")
    return proc.stderr


def probe_duration(path: str | Path) -> float:
    """取得音檔長度（秒）。"""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe 讀取失敗：{path}\n{proc.stderr[-500:]}")
    return float(json.loads(proc.stdout)["format"]["duration"])


def parse_time(spec: str) -> float:
    """把 '2:30'、'1:02:03.5'、'150' 這類時間字串轉成秒數。"""
    spec = spec.strip()
    parts = spec.split(":")
    if not 1 <= len(parts) <= 3 or not all(p.strip() for p in parts):
        raise ValueError(f"看不懂的時間格式：{spec}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"看不懂的時間格式：{spec}") from None
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def parse_range(spec: str) -> tuple[float, float]:
    """把 '2:10-2:30' 轉成 (開始秒, 結束秒)。"""
    m = re.fullmatch(r"\s*([\d:.]+)\s*[-~到至]\s*([\d:.]+)\s*", spec)
    if not m:
        raise ValueError(f"看不懂的時間範圍：{spec}（範例：2:10-2:30）")
    start, end = parse_time(m.group(1)), parse_time(m.group(2))
    if end <= start:
        raise ValueError(f"結束時間必須在開始之後：{spec}")
    return start, end


def fmt_time(seconds: float) -> str:
    """秒數轉 '分:秒.毫秒' 顯示。"""
    m, s = divmod(max(seconds, 0.0), 60)
    return f"{int(m)}:{s:05.2f}"


def encode_args(output: Path) -> list[str]:
    """依副檔名決定輸出編碼參數。"""
    ext = output.suffix.lower()
    if ext == ".wav":
        return ["-c:a", "pcm_s16le"]
    if ext == ".flac":
        return ["-c:a", "flac"]
    if ext in (".m4a", ".aac", ".mp4"):
        return ["-c:a", "aac", "-b:a", "192k"]
    return ["-c:a", "libmp3lame", "-b:a", "192k"]  # 預設 mp3


def collect_audio_files(inputs: list[str]) -> list[Path]:
    """把輸入（檔案或資料夾）展開成音檔清單。"""
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files += sorted(f for f in p.iterdir()
                            if f.suffix.lower() in AUDIO_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"找不到檔案：{item}")
    if not files:
        raise FileNotFoundError("資料夾裡沒有可處理的音檔")
    return files
