"""Test d'intégration filesystem réel pour VenvReleaser (T11).

Valide sur le système de fichiers réel (via LinuxCommandExecutor,
sans mock) les hypothèses de la conception qu'un exécuteur mocké ne
peut pas vérifier :
    - `python3 -m venv --without-pip` (rapide, sans réseau) suffit à
      produire un venv activable ;
    - la migration d'un `venv_path` répertoire réel vers un lien
      fonctionne réellement (deux `rename(2)`) ;
    - `sys.prefix`, vu depuis `<venv_path>/bin/python`, résout vers
      `venv_path` et non vers la cible réelle du lien (cohérence
      legacy — conception §2) ;
    - `find -mindepth 1 -maxdepth 1 -type d -printf '%f\\n'` et
      `rm -rf` se comportent comme attendu sur ce système (GNU
      findutils/coreutils).

Écrit après T5/T6 (VenvReleaser stabilisé), sans TDD : test
d'intégration système, pas un cycle red-green sur du comportement
nouveau.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.venv_release import _MIGRATE_SCRIPT, VenvReleaser

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration


def _build_bare_venv(path: Path) -> None:
    """Construit un venv minimal (sans pip) directement à `path`.

    Args:
        path: Emplacement définitif du venv (un venv n'est pas
            relocalisable : shebangs absolus).
    """
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


class _BareVenvInstaller(VenvInstaller):
    """VenvInstaller de test : construit un venv nu, sans pip install.

    Évite toute dépendance réseau/pip dans les tests d'intégration
    filesystem (F01/T3) : seule la mécanique de VenvReleaser (bascule,
    horodatage, rétention) est sous test, pas VenvInstaller.
    """

    def install(
        self,
        venv_path: Path,
        source_dir: Path,
        recreate: bool = False,
    ) -> CommandResult:
        """Construit un venv nu à `venv_path` (ignore `source_dir`)."""
        _build_bare_venv(venv_path)
        return CommandResult(
            command=(),
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            duration=0.0,
        )


@pytest.fixture
def releaser() -> VenvReleaser:
    """VenvReleaser réel, sur un LinuxCommandExecutor réel."""
    executor = LinuxCommandExecutor()
    installer = VenvInstaller(executor)
    return VenvReleaser(executor, installer)


@pytest.fixture
def bare_releaser() -> VenvReleaser:
    """VenvReleaser réel, avec un installer qui ne fait pas de pip
    install (F01/T3) : ces tests exercent release() de bout en bout
    (bascule, horodatage, rétention) avec une horloge réelle qui
    avance entre chaque appel — jamais figée, sous peine de masquer
    la course d'origine (F01) — sans dépendance réseau/pip."""
    executor = LinuxCommandExecutor()
    installer = _BareVenvInstaller(executor)
    return VenvReleaser(executor, installer)


