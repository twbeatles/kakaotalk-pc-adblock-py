import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PYTHON = ROOT / "legacy" / "python-v11"
if str(LEGACY_PYTHON) not in sys.path:
    sys.path.insert(0, str(LEGACY_PYTHON))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
