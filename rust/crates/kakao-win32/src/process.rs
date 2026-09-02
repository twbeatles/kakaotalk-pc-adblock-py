#![cfg(windows)]

use std::collections::HashSet;

use windows::Win32::Foundation::CloseHandle;
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W, TH32CS_SNAPPROCESS,
};

pub fn kakaotalk_pids() -> HashSet<i64> {
    process_ids("kakaotalk.exe")
}

pub fn process_ids(image_name: &str) -> HashSet<i64> {
    let mut pids = HashSet::new();
    let normalized = image_name.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return pids;
    }
    let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
    let Ok(snapshot) = snapshot else {
        return pids;
    };
    let mut entry = PROCESSENTRY32W {
        dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
        ..Default::default()
    };
    let mut ok = unsafe { Process32FirstW(snapshot, &mut entry) }.is_ok();
    while ok {
        let name = decode_wide(&entry.szExeFile);
        if name.eq_ignore_ascii_case(&normalized) {
            pids.insert(i64::from(entry.th32ProcessID));
        }
        ok = unsafe { Process32NextW(snapshot, &mut entry) }.is_ok();
    }
    let _ = unsafe { CloseHandle(snapshot) };
    pids
}

fn decode_wide(buf: &[u16]) -> String {
    let end = buf.iter().position(|ch| *ch == 0).unwrap_or(buf.len());
    String::from_utf16_lossy(&buf[..end])
}
