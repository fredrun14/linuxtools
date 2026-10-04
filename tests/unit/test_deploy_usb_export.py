"""Tests pour le module deploy.usb_export."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.usb_export import (
    UsbExportConfig,
    UsbExporter,
    UsbExportReport,
)
from linuxtools.errors.exceptions import InstallationError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_MODULE = "linuxtools.deploy.usb_export"
# Vraie méthode, capturée avant que la fixture autouse ne la remplace
_REAL_FIND_UV = UsbExporter._find_uv  # noqa: SLF001
# Artefacts d'outillage local qui ne doivent jamais être copiés
_ARTEFACTS_DEV = (
    ".integration-runs",
    ".claude",
    ".idea",
    ".vscode",
    ".coverage",
    "coverage.xml",
    ".tox",
    ".nox",
    ".hypothesis",
)
# Parmi eux, ceux qui sont des fichiers (les autres sont des dossiers)
_ARTEFACTS_DEV_FICHIERS = (".coverage", "coverage.xml")


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
        if command[1:3] == ["venv", "--python"]:
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


@pytest.fixture(autouse=True)
def _uv_par_defaut(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Fixe un faux uv réel pour ne pas dépendre de la machine.

    Le fichier existe vraiment : le mode sources le copie sur la cible.
    """
    faux = tmp_path_factory.mktemp("fake_bin") / "uv"
    faux.write_text("#!/bin/sh\necho uv\n")
    faux.chmod(0o755)
    with patch.object(UsbExporter, "_find_uv", return_value=str(faux)):
        yield


def _faux_uv(
    home: Path,
    sub: str,
    mode: int = 0o755,
    parent_mode: int = 0o755,
) -> Path:
    """Crée un faux binaire uv sous `home/sub` avec les modes donnés.

    Les permissions sont fixées explicitement (chmod) : l'umask du
    runner n'est pas fiable.
    """
    binaire = home / sub
    binaire.parent.mkdir(parents=True, exist_ok=True)
    binaire.parent.chmod(parent_mode)
    binaire.write_text("#!/bin/sh\necho uv\n")
    binaire.chmod(mode)
    return binaire


def _find_uv_reel(
    executor: MagicMock,
    home: Path | None,
    which: str | None = None,
    sudo_user: str | None = None,
    getpwnam_effect: Exception | None = None,
    exporter: UsbExporter | None = None,
) -> tuple[str | None, MagicMock]:
    """Appelle la vraie `_find_uv` avec which/environ/getpwnam mockés.

    `pw_uid` vaut l'uid courant : les faux binaires du test nous
    appartiennent (le contrôle de propriétaire doit les accepter).
    """
    env = {"SUDO_USER": sudo_user} if sudo_user is not None else {}
    pw = MagicMock()
    if getpwnam_effect is not None:
        pw.side_effect = getpwnam_effect
    else:
        pw.return_value.pw_dir = str(home)
        pw.return_value.pw_uid = os.getuid()
    with (
        patch(f"{_MODULE}.shutil.which", return_value=which),
        patch.dict(f"{_MODULE}.os.environ", env, clear=True),
        patch(f"{_MODULE}.pwd.getpwnam", pw),
    ):
        return _REAL_FIND_UV(exporter or UsbExporter(executor)), pw