class TestVenvReleaserActivateFilesystemReel:
    """activate() sur un vrai système de fichiers."""

    def test_migration_puis_bascule_puis_sys_prefix(
        self, tmp_path: Path, releaser: VenvReleaser
    ) -> None:
        """Migration d'un répertoire réel, puis bascule normale, en
        vérifiant à chaque étape l'état réel du filesystem et la
        résolution de sys.prefix (hypothèse conception §7)."""
        root = tmp_path / "app"
        root.mkdir()
        venv_path = root / "venv"
        versions_dir = root / "venvs"
        versions_dir.mkdir()

        # État initial : venv_path est un répertoire réel (comme sur
        # tous les hôtes avant le premier déploiement atomic_swap).
        _build_bare_venv(venv_path)

        version1 = versions_dir / "venv-20260901-000000-000000"
        _build_bare_venv(version1)

        # --- Migration ---
        legacy = releaser.activate(venv_path, version1)

        assert venv_path.is_symlink()
        assert venv_path.resolve() == version1
        assert legacy is not None
        assert legacy.is_dir()
        assert not legacy.is_symlink()
        # Le répertoire migré contient bien l'ancien venv (pas vide).
        assert (legacy / "pyvenv.cfg").exists()

        # sys.prefix résout vers venv_path (le lien), pas vers
        # version1 : Python repère pyvenv.cfg sans résoudre le lien.
        result = subprocess.run(
            [
                str(venv_path / "bin" / "python"),
                "-c",
                "import sys; print(sys.prefix)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == str(venv_path)

        # --- Bascule normale (lien -> lien) ---
        version2 = versions_dir / "venv-20260910-000000-000000"
        _build_bare_venv(version2)

        previous = releaser.activate(venv_path, version2)

        assert previous == version1
        assert venv_path.is_symlink()
        assert venv_path.resolve() == version2

    def test_purge_reelle_conserve_keep_versions(
        self, tmp_path: Path, releaser: VenvReleaser
    ) -> None:
        """La purge (find + rm -rf réels) conserve keep_versions
        versions, la plus ancienne est supprimée du disque."""
        root = tmp_path / "app"
        root.mkdir()
        venv_path = root / "venv"
        versions_dir = root / "venvs"
        versions_dir.mkdir()

        version1 = versions_dir / "venv-20260901-000000-000000"
        version2 = versions_dir / "venv-20260910-000000-000000"
        version3 = versions_dir / "venv-20260920-000000-000000"
        for version in (version1, version2, version3):
            _build_bare_venv(version)

        # venv_path pointe déjà sur version2 (previous), on bascule
        # sur version3 puis on purge avec keep=2.
        releaser.activate(venv_path, version2)
        releaser.activate(venv_path, version3)

        messages = releaser._prune(  # noqa: SLF001 - test d'intégration ciblé
            venv_path, version3, version2, keep_versions=2
        )

        assert messages == ()
        assert not version1.exists()
        assert version2.exists()
        assert version3.exists()


class TestVenvReleaserReleaseFilesystemReelF01:
    """release() de bout en bout, horloge réelle (F01, T3).

    Reproduit le scénario ayant motivé le No-Go de la revue : ces
    tests auraient échoué avec le code d'avant T1/T2 (previous_id
    purgé hors fenêtre, legacy horodaté après la nouvelle version).
    """

    def test_releases_successifs_horloge_reelle_protegent_le_repli(
        self, tmp_path: Path, bare_releaser: VenvReleaser
    ) -> None:
        """Migration puis 2 release() successifs, horloge réelle (pas
        figée) : après chaque release(), le fallback_version annoncé
        existe toujours sur le disque (F01 : avant correction, le
        legacy migré triait après la nouvelle version et se faisait
        purger comme si c'était la plus ancienne)."""
        root = tmp_path / "app"
        root.mkdir()
        venv_path = root / "venv"
        source_dir = tmp_path / "src"  # ignoré par _BareVenvInstaller

        # État initial : venv_path est un répertoire réel (migration).
        _build_bare_venv(venv_path)

        verify = MagicMock(return_value=())

        outcome1 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        assert outcome1.success is True
        assert outcome1.fallback_version is not None
        assert outcome1.fallback_version.exists(), (
            "legacy purgé à tort dès la 1re release (F01)"
        )

        outcome2 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        assert outcome2.success is True
        assert outcome2.fallback_version is not None
        assert outcome2.fallback_version.exists(), (
            "fallback_version purgé après le 2e release() (F01)"
        )
        assert outcome2.fallback_version == outcome1.active_version

        outcome3 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        assert outcome3.success is True
        assert outcome3.fallback_version is not None
        assert outcome3.fallback_version.exists(), (
            "fallback_version purgé après le 3e release() (F01)"
        )
        assert outcome3.fallback_version == outcome2.active_version

    def test_rollback_puis_release_protege_la_cible_du_rollback(
        self, tmp_path: Path, bare_releaser: VenvReleaser
    ) -> None:
        """Après migration + release(), un rollback (activate direct
        vers une version chronologiquement plus ancienne) puis un
        nouveau release() : la version vers laquelle on avait
        rebasculé (nouveau previous_id) n'est pas purgée, même si elle
        n'est plus la plus récente chronologiquement parmi les
        versions restantes (F01/F02)."""
        root = tmp_path / "app"
        root.mkdir()
        venv_path = root / "venv"
        source_dir = tmp_path / "src"  # ignoré par _BareVenvInstaller
        _build_bare_venv(venv_path)

        verify = MagicMock(return_value=())

        outcome1 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        version1 = outcome1.active_version
        assert version1 is not None

        outcome2 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        version2 = outcome2.active_version
        assert version2 is not None
        assert version1.exists()
        assert version2.exists()

        # --- Rollback direct vers version1 (chronologiquement plus
        # ancienne que version2) ---
        bare_releaser.activate(venv_path, version1)
        assert venv_path.resolve() == version1

        outcome3 = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )
        assert outcome3.success is True
        # previous_id de ce 3e release() est version1 (cible du
        # rollback) : protégé bien qu'antérieur chronologiquement à
        # version2, qui lui n'est plus protégée et peut être purgée.
        assert outcome3.fallback_version == version1
        assert version1.exists(), (
            "version1 (cible du rollback) purgée à tort (F01/F02)"
        )


class TestVenvReleaserRollbackFilesystemReel:
    """Rollback après migration, sur système de fichiers réel (F14).

    Rejoue le critère d'acceptation CDC §8 (« le rollback rebascule le
    lien vers la version précédente sans copie ») que la régression
    F12/F14 de la passe 2 cassait : un `activate()` vers
    `fallback_version` (toujours un id `-legacy` après migration) doit
    réussir."""

    def test_migration_puis_rollback_vers_fallback_version(
        self, tmp_path: Path, bare_releaser: VenvReleaser
    ) -> None:
        """release() déclenche une migration (venv_path répertoire
        réel), puis activate(venv_path, outcome.fallback_version)
        (rollback documenté) réussit et le lien pointe sur le legacy."""
        root = tmp_path / "app"
        root.mkdir()
        venv_path = root / "venv"
        source_dir = tmp_path / "src"  # ignoré par _BareVenvInstaller

        # État initial : venv_path est un répertoire réel (migration).
        _build_bare_venv(venv_path)

        verify = MagicMock(return_value=())

        outcome = bare_releaser.release(
            venv_path, source_dir, verify, keep_versions=2
        )

        assert outcome.success is True
        assert outcome.fallback_version is not None
        assert outcome.fallback_version.name.endswith("-legacy")

        # --- Rollback documenté vers la version de repli ---
        previous = bare_releaser.activate(venv_path, outcome.fallback_version)

        assert previous == outcome.active_version
        assert venv_path.is_symlink()
        assert venv_path.resolve() == outcome.fallback_version


class TestMigrateScriptCompensation:
    """Exécution réelle de `_MIGRATE_SCRIPT` (le script constant).

    Ce script tourne sur l'hôte distant (jamais dans le process de
    test) : un exécuteur mocké ne peut pas vérifier sa logique de
    compensation. Seule une exécution réelle du script le peut
    (mutation contrôlée : sans compensation, `venv_path` resterait
    absent après un second rename raté)."""

    def test_second_rename_echoue_restaure_venv_path(
        self, tmp_path: Path
    ) -> None:
        """Si `os.rename(tmp, venv)` échoue, le script remet `legacy`
        à la place de `venv` avant de sortir en erreur : `venv_path`
        n'est jamais laissé absent."""
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "marker").write_text("original")
        legacy = tmp_path / "venv-legacy"
        # tmp n'existe pas : le second os.rename(tmp, venv) échoue
        # avec FileNotFoundError (sous-classe d'OSError).
        tmp = tmp_path / "does-not-exist"

        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                _MIGRATE_SCRIPT,
                str(venv),
                str(legacy),
                str(tmp),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert venv.exists()
        assert (venv / "marker").read_text() == "original"
        assert not legacy.exists()
