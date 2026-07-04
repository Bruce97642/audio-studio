"""語音轉逐字稿（faster-whisper）＋ 用文字找出現時間點。"""

from __future__ import annotations

import json
import re
from pathlib import Path

_model_cache: dict[str, object] = {}

TRADITIONAL_PROMPT = "以下是繁體中文的逐字稿，請使用繁體中文。"


def _load_model(size: str):
    if size not in _model_cache:
        from faster_whisper import WhisperModel
        print(f"  載入 Whisper 模型（{size}，第一次會自動下載）...")
        _model_cache[size] = WhisperModel(size, device="cpu",
                                          compute_type="int8")
    return _model_cache[size]


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _run_whisper(path: Path, model_size: str, language: str | None,
                 words: bool = False):
    model = _load_model(model_size)
    prompt = TRADITIONAL_PROMPT if language in (None, "zh") else None
    segments, info = model.transcribe(
        str(path), language=language, word_timestamps=words,
        initial_prompt=prompt, vad_filter=True)
    return list(segments), info


def transcribe(input_path: str | Path, model_size: str = "small",
               language: str | None = None, fmt: str = "txt",
               output: str | Path | None = None) -> Path:
    """轉逐字稿，輸出 txt / srt / json 檔。"""
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到檔案：{src}")
    segments, info = _run_whisper(src, model_size, language,
                                  words=(fmt == "json"))
    out = (Path(output).resolve() if output
           else src.with_suffix("." + fmt))

    if fmt == "srt":
        lines = []
        for i, seg in enumerate(segments, 1):
            lines += [str(i), f"{_srt_time(seg.start)} --> {_srt_time(seg.end)}",
                      seg.text.strip(), ""]
        out.write_text("\n".join(lines), encoding="utf-8")
    elif fmt == "json":
        data = {"language": info.language, "segments": [
            {"start": round(seg.start, 2), "end": round(seg.end, 2),
             "text": seg.text.strip(),
             "words": [{"start": round(w.start, 2), "end": round(w.end, 2),
                        "word": w.word} for w in (seg.words or [])]}
            for seg in segments]}
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    else:
        text = "\n".join(seg.text.strip() for seg in segments)
        out.write_text(text, encoding="utf-8")

    print(f"  辨識語言：{info.language}，共 {len(segments)} 段")
    return out


def _normalize(text: str) -> str:
    """只留中英數字，方便模糊比對。"""
    return re.sub(r"[^\w一-鿿]", "", text).lower()


def find(input_path: str | Path, query: str, model_size: str = "small",
         language: str | None = None) -> list[tuple[float, float, str]]:
    """找出某句話在錄音中的時間範圍，回傳 [(開始, 結束, 前後文), ...]。"""
    src = Path(input_path).resolve()
    target = _normalize(query)
    if not target:
        raise ValueError("搜尋文字不能是空的")
    segments, _ = _run_whisper(src, model_size, language, words=True)

    # 把所有詞攤平成字元流，每個字元記住它屬於哪個詞
    words = [w for seg in segments for w in (seg.words or [])]
    chars, owner = [], []
    for idx, w in enumerate(words):
        for ch in _normalize(w.word):
            chars.append(ch)
            owner.append(idx)
    stream = "".join(chars)

    matches = []
    pos = stream.find(target)
    while pos != -1:
        first, last = owner[pos], owner[pos + len(target) - 1]
        context = "".join(w.word for w in
                          words[max(0, first - 3):last + 4]).strip()
        matches.append((words[first].start, words[last].end, context))
        pos = stream.find(target, pos + 1)
    return matches
