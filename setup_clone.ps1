# 安裝語音克隆引擎 F5-TTS（可選）
# 用法：powershell -File setup_clone.ps1
#
# 跟 DeepFilterNet 一樣需要 Python 3.11 的獨立環境。
# 裝好之後，「文稿配音」會多出「磁性播音（克隆聲線）」選項，
# 聲音比純 TTS 自然很多。
#
# 聲音來源：參考音是用有授權的合成語音當種子調出來的，
# 不是任何真實配音員——克隆真人嗓音有人格權問題。

$ErrorActionPreference = 'Continue'
$py311 = "$env:USERPROFILE\python311\python.exe"
$venv = Join-Path $PSScriptRoot ".clone311"

if (-not (Test-Path $py311)) {
    Write-Host "下載 Python 3.11（使用者層級安裝，不需系統管理員）..."
    $exe = "$env:TEMP\python-3.11.9-amd64.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $exe
    Start-Process -FilePath $exe -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=0',"TargetDir=$env:USERPROFILE\python311" -Wait
}
if (-not (Test-Path $py311)) { Write-Host "Python 3.11 安裝失敗"; exit 1 }

Write-Host "建立虛擬環境並安裝 F5-TTS（含 PyTorch，約 2GB，會跑一陣子）..."
& $py311 -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$venv\Scripts\python.exe" -m pip install --quiet torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu
& "$venv\Scripts\python.exe" -m pip install --quiet f5-tts soundfile

& "$venv\Scripts\python.exe" -c "import f5_tts" 2>$null
if (-not $?) {
    Write-Host "安裝似乎沒成功，請把上面的錯誤訊息回報。"
    exit 1
}

# 從 F5-TTS 內附的自然中文語音，做出降調男聲參考音
Write-Host "產生克隆參考音..."
$examples = & "$venv\Scripts\python.exe" -c "import os, f5_tts; print(os.path.join(os.path.dirname(f5_tts.__file__), 'infer', 'examples', 'basic', 'basic_ref_zh.wav'))"
$voices = Join-Path $PSScriptRoot "voices"
New-Item -ItemType Directory -Force $voices | Out-Null
ffmpeg -hide_banner -v error -y -i "$examples" -af "rubberband=pitch=0.667,highpass=f=70,equalizer=f=120:t=q:w=1:g=2,loudnorm=I=-18:TP=-2:LRA=7" -ar 24000 -ac 1 (Join-Path $voices "ref_natural_male.wav")

if (Test-Path (Join-Path $voices "ref_natural_male.wav")) {
    Write-Host "完成！第一次使用「磁性播音」時會自動下載模型（約 1.3GB）。"
} else {
    Write-Host "參考音產生失敗，請確認 ffmpeg 在 PATH 上。"
    exit 1
}
