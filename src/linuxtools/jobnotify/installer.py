"""Installeur d'un job systemd notifié (artefacts, report, retrait).

Amène le poste à l'état voulu pour un `NotifiedJob`, ou le retire. Cinq
artefacts, plus le dossier d'état persistant :

    1. le descripteur JSON du job (`NotifiedJob.to_descriptor`) ;
    2. le runtime (copie exacte de `runtime.py`, lu comme ressource du paquet) ;
    3. le service compagnon qui tient le verrou `systemd-inhibit` (si `lock`) ;
    4. le drop-in du service surveillé (début, instantané, fin) ;
    5. l'entrée XDG autostart qui rattrape les notifications manquées.

Ordre d'écriture : descripteur, runtime, unités, autostart, puis UN seul
`daemon-reload`. Les textes d'unité ne sont construits que des champs validés du
job et du `home` contrôlé : aucune chaîne libre n'y entre. Le retrait ne
supprime que des chemins constants (jamais de `rmtree`) ; les dossiers ne
disparaissent que vides, car les dossiers parents sont partagés entre jobs.
"""

import contextlib
import json
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final

from linuxtools.filesystem.linux import write_text_secure
from linuxtools.jobnotify.runtime import (
    ACTIVE_STATES,
    WATCHED_RUNNING_STATES,
    parse_descriptor,
)
from linuxtools.jobnotify.spec import FingerprintProbe, NotifiedJob
from linuxtools.logging.base import Logger
from linuxtools.systemd.executor import SystemdExecutor, UserSystemdExecutor

_PYTHON: Final = "/usr/bin/python3"
_INHIBIT: Final = "/usr/bin/systemd-inhibit"
# Un `home` valide : absolu, sans espace, %, $, guillemet, antislash ni saut de
# ligne (systemd découpe et interprète ces caractères dans `Environment=`).
_HOME_RE: Final = re.compile(r"/[A-Za-z0-9_.+@:/-]*")

# Fichiers que le runtime écrit lui-même : seuls ceux-là sont retirés.
_STATE_FILES_SYSTEM: Final = ("state.json",)
_STATE_FILES_USER: Final = ("state.json", "seen")
_RUN_FILES: Final = ("lock", "before")


@dataclass(frozen=True)
class _Layout:
    """Chemins constants d'un job (écritures sous `base`, chemins réels en unités).

    Attributes:
        base: Racine des écritures (`root_dir` en système, `home` en user) ;
            exemptée du refus de lien symbolique.
        runtime: Chemin du runtime (le descripteur est `<runtime>.json`).
        runtime_real: Chemin du runtime écrit dans les unités et l'autostart.
        guard: Unité du compagnon.
        dropin_dir: Dossier du drop-in du service surveillé.
        dropin: Drop-in du service surveillé.
        desktop: Entrée XDG autostart.
        state_dir: Dossier d'état persistant.
        state_files: Fichiers d'état écrits par le runtime.
        run_dir: Dossier volatil (système seulement, créé par le runtime).
        prune_dirs: Dossiers retirés au retrait s'ils sont vides, du plus
            profond au plus haut ; les parents sont partagés entre jobs.
        file_mode: Mode du runtime.
        private_mode: Mode du descripteur.
        dir_mode: Mode des dossiers créés.
    """

    base: Path
    runtime: Path
    runtime_real: str
    guard: Path
    dropin_dir: Path
    dropin: Path
    desktop: Path
    state_dir: Path
    state_files: tuple[str, ...]
    run_dir: Path | None
    prune_dirs: tuple[Path, ...]
    file_mode: int
    private_mode: int
    dir_mode: int

    @property
    def descriptor(self) -> Path:
        """Descripteur JSON, posé à côté du runtime."""
        return self.runtime.with_name(f"{self.runtime.name}.json")


def _system_layout(job: NotifiedJob, root: Path) -> _Layout:
    """Chemins du scope système sous `root` (`/` en production)."""
    libexec = root / "usr/local/libexec" / job.owner
    runtime = libexec / f"{job.name}-notify"
    unit_dir = root / "etc/systemd/system"
    dropin_dir = unit_dir / f"{job.watched_unit}.d"
    state_dir = root / "var/lib" / job.owner / job.name
    run_dir = root / "run" / job.owner / job.name
    return _Layout(
        base=root,
        runtime=runtime,
        runtime_real=f"/usr/local/libexec/{job.owner}/{job.name}-notify",
        guard=unit_dir / f"{job.owner}-{job.name}-guard.service",
        dropin_dir=dropin_dir,
        dropin=dropin_dir / f"{job.owner}-notify.conf",
        desktop=root / "etc/xdg/autostart" / f"{job.owner}-{job.name}-notify.desktop",
        state_dir=state_dir,
        state_files=_STATE_FILES_SYSTEM,
        run_dir=run_dir,
        prune_dirs=(
            run_dir / "ids",
            run_dir,
            state_dir,
            dropin_dir,
            libexec,
            state_dir.parent,
            run_dir.parent,
        ),
        file_mode=0o644,
        private_mode=0o644,
        dir_mode=0o755,
    )


