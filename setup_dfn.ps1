# 安裝 DeepFilterNet3 深度降噪引擎（可選，但強烈建議）
# 用法：powershell -File setup_dfn.ps1
#
# 為什麼需要獨立環境：DeepFilterNet 只支援到 Python 3.11，
# 所以這裡裝一份使用者層級的 Python 3.11 + 專用虛擬環境，
# 主程式（任何 Python 版本）處理時會自動呼叫它。
# 裝好之後，「標準」以上的降噪強度會自動改用 DeepFilterNet3。

$ErrorActionPreference = 'Continue'
$py311 = "$env:USERPROFILE\python311\python.exe"
$venv = Join-Path $PSScriptRoot ".dfn311"

if (-not (Test-Path $py311)) {
    Write-Host "下載 Python 3.11（使用者層級安裝，不需系統管理員）..."
    $exe = "$env:TEMP\python-3.11.9-amd64.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $exe
    Start-Process -FilePath $exe -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=0',"TargetDir=$env:USERPROFILE\python311" -Wait
}
if (-not (Test-Path $py311)) { Write-Host "Python 3.11 安裝失敗"; exit 1 }

Write-Host "建立虛擬環境並安裝 DeepFilterNet（PyTorch 約 200MB，請稍候）..."
& $py311 -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$venv\Scripts\python.exe" -m pip install --quiet numpy==1.26.4 torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
& "$venv\Scripts\python.exe" -m pip install --quiet deepfilternet==0.5.6 soundfile

if (Test-Path "$venv\Scripts\deepFilter.exe") {
    Write-Host "完成！之後清理音檔會自動使用 DeepFilterNet3。"
} else {
    Write-Host "安裝似乎沒成功，請把上面的錯誤訊息回報。"
    exit 1
}
