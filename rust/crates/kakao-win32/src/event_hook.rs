#![cfg(windows)]

use std::sync::OnceLock;
use std::time::Duration;

use crossbeam_channel::{Receiver, Sender, TryRecvError};
use windows::Win32::Foundation::HWND;
use windows::Win32::UI::Accessibility::{SetWinEventHook, UnhookWinEvent, HWINEVENTHOOK};
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, MsgWaitForMultipleObjects, PeekMessageW, TranslateMessage,
    EVENT_OBJECT_CREATE, EVENT_OBJECT_DESTROY, EVENT_OBJECT_HIDE, EVENT_OBJECT_LOCATIONCHANGE,
    EVENT_OBJECT_NAMECHANGE, EVENT_OBJECT_SHOW, EVENT_SYSTEM_FOREGROUND, MSG, PM_REMOVE,
    QS_ALLINPUT, WINEVENT_OUTOFCONTEXT, WM_QUIT,
};

const OBJID_WINDOW: i32 = 0;
const CHILDID_SELF: i32 = 0;

#[derive(Debug, Clone, Copy)]
pub struct WinEvent {
    pub hwnd: i64,
    pub event: u32,
    pub time: u32,
}

static EVENT_TX: OnceLock<Sender<WinEvent>> = OnceLock::new();

unsafe extern "system" fn hook_proc(
    _hook: HWINEVENTHOOK,
    event: u32,
    hwnd: HWND,
    id_object: i32,
    id_child: i32,
    _thread: u32,
    time: u32,
) {
    if hwnd.0.is_null() || id_object != OBJID_WINDOW || id_child != CHILDID_SELF {
        return;
    }
    if let Some(tx) = EVENT_TX.get() {
        let _ = tx.try_send(WinEvent {
            hwnd: hwnd.0 as isize as i64,
            event,
            time,
        });
    }
}

pub struct EventHook {
    hooks: Vec<HWINEVENTHOOK>,
    rx: Receiver<WinEvent>,
}

impl EventHook {
    pub fn install() -> Option<Self> {
        let (tx, rx) = crossbeam_channel::bounded(1024);
        let _ = EVENT_TX.set(tx);
        let ranges = [
            (EVENT_OBJECT_CREATE, EVENT_OBJECT_NAMECHANGE),
            (EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
        ];
        let mut hooks = Vec::new();
        for (min, max) in ranges {
            let hook = unsafe {
                SetWinEventHook(min, max, None, Some(hook_proc), 0, 0, WINEVENT_OUTOFCONTEXT)
            };
            if hook.0.is_null() {
                for installed in &hooks {
                    unsafe {
                        let _ = UnhookWinEvent(*installed);
                    }
                }
                return None;
            }
            hooks.push(hook);
        }
        Some(Self { hooks, rx })
    }

    pub fn try_recv(&self) -> Result<WinEvent, TryRecvError> {
        self.rx.try_recv()
    }

    pub fn drain(&self) -> Vec<WinEvent> {
        let mut events = Vec::new();
        while let Ok(event) = self.rx.try_recv() {
            events.push(event);
        }
        events
    }

    pub fn wait_message(&self, timeout: Duration) {
        unsafe {
            MsgWaitForMultipleObjects(None, false, timeout.as_millis() as u32, QS_ALLINPUT);
            let mut msg = MSG::default();
            while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
                if msg.message == WM_QUIT {
                    break;
                }
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }
    }
}

impl Drop for EventHook {
    fn drop(&mut self) {
        for hook in self.hooks.drain(..) {
            unsafe {
                let _ = UnhookWinEvent(hook);
            }
        }
    }
}

pub fn post_quit() {
    unsafe {
        windows::Win32::UI::WindowsAndMessaging::PostQuitMessage(0);
    }
}

pub const EVENT_CREATE: u32 = EVENT_OBJECT_CREATE;
pub const EVENT_DESTROY: u32 = EVENT_OBJECT_DESTROY;
pub const EVENT_SHOW: u32 = EVENT_OBJECT_SHOW;
pub const EVENT_HIDE: u32 = EVENT_OBJECT_HIDE;
pub const EVENT_LOCATION: u32 = EVENT_OBJECT_LOCATIONCHANGE;
pub const EVENT_NAME: u32 = EVENT_OBJECT_NAMECHANGE;
pub const EVENT_FOREGROUND: u32 = EVENT_SYSTEM_FOREGROUND;
