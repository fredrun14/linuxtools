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
import sys
from collections.abc import Iterator, Mapping
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
_ENV: Final = "/usr/bin/env"
_INHIBIT: Final = "/usr/bin/systemd-inhibit"
# Un `home` ou un dossier XDG valide : absolu, sans espace, %, $, guillemet,
# antislash ni saut de ligne (systemd découpe et interprète ces caractères dans
# `Environment=`).
_HOME_RE: Final = re.compile(r"/[A-Za-z0-9_.+@:/-]*")

# Fichiers que le runtime écrit lui-même : seuls ceux-là sont retirés.
_STATE_FILES_SYSTEM: Final = ("state.json",)
_STATE_FILES_USER: Final = ("state.json", "seen")
_RUN_FILES: Final = ("lock", "before")
# `ids/<uid>` : un fichier régulier par utilisateur notifié (nom décimal), écrit
# par le runtime ; tout autre nom est étranger et préservé.
_RUN_ID_RE: Final = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class _Layout:
    """Chemins constants d'un job (écritures sous `base`, chemins réels en unités).

    Attributes:
        base: Racine des écritures (`root_dir` en système, `home` en user) ;
            exemptée du refus de lien symbolique.
        follow_links: True en scope user (F18) : un lien symbolique est suivi
            tant que sa cible résolue reste sous `base` ; False en système, où
            tout lien est refusé (frontière de privilège).
        runtime: Chemin du runtime (le descripteur est `<runtime>.json`).
        runtime_real: Chemin du runtime écrit dans les unités et l'autostart.
        guard: Unité du compagnon.
        dropin_dir: Dossier du drop-in du service surveillé.
        dropin: Drop-in du service surveillé.
        desktop: Entrée XDG autostart.
        state_dir: Dossier d'état persistant.
        state_files: Fichiers d'état écrits par le runtime.
        state_home: Valeur de `XDG_STATE_HOME` fixée dans les unités (user ; None
            en système).
        run_dir: Dossier volatil (système seulement, créé par le runtime).
        prune_dirs: Dossiers retirés au retrait s'ils sont vides, du plus
            profond au plus haut ; les parents sont partagés entre jobs.
        file_mode: Mode du runtime.
        private_mode: Mode du descripteur.
        dir_mode: Mode des dossiers créés.
    """

    base: Path
    follow_links: bool
    runtime: Path
    runtime_real: str
    guard: Path
    dropin_dir: Path
    dropin: Path
    desktop: Path
    state_dir: Path
    state_files: tuple[str, ...]
    state_home: Path | None
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
        follow_links=False,
        runtime=runtime,
        runtime_real=f"/usr/local/libexec/{job.owner}/{job.name}-notify",
        guard=unit_dir / f"{job.owner}-{job.name}-guard.service",
        dropin_dir=dropin_dir,
        dropin=dropin_dir / f"{job.owner}-notify.conf",
        desktop=root / "etc/xdg/autostart" / f"{job.owner}-{job.name}-notify.desktop",
        state_dir=state_dir,
        state_files=_STATE_FILES_SYSTEM,
        state_home=None,
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


def _xdg_dir(env: Mapping[str, str], key: str, home: Path, default: str) -> Path:
    """Dossier XDG du gestionnaire `systemd --user`, ou son repli sous `home`.

    Comme la spécification XDG, une valeur vide ou relative est ignorée. Une
    valeur citée par systemd (`$'…'`, guillemets) n'est jamais ignorée : le repli
    écrirait ailleurs que là où le gestionnaire lit (F23). Le
    dossier est écrit dans les unités et sert de base aux refus de lien
    symbolique : il doit être sûr et sous `home`.

    Args:
        env: Environnement du gestionnaire `systemd --user` (F15).
        key: Variable XDG (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`).
        home: Dossier personnel (validé).
        default: Repli relatif à `home` (`.local/share`, `.config`, ...).

    Returns:
        Le dossier à utiliser, absolu.

    Raises:
        ValueError: Valeur citée, ou absolue avec un caractère hors liste
            blanche, un `..`, ou située hors de `home`.
    """
    value = env.get(key, "")
    if value.startswith(("$", "'", '"')):
        msg = f"{key} cité par systemd (valeur à caractères spéciaux) : {value!r}"
        raise ValueError(msg)
    if not value.startswith("/"):
        return home / default
    path = Path(value)
    if (
        _HOME_RE.fullmatch(str(path)) is None
        or ".." in path.parts
        or not path.is_relative_to(home)
    ):
        msg = f"{key} invalide (absolu, sûr et sous le home attendu) : {value!r}"
        raise ValueError(msg)
    return path


