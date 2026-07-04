"""核心清理管線：AI 降噪 → 人聲增強 → 響度標準化。"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .ffmpeg_utils import (REPO_ROOT, RNNOISE_MODEL, FFmpegError,
                           encode_args, run_ffmpeg)

# 響度目標（EBU R128）：video 給 YouTube/FB/IG 影片，podcast 給純聲音節目
PRESETS = {
    "video": {"I": -14, "TP": -1.5, "LRA": 11},
    "podcast": {"I": -16, "TP": -1.5, "LRA": 11},
}

DEFAULT_SUFFIX = "_乾淨版"

# 人聲增強鏈：切低頻隆隆聲 → 消齒音 → 壓縮讓音量平均 → EQ 補溫暖度/清晰度/空氣感
ENHANCE_CHAIN = (
    "highpass=f=75,"
    "deesser,"
    "acompressor=threshold=-20dB:ratio=3:attack=10:release=250:makeup=3dB,"
    "equalizer=f=160:t=q:w=1.2:g=1.5,"
    "equalizer=f=3200:t=q:w=1.2:g=2,"
    "equalizer=f=10000:t=q:w=1.5:g=1"
)


def _separate_vocals(src: Path, workdir: Path) -> Path:
    """用 Demucs 把人聲從音樂/複雜背景中抽出來。

    音檔讀寫都自己用 ffmpeg + soundfile 做，避開 torchaudio
    在 Windows 上缺 torchcodec 而無法存檔的問題。
    """
    print("  [1/4] Demucs AI 人聲分離中（第一次會下載模型，請稍候）...")
    try:
        import torch
        from demucs.apply import apply_model
        from demucs.pretrained import get_model
    except ImportError:
        raise RuntimeError(
            "要用 --separate 需要先安裝 Demucs：pip install demucs") from None
    import soundfile as sf

    model = get_model("htdemucs")
    model.cpu().eval()

    # 轉成模型的工作格式（44.1kHz 立體聲）
    prepared = workdir / "for_demucs.wav"
    run_ffmpeg(["-i", str(src), "-ac", str(model.audio_channels),
                "-ar", str(model.samplerate), "-c:a", "pcm_f32le",
                str(prepared)])
    data, _ = sf.read(prepared, dtype="float32", always_2d=True)
    wav = torch.from_numpy(data.T)

    # 依 demucs 官方流程做正規化 → 分離 → 還原音量
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)
    with torch.no_grad():
        sources = apply_model(model, wav[None], device="cpu",
                              shifts=1, split=True, overlap=0.25)[0]
    sources = sources * ref.std() + ref.mean()

    vocals = workdir / "vocals.wav"
    sf.write(vocals, sources[model.sources.index("vocals")].numpy().T,
             model.samplerate)
    return vocals


def _denoise_extra(src: Path, dst: Path) -> None:
    """noisereduce 頻譜降噪（第二層，對付頑固的穩定噪音）。"""
    import noisereduce as nr
    import soundfile as sf
    data, sr = sf.read(src)
    cleaned = nr.reduce_noise(y=data, sr=sr, stationary=False,
                              prop_decrease=0.85)
    sf.write(dst, cleaned, sr)


def _measure_loudnorm(src: Path, target: dict) -> dict | None:
    """loudnorm 第一遍：量測目前響度，回傳量測值（失敗回 None）。"""
    spec = f"loudnorm=I={target['I']}:TP={target['TP']}:LRA={target['LRA']}"
    stderr = run_ffmpeg(["-i", str(src), "-af", f"{spec}:print_format=json",
                         "-f", "null", "-"])
    start = stderr.rfind("{")
    if start == -1:
        return None
    try:
        stats = json.loads(stderr[start:stderr.rfind("}") + 1])
    except json.JSONDecodeError:
        return None
    if any("-inf" in str(v).lower() for v in stats.values()):
        return None  # 幾乎無聲的檔案，改用單遍模式
    return stats


def clean(input_path: str | Path, output: str | Path | None = None,
          preset: str = "video", extra: bool = False,
          separate: bool = False) -> Path:
    """完整清理一個音檔，回傳輸出路徑。"""
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到檔案：{src}")
    if not RNNOISE_MODEL.exists():
        raise FileNotFoundError(
            f"降噪模型不見了：{RNNOISE_MODEL}\n"
            "請重新下載 bd.rnnn 放回 models 資料夾")
    target = PRESETS[preset]
    out = (Path(output).resolve() if output
           else src.with_name(src.stem + DEFAULT_SUFFIX + ".mp3"))

    workdir = Path(tempfile.mkdtemp(prefix="audio_studio_"))
    try:
        stage = src
        if separate:
            stage = _separate_vocals(stage, workdir)

        # 統一轉成 48kHz 單聲道（RNNoise 的工作格式）
        unified = workdir / "unified.wav"
        run_ffmpeg(["-i", str(stage), "-ac", "1", "-ar", "48000",
                    "-c:a", "pcm_s16le", str(unified)])

        print("  [2/4] RNNoise AI 降噪中...")
        denoised = workdir / "denoised.wav"
        run_ffmpeg(["-i", str(unified),
                    "-af", "arnndn=m=models/bd.rnnn",
                    str(denoised)], cwd=REPO_ROOT)

        if extra:
            print("        加強頻譜降噪中...")
            extra_out = workdir / "denoised2.wav"
            _denoise_extra(denoised, extra_out)
            denoised = extra_out

        print("  [3/4] 人聲增強（EQ + 壓縮 + 消齒音）...")
        enhanced = workdir / "enhanced.wav"
        run_ffmpeg(["-i", str(denoised), "-af", ENHANCE_CHAIN, str(enhanced)])

        print(f"  [4/4] 響度標準化（{preset}：{target['I']} LUFS）...")
        # 用「靜態增益＋限幅器」而不是 loudnorm 動態模式：
        # 全段等比例放大，安靜段的殘餘噪音才不會被抬回來
        stats = _measure_loudnorm(enhanced, target)
        if stats:
            gain = target["I"] - float(stats["input_i"])
            headroom = target["TP"] - float(stats["input_tp"])
            gain = min(gain, headroom + 6)  # 最多讓限幅器吃 6dB，保護動態
            limit = 10 ** (target["TP"] / 20)
            final_af = (f"volume={gain:.2f}dB,"
                        f"alimiter=limit={limit:.4f}:attack=5:release=80"
                        f":level=false")
        else:
            final_af = "anull"  # 幾乎無聲的檔案，不動它
        out.parent.mkdir(parents=True, exist_ok=True)
        run_ffmpeg(["-i", str(enhanced), "-af", final_af, "-ar", "48000",
                    *encode_args(out), str(out)])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return out
