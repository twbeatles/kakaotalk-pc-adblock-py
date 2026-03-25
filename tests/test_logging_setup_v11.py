import logging
from pathlib import Path

from kakao_adblocker import logging_setup


def test_setup_logging_closes_existing_handlers(monkeypatch, tmp_path: Path):
    appdata_root = tmp_path / "Roaming"
    log_path = appdata_root / "KakaoTalkAdBlockerLayout" / "layout_adblock.log"
    monkeypatch.setenv("APPDATA", str(appdata_root))

    logger = logging.getLogger("KakaoTalkLayoutAdBlocker")
    logging_setup._reset_logger_handlers(logger)

    class OldHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.closed_called = False

        def emit(self, record):
            return None

        def close(self):
            self.closed_called = True
            super().close()

    old_handler = OldHandler()
    logger.addHandler(old_handler)

    configured = logging_setup.setup_logging("INFO")

    assert configured is logger
    assert old_handler.closed_called is True
    assert logger.propagate is False
    assert log_path.exists()

    logging_setup._reset_logger_handlers(logger)
