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
    Write-Host "2. Popup negative guard: verify a non-ad popup host with non-empty title is not dismissed by default even if it contains AdFitWebView."
    Write-Host "3. Token-less bottom panel: verify a bottom Chrome widget without ad token is not hidden by default."
    Write-Host "4. OFF/ON transition: toggle blocking OFF then ON and verify engine resumes immediately."
    Write-Host "5. Stop/exit restore: exit during active blocking and verify hidden windows are not re-hidden after restore."
    Write-Host "6. Restore failure reset: trigger/observe restore failure and verify '복원 실패 초기화' clears the counters."
    Write-Host "7. Logging startup fallback: simulate log-file lock/permission issue and verify startup survives with status/log warning."
    Write-Host "8. Tk/logging self-check: break Tk runtime or logging bootstrap intentionally and verify --self-check reports failure."
} finally {
    Pop-Location
}
