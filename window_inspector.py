# -*- coding: utf-8 -*-
"""
KakaoTalk Window Inspector v2.0
================================
Enhanced window hierarchy analysis tool for debugging ad layouts.

Features:
- Recursive hierarchy with indentation
- Window style flags display
- JSON export option
- Ad candidate highlighting
"""

import ctypes
import ctypes.wintypes
import logging
import json
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Constants & Setup
# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# Windows API Constants & Setup
# ═══════════════════════════════════════════════════════════════════════════════
user32 = ctypes.windll.user32
import struct
_is_64bit = struct.calcsize("P") == 8
if _is_64bit:
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_longlong
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
    user32.SetWindowLongPtrW.restype = ctypes.c_longlong
    def GetWindowLong(hwnd, index):
        return user32.GetWindowLongPtrW(hwnd, index)
    def SetWindowLong(hwnd, index, value):
        return user32.SetWindowLongPtrW(hwnd, index, value)
else:
    def GetWindowLong(hwnd, index):
        return user32.GetWindowLongW(hwnd, index)
    def SetWindowLong(hwnd, index, value):
        return user32.SetWindowLongW(hwnd, index, value)

GWL_STYLE = -16
GWL_EXSTYLE = -20

# Style flags
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_BORDER = 0x00800000
WS_CAPTION = 0x00C00000

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

# Ad-related class patterns
AD_CLASS_PATTERNS = [
    "Chrome_WidgetWin_",
    "RichPopWnd",
    "BannerAd",
    "AdView",
]

KAKAO_PATTERNS = ["EVA_", "Kakao"]


