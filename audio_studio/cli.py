"""audio-studio 指令列介面。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .ffmpeg_utils import collect_audio_files, fmt_time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audio-studio",
        description="把吵雜錄音變成錄音室等級人聲的開源工具箱")
    parser.add_argument("--version", action="version",
                        version=f"audio-studio {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("clean", help="一鍵清理：降噪＋人聲增強＋響度標準化")
    p.add_argument("inputs", nargs="+", help="音檔或整個資料夾")
    p.add_argument("-o", "--output", help="輸出檔名（僅限單一輸入）")
    p.add_argument("--preset", choices=["video", "podcast", "loud"],
                   default="video",
                   help="響度：video=-14（預設）、podcast=-16、loud=-12 LUFS")
    p.add_argument("--denoise",
                   choices=["off", "light", "standard", "strong", "max"],
                   default="standard",
                   help="降噪強度（預設 standard；max 會連講話空檔都壓黑）")
    p.add_argument("--style",
                   choices=["natural", "warm", "radio", "bright"],
                   default="warm",
                   help="音色：natural 自然、warm 溫暖（預設）、"
                        "radio 廣播主持人、bright 清亮")
    p.add_argument("--dehum", action="store_true",
                   help="消除 60Hz 電流/冷氣嗡嗡聲（含諧波）")
    p.add_argument("--declip", action="store_true",
                   help="爆音修復（錄音破音時試試）")
    p.add_argument("--extra", action="store_true",
                   help="（舊參數）等同 --denoise strong")
    p.add_argument("--separate", action="store_true",
                   help="先用 Demucs 把人聲從音樂/複雜背景抽出來（較慢）")

    p = sub.add_parser("cut", help="剪掉（或只保留）指定時間範圍")
    p.add_argument("input", help="音檔")
    p.add_argument("-r", "--remove", action="append", default=[],
                   metavar="開始-結束", help="要剪掉的範圍，例如 2:10-2:30，可重複")
    p.add_argument("-k", "--keep", action="append", default=[],
                   metavar="開始-結束", help="只保留的範圍，可重複")
    p.add_argument("-o", "--output", help="輸出檔名")

    p = sub.add_parser("join", help="把多個音檔接成一個")
    p.add_argument("inputs", nargs="+", help="至少兩個音檔，依順序接合")
    p.add_argument("-o", "--output", required=True, help="輸出檔名")

    p = sub.add_parser("trim", help="去掉頭尾空白（可加 --gaps 縮短中間停頓）")
    p.add_argument("input", help="音檔")
    p.add_argument("--gaps", action="store_true", help="連中間的長停頓一起縮短")
    p.add_argument("--db", type=float, default=-45.0,
                   help="安靜門檻 dB（預設 -45）")
    p.add_argument("-o", "--output", help="輸出檔名")

    p = sub.add_parser("transcribe", help="語音轉逐字稿（txt/srt/json）")
    p.add_argument("input", help="音檔")
    p.add_argument("--model", default="small",
                   help="Whisper 模型大小：tiny/base/small/medium（預設 small）")
    p.add_argument("--format", choices=["txt", "srt", "json"], default="txt")
    p.add_argument("--lang", default=None, help="語言代碼，例如 zh（預設自動偵測）")
    p.add_argument("-o", "--output", help="輸出檔名")

    p = sub.add_parser("find", help="找出某句話出現的時間點（配合 cut 剪掉它）")
    p.add_argument("input", help="音檔")
    p.add_argument("text", help="要找的字句")
    p.add_argument("--model", default="small")
    p.add_argument("--lang", default=None)

    p = sub.add_parser("analyze", help="音檔健檢：響度/峰值/噪音底層")
    p.add_argument("input", help="音檔")

    p = sub.add_parser("diagnose",
                       help="AI 環境診斷：分析噪音/哼聲/爆音，推薦降噪設定")
    p.add_argument("input", help="音檔")

    p = sub.add_parser("speak", help="文稿配音：文字直接合成廣告級配音")
    p.add_argument("text", help="文稿內容，或 .txt 檔路徑")
    p.add_argument("--voice", default="磁性男聲",
                   help="配音風格（用 voices 指令看全部選項）")
    p.add_argument("-o", "--output", default="配音.mp3", help="輸出檔名")
    p.add_argument("--preset", choices=["video", "podcast", "loud"],
                   default="video", help="響度目標")
    p.add_argument("--raw", action="store_true",
                   help="只要原始合成聲音，不做廣播級後製")

    sub.add_parser("voices", help="列出所有配音風格")

    return parser


def _cmd_clean(args) -> None:
    from .pipeline import clean
    files = collect_audio_files(args.inputs)
    if args.output and len(files) > 1:
        raise SystemExit("多檔批次模式不能指定 -o，輸出會放在各檔案旁邊")
    denoise = args.denoise
    if args.extra and denoise == "standard":
        denoise = "strong"  # 舊參數相容
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] 清理 {f.name}")
        out = clean(f, output=args.output, preset=args.preset,
                    denoise=denoise, style=args.style, dehum=args.dehum,
                    declip=args.declip, separate=args.separate)
        print(f"  完成 → {out}")


def _cmd_cut(args) -> None:
    from .edit import cut
    if bool(args.remove) == bool(args.keep):
        raise SystemExit("請用 -r 指定要剪掉的範圍，或用 -k 指定要保留的範圍（擇一）")
    mode = "remove" if args.remove else "keep"
    out = cut(args.input, args.remove or args.keep, mode=mode,
              output=args.output)
    print(f"  完成 → {out}")


def _cmd_join(args) -> None:
    from .edit import join
    out = join(args.inputs, args.output)
    print(f"  完成 → {out}")


def _cmd_trim(args) -> None:
    from .edit import trim_silence
    out = trim_silence(args.input, output=args.output,
                       threshold=args.db, gaps=args.gaps)
    print(f"  完成 → {out}")


def _cmd_transcribe(args) -> None:
    from .transcribe import transcribe
    out = transcribe(args.input, model_size=args.model, language=args.lang,
                     fmt=args.format, output=args.output)
    print(f"  完成 → {out}")


def _cmd_find(args) -> None:
    from .transcribe import find
    matches = find(args.input, args.text, model_size=args.model,
                   language=args.lang)
    if not matches:
        print(f"  沒找到「{args.text}」")
        return
    print(f"  找到 {len(matches)} 處：")
    for start, end, context in matches:
        print(f"    {fmt_time(start)} - {fmt_time(end)}  …{context}…")
    print("  要剪掉的話：audio-studio cut 檔案 -r 開始-結束")


def _cmd_analyze(args) -> None:
    from .analyze import analyze
    analyze(args.input)


def _cmd_diagnose(args) -> None:
    from .environment import diagnose
    result = diagnose(args.input)
    for note in result["notes"]:
        print(f"  {note}")
    cmd = f"audio-studio clean \"{args.input}\" --denoise {result['denoise']}"
    if result["dehum"]:
        cmd += " --dehum"
    if result["declip"]:
        cmd += " --declip"
    print(f"  建議指令：{cmd}")


def _cmd_speak(args) -> None:
    from .clone import CLONE_VOICES, synthesize_clone
    from .tts import synthesize
    text = args.text
    maybe_file = Path(text)
    if maybe_file.suffix.lower() == ".txt" and maybe_file.is_file():
        text = maybe_file.read_text(encoding="utf-8")
    if args.voice in CLONE_VOICES:  # 克隆聲線走 F5-TTS
        out = synthesize_clone(text, voice=args.voice, output=args.output,
                               loudness=args.preset, enhance=not args.raw)
    else:
        out = synthesize(text, preset_name=args.voice, output=args.output,
                         loudness=args.preset, enhance=not args.raw)
    print(f"  完成 → {out}")


def _cmd_voices(args) -> None:
    from .clone import CLONE_VOICES, available
    from .tts import VOICE_PRESETS
    all_voices = {**VOICE_PRESETS, **CLONE_VOICES}
    width = max(len(k) for k in all_voices)
    for name, preset in VOICE_PRESETS.items():
        print(f"  {name:<{width}}  {preset['desc']}")
    tag = "" if available() else "（需先執行 setup_clone.ps1）"
    for name, preset in CLONE_VOICES.items():
        print(f"  {name:<{width}}  {preset['desc']}{tag}")


COMMANDS = {
    "clean": _cmd_clean, "cut": _cmd_cut, "join": _cmd_join,
    "trim": _cmd_trim, "transcribe": _cmd_transcribe,
    "find": _cmd_find, "analyze": _cmd_analyze, "diagnose": _cmd_diagnose,
    "speak": _cmd_speak, "voices": _cmd_voices,
}


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"錯誤：{exc}")
