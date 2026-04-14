from __future__ import annotations

import csv
import ctypes
import io
import os
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any, Optional, Set, Tuple

try:
    import psutil as _psutil
except Exception:
    _psutil = None
PSUTIL_AVAILABLE = _psutil is not None
psutil: Any = _psutil

try:
    import winreg as _winreg
except Exception:
    _winreg = None
WINREG_AVAILABLE = _winreg is not None
winreg: Any = _winreg


class ProcessInspector:
    _warning_lock = threading.Lock()
    _last_warning = ""

    @staticmethod
    def _set_warning(message: str) -> None:
        with ProcessInspector._warning_lock:
            ProcessInspector._last_warning = message or ""

    @staticmethod
    def consume_last_warning() -> str:
        with ProcessInspector._warning_lock:
            message = ProcessInspector._last_warning
            ProcessInspector._last_warning = ""
            return message

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
            ProcessInspector._set_warning("")
            return set()

        pids: Set[int] = set()
        warning_messages: list[str] = []
        psutil_mod: Any = psutil
        if psutil_mod is not None:
            try:
                proc_iter = psutil_mod.process_iter(["pid", "name"])
            except Exception as exc:
                proc_iter = None
                warning_messages.append(f"psutil init failed ({exc.__class__.__name__})")
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
                    ProcessInspector._set_warning("")
                    return pids
                except Exception as exc:
                    # Fall through to tasklist fallback on psutil loop failure.
                    warning_messages.append(f"psutil loop failed ({exc.__class__.__name__})")
            if warning_messages:
                warning_messages.append("using tasklist fallback")

        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {normalized}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                timeout=3,
            )
            if result.returncode != 0:
                warning_messages.append(f"tasklist returncode={result.returncode}")
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
        except Exception as exc:
            warning_messages.append(f"tasklist failed ({exc.__class__.__name__})")

        ProcessInspector._set_warning("; ".join(warning_messages) if warning_messages else "")
        return pids

    @staticmethod
    def probe_tasklist() -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                timeout=3,
            )
            if result.returncode != 0:
                return False, f"tasklist returncode={result.returncode}"
            return True, "tasklist 실행 가능"
        except Exception as exc:
            return False, f"{exc.__class__.__name__}: {exc}"


