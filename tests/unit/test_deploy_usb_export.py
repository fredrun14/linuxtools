"""Tests pour le module deploy.usb_export."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.usb_export import (
    UsbExportConfig,
    UsbExporter,
    UsbExportReport,
)
from linuxtools.errors.exceptions import InstallationError, ValidationError

_MODULE = "linuxtools.deploy.usb_export"


def _cmd_result(
    success: bool = True, stderr: str = "", command: tuple[str, ...] = ()
) -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=command,
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


def _venv_run_side_effect(
    add_stale_symlink: bool = False,
) -> Callable[..., CommandResult]:
    """Fabrique un side_effect simulant `uv venv` / `uv pip install`.

    `uv venv` crée réellement l'arborescence attendue (bin/python3
    symlink vers un "interpréteur" factice) sur le disque, pour que
    le `copytree_secure(..., follow_symlinks=True)` réel du code sous
    test ait une source à copier. `uv pip install` ne fait rien de
    plus qu'un succès simulé.

    Args:
        add_stale_symlink: Si True, ajoute un symlink de répertoire
            supplémentaire (`lib64 -> lib`) pour le test de
            non-régression exFAT/FAT/NTFS.
    """

    def _run(
        command: list[str], *args: object, **kwargs: object
    ) -> CommandResult:
        if command[:2] == ["uv", "venv"]:
            venv_path = Path(command[-1])
            bin_dir = venv_path / "bin"
            bin_dir.mkdir(parents=True)
            real_interpreter = venv_path.parent / "real_python3"
            real_interpreter.write_text("#!/bin/sh\necho python\n")
            real_interpreter.chmod(0o755)
            (bin_dir / "python3").symlink_to(real_interpreter)
            if add_stale_symlink:
                real_lib = venv_path / "lib"
                (real_lib / "site-packages").mkdir(parents=True)
                (venv_path / "lib64").symlink_to(
                    real_lib, target_is_directory=True
                )
            return _cmd_result(success=True, command=tuple(command))
        if "install" in command:
            return _cmd_result(success=True, command=tuple(command))
        return _cmd_result(success=True, command=tuple(command))

    return _run


@pytest.fixture
def project_src(tmp_path: Path) -> Path:
    """Crée un projet consommateur factice avec pyproject.toml."""
    src = tmp_path / "project_src"
    src.mkdir()
    (src / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (src / "demo.py").write_text("print('hi')\n")
    return src


@pytest.fixture
def executor() -> MagicMock:
    """Exécuteur mocké, spec=CommandExecutor, succès par défaut."""
    mock = MagicMock(spec=CommandExecutor)
    mock.run.return_value = _cmd_result(success=True)
    return mock


@pytest.fixture(autouse=True)
def _sans_linuxtools_par_defaut() -> Iterator[None]:
    """Neutralise find_editable_source par défaut dans tous les tests.

    Évite qu'un test dépende de l'état réel d'installation éditable
    de linuxtools sur la machine qui exécute la suite.
    """
    with patch(f"{_MODULE}.find_editable_source", return_value=None):
        yield


class TestExportValidation:
    """Tests des validations d'entrée (avant tout effet de bord)."""

    def test_export_mode_invalide_leve_validation_error(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Un mode hors {"sources", "venv"} lève ValidationError."""
        exporter = UsbExporter(executor)
        config = UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode="invalide",  # type: ignore[arg-type]
        )
        with pytest.raises(ValidationError):
            exporter.export(config)

    def test_export_venv_sans_cli_entry_point_leve_validation_error(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """cli_entry_point absent en mode venv lève ValidationError."""
        exporter = UsbExporter(executor)
        config = UsbExportConfig(target_dir=tmp_path / "usb", mode="venv")
        with pytest.raises(ValidationError):
            exporter.export(config)

    def test_export_cli_entry_point_mal_forme_leve_validation_error(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """cli_entry_point sans ':' unique lève ValidationError."""
        exporter = UsbExporter(executor)
        config = UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode="venv",
            cli_entry_point="module_sans_fonction",
        )
        with pytest.raises(ValidationError):
            exporter.export(config)

    def test_export_cli_entry_point_injection_shell_leve_validation_error(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Métacaractères shell dans cli_entry_point -> ValidationError.

        Non-régression : sans validation par regex d'identifiant
        Python, cette valeur casserait la ligne `-c "from {module}
        import {function}; {function}()"` de run.sh et permettrait
        l'exécution de commandes arbitraires (run.sh est souvent
        lancé avec sudo).
        """
        exporter = UsbExporter(executor)
        config = UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode="venv",
            project_src=project_src,
            cli_entry_point=(
                'demo.cli:main"; touch /tmp/PWNED_RUNSH; echo "'
            ),
        )
        with pytest.raises(ValidationError):
            exporter.export(config)
        # Aucun effet de bord : la validation intervient avant toute
        # écriture disque.
        assert not (tmp_path / "usb").exists()

    def test_export_project_src_introuvable_leve_file_not_found_error(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """project_src fourni mais inexistant lève FileNotFoundError."""
        exporter = UsbExporter(executor)
        config = UsbExportConfig(
            target_dir=tmp_path / "usb",
            mode="sources",
            project_src=tmp_path / "absent",
        )
        with pytest.raises(FileNotFoundError):
            exporter.export(config)


class TestExportModeSources:
    """Tests du mode "sources" (copie + install.sh)."""

    def test_export_sources_cas_nominal_cree_uv_projet_script(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Cas nominal : uv, sources projet et install.sh sont créés."""
        target_dir = tmp_path / "usb"
        fake_uv = tmp_path / "fake_uv"
        fake_uv.write_text("#!/bin/sh\necho uv\n")
        fake_uv.chmod(0o755)

        with patch(f"{_MODULE}.shutil.which", return_value=str(fake_uv)):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert isinstance(report, UsbExportReport)
        assert (target_dir / "uv").exists()
        assert (target_dir / project_src.name / "demo.py").exists()
        assert (target_dir / "install.sh").exists()
        assert os.access(target_dir / "install.sh", os.X_OK)
        assert report.warnings == (
            "linuxtools non détecté — installation éditable "
            "requise pour l'auto-détection.",
        )

    def test_export_sources_sans_uv_sur_path_ajoute_avertissement(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """uv absent du PATH -> avertissement, pas d'échec."""
        target_dir = tmp_path / "usb"
        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert not (target_dir / "uv").exists()
        assert any("uv absent du PATH" in w for w in report.warnings)

    def test_export_sources_avec_linuxtools_detecte_copie_linuxtools(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """linuxtools détecté (éditable) -> copié sur la clé."""
        target_dir = tmp_path / "usb"
        lpu_src = tmp_path / "lpu_src"
        lpu_src.mkdir()
        (lpu_src / "marker.txt").write_text("linuxtools")

        with (
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch(f"{_MODULE}.find_editable_source", return_value=lpu_src),
        ):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert (target_dir / "linuxtools" / "marker.txt").exists()
        assert not any("linuxtools non détecté" in w for w in report.warnings)

    def test_export_sources_sans_linuxtools_ajoute_avertissement(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """linuxtools non détecté -> avertissement, pas de répertoire."""
        target_dir = tmp_path / "usb"
        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert not (target_dir / "linuxtools").exists()
        assert any("linuxtools non détecté" in w for w in report.warnings)

    def test_install_script_genere_ne_contient_jamais_python3_m_pip(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Non-régression : aucune trace de `python3 -m pip install`."""
        target_dir = tmp_path / "usb"
        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        content = (target_dir / "install.sh").read_text(encoding="utf-8")
        assert "python3 -m pip install" not in content
        assert "-m pip" not in content
        assert "uv tool install" in content
        assert project_src.name in content

    def test_install_script_avec_lpu_utilise_uv_tool_install_with(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """linuxtools détecté -> `uv tool install --with`.

        Non-régression : `uv pip install --system` serait ignoré
        par le venv d'outil isolé créé par `uv tool install`.
        """
        target_dir = tmp_path / "usb"
        lpu_src = tmp_path / "lpu_src"
        lpu_src.mkdir()
        (lpu_src / "marker.txt").write_text("linuxtools")

        with (
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch(f"{_MODULE}.find_editable_source", return_value=lpu_src),
        ):
            exporter = UsbExporter(executor)
            exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        content = (target_dir / "install.sh").read_text(encoding="utf-8")
        assert "uv pip install --system" not in content
        assert (
            'uv tool install --with "$USB/linuxtools" '
            f'"$USB/{project_src.name}"'
        ) in content

    def test_export_sources_reexport_sur_cible_existante_ne_leve_pas(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Deux export() successifs sur la même cible n'échouent pas.

        Non-régression : copytree_secure lève FileExistsError si dst
        existe déjà (dirs_exist_ok=False par défaut) — un ré-export
        sur une clé déjà préparée doit rester possible.
        """
        target_dir = tmp_path / "usb"
        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert (target_dir / project_src.name / "demo.py").exists()
        assert (target_dir / "install.sh").exists()
        assert report.created_paths


class TestExportModeVenv:
    """Tests du mode "venv" (venv autonome + run.sh)."""

    def test_export_venv_cas_nominal_construit_venv_et_run_script(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Cas nominal : venv construit, run.sh généré et référencé."""
        target_dir = tmp_path / "usb"
        executor.run.side_effect = _venv_run_side_effect()

        exporter = UsbExporter(executor)
        report = exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode="venv",
                project_src=project_src,
                cli_entry_point="demo.cli:main",
            )
        )

        assert (target_dir / "venv" / "bin" / "python3").exists()
        assert (target_dir / "run.sh").exists()
        assert os.access(target_dir / "run.sh", os.X_OK)
        run_content = (target_dir / "run.sh").read_text(encoding="utf-8")
        assert "from demo.cli import main; main()" in run_content
        assert str(target_dir / "venv") in report.created_paths

    def test_export_venv_echec_uv_venv_leve_installation_error(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Échec de `uv venv` -> InstallationError."""
        executor.run.return_value = _cmd_result(
            success=False, stderr="uv venv a échoué"
        )
        exporter = UsbExporter(executor)
        with pytest.raises(InstallationError):
            exporter.export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                )
            )

    def test_export_venv_echec_pip_install_leve_installation_error(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """`uv venv` réussit, `uv pip install` échoue -> InstallationError."""

        def _run(
            command: list[str], *a: object, **kw: object
        ) -> CommandResult:
            if command[:2] == ["uv", "venv"]:
                venv_path = Path(command[-1])
                (venv_path / "bin").mkdir(parents=True)
                return _cmd_result(success=True)
            return _cmd_result(success=False, stderr="pip install a échoué")

        executor.run.side_effect = _run
        exporter = UsbExporter(executor)
        with pytest.raises(InstallationError):
            exporter.export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                )
            )

    def test_export_venv_copie_sans_symlinks_residuels(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Régression exFAT/FAT/NTFS : aucun symlink dans venv/ final."""
        target_dir = tmp_path / "usb"
        executor.run.side_effect = _venv_run_side_effect(
            add_stale_symlink=True
        )

        exporter = UsbExporter(executor)
        exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode="venv",
                project_src=project_src,
                cli_entry_point="demo.cli:main",
            )
        )

        venv_dir = target_dir / "venv"
        assert venv_dir.exists()
        residual_symlinks = [
            p for p in venv_dir.rglob("*") if p.is_symlink()
        ]
        assert residual_symlinks == []
        # lib64 doit être une copie réelle du contenu de lib/, pas un
        # symlink résiduel.
        assert (venv_dir / "lib64" / "site-packages").is_dir()
        assert not (venv_dir / "lib64").is_symlink()
        assert (venv_dir / "bin" / "python3").is_file()
        assert not (venv_dir / "bin" / "python3").is_symlink()

    def test_export_venv_bin_python3_reste_executable(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """venv/bin/python3 reste exécutable après export().

        Non-régression : copytree_secure force 0o644 sur chaque
        fichier copié — sans restauration explicite des bits
        d'exécution, run.sh (`exec "$USB/venv/bin/python3"`)
        échouerait avec "Permission denied" sur ext4/btrfs.
        """
        target_dir = tmp_path / "usb"
        executor.run.side_effect = _venv_run_side_effect()

        exporter = UsbExporter(executor)
        exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode="venv",
                project_src=project_src,
                cli_entry_point="demo.cli:main",
            )
        )

        python_bin = target_dir / "venv" / "bin" / "python3"
        assert os.access(python_bin, os.X_OK)

    def test_export_venv_reexport_sur_cible_existante_ne_leve_pas(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Deux export() successifs en mode venv n'échouent pas.

        Non-régression : copytree_secure lève FileExistsError si dst
        existe déjà — un ré-export sur une clé déjà préparée doit
        rester possible.
        """
        target_dir = tmp_path / "usb"
        executor.run.side_effect = _venv_run_side_effect()

        exporter = UsbExporter(executor)
        exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode="venv",
                project_src=project_src,
                cli_entry_point="demo.cli:main",
            )
        )
        report = exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode="venv",
                project_src=project_src,
                cli_entry_point="demo.cli:main",
            )
        )

        assert (target_dir / "venv" / "bin" / "python3").exists()
        assert (target_dir / "run.sh").exists()
        assert report.created_paths