class TestFindUv:
    """Tests de la résolution de uv (PATH puis home de SUDO_USER)."""

    def test_find_uv_sur_path_retourne_which(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """uv présent dans le PATH -> chemin de shutil.which."""
        res, _ = _find_uv_reel(executor, tmp_path, which="/usr/bin/uv")
        assert res == "/usr/bin/uv"

    def test_find_uv_absent_du_path_avec_sudo_user_retourne_local_bin(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Hors PATH + SUDO_USER -> ~/.local/bin/uv de cet utilisateur."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(binaire)

    def test_find_uv_sudo_user_retombe_sur_cargo_bin(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Pas de .local/bin/uv -> ~/.cargo/bin/uv."""
        binaire = _faux_uv(tmp_path, ".cargo/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(binaire)

    def test_find_uv_binaire_non_executable_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Un fichier uv sans bit d'exécution n'est pas retenu."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o644)
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res is None

    def test_find_uv_sudo_user_inconnu_retourne_none(
        self, executor: MagicMock
    ) -> None:
        """SUDO_USER absent de passwd (KeyError) -> None."""
        res, _ = _find_uv_reel(
            executor, None, sudo_user="ghost", getpwnam_effect=KeyError("x")
        )
        assert res is None

    @pytest.mark.parametrize("sudo_user", ["root", ""])
    def test_find_uv_sudo_user_root_ou_vide_ne_sonde_pas_passwd(
        self, sudo_user: str, tmp_path: Path, executor: MagicMock
    ) -> None:
        """SUDO_USER root ou vide -> aucune recherche secondaire."""
        res, pw = _find_uv_reel(executor, tmp_path, sudo_user=sudo_user)
        assert res is None
        pw.assert_not_called()

    def test_find_uv_rien_trouve_retourne_none(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Ni PATH ni SUDO_USER -> None."""
        res, _ = _find_uv_reel(executor, tmp_path)
        assert res is None

    def test_find_uv_prefere_local_bin_a_cargo_bin(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Les deux candidats présents -> .local/bin gagne."""
        local = _faux_uv(tmp_path, ".local/bin/uv")
        _faux_uv(tmp_path, ".cargo/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(local)

    def test_find_uv_which_prioritaire_sur_sudo_user(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """uv dans le PATH -> SUDO_USER n'est même pas consulté."""
        _faux_uv(tmp_path, ".local/bin/uv")
        res, pw = _find_uv_reel(
            executor, tmp_path, which="/usr/bin/uv", sudo_user="alice"
        )
        assert res == "/usr/bin/uv"
        pw.assert_not_called()

    def test_find_uv_bascule_sur_cargo_si_local_non_executable(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """.local/bin/uv non exécutable -> repli sur .cargo/bin/uv."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o644)
        cargo = _faux_uv(tmp_path, ".cargo/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(cargo)

    def test_find_uv_binaire_modifiable_par_groupe_est_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Binaire en 0o775 (écriture groupe) -> refusé."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o775)
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res is None

    def test_find_uv_parent_modifiable_par_groupe_est_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Binaire sain, parent en 0o775 (écriture groupe) -> refusé."""
        _faux_uv(tmp_path, ".local/bin/uv", parent_mode=0o775)
        exporter = UsbExporter(executor)
        res, _ = _find_uv_reel(
            executor, tmp_path, sudo_user="alice", exporter=exporter
        )
        assert res is None
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert "modifiable par le groupe ou les autres" in rejet

    def test_find_uv_binaire_modifiable_par_les_autres_est_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Binaire en 0o757 (écriture autres) -> refusé."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o757)
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res is None

    def test_find_uv_repertoire_parent_modifiable_par_les_autres_est_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Binaire sain mais répertoire parent en 0o777 -> refusé."""
        _faux_uv(tmp_path, ".local/bin/uv", parent_mode=0o777)
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res is None

    def test_find_uv_bascule_sur_cargo_si_local_modifiable(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] .local/bin/uv en 0o775 -> repli sur .cargo/bin/uv sain."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o775)
        cargo = _faux_uv(tmp_path, ".cargo/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(cargo)

    def test_find_uv_stat_oserror_candidat_ignore(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] stat() du répertoire parent qui échoue -> rejeté."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv")
        stat_reel = Path.stat

        def stat_pivot(self: Path, **kwargs: bool) -> os.stat_result:
            """Échoue uniquement sur le répertoire parent (course)."""
            if self == binaire.parent:
                raise OSError("course")
            return stat_reel(self, **kwargs)

        exporter = UsbExporter(executor)
        with patch.object(Path, "stat", autospec=True, side_effect=stat_pivot):
            res, _ = _find_uv_reel(
                executor, tmp_path, sudo_user="alice", exporter=exporter
            )
        assert res is None
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert rejet.endswith(" : illisible")

    def test_find_uv_candidat_rejete_logge_un_warning(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Un candidat refusé produit un log_warning explicite."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv", mode=0o775)
        logger = MagicMock()
        env = {"SUDO_USER": "alice"}
        pw = MagicMock()
        pw.return_value.pw_dir = str(tmp_path)
        pw.return_value.pw_uid = os.getuid()
        with (
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(f"{_MODULE}.os.environ", env, clear=True),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            res = _REAL_FIND_UV(UsbExporter(executor, logger=logger))
        assert res is None
        logger.log_warning.assert_called_once()
        assert str(binaire) in logger.log_warning.call_args.args[0]

    def test_find_uv_symlink_vers_cible_dans_repertoire_permissif_est_refuse(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Lien sain -> cible dans un répertoire 0o777 : refusé."""
        cible = _faux_uv(tmp_path / "ailleurs", "uv", parent_mode=0o777)
        lien = tmp_path / ".local/bin/uv"
        lien.parent.mkdir(parents=True)
        lien.symlink_to(cible)
        exporter = UsbExporter(executor)
        res, _ = _find_uv_reel(
            executor, tmp_path, sudo_user="alice", exporter=exporter
        )
        assert res is None
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert "modifiable par le groupe ou les autres" in rejet
        # F11 : la raison nomme la cible résolue fautive
        assert f"(cible : {cible.resolve()})" in rejet

    def test_find_uv_refus_sans_lien_n_ajoute_pas_de_cible(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Candidat refusé sans lien -> pas de suffixe « (cible : … ) »."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o757)
        exporter = UsbExporter(executor)
        _find_uv_reel(executor, tmp_path, sudo_user="alice", exporter=exporter)
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert "modifiable par le groupe ou les autres" in rejet
        assert "(cible :" not in rejet

    def test_find_uv_home_en_lien_n_ajoute_pas_de_cible(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Seul le home est un lien (/home -> /var/home) : pas de suffixe."""
        reel = tmp_path / "reel"
        _faux_uv(reel, ".local/bin/uv", mode=0o757)
        home = tmp_path / "home"
        home.symlink_to(reel)
        exporter = UsbExporter(executor)
        res, _ = _find_uv_reel(
            executor, home, sudo_user="alice", exporter=exporter
        )
        assert res is None
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert "modifiable par le groupe ou les autres" in rejet
        assert "(cible :" not in rejet

    def test_find_uv_lien_du_candidat_ajoute_la_cible_meme_home_en_lien(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Home en lien ET candidat en lien : le suffixe reste présent."""
        reel = tmp_path / "reel"
        cible = _faux_uv(reel / "ailleurs", "uv", parent_mode=0o777)
        lien = reel / ".local/bin/uv"
        lien.parent.mkdir(parents=True)
        lien.symlink_to(cible)
        home = tmp_path / "home"
        home.symlink_to(reel)
        exporter = UsbExporter(executor)
        _find_uv_reel(executor, home, sudo_user="alice", exporter=exporter)
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert f"(cible : {cible.resolve()})" in rejet

    def test_find_uv_boucle_de_liens_est_refusee_avec_raison(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Boucle de liens -> raison « illisible », repli cargo."""
        a = tmp_path / ".local/bin/uv"
        a.parent.mkdir(parents=True)
        b = tmp_path / ".local/bin/uv-b"
        a.symlink_to(b)
        b.symlink_to(a)
        cargo = _faux_uv(tmp_path, ".cargo/bin/uv")
        exporter = UsbExporter(executor)
        res, _ = _find_uv_reel(
            executor, tmp_path, sudo_user="alice", exporter=exporter
        )
        assert res == str(cargo)
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert str(a) in rejet
        assert "illisible (boucle de liens ou erreur d'accès)" in rejet

    def test_find_uv_symlink_sain_retourne_le_chemin_resolu(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Lien sain -> on retourne la cible contrôlée, pas le lien."""
        cible = _faux_uv(tmp_path / "ailleurs", "uv-0.9")
        lien = tmp_path / ".local/bin/uv"
        lien.parent.mkdir(parents=True)
        lien.symlink_to(cible)
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(cible.resolve())
        assert res != str(lien)

    def test_find_uv_lien_casse_est_refuse(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Lien symbolique cassé -> refusé, repli sur cargo."""
        lien = tmp_path / ".local/bin/uv"
        lien.parent.mkdir(parents=True)
        lien.symlink_to(tmp_path / "inexistant")
        cargo = _faux_uv(tmp_path, ".cargo/bin/uv")
        res, _ = _find_uv_reel(executor, tmp_path, sudo_user="alice")
        assert res == str(cargo)

    def test_find_uv_proprietaire_inattendu_est_refuse(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Cible appartenant à un tiers (ni root ni SUDO_USER)."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv")
        stat_reel = Path.stat
        tiers = os.getuid() + 4242

        def stat_pivot(self: Path, **kwargs: object) -> MagicMock:
            """Falsifie uniquement le propriétaire du binaire (sans root)."""
            vrai = stat_reel(self)
            if self == binaire:
                faux = MagicMock()
                faux.st_mode = vrai.st_mode
                faux.st_uid = tiers
                return faux
            return MagicMock(st_mode=vrai.st_mode, st_uid=vrai.st_uid)

        exporter = UsbExporter(executor)
        with patch.object(Path, "stat", autospec=True, side_effect=stat_pivot):
            res, _ = _find_uv_reel(
                executor, tmp_path, sudo_user="alice", exporter=exporter
            )
        assert res is None
        (rejet,) = exporter._uv_rejections  # noqa: SLF001
        assert f"propriétaire inattendu (uid {tiers})" in rejet

    def test_find_uv_proprietaire_root_est_accepte(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Cible appartenant à root (uid 0) -> acceptée."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv")
        stat_reel = Path.stat

        def stat_pivot(self: Path, **kwargs: object) -> MagicMock:
            """Fait apparaître le binaire comme appartenant à root."""
            vrai = stat_reel(self)
            uid = 0 if self == binaire else vrai.st_uid
            return MagicMock(st_mode=vrai.st_mode, st_uid=uid)

        # SUDO_USER a un autre uid : seul root justifie l'acceptation
        pw = MagicMock()
        pw.return_value.pw_dir = str(tmp_path)
        pw.return_value.pw_uid = os.getuid() + 4242
        with (
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
            patch.object(Path, "stat", autospec=True, side_effect=stat_pivot),
        ):
            res = _REAL_FIND_UV(UsbExporter(executor))
        assert res == str(binaire.resolve())


class TestUvRejections:
    """Les raisons de refus de uv remontent sans dépendre du logger."""

    def test_require_uv_liste_les_candidats_refuses_sans_logger(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """[SEC] Sans logger, l'erreur nomme le candidat et la raison."""
        binaire = _faux_uv(tmp_path, ".local/bin/uv", mode=0o775)
        exporter = UsbExporter(executor)  # volontairement sans logger
        with (
            patch.object(
                UsbExporter,
                "_find_uv",
                lambda self: _find_uv_reel(
                    executor, tmp_path, sudo_user="alice", exporter=self
                )[0],
            ),
            pytest.raises(InstallationError) as exc,
        ):
            exporter._require_uv()  # noqa: SLF001
        message = str(exc.value)
        assert str(binaire) in message
        assert "modifiable par le groupe ou les autres" in message
        assert "Installez uv" not in message

    def test_require_uv_sans_refus_garde_le_message_installez_uv(
        self, executor: MagicMock
    ) -> None:
        """Aucun candidat refusé -> message historique inchangé."""
        with (
            patch.object(UsbExporter, "_find_uv", return_value=None),
            pytest.raises(InstallationError, match="Installez uv"),
        ):
            UsbExporter(executor)._require_uv()  # noqa: SLF001

    def test_dry_run_venv_avertissement_contient_la_raison_du_refus(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """[SEC] Dry-run venv : l'avertissement cite le candidat refusé."""
        binaire = _faux_uv(tmp_path / "home", ".local/bin/uv", mode=0o775)
        pw = MagicMock()
        pw.return_value.pw_dir = str(tmp_path / "home")
        pw.return_value.pw_uid = os.getuid()
        with (
            patch.object(UsbExporter, "_find_uv", _REAL_FIND_UV),
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                    dry_run=True,
                )
            )
        avertissement = next(
            w for w in report.warnings if "uv introuvable" in w
        )
        assert "échouera" in avertissement
        assert str(binaire) in avertissement
        assert "modifiable par le groupe ou les autres" in avertissement

    def test_export_sources_uv_refuse_avertissement_contient_la_raison(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """[SEC] Mode sources (réel) : l'avertissement cite le refus."""
        binaire = _faux_uv(tmp_path / "home", ".local/bin/uv", mode=0o775)
        pw = MagicMock()
        pw.return_value.pw_dir = str(tmp_path / "home")
        pw.return_value.pw_uid = os.getuid()
        with (
            patch.object(UsbExporter, "_find_uv", _REAL_FIND_UV),
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="sources",
                    project_src=project_src,
                )
            )
        avertissement = next(
            w for w in report.warnings if "uv introuvable" in w
        )
        assert "à copier manuellement" in avertissement
        assert str(binaire) in avertissement
        assert "modifiable par le groupe ou les autres" in avertissement

    def test_dry_run_sources_avertissement_contient_la_raison_du_refus(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """[SEC] Dry-run sources : avertit et cite le candidat refusé."""
        binaire = _faux_uv(tmp_path / "home", ".local/bin/uv", mode=0o775)
        pw = MagicMock()
        pw.return_value.pw_dir = str(tmp_path / "home")
        pw.return_value.pw_uid = os.getuid()
        with (
            patch.object(UsbExporter, "_find_uv", _REAL_FIND_UV),
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="sources",
                    project_src=project_src,
                    dry_run=True,
                )
            )
        avertissement = next(
            w for w in report.warnings if "uv introuvable" in w
        )
        assert "à copier manuellement" in avertissement
        assert str(binaire) in avertissement

    def test_export_sources_sans_refus_garde_le_texte_historique(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Aucun refus -> avertissement sources strictement inchangé."""
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="sources",
                    project_src=project_src,
                )
            )
        assert (
            "uv introuvable — à copier manuellement sur la cible."
            in report.warnings
        )

    def test_find_uv_remet_les_refus_a_zero_a_chaque_appel(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Deux appels successifs : pas d'accumulation des refus."""
        _faux_uv(tmp_path, ".local/bin/uv", mode=0o775)
        exporter = UsbExporter(executor)
        _find_uv_reel(executor, tmp_path, sudo_user="alice", exporter=exporter)
        _find_uv_reel(executor, tmp_path, sudo_user="alice", exporter=exporter)
        assert len(exporter._uv_rejections) == 1  # noqa: SLF001


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
            cli_entry_point=('demo.cli:main"; touch /tmp/PWNED_RUNSH; echo "'),
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

        with patch.object(UsbExporter, "_find_uv", return_value=str(fake_uv)):
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

    @pytest.mark.parametrize("artefact", _ARTEFACTS_DEV)
    def test_export_sources_exclut_les_artefacts_de_dev(
        self, tmp_path: Path, executor: MagicMock, artefact: str
    ) -> None:
        """Chaque artefact d'outillage local est absent de la cible."""
        proj = tmp_path / "monprojet"
        (proj / "src" / "pkg").mkdir(parents=True)
        (proj / "src" / "pkg" / "mod.py").write_text("x = 1\n")
        # Fichiers simples pour .coverage et coverage.xml, dossiers sinon
        if artefact in _ARTEFACTS_DEV_FICHIERS:
            (proj / artefact).write_text("data")
        else:
            (proj / artefact).mkdir()
            (proj / artefact / "x").write_text("data")
        target_dir = tmp_path / "usb"

        with patch.object(UsbExporter, "_find_uv", return_value=None):
            UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=proj,
                )
            )

        copie = target_dir / "monprojet"
        assert (copie / "src" / "pkg" / "mod.py").exists()
        assert not (copie / artefact).exists()

    def test_export_sources_noms_proches_des_artefacts_conserves(
        self, tmp_path: Path, executor: MagicMock
    ) -> None:
        """Motifs exacts : un nom proche d'un artefact n'est pas exclu."""
        proj = tmp_path / "monprojet"
        (proj / "integration-runs-doc").mkdir(parents=True)
        (proj / "integration-runs-doc" / "a.md").write_text("doc")
        (proj / "idea.md").write_text("notes")
        target_dir = tmp_path / "usb"

        with patch.object(UsbExporter, "_find_uv", return_value=None):
            UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=proj,
                )
            )

        copie = target_dir / "monprojet"
        assert (copie / "integration-runs-doc" / "a.md").exists()
        assert (copie / "idea.md").exists()

    def test_export_sources_sans_uv_ajoute_avertissement(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """uv introuvable -> avertissement, pas d'échec."""
        target_dir = tmp_path / "usb"
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            exporter = UsbExporter(executor)
            report = exporter.export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert not (target_dir / "uv").exists()
        assert any("uv introuvable" in w for w in report.warnings)

    def test_export_sources_sous_sudo_copie_uv_de_sudo_user(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Sous sudo, uv du home de SUDO_USER est copié sur la cible."""
        home = tmp_path / "home_alice"
        _faux_uv(home, ".local/bin/uv")
        target_dir = tmp_path / "usb"
        pw = MagicMock()
        pw.return_value.pw_dir = str(home)
        pw.return_value.pw_uid = os.getuid()
        with (
            patch.object(UsbExporter, "_find_uv", _REAL_FIND_UV),
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=target_dir,
                    mode="sources",
                    project_src=project_src,
                )
            )

        assert (target_dir / "uv").read_text() == "#!/bin/sh\necho uv\n"

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

    def test_export_venv_sous_sudo_utilise_uv_de_sudo_user(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Régression : sous sudo, les commandes utilisent le uv absolu."""
        home = tmp_path / "home_alice"
        binaire = _faux_uv(home, ".local/bin/uv")
        executor.run.side_effect = _venv_run_side_effect()
        pw = MagicMock()
        pw.return_value.pw_dir = str(home)
        pw.return_value.pw_uid = os.getuid()
        with (
            patch.object(UsbExporter, "_find_uv", _REAL_FIND_UV),
            patch(f"{_MODULE}.shutil.which", return_value=None),
            patch.dict(
                f"{_MODULE}.os.environ", {"SUDO_USER": "alice"}, clear=True
            ),
            patch(f"{_MODULE}.pwd.getpwnam", pw),
        ):
            UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                )
            )

        commandes = [c.args[0] for c in executor.run.call_args_list]
        assert len(commandes) == 2
        assert all(cmd[0] == str(binaire) for cmd in commandes)

    def test_export_venv_uv_introuvable_leve_erreur_sans_creer_cible(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """uv introuvable -> erreur claire, rien écrit sur la clé."""
        target_dir = tmp_path / "usb"
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            with pytest.raises(InstallationError, match="uv introuvable"):
                UsbExporter(executor).export(
                    UsbExportConfig(
                        target_dir=target_dir,
                        mode="venv",
                        project_src=project_src,
                        cli_entry_point="demo.cli:main",
                    )
                )

        executor.run.assert_not_called()
        assert not target_dir.exists()

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
            if command[1:3] == ["venv", "--python"]:
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
        residual_symlinks = [p for p in venv_dir.rglob("*") if p.is_symlink()]
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

    @staticmethod
    def _run_capturant_pip(
        capture: dict[str, object], succes: bool = True
    ) -> Callable[..., CommandResult]:
        """Side_effect qui relève la commande pip et lit l'override.

        Le répertoire temporaire est supprimé après l'export : le
        contenu du fichier d'override doit donc être lu pendant l'appel.

        Args:
            capture: Dictionnaire rempli (commande, contenu, chemin).
            succes: Si False, `uv pip install` échoue.
        """
        base = _venv_run_side_effect()

        def _run(
            command: list[str], *a: object, **kw: object
        ) -> CommandResult:
            if "install" not in command:
                return base(command, *a, **kw)
            capture["commande"] = list(command)
            if "--override" in command:
                chemin = Path(command[command.index("--override") + 1])
                capture["override_path"] = chemin
                capture["override_contenu"] = chemin.read_text(
                    encoding="utf-8"
                )
            if not succes:
                return _cmd_result(success=False, stderr="pip a échoué")
            return _cmd_result(success=True, command=tuple(command))

        return _run

    def _exporter_avec_lpu(
        self,
        tmp_path: Path,
        project_src: Path,
        executor: MagicMock,
        lpu_src: Path | None,
    ) -> None:
        """Lance un export venv avec `find_editable_source` simulé."""
        with patch(f"{_MODULE}.find_editable_source", return_value=lpu_src):
            UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                )
            )

    def test_export_venv_avec_lpu_ignore_sources_et_impose_override(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Avec linuxtools local : --no-sources + override en file://."""
        lpu_src = tmp_path / "lpu"
        lpu_src.mkdir()
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        self._exporter_avec_lpu(tmp_path, project_src, executor, lpu_src)

        commande = capture["commande"]
        assert isinstance(commande, list)
        assert "--no-sources" in commande
        assert "--override" in commande
        assert capture["override_contenu"] == (
            f"linuxtools @ file://{lpu_src.resolve()}\n"
        )
        # Le chemin du projet et celui de linuxtools restent installés
        assert str(lpu_src) in commande
        assert str(project_src) in commande
        override = capture["override_path"]
        assert isinstance(override, Path)
        assert not override.is_relative_to(tmp_path / "usb")

    def test_export_venv_sans_lpu_ignore_sources_sans_override(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Sans linuxtools local : --no-sources seul, pas d'override."""
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        self._exporter_avec_lpu(tmp_path, project_src, executor, None)

        commande = capture["commande"]
        assert isinstance(commande, list)
        assert "--no-sources" in commande
        assert "--override" not in commande

    def test_export_venv_override_encode_espace_et_diese(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Un chemin avec espace et # est encodé dans l'URI d'override."""
        # Ce test valide l'ENCODAGE de l'override (%20, %23), pas la
        # résolution par uv. En conditions réelles, uv 0.10 refuse un
        # chemin linuxtools contenant « # » (limite d'uv, identique pour
        # l'argument positionnel et pour l'override) ; l'espace seul
        # fonctionne.
        lpu_src = tmp_path / "mon lpu#dev"
        lpu_src.mkdir()
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        self._exporter_avec_lpu(tmp_path, project_src, executor, lpu_src)

        contenu = capture["override_contenu"]
        assert isinstance(contenu, str)
        assert contenu.endswith("/mon%20lpu%23dev\n")
        assert contenu.startswith("linuxtools @ file:///")
        assert len(contenu.splitlines()) == 1

    def test_export_venv_override_utilise_le_chemin_resolu_du_lien(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Un lpu fourni en lien symbolique : l'URI vise la cible réelle."""
        reel = tmp_path / "linuxtools_reel"
        reel.mkdir()
        lien = tmp_path / "lien_lpu"
        lien.symlink_to(reel, target_is_directory=True)
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        self._exporter_avec_lpu(tmp_path, project_src, executor, lien)

        # Attendu littéral : cible du lien, jamais le nom du lien
        assert capture["override_contenu"] == (
            f"linuxtools @ file://{reel.resolve()}\n"
        )
        contenu = capture["override_contenu"]
        assert isinstance(contenu, str)
        assert "lien_lpu" not in contenu

    def test_export_venv_echec_ecriture_override_nettoie_et_ne_lance_pas_pip(
        self,
        tmp_path: Path,
        project_src: Path,
        executor: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OSError sur l'override : propagée, pas de pip, tmp supprimé."""
        lpu_src = tmp_path / "lpu"
        lpu_src.mkdir()
        # Isole le dossier temporaire pour pouvoir le lister ensuite
        racine_tmp = tmp_path / "tmp_isole"
        racine_tmp.mkdir()
        monkeypatch.setattr("tempfile.tempdir", str(racine_tmp))
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        vraie_ecriture = Path.write_text

        def _write_text(
            self_: Path, data: str, encoding: str | None = None
        ) -> int:
            if self_.name == "override.txt":
                raise OSError("disque plein simulé")
            return vraie_ecriture(self_, data, encoding=encoding)

        with (
            patch.object(Path, "write_text", _write_text),
            pytest.raises(OSError, match="disque plein simulé"),
        ):
            self._exporter_avec_lpu(tmp_path, project_src, executor, lpu_src)

        # Aucun `uv pip install` lancé (seul `uv venv` est passé)
        assert "commande" not in capture
        assert list(racine_tmp.glob("usbexp-venv-*")) == []
        assert not (tmp_path / "usb" / "venv").exists()

    def test_export_venv_override_supprime_apres_export(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Le dossier temporaire (et l'override) disparaît après export."""
        lpu_src = tmp_path / "lpu"
        lpu_src.mkdir()
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(capture)

        self._exporter_avec_lpu(tmp_path, project_src, executor, lpu_src)

        override = capture["override_path"]
        assert isinstance(override, Path)
        assert not override.exists()
        assert not override.parent.exists()

    def test_export_venv_override_supprime_si_pip_echoue(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Même si `pip install` échoue, l'override est supprimé."""
        lpu_src = tmp_path / "lpu"
        lpu_src.mkdir()
        capture: dict[str, object] = {}
        executor.run.side_effect = self._run_capturant_pip(
            capture, succes=False
        )

        with pytest.raises(InstallationError):
            self._exporter_avec_lpu(tmp_path, project_src, executor, lpu_src)

        override = capture["override_path"]
        assert isinstance(override, Path)
        assert not override.exists()
        assert not override.parent.exists()


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

    def test_export_dry_run_venv_sans_uv_ne_leve_pas(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Dry-run venv sans uv : pas d'exception, ligne exacte."""
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                    dry_run=True,
                )
            )

        assert "[dry-run] uv      : (introuvable)" in report.created_paths

    def test_export_dry_run_venv_sans_uv_avertit_que_l_export_echouera(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Dry-run venv sans uv -> avertissement dans le rapport."""
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                    dry_run=True,
                )
            )

        assert (
            "uv introuvable — l'export réel (mode venv) échouera."
            in report.warnings
        )

    def test_export_dry_run_venv_avec_uv_affiche_chemin_sans_avertir(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Dry-run venv avec uv trouvé -> chemin affiché, aucun warning."""
        with patch.object(UsbExporter, "_find_uv", return_value="/opt/uv"):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="venv",
                    project_src=project_src,
                    cli_entry_point="demo.cli:main",
                    dry_run=True,
                )
            )

        assert "[dry-run] uv      : /opt/uv" in report.created_paths
        assert not any("uv introuvable" in w for w in report.warnings)

    def test_export_dry_run_sources_sans_uv_avertit(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Dry-run sources sans uv : avertissement texte historique."""
        with patch.object(UsbExporter, "_find_uv", return_value=None):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="sources",
                    project_src=project_src,
                    dry_run=True,
                )
            )

        assert "[dry-run] uv      : (introuvable)" in report.created_paths
        assert (
            "uv introuvable — à copier manuellement sur la cible."
            in report.warnings
        )

    def test_export_dry_run_sources_avec_uv_pas_d_avertissement(
        self, tmp_path: Path, project_src: Path, executor: MagicMock
    ) -> None:
        """Dry-run sources avec uv trouvé -> aucun avertissement uv."""
        with patch.object(UsbExporter, "_find_uv", return_value="/opt/uv"):
            report = UsbExporter(executor).export(
                UsbExportConfig(
                    target_dir=tmp_path / "usb",
                    mode="sources",
                    project_src=project_src,
                    dry_run=True,
                )
            )

        assert not any("uv introuvable" in w for w in report.warnings)


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
        assert not any(Path(p).name == "configs" for p in report.created_paths)
