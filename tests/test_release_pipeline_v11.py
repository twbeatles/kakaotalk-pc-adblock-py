from pathlib import Path


def test_windows_ci_runs_packaged_self_check_in_release_build():
    workflow = Path(".github/workflows/windows-ci.yml").read_text(encoding="utf-8")
    build_lines = [line.strip() for line in workflow.splitlines() if "build_release.ps1" in line]

    assert build_lines == [
        r"run: powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -NoSign"
    ]
    assert all("-SkipSmokeCheck" not in line for line in build_lines)


def test_startup_smoke_uses_bounded_wait_in_build_script():
    script = Path("scripts/build_release.ps1").read_text(encoding="utf-8")
    startup_section = script.split("function Invoke-StartupSmoke", 1)[1].split("Push-Location", 1)[0]

    assert "-Wait `" not in startup_section
    assert ".WaitForExit(60000)" in startup_section
    assert "packaged startup smoke timed out" in startup_section
