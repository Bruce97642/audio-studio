"""核心清理管線：AI 降噪（四段強度）→ 人聲增強（四種音色）→ 響度標準化。"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .ffmpeg_utils import (REPO_ROOT, RNNOISE_MODEL, FFmpegError,
                           encode_args, run_ffmpeg)

# 響度目標（EBU R128）
PRESETS = {
    "video": {"I": -14, "TP": -1.5, "LRA": 11},    # YouTube / FB / IG 影片
    "podcast": {"I": -16, "TP": -1.5, "LRA": 11},  # Podcast / 純聲音
    "loud": {"I": -12, "TP": -1.5, "LRA": 9},      # 廣告 / 宣傳（最大聲）
}

DENOISE_LEVELS = ("off", "light", "standard", "strong", "max")
DENOISE_LABELS = {"off": "關閉", "light": "輕度", "standard": "標準",
                  "strong": "加強", "max": "最強"}

# 四種音色風格的動態處理 + EQ 鏈
STYLES = {
    # 自然：幾乎不修飾，只把音量弄平均
    "natural": [
        "acompressor=threshold=-18dB:ratio=2.5:attack=12:release=250:makeup=2dB",
        "equalizer=f=3000:t=q:w=1.2:g=1.5",
    ],
    # 溫暖（預設）：講話自然又有質感
    "warm": [
        "acompressor=threshold=-20dB:ratio=3:attack=10:release=250:makeup=3dB",
        "equalizer=f=160:t=q:w=1.2:g=1.5",
        "equalizer=f=3200:t=q:w=1.2:g=2",
        "equalizer=f=10000:t=q:w=1.5:g=1",
    ],
    # 廣播主持人：厚實、有磁性、貼耳 —— 兩段壓縮 + 低頻量感 + 諧波激勵
    "radio": [
        "acompressor=threshold=-22dB:ratio=4:attack=5:release=180:makeup=4dB",
        "bass=g=3:f=130",
        "equalizer=f=3000:t=q:w=1.2:g=2.5",
        "aexciter=amount=1.5",
        "acompressor=threshold=-12dB:ratio=2:attack=3:release=120:makeup=1dB",
    ],
    # 清亮：明亮清晰，適合教學與說明
    "bright": [
        "acompressor=threshold=-18dB:ratio=3:attack=8:release=200:makeup=3dB",
        "equalizer=f=250:t=q:w=1:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3",
        "treble=g=2.5:f=9000",
        "aexciter=amount=2",
    ],
}
STYLE_LABELS = {"natural": "自然", "warm": "溫暖", "radio": "廣播主持人",
                "bright": "清亮"}

DEFAULT_SUFFIX = "_乾淨版"


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

    prepared = workdir / "for_demucs.wav"
    run_ffmpeg(["-i", str(src), "-ac", str(model.audio_channels),
                "-ar", str(model.samplerate), "-c:a", "pcm_f32le",
                str(prepared)])
    data, _ = sf.read(prepared, dtype="float32", always_2d=True)
    wav = torch.from_numpy(data.T)

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


def _denoise_spectral(src: Path, dst: Path, strength: float) -> None:
    """noisereduce 頻譜降噪（第二層，對付頑固噪音）。"""
    import noisereduce as nr
    import soundfile as sf
    data, sr = sf.read(src)
    cleaned = nr.reduce_noise(y=data, sr=sr, stationary=False,
                              prop_decrease=strength)
    sf.write(dst, cleaned, sr)


def _denoise(unified: Path, workdir: Path, level: str) -> Path:
    """依強度跑一到三層降噪。"""
    if level == "off":
        return unified
    print(f"  [2/4] AI 降噪中（{DENOISE_LABELS[level]}）...")

    # 第一層：RNNoise 神經網路（輕度時只混一半，保留最多原音細節）
    mix = 0.55 if level == "light" else 1.0
    denoised = workdir / "denoised.wav"
    run_ffmpeg(["-i", str(unified),
                "-af", f"arnndn=m=models/bd.rnnn:mix={mix}",
                str(denoised)], cwd=REPO_ROOT)

    # 第二層：頻譜降噪
    if level in ("strong", "max"):
        strength = 0.85 if level == "strong" else 0.95
        spectral = workdir / "denoised2.wav"
        _denoise_spectral(denoised, spectral, strength)
        denoised = spectral

    # 第三層：FFT 殘噪追蹤（只有最強檔）
    if level == "max":
        fft = workdir / "denoised3.wav"
        run_ffmpeg(["-i", str(denoised),
                    "-af", "afftdn=nr=12:nf=-47:tn=1", str(fft)])
        denoised = fft
    return denoised


def _noise_gate(denoised: Path, workdir: Path) -> Path:
    """自適應噪音門：量出這個檔案自己的噪音地板，動態決定門檻。

    compand 的偵測器跟的是「峰值包絡」不是 RMS，所以這裡用
    20ms 視窗的峰值分布來估計：地板 = 15 百分位、人聲 = 97 百分位。
    分離度不足 18dB 時直接跳過（硬開門會咬到人聲，寧可不開）。
    """
    import numpy as np
    import soundfile as sf
    data, sr = sf.read(denoised)
    if data.ndim > 1:
        data = data.mean(axis=1)
    frame = max(1, int(sr * 0.02))
    usable = len(data) // frame * frame
    if usable == 0:
        return denoised
    peaks = np.abs(data[:usable]).reshape(-1, frame).max(axis=1)
    db = 20 * np.log10(np.maximum(peaks, 1e-6))
    floor, speech = np.percentile(db, 15), np.percentile(db, 97)
    if speech - floor < 18:
        return denoised

    # hi 以上不動；lo 以下往下推 20dB。
    # 門檻取「地板 +10」和「人聲 -42」較高者：深度降噪後地板極低時，
    # 還能咬到人聲下方 40 幾 dB 的零星殘渣，又不會碰到講話的尾音
    hi = max(floor + 10, speech - 42)
    lo = hi - 7
    points = f"-90/-130|{lo:.1f}/{lo - 20:.1f}|{hi:.1f}/{hi:.1f}|0/0"
    gated = workdir / "gated.wav"
    # volume=-90：包絡偵測器從靜音起步。預設是 0dB，
    # 會讓開頭好幾秒門都關不起來（偵測器還在從最大聲往下降）
    run_ffmpeg(["-i", str(denoised),
                "-af", f"compand=attacks=0.02:decays=0.3"
                       f":points={points}:soft-knee=4:volume=-90",
                str(gated)])
    return gated


def _build_enhance_chain(style: str, dehum: bool, declip: bool) -> str:
    """組出人聲增強濾波鏈。"""
    parts: list[str] = []
    if declip:
        parts.append("adeclip")  # 爆音修復（盡力而為）
    # 廣播/清亮風格切多一點低頻，聲音更乾淨
    parts.append("highpass=f=90" if style in ("radio", "bright")
                 else "highpass=f=75")
    if dehum:
        # 台灣市電 60Hz：連同諧波一起挖掉（窄口濾波，不傷人聲）
        parts += [f"bandreject=f={f}:width_type=q:w=8"
                  for f in (60, 120, 180, 240)]
    parts.append("deesser")
    parts += STYLES[style]
    return ",".join(parts)


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
          preset: str = "video", denoise: str = "standard",
          style: str = "warm", dehum: bool = False, declip: bool = False,
          separate: bool = False) -> Path:
    """完整清理一個音檔，回傳輸出路徑。"""
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到檔案：{src}")
    if not RNNOISE_MODEL.exists():
        raise FileNotFoundError(
            f"降噪模型不見了：{RNNOISE_MODEL}\n"
            "請重新下載 bd.rnnn 放回 models 資料夾")
    if denoise not in DENOISE_LEVELS:
        raise ValueError(f"降噪強度要是 {DENOISE_LEVELS} 其中之一")
    if style not in STYLES:
        raise ValueError(f"音色風格要是 {tuple(STYLES)} 其中之一")
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

        denoised = _denoise(unified, workdir, denoise)

        # 最強降噪、或廣播/清亮風格（激勵器會放大殘噪）→ 掛自適應噪音門
        if denoise == "max" or style in ("radio", "bright"):
            denoised = _noise_gate(denoised, workdir)

        print(f"  [3/4] 人聲增強（{STYLE_LABELS[style]}音色）...")
        enhanced = workdir / "enhanced.wav"
        chain = _build_enhance_chain(style, dehum, declip=declip)
        run_ffmpeg(["-i", str(denoised), "-af", chain, str(enhanced)])

        print(f"  [4/4] 響度標準化（{preset}：{target['I']} LUFS）...")
        # 用「靜態增益＋限幅器」而不是 loudnorm 動態模式：
        # 全段等比例放大，安靜段的殘餘噪音才不會被抬回來。
        # 壓峰後響度會略低於目標，所以再量一次、補到位（兩段式母帶增益）
        out.parent.mkdir(parents=True, exist_ok=True)
        limit = 10 ** (target["TP"] / 20)

        def _level_pass(src_p: Path, dst_p: Path, gain_db: float) -> None:
            af = (f"volume={gain_db:.2f}dB,"
                  f"alimiter=limit={limit:.4f}:attack=5:release=80"
                  f":level=false")
            enc = (["-c:a", "pcm_s16le"] if dst_p.suffix == ".wav"
                   else encode_args(dst_p))
            run_ffmpeg(["-i", str(src_p), "-af", af, "-ar", "48000",
                        *enc, str(dst_p)])

        stats = _measure_loudnorm(enhanced, target)
        if not stats:  # 幾乎無聲的檔案，不動它
            run_ffmpeg(["-i", str(enhanced), "-ar", "48000",
                        *encode_args(out), str(out)])
            return out

        gain = target["I"] - float(stats["input_i"])
        headroom = target["TP"] - float(stats["input_tp"])
        gain = min(gain, headroom + 6)  # 最多讓限幅器吃 6dB，保護動態

        leveled = workdir / "leveled.wav"
        _level_pass(enhanced, leveled, gain)
        stats2 = _measure_loudnorm(leveled, target)
        residual = (target["I"] - float(stats2["input_i"])) if stats2 else 0.0
        if residual > 0.7:  # 差超過 0.7dB 才補第二刀，最多再讓限幅器吃 4dB
            headroom2 = target["TP"] - float(stats2["input_tp"])
            _level_pass(leveled, out, min(residual, headroom2 + 4))
        else:
            run_ffmpeg(["-i", str(leveled), *encode_args(out), str(out)])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return out