def get_class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def get_window_text(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def get_window_rect(hwnd) -> tuple:
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def get_style(hwnd) -> int:
    return GetWindowLong(hwnd, GWL_STYLE)


def get_ex_style(hwnd) -> int:
    return GetWindowLong(hwnd, GWL_EXSTYLE)


def is_visible(hwnd) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def get_parent(hwnd):
    return user32.GetParent(hwnd)


def decode_style(style: int) -> List[str]:
    """Style 플래그 디코딩"""
    flags = []
    if style & WS_VISIBLE:
        flags.append("VISIBLE")
    if style & WS_CHILD:
        flags.append("CHILD")
    if style & WS_POPUP:
        flags.append("POPUP")
    if style & WS_BORDER:
        flags.append("BORDER")
    if style & WS_CAPTION:
        flags.append("CAPTION")
    return flags


def decode_ex_style(ex_style: int) -> List[str]:
    """ExStyle 플래그 디코딩"""
    flags = []
    if ex_style & WS_EX_TOPMOST:
        flags.append("TOPMOST")
    if ex_style & WS_EX_TOOLWINDOW:
        flags.append("TOOLWIN")
    if ex_style & WS_EX_LAYERED:
        flags.append("LAYERED")
    if ex_style & WS_EX_TRANSPARENT:
        flags.append("TRANSPARENT")
    return flags


def is_ad_candidate(class_name: str, width: int, height: int) -> bool:
    """광고 후보 판단"""
    # Check class patterns
    for pattern in AD_CLASS_PATTERNS:
        if pattern in class_name:
            return True
    
    # Check size heuristics (banner-like)
    if width > 200 and 60 <= height <= 200:
        return True
    
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Window Inspection
# ═══════════════════════════════════════════════════════════════════════════════
class WindowInspector:
    def __init__(self, output_format: str = "text"):
        self.output_format = output_format
        self.results: List[Dict] = []
        self.logger = self._setup_logging()
    
    def _setup_logging(self) -> logging.Logger:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"window_inspection_{timestamp}.log"
        
        print(f"로깅 파일: {log_file}")
        
        logger = logging.getLogger("WindowInspector")
        logger.setLevel(logging.DEBUG)
        
        # Avoid adding duplicate handlers
        if not logger.handlers:
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(fh)
        
        return logger
    
    def inspect_all(self):
        """모든 KakaoTalk 관련 윈도우 검사"""
        print("=" * 60)
        print("KakaoTalk Window Inspector v2.0")
        print("=" * 60)
        print("윈도우 검사 시작... 잠시만 기다려주세요.\n")
        
        self.logger.info("=== Window Inspection Start ===")
        self.logger.info(f"Time: {datetime.now()}")
        self.logger.info("")
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        
        def enum_callback(hwnd, _):
            class_name = get_class_name(hwnd)
            title = get_window_text(hwnd)
            
            # Filter for KakaoTalk related windows
            is_kakao = any(p in class_name or p in title for p in KAKAO_PATTERNS)
            is_kakao = is_kakao or "카카오톡" in title or "KakaoTalk" in title
            
            if is_kakao:
                self._inspect_window(hwnd, depth=0)
            
            return True
        
        # Store callback reference to prevent garbage collection during enumeration
        wrapped_callback = WNDENUMPROC(enum_callback)
        user32.EnumWindows(wrapped_callback, 0)
        
        self.logger.info("")
        self.logger.info("=== Window Inspection End ===")
        
        # Summary
        print(f"\n검사 완료. 총 {len(self.results)}개 윈도우 발견.")
        ad_candidates = [r for r in self.results if r.get("is_ad_candidate")]
        if ad_candidates:
            print(f"⚠️  광고 후보: {len(ad_candidates)}개")
            for ad in ad_candidates[:5]:  # Show first 5
                print(f"   - {ad['class']} ({ad['width']}x{ad['height']})")
        
        # Export JSON if requested
        if self.output_format == "json":
            self._export_json()
    
    def _inspect_window(self, hwnd, depth: int):
        """단일 윈도우 검사 (재귀)"""
        class_name = get_class_name(hwnd)
        title = get_window_text(hwnd)
        x, y, w, h = get_window_rect(hwnd)
        style = get_style(hwnd)
        ex_style = get_ex_style(hwnd)
        visible = is_visible(hwnd)
        
        style_flags = decode_style(style)
        ex_style_flags = decode_ex_style(ex_style)
        is_ad = is_ad_candidate(class_name, w, h)
        
        # Build result
        result = {
            "handle": hex(hwnd),
            "class": class_name,
            "title": title[:50] if title else "",
            "x": x, "y": y, "width": w, "height": h,
            "visible": visible,
            "style_flags": style_flags,
            "ex_style_flags": ex_style_flags,
            "is_ad_candidate": is_ad,
            "depth": depth
        }
        self.results.append(result)
        
        # Format output
        indent = "  " * depth
        vis_marker = "V" if visible else "H"
        ad_marker = " ⚠️AD" if is_ad else ""
        
        line = (
            f"{indent}[{hex(hwnd)}] {class_name} "
            f"'{title[:30]}' "
            f"{w}x{h} [{vis_marker}]{ad_marker}"
        )
        
        if style_flags or ex_style_flags:
            all_flags = style_flags + ex_style_flags
            line += f" ({', '.join(all_flags)})"
        
        # Console output (color for ad candidates)
        if is_ad:
            print(f"\033[93m{line}\033[0m")  # Yellow
        else:
            print(line)
        
        self.logger.info(line)
        
        # Enumerate children (direct children only for proper hierarchy)
        children = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        
        def child_callback(child_hwnd, _):
            if get_parent(child_hwnd) == hwnd:
                children.append(child_hwnd)
            return True
        
        # Store callback reference to prevent garbage collection during enumeration
        wrapped_child_callback = WNDENUMPROC(child_callback)
        user32.EnumChildWindows(hwnd, wrapped_child_callback, 0)
        
        for child in children:
            self._inspect_window(child, depth + 1)
    
    def _export_json(self):
        """JSON 형식으로 내보내기"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = f"window_inspection_{timestamp}.json"
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        
        print(f"\nJSON 내보내기: {json_file}")


def main():
    parser = argparse.ArgumentParser(
        description="KakaoTalk Window Inspector - 윈도우 계층 구조 분석 도구"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="JSON 형식으로 내보내기"
    )
    parser.add_argument(
        "--filter", type=str, default="",
        help="클래스명 필터 (예: EVA_)"
    )
    
    args = parser.parse_args()
    
    output_format = "json" if args.json else "text"
    inspector = WindowInspector(output_format)
    inspector.inspect_all()


if __name__ == "__main__":
    main()
