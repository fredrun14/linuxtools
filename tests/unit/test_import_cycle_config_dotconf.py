"""Le cycle d'import config ⇄ dotconf ne casse aucun ordre d'import."""

from __future__ import annotations

import subprocess
import sys

import pytest

_ORDRES = [
    ("linuxtools.config.manager", "linuxtools.dotconf"),
    ("linuxtools.dotconf", "linuxtools.config.manager"),
    ("linuxtools.config", "linuxtools.dotconf"),
    ("linuxtools.dotconf", "linuxtools.config"),
]


@pytest.mark.parametrize(("premier", "second"), _ORDRES)
def test_config_et_dotconf_importables_dans_les_deux_ordres(
    premier: str, second: str
) -> None:
    """Chaque ordre d'import, en interpréteur neuf, se termine sans ImportError."""
    script = f"import importlib\nimportlib.import_module({premier!r})\n"
    script += f"importlib.import_module({second!r})\n"

    # args construits par le test, sans entrée externe
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
