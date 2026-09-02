use std::io::Read;
use std::time::{SystemTime, UNIX_EPOCH};

use base64::Engine as _;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde_json::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::config::{UPDATE_PUBLIC_KEY_B64, VERSION};

pub const MANIFEST_URL: &str =
    "https://github.com/twbeatles/kakaotalk-pc-adblock-py/releases/latest/download/update.json";
pub const USER_AGENT: &str = "KakaoTalkLayoutAdBlocker-Updater";
pub const RELEASE_DOWNLOAD_PREFIX: &str =
    "https://github.com/twbeatles/kakaotalk-pc-adblock-py/releases/download/";
const MAX_MANIFEST_BYTES: usize = 64 * 1024;
const MAX_ARTIFACT_BYTES: u64 = 512 * 1024 * 1024;

#[derive(Debug, Error)]
pub enum UpdateError {
    #[error("{0}")]
    Message(String),
    #[error("현재 최신 버전을 사용 중입니다.")]
    NoUpdate,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateManifest {
    pub version: String,
    pub tag: String,
    pub artifact_url: String,
    pub sha256: String,
    pub size: u64,
}

pub fn version_tuple(value: &str) -> Result<Vec<u32>, UpdateError> {
    let parts: Vec<&str> = value.trim().split('.').collect();
    if parts.is_empty()
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.chars().all(|c| c.is_ascii_digit()))
    {
        return Err(UpdateError::Message(format!(
            "Invalid update version: {value}"
        )));
    }
    Ok(parts.iter().map(|part| part.parse().unwrap_or(0)).collect())
}

pub fn is_newer(candidate: &str, current: &str) -> Result<bool, UpdateError> {
    let mut left = version_tuple(candidate)?;
    let mut right = version_tuple(current)?;
    let width = left.len().max(right.len());
    left.resize(width, 0);
    right.resize(width, 0);
    Ok(left > right)
}

pub fn canonical_payload(payload: &Value) -> Result<Vec<u8>, UpdateError> {
    serde_json::to_vec(payload).map_err(|err| UpdateError::Message(err.to_string()))
}

/// Match Python json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))
pub fn canonical_payload_python(payload: &Value) -> Result<Vec<u8>, UpdateError> {
    let dumped = pythonish_dumps(payload);
    Ok(dumped.into_bytes())
}

