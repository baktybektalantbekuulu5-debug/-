<#
Озвучка через ElevenLabs. Ключ читается из файла .env в корне проекта (строка ELEVENLABS_API_KEY=...).
Файл .env не попадает в Git.

Примеры (запускать из корня проекта):
  .\tools\voice.ps1 -Check                                   # проверить ключ и остаток символов
  .\tools\voice.ps1 -ListVoices                              # список голосов аккаунта с их ID
  .\tools\voice.ps1 -VoiceId <ID> -Text "[excited] Привет!" -Out out\voices\test.mp3
  .\tools\voice.ps1 -VoiceId <ID> -TextFile реплика.txt -Out out\voices\line01.mp3
#>
param(
    [switch]$Check,
    [switch]$ListVoices,
    [string]$VoiceId,
    [string]$Text,
    [string]$TextFile,
    [string]$Out,
    [string]$Model = 'eleven_v3',
    [string]$Format = 'mp3_44100_128'
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
$api = 'https://api.elevenlabs.io/v1'

function Get-Key {
    $key = $env:ELEVENLABS_API_KEY
    if (-not $key -and (Test-Path $envFile)) {
        foreach ($line in [IO.File]::ReadAllLines($envFile)) {
            if ($line -match '^\s*ELEVENLABS_API_KEY\s*=\s*(.*)$') { $key = $Matches[1].Trim().Trim('"').Trim("'") }
        }
    }
    if (-not $key) {
        Write-Host "Ключ не найден. Откройте файл .env в корне проекта и впишите его после ELEVENLABS_API_KEY=" -ForegroundColor Yellow
        exit 2
    }
    return $key
}

function Show-ApiError($err) {
    $msg = $err.Exception.Message
    $resp = $err.Exception.Response
    if ($resp) {
        $text = $err.ErrorDetails.Message
        if (-not $text) {
            try {
                $stream = $resp.GetResponseStream()
                if ($stream.CanSeek) { $stream.Position = 0 }
                $text = (New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)).ReadToEnd()
            } catch {}
        }
        try { $d = ($text | ConvertFrom-Json).detail; if ($d.message) { $text = "$($d.status): $($d.message)" } } catch {}
        $msg = "HTTP $([int]$resp.StatusCode): $text"
    }
    Write-Host "Ошибка ElevenLabs: $msg" -ForegroundColor Red
    if ($msg -match 'api_key_id_used_as_api_key') {
        Write-Host "В .env вписан идентификатор ключа, а не сам ключ. Настоящий ключ начинается с 'sk_' и показывается только в момент создания." -ForegroundColor Yellow
    }
    exit 1
}

$headers = @{ 'xi-api-key' = (Get-Key) }

# PowerShell 5.1 читает JSON без charset как Latin-1, поэтому декодируем ответ как UTF-8 сами
function Get-Json($url) {
    $r = Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing
    return [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
}

if ($Check) {
    try { $u = Get-Json "$api/user" } catch { Show-ApiError $_ }
    $s = $u.subscription
    Write-Host "Ключ рабочий. Тариф: $($s.tier). Использовано символов: $($s.character_count) из $($s.character_limit)." -ForegroundColor Green
    exit 0
}

if ($ListVoices) {
    try { $v = Get-Json "$api/voices" } catch { Show-ApiError $_ }
    $v.voices | Sort-Object name | Format-Table name, voice_id, category -AutoSize
    exit 0
}

if ($TextFile) { $Text = [IO.File]::ReadAllText((Resolve-Path $TextFile), [Text.Encoding]::UTF8) }
if (-not $VoiceId -or -not $Text -or -not $Out) {
    Write-Host "Нужны параметры -VoiceId, -Text (или -TextFile) и -Out. Примеры — в начале этого файла." -ForegroundColor Yellow
    exit 2
}
$outPath = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }
$dir = Split-Path -Parent $outPath
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
$body = [Text.Encoding]::UTF8.GetBytes((@{ text = $Text; model_id = $Model } | ConvertTo-Json -Compress))
try {
    Invoke-WebRequest -Uri "$api/text-to-speech/$VoiceId`?output_format=$Format" -Method Post -Headers $headers `
        -ContentType 'application/json; charset=utf-8' -Body $body -OutFile $outPath -UseBasicParsing
} catch { Show-ApiError $_ }
Write-Host "Готово: $outPath ($((Get-Item $outPath).Length) байт, символов в тексте: $($Text.Length))" -ForegroundColor Green
