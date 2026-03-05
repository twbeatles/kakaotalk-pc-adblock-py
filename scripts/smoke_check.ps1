param(
    [string]$PythonExe = "python",
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location $repoRoot
try {
    Write-Host "Running self-check..."
    & $PythonExe "kakaotalk_layout_adblock_v11.py" --self-check
    if ($LASTEXITCODE -ne 0) {
        throw "--self-check failed with exit code $LASTEXITCODE"
    }

    if ($RunTests) {
        Write-Host "Running pytest -q..."
        & $PythonExe -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "Manual smoke checklist:"
    Write-Host "1. Tray unavailable fallback: start with --minimized in tray-disabled env and verify main window is shown."
    Write-Host "2. OFF/ON transition: toggle blocking OFF then ON and verify engine resumes immediately."
    Write-Host "3. Restore failure reset: trigger/observe restore failure and verify '복원 실패 초기화' clears the counters."
} finally {
    Pop-Location
}