fn pythonish_dumps(value: &Value) -> String {
    match value {
        Value::Null => "null".into(),
        Value::Bool(true) => "true".into(),
        Value::Bool(false) => "false".into(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => format!("\"{}\"", escape_json_string(s)),
        Value::Array(items) => {
            let inner: Vec<String> = items.iter().map(pythonish_dumps).collect();
            format!("[{}]", inner.join(","))
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let inner: Vec<String> = keys
                .into_iter()
                .map(|k| format!("\"{}\":{}", escape_json_string(k), pythonish_dumps(&map[k])))
                .collect();
            format!("{{{}}}", inner.join(","))
        }
    }
}

fn escape_json_string(input: &str) -> String {
    let mut out = String::new();
    for ch in input.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

pub fn expected_artifact_url(tag: &str) -> String {
    format!("{RELEASE_DOWNLOAD_PREFIX}{tag}/KakaoTalkLayoutAdBlocker_v11.exe")
}

pub fn parse_and_verify_manifest(
    document: &[u8],
    current_version: &str,
) -> Result<UpdateManifest, UpdateError> {
    if document.len() > MAX_MANIFEST_BYTES {
        return Err(UpdateError::Message(
            "업데이트 매니페스트가 올바르지 않습니다.".into(),
        ));
    }
    let parsed: Value = serde_json::from_slice(document)
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let payload = parsed.get("payload").cloned().ok_or_else(|| {
        UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into())
    })?;
    let signature_b64 = parsed
        .get("signature")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into())
        })?;
    let signature = base64::engine::general_purpose::STANDARD
        .decode(signature_b64)
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let public = base64::engine::general_purpose::STANDARD
        .decode(UPDATE_PUBLIC_KEY_B64)
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let key_bytes: [u8; 32] = public
        .as_slice()
        .try_into()
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let key = VerifyingKey::from_bytes(&key_bytes)
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let sig_bytes: [u8; 64] = signature
        .as_slice()
        .try_into()
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;
    let sig = Signature::from_bytes(&sig_bytes);
    let canonical = canonical_payload_python(&payload)?;
    key.verify(&canonical, &sig)
        .map_err(|_| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?;

    let version = payload
        .get("version")
        .and_then(Value::as_str)
        .ok_or_else(|| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?
        .to_string();
    let tag = payload
        .get("tag")
        .and_then(Value::as_str)
        .ok_or_else(|| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?
        .to_string();
    let artifact_url = payload
        .get("artifact_url")
        .and_then(Value::as_str)
        .ok_or_else(|| UpdateError::Message("업데이트 서명 또는 형식 검증에 실패했습니다.".into()))?
        .to_string();
    let sha256 = payload
        .get("sha256")
        .and_then(Value::as_str)
        .ok_or_else(|| UpdateError::Message("업데이트 파일 정보가 올바르지 않습니다.".into()))?
        .to_lowercase();
    let size = payload
        .get("size")
        .and_then(Value::as_u64)
        .ok_or_else(|| UpdateError::Message("업데이트 파일 정보가 올바르지 않습니다.".into()))?;
    if !tag.starts_with('v') || tag[1..] != version {
        return Err(UpdateError::Message(
            "업데이트 태그 정보가 올바르지 않습니다.".into(),
        ));
    }
    if artifact_url != expected_artifact_url(&tag) || !artifact_url.starts_with("https://") {
        return Err(UpdateError::Message(
            "업데이트 파일 위치가 올바르지 않습니다.".into(),
        ));
    }
    if sha256.len() != 64 || !sha256.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(UpdateError::Message(
            "업데이트 파일 정보가 올바르지 않습니다.".into(),
        ));
    }
    if size == 0 || size > MAX_ARTIFACT_BYTES {
        return Err(UpdateError::Message(
            "업데이트 파일 크기가 허용 범위를 벗어났습니다.".into(),
        ));
    }
    if !is_newer(&version, current_version)? {
        return Err(UpdateError::NoUpdate);
    }
    Ok(UpdateManifest {
        version,
        tag,
        artifact_url,
        sha256,
        size,
    })
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

pub fn download_and_verify(
    manifest: &UpdateManifest,
    dest: &std::path::Path,
) -> Result<(), UpdateError> {
    let response = ureq::get(&manifest.artifact_url)
        .set("User-Agent", USER_AGENT)
        .call()
        .map_err(|err| UpdateError::Message(format!("업데이트 다운로드 실패: {err}")))?;
    let mut bytes = Vec::new();
    response
        .into_reader()
        .take(manifest.size.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|err| UpdateError::Message(format!("업데이트 다운로드 실패: {err}")))?;
    if bytes.len() as u64 != manifest.size {
        return Err(UpdateError::Message(
            "업데이트 파일 크기가 허용 범위를 벗어났습니다.".into(),
        ));
    }
    if sha256_hex(&bytes) != manifest.sha256 {
        return Err(UpdateError::Message(
            "업데이트 파일 해시가 일치하지 않습니다.".into(),
        ));
    }
    std::fs::write(dest, bytes)
        .map_err(|err| UpdateError::Message(format!("업데이트 저장 실패: {err}")))?;
    Ok(())
}

pub fn check_for_update() -> Result<UpdateManifest, UpdateError> {
    let body = ureq::get(MANIFEST_URL)
        .set("User-Agent", USER_AGENT)
        .call()
        .map_err(|err| UpdateError::Message(format!("업데이트 정보 다운로드 실패: {err}")))?
        .into_string()
        .map_err(|err| UpdateError::Message(format!("업데이트 정보 다운로드 실패: {err}")))?;
    parse_and_verify_manifest(body.as_bytes(), VERSION)
}

pub fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn newer_version_compares_componentwise() {
        assert!(is_newer("11.0.2", "11.0.1").unwrap());
        assert!(!is_newer("11.0.1", "11.0.1").unwrap());
        assert!(!is_newer("10.9.9", "11.0.1").unwrap());
    }

    #[test]
    fn canonical_payload_sorts_keys() {
        let payload = json!({"b": 1, "a": "카카오"});
        assert_eq!(
            String::from_utf8(canonical_payload_python(&payload).unwrap()).unwrap(),
            "{\"a\":\"카카오\",\"b\":1}"
        );
    }

    #[test]
    fn artifact_url_is_pinned() {
        assert_eq!(
            expected_artifact_url("v11.0.2"),
            "https://github.com/twbeatles/kakaotalk-pc-adblock-py/releases/download/v11.0.2/KakaoTalkLayoutAdBlocker_v11.exe"
        );
    }
}
