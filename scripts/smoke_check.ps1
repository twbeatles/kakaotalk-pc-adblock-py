param(
    [string]$PythonExe = "python",
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pytestBaseTemp = Join-Path $repoRoot ".pytest_tmp"

Push-Location $repoRoot
try {
    Write-Host "Running self-check..."
    & $PythonExe "kakaotalk_layout_adblock_v11.py" --self-check
    if ($LASTEXITCODE -ne 0) {
        throw "--self-check failed with exit code $LASTEXITCODE"
    }

    if ($RunTests) {
        Write-Host "Running pytest -q --basetemp .pytest_tmp..."
        & $PythonExe -m pytest -q --basetemp .pytest_tmp
        if ($LASTEXITCODE -ne 0) {
            throw "pytest failed with exit code $LASTEXITCODE"
        }
    }

    Write-Host ""
    Write-Host "Manual smoke checklist:"
    Write-Host "1. Tray visibility: start with --minimized and verify the tray icon is actually visible without opening the main window."
    Write-Host "2. Tray unavailable fallback: start with --minimized in tray-disabled env and verify main window is shown."
    Write-Host "3. Popup negative guard: verify a non-ad popup host with non-empty title is not dismissed by default even if it contains AdFitWebView."
    Write-Host "4. Token-less bottom panel: verify a bottom Chrome widget without ad token is not hidden by default."
    Write-Host "5. OFF/ON transition: toggle blocking OFF then ON and verify engine resumes immediately."
    Write-Host "6. Stop/exit restore: exit during active blocking and verify hidden windows are not re-hidden after restore."
    Write-Host "7. Restore failure reset: trigger/observe restore failure and verify '복원 실패 초기화' clears the counters."
    Write-Host "8. Logging startup fallback: simulate log-file lock/permission issue and verify startup survives with status/log warning."
    Write-Host "9. Tk/logging self-check: break Tk runtime or logging bootstrap intentionally and verify --self-check reports failure."
} finally {
    if (Test-Path $pytestBaseTemp) {
        try {
            Remove-Item -Recurse -Force $pytestBaseTemp
        } catch {
            Write-Warning "Failed to clean ${pytestBaseTemp}: $($_.Exception.Message)"
        }
    }
    Pop-Location
}
