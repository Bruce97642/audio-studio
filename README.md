# audio-studio 🎙️

把吵雜環境的錄音，變成接近錄音室品質的乾淨人聲。全程在自己電腦上跑，免費、離線、開源。

- **AI 降噪**：RNNoise 神經網路降噪 + 頻譜降噪雙引擎
- **背景音樂消除**：Demucs AI 人聲分離（市場放歌、店裡有音樂都能救）
- **人聲增強**：消齒音、EQ、壓縮、響度標準化（符合 YouTube / Podcast 播出標準）
- **指令剪輯**：剪片段、接檔案、去空白，講時間就剪
- **逐字稿**：Whisper 語音辨識（繁體中文），還能「用文字找聲音」——說出那句話，找到它的時間點，直接剪掉

## 實測成績（本機端對端驗證）

測試方法：中文語音混入粉紅噪音＋電流哼聲（訊噪比僅 10.1 dB 的惡劣條件）。

| 項目 | 結果 |
|------|------|
| 一鍵清理（預設） | 訊噪比 10.1 → **20.2 dB** |
| 一鍵清理（`--extra`） | 訊噪比 10.1 → **26.3 dB** |
| 背景音樂消除（`--separate`） | 音樂壓低 **38.3 dB**（幾乎無聲） |
| 響度標準化 | -14 LUFS、真實峰值 ≤ -1.5 dBTP |
| 剪輯精準度 | 誤差 < 0.1 秒 |

隨時可重跑驗證：`powershell -File tests\run_tests.ps1 -Full`

## 安裝

需求：Windows / macOS / Linux，Python 3.10+，[FFmpeg](https://ffmpeg.org/)（要在 PATH 裡）。

```bash
git clone <這個專案>
cd audio-studio
pip install -e .          # 核心功能
pip install demucs        # （可選）背景音樂消除
```

降噪模型 `models/bd.rnnn` 已附在專案裡（來自 [rnnoise-models](https://github.com/GregorR/rnnoise-models)）。

## 使用方式

### 最推薦：五步驟網頁精靈
雙擊 **`錄音工作室.bat`**，瀏覽器會打開一個本機網頁，照著走就好：

> ① 上傳檔案 → ② 選項設定 → ③ 溝通剪輯 → ④ 轉檔設定 → ⑤ 完成出檔

第 ③ 步直接用白話打字剪輯：
- 「剪掉 2:10-2:30」「只保留 1:00-2:00」
- 「刪掉『下星期三』」← AI 自動找到那句話的位置剪掉
- 「去空白」「縮短停頓」「還原」

需要 Streamlit：`pip install streamlit`（啟動精靈才需要，指令列功能不用）。

### 最快：拖曳
把錄音檔（mp3 / m4a / wav 都行，可一次多個）拖到 **`一鍵清理.bat`** 圖示上，
乾淨版就出現在原檔案旁邊（`原檔名_乾淨版.mp3`）。

### 指令列

```bash
# 一鍵清理（降噪 → 人聲增強 → 響度標準化）
audio-studio clean 錄音.m4a
audio-studio clean 錄音.m4a --extra        # 噪音很頑固時，加開第二層降噪
audio-studio clean 錄音.m4a --separate     # 背景有音樂時，先 AI 分離人聲
audio-studio clean 錄音資料夾\             # 整個資料夾批次處理
audio-studio clean 錄音.m4a --preset podcast   # Podcast 響度（-16 LUFS）

# 剪輯
audio-studio cut 錄音.mp3 -r 2:10-2:30            # 剪掉 2分10秒到2分30秒
audio-studio cut 錄音.mp3 -r 0:00-0:05 -r 3:00-3:10   # 一次剪多段
audio-studio cut 錄音.mp3 -k 1:00-2:00            # 只保留這一段
audio-studio join 開場.mp3 正文.mp3 結尾.mp3 -o 完整版.mp3
audio-studio trim 錄音.mp3                        # 去頭尾空白
audio-studio trim 錄音.mp3 --gaps                 # 連中間的長停頓一起縮短

# 逐字稿與文字剪輯
audio-studio transcribe 錄音.mp3                  # 逐字稿 txt
audio-studio transcribe 錄音.mp3 --format srt     # 字幕檔（給 CapCut 用）
audio-studio find 錄音.mp3 "呃那個我們再重來"       # 找出這句話的時間點
audio-studio cut 錄音.mp3 -r 1:23.4-1:26.1        # 然後剪掉它

# 健檢
audio-studio analyze 錄音.mp3                     # 響度/峰值/噪音底層報告
```

### 搭配 Claude 用白話剪輯
在 Claude Code 裡直接說：

> 「幫我把這個錄音清乾淨，然後把講錯的那句『下星期三』剪掉」

Claude 會自動組合 `clean` → `find` → `cut` 完成。

## 技術架構

```
輸入（任何格式）
  └─ [可選] Demucs htdemucs 人聲分離（背景有音樂時）
  └─ RNNoise 神經網路降噪（48kHz）
  └─ [可選] noisereduce 非平穩頻譜降噪
  └─ 人聲增強：高通 75Hz → 消齒音 → 壓縮 3:1 → EQ（溫暖度/清晰度/空氣感）
  └─ 響度標準化：靜態增益 + 真峰值限幅器（不會把安靜段的噪音抬回來）
輸出 mp3 / wav / m4a / flac
```

逐字稿使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CPU int8，預設 small 模型）。

## 老實說的限制

- **錄的時候就爆音破音，AI 救不回來**。麥克風離嘴近一點，勝過一切後製。
- 對「講話」效果最好；唱歌混音樂的素材請用 `--separate`，但天花板較低。
- 第一次用 `transcribe` / `--separate` 會自動下載模型（數百 MB）。

## 授權

[MIT](LICENSE) — 歡迎自由使用、修改、散布。
