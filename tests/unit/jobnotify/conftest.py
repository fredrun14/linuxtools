"""Fixtures communes aux tests de `jobnotify`."""

from __future__ import annotations

import pytest

from linuxtools.jobnotify import installer as installer_module


@pytest.fixture(autouse=True)
def _non_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le test ne dépend pas de l'uid réel (la CI peut tourner en root)."""
    monkeypatch.setattr(installer_module, "_is_root", lambda: False)