def _unit_search_dir(unit_path: str, home: Path) -> Path:
    """Premier dossier d'unités persistant, sûr et sous `home` (F22).

    Ignore les dossiers volatils ou générés (`*.control`, `generator*`,
    `transient`), les entrées relatives ou hors de `home`, et celles que
    `Environment=`/les unités ne peuvent pas citer sans risque.

    Args:
        unit_path: Valeur de `systemctl --user show -p UnitPath` (séparée par
            des espaces, dans l'ordre de priorité du gestionnaire).
        home: Dossier personnel (validé).

    Returns:
        Le premier dossier retenu, ou `~/.config/systemd/user` à défaut.
    """
    for entry in unit_path.split():
        path = Path(entry)
        if (
            entry.startswith("/")
            and _HOME_RE.fullmatch(entry) is not None
            and ".." not in path.parts
            and path.is_relative_to(home)
            and not path.name.endswith(".control")
            and not path.name.startswith(("generator", "transient"))
        ):
            return path
    return home / ".config/systemd/user"


def _user_layout(
    job: NotifiedJob, home: Path, env: Mapping[str, str], unit_dir: Path
) -> _Layout:
    """Chemins du scope user : XDG du gestionnaire, unités dans `unit_dir`.

    `unit_dir` (dossier des unités et drop-ins) vient de `UnitPath` (F22) ;
    l'autostart, lu par la session, suit `XDG_CONFIG_HOME`.
    """
    data_dir = _xdg_dir(env, "XDG_DATA_HOME", home, ".local/share") / job.owner
    runtime = data_dir / f"{job.name}-notify"
    config_dir = _xdg_dir(env, "XDG_CONFIG_HOME", home, ".config")
    dropin_dir = unit_dir / f"{job.watched_unit}.d"
    state_root = _xdg_dir(env, "XDG_STATE_HOME", home, ".local/state")
    state_dir = state_root / job.owner / job.name
    return _Layout(
        base=home,
        follow_links=True,
        runtime=runtime,
        runtime_real=str(runtime),
        guard=unit_dir / f"{job.owner}-{job.name}-guard.service",
        dropin_dir=dropin_dir,
        dropin=dropin_dir / f"{job.owner}-notify.conf",
        desktop=config_dir / "autostart" / f"{job.owner}-{job.name}-notify.desktop",
        state_dir=state_dir,
        state_files=_STATE_FILES_USER,
        state_home=state_root,
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


@contextlib.contextmanager
def _tolerate_unreadable(*, dry_run: bool) -> Iterator[None]:
    """Ignore un composant illisible en dry-run, le traduit en `RuntimeError` sinon.

    Raises:
        RuntimeError: `PermissionError` hors dry-run (cause chaînée).
    """
    try:
        yield
    except PermissionError as exc:
        if not dry_run:
            msg = "Retrait impossible, composant illisible (sudo requis)"
            raise RuntimeError(msg) from exc
        # Dry-run : rien à planifier sous un composant illisible.


def _refuse_symlinks(
    root: Path,
    path: Path,
    *,
    follow_links: bool = False,
    removal: bool = False,
) -> None:
    """Refuse un lien symbolique sur un composant de `path` sous `root`.

    `root` lui-même est exempt. Un composant illisible (`PermissionError`) arrête
    la vérification sans erreur : en dessous, rien n'est atteignable.

    Avec `follow_links` (scope user, sans frontière de privilège : dotfiles gérés
    par stow), un lien est suivi mais sa cible résolue doit rester sous `root`.

    Au retrait (`removal`), un lien dont la cible est absente (stow défait) est
    traité comme un composant illisible : rien n'est planifié en dessous, donc le
    retrait du reste n'est pas bloqué (F28). Le refus demeure pour l'installation
    et pour une boucle.

    Args:
        root: Racine exemptée (`root_dir` ou `home`).
        path: Chemin à contrôler, sous `root`.
        follow_links: Accepte un lien dont la cible résolue reste sous `root`.
        removal: True au retrait : un lien à cible absente arrête la vérification.

    Raises:
        RuntimeError: Lien symbolique (scope système), lien dont la cible
            résolue sort de `root` (scope user), ou lien irrésoluble (boucle ;
            cible absente hors retrait).
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
        if not is_link:
            continue
        if not follow_links:
            msg = f"Lien symbolique refusé : {current}"
            raise RuntimeError(msg)
        try:
            target = current.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            if removal and isinstance(exc, FileNotFoundError):
                return  # cible absente : rien à retirer dessous (F28)
            # Boucle (`RuntimeError` en 3.11, `OSError` ensuite) ou cible absente :
            # un seul message, identique en dry-run et en réel (F24).
            msg = f"Lien symbolique irrésoluble (boucle ou cible absente) : {current}"
            raise RuntimeError(msg) from exc
        if not target.is_relative_to(root.resolve()):
            msg = f"Lien symbolique refusé (cible hors de {root}) : {current}"
            raise RuntimeError(msg)


def _ensure_dir(root: Path, path: Path, mode: int, *, follow_links: bool) -> None:
    """Crée les composants manquants de `path` sous `root`, en `mode`.

    Le mode est appliqué par `chmod` (indépendant de l'umask) ; un composant
    existant n'est jamais modifié.

    Raises:
        RuntimeError: Lien symbolique (cf. `_refuse_symlinks`) ou création refusée.
    """
    _refuse_symlinks(root, path, follow_links=follow_links)
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if not current.exists():
            with _io_errors("Écriture refusée", current):
                current.mkdir()
                current.chmod(mode)


def _write_atomic(layout: _Layout, path: Path, content: str, mode: int) -> None:
    """Écrit `path` de façon atomique, sans suivre de lien symbolique final.

    Le contenu va dans un temporaire voisin (`O_EXCL`/`O_NOFOLLOW`, mode `mode`)
    puis `replace` le substitue à la cible : celle-ci n'est jamais vide ni
    tronquée. Un lien symbolique sur la cible est remplacé, jamais suivi (y
    compris en scope user, où seuls les dossiers parents peuvent être des liens).

    Raises:
        RuntimeError: Écriture refusée (lien, E/S) ; le temporaire est supprimé
            et la cible laissée intacte.
    """
    _ensure_dir(
        layout.base, path.parent, layout.dir_mode, follow_links=layout.follow_links
    )
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


def _is_root() -> bool:
    """Indique si le processus tourne en root (point d'injection des tests)."""
    return os.geteuid() == 0


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

    Note:
        En scope `user`, le retrait ne touche pas `$XDG_RUNTIME_DIR/<owner>/<job>`
        (`lock`, `id`, `before`) : c'est un tmpfs de session, vidé à la
        déconnexion, et les fichiers périmés sont ignorés par le runtime.
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
            ValueError: Si l'exécuteur ne correspond pas au scope du job, si
                `home` (scope user) n'est pas un chemin absolu sûr, si
                l'installeur tourne en root en scope user, ou si un dossier XDG du
                gestionnaire `systemd --user` est dangereux ou hors de `home`.

        Note:
            En scope `user`, les `XDG_DATA_HOME`, `XDG_CONFIG_HOME` et
            `XDG_STATE_HOME` viennent de `systemctl --user show-environment`
            (exécuteur injecté), jamais de l'environnement de l'installeur ni de
            la session (F15) ; à défaut, les emplacements par défaut sous `home`.
            Le dossier des unités et drop-ins vient de `show -p UnitPath` (F22).
        """
        if isinstance(systemd, UserSystemdExecutor) != (job.scope == "user"):
            msg = f"exécuteur systemd incompatible avec le scope {job.scope!r}"
            raise ValueError(msg)
        self._job = job
        self._systemd = systemd
        self._logger = logger
        if job.scope == "user":
            if _is_root():
                msg = (
                    "scope user : lancer l'installeur en tant que l'utilisateur "
                    "concerné, pas en root (il viserait /root et le gestionnaire "
                    "systemd de root)"
                )
                raise ValueError(msg)
            user_home = Path.home() if home is None else home
            _validate_home(user_home)
            manager_env = self._manager_environment()
            unit_dir = _unit_search_dir(self._manager_unit_path(), user_home)
            self._layout = _user_layout(job, user_home, manager_env, unit_dir)
        else:
            self._layout = _system_layout(job, root_dir)

    def _manager_environment(self) -> Mapping[str, str]:
        """Environnement du gestionnaire `systemd --user` (vide s'il est illisible).

        Un échec n'est pas masqué : il est journalisé, et les emplacements par
        défaut sous `home` s'appliquent (jamais `os.environ`).
        """
        try:
            return self._systemd.show_environment()
        except RuntimeError as exc:
            self._logger.log_warning(
                f"[{self._job.name}] environnement du gestionnaire systemd --user "
                f"illisible ({exc}) : emplacements XDG par défaut sous le home"
            )
            return {}

    def _manager_unit_path(self) -> str:
        """`UnitPath` du gestionnaire `systemd --user` (vide s'il est illisible).

        `show-environment` ne donne pas le chemin de recherche des unités (F22) :
        seule cette propriété dit où le gestionnaire lit. Un échec est journalisé,
        et le dossier par défaut sous `home` s'applique ; la post-condition
        d'après `daemon-reload` détecte alors une unité hors chemin.
        """
        try:
            return self._systemd.show_property("UnitPath")
        except RuntimeError as exc:
            self._logger.log_warning(
                f"[{self._job.name}] UnitPath du gestionnaire systemd --user "
                f"illisible ({exc}) : dossier d'unités par défaut sous le home"
            )
            return ""

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
        self._refuse_all_symlinks(removal=not enabled)
        if enabled:
            actions = self._install(dry_run=dry_run)
        else:
            actions = self._remove(dry_run=dry_run)
        return actions

    def _note(self, actions: list[str], action: str) -> None:
        """Ajoute `action` à la liste rendue et la journalise aussitôt (F29).

        Une étape suivante qui échoue ne fait donc pas perdre ce qui a déjà été
        fait.
        """
        actions.append(action)
        self._logger.log_info(f"[{self._job.name}] {action}")

    def run_in_progress(self) -> bool:
        """Indique si un run du service surveillé est en cours (compagnon compris).

        Returns:
            True si le compagnon est `active`/`activating` ou si le service
            surveillé est `activating`/`active`/`deactivating`.
        """
        # Le compagnon est interrogé même sans verrou (contrairement au runtime) :
        # après un passage verrou -> sans verrou, un ancien compagnon peut rester
        # actif, et son unité (encore sur le poste) ne doit pas changer sous lui.
        status = self._systemd.get_status
        return (
            status(self._guard_unit) in ACTIVE_STATES
            or status(self._job.watched_unit) in WATCHED_RUNNING_STATES
        )

    # ------------------------------------------------------------------
    # Contenus
    # ------------------------------------------------------------------

    @property
    def _start_in_guard(self) -> bool:
        """Vrai si le compagnon porte la notification de début (verrou système).

        En scope user le verrou dépend de polkit (Q-04) et peut être refusé : le
        compagnon échouerait et le début serait perdu. Il n'y fait donc qu'inhiber,
        et le drop-in porte le début (`ExecStartPre=-`), comme sans verrou (F04).
        """
        return self._job.lock and self._job.scope == "system"

    def _environment_line(self) -> list[str]:
        """Ligne `Environment=` du scope user (liste vide en scope système).

        Une unité `systemd --user` n'a pas forcément `XDG_STATE_HOME` : sans lui
        le runtime ne sait pas où écrire (`HOME` est défini par le gestionnaire
        user, il n'est donc pas répété). La valeur est celle que résout
        l'installeur d'après le gestionnaire ; l'autostart la fixe aussi dans son
        `Exec` (`_desktop_exec`), donc `start`, `end` et `login` lisent au même
        endroit quelle que soit la session (F03, F15).
        """
        state_home = self._layout.state_home
        if state_home is None:
            return []
        return [f"Environment=XDG_STATE_HOME={state_home}"]

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
            f"ExecStart={_INHIBIT} --what=shutdown:sleep:handle-lid-switch "
            f"--mode=block --who={job.owner} {why} /usr/bin/sleep 3600",
        ]
        if self._start_in_guard:
            lines.append(self._exec("ExecStartPost", "start"))
        return "\n".join(lines) + "\n"

    def _dropin_content(self) -> str:
        """Texte exact du drop-in du service surveillé."""
        job = self._job
        lines: list[str] = []
        if job.lock:
            lines += ["[Unit]", f"Wants={self._guard_unit}", ""]
        lines += ["[Service]", *self._environment_line()]
        if not self._start_in_guard:
            lines.append(self._exec("ExecStartPre", "start"))
        if isinstance(job.probe, FingerprintProbe):
            lines.append(self._exec("ExecStartPre", "snapshot"))
        lines.append(self._exec("ExecStopPost", "end"))
        return "\n".join(lines) + "\n"

    def _desktop_exec(self) -> str:
        """Ligne `Exec=` de l'autostart, racine d'état figée en scope user (F15).

        La session qui lance l'autostart n'a pas forcément le `XDG_STATE_HOME` du
        gestionnaire : `env` le fixe, comme `Environment=` pour les unités.
        """
        state_home = self._layout.state_home
        prefix = "" if state_home is None else f"{_ENV} XDG_STATE_HOME={state_home} "
        return (
            f"Exec={prefix}{_PYTHON} -I {self._layout.runtime_real} "
            f"login {self._job.name}\n"
        )

    def _desktop_content(self) -> str:
        """Texte exact de l'entrée XDG autostart (rattrapage `login`)."""
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name=Notification {self._job.name}\n"
            f"{self._desktop_exec()}"
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
        actions: list[str] = []
        if self._must_defer(unit_change=any(m.is_unit for m in pending)):
            self._note(actions, self._deferred())
            return actions

        for managed in pending:
            self._note(actions, self._apply(managed, dry_run=dry_run))
        if need_state_dir:
            if dry_run:
                self._note(actions, f"[dry-run] Créerait le dossier {layout.state_dir}")
            else:
                _ensure_dir(
                    layout.base,
                    layout.state_dir,
                    layout.dir_mode,
                    follow_links=layout.follow_links,
                )
                with _io_errors("Écriture refusée", layout.state_dir):
                    layout.state_dir.chmod(layout.dir_mode)  # corrige une dérive
                self._note(actions, f"Dossier prêt {layout.state_dir}")
        if not dry_run:
            if any(m.is_unit for m in pending):
                self._reload()
            if self._job.scope == "user":
                self._verify_loaded()
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
        _write_atomic(self._layout, path, managed.content, managed.mode)
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

    def _run_id_files(self) -> list[Path]:
        """Fichiers `ids/<uid>` que le runtime a écrits (nom décimal, réguliers).

        Un lien symbolique, un dossier ou un nom non décimal n'est jamais retiré
        (ni suivi) : il reste, avec ses parents.

        Raises:
            RuntimeError: Si `ids` lui-même est un lien symbolique (F19) : il
                n'est jamais parcouru, `iterdir()` le suivrait.
        """
        run_dir = self._layout.run_dir
        if run_dir is None:
            return []
        ids = run_dir / "ids"
        if ids.is_symlink():
            msg = f"Lien symbolique refusé : {ids}"
            raise RuntimeError(msg)
        if not ids.is_dir():
            return []
        return sorted(
            entry
            for entry in ids.iterdir()
            if _RUN_ID_RE.fullmatch(entry.name)
            and entry.is_file()
            and not entry.is_symlink()
        )

    def _removal_plan(self, *, dry_run: bool) -> tuple[list[Path], list[Path]]:
        """Fichiers constants présents et dossiers qui seront vides après eux.

        Un dossier n'est retiré que si tout son contenu l'est aussi : un fichier
        étranger, ou celui d'un autre job, le préserve avec ses parents. Un dossier
        qui est un lien symbolique (scope user, stow) n'est jamais élagué, comme
        un fichier étranger : `rmdir` d'un lien échouerait (F21).

        Un composant illisible (`/run/<owner>` en root 0700, sans sudo) : en
        dry-run, rien n'est planifié en dessous (comme `_refuse_symlinks`) ; en
        réel, on ne peut ni retirer ni garantir l'état, d'où une `RuntimeError`.

        Args:
            dry_run: True si le retrait ne sera pas appliqué.

        Raises:
            RuntimeError: Composant illisible, hors dry-run.
        """
        files: list[Path] = []
        gone: set[Path] = set()
        dirs: list[Path] = []
        for path in self._constant_files():
            with _tolerate_unreadable(dry_run=dry_run):
                if path.exists():
                    files.append(path)
        with _tolerate_unreadable(dry_run=dry_run):
            files.extend(self._run_id_files())
        gone.update(files)
        for directory in self._layout.prune_dirs:
            with _tolerate_unreadable(dry_run=dry_run):
                if (
                    directory.is_dir()
                    and not directory.is_symlink()
                    and all(c in gone for c in directory.iterdir())
                ):
                    gone.add(directory)
                    dirs.append(directory)
        return files, dirs

    def _remove(self, *, dry_run: bool) -> list[str]:
        """Retire les chemins constants présents puis les dossiers devenus vides."""
        files, dirs = self._removal_plan(dry_run=dry_run)
        units = (self._layout.guard, self._layout.dropin)
        actions: list[str] = []
        if self._must_defer(unit_change=any(path in units for path in files)):
            self._note(actions, self._deferred())
            return actions

        unit_removed = False
        try:
            for path in (*files, *dirs):
                if dry_run:
                    self._note(actions, f"[dry-run] Retirerait {path}")
                    continue
                with _io_errors("Retrait refusé", path):
                    if path in dirs:
                        path.rmdir()
                    else:
                        path.unlink()
                unit_removed = unit_removed or path in units
                self._note(actions, f"Retiré {path}")
        finally:
            # Une unité déjà retirée doit être déchargée même si une étape
            # suivante échoue (F21), sinon systemd garde l'ancienne.
            in_progress = sys.exception()
            if unit_removed:
                try:
                    self._reload()
                except RuntimeError as exc:
                    if in_progress is None:
                        raise
                    # L'erreur d'origine prime : l'échec du reload est journalisé
                    # sans la masquer (F29).
                    self._logger.log_error(
                        f"[{self._job.name}] rechargement systemd en échec après "
                        f"un retrait interrompu : {exc}"
                    )
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

    def _verify_loaded(self) -> None:
        """Vérifie que le gestionnaire user voit les unités écrites (F22, F27).

        Exécutée à chaque `sync` réel d'installation, même sans rien écrire (un
        second `sync` ne doit pas masquer une unité hors chemin). Deux contrôles :

        - structurel : le dossier des unités figure dans `UnitPath` (comparaison
          sur chemins résolus) ;
        - chargement : le drop-in figure dans `DropInPaths` de l'unité surveillée
          et, avec verrou, le compagnon a pour `FragmentPath` le fichier écrit.
          Ils ne valent que pour une unité `LoadState=loaded` : une unité
          surveillée absente ou masquée n'a aucun drop-in à rendre, d'où un
          avertissement journalisé et non une erreur.

        Raises:
            RuntimeError: Si le dossier des unités est hors de `UnitPath`, si une
                unité chargée n'a pas le fichier écrit, ou si `systemctl show`
                échoue.
        """
        layout = self._layout
        unit_dir = layout.guard.parent
        search = {
            Path(entry).resolve()
            for entry in self._systemd.show_property("UnitPath").split()
        }
        if unit_dir.resolve() not in search:
            msg = (
                f"dossier des unités {unit_dir} hors de UnitPath du gestionnaire "
                "systemd --user : les notifications n'auraient pas lieu"
            )
            raise RuntimeError(msg)
        watched = self._job.watched_unit
        if self._is_loaded(watched):
            dropins = self._systemd.show_property("DropInPaths", watched)
            if f" {layout.dropin} " not in f" {dropins} ":
                msg = (
                    f"drop-in {layout.dropin} non chargé par systemd --user : "
                    "les notifications n'auraient pas lieu"
                )
                raise RuntimeError(msg)
        if self._job.lock and self._is_loaded(self._guard_unit):
            fragment = self._systemd.show_property("FragmentPath", self._guard_unit)
            if fragment != str(layout.guard):
                msg = (
                    f"compagnon {layout.guard} non chargé par systemd --user "
                    f"(FragmentPath={fragment!r}) : dossier hors de UnitPath"
                )
                raise RuntimeError(msg)

    def _is_loaded(self, unit: str) -> bool:
        """Dit si `unit` est `LoadState=loaded`, sinon journalise un avertissement.

        Args:
            unit: Nom de l'unité interrogée.

        Returns:
            True si le gestionnaire a chargé l'unité ; False (absente, masquée…)
            après avoir journalisé l'état, sans erreur.
        """
        state = self._systemd.show_property("LoadState", unit)
        if state == "loaded":
            return True
        self._logger.log_warning(
            f"[{self._job.name}] unité {unit} non chargée par systemd --user "
            f"(LoadState={state!r}) : chargement des drop-ins non vérifié"
        )
        return False

    def _refuse_all_symlinks(self, *, removal: bool) -> None:
        """Refuse tout lien symbolique sur les chemins gérés, avant toute action.

        Args:
            removal: True au retrait (un lien à cible absente est toléré, F28).
        """
        layout = self._layout
        for path in (*self._constant_files(), layout.state_dir):
            _refuse_symlinks(
                layout.base, path, follow_links=layout.follow_links, removal=removal
            )
        if layout.run_dir is not None:
            ids = layout.run_dir / "ids"  # F19 ; run_dir lui-même en est un préfixe
            _refuse_symlinks(
                layout.base, ids, follow_links=layout.follow_links, removal=removal
            )
