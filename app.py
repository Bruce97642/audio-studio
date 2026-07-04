"""錄音工作室 — 五步驟網頁精靈（Streamlit）。

① 上傳檔案 → ② 選項設定 → ③ 溝通剪輯 → ④ 轉檔設定 → ⑤ 完成出檔
啟動：python -m streamlit run app.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from audio_studio.commands import HELP_TEXT, parse_command
from audio_studio.edit import cut, trim_silence
from audio_studio.ffmpeg_utils import (AUDIO_EXTS, encode_args, fmt_time,
                                       probe_duration, run_ffmpeg)
from audio_studio.pipeline import clean

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"
OUTPUT_DIR = ROOT / "成品"

st.set_page_config(page_title="錄音工作室", page_icon="🎙️", layout="centered")

STEP_LABELS = ["① 上傳檔案", "② 選項設定", "③ 溝通剪輯",
               "④ 轉檔設定", "⑤ 完成出檔"]


def init_state() -> None:
    defaults = {"step": 1, "workdir": None, "src": None, "orig_name": None,
                "history": [], "msg": "", "transcript": None, "outfile": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    if st.session_state.workdir is None:
        WORKSPACE.mkdir(exist_ok=True)
        st.session_state.workdir = tempfile.mkdtemp(prefix="session_",
                                                    dir=WORKSPACE)


def steps_bar() -> None:
    cur = st.session_state.step
    parts = []
    for i, label in enumerate(STEP_LABELS, 1):
        parts.append(f"**:blue[{label}]**" if i == cur else f":gray[{label}]")
    st.markdown("　".join(parts))
    st.divider()


def goto(step: int) -> None:
    st.session_state.step = step
    st.rerun()


# ---------- 步驟 1：上傳 ----------

def step1() -> None:
    st.subheader("把錄音檔交給我")

    # 測試掛鉤：?demo=本機路徑 可跳過瀏覽器上傳（自動化驗證用）
    demo = st.query_params.get("demo")
    if demo and st.session_state.src is None and Path(demo).exists():
        p = Path(demo)
        dst = Path(st.session_state.workdir) / f"原始{p.suffix}"
        dst.write_bytes(p.read_bytes())
        st.session_state.src = str(dst)
        st.session_state.orig_name = p.name

    if st.session_state.src is None:
        up = st.file_uploader(
            "手機錄音、會議錄音、影片檔都可以（mp3 / m4a / wav / mp4…）",
            type=[e.lstrip(".") for e in sorted(AUDIO_EXTS)])
        if up is not None:
            dst = Path(st.session_state.workdir) / f"原始{Path(up.name).suffix}"
            dst.write_bytes(up.getbuffer())
            st.session_state.src = str(dst)
            st.session_state.orig_name = up.name
            st.rerun()
    else:
        st.audio(st.session_state.src)
        st.caption(f"檔案：{st.session_state.orig_name}　"
                   f"長度：{fmt_time(probe_duration(st.session_state.src))}")
        col1, col2 = st.columns(2)
        if col1.button("下一步 →", type="primary", use_container_width=True):
            goto(2)
        if col2.button("換一個檔案", use_container_width=True):
            st.session_state.src = None
            st.rerun()


# ---------- 步驟 2：選項 ----------

LEVEL_MAP = {"關閉": "off", "輕度": "light", "標準": "standard",
             "加強": "strong", "最強": "max"}
STYLE_MAP = {"溫暖": "warm", "廣播主持人": "radio",
             "清亮": "bright", "自然": "natural"}
PRESET_MAP = {"影片": "video", "Podcast": "podcast", "廣告": "loud"}


def step2() -> None:
    st.subheader("要怎麼清理？")

    use = st.radio("響度用途",
                   ["影片（YouTube / FB / IG）", "Podcast / 純聲音",
                    "廣告宣傳（最大聲）"])
    level = st.select_slider(
        "降噪強度",
        options=["關閉", "輕度", "標準", "加強", "最強"], value="加強")
    st.caption("輕度＝環境本來就安靜｜標準＝一般吵｜加強＝很吵（商用建議）｜"
               "最強＝三層 AI 降噪＋噪音門，講話空檔壓到全黑")
    style = st.selectbox("音色風格", [
        "廣播主持人 — 厚實、有磁性，最有專業播音感（商用推薦）",
        "溫暖 — 講話自然又有質感",
        "清亮 — 明亮清晰，適合教學說明",
        "自然 — 幾乎不修飾，只把音量弄平均",
    ])
    dehum = st.checkbox("消除電流／冷氣／電風扇的嗡嗡聲（60Hz 哼聲）")
    separate = st.checkbox("背景有音樂 — AI 人聲分離（會比較久）")
    with st.expander("進階選項"):
        declip = st.checkbox("爆音修復 — 錄音破音/太爆時試試")

    col1, col2 = st.columns(2)
    if col1.button("開始清理 ✨", type="primary", use_container_width=True):
        preset = next(v for k, v in PRESET_MAP.items() if use.startswith(k))
        style_key = STYLE_MAP[style.split(" — ")[0]]
        with st.spinner("AI 清理中，請稍候…（背景有音樂時可能要一兩分鐘）"):
            out = clean(st.session_state.src,
                        output=Path(st.session_state.workdir) / "clean.mp3",
                        preset=preset, denoise=LEVEL_MAP[level],
                        style=style_key, dehum=dehum, declip=declip,
                        separate=separate)
        st.session_state.history = [str(out)]
        st.session_state.msg = "清理完成！先聽聽看，需要剪的地方直接打字跟我說。"
        goto(3)
    if col2.button("← 上一步", use_container_width=True):
        goto(1)


# ---------- 步驟 3：溝通剪輯 ----------

def _next_path() -> Path:
    return (Path(st.session_state.workdir)
            / f"v{len(st.session_state.history)}.mp3")


def _handle_command(text: str) -> None:
    current = st.session_state.history[-1]
    action, payload = parse_command(text)
    try:
        if action == "remove" or action == "keep":
            out = cut(current, payload, mode=action, output=_next_path())
            st.session_state.history.append(str(out))
            word = "剪掉" if action == "remove" else "只保留"
            st.session_state.msg = (f"好了，{word} {'、'.join(payload)}。"
                                    f"現在長度 {fmt_time(probe_duration(out))}。")
        elif action == "trim":
            out = trim_silence(current, output=_next_path(), threshold=-40)
            st.session_state.history.append(str(out))
            st.session_state.msg = (f"頭尾空白清掉了，"
                                    f"現在長度 {fmt_time(probe_duration(out))}。")
        elif action == "gaps":
            out = trim_silence(current, output=_next_path(),
                               threshold=-40, gaps=True)
            st.session_state.history.append(str(out))
            st.session_state.msg = (f"長停頓縮短了，"
                                    f"現在長度 {fmt_time(probe_duration(out))}。")
        elif action in ("remove_text", "find_text"):
            from audio_studio.transcribe import find
            with st.spinner(f"正在錄音裡找「{payload}」…"):
                matches = find(current, payload, "small", "zh")
            if not matches:
                st.session_state.msg = f"沒找到「{payload}」，換個說法試試？"
            elif action == "find_text":
                lines = [f"- {fmt_time(s)} ~ {fmt_time(e)}（…{c}…）"
                         for s, e, c in matches]
                st.session_state.msg = ("找到 " + str(len(matches)) + " 處：\n"
                                        + "\n".join(lines))
            else:
                ranges = [f"{max(0, s - 0.05):.3f}-{e + 0.05:.3f}"
                          for s, e, _ in matches]
                out = cut(current, ranges, mode="remove", output=_next_path())
                st.session_state.history.append(str(out))
                where = "、".join(f"{fmt_time(s)}~{fmt_time(e)}"
                                  for s, e, _ in matches)
                st.session_state.msg = (f"找到 {len(matches)} 處（{where}），"
                                        f"都剪掉了。現在長度 "
                                        f"{fmt_time(probe_duration(out))}。")
        elif action == "speed":
            out = _next_path()
            run_ffmpeg(["-i", str(current), "-af", f"atempo={payload}",
                        *encode_args(out), str(out)])
            st.session_state.history.append(str(out))
            word = "加快" if payload > 1 else "放慢"
            st.session_state.msg = (f"{word}為 {payload} 倍（音調不變），"
                                    f"現在長度 {fmt_time(probe_duration(out))}。")
        elif action == "volume":
            out = _next_path()
            run_ffmpeg(["-i", str(current), "-af", f"volume={payload}dB",
                        *encode_args(out), str(out)])
            st.session_state.history.append(str(out))
            word = "大聲" if payload > 0 else "小聲"
            st.session_state.msg = f"{word}了 {abs(payload):.0f}dB。"
        elif action == "fade":
            d = probe_duration(current)
            out = _next_path()
            run_ffmpeg(["-i", str(current),
                        "-af", f"afade=t=in:st=0:d=0.4,"
                               f"afade=t=out:st={max(d - 0.6, 0):.3f}:d=0.6",
                        *encode_args(out), str(out)])
            st.session_state.history.append(str(out))
            st.session_state.msg = "頭尾加上淡入淡出了。"
        elif action == "undo":
            if len(st.session_state.history) > 1:
                st.session_state.history.pop()
                st.session_state.msg = "已還原上一步。"
            else:
                st.session_state.msg = "已經是最原始的清理版了，沒有可還原的。"
        else:
            st.session_state.msg = HELP_TEXT
    except Exception as exc:  # 把技術錯誤翻成白話給使用者看
        st.session_state.msg = f"這一步出了點問題：{exc}"


def step3() -> None:
    st.subheader("聽聽看，要剪哪裡跟我說")
    current = st.session_state.history[-1]
    st.audio(current)
    st.caption(f"目前長度：{fmt_time(probe_duration(current))}　"
               f"（已做 {len(st.session_state.history) - 1} 個剪輯動作）")

    with st.form("cmd_form", clear_on_submit=True):
        text = st.text_input("剪輯指令",
                             placeholder="例：剪掉 2:10-2:30／刪掉『下星期三』／去空白")
        submitted = st.form_submit_button("送出", type="primary")
    if submitted and text.strip():
        _handle_command(text)
        st.rerun()

    if st.session_state.msg:
        st.info(st.session_state.msg.replace("\n", "  \n"))

    with st.expander("逐字稿（想看講了什麼、對時間點時用）"):
        if st.button("產生逐字稿"):
            from audio_studio.transcribe import transcribe
            with st.spinner("語音辨識中…"):
                out = transcribe(current, model_size="small", language="zh",
                                 fmt="srt",
                                 output=Path(st.session_state.workdir)
                                 / "逐字稿.srt")
            st.session_state.transcript = out.read_text(encoding="utf-8")
        if st.session_state.transcript:
            st.text(st.session_state.transcript)
            st.caption("注意：剪輯之後時間軸會變，需要重新產生。")

    col1, col2 = st.columns(2)
    if col1.button("剪好了，下一步 →", type="primary",
                   use_container_width=True):
        goto(4)
    if len(st.session_state.history) > 1:
        if col2.button("↩ 還原上一步", use_container_width=True):
            st.session_state.history.pop()
            st.session_state.msg = "已還原上一步。"
            st.rerun()


# ---------- 步驟 4：轉檔 ----------

def step4() -> None:
    st.subheader("輸出設定")
    default_name = Path(st.session_state.orig_name).stem + "_乾淨版"
    name = st.text_input("檔名", value=default_name)
    fmt = st.radio("格式", ["mp3（最通用，建議）", "wav（無損，檔案大）",
                           "m4a（Apple 系）"])

    col1, col2 = st.columns(2)
    if col1.button("輸出成品 🎁", type="primary", use_container_width=True):
        ext = "." + fmt.split("（")[0]
        OUTPUT_DIR.mkdir(exist_ok=True)
        out = OUTPUT_DIR / f"{name.strip() or default_name}{ext}"
        with st.spinner("轉檔中…"):
            run_ffmpeg(["-i", st.session_state.history[-1],
                        *encode_args(out), str(out)])
        st.session_state.outfile = str(out)
        goto(5)
    if col2.button("← 回去再剪", use_container_width=True):
        goto(3)


# ---------- 步驟 5：完成 ----------

def step5() -> None:
    st.subheader("完成！🎉")
    out = Path(st.session_state.outfile)
    st.audio(str(out))
    st.success(f"成品已存檔：`{out}`")
    st.download_button("⬇ 下載成品", data=out.read_bytes(),
                       file_name=out.name, type="primary",
                       use_container_width=True)
    if st.button("再處理下一個檔案", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def main() -> None:
    init_state()
    st.title("🎙️ 錄音工作室")
    steps_bar()
    {1: step1, 2: step2, 3: step3, 4: step4, 5: step5}[st.session_state.step]()


main()