class StartupManager:
    KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    NAME = "KakaoTalkAdBlockerLayout"

    @staticmethod
    def build_command() -> str:
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --startup-launch --minimized'
        script = Path(sys.argv[0]).resolve()
        return f'"{sys.executable}" "{script}" --startup-launch --minimized'

    @staticmethod
    def get_registered_command() -> Optional[str]:
        winreg_mod: Any = winreg
        if winreg_mod is None:
            return None
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_READ,
            )
            try:
                value, _reg_type = winreg_mod.QueryValueEx(key, StartupManager.NAME)
                return str(value or "")
            finally:
                winreg_mod.CloseKey(key)
        except Exception:
            return None

    @staticmethod
    def _split_command(command: str) -> list[str]:
        if not command:
            return []
        try:
            tokens = shlex.split(command, posix=False)
        except Exception:
            return []
        return [token[1:-1] if len(token) >= 2 and token[0] == token[-1] == '"' else token for token in tokens]

    @staticmethod
    def _command_target_paths(command: str) -> list[str]:
        tokens = StartupManager._split_command(command)
        if not tokens:
            return []
        targets = [tokens[0]]
        for token in tokens[1:]:
            normalized = token.lower()
            if normalized.startswith("-") or normalized.startswith("/"):
                break
            targets.append(token)
            if len(targets) >= 2:
                break
        return targets

    @staticmethod
    def registration_health() -> tuple[str, str]:
        command = StartupManager.get_registered_command()
        if not command:
            return "not_registered", "Run 등록 안 됨"
        expected = StartupManager.build_command()
        targets = StartupManager._command_target_paths(command)
        missing_targets = [target for target in targets if target and not Path(target).exists()]
        if missing_targets:
            missing_text = ", ".join(missing_targets)
            return "missing_target", f"Run 등록 대상 누락: {missing_text}"
        if command != expected:
            return "stale_command", "Run 등록 명령 불일치"
        return "healthy", "Run 등록 명령 정상"

    @staticmethod
    def probe_registration_command() -> Tuple[bool, str]:
        status, detail = StartupManager.registration_health()
        return status in {"healthy", "not_registered"}, detail

    @staticmethod
    def sync_registration_command() -> bool:
        winreg_mod: Any = winreg
        if winreg_mod is None:
            return False
        expected = StartupManager.build_command()
        current = StartupManager.get_registered_command()
        if current == expected:
            return True
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_SET_VALUE,
            )
            try:
                winreg_mod.SetValueEx(key, StartupManager.NAME, 0, winreg_mod.REG_SZ, expected)
            finally:
                winreg_mod.CloseKey(key)
            return True
        except Exception:
            return False

    @staticmethod
    def wait_for_shell_ready(timeout_seconds: float = 15.0, poll_interval_seconds: float = 0.5) -> bool:
        if os.name != "nt":
            return False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            find_window = user32.FindWindowW
            find_window.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            find_window.restype = wintypes.HWND
        except Exception:
            return False

        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        stable_hits = 0
        required_hits = 2
        while time.monotonic() < deadline:
            explorer_ready = bool(ProcessInspector.get_process_ids("explorer.exe"))
            tray_ready = bool(find_window("Shell_TrayWnd", None))
            if explorer_ready and tray_ready:
                stable_hits += 1
                if stable_hits >= required_hits:
                    return True
            else:
                stable_hits = 0
            time.sleep(max(poll_interval_seconds, 0.05))
        return bool(ProcessInspector.get_process_ids("explorer.exe")) and bool(find_window("Shell_TrayWnd", None))

    @staticmethod
    def is_enabled() -> bool:
        winreg_mod: Any = winreg
        if winreg_mod is None:
            return False
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_READ,
            )
            try:
                winreg_mod.QueryValueEx(key, StartupManager.NAME)
                return True
            finally:
                winreg_mod.CloseKey(key)
        except Exception:
            return False

    @staticmethod
    def set_enabled(enable: bool) -> bool:
        winreg_mod: Any = winreg
        if winreg_mod is None:
            return False
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_SET_VALUE,
            )
            try:
                if enable:
                    cmd = StartupManager.build_command()
                    winreg_mod.SetValueEx(key, StartupManager.NAME, 0, winreg_mod.REG_SZ, cmd)
                else:
                    try:
                        winreg_mod.DeleteValue(key, StartupManager.NAME)
                    except FileNotFoundError:
                        pass
            finally:
                winreg_mod.CloseKey(key)
            return True
        except Exception:
            return False

    @staticmethod
    def probe_access() -> Tuple[bool, str]:
        winreg_mod: Any = winreg
        if winreg_mod is None:
            return False, "winreg unavailable"
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_READ,
            )
            try:
                pass
            finally:
                winreg_mod.CloseKey(key)
        except Exception as exc:
            return False, f"read failed ({exc.__class__.__name__}: {exc})"
        try:
            key = winreg_mod.OpenKey(
                winreg_mod.HKEY_CURRENT_USER,
                StartupManager.KEY,
                0,
                winreg_mod.KEY_SET_VALUE,
            )
            try:
                return True, "Run 레지스트리 읽기/쓰기 가능"
            finally:
                winreg_mod.CloseKey(key)
        except Exception as exc:
            return False, f"write failed ({exc.__class__.__name__}: {exc})"


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
    RELEASES_URL = "https://github.com/twbeatles/kakaotalk-pc-adblock-py/releases"

    @staticmethod
    def open_releases_page() -> bool:
        return ShellService.open_url(ReleaseService.RELEASES_URL)


__all__ = ["ProcessInspector", "StartupManager", "ShellService", "ReleaseService"]
