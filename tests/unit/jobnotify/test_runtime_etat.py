"""Tests de l'écriture de l'état du runtime."""

import json
from pathlib import Path

import pytest

from linuxtools.jobnotify.runtime import (
    start,
)
from tests.unit.jobnotify.runtime_support import (
    ALICE_PROPS,
    BOOT_A,
    STATE_RELATIVE,
    FakeRunner,
    Recorder,
    ctx_for,
    notify_calls,
    read_state_file,
    system_handler,
    write_boot_id,
)


@pytest.mark.parametrize(
    "lien",
    ["var/lib/fedora-post-install/dnf5-auto", "var/lib"],
    ids=["dossier_d_etat", "parent"],
)
def test_etat_lien_symbolique_refuse_ecriture(tmp_path: Path, lien: str) -> None:
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    link = tmp_path / lien
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(ailleurs)
    write_boot_id(tmp_path, BOOT_A)
    recorder = Recorder()
    runner = FakeRunner(system_handler(sessions={"1": ALICE_PROPS}))

    start(ctx_for(runner, tmp_path, recorder, euid=0))

    assert list(ailleurs.rglob("*")) == []
    assert any("lien symbolique" in m for m in recorder.messages)
    assert len(notify_calls(runner)) == 1  # l'échec d'écriture n'empêche pas l'envoi


def test_etat_dossier_d_etat_qui_est_un_fichier_refuse(tmp_path: Path) -> None:
    cible = tmp_path / STATE_RELATIVE.parent
    cible.parent.mkdir(parents=True)
    cible.write_text("je ne suis pas un dossier")
    write_boot_id(tmp_path, BOOT_A)
    recorder = Recorder()

    start(ctx_for(FakeRunner(system_handler()), tmp_path, recorder, euid=0))

    assert any("pas un dossier" in m for m in recorder.messages)


def test_etat_ecrit_par_fichier_temporaire_puis_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_boot_id(tmp_path, BOOT_A)
    replaced: list[tuple[Path, Path, str]] = []
    real_replace = Path.replace

    def spy(self: Path, target: Path) -> Path:
        replaced.append((self, Path(target), self.read_text()))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)

    start(ctx_for(FakeRunner(system_handler()), tmp_path, Recorder(), euid=0))

    final = tmp_path / STATE_RELATIVE
    state_moves = [m for m in replaced if m[1] == final]
    assert len(state_moves) == 1
    source, _, content = state_moves[0]
    assert source != final
    assert source.parent == final.parent
    assert json.loads(content)["status"] == "running"
    assert not source.exists()
    assert [p.name for p in final.parent.iterdir()] == ["state.json"]


def test_etat_echec_du_replace_ne_laisse_pas_de_fichier_temporaire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_boot_id(tmp_path, BOOT_A)

    def replace_en_echec(self: Path, target: Path) -> Path:
        raise OSError("disque plein")

    monkeypatch.setattr(Path, "replace", replace_en_echec)
    recorder = Recorder()

    start(ctx_for(FakeRunner(system_handler()), tmp_path, recorder, euid=0))

    assert list((tmp_path / STATE_RELATIVE).parent.iterdir()) == []
    assert any("disque plein" in m for m in recorder.messages)


def test_etat_remplace_un_lien_symbolique_sans_ecrire_la_cible(
    tmp_path: Path,
) -> None:
    victime = tmp_path / "victime"
    victime.write_text("intact")
    lien = tmp_path / STATE_RELATIVE
    lien.parent.mkdir(parents=True)
    lien.symlink_to(victime)
    write_boot_id(tmp_path, BOOT_A)

    start(ctx_for(FakeRunner(system_handler()), tmp_path, Recorder(), euid=0))

    assert victime.read_text() == "intact"
    assert not lien.is_symlink()
    assert read_state_file(tmp_path)["status"] == "running"
