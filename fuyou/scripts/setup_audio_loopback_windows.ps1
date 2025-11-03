<#
.SYNOPSIS
  Inspect loopback-capable audio devices on Windows and provide guidance.

.NOTES
  This script is non-destructive: it only reports detected devices and suggests
  configuration steps (Stereo Mix, WASAPI loopback, or virtual cables).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message)
    Write-Host "[setup_audio_loopback] $Message"
}

Write-Log "Windows ループバック環境を確認しています..."

$loopbackTerms = @(
    'Stereo Mix',
    'Loopback',
    'CABLE Output',
    'CABLE Input',
    'VB-Audio',
    'Virtual Audio'
)

$endpoints = @()
try {
    $endpoints = Get-PnpDevice -Class AudioEndpoint -Status OK | Sort-Object -Property FriendlyName
} catch {
    Write-Log "Get-PnpDevice でデバイス一覧を取得できませんでした: $($_.Exception.Message)"
    $endpoints = @()
}

if ($endpoints.Count -gt 0) {
    Write-Log "オーディオエンドポイント:"
    $endpoints | ForEach-Object {
        Write-Host ("  - {0} ({1})" -f $_.FriendlyName, $_.InstanceId)
    }

    $candidates = $endpoints | Where-Object {
        $name = $_.FriendlyName
        foreach ($term in $loopbackTerms) {
            if ($name -like "*$term*") { return $true }
        }
        return $false
    }

    if ($candidates.Count -gt 0) {
        Write-Log "ループバック候補が見つかりました:"
        $candidates | ForEach-Object {
            Write-Host ("  ✓ {0}" -f $_.FriendlyName)
        }
    } else {
        Write-Log "ループバック候補が見つかりません。以下を試してください:"
        Write-Host "  1. サウンド設定 > 入力 > 入力デバイスの管理 で『Stereo Mix』を有効化"
        Write-Host "  2. WASAPI Loopback を提供する仮想オーディオデバイス（VB-Audio など）を導入"
        Write-Host "  3. オーディオドライバの最新化や再インストール"
        if (-not $env:CI) {
            Write-Log "録音デバイス設定ダイアログ (Recording タブ) を開きます。"
            try {
                Start-Process -FilePath "control.exe" -ArgumentList "mmsys.cpl,,1" | Out-Null
            } catch {
                Write-Log "ダイアログの起動に失敗しました: $($_.Exception.Message)"
            }
        }
    }
} else {
    Write-Log "AudioEndpoint クラスでデバイスが検出できませんでした。Win32_SoundDevice を確認します..."
    try {
        $soundDevices = Get-CimInstance -ClassName Win32_SoundDevice | Sort-Object -Property Name
        if ($soundDevices.Count -eq 0) {
            Write-Log "サウンドデバイスが見つかりません。ドライバが正しくインストールされているか確認してください。"
        } else {
            $soundDevices | ForEach-Object {
                Write-Host ("  - {0}" -f $_.Name)
            }
        }
    } catch {
        Write-Log "Win32_SoundDevice の取得にも失敗しました: $($_.Exception.Message)"
    }
}

Write-Log "必要に応じて 'mmsys.cpl' で『Stereo Mix』を既定デバイスに設定してください。"
Write-Log "完了しました。"
exit 0
