"""剪輯功能：剪掉片段、接檔案、去除空白。"""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_utils import (FFmpegError, encode_args, fmt_time,
                           parse_range, probe_duration, run_ffmpeg)

MIN_SEGMENT = 0.05  # 小於這個長度的碎片直接丟棄（秒）


def _keep_segments(duration: float, remove: list[tuple[float, float]]
                   ) -> list[tuple[float, float]]:
    """由「要剪掉的範圍」推出「要保留的範圍」。"""
    merged: list[list[float]] = []
    for start, end in sorted(remove):
        start, end = max(0.0, start), min(end, duration)
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    keep, cursor = [], 0.0
    for start, end in merged:
        if start - cursor > MIN_SEGMENT:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor > MIN_SEGMENT:
        keep.append((cursor, duration))
    return keep


def _concat_segments(src: Path, segments: list[tuple[float, float]],
                     out: Path) -> None:
    parts, labels = [], []
    for i, (start, end) in enumerate(segments):
        parts.append(f"[0:a]atrim=start={start:.4f}:end={end:.4f},"
                     f"asetpts=PTS-STARTPTS[s{i}]")
        labels.append(f"[s{i}]")
    graph = (";".join(parts) + ";" + "".join(labels)
             + f"concat=n={len(segments)}:v=0:a=1[out]")
    run_ffmpeg(["-i", str(src), "-filter_complex", graph,
                "-map", "[out]", *encode_args(out), str(out)])


def cut(input_path: str | Path, ranges: list[str], mode: str = "remove",
        output: str | Path | None = None) -> Path:
    """剪音檔。mode='remove' 剪掉指定範圍；mode='keep' 只留指定範圍。"""
    src = Path(input_path).resolve()
    duration = probe_duration(src)
    parsed = [parse_range(r) for r in ranges]

    if mode == "keep":
        segments = [(max(0.0, a), min(b, duration)) for a, b in sorted(parsed)]
        segments = [(a, b) for a, b in segments if b - a > MIN_SEGMENT]
    else:
        segments = _keep_segments(duration, parsed)
    if not segments:
        raise ValueError("剪完就什麼都不剩了，請檢查時間範圍")

    out = (Path(output).resolve() if output
           else src.with_name(src.stem + "_剪輯版" + src.suffix))
    _concat_segments(src, segments, out)

    kept = sum(b - a for a, b in segments)
    print(f"  原長 {fmt_time(duration)} → 剪後 {fmt_time(kept)}"
          f"（保留 {len(segments)} 段）")
    return out


def join(inputs: list[str], output: str | Path) -> Path:
    """把多個音檔接成一個（自動統一取樣率與聲道）。"""
    if len(inputs) < 2:
        raise ValueError("至少要兩個檔案才能接")
    srcs = [Path(p).resolve() for p in inputs]
    for s in srcs:
        if not s.exists():
            raise FileNotFoundError(f"找不到檔案：{s}")
    out = Path(output).resolve()

    args, parts, labels = [], [], []
    for i, s in enumerate(srcs):
        args += ["-i", str(s)]
        parts.append(f"[{i}:a]aresample=48000,"
                     f"aformat=channel_layouts=mono[a{i}]")
        labels.append(f"[a{i}]")
    graph = (";".join(parts) + ";" + "".join(labels)
             + f"concat=n={len(srcs)}:v=0:a=1[out]")
    run_ffmpeg([*args, "-filter_complex", graph,
                "-map", "[out]", *encode_args(out), str(out)])
    print(f"  已接合 {len(srcs)} 個檔案 → 總長 {fmt_time(probe_duration(out))}")
    return out


def trim_silence(input_path: str | Path, output: str | Path | None = None,
                 threshold: float = -45.0, gaps: bool = False) -> Path:
    """去掉頭尾空白；gaps=True 時把中間的長停頓也縮短。"""
    src = Path(input_path).resolve()
    out = (Path(output).resolve() if output
           else src.with_name(src.stem + "_去空白" + src.suffix))

    head_tail = (f"silenceremove=start_periods=1:start_silence=0.15"
                 f":start_threshold={threshold}dB")
    chain = f"{head_tail},areverse,{head_tail},areverse"
    if gaps:
        chain += (f",silenceremove=stop_periods=-1:stop_duration=0.8"
                  f":stop_threshold={threshold}dB:stop_silence=0.3")

    before = probe_duration(src)
    run_ffmpeg(["-i", str(src), "-af", chain, *encode_args(out), str(out)])
    after = probe_duration(out)
    print(f"  {fmt_time(before)} → {fmt_time(after)}"
          f"（省下 {before - after:.1f} 秒）")
    return out
