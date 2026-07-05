"""ElevenLabs 頂級 AI 配音——業界最自然的中文語音。

需要一組 ElevenLabs API key（免費方案每月 1 萬字、支援中文、
個人自用免費）。金鑰放在下列任一處（都不進版控）：
  1. 環境變數 ELEVENLABS_API_KEY
  2. 專案根目錄的 .elevenlabs_key 檔
  3. Streamlit secrets（雲端部署用）

配音出來已經很乾淨，只套「溫和母帶」（響度標準化 + 極輕 EQ），
不做任何會產生失真的重後製。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .ffmpeg_utils import REPO_ROOT, encode_args, run_ffmpeg

KEY_FILE = REPO_ROOT / ".elevenlabs_key"
MODEL = "eleven_multilingual_v2"  # 支援中文、最穩定

# 精選幾個適合中文旁白的聲音（ElevenLabs 內建、可商用的公開聲庫）。
# 名稱是這裡自訂的中文標籤，voice_id 是 ElevenLabs 的固定 ID。
ELEVEN_VOICES: dict[str, dict] = {
    "旁白男聲": {
        "voice_id": "onwK4e9ZLuTAKqWW03F9",  # Daniel — 沉穩權威
        "style": "warm",
        "desc": "沉穩權威的旁白腔（像參考影片那種正經配音）",
    },
    "磁性男聲": {
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",  # George — 溫暖低沉
        "style": "warm",
        "desc": "溫暖低沉、有磁性",
    },
    "清晰男聲": {
        "voice_id": "TX3LPaxmHKxFdv7VOQHJ",  # Liam — 清楚年輕
        "style": "clear",
        "desc": "清楚明亮、年輕有精神",
    },
    "知性女聲": {
        "voice_id": "XrExE9yKIg1WjnnlVkGX",  # Matilda — 溫柔專業
        "style": "warm",
        "desc": "溫柔專業的女聲旁白",
    },
    "活潑女聲": {
        "voice_id": "cgSgspJ2msm6clMCkdW9",  # Jessica — 活潑親切
        "style": "clear",
        "desc": "活潑親切、適合電商與活動",
    },
}

DEFAULT_VOICE = "旁白男聲"


def get_api_key() -> str | None:
    """依序從環境變數、金鑰檔、Streamlit secrets 找 API key。"""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key.strip()
    if KEY_FILE.exists():
        text = KEY_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    try:
        import streamlit as st
        return (st.secrets.get("ELEVENLABS_API_KEY") or "").strip() or None
    except Exception:
        return None


def available() -> bool:
    return get_api_key() is not None


def save_api_key(key: str) -> None:
    KEY_FILE.write_text(key.strip(), encoding="utf-8")


def _tts_bytes(text: str, voice_id: str, api_key: str) -> bytes:
    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=api_key)
    audio = client.text_to_speech.convert(
        voice_id=voice_id, model_id=MODEL, text=text,
        output_format="mp3_44100_128")
    return b"".join(audio)


def synthesize_eleven(text: str, voice: str = DEFAULT_VOICE,
                      output: str | Path = "配音.mp3",
                      loudness: str = "video", polish: bool = True) -> Path:
    """用 ElevenLabs 把文稿變成配音。"""
    text = text.strip()
    if not text:
        raise ValueError("文稿是空的")
    if voice not in ELEVEN_VOICES:
        raise ValueError(f"沒有「{voice}」這個聲音")
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "還沒設定 ElevenLabs API key。請到 elevenlabs.io 免費註冊，"
            "在 Profile 複製 API key，貼進精靈的設定欄，或存成專案根目錄"
            "的 .elevenlabs_key 檔。")
    preset = ELEVEN_VOICES[voice]
    out = Path(output).resolve()

    workdir = Path(tempfile.mkdtemp(prefix="audio_eleven_"))
    try:
        raw = workdir / "raw.mp3"
        print(f"  [1/2] ElevenLabs 配音中（{voice}）...")
        try:
            raw.write_bytes(_tts_bytes(text, preset["voice_id"], api_key))
        except Exception as exc:
            raise RuntimeError(
                f"ElevenLabs 配音失敗：{exc}\n"
                "（可能是 key 錯了、額度用完、或沒網路）") from exc
        if raw.stat().st_size == 0:
            raise RuntimeError("ElevenLabs 沒有回傳聲音，請檢查 key 與額度")

        if polish:
            print("  [2/2] 溫和母帶（響度標準化 + 極輕 EQ）...")
            from .pipeline import polish_voice
            polish_voice(raw, out, preset=loudness, style=preset["style"])
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            run_ffmpeg(["-i", str(raw), *encode_args(out), str(out)])
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return out
