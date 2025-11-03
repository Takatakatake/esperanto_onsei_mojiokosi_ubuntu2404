<#
.SYNOPSIS
  Beginner-friendly launcher for Windows users.
.NOTES
  Activates .venv311 when present, then runs the easy-start CLI.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $repoRoot

$venvActivate = Join-Path $repoRoot ".venv311\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$pythonArgs = @("-m", "transcriber.cli", "--easy-start") + $args

if (-not $pythonCmd) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        Write-Warning "python が見つからなかったため、py -3 を利用します。"
        $pythonCmd = $launcher
        $pythonArgs = @("-3", "-m", "transcriber.cli", "--easy-start") + $args
    }
}

if (-not $pythonCmd) {
    Write-Error "Python が見つかりません。python.org からインストールし、PATH に追加してください。"
    exit 127
}

$pythonPath = $pythonCmd.Source
if (-not $pythonPath) {
    $pythonPath = $pythonCmd.Path
}

& $pythonPath @pythonArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Warning ("easy_start が終了コード {0} で終了しました。上記の出力または logs ディレクトリを確認してください。" -f $exitCode)
    exit $exitCode
}
