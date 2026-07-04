# audio-studio 🎙️

把吵雜環境的錄音，變成接近錄音室品質的乾淨人聲。全程在自己電腦上跑，免費、離線、開源。

- **文稿配音**：貼上文字，AI 直接合成廣告級配音——八種配音風格
  （磁性男聲／沉穩／活力／知性／溫暖／甜美／戲劇／播報），
  台灣腔為主，合成後自動套廣播級後製鏈（需要網路）
- **現場錄音**：直接在瀏覽器按鈕錄音，不用另外開錄音 App
- **AI 環境診斷**：錄完（或上傳後）自動分析訊噪比、60Hz 電流哼聲、爆音，
  依背景環境自動選好最適合的降噪組合，可再手動調整
- **AI 降噪五段強度**：RNNoise 神經網路 → noisereduce 頻譜降噪 → FFT 殘噪追蹤，最強檔再掛「自適應噪音門」把講話空檔壓到全黑
- **四種音色風格**：溫暖／**廣播主持人**（胸腔共鳴＋去濁＋類比飽和諧波，渾厚磁性播音腔）／清亮／自然
- **背景音樂消除**：Demucs AI 人聲分離（市場放歌、店裡有音樂都能救）
- **聲音修復**：60Hz 電流哼聲消除（含諧波）、爆音修復
- **響度標準化**：影片 -14／Podcast -16／廣告 -12 LUFS，兩段式母帶增益精準到位
- **指令剪輯**：剪片段、接檔案、去空白、變速、音量、淡入淡出，講時間就剪
- **逐字稿**：Whisper 語音辨識（繁體中文），還能「用文字找聲音」——說出那句話，找到它的時間點，直接剪掉

## 實測成績（本機端對端驗證）

**測試一：合成穩定噪音**（中文語音＋粉紅噪音＋電流哼聲，訊噪比僅 10.1 dB）

| 降噪強度 | RNNoise（內建備援） | DeepFilterNet3（建議加裝） |
|------|------|------|
| 標準 | 19.6 dB | **44.8 dB** |
| 加強 | 24.8 dB | **54.9 dB** |

**測試二：真實情境模擬**（活動中心：六層人群交談聲＋房間回音＋手機 AAC 壓縮，
人聲與人群只差 5.3 dB）——這才是真實世界的難度：

| 降噪強度 | RNNoise | DeepFilterNet3 |
|------|------|------|
| 標準 | 0.7 dB（幾乎無效，還會悶掉人聲） | **7.8 dB，人聲完整** |
| 加強 | 0.3 dB（失效） | **12.8 dB** |

> 老實說：2018 年的 RNNoise 面對「會動的噪音」（人群、車流）敵我不分，
> 這是很多降噪工具「聽起來沒差」的原因。DeepFilterNet3（2023）能分清楚。
> 所以強烈建議跑一次 `setup_dfn.ps1`。

**其他能力**

| 項目 | 結果 |
|------|------|
| 背景音樂消除（`--separate`） | 音樂壓低 **38.3 dB**（幾乎無聲） |
| 60Hz 哼聲消除 | 哼聲頻帶再壓 **6.5 dB**（AI 降噪之外） |
| 響度標準化 | 目標 ±0.5 LUFS、真實峰值 ≤ -1.5 dBTP |
| 剪輯精準度 | 誤差 < 0.1 秒 |
| 廣播主持人音色・胸腔共鳴 | 100-150Hz 頻段 +3.8 dB（男聲測試） |
| 廣播主持人音色・去濁 | 300-500Hz 濁音頻段 -2.1 dB |
| 廣播主持人音色・類比飽和諧波 | 2、3 倍泛音各增生 **+6 dB**（磁性音色的來源） |

> 「口條」（講話節奏、咬字習慣）是表演技巧，後製沒辦法幫你改；
> 但聲音的胸腔厚度、去濁、齒音清晰、類比暖度都是後製能做到的，
> 這幾項都已經用量測數字驗證過會真的往目標方向走。

隨時可重跑驗證：`powershell -File tests\run_tests.ps1 -Full`

## 🌐 線上版本（手機、其他電腦都能用）

不用裝任何東西，瀏覽器打開網址就能用：

**👉 [填入部署完成後的網址]**

網址設有密碼保護，第一次打開會要求輸入密碼。

<details>
<summary>怎麼部署自己的線上版本（Streamlit Community Cloud，免費）</summary>

