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
    Write-Host "2. Token-less bottom panel: verify a bottom Chrome widget without ad token is not hidden by default."
    Write-Host "3. OFF/ON transition: toggle blocking OFF then ON and verify engine resumes immediately."
    Write-Host "4. Stop/exit restore: exit during active blocking and verify hidden windows are not re-hidden after restore."
    Write-Host "5. Restore failure reset: trigger/observe restore failure and verify '복원 실패 초기화' clears the counters."
    Write-Host "6. Tk self-check: break Tk runtime intentionally or run in a bad GUI env and verify --self-check reports failure."
} finally {
    Pop-Location
}
