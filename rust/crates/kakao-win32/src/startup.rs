#![cfg(windows)]

use windows::core::{w, PCWSTR};
use windows::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_SUCCESS};
use windows::Win32::System::Registry::{
    RegCloseKey, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW, RegSetValueExW, HKEY,
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ, REG_VALUE_TYPE,
};

const RUN_KEY: PCWSTR = w!("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run");
const VALUE_NAME: PCWSTR = w!("KakaoTalkAdBlockerLayout");

pub fn get_run_command() -> Option<String> {
    let mut key = HKEY::default();
    let status = unsafe { RegOpenKeyExW(HKEY_CURRENT_USER, RUN_KEY, Some(0), KEY_READ, &mut key) };
    if status != ERROR_SUCCESS {
        return None;
    }
    let mut data = vec![0u16; 1024];
    let mut size = (data.len() * 2) as u32;
    let mut kind = REG_VALUE_TYPE::default();
    let status = unsafe {
        RegQueryValueExW(
            key,
            VALUE_NAME,
            None,
            Some(&mut kind),
            Some(data.as_mut_ptr().cast()),
            Some(&mut size),
        )
    };
    let _ = unsafe { RegCloseKey(key) };
    if status != ERROR_SUCCESS {
        return None;
    }
    let chars = (size as usize) / 2;
    let end = data[..chars.min(data.len())]
        .iter()
        .position(|ch| *ch == 0)
        .unwrap_or(chars.min(data.len()));
    Some(String::from_utf16_lossy(&data[..end]))
}

pub fn set_run_command(command: &str) -> bool {
    let mut key = HKEY::default();
    let status =
        unsafe { RegOpenKeyExW(HKEY_CURRENT_USER, RUN_KEY, Some(0), KEY_SET_VALUE, &mut key) };
    if status != ERROR_SUCCESS {
        return false;
    }
    let mut wide: Vec<u16> = command.encode_utf16().collect();
    wide.push(0);
    let bytes = unsafe { std::slice::from_raw_parts(wide.as_ptr().cast::<u8>(), wide.len() * 2) };
    let status = unsafe { RegSetValueExW(key, VALUE_NAME, Some(0), REG_SZ, Some(bytes)) };
    let _ = unsafe { RegCloseKey(key) };
    status == ERROR_SUCCESS
}

pub fn delete_run_command() -> bool {
    let mut key = HKEY::default();
    let status =
        unsafe { RegOpenKeyExW(HKEY_CURRENT_USER, RUN_KEY, Some(0), KEY_SET_VALUE, &mut key) };
    if status != ERROR_SUCCESS {
        return false;
    }
    let status = unsafe { RegDeleteValueW(key, VALUE_NAME) };
    let _ = unsafe { RegCloseKey(key) };
    status == ERROR_SUCCESS || status == ERROR_FILE_NOT_FOUND
}
