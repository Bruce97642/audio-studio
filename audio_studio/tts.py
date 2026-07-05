"""文稿配音：給文字，直接合成廣告級配音。

聲音基底用微軟神經網路語音（需要網路），合成後自動套用
本工具的音色鏈與響度標準化，做出「廣告成品」等級的輸出。

風格分類參考台灣廣告配音員 DEMO 的常見類型。註：這些是合法的
AI 合成聲音，不是克隆任何真實配音員——克隆真人嗓音商用會有
人格權的法律風險。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

# 每種風格 = 基底聲音 + 語速/音調 + 後製音色鏈
# rate/pitch 是相對調整；style 對應 pipeline.STYLES
VOICE_PRESETS: dict[str, dict] = {
    # 溫和的 rate/pitch（極端調整會讓 edge-tts 破音失真）；
    # style 用溫和母帶（clean/warm/clear），不再套會失真的重後製鏈
    "沉穩男聲": {
        "voice": "zh-TW-YunJheNeural", "rate": "-8%", "pitch": "-3Hz",
        "style": "warm",
        "desc": "企業簡介／紀錄片——慢而穩，信賴感",
    },
    "活力男聲": {
        "voice": "zh-TW-YunJheNeural", "rate": "+8%", "pitch": "+2Hz",
        "style": "clear",
        "desc": "促銷檔期／活動宣傳——節奏快、有精神",
    },
    "端正女聲": {
        "voice": "zh-TW-HsiaoChenNeural", "rate": "+0%", "pitch": "+0Hz",
        "style": "clean",
        "desc": "新聞資訊／導覽解說——清楚端正",
    },
    "溫暖女聲": {
        "voice": "zh-TW-HsiaoYuNeural", "rate": "-5%", "pitch": "-2Hz",
        "style": "warm",
        "desc": "品牌故事／療癒內容——柔和貼近",
    },
    "甜美女聲": {
        "voice": "zh-TW-HsiaoYuNeural", "rate": "+6%", "pitch": "+4Hz",
        "style": "clear",
        "desc": "電商／青春活潑內容",
    },
    "播報男聲": {
        "voice": "zh-CN-YunyangNeural", "rate": "+0%", "pitch": "+0Hz",
        "style": "clean",
        "desc": "正式新聞播報腔（大陸腔）",
    },
}

DEFAULT_PRESET = "沉穩男聲"


def resolve_preset(name: str) -> str:
    """容錯比對風格名稱（可用前兩個字）。"""
    if name in VOICE_PRESETS:
        return name
    for key in VOICE_PRESETS:
        if key.startswith(name) or name.startswith(key[:2]):
            return key
    raise ValueError(
        f"沒有「{name}」這種配音風格，可用：{'、'.join(VOICE_PRESETS)}")


async def _edge_synth(text: str, preset: dict, out: Path) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(
        text, preset["voice"], rate=preset["rate"], pitch=preset["pitch"])
    await communicate.save(str(out))


def synthesize(text: str, preset_name: str = DEFAULT_PRESET,
               output: str | Path = "配音.mp3",
               loudness: str = "video", enhance: bool = True) -> Path:
    """文稿 → 配音成品。需要網路（聲音由微軟語音服務合成）。"""
    text = text.strip()
    if not text:
        raise ValueError("文稿是空的")
    key = resolve_preset(preset_name)
    preset = VOICE_PRESETS[key]
    out = Path(output).resolve()

    workdir = Path(tempfile.mkdtemp(prefix="audio_tts_"))
    try:
        raw = workdir / "raw.mp3"
        print(f"  [1/2] 合成配音（{key}，{preset['voice']}）...")
        # 微軟的免費端點偶爾會拒絕連發的請求，自動重試三次
        last_error: Exception | None = None
        for attempt in range(3):
            if attempt:
                import time
                time.sleep(2 * attempt)
                print(f"        重試第 {attempt} 次...")
            try:
                asyncio.run(_edge_synth(text, preset, raw))
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(
                f"配音合成失敗（這個功能需要網路連線）：{last_error}"
            ) from last_error
        if not raw.exists() or raw.stat().st_size == 0:
            raise RuntimeError("配音合成失敗：沒有收到聲音資料，"
                               "請檢查網路連線後再試一次")

        if enhance:
            print("  [2/2] 溫和母帶（響度標準化 + 極輕 EQ）...")
            from .pipeline import polish_voice
            polish_voice(raw, out, preset=loudness, style=preset["style"])
        else:
            from .ffmpeg_utils import encode_args, run_ffmpeg
            run_ffmpeg(["-i", str(raw), *encode_args(out), str(out)])
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return out