def _user_layout(job: NotifiedJob, home: Path) -> _Layout:
    """Chemins du scope user, tous sous `home`."""
    data_dir = home / ".local/share" / job.owner
    runtime = data_dir / f"{job.name}-notify"
    unit_dir = home / ".config/systemd/user"
    dropin_dir = unit_dir / f"{job.watched_unit}.d"
    state_dir = home / ".local/state" / job.owner / job.name
    return _Layout(
        base=home,
        runtime=runtime,
        runtime_real=str(runtime),
        guard=unit_dir / f"{job.owner}-{job.name}-guard.service",
        dropin_dir=dropin_dir,
        dropin=dropin_dir / f"{job.owner}-notify.conf",
        desktop=home / ".config/autostart" / f"{job.owner}-{job.name}-notify.desktop",
        state_dir=state_dir,
        state_files=_STATE_FILES_USER,
        run_dir=None,
        prune_dirs=(state_dir, dropin_dir, data_dir, state_dir.parent),
        file_mode=0o700,
        private_mode=0o600,
        dir_mode=0o700,
    )


@dataclass(frozen=True)
class _Managed:
    """Fichier géré : chemin, contenu voulu (None : doit être absent) et mode."""

    path: Path
    content: str | None
    mode: int
    is_unit: bool


@contextlib.contextmanager
def _io_errors(action: str, path: Path) -> Iterator[None]:
    """Traduit une `OSError` en `RuntimeError` chaînée.

    Raises:
        RuntimeError: Message `<action> : <chemin>`, cause = l'`OSError`.
    """
    try:
        yield
    except OSError as exc:
        msg = f"{action} : {path}"
        raise RuntimeError(msg) from exc


def _refuse_symlinks(root: Path, path: Path) -> None:
    """Refuse un lien symbolique sur un composant de `path` sous `root`.

    `root` lui-même est exempt. Un composant illisible (`PermissionError`) arrête
    la vérification sans erreur : en dessous, rien n'est atteignable.

    Raises:
        RuntimeError: Si un composant, cible comprise, est un lien symbolique.
    """
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        try:
            is_link = current.is_symlink()
        except PermissionError:
            # Dossier parent illisible : on ne peut pas le traverser, donc rien
            # n'y est modifiable non plus ; le composant n'est pas un lien.
            return
        if is_link:
            msg = f"Lien symbolique refusé : {current}"
            raise RuntimeError(msg)


def _ensure_dir(root: Path, path: Path, mode: int) -> None:
    """Crée les composants manquants de `path` sous `root`, en `mode`.

    Le mode est appliqué par `chmod` (indépendant de l'umask) ; un composant
    existant n'est jamais modifié.

    Raises:
        RuntimeError: Lien symbolique ou création refusée.
    """
    _refuse_symlinks(root, path)
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if not current.exists():
            with _io_errors("Écriture refusée", current):
                current.mkdir()
                current.chmod(mode)


