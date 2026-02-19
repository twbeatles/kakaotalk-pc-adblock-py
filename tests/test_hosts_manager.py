import importlib.util
import logging
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "카카오톡 광고제거 v10.0.py"
    spec = importlib.util.spec_from_file_location("kakao_adblock", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hosts_block_unblock_idempotent_and_preserve_crlf(tmp_path: Path):
    m = load_module()

    # Keep backups inside the test temp dir.
    m.APPDATA_DIR = str(tmp_path)

    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    hosts_path = tmp_path / "hosts"
    start = m.HostsManager.START
    end = m.HostsManager.END

    original = (
        "127.0.0.1 localhost\r\n"
        "# custom line\r\n"
        f"{start}\r\n"
        "0.0.0.0 old.example\r\n"
        f"{end}\r\n"
        "# tail\r\n"
    )
    hosts_path.write_text(original, encoding="utf-8", newline="\n")

    hm = m.HostsManager(logger, hosts_path=str(hosts_path))

    ok = hm.block(["Example.COM", "example.com", "bad domain", "test.com"])
    assert ok is True

    data = hosts_path.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")  # no lone LF
    text = data.decode("utf-8", errors="replace")

    assert "# custom line" in text
    assert "# tail" in text
    assert text.count(start) == 1
    assert text.count(end) == 1
    assert "0.0.0.0 example.com" in text
    assert "0.0.0.0 test.com" in text
    assert "bad domain" not in text

    # Idempotent: running again shouldn't create duplicate blocks.
    ok2 = hm.block(["example.com", "test.com"])
    assert ok2 is True
    text2 = hosts_path.read_text(encoding="utf-8", errors="replace")
    assert text2.count(start) == 1
    assert text2.count(end) == 1

    ok3 = hm.unblock()
    assert ok3 is True
    after = hosts_path.read_text(encoding="utf-8", errors="replace")
    assert start not in after
    assert end not in after
    assert "# custom line" in after
    assert "# tail" in after


def test_hosts_malformed_marker_block_fails_safe_without_changes(tmp_path: Path):
    m = load_module()

    m.APPDATA_DIR = str(tmp_path)
    logger = logging.getLogger("test")
    logger.addHandler(logging.NullHandler())

    hosts_path = tmp_path / "hosts"
    start = m.HostsManager.START
    malformed = (
        "127.0.0.1 localhost\r\n"
        f"{start}\r\n"
        "0.0.0.0 ad.example\r\n"
        "# END marker intentionally missing\r\n"
    )
    hosts_path.write_text(malformed, encoding="utf-8", newline="\n")
    before_bytes = hosts_path.read_bytes()

    hm = m.HostsManager(logger, hosts_path=str(hosts_path))

    assert hm.block(["example.com"]) is False
    assert hosts_path.read_bytes() == before_bytes

    assert hm.unblock() is False
    assert hosts_path.read_bytes() == before_bytes