1. 把這個 GitHub 專案 fork 或直接用你自己推上去的版本
2. 打開 [share.streamlit.io](https://share.streamlit.io) → 用 GitHub 帳號登入
3. 「New app」→ 選這個 repository → Main file 填 `app.py` → Deploy
4. 部署完成後，進「Manage app → Settings → Secrets」，貼上：
   ```
   APP_PASSWORD = "改成你自己的密碼"
   ```
   儲存後網站會重啟，之後打開網址就會要求輸入這組密碼。
5. 手機也能用同一個網址，行動版瀏覽器支援現場錄音功能（需允許麥克風權限）。

`packages.txt`（安裝 ffmpeg）、`runtime.txt`（Python 版本）、`requirements.txt`
都已經配置好，部署不需要額外設定。

**免費額度的限制**：Streamlit Community Cloud 免費方案記憶體約 1GB，
一般清理錄音沒問題；如果同時處理很長的錄音或勾選背景音樂分離，速度可能較慢。
</details>

## 安裝

需求：Windows / macOS / Linux，Python 3.10+，[FFmpeg](https://ffmpeg.org/)（要在 PATH 裡）。

```bash
git clone <這個專案>
cd audio-studio
pip install -e .          # 核心功能
pip install demucs        # （可選）背景音樂消除
```

**強烈建議加裝 DeepFilterNet3 深度降噪引擎**（對人群交談、車流這種
「會動的噪音」遠強於內建的 RNNoise）：

```powershell
powershell -File setup_dfn.ps1
```

裝好之後「標準」以上的降噪強度會自動改用 DeepFilterNet3，不用改任何設定。

降噪模型 `models/bd.rnnn` 已附在專案裡（來自 [rnnoise-models](https://github.com/GregorR/rnnoise-models)）。

## 使用方式

### 最推薦：五步驟網頁精靈
雙擊 **`錄音工作室.bat`**，瀏覽器會打開一個本機網頁，照著走就好：

> ① 上傳檔案／現場錄音 → ② 選項設定 → ③ 溝通剪輯 → ④ 轉檔設定 → ⑤ 完成出檔

第 ① 步可以直接在瀏覽器現場錄音；錄好（或上傳後）會自動跑
**AI 環境診斷**：量訊噪比、抓 60Hz 電流哼聲、抓爆音，
第 ② 步的降噪強度與修復選項會自動選好建議值。

第 ② 步可調整：響度用途（影片／Podcast／廣告）、降噪強度五段滑桿、
四種音色風格、消除電流嗡嗡聲、AI 人聲分離、爆音修復。

第 ③ 步直接用白話打字剪輯：
- 「剪掉 2:10-2:30」「只保留 1:00-2:00」
- 「刪掉『下星期三』」← AI 自動找到那句話的位置剪掉
- 「去空白」「縮短停頓」「還原」
- 「加快 1.2 倍」「放慢 0.9」「大聲一點」「淡入淡出」

需要 Streamlit：`pip install streamlit`（啟動精靈才需要，指令列功能不用）。

### 最快：拖曳
把錄音檔（mp3 / m4a / wav 都行，可一次多個）拖到 **`一鍵清理.bat`** 圖示上，
乾淨版就出現在原檔案旁邊（`原檔名_乾淨版.mp3`）。

### 指令列

```bash
# 一鍵清理（降噪 → 人聲增強 → 響度標準化）
audio-studio clean 錄音.m4a
audio-studio clean 錄音.m4a --denoise max      # 最強降噪（三層 AI＋噪音門）
audio-studio clean 錄音.m4a --style radio      # 廣播主持人音色（商用推薦）
audio-studio clean 錄音.m4a --dehum            # 消除 60Hz 電流/冷氣嗡嗡聲
audio-studio clean 錄音.m4a --declip           # 爆音修復
audio-studio clean 錄音.m4a --separate         # 背景有音樂時，先 AI 分離人聲
audio-studio clean 錄音資料夾\                 # 整個資料夾批次處理
audio-studio clean 錄音.m4a --preset loud      # 廣告響度（-12 LUFS）

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

# 文稿配音（需要網路）
audio-studio voices                               # 看八種配音風格
audio-studio speak "文稿內容" --voice 磁性男聲 -o 配音.mp3
audio-studio speak 文稿.txt --voice 溫暖女聲      # 也可以直接給 txt 檔
audio-studio speak "文稿" --voice 磁性男聲 --raw  # 不做後製的原始合成

# 健檢與診斷
audio-studio analyze 錄音.mp3                     # 響度/峰值/噪音底層報告
audio-studio diagnose 錄音.mp3                    # AI 環境診斷＋建議指令
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
- **文稿配音**：聲音是合法的 AI 合成聲（微軟神經網路語音），
  **不是、也不能克隆任何真實配音員的嗓音**——克隆真人聲音商用有
  人格權法律風險。合成走微軟的免費端點，正式大量商用建議申請
  Azure 語音服務（每月有免費額度，聲音相同、授權明確）。

## 授權

[MIT](LICENSE) — 歡迎自由使用、修改、散布。
