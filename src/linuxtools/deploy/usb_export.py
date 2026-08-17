"""Préparation d'une clé USB de déploiement offline.

Deux modes : "sources" (copie des sources + `uv tool install`,
réseau requis sur la cible) et "venv" (venv Python autonome
précompilé, aucun réseau requis sur la cible). Généralise
`UsbExportManager` (fedora_post_install) sans dépendre d'un nom de
projet en dur — cf. discovery.py et content_writer.py pour les
primitives réutilisées.
"""

from __future__ import annotations

# stdlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

# local
from linuxtools.commands.builder import CommandBuilder
from linuxtools.deploy.content_writer import deposit_content
from linuxtools.deploy.discovery import (
    find_editable_source,
    find_project_source,
)
from linuxtools.errors.exceptions import (
    InstallationError,
    ValidationError,
)
from linuxtools.filesystem.backup import (
    LinuxFileBackup,
    copytree_secure,
)
from linuxtools.filesystem.linux import _open_secure

if TYPE_CHECKING:
    from collections.abc import Callable

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.logging.base import Logger

UsbExportMode = Literal["sources", "venv"]

_MODES: tuple[UsbExportMode, ...] = ("sources", "venv")

# Identifiant Python : lettre/underscore initial, puis alphanum/_.
# `module` accepte les points (paquets imbriqués), pas `function`.
_MODULE_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
_FUNCTION_RE = re.compile(r"^[A-Za-z_]\w*$")

# Nom de répertoire projet interpolé dans install.sh : alphanumérique,
# points, tirets, underscores — pas de métacaractère shell.
_PROJ_NAME_RE = re.compile(r"^[\w.-]+$")

_IGNORE = shutil.ignore_patterns(
    ".venv",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    "*.egg-info",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    ".mypy_cache",
    "uv.lock",
)


