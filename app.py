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

STEP_NAMES = ["上傳檔案", "選項設定", "溝通剪輯", "轉檔設定", "完成出檔"]

# ---------- 視覺主題（深色錄音室 + 琥珀橘，Inter × Noto Sans TC）----------

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap');

body, p, h1, h2, h3, h4, h5, h6, label, input, textarea,
.stMarkdown, .stMarkdown div, .stMarkdown span,
.stButton button, .stButton button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stDownloadButton"] button p,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  font-family: 'Inter', 'Noto Sans TC', sans-serif !important;
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 500px at 15% -10%, #1E1B4B 0%, rgba(30,27,75,0) 60%),
    radial-gradient(900px 500px at 110% 15%, rgba(249,115,22,.07) 0%, rgba(249,115,22,0) 55%),
    #0F0F23;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { display: none; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2.4rem; max-width: 780px; }

h1, h2, h3 { color: #F8FAFC; }
h3 { font-weight: 600; letter-spacing: .3px; }
[data-testid="stCaptionContainer"] { color: #94A3B8; }

/* 按鈕 */
.stButton button, [data-testid="stFormSubmitButton"] button {
  border-radius: 12px; font-weight: 600; padding: .62rem 1.15rem;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
  cursor: pointer;
}
.stButton button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stDownloadButton"] button[kind="primary"] {
  background: linear-gradient(135deg, #F97316, #EA580C);
  border: none; color: #fff;
  box-shadow: 0 4px 18px rgba(249,115,22,.32);
}
.stButton button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
[data-testid="stDownloadButton"] button[kind="primary"]:hover {
  transform: translateY(-1px);
  box-shadow: 0 7px 24px rgba(249,115,22,.48);
}
.stButton button[kind="secondary"] {
  background: rgba(39,39,59,.55);
  border: 1px solid rgba(148,163,184,.25); color: #E2E8F0;
}
.stButton button[kind="secondary"]:hover {
  border-color: rgba(249,115,22,.7); color: #FDBA74;
  transform: translateY(-1px);
}

/* 上傳區 */
[data-testid="stFileUploader"] section {
  background: rgba(39,39,59,.45);
  border: 1.5px dashed rgba(249,115,22,.45);
  border-radius: 16px;
  transition: border-color .2s ease;
}
[data-testid="stFileUploader"] section:hover { border-color: #F97316; }

/* 訊息卡 */
[data-testid="stAlert"] {
  background: rgba(30,27,75,.5);
  border: 1px solid rgba(99,102,241,.35);
  border-radius: 12px;
}

/* 摺疊區與輸入框 */
[data-testid="stExpander"] {
  background: rgba(39,39,59,.35);
  border: 1px solid rgba(148,163,184,.14);
  border-radius: 12px;
}
.stTextInput input {
  background: #1A1A2E; border: 1px solid rgba(148,163,184,.25);
  border-radius: 10px; color: #F8FAFC;
}
.stTextInput input:focus {
  border-color: #F97316; box-shadow: 0 0 0 2px rgba(249,115,22,.22);
}

audio { width: 100%; }
[data-testid="stAudio"] { margin: .3rem 0 .2rem; }

/* 品牌區 */
.as-brand { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.as-brand-icon {
  width: 48px; height: 48px; border-radius: 14px; flex: none;
  background: linear-gradient(135deg, #F97316, #C2410C);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(249,115,22,.35);
}
.as-brand-title { font-size: 26px; font-weight: 700; color: #F8FAFC; line-height: 1.15; }
.as-brand-sub { font-size: 11px; letter-spacing: 4px; color: #F97316; font-weight: 600; }

/* 步驟指示器 */
.as-stepper { display: flex; align-items: flex-start; margin: 4px 0 26px; }
.as-step { display: flex; flex-direction: column; align-items: center; gap: 7px; min-width: 72px; }
.as-dot {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px; transition: all .3s ease;
}
.as-todo .as-dot { background: #1A1A2E; border: 1.5px solid #33334D; color: #64748B; }
.as-current .as-dot {
  background: linear-gradient(135deg, #F97316, #EA580C); color: #fff;
  box-shadow: 0 0 0 4px rgba(249,115,22,.20), 0 4px 14px rgba(249,115,22,.42);
}
.as-done .as-dot { background: rgba(249,115,22,.14); border: 1.5px solid #F97316; }
.as-lbl { font-size: 12px; color: #64748B; }
.as-current .as-lbl { color: #F8FAFC; font-weight: 600; }
.as-done .as-lbl { color: #CBD5E1; }
.as-bar { flex: 1; height: 2px; background: #33334D; margin-top: 16px; border-radius: 2px; }
.as-bar.done { background: linear-gradient(90deg, #F97316, rgba(249,115,22,.35)); }
</style>
"""

MIC_SVG = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
           'stroke="white" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 '
           '6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
           '<line x1="12" x2="12" y1="19" y2="22"/></svg>')

CHECK_SVG = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" '
             'stroke="#F97316" stroke-width="3.2" stroke-linecap="round" '
             'stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>')

BRAND_HTML = (
    '<div class="as-brand">'
    f'<div class="as-brand-icon">{MIC_SVG}</div>'
    '<div><div class="as-brand-title">錄音工作室</div>'
    '<div class="as-brand-sub">AUDIO STUDIO · AI 人聲後製</div></div>'
    '</div>')


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
    parts = ['<div class="as-stepper">']
    for i, name in enumerate(STEP_NAMES, 1):
        cls = ("as-done" if i < cur
               else "as-current" if i == cur else "as-todo")
        dot = CHECK_SVG if i < cur else str(i)
        parts.append(f'<div class="as-step {cls}">'
                     f'<div class="as-dot">{dot}</div>'
                     f'<div class="as-lbl">{name}</div></div>')
        if i < len(STEP_NAMES):
            parts.append(f'<div class="as-bar{" done" if i < cur else ""}">'
                         '</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


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
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    st.markdown(BRAND_HTML, unsafe_allow_html=True)
    steps_bar()
    {1: step1, 2: step2, 3: step3, 4: step4, 5: step5}[st.session_state.step]()


main()
