from __future__ import annotations

from typing import Optional, Set, Tuple


class UIAAdBlocker:
    """Deprecated in v11. Kept as a no-op compatibility shim."""

    def __init__(self, *_args, **_kwargs):
        pass

    def scan(self, _kakao_pid: Optional[int]) -> Tuple[int, Set[int]]:
        return 0, set()


__all__ = ["UIAAdBlocker"]
