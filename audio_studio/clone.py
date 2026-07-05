"""語音克隆配音：用 F5-TTS 零樣本克隆一個「磁性播音」聲線。

聲音來源說明（重要）：
- 參考音是用「有授權的合成語音」當種子、再調成低沉磁性做出來的，
  不是任何真實配音員的聲音——克隆真人嗓音有人格權問題。
- F5-TTS 學參考音的音色，配上自然的語調，比純 TTS 自然很多。
- 合成後照樣套本工具的音色鏈與響度標準化。

F5-TTS 跑在獨立的 .clone311（Python 3.11）環境，因為它相依的
套件版本跟主環境不同。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .ffmpeg_utils import REPO_ROOT, encode_args, run_ffmpeg

CLONE_PY = REPO_ROOT / ".clone311" / "Scripts" / "python.exe"
VOICES_DIR = REPO_ROOT / "voices"

# 可克隆聲線。參考音是「有授權的自然真人語音」降調到目標音域做的，
# 自然的語調靠它、低沉磁性靠 pitch（降調倍率）+ 後製音色鏈。
# pitch < 1 = 降調變低沉；1 = 不變。
CLONE_VOICES: dict[str, dict] = {
    "自然旁白": {
        "ref_audio": "ref_natural_male.wav",
        "ref_text": "对，这就是我，万人敬仰的太乙真人。",
        "pitch": 1.0, "style": "warm",
        "desc": "自然男聲旁白（克隆聲線，離線）",
    },
}

DEFAULT_CLONE = "自然旁白"


def available() -> bool:
    """檢查克隆環境是否已安裝。"""
    return CLONE_PY.exists() and any(VOICES_DIR.glob("ref_*.wav"))


def _run_f5(ref_audio: Path, ref_text: str, gen_text: str,
            out: Path) -> None:
    """呼叫 F5-TTS 產生克隆語音。"""
    cmd = [str(CLONE_PY), "-m", "f5_tts.infer.infer_cli",
           "--model", "F5TTS_v1_Base",
           "--ref_audio", str(ref_audio),
           "--ref_text", ref_text,
           "--gen_text", gen_text,
           "--output_dir", str(out.parent),
           "--output_file", out.name]
    # F5-TTS 會把（可能是簡體的）參考逐字稿印到主控台，
    # Windows 的 cp950 (Big5) 編不了簡體字會崩潰 → 強制 UTF-8
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"F5-TTS 克隆失敗：\n{proc.stderr[-1500:]}")


def synthesize_clone(text: str, voice: str = DEFAULT_CLONE,
                     output: str | Path = "克隆配音.mp3",
                     loudness: str = "video", enhance: bool = True) -> Path:
    """用克隆聲線把文稿變成配音。"""
    text = text.strip()
    if not text:
        raise ValueError("文稿是空的")
    if voice not in CLONE_VOICES:
        raise ValueError(f"沒有「{voice}」這個克隆聲線")
    if not available():
        raise RuntimeError(
            "克隆功能還沒安裝，請先執行 setup_clone.ps1")
    preset = CLONE_VOICES[voice]
    ref_audio = VOICES_DIR / preset["ref_audio"]
    out = Path(output).resolve()

    workdir = Path(tempfile.mkdtemp(prefix="audio_clone_"))
    try:
        raw = workdir / "clone.wav"
        print(f"  [1/2] 克隆配音中（{voice}，F5-TTS，CPU 約需 1～3 分）...")
        _run_f5(ref_audio, preset["ref_text"], text, raw)

        # 只在 pitch != 1 時才降調（降調用 rubberband 會有輕微失真，
        # 預設 1.0 = 不動，保留 F5 最乾淨的自然輸出）
        stage = raw
        if abs(preset.get("pitch", 1.0) - 1.0) > 0.01:
            print(f"  [調整音域] pitch {preset['pitch']}...")
            stage = workdir / "pitched.wav"
            run_ffmpeg(["-i", str(raw),
                        "-af", f"rubberband=pitch={preset['pitch']}",
                        str(stage)])

        if enhance:
            print("  [2/2] 溫和母帶（響度標準化 + 極輕 EQ）...")
            from .pipeline import polish_voice
            polish_voice(stage, out, preset=loudness, style=preset["style"])
        else:
            run_ffmpeg(["-i", str(stage), *encode_args(out), str(out)])
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    return out
