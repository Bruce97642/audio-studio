"""AI 環境診斷：分析錄音的背景環境，自動推薦最適合的降噪組合。

量什麼：
- 訊噪比（人聲 RMS vs 噪音地板 RMS，用 50ms 視窗的百分位估計）
- 60Hz 電流哼聲（只在「最安靜的 20% 片段」上做頻譜，避免把
  男聲基頻的 120Hz 諧波誤判成哼聲）
- 爆音（貼近滿刻度的取樣比例）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .ffmpeg_utils import run_ffmpeg

# 訊噪比 → 降噪強度
SNR_LEVELS = [(12, "max"), (20, "strong"), (32, "standard")]
HUM_EXCESS_DB = 8.0     # 哼聲頻帶比鄰近頻譜高這麼多才算有哼聲
CLIP_RATIO = 0.0003     # 貼近滿刻度的取樣超過此比例就建議爆音修復


def diagnose(input_path: str | Path) -> dict:
    """分析環境，回傳量測值＋建議設定＋白話說明。"""
    import numpy as np
    import soundfile as sf

    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到檔案：{src}")

    with tempfile.TemporaryDirectory(prefix="audio_diag_") as td:
        wav = Path(td) / "diag.wav"
        run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", "48000",
                    "-c:a", "pcm_f32le", str(wav)])
        data, sr = sf.read(wav, dtype="float32")

    notes: list[str] = []
    result = {"snr": None, "noise_floor": None, "speech": None,
              "hum": False, "hum_excess": 0.0,
              "clip": False, "clip_ratio": 0.0,
              "denoise": "standard", "dehum": False, "declip": False,
              "notes": notes}

    frame = int(sr * 0.05)
    if len(data) < frame * 8:  # 不到 0.4 秒，量不出東西
        notes.append("錄音太短，無法診斷環境，先用標準設定。")
        return result

    # --- 訊噪比 ---
    usable = len(data) // frame * frame
    frames = data[:usable].reshape(-1, frame)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    rms_db = 20 * np.log10(np.maximum(rms, 1e-7))
    noise_floor = float(np.percentile(rms_db, 10))
    speech = float(np.percentile(rms_db, 90))
    snr = speech - noise_floor
    result.update(snr=round(snr, 1), noise_floor=round(noise_floor, 1),
                  speech=round(speech, 1))

    result["denoise"] = "light"
    for threshold, level in SNR_LEVELS:
        if snr < threshold:
            result["denoise"] = level
            break

    labels = {"max": "很吵 → 建議「最強」降噪（三層 AI＋噪音門）",
              "strong": "偏吵 → 建議「加強」降噪",
              "standard": "普通 → 建議「標準」降噪",
              "light": "很安靜 → 「輕度」降噪就夠，保留最多原音"}
    notes.append(f"環境噪音：訊噪比 {snr:.0f} dB，{labels[result['denoise']]}")

    # --- 60Hz 哼聲 ---
    # 取「最長的一段連續安靜片段」做頻譜：把不連續片段串起來會讓
    # 相位斷裂、尖峰被抹平，連續段才量得準
    try:
        from scipy.signal import welch
        # 噪音地板 +3dB 以內都算安靜段（百分位切法會把連續段切碎）
        quiet_mask = rms_db <= noise_floor + 3.0
        best_start, best_len, run_start = 0, 0, None
        for i, q in enumerate(list(quiet_mask) + [False]):
            if q and run_start is None:
                run_start = i
            elif not q and run_start is not None:
                if i - run_start > best_len:
                    best_start, best_len = run_start, i - run_start
                run_start = None
        quiet = frames[best_start:best_start + best_len].ravel()
        if len(quiet) >= sr:  # 至少一秒的連續安靜段才可靠
            freqs, psd = welch(quiet, fs=sr,
                               nperseg=min(8192, len(quiet)))
            near_hum = np.zeros_like(freqs, dtype=bool)
            for hum_f in (60, 120, 180, 240):
                near_hum |= (freqs >= hum_f - 8) & (freqs <= hum_f + 8)
            # 每個哼聲頻率跟「自己附近的頻譜」比，
            # 才不會被低頻噪音本來就比較大聲的斜坡偏差干擾
            excess = 0.0
            for hum_f in (60, 120, 180):
                sel = (freqs >= hum_f - 6) & (freqs <= hum_f + 6)
                local = ((freqs >= hum_f - 35) & (freqs <= hum_f + 35)
                         & ~near_hum)
                if not (sel.any() and local.any()):
                    continue
                ref = np.median(psd[local])
                if ref > 0:
                    excess = max(excess,
                                 10 * np.log10(psd[sel].max() / ref))
            result["hum_excess"] = round(float(excess), 1)
            if excess >= HUM_EXCESS_DB:
                result["hum"] = True
                result["dehum"] = True
                notes.append(f"偵測到 60Hz 電流／冷氣哼聲（超出背景 "
                             f"{excess:.0f} dB）→ 已自動勾選消除")
    except ImportError:
        pass  # 沒裝 scipy 就跳過哼聲檢測

    # --- 爆音 ---
    clip_ratio = float(np.mean(np.abs(data) >= 0.98))
    result["clip_ratio"] = round(clip_ratio, 5)
    if clip_ratio >= CLIP_RATIO:
        result["clip"] = True
        result["declip"] = True
        notes.append(f"偵測到爆音（{clip_ratio * 100:.2f}% 的取樣破表）"
                     "→ 已自動勾選爆音修復，但錄音時請離麥克風遠一點")

    if len(notes) == 1:
        notes.append("沒有偵測到電流聲或爆音，狀態良好。")
    return result
