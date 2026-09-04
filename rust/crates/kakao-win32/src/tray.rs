#![cfg(windows)]

use std::mem::size_of;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use windows::core::{w, PCWSTR};
use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Shell::{
    Shell_NotifyIconW, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NOTIFYICONDATAW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, CreatePopupMenu, CreateWindowExW, DefWindowProcW, DestroyMenu, DestroyWindow,
    DispatchMessageW, GetCursorPos, GetMessageW, GetWindowLongPtrW, LoadIconW, PostQuitMessage,
    RegisterClassW, SetForegroundWindow, SetWindowLongPtrW, TrackPopupMenu, TranslateMessage,
    CS_HREDRAW, CS_VREDRAW, GWLP_USERDATA, IDI_APPLICATION, MF_CHECKED, MF_GRAYED, MF_SEPARATOR,
    MF_STRING, MSG, TPM_RIGHTBUTTON, WINDOW_EX_STYLE, WINDOW_STYLE, WM_APP, WM_COMMAND,
    WM_CONTEXTMENU, WM_DESTROY, WM_RBUTTONUP, WNDCLASSW,
};

// MAKEINTRESOURCE(1): first ICON resource embedded by kakao-app/build.rs.
#[allow(clippy::manual_dangling_ptr)]
fn app_icon_resource() -> PCWSTR {
    PCWSTR(1usize as *const u16)
}

const WM_TRAY: u32 = WM_APP + 1;
pub const ID_TOGGLE_ENABLED: u32 = 1001;
pub const ID_TOGGLE_AGGRESSIVE: u32 = 1002;
pub const ID_TOGGLE_STARTUP: u32 = 1003;
pub const ID_RESET_RESTORE: u32 = 1004;
pub const ID_OPEN_LOGS: u32 = 1005;
pub const ID_OPEN_RELEASES: u32 = 1006;
pub const ID_CHECK_UPDATE: u32 = 1007;
pub const ID_EXIT: u32 = 1008;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayCommand {
    ToggleEnabled,
    ToggleAggressive,
    ToggleStartup,
    ResetRestoreFailures,
    OpenLogs,
    OpenReleases,
    CheckUpdate,
    Exit,
}

impl TrayCommand {
    fn from_id(id: u32) -> Option<Self> {
        match id {
            ID_TOGGLE_ENABLED => Some(Self::ToggleEnabled),
            ID_TOGGLE_AGGRESSIVE => Some(Self::ToggleAggressive),
            ID_TOGGLE_STARTUP => Some(Self::ToggleStartup),
            ID_RESET_RESTORE => Some(Self::ResetRestoreFailures),
            ID_OPEN_LOGS => Some(Self::OpenLogs),
            ID_OPEN_RELEASES => Some(Self::OpenReleases),
            ID_CHECK_UPDATE => Some(Self::CheckUpdate),
            ID_EXIT => Some(Self::Exit),
            _ => None,
        }
    }
}

pub struct TrayFlags {
    pub enabled: Arc<AtomicBool>,
    pub aggressive: Arc<AtomicBool>,
    pub startup: Arc<AtomicBool>,
}

struct TrayHost<F>
where
    F: FnMut(TrayCommand),
{
    flags: TrayFlags,
    on_command: F,
    nid: NOTIFYICONDATAW,
}

pub fn run_loop<F>(flags: TrayFlags, on_command: F) -> Result<(), String>
where
    F: FnMut(TrayCommand),
{
    unsafe { run_loop_inner(flags, on_command) }
}