class TestExportDryRun:
    """Tests du mode dry-run (aucune écriture disque)."""

    @pytest.mark.parametrize("mode", ["sources", "venv"])
    def test_export_dry_run_ne_cree_aucun_fichier(
        self,
        mode: str,
        tmp_path: Path,
        project_src: Path,
        executor: MagicMock,
    ) -> None:
        """dry_run=True ne crée ni target_dir ni ses artefacts."""
        target_dir = tmp_path / "usb"
        exporter = UsbExporter(executor)
        report = exporter.export(
            UsbExportConfig(
                target_dir=target_dir,
                mode=mode,  # type: ignore[arg-type]
                project_src=project_src,
                cli_entry_point="demo.cli:main",
                dry_run=True,
            )
        )

        assert not target_dir.exists()
        assert report.created_paths
        executor.run.assert_not_called()


class TestExportConfigs:
    """Tests de la copie de configs (user_config_dir / project/configs)."""

    def test_export_copie_user_config_dir_quand_fourni(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """user_config_dir fourni -> copié en priorité sur configs/."""
        target_dir = tmp_path / "usb"
        user_config_dir = tmp_path / "user_configs"
        user_config_dir.mkdir()
        (user_config_dir / "user.toml").write_text("x = 1\n")
        (project_src / "configs").mkdir()
        (project_src / "configs" / "proj.toml").write_text("y = 2\n")

        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                    user_config_dir=user_config_dir,
                )
            )

        assert (target_dir / "configs" / "user.toml").exists()
        assert not (target_dir / "configs" / "proj.toml").exists()

    def test_export_copie_configs_projet_si_user_config_dir_absent(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Sans user_config_dir, bascule sur project_src/configs."""
        target_dir = tmp_path / "usb"
        (project_src / "configs").mkdir()
        (project_src / "configs" / "proj.toml").write_text("y = 2\n")

        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert (target_dir / "configs" / "proj.toml").exists()

    def test_export_sans_configs_ni_user_config_dir_ne_leve_pas(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Ni user_config_dir ni project_src/configs -> pas d'erreur."""
        target_dir = tmp_path / "usb"
        with patch(f"{_MODULE}.shutil.which", return_value=None):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert not (target_dir / "configs").exists()
        # Le nom du répertoire temporaire pytest peut contenir la
        # sous-chaîne "configs" (dérivé du nom de la fonction de
        # test) : on vérifie donc le nom de fichier final, pas une
        # sous-chaîne quelconque du chemin complet.
        assert not any(
            Path(p).name == "configs" for p in report.created_paths
        )