def _write_atomic(
    root: Path, path: Path, content: str, mode: int, dir_mode: int
) -> None:
    """Écrit `path` de façon atomique, sans suivre de lien symbolique.

    Le contenu va dans un temporaire voisin (`O_EXCL`/`O_NOFOLLOW`, mode `mode`)
    puis `replace` le substitue à la cible : celle-ci n'est jamais vide ni
    tronquée. Un lien symbolique sur la cible est remplacé, jamais suivi.

    Raises:
        RuntimeError: Écriture refusée (lien, E/S) ; le temporaire est supprimé
            et la cible laissée intacte.
    """
    _ensure_dir(root, path.parent, dir_mode)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.unlink(missing_ok=True)  # reste d'un run interrompu
        write_text_secure(temporary, content, mode, exclusive=True)
        temporary.replace(path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        msg = f"Écriture refusée : {path}"
        raise RuntimeError(msg) from exc


def _is_conform(path: Path, content: str, mode: int) -> bool:
    """Indique si le fichier existe avec le bon contenu et le bon mode."""
    return (
        path.is_file()
        and path.read_bytes() == content.encode("utf-8")
        and stat.S_IMODE(path.stat().st_mode) == mode
    )


def _dir_conform(path: Path, mode: int) -> bool:
    """Indique si le dossier existe avec le bon mode."""
    return path.is_dir() and stat.S_IMODE(path.stat().st_mode) == mode


def _validate_home(home: Path) -> None:
    """Refuse un `home` qui ne serait pas un chemin absolu sûr pour une unité.

    Raises:
        ValueError: `home` relatif, avec `..` ou un caractère hors liste blanche.
    """
    if _HOME_RE.fullmatch(str(home)) is None or ".." in home.parts:
        msg = f"home invalide : {str(home)!r}"
        raise ValueError(msg)


class NotifiedJobInstaller:
    """Amène le poste à l'état voulu pour un `NotifiedJob` (ou le retire).

    Attributes:
        _job: Job décrit par ses données.
        _systemd: Exécuteur systemctl (daemon-reload, état des unités).
        _logger: Logger injecté.
        _layout: Chemins constants du job, selon le scope.
        _home: Dossier personnel (scope user), pour l'environnement des unités.
    """

    def __init__(
        self,
        job: NotifiedJob,
        systemd: SystemdExecutor,
        logger: Logger,
        root_dir: Path = Path("/"),
        home: Path | None = None,
    ) -> None:
        """Initialise l'installeur.

        Args:
            job: Job à installer.
            systemd: Exécuteur systemctl injecté (`UserSystemdExecutor` pour le
                scope `user`, `SystemdExecutor` pour le scope `system`).
            logger: Logger injecté.
            root_dir: Racine du système cible, scope système (`/` en production,
                `tmp_path` en test) ; écritures uniquement.
            home: Dossier personnel, scope user (`Path.home()` par défaut) ;
                tout y est écrit. Ignoré en scope système.

        Raises:
            ValueError: Si l'exécuteur ne correspond pas au scope du job, ou si
                `home` (scope user) n'est pas un chemin absolu sûr.
        """
        if isinstance(systemd, UserSystemdExecutor) != (job.scope == "user"):
            msg = f"exécuteur systemd incompatible avec le scope {job.scope!r}"
            raise ValueError(msg)
        self._job = job
        self._systemd = systemd
        self._logger = logger
        self._home: Path | None = None
        if job.scope == "user":
            self._home = Path.home() if home is None else home
            _validate_home(self._home)
            self._layout = _user_layout(job, self._home)
        else:
            self._layout = _system_layout(job, root_dir)

    @property
    def _guard_unit(self) -> str:
        """Nom de l'unité du compagnon."""
        return self._layout.guard.name

    def sync(self, *, enabled: bool, dry_run: bool) -> list[str]:
        """Amène le poste à l'état voulu.

        Args:
            enabled: True installe ou corrige, False retire.
            dry_run: Si True, liste les actions (`[dry-run] …`) sans rien
                modifier ni appeler systemd.

        Returns:
            Actions effectuées (liste vide si déjà conforme).

        Raises:
            RuntimeError: Si un chemin traverse un lien symbolique, si
                l'écriture est refusée ou si `systemctl daemon-reload` échoue.
        """
        self._refuse_all_symlinks()
        if enabled:
            actions = self._install(dry_run=dry_run)
        else:
            actions = self._remove(dry_run=dry_run)
        for action in actions:
            self._logger.log_info(f"[{self._job.name}] {action}")
        return actions

    def run_in_progress(self) -> bool:
        """Indique si un run du service surveillé est en cours (compagnon compris).

        Returns:
            True si le compagnon est `active`/`activating` ou si le service
            surveillé est `activating`/`active`/`deactivating`.
        """
        status = self._systemd.get_status
        return (
            status(self._guard_unit) in ACTIVE_STATES
            or status(self._job.watched_unit) in WATCHED_RUNNING_STATES
        )

    # ------------------------------------------------------------------
    # Contenus
    # ------------------------------------------------------------------

    def _environment_line(self) -> list[str]:
        """Ligne `Environment=` du scope user (liste vide en scope système).

        Une unité `systemd --user` n'a pas forcément `HOME` ni `XDG_STATE_HOME` :
        sans eux le runtime refuse tout (échec fermé). Les valeurs viennent du
        seul `home` validé.
        """
        if self._home is None:
            return []
        return [
            f"Environment=HOME={self._home} XDG_STATE_HOME={self._home}/.local/state"
        ]

    def _exec(self, key: str, verb: str) -> str:
        """Ligne `Exec…=` du runtime, tolérante (préfixe `-`, A-07).

        Le nom du job est passé en dernier argument : le runtime refuse un appel
        dont le job diffère de celui de son descripteur (F07, Q-07).
        """
        return (
            f"{key}=-{_PYTHON} -I {self._layout.runtime_real} {verb} {self._job.name}"
        )

    def _guard_content(self) -> str:
        """Texte exact du compagnon : verrou d'inhibition lié au service."""
        job = self._job
        why = f"--why={job.inhibit_why}"
        if " " in why:  # systemd découpe ExecStart sur les espaces
            why = f'"{why}"'
        lines = [
            "[Unit]",
            "Description=Verrou d'extinction et de veille pendant "
            f"{job.watched_unit.removesuffix('.service')}",
            f"BindsTo={job.watched_unit}",
        ]
        if job.guard_after:
            lines.append(f"After={' '.join(job.guard_after)}")
        lines += [
            "",
            "[Service]",
            "Type=exec",
            *self._environment_line(),
            f"ExecStart={_INHIBIT} --what=shutdown:sleep:handle-lid-switch "
            f"--mode=block --who={job.owner} {why} /usr/bin/sleep 3600",
            self._exec("ExecStartPost", "start"),
        ]
        return "\n".join(lines) + "\n"

    def _dropin_content(self) -> str:
        """Texte exact du drop-in du service surveillé."""
        job = self._job
        lines: list[str] = []
        if job.lock:
            lines += ["[Unit]", f"Wants={self._guard_unit}", ""]
        lines += ["[Service]", *self._environment_line()]
        if not job.lock:
            lines.append(self._exec("ExecStartPre", "start"))
        if isinstance(job.probe, FingerprintProbe):
            lines.append(self._exec("ExecStartPre", "snapshot"))
        lines.append(self._exec("ExecStopPost", "end"))
        return "\n".join(lines) + "\n"

    def _desktop_content(self) -> str:
        """Texte exact de l'entrée XDG autostart (rattrapage `login`)."""
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name=Notification {self._job.name}\n"
            f"Exec={_PYTHON} -I {self._layout.runtime_real} login {self._job.name}\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-Phase=Applications\n"
        )

    @staticmethod
    def _packaged_runtime() -> str:
        """Lit le runtime livré dans le paquet (ressource, wheel compris)."""
        resource = resources.files("linuxtools.jobnotify").joinpath("runtime.py")
        return resource.read_text(encoding="utf-8")

    def _managed(self) -> tuple[_Managed, ...]:
        """Fichiers gérés, dans l'ordre d'écriture : descripteur d'abord.

        Le compagnon, sans verrou, a un contenu `None` : un reste d'une
        installation précédente avec verrou est retiré.
        """
        layout = self._layout
        return (
            _Managed(
                layout.descriptor,
                self._job.to_descriptor(),
                layout.private_mode,
                is_unit=False,
            ),
            _Managed(
                layout.runtime,
                self._packaged_runtime(),
                layout.file_mode,
                is_unit=False,
            ),
            _Managed(
                layout.guard,
                self._guard_content() if self._job.lock else None,
                0o644,
                is_unit=True,
            ),
            _Managed(layout.dropin, self._dropin_content(), 0o644, is_unit=True),
            _Managed(layout.desktop, self._desktop_content(), 0o644, is_unit=False),
        )

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def _install(self, *, dry_run: bool) -> list[str]:
        """Installe ou corrige les artefacts et le dossier d'état."""
        self._check_descriptor()
        layout = self._layout
        pending = [m for m in self._managed() if not self._is_done(m)]
        need_state_dir = not _dir_conform(layout.state_dir, layout.dir_mode)
        if self._must_defer(unit_change=any(m.is_unit for m in pending)):
            return [self._deferred()]

        actions = [self._apply(managed, dry_run=dry_run) for managed in pending]
        if need_state_dir:
            if dry_run:
                actions.append(f"[dry-run] Créerait le dossier {layout.state_dir}")
            else:
                _ensure_dir(layout.base, layout.state_dir, layout.dir_mode)
                with _io_errors("Écriture refusée", layout.state_dir):
                    layout.state_dir.chmod(layout.dir_mode)  # corrige une dérive
                actions.append(f"Dossier prêt {layout.state_dir}")
        if any(m.is_unit for m in pending) and not dry_run:
            self._reload()
        return actions

    def _check_descriptor(self) -> None:
        """Refuse un descripteur que le runtime refuserait (échec fermé, en silence).

        Appelé avant toute écriture : le runtime ignore sans bruit un descripteur
        hors schéma, et le job ne notifierait plus jamais.

        Raises:
            ValueError: Si `parse_descriptor` rejette le descripteur produit.
        """
        if parse_descriptor(json.loads(self._job.to_descriptor())) is None:
            msg = f"descripteur de {self._job.name!r} refusé par le runtime"
            raise ValueError(msg)

    @staticmethod
    def _is_done(managed: _Managed) -> bool:
        """Indique si le fichier est déjà dans l'état voulu."""
        if managed.content is None:
            return not managed.path.exists()
        return _is_conform(managed.path, managed.content, managed.mode)

    def _apply(self, managed: _Managed, *, dry_run: bool) -> str:
        """Écrit (ou retire, si contenu `None`) un fichier ; rend l'action."""
        path = managed.path
        if managed.content is None:
            if dry_run:
                return f"[dry-run] Retirerait {path}"
            with _io_errors("Retrait refusé", path):
                path.unlink()
            return f"Retiré {path}"
        if dry_run:
            return f"[dry-run] Écrirait {path}"
        _write_atomic(
            self._layout.base,
            path,
            managed.content,
            managed.mode,
            self._layout.dir_mode,
        )
        return f"Écrit {path}"

    # ------------------------------------------------------------------
    # Retrait
    # ------------------------------------------------------------------

    def _constant_files(self) -> list[Path]:
        """Chemins constants que l'installeur ou le runtime écrivent."""
        layout = self._layout
        paths = [
            layout.descriptor,
            layout.runtime,
            layout.guard,
            layout.dropin,
            layout.desktop,
            *(layout.state_dir / name for name in layout.state_files),
        ]
        if layout.run_dir is not None:
            paths += [layout.run_dir / name for name in _RUN_FILES]
        return paths

    def _removal_plan(self) -> tuple[list[Path], list[Path]]:
        """Fichiers constants présents et dossiers qui seront vides après eux.

        Un dossier n'est retiré que si tout son contenu l'est aussi : un fichier
        étranger, ou celui d'un autre job, le préserve avec ses parents.
        """
        files = [path for path in self._constant_files() if path.exists()]
        gone = set(files)
        dirs: list[Path] = []
        for directory in self._layout.prune_dirs:
            if directory.is_dir() and all(c in gone for c in directory.iterdir()):
                gone.add(directory)
                dirs.append(directory)
        return files, dirs

    def _remove(self, *, dry_run: bool) -> list[str]:
        """Retire les chemins constants présents puis les dossiers devenus vides."""
        files, dirs = self._removal_plan()
        units = (self._layout.guard, self._layout.dropin)
        if self._must_defer(unit_change=any(path in units for path in files)):
            return [self._deferred()]

        actions: list[str] = []
        for path in (*files, *dirs):
            if dry_run:
                actions.append(f"[dry-run] Retirerait {path}")
                continue
            with _io_errors("Retrait refusé", path):
                if path in dirs:
                    path.rmdir()
                else:
                    path.unlink()
            actions.append(f"Retiré {path}")
        if any(path in units for path in files) and not dry_run:
            self._reload()
        return actions

    # ------------------------------------------------------------------
    # Communs
    # ------------------------------------------------------------------

    def _deferred(self) -> str:
        """Action rendue quand un run est en cours (unité sans `.service`)."""
        unit = self._job.watched_unit.removesuffix(".service")
        return f"différé : {unit} en cours d'exécution"

    def _must_defer(self, *, unit_change: bool) -> bool:
        """Décide de différer si une unité va changer pendant un run (R1).

        Args:
            unit_change: True si le compagnon ou le drop-in doit changer.

        Returns:
            True si un run est en cours (cf. `run_in_progress`).
        """
        if unit_change and self.run_in_progress():
            self._logger.log_info(
                f"[{self._job.name}] ⚠ Unités non modifiées, {self._deferred()}."
            )
            return True
        return False

    def _reload(self) -> None:
        """Recharge systemd après un changement d'unité.

        Raises:
            RuntimeError: Si `systemctl daemon-reload` échoue.
        """
        if not self._systemd.reload_systemd():
            msg = "systemctl daemon-reload a échoué"
            raise RuntimeError(msg)

    def _refuse_all_symlinks(self) -> None:
        """Refuse tout lien symbolique sur les chemins gérés, avant toute action."""
        layout = self._layout
        for path in (*self._constant_files(), layout.state_dir):
            _refuse_symlinks(layout.base, path)
        if layout.run_dir is not None:
            _refuse_symlinks(layout.base, layout.run_dir)
