import ctypes
import ctypes.wintypes
import logging
import sys

# 로깅 설정
logging.basicConfig(filename='window_inspection.log', level=logging.DEBUG, 
                    format='%(message)s', encoding='utf-8', filemode='w')

user32 = ctypes.windll.user32

def inspect_windows():
    print("윈도우 검사 시작... 잠시만 기다려주세요.")
    logging.info("=== Window Inspection Start ===\n")
    
    def enum_cb(hwnd, _):
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, 256)
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        
        if "KakaoTalk" in title.value or "카카오톡" in title.value or \
           class_name.value.startswith("EVA_"):
            
            logging.info(f"═══ Main Window ═══")
            logging.info(f"  Handle: {hwnd}")
            logging.info(f"  Class: {class_name.value}")
            logging.info(f"  Title: {title.value}")
            print(f"발견: {title.value} ({class_name.value})")
            
            # 자식 윈도우 검사 (재귀적)
            inspect_children(hwnd, 1)
            logging.info("")
            
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    
    logging.info("=== Window Inspection End ===")
    print("검사 완료. window_inspection.log 파일이 생성되었습니다.")

def inspect_children(parent, depth):
    children_found = []
    
    def child_cb(hwnd, _):
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, 256)
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        
        visible = user32.IsWindowVisible(hwnd)
        
        children_found.append({
            'hwnd': hwnd,
            'class': class_name.value,
            'title': title.value,
            'size': (width, height),
            'rect': (rect.left, rect.top, rect.right, rect.bottom),
            'visible': visible
        })
        
        return True
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumChildWindows(parent, WNDENUMPROC(child_cb), 0)
    
    indent = "  " * depth
    for child in children_found:
        vis_str = "✓" if child['visible'] else "✗"
        logging.info(f"{indent}├─ [{vis_str}] Class: {child['class']}")
        if child['title']:
            logging.info(f"{indent}│    Title: {child['title']}")
        logging.info(f"{indent}│    Size: {child['size'][0]}x{child['size'][1]}, Handle: {child['hwnd']}")
        logging.info(f"{indent}│    Rect: {child['rect'][0]},{child['rect'][1]}-{child['rect'][2]},{child['rect'][3]}")

if __name__ == "__main__":
    inspect_windows()

