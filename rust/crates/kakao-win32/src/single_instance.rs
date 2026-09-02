#![cfg(windows)]

use windows::core::w;
use windows::Win32::Foundation::{CloseHandle, GetLastError, HANDLE, WIN32_ERROR};
use windows::Win32::System::Threading::CreateMutexW;

const MUTEX_NAME: windows::core::PCWSTR = w!("Local\\KakaoTalkLayoutAdBlocker_v11");
const ERROR_ALREADY_EXISTS: u32 = 183;

pub struct InstanceMutex {
    handle: HANDLE,
}

impl InstanceMutex {
    pub fn acquire() -> Result<Self, AlreadyRunning> {
        let handle = unsafe { CreateMutexW(None, true, MUTEX_NAME) }.map_err(|_| AlreadyRunning)?;
        if unsafe { GetLastError() } == WIN32_ERROR(ERROR_ALREADY_EXISTS) {
            let _ = unsafe { CloseHandle(handle) };
            return Err(AlreadyRunning);
        }
        Ok(Self { handle })
    }
}

impl Drop for InstanceMutex {
    fn drop(&mut self) {
        let _ = unsafe { CloseHandle(self.handle) };
    }
}

#[derive(Debug)]
pub struct AlreadyRunning;
