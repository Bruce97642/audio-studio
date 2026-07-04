# audio-studio 端對端驗證腳本
# 用法：powershell -File tests\run_tests.ps1        （核心測試，約 1 分鐘）
#       powershell -File tests\run_tests.ps1 -Full  （加測 Whisper 逐字稿與 Demucs 分離）
param([switch]$Full)

# 注意：Windows PowerShell 5.1 會把原生程式的 stderr 當錯誤，
# 所以這裡不用 Stop，改由每項 Check 的 PASS/FAIL 判定結果
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$t = "tests"
$fails = 0

function Get-Rms($file, $range) {
    $out = ffmpeg -hide_banner -i $file -af "atrim=$range,astats=measure_perchannel=none" -f null - 2>&1 | Out-String
    return [double][regex]::Match($out, 'RMS level dB:\s+(-?[\d.]+)').Groups[1].Value
}
function Get-Dur($file) {
    return [double](ffprobe -v error -show_entries format=duration -of csv=p=0 $file)
}
function Check($name, $ok, $detail) {
    if ($ok) { Write-Host "  PASS  $name  ($detail)" }
    else { Write-Host "  FAIL  $name  ($detail)"; $script:fails++ }
}

Write-Host "=== 1. 產生測試音檔（TTS 人聲 + 人工噪音）==="
Add-Type -AssemblyName System.Speech
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zh = $tts.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' } | Select-Object -First 1
if ($zh) { $tts.SelectVoice($zh.VoiceInfo.Name) }
$tts.SetOutputToWaveFile("$t\speech_clean.wav")
$tts.Speak('大家好，歡迎來到光復鄉的社區廣播。今天我們要介紹在地小農的有機蔬菜，還有下星期六早上九點，在社區活動中心舉辦的市集活動。現場有音樂表演和美食攤位，歡迎大家帶著全家人一起來參加。')
$tts.Dispose()

# 前 2 秒純噪音，之後人聲混粉紅噪音＋120Hz 哼聲（模擬吵雜現場）
ffmpeg -hide_banner -v error -y -i "$t\speech_clean.wav" `
    -f lavfi -t 30 -i "anoisesrc=color=pink:amplitude=0.15:sample_rate=48000:seed=42" `
    -f lavfi -t 30 -i "sine=frequency=120:sample_rate=48000" `
    -filter_complex "[0:a]aresample=48000,aformat=channel_layouts=mono,adelay=2000,apad=pad_dur=1.5[sp];[2:a]volume=0.05[hum];[1:a][hum]amix=inputs=2:normalize=0[nz];[sp][nz]amix=inputs=2:duration=first:normalize=0[out]" `
    -map "[out]" -c:a pcm_s16le "$t\speech_noisy.wav"

$dur = Get-Dur "$t\speech_noisy.wav"
$snrBefore = (Get-Rms "$t\speech_noisy.wav" '5:15') - (Get-Rms "$t\speech_noisy.wav" '0.2:1.8')
Write-Host ("  測試檔長度 {0:N1}s，處理前訊噪比 {1:N1} dB" -f $dur, $snrBefore)

Write-Host "=== 2. clean 一鍵清理 ==="
audio-studio clean "$t\speech_noisy.wav" -o "$t\out_default.mp3"
$snrAfter = (Get-Rms "$t\out_default.mp3" '5:15') - (Get-Rms "$t\out_default.mp3" '0.2:1.8')
Check "降噪（預設）" ($snrAfter - $snrBefore -ge 8) ("SNR {0:N1} -> {1:N1} dB" -f $snrBefore, $snrAfter)

audio-studio clean "$t\speech_noisy.wav" --extra -o "$t\out_extra.mp3"
$snrExtra = (Get-Rms "$t\out_extra.mp3" '5:15') - (Get-Rms "$t\out_extra.mp3" '0.2:1.8')
Check "降噪（--extra）" ($snrExtra - $snrBefore -ge 12) ("SNR {0:N1} -> {1:N1} dB" -f $snrBefore, $snrExtra)

ffmpeg -hide_banner -v error -y -i "$t\speech_noisy.wav" -c:a aac -b:a 128k "$t\speech_noisy.m4a"
audio-studio clean "$t\speech_noisy.m4a" -o "$t\out_m4a.mp3"
Check "m4a 輸入" (Test-Path "$t\out_m4a.mp3") "手機錄音格式"

Write-Host "=== 3. 剪輯功能 ==="
audio-studio cut "$t\out_default.mp3" -r 0:05-0:10 -o "$t\cut_remove.mp3"
$d = Get-Dur "$t\cut_remove.mp3"
Check "cut 剪掉範圍" ([Math]::Abs($d - ($dur - 5)) -lt 0.4) ("{0:N2}s，預期 {1:N2}s" -f $d, ($dur - 5))

audio-studio cut "$t\out_default.mp3" -k 0:02-0:12 -o "$t\cut_keep.mp3"
$d = Get-Dur "$t\cut_keep.mp3"
Check "cut 只保留範圍" ([Math]::Abs($d - 10) -lt 0.4) ("{0:N2}s，預期 10s" -f $d)

audio-studio join "$t\cut_remove.mp3" "$t\cut_keep.mp3" -o "$t\joined.mp3"
$d = Get-Dur "$t\joined.mp3"
$expect = (Get-Dur "$t\cut_remove.mp3") + (Get-Dur "$t\cut_keep.mp3")
Check "join 接檔" ([Math]::Abs($d - $expect) -lt 0.5) ("{0:N2}s，預期 {1:N2}s" -f $d, $expect)

audio-studio trim "$t\out_default.mp3" --db -35 -o "$t\trimmed.mp3"
$d = Get-Dur "$t\trimmed.mp3"
Check "trim 去空白" ($dur - $d -ge 1.5) ("{0:N2}s -> {1:N2}s" -f $dur, $d)

if ($Full) {
    Write-Host "=== 4. Whisper 逐字稿 ==="
    audio-studio transcribe "$t\out_extra.mp3" --format srt --lang zh -o "$t\out_extra.srt"
    $srt = Get-Content "$t\out_extra.srt" -Raw -Encoding UTF8
    Check "transcribe" ($srt -match '光復' -and $srt -match '-->') "辨識出關鍵詞與時間軸"

    Write-Host "=== 5. Demucs 音樂分離 ==="
    ffmpeg -hide_banner -v error -y -i "$t\speech_clean.wav" `
        -f lavfi -t 30 -i "sine=frequency=220:sample_rate=48000" `
        -f lavfi -t 30 -i "sine=frequency=277:sample_rate=48000" `
        -f lavfi -t 30 -i "sine=frequency=330:sample_rate=48000" `
        -filter_complex "[1:a][2:a][3:a]amix=inputs=3:normalize=0,volume=0.25,tremolo=f=2:d=0.7[music];[0:a]aresample=48000,aformat=channel_layouts=mono,adelay=2000,apad=pad_dur=1.5[sp];[sp][music]amix=inputs=2:duration=first:normalize=0[out]" `
        -map "[out]" -c:a pcm_s16le "$t\speech_music.wav"
    audio-studio clean "$t\speech_music.wav" --separate -o "$t\out_separate.mp3"
    $musicDrop = (Get-Rms "$t\speech_music.wav" '0.2:1.8') - (Get-Rms "$t\out_separate.mp3" '0.2:1.8')
    Check "音樂消除" ($musicDrop -ge 15) ("背景音樂壓低 {0:N1} dB" -f $musicDrop)
}

Write-Host ""
if ($fails -eq 0) { Write-Host "全部通過！" } else { Write-Host "$fails 項失敗"; exit 1 }