unsafe fn run_loop_inner<F>(flags: TrayFlags, on_command: F) -> Result<(), String>
where
    F: FnMut(TrayCommand),
{
    let instance = GetModuleHandleW(None).map_err(|err| err.to_string())?;
    let icon = load_app_icon(instance.into())?;
    let class = w!("KakaoTalkLayoutAdBlockerTray");
    let wc = WNDCLASSW {
        style: CS_HREDRAW | CS_VREDRAW,
        lpfnWndProc: Some(wnd_proc::<F>),
        hInstance: instance.into(),
        hIcon: icon,
        lpszClassName: class,
        ..Default::default()
    };
    let _ = RegisterClassW(&wc);
    // Note: HWND_MESSAGE creates a message-only window which Shell_NotifyIconW rejects with 0x80004005 (E_FAIL).
    // Shell_NotifyIconW requires a standard top-level window (parent: None) to receive shell callbacks.
    let hwnd = CreateWindowExW(
        WINDOW_EX_STYLE::default(),
        class,
        w!("KakaoTalk Layout AdBlocker"),
        WINDOW_STYLE::default(),
        0,
        0,
        0,
        0,
        None,
        None,
        Some(instance.into()),
        None,
    )
    .map_err(|err| err.to_string())?;
    let mut nid = NOTIFYICONDATAW {
        cbSize: size_of::<NOTIFYICONDATAW>() as u32,
        hWnd: hwnd,
        uID: 1,
        uFlags: NIF_ICON | NIF_MESSAGE | NIF_TIP,
        uCallbackMessage: WM_TRAY,
        hIcon: icon,
        ..Default::default()
    };
    write_tip(&mut nid, "KakaoTalk Layout AdBlocker");
    let mut added = Shell_NotifyIconW(NIM_ADD, &nid).as_bool();
    if !added {
        let _ = Shell_NotifyIconW(NIM_DELETE, &nid);
        std::thread::sleep(std::time::Duration::from_millis(100));
        added = Shell_NotifyIconW(NIM_ADD, &nid).as_bool();
    }
    if !added {
        let err = windows::Win32::Foundation::GetLastError();
        return Err(format!("Shell_NotifyIconW NIM_ADD failed: {err:?}"));
    }

    let mut host = TrayHost {
        flags,
        on_command,
        nid,
    };
    SetWindowLongPtrW(hwnd, GWLP_USERDATA, std::ptr::addr_of_mut!(host) as isize);

    let mut msg = MSG::default();
    while GetMessageW(&mut msg, None, 0, 0).as_bool() {
        let _ = TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    let _ = Shell_NotifyIconW(NIM_DELETE, &host.nid);
    Ok(())
}

unsafe extern "system" fn wnd_proc<F: FnMut(TrayCommand)>(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    let host = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut TrayHost<F>;
    if host.is_null() {
        return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
    }
    match msg {
        WM_TRAY => {
            let event = lparam.0 as u32;
            if event == WM_RBUTTONUP || event == WM_CONTEXTMENU {
                unsafe { show_menu(hwnd, &mut *host) };
            }
            LRESULT(0)
        }
        WM_COMMAND => {
            let id = (wparam.0 as u32) & 0xFFFF;
            if let Some(cmd) = TrayCommand::from_id(id) {
                let exit = cmd == TrayCommand::Exit;
                (unsafe { &mut *host }.on_command)(cmd);
                if exit {
                    unsafe {
                        let _ = DestroyWindow(hwnd);
                    }
                }
            }
            LRESULT(0)
        }
        WM_DESTROY => {
            unsafe {
                let _ = Shell_NotifyIconW(NIM_DELETE, &(*host).nid);
                PostQuitMessage(0);
            }
            LRESULT(0)
        }
        _ => unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
}

unsafe fn show_menu<F: FnMut(TrayCommand)>(hwnd: HWND, host: &mut TrayHost<F>) {
    let Ok(menu) = CreatePopupMenu() else {
        return;
    };
    append(menu, 0, "KakaoTalk Layout AdBlocker", false, false);
    append_sep(menu);
    let enabled = host.flags.enabled.load(Ordering::SeqCst);
    append(
        menu,
        ID_TOGGLE_ENABLED,
        if enabled {
            "차단 끄기"
        } else {
            "차단 켜기"
        },
        false,
        true,
    );
    append(
        menu,
        ID_TOGGLE_AGGRESSIVE,
        "공격 모드",
        host.flags.aggressive.load(Ordering::SeqCst),
        true,
    );
    append(
        menu,
        ID_TOGGLE_STARTUP,
        "시작프로그램 등록",
        host.flags.startup.load(Ordering::SeqCst),
        true,
    );
    append(menu, ID_RESET_RESTORE, "복원 실패 초기화", false, true);
    append_sep(menu);
    append(menu, ID_OPEN_LOGS, "로그 폴더 열기", false, true);
    append(menu, ID_OPEN_RELEASES, "GitHub 릴리스 열기", false, true);
    append(menu, ID_CHECK_UPDATE, "업데이트 확인", false, true);
    append_sep(menu);
    append(menu, ID_EXIT, "종료", false, true);

    let mut pt = POINT::default();
    let _ = GetCursorPos(&mut pt);
    let _ = SetForegroundWindow(hwnd);
    let _ = TrackPopupMenu(menu, TPM_RIGHTBUTTON, pt.x, pt.y, None, hwnd, None);
    let _ = DestroyMenu(menu);
}

fn append(
    menu: windows::Win32::UI::WindowsAndMessaging::HMENU,
    id: u32,
    text: &str,
    checked: bool,
    enabled: bool,
) {
    let mut flags = MF_STRING;
    if checked {
        flags |= MF_CHECKED;
    }
    if !enabled {
        flags |= MF_GRAYED;
    }
    let wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
    let _ = unsafe { AppendMenuW(menu, flags, id as usize, PCWSTR(wide.as_ptr())) };
}

fn append_sep(menu: windows::Win32::UI::WindowsAndMessaging::HMENU) {
    let _ = unsafe { AppendMenuW(menu, MF_SEPARATOR, 0, PCWSTR::null()) };
}

fn load_app_icon(
    instance: windows::Win32::Foundation::HINSTANCE,
) -> Result<windows::Win32::UI::WindowsAndMessaging::HICON, String> {
    unsafe {
        LoadIconW(Some(instance), app_icon_resource())
            .or_else(|_| LoadIconW(None, IDI_APPLICATION))
            .map_err(|err| err.to_string())
    }
}

fn write_tip(nid: &mut NOTIFYICONDATAW, tip: &str) {
    let mut wide: Vec<u16> = tip.encode_utf16().take(127).collect();
    wide.push(0);
    for (i, ch) in wide.iter().enumerate() {
        if i < nid.szTip.len() {
            nid.szTip[i] = *ch;
        }
    }
}

pub fn shell_open(target: &str) -> bool {
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    let wide: Vec<u16> = target.encode_utf16().chain(std::iter::once(0)).collect();
    let result = unsafe {
        windows::Win32::UI::Shell::ShellExecuteW(
            None,
            w!("open"),
            PCWSTR(wide.as_ptr()),
            None,
            None,
            SW_SHOWNORMAL,
        )
    };
    result.0 as usize > 32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn menu_ids_map_to_commands() {
        assert_eq!(
            TrayCommand::from_id(ID_TOGGLE_ENABLED),
            Some(TrayCommand::ToggleEnabled)
        );
        assert_eq!(TrayCommand::from_id(ID_EXIT), Some(TrayCommand::Exit));
        assert_eq!(TrayCommand::from_id(0), None);
    }
}
