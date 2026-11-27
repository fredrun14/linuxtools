"""Le wheel livre ``runtime.py`` comme ressource lue par l'installeur (T6)."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

import linuxtools.jobnotify.runtime as runtime_module

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_IN_WHEEL = "linuxtools/jobnotify/runtime.py"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv introuvable")
def test_wheel_construit_contient_runtime_identique_a_la_source(
    tmp_path: Path,
) -> None:
    """Un vrai build place ``runtime.py`` dans le wheel, octet pour octet."""
    out_dir = tmp_path / "dist"

    subprocess.run(  # noqa: S603 - argv fixe, dossier temporaire du test
        [str(shutil.which("uv")), "build", "--wheel", "--out-dir", str(out_dir)],
        cwd=_ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        check=True,
    )

    (wheel,) = out_dir.glob("linuxtools-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        assert (
            archive.read(_RUNTIME_IN_WHEEL)
            == Path(runtime_module.__file__).read_bytes()
        )
