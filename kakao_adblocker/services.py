from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Set

try:
    import psutil

    PSUTIL_AVAILABLE = True
except Exception:
    psutil = None
    PSUTIL_AVAILABLE = False

try:
    import winreg

    WINREG_AVAILABLE = True
except Exception:
    winreg = None
    WINREG_AVAILABLE = False


class ProcessInspector:
    @staticmethod
    def _normalize_image_name(image_name: str) -> str:
        name = (image_name or "").strip().lower()
        if not name:
            return ""
        return name if name.endswith(".exe") else f"{name}.exe"

    @staticmethod
    def get_process_ids(image_name: str = "kakaotalk.exe") -> Set[int]:
        normalized = ProcessInspector._normalize_image_name(image_name)
        if not normalized:
            return set()

        pids: Set[int] = set()
        if PSUTIL_AVAILABLE:
            try:
                proc_iter = psutil.process_iter(["pid", "name"])
            except Exception:
                proc_iter = None
            if proc_iter is not None:
                try:
                    for proc in proc_iter:
                        try:
                            proc_info = proc.info or {}
                            proc_name = (proc_info.get("name") or "").strip().lower()
                            if proc_name == normalized:
                                pids.add(int(proc_info["pid"]))
                        except Exception:
                            continue
                    return pids
                except Exception:
                    # Fall through to tasklist fallback on psutil loop failure.
                    pass

        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {normalized}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                timeout=3,
            )
            parser = csv.reader(io.StringIO(result.stdout))
            for row in parser:
                if len(row) < 2:
                    continue
                image = row[0].strip().lower()
                if image != normalized:
                    continue
                try:
                    pids.add(int(row[1]))
                except Exception:
                    continue
        except Exception:
            pass
        return pids


class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerLayout"

    @staticmethod
    def is_enabled() -> bool:
        if not WINREG_AVAILABLE:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, StartupManager.NAME)
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    @staticmethod
    def set_enabled(enable: bool) -> bool:
        if not WINREG_AVAILABLE:
            return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY, 0, winreg.KEY_SET_VALUE)
            try:
                if enable:
                    if getattr(sys, "frozen", False):
                        cmd = f'"{sys.executable}" --minimized'
                    else:
                        script = Path(sys.argv[0]).resolve()
                        cmd = f'"{sys.executable}" "{script}" --minimized'
                    winreg.SetValueEx(key, StartupManager.NAME, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.NAME)
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            return True
        except Exception:
            return False


class ShellService:
    @staticmethod
    def open_folder(path: str) -> bool:
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{path}")
            return True
        except Exception:
            return False

    @staticmethod
    def open_url(url: str) -> bool:
        try:
            if os.name == "nt":
                subprocess.Popen(
                    ["rundll32", "url.dll,FileProtocolHandler", url],
                    creationflags=0x08000000,
                )
            else:
                webbrowser.open(url)
            return True
        except Exception:
            return False


class ReleaseService:
    RELEASES_URL = "https://github.com/twbeatles/kakaotalk-pc-adblock-py"

    @staticmethod
    def open_releases_page() -> bool:
        return ShellService.open_url(ReleaseService.RELEASES_URL)


__all__ = ["ProcessInspector", "StartupManager", "ShellService", "ReleaseService"]
