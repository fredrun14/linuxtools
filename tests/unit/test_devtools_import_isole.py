"""Le package devtools s'importe sans les extras optionnels (F29)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from linuxtools.devtools.bumper import _tag_tuple

# Importe tous les modules de devtools avec `webapitools` (extra `network`)
# rendu introuvable : `sys.modules[nom] = None` fait lever ImportError.
_SCRIPT = """
import importlib, sys
sys.modules["webapitools"] = None
for nom in ("bumper", "changelog", "cli", "discovery", "lockfile",
            "manifest", "report", "__main__"):
    importlib.import_module("linuxtools.devtools." + nom)
"""


def test_devtools_importable_sans_extra_network() -> None:
    """Tous les modules devtools s'importent sans `webapitools`."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_tag_tuple_tag_valide() -> None:
    """`vX.Y.Z` devient un tuple d'entiers."""
    assert _tag_tuple("v2.11.1") == (2, 11, 1)


@pytest.mark.parametrize(
    "tag", ["2.11.1", "v2.11", "v2.11.1-rc1", "v2.11.1\n", ""]
)
def test_tag_tuple_formes_refusees(tag: str) -> None:
    """Toute forme autre que `vX.Y.Z` strict donne None."""
    assert _tag_tuple(tag) is None


def test_tag_tuple_comparaison_numerique() -> None:
    """La comparaison est numérique, pas lexicale."""
    assert _tag_tuple("v2.10.0") > _tag_tuple("v2.9.9")  # type: ignore[operator]
