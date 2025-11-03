<#
.SYNOPSIS
  Repository root shortcut for Windows users.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $scriptDir "scripts\easy_start.ps1"

if (-not (Test-Path $target)) {
    Write-Error "Could not locate scripts\easy_start.ps1 relative to the repository root."
    exit 1
}

& $target @args
exit $LASTEXITCODE