@dataclass(frozen=True)
class UsbExportConfig:
    """Configuration d'une préparation de clé USB de déploiement.

    Attributes:
        target_dir: Répertoire final sur le support de destination
            (ex. /run/media/user/USB/mon-outil). Utilisé tel quel —
            aucun sous-répertoire n'est ajouté automatiquement (à la
            différence de l'original `UsbExportManager`, qui imposait
            un sous-répertoire `fpi/`). C'est à l'appelant de choisir
            un sous-dossier dédié pour ne pas écraser le contenu d'un
            répertoire existant.
        mode: "sources" (copie + uv tool install, réseau requis sur
            la cible) ou "venv" (venv autonome précompilé, aucun
            réseau requis).
        project_src: Racine du projet consommateur. Si None,
            détectée via discovery.find_project_source() (cwd de
            l'appelant).
        user_config_dir: Répertoire de config à copier vers
            target_dir/configs. Si None, tente project_src/configs.
        cli_entry_point: Point d'entrée "paquet.module:fonction"
            utilisé par run.sh en mode "venv" (ex.
            "fedora_post_install.cli:main"). Requis en mode "venv" —
            rupture volontaire avec l'original, qui devinait ce point
            d'entrée : `linuxtools` ne peut pas connaître le point
            d'entrée d'un projet consommateur quelconque, ce champ
            doit donc être fourni explicitement. Ignoré en mode
            "sources".
        dry_run: Si True, ne rien écrire — journaliser les
            opérations prévues.
    """

    target_dir: Path
    mode: UsbExportMode
    project_src: Path | None = None
    user_config_dir: Path | None = None
    cli_entry_point: str | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class UsbExportReport:
    """Résultat d'une préparation de clé USB.

    Attributes:
        created_paths: Chemins créés/générés (ou qui le seraient en
            dry-run).
        warnings: Avertissements non bloquants (ex. linuxtools non
            détecté en mode éditable).
    """

    created_paths: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class UsbExporter:
    """Prépare une clé USB de déploiement offline pour un projet.

    Deux modes : "sources" (copie sources + uv + script
    d'installation utilisant `uv tool install`) et "venv" (venv
    Python autonome précompilé + script de lancement, sans réseau
    requis sur la cible).

    Example:
        from pathlib import Path
        from linuxtools.deploy import UsbExportConfig, UsbExporter
        from linuxtools.commands import LinuxCommandExecutor

        exporter = UsbExporter(LinuxCommandExecutor())
        report = exporter.export(
            UsbExportConfig(
                target_dir=Path("/run/media/user/USB/mon-outil"),
                mode="sources",
            )
        )
    """

    def __init__(
        self,
        executor: CommandExecutor,
        logger: Logger | None = None,
    ) -> None:
        """Initialise l'exportateur.

        Args:
            executor: Exécuteur de commandes (uv venv, uv pip
                install).
            logger: Logger optionnel.
        """
        self._executor = executor
        self._logger = logger
        self._file_backup = LinuxFileBackup(logger)

    def export(self, config: UsbExportConfig) -> UsbExportReport:
        """Prépare la clé USB selon `config.mode`.

        Args:
            config: Paramètres de l'export.

        Returns:
            Rapport listant les chemins créés et avertissements.

        Raises:
            ValidationError: Mode invalide, cli_entry_point
                absent/mal formé en mode "venv" (module/fonction
                doivent être des identifiants Python valides), ou
                nom de projet contenant un métacaractère shell en
                mode "sources".
            FileNotFoundError: project_src introuvable (ni fourni,
                ni auto-détecté).
            InstallationError: Échec de construction du venv (mode
                "venv" uniquement).
        """
        if config.mode not in _MODES:
            raise ValidationError(
                f"Mode invalide : '{config.mode}'. Valeurs "
                f"acceptées : {', '.join(_MODES)}."
            )

        entry_point: tuple[str, str] | None = None
        if config.mode == "venv":
            entry_point = self._validate_cli_entry_point(
                config.cli_entry_point
            )

        proj = config.project_src or find_project_source()
        if proj is None or not proj.exists():
            raise FileNotFoundError(
                "Répertoire source du projet introuvable. Fournissez "
                "UsbExportConfig.project_src explicitement."
            )

        lpu = find_editable_source("linuxtools")
        warnings: list[str] = []
        if lpu is None:
            warnings.append(
                "linuxtools non détecté — installation éditable "
                "requise pour l'auto-détection."
            )

        if config.dry_run:
            lines = self._dry_run_report(config, proj, lpu)
            return UsbExportReport(
                created_paths=tuple(lines),
                warnings=tuple(warnings),
            )

        config.target_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []

        if config.mode == "sources":
            uv_missing_warning = self._copy_sources(
                config.target_dir, proj, lpu, copied
            )
            if uv_missing_warning:
                warnings.append(uv_missing_warning)
            copied.append(
                self._write_install_script(
                    config.target_dir, proj.name, lpu is not None
                )
            )
        elif entry_point is not None:
            copied.append(str(self._build_venv(config.target_dir, proj, lpu)))
            copied.append(
                self._write_run_script(config.target_dir, entry_point)
            )

        configs_copied = self._copy_configs(config, proj)
        if configs_copied:
            copied.append(configs_copied)

        return UsbExportReport(
            created_paths=tuple(copied),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _validate_cli_entry_point(
        cli_entry_point: str | None,
    ) -> tuple[str, str]:
        """Valide et découpe "module:fonction" en mode venv.

        `module` et `function` sont interpolés tels quels dans le
        run.sh généré (`-c "from {module} import {function};
        {function}()"`), exécuté via `exec`. Sans validation stricte
        par regex d'identifiant Python, une valeur telle que
        `demo.cli:main"; rm -rf /; echo "` casserait la ligne `-c`
        et permettrait l'exécution de commandes arbitraires (run.sh
        est souvent lancé avec sudo).

        Args:
            cli_entry_point: Valeur à valider, au format
                "module:fonction".

        Returns:
            Tuple (module, fonction) validés.

        Raises:
            ValidationError: Absent, vide, sans ':' unique, ou
                module/fonction non conformes à la syntaxe d'un
                identifiant Python.
        """
        if not cli_entry_point or cli_entry_point.count(":") != 1:
            raise ValidationError(
                "cli_entry_point requis au format 'module:fonction' "
                "en mode venv."
            )
        module, function = cli_entry_point.split(":", 1)
        if not _MODULE_RE.match(module) or not _FUNCTION_RE.match(function):
            raise ValidationError(
                "cli_entry_point invalide : 'module' et 'fonction' "
                "doivent être des identifiants Python valides "
                f"(reçu : {cli_entry_point!r})."
            )
        return module, function

    def _copy_sources(
        self,
        target_dir: Path,
        proj: Path,
        lpu: Path | None,
        copied: list[str],
    ) -> str | None:
        """Copie uv, le projet et linuxtools vers target_dir.

        Args:
            target_dir: Répertoire cible.
            proj: Racine du projet consommateur.
            lpu: Racine de linuxtools (ou None).
            copied: Liste des chemins créés, mise à jour en place.

        Returns:
            Avertissement si `uv` est absent du PATH, sinon None.
        """
        warning: str | None = None
        uv_bin = shutil.which("uv")
        if uv_bin:
            dst = target_dir / "uv"
            self._file_backup.backup(uv_bin, dst)
            # TOCTOU-safe : fchmod sur un fd ouvert en O_NOFOLLOW,
            # pas de second accès par chemin entre la copie et le
            # chmod (cf. filesystem/linux.py::write_text_secure).
            fd = _open_secure(dst, os.O_RDONLY, 0o000)
            try:
                # 0o755 (rwxr-xr-x) : permission standard d'un
                # exécutable, pas un 0o777 excessif — cohérent avec
                # le TOCTOU-safe ci-dessus (fchmod sur fd O_NOFOLLOW).
                os.fchmod(fd, 0o755)  # nosec B103
            finally:
                os.close(fd)
            copied.append(str(dst))
            if self._logger:
                self._logger.log_info(f"uv → {dst}")
        else:
            warning = "uv absent du PATH — à copier manuellement sur la cible."

        proj_dst = target_dir / proj.name
        self._copy_dir(proj, proj_dst)
        copied.append(str(proj_dst))

        if lpu:
            lpu_dst = target_dir / "linuxtools"
            self._copy_dir(lpu, lpu_dst)
            copied.append(str(lpu_dst))

        return warning

    def _write_install_script(
        self, target_dir: Path, proj_name: str, has_lpu: bool
    ) -> str:
        """Génère install.sh pour le mode sources.

        Args:
            target_dir: Répertoire cible.
            proj_name: Nom du répertoire du projet copié sur la clé.
            has_lpu: True si linuxtools est disponible sur la clé.

        Returns:
            Chemin du script généré (str).

        Raises:
            ValidationError: proj_name contient un caractère hors
                de [A-Za-z0-9._-] (protection contre l'injection
                shell dans install.sh).
        """
        if not _PROJ_NAME_RE.match(proj_name):
            raise ValidationError(
                f"Nom de projet invalide pour install.sh : {proj_name!r}."
            )
        # `uv tool install` crée un venv d'outil isolé qui ignore le
        # site-packages système : un `uv pip install --system`
        # préalable de linuxtools ne servirait à rien. On l'injecte
        # plutôt via --with pour qu'il soit visible dans le venv
        # d'outil, sans dépendre du réseau.
        install_line = (
            f'uv tool install --with "$USB/linuxtools" "$USB/{proj_name}"'
            if has_lpu
            else f'uv tool install "$USB/{proj_name}"'
        )
        script = f"""\
#!/usr/bin/env bash
set -euo pipefail
USB="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

if ! command -v uv &>/dev/null; then
    if [ -x "$USB/uv" ]; then
        sudo cp "$USB/uv" /usr/local/bin/uv
    else
        echo "ERREUR : uv introuvable." >&2
        exit 1
    fi
fi

{install_line}
"""
        dest_path = target_dir / "install.sh"
        deposit_content(
            self._executor,
            script,
            dest_path,
            0o755,
            is_remote=False,
            logger=self._logger,
        )
        return str(dest_path)

    def _build_venv(
        self, target_dir: Path, proj: Path, lpu: Path | None
    ) -> Path:
        """Construit un venv Python autonome sur la clé USB.

        Construit dans un répertoire temporaire (filesystem normal)
        puis copie vers la clé en déréférençant tous les symlinks
        (`lib64 -> lib`, `bin/python3 -> interpréteur`), impossibles
        à représenter sur exFAT/FAT/NTFS.

        Args:
            target_dir: Répertoire cible.
            proj: Racine du projet consommateur.
            lpu: Racine de linuxtools (ou None).

        Returns:
            Chemin du venv créé sur la clé.

        Raises:
            InstallationError: Si `uv venv` ou `uv pip install`
                échoue.
        """
        venv_dir = target_dir / "venv"
        tmp_root = Path(tempfile.mkdtemp(prefix="usbexp-venv-"))
        tmp_venv = tmp_root / "venv"
        try:
            if self._logger:
                self._logger.log_info(f"Création du venv → {venv_dir}")
            result = self._executor.run(
                CommandBuilder("uv")
                .with_args(["venv", "--python", "python3", str(tmp_venv)])
                .build()
            )
            if result.return_code != 0:
                raise InstallationError(
                    f"Échec création venv : {result.stderr[:500]}"
                )

            python_bin = str(tmp_venv / "bin" / "python3")
            packages: list[str] = []
            if lpu:
                packages.append(str(lpu))
            packages.append(str(proj))

            if self._logger:
                self._logger.log_info("Installation des paquets dans le venv…")
            result = self._executor.run(
                CommandBuilder("uv")
                .with_args(
                    [
                        "pip",
                        "install",
                        "--python",
                        python_bin,
                        *packages,
                    ]
                )
                .build()
            )
            if result.return_code != 0:
                raise InstallationError(
                    f"Échec pip install : {result.stderr[:500]}"
                )

            if self._logger:
                self._logger.log_info(f"Copie du venv → {venv_dir}")
            # ignore=None : pas de filtrage _IGNORE sur un venv
            # fraîchement construit (pas de .git/.venv à exclure).
            # follow_symlinks=True : déréférence bin/python3, lib64,
            # etc., irreprésentables sur exFAT/FAT/NTFS.
            self._copy_dir(
                tmp_venv, venv_dir, ignore=None, follow_symlinks=True
            )
            self._restore_venv_exec_bits(venv_dir)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

        return venv_dir

    def _restore_venv_exec_bits(self, venv_dir: Path) -> None:
        """Restaure les bits d'exécution perdus par copytree_secure.

        copytree_secure force 0o644 sur chaque fichier copié
        (protection TOCTOU côté écriture, cf.
        filesystem/backup.py::_copy_secure) — sans cette étape, ni
        l'interpréteur (venv/bin/python3) ni les scripts de console
        ne resteraient exécutables, et run.sh échouerait avec
        "Permission denied" sur tout support respectant les
        permissions (ext4, btrfs — le problème n'apparaît pas sur
        FAT/exFAT, qui ignorent les bits Unix).

        Args:
            venv_dir: Racine du venv copié sur la clé.
        """
        bin_dir = venv_dir / "bin"
        if not bin_dir.is_dir():
            return
        for entry in bin_dir.iterdir():
            if not entry.is_file():
                continue
            # TOCTOU-safe : fchmod sur un fd ouvert en O_NOFOLLOW.
            fd = _open_secure(entry, os.O_RDONLY, 0o000)
            try:
                # 0o755 (rwxr-xr-x) : permission standard d'un
                # exécutable de venv, pas un 0o777 excessif.
                os.fchmod(fd, 0o755)  # nosec B103
            finally:
                os.close(fd)
        if self._logger:
            self._logger.log_info(f"Bits d'exécution restaurés → {bin_dir}")

    def _write_run_script(
        self, target_dir: Path, entry_point: tuple[str, str]
    ) -> str:
        """Génère run.sh pour le mode venv.

        Args:
            target_dir: Répertoire cible.
            entry_point: Tuple (module, fonction) déjà validés par
                _validate_cli_entry_point (identifiants Python —
                sûrs pour interpolation dans la commande shell).

        Returns:
            Chemin du script généré (str).
        """
        module, function = entry_point
        script = f"""\
#!/usr/bin/env bash
set -euo pipefail
USB="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

exec "$USB/venv/bin/python3" \\
    -c "from {module} import {function}; {function}()" -- "$@"
"""
        dest_path = target_dir / "run.sh"
        deposit_content(
            self._executor,
            script,
            dest_path,
            0o755,
            is_remote=False,
            logger=self._logger,
        )
        return str(dest_path)

    def _copy_dir(
        self,
        src: Path,
        dst: Path,
        *,
        ignore: Callable[[str, list[str]], set[str]] | None = _IGNORE,
        follow_symlinks: bool = False,
    ) -> str:
        """Copie src vers dst, en écrasant dst s'il existe déjà.

        Supprime dst au préalable s'il existe déjà, avant de
        déléguer à copytree_secure (dirs_exist_ok=False) : rend un
        second export() sur une même cible idempotent au lieu de
        lever FileExistsError.

        Args:
            src: Répertoire source.
            dst: Répertoire destination.
            ignore: Callable de filtrage compatible
                shutil.ignore_patterns (défaut : _IGNORE, exclut
                .venv/.git/__pycache__/etc.). None pour tout copier.
            follow_symlinks: Transmis à copytree_secure (défaut
                False).

        Returns:
            Chemin de la destination (str).
        """
        if dst.exists():
            shutil.rmtree(dst)
        copytree_secure(
            src, dst, ignore=ignore, follow_symlinks=follow_symlinks
        )
        if self._logger:
            self._logger.log_info(f"{src} → {dst}")
        return str(dst)

    def _copy_configs(self, config: UsbExportConfig, proj: Path) -> str | None:
        """Copie les configs utilisateur ou projet vers target_dir.

        Priorité à `config.user_config_dir` s'il existe, sinon
        `proj/configs` s'il existe, sinon rien (cas normal, pas
        d'avertissement).

        Args:
            config: Configuration de l'export.
            proj: Racine du projet consommateur.

        Returns:
            Chemin de configs/ sur la clé (str), ou None si aucune
            source de configuration n'a été trouvée.
        """
        if config.user_config_dir and config.user_config_dir.exists():
            return self._copy_dir(
                config.user_config_dir, config.target_dir / "configs"
            )
        configs_src = proj / "configs"
        if configs_src.exists():
            return self._copy_dir(configs_src, config.target_dir / "configs")
        return None

    def _dry_run_report(
        self,
        config: UsbExportConfig,
        proj: Path,
        lpu: Path | None,
    ) -> list[str]:
        """Logue et retourne la liste des opérations prévues.

        Args:
            config: Configuration de l'export.
            proj: Racine du projet consommateur.
            lpu: Racine de linuxtools (ou None).

        Returns:
            Liste des lignes de rapport.
        """
        uv_bin = shutil.which("uv")
        configs_src = (
            str(config.user_config_dir)
            if config.user_config_dir
            else f"{proj}/configs"
        )
        lines: list[str] = [
            f"[dry-run] Cible   : {config.target_dir}",
            f"[dry-run] Mode    : {config.mode}",
            f"[dry-run] Projet  : {proj}",
            f"[dry-run] LPU     : {lpu or '(non détecté)'}",
            f"[dry-run] Configs : {configs_src}",
        ]
        if config.mode == "sources":
            if uv_bin:
                lines.append(f"[dry-run] uv      : {uv_bin}")
            else:
                lines.append("[dry-run] uv      : (absent du PATH)")
            lines.append(f"[dry-run] Crée  : {config.target_dir}/{proj.name}/")
            lines.append(
                f"[dry-run] Crée  : {config.target_dir}/linuxtools/"
                if lpu
                else "[dry-run] LPU   : (ignoré)"
            )
            lines.append(f"[dry-run] Crée  : {config.target_dir}/configs/")
            lines.append(f"[dry-run] Génère: {config.target_dir}/install.sh")
        else:
            lines.append(f"[dry-run] Construit : {config.target_dir}/venv/")
            lines.append(f"[dry-run] Crée     : {config.target_dir}/configs/")
            lines.append(f"[dry-run] Génère   : {config.target_dir}/run.sh")
        if self._logger:
            for line in lines:
                self._logger.log_info(line)
        return lines
