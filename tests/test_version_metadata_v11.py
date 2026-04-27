import re
from pathlib import Path

from kakao_adblocker.config import VERSION


def test_windows_version_resource_matches_package_version():
    version_info = Path("packaging/windows_version_info.txt").read_text(encoding="utf-8")
    parts = [int(part) for part in VERSION.split(".")]
    assert len(parts) == 3
    tuple_text = f"({parts[0]}, {parts[1]}, {parts[2]}, 0)"
    resource_version = f"{VERSION}.0"

    assert f"filevers={tuple_text}" in version_info
    assert f"prodvers={tuple_text}" in version_info
    assert re.search(rf'StringStruct\(u"FileVersion", u"{re.escape(resource_version)}"\)', version_info)
    assert re.search(rf'StringStruct\(u"ProductVersion", u"{re.escape(resource_version)}"\)', version_info)
