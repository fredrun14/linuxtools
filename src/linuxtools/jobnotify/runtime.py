"""Runtime d'un job systemd notifié (stdlib seule, hors venv).

Ce fichier est copié tel quel sur le poste par l'installeur, une copie par job
(``<job>-notify``), puis lancé par ``/usr/bin/python3 -I`` : AUCUN import de
``linuxtools`` ni de tiers (contrat Q-01). Il lit le descripteur JSON posé à côté
de lui (``<script>.json``), écrit par ``NotifiedJob.to_descriptor``.
Appel : ``<verbe> [job]`` ; le job, s'il est donné, doit égaler celui du descripteur.
Le runtime rend toujours 0 : un échec de notification ne casse jamais le job.
"""

# stdlib uniquement : voir la docstring du module.
from __future__ import annotations

import contextlib
import enum
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import string
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, Protocol, TypedDict, TypeGuard


class Outcome(enum.StrEnum):
    """Issue d'un run surveillé."""

    SUCCESS = "success"
    SUCCESS_RESTART = "success_restart"  # réussi, redémarrage requis
    NOTHING = "nothing"  # rien à mettre à jour
    DONE_NO_DETAIL = "done_no_detail"  # terminé, historique illisible
    FAILURE = "failure"
    INTERRUPTED = "interrupted"


def compute_dnf5_outcome(
    *,
    service_result: str,
    system_stopping: bool,
    transactions: Sequence[Mapping[str, object]] | None,
    started_at: float,
    needs_restart: bool,
) -> Outcome:
    """Déduit l'issue d'un run de dnf5-automatic (table de la conception).

    Args:
        service_result: Valeur de ``$SERVICE_RESULT`` ("success", "exit-code", ...).
        system_stopping: ``systemctl is-system-running`` vaut ``stopping``.
        transactions: Entrées de ``dnf5 history list --json``, ou None si illisible.
        started_at: Epoch (s) du début du run, lu dans ``state.json``.
        needs_restart: ``dnf5 needs-restarting`` a rendu le code 1.

    Returns:
        L'issue à notifier.
    """
    if system_stopping:
        return Outcome.INTERRUPTED
    if service_result != "success":
        return Outcome.FAILURE
    if transactions is None:
        return Outcome.DONE_NO_DETAIL
    if not any(_is_run_transaction(t, started_at) for t in transactions):
        return Outcome.NOTHING
    return Outcome.SUCCESS_RESTART if needs_restart else Outcome.SUCCESS


def compute_flatpak_outcome(
    *,
    service_result: str,
    system_stopping: bool,
    has_state: bool,
    before: str | None,
    after: str | None,
) -> Outcome:
    """Déduit l'issue d'un run de flatpak-automatic (ADR empreinte).

    Args:
        service_result: Valeur de ``$SERVICE_RESULT``.
        system_stopping: ``systemctl is-system-running`` vaut ``stopping``.
        has_state: Un état ``running`` du boot courant décrit ce run.
        before: Empreinte prise avant le run, ou None si absente ou illisible.
        after: Empreinte prise après le run, ou None si illisible.

    Returns:
        INTERRUPTED, FAILURE, DONE_NO_DETAIL, NOTHING ou SUCCESS, dans cet ordre
        de priorité ; jamais SUCCESS_RESTART (Q-07).
    """
    if system_stopping:
        return Outcome.INTERRUPTED
    if service_result != "success":
        return Outcome.FAILURE
    if not has_state or before is None or after is None:
        return Outcome.DONE_NO_DETAIL
    return Outcome.NOTHING if before == after else Outcome.SUCCESS


def compute_fwupd_outcome(
    *, service_result: str, system_stopping: bool, pending: bool | None
) -> Outcome:
    """Déduit l'issue d'un run de fwupd-automatic.

    Args:
        service_result: Valeur de ``$SERVICE_RESULT``.
        system_stopping: ``systemctl is-system-running`` vaut ``stopping``.
        pending: Un périphérique attend le redémarrage (``UpdateState == 4``),
            ou None si l'état est illisible.

    Returns:
        INTERRUPTED, SUCCESS_RESTART, FAILURE, DONE_NO_DETAIL ou NOTHING, dans
        cet ordre de priorité ; jamais SUCCESS.
    """
    if system_stopping:
        return Outcome.INTERRUPTED
    # Avant l'échec : une capsule déjà en attente reste à signaler même si un
    # nouvel ``update`` a échoué.
    if pending is True:
        return Outcome.SUCCESS_RESTART
    if service_result != "success":
        return Outcome.FAILURE
    if pending is None:
        return Outcome.DONE_NO_DETAIL
    return Outcome.NOTHING


def _is_run_transaction(transaction: object, started_at: float) -> bool:
    """Indique si une entrée de l'historique appartient au run de dnf automatic.

    Une entrée mal formée (pas un mapping, clé absente, type inattendu) est
    ignorée : elle ne lève jamais d'exception.

    Args:
        transaction: Entrée de ``dnf5 history list --json``.
        started_at: Epoch (s) du début du run.

    Returns:
        True si la transaction date du run et vient de ``dnf5 automatic``.
    """
    if not isinstance(transaction, Mapping):
        return False
    start_time = transaction.get("start_time")
    command_line = transaction.get("command_line")
    if isinstance(start_time, bool) or not isinstance(start_time, int):
        return False
    if not isinstance(command_line, str):
        return False
    # Le sous-commande est le 2e mot (le 1er est le binaire, éventuellement
    # en chemin absolu) : « dnf install dnf5-plugin-automatic » n'en est pas un.
    return start_time >= started_at and command_line.split()[1:2] == ["automatic"]


# ---------------------------------------------------------------------------
# T2 : sessions graphiques et envoi des notifications
# ---------------------------------------------------------------------------

# Chemins ABSOLUS : le hook tourne en root, jamais de résolution par $PATH.
LOGINCTL = "/usr/bin/loginctl"
RUNUSER = "/usr/bin/runuser"
ENV_BIN = "/usr/bin/env"
BUSCTL = "/usr/bin/busctl"
SYSTEMCTL = "/usr/bin/systemctl"
DNF5 = "/usr/bin/dnf5"
FWUPDMGR = "/usr/bin/fwupdmgr"

CALL_TIMEOUT_S = 5  # durée maximale (s) de chaque commande lancée par le hook
TOTAL_BUDGET_S = 30  # durée maximale (s) d'un verbe : reste sous TimeoutStopSec (90)
_MIN_UID = 1000  # jamais root ni un compte système
_MAX_UID = 2**32 - 2  # 2**32 - 1 est l'uid invalide (« -1 »)
_MAX_NOTIFICATION_ID = 2**32 - 1  # un ID de notification est un uint32 non nul
_MAX_ID_FILE_SIZE = 16  # octets : largement assez pour un uint32 décimal
_GRAPHICAL_TYPES = frozenset({"wayland", "x11"})
# États loginctl d'une session utilisable (« closing » est en fin de vie).
_LIVE_STATES = frozenset({"active", "online"})
_URGENCY_NORMAL = "1"
_URGENCY_CRITICAL = "2"

# (argv, délai en secondes) -> (code de retour, sortie standard)
Runner = Callable[[Sequence[str], float], tuple[int, str]]


def default_runner(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Runner réel : le SEUL endroit du hook qui lance un sous-processus.

    Sans shell, délai obligatoire, sortie lue comme du texte (les octets
    invalides sont remplacés plutôt que de lever).

    Args:
        argv: Commande et arguments (liste, chemin absolu en tête).
        timeout: Délai maximal en secondes.

    Returns:
        ``(code de retour, sortie standard)``.

    Raises:
        subprocess.TimeoutExpired: Si le délai est dépassé.
        OSError: Si le programme est introuvable ou non exécutable.
    """
    # S603 : argv en liste, sans shell, binaire en chemin absolu (jamais de $PATH).
    completed = subprocess.run(  # noqa: S603
        list(argv),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout


@dataclass(frozen=True)
class Session:
    """Utilisateur à notifier : un uid et le nom de sa session graphique locale."""

    uid: int
    user: str


def _write_stderr(message: str) -> int:
    """Écrit sur le stderr courant (résolu à l'appel : journal de systemd)."""
    return sys.stderr.write(message)


@dataclass(frozen=True)
class Descriptor:
    """Descripteur validé d'un job : miroir des champs de ``NotifiedJob``.

    Attributes:
        name: Nom du job ; donne les chemins d'état et le préfixe du journal.
        owner: Application propriétaire ; donne les chemins et le nom d'émetteur.
        watched_unit: Service surveillé (``dnf5-automatic.service``).
        scope: ``system`` ou ``user``.
        start_texts: (résumé, corps) de la notification de lancement.
        end_texts: (résumé, corps) par issue atteignable.
        lock: Un verrou d'inhibition (compagnon) est posé pendant le run.
        probe_kind: Clé du catalogue de sondes (``none``, ``fingerprint``, ``dnf5``,
            ``fwupd``).
        probe_argv: Commande de l'instantané (sonde ``fingerprint`` seulement).
        icon: Nom d'icône de la notification.
        inhibit_why: Motif affiché par l'inhibiteur (utile à l'installeur).
        guard_after: Unités après lesquelles démarre le compagnon (idem).
    """

    name: str
    owner: str
    watched_unit: str
    scope: str
    start_texts: tuple[str, str]
    end_texts: Mapping[Outcome, tuple[str, str]]
    lock: bool
    probe_kind: str
    probe_argv: tuple[str, ...]
    icon: str
    inhibit_why: str
    guard_after: tuple[str, ...]

    @property
    def guard_unit(self) -> str:
        """Service compagnon qui porte l'inhibiteur (``<owner>-<name>-guard``)."""
        return f"{self.owner}-{self.name}-guard.service"


def _default_trusted_uids() -> frozenset[int]:
    """Propriétaires admis pour le descripteur : root et l'utilisateur courant."""
    return frozenset({0, os.geteuid()})


@dataclass
class Ctx:
    """Dépendances injectées du runtime (seams de test)."""

    runner: Runner
    root_dir: Path = Path("/")
    env: Mapping[str, str] = field(default_factory=dict)
    # Horloge murale : horodatage de l'état (comparé à des mtime de fichiers).
    now: Callable[[], float] = time.time
    # Horloge monotone : mesure du budget (insensible aux sauts de l'horloge murale).
    monotonic: Callable[[], float] = time.monotonic
    geteuid: Callable[[], int] = os.geteuid
    # Métadonnées d'un binaire sans suivre le lien final (contrôle des sondes, F06).
    lstat: Callable[[str], os.stat_result] = os.lstat
    # Pause entre deux essais non bloquants du verrou (seam de test).
    sleep: Callable[[float], None] = time.sleep
    stderr: Callable[[str], object] = _write_stderr
    # Instant monotone de début du verbe, posé par ``main`` ;
    # None : pas de budget imposé.
    started: float | None = None
    # Script en cours : le descripteur est ``<script>.json``, à côté de lui.
    script: Path = Path(__file__)
    # Propriétaires acceptés pour le fichier descripteur (root en production).
    trusted_uids: frozenset[int] = field(default_factory=_default_trusted_uids)
    # Descripteur du job, posé par ``main`` (ou injecté par un test).
    descriptor: Descriptor | None = None


def _job(ctx: Ctx) -> Descriptor:
    """Rend le descripteur du contexte.

    Raises:
        RuntimeError: Si aucun descripteur n'a été chargé (``main`` en pose un).
    """
    if ctx.descriptor is None:
        msg = "aucun descripteur chargé"
        raise RuntimeError(msg)
    return ctx.descriptor


def _systemctl(ctx: Ctx, *args: str) -> list[str]:
    """Commande ``systemctl`` du gestionnaire du job (``--user`` en scope user)."""
    scope = ["--user"] if _is_user_scope(ctx) else []
    return [SYSTEMCTL, *scope, *args]


def _warn(ctx: Ctx, message: str) -> None:
    """Écrit un diagnostic sur stderr, préfixé par ``<job>-notify``."""
    prefix = f"{ctx.descriptor.name}-notify" if ctx.descriptor else ctx.script.stem
    ctx.stderr(f"{prefix} : {message}\n")


def _call(ctx: Ctx, argv: Sequence[str]) -> tuple[int, str] | None:
    """Lance une commande via le runner injecté, sans jamais lever.

    Args:
        ctx: Dépendances du hook.
        argv: Commande et arguments (liste, chemin absolu en tête).

    Returns:
        ``(code de retour, sortie)``, ou None si la commande n'a pas pu tourner
        (délai dépassé, programme absent, budget épuisé) ; le diagnostic va alors
        sur stderr.
    """
    if ctx.started is not None and ctx.monotonic() - ctx.started >= TOTAL_BUDGET_S:
        _warn(ctx, f"budget de temps dépassé, {argv[0]} sauté")
        return None
    try:
        return ctx.runner(argv, CALL_TIMEOUT_S)
    except (subprocess.SubprocessError, OSError) as exc:
        _warn(ctx, f"{argv[0]} inutilisable ({exc})")
        return None


def _parse_uid(raw: str) -> int | None:
    """Convertit la valeur ``User`` de loginctl en uid utilisable.

    Args:
        raw: Valeur brute lue dans la sortie de ``loginctl show-session``.

    Returns:
        L'uid s'il est numérique et compris entre ``_MIN_UID`` et ``_MAX_UID``,
        sinon None (root, compte système, valeur invalide).
    """
    if not (raw.isascii() and raw.isdigit()):
        return None
    uid = int(raw)
    return uid if _MIN_UID <= uid <= _MAX_UID else None


def _show_session(ctx: Ctx, session_id: str) -> Session | None:
    """Renvoie l'utilisateur d'une session si elle est graphique et locale.

    Args:
        ctx: Dépendances du hook.
        session_id: Identifiant de session issu de ``loginctl list-sessions``.

    Returns:
        La session à notifier, ou None si elle ne convient pas (dont une session
        en fin de vie, ``State=closing``).
    """
    argv = [LOGINCTL, "show-session", session_id]
    for prop in ("State", "Type", "Class", "Remote", "Name", "User"):
        argv += ["-p", prop]
    result = _call(ctx, argv)
    if result is None:
        return None
    if result[0] != 0:
        _warn(ctx, f"session {session_id} illisible")
        return None
    props = dict(line.split("=", 1) for line in result[1].splitlines() if "=" in line)
    uid = _parse_uid(props.get("User", ""))
    user = props.get("Name", "")
    if (
        props.get("State") not in _LIVE_STATES
        or props.get("Type") not in _GRAPHICAL_TYPES
        or props.get("Class") != "user"
        or props.get("Remote") != "no"
        or uid is None
        or not user
    ):
        return None
    return Session(uid=uid, user=user)


def list_graphical_sessions(ctx: Ctx) -> list[Session]:
    """Liste les utilisateurs ayant une session graphique locale.

    Le nom et l'uid ne viennent que de ``loginctl`` ; une session de root ou
    d'un uid invalide est ignorée. Le résultat est dédupliqué par uid.

    Args:
        ctx: Dépendances du hook.

    Returns:
        Les sessions à notifier (liste vide si aucune ou si loginctl échoue).
    """
    result = _call(ctx, [LOGINCTL, "list-sessions", "--no-legend"])
    if result is None:
        return []
    if result[0] != 0:
        _warn(ctx, "loginctl list-sessions a échoué")
        return []
    sessions: dict[int, Session] = {}
    for line in result[1].splitlines():
        fields = line.split()
        # Un identifiant qui ressemblerait à une option n'est jamais transmis.
        if not fields or not fields[0].isalnum():
            continue
        session = _show_session(ctx, fields[0])
        if session is not None:
            sessions.setdefault(session.uid, session)
    return list(sessions.values())


def _parse_notify_reply(output: str) -> int | None:
    """Extrait l'ID de la réponse ``u <id>`` de ``busctl call ... Notify``.

    Args:
        output: Sortie standard de busctl.

    Returns:
        L'ID de notification, ou None si la réponse n'a pas la forme attendue.
    """
    fields = output.split()
    if len(fields) != _NOTIFY_REPLY_FIELDS or fields[0] != "u":
        return None
    raw = fields[1]
    return int(raw) if raw.isascii() and raw.isdigit() else None


def _notify_command(
    ctx: Ctx,
    replaces_id: int,
    summary: str,
    body: str,
    urgency: str,
) -> list[str]:
    """Construit l'appel ``busctl --user ... Notify`` (partagé root / utilisateur).

    Args:
        ctx: Dépendances du runtime (descripteur : émetteur et icône).
        replaces_id: ID de la notification à remplacer (0 : nouvelle).
        summary: Résumé (constante du module).
        body: Corps (constante du module).
        urgency: Urgence freedesktop (``"1"`` normale, ``"2"`` critique).

    Returns:
        L'argv de busctl, sans shell, chemin absolu en tête.
    """
    return [
        BUSCTL,
        "--user",
        "call",
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
        "Notify",
        "susssasa{sv}i",
        _job(ctx).owner,
        str(replaces_id),
        _job(ctx).icon,
        summary,
        body,
        "0",  # aucune action
        "1",  # un seul hint ...
        "urgency",
        "y",
        urgency,
        "0",  # expire = 0 : reste affichée jusqu'à lecture
    ]


def _deliver(ctx: Ctx, argv: Sequence[str], recipient: str) -> int | None:
    """Lance un appel Notify et en extrait l'ID, en journalisant l'échec.

    Args:
        ctx: Dépendances du hook.
        argv: Commande complète à lancer.
        recipient: Nom du destinataire, pour le message d'erreur.

    Returns:
        L'ID renvoyé par le serveur de notifications, ou None si l'envoi échoue.
    """
    result = _call(ctx, argv)
    if result is None:
        return None
    notification_id = _parse_notify_reply(result[1]) if result[0] == 0 else None
    if notification_id is None:
        _warn(ctx, f"envoi impossible pour {recipient}")
    return notification_id


def send_notification(  # noqa: PLR0913 (signature portée du hook : verbes T2/T3)
    ctx: Ctx,
    session: Session,
    *,
    summary: str,
    body: str,
    replaces_id: int = 0,
    persistent: bool,
) -> int | None:
    """Envoie une notification dans la session de l'utilisateur.

    Args:
        ctx: Dépendances du hook.
        session: Utilisateur destinataire.
        summary: Résumé (constante du module, jamais une donnée externe).
        body: Corps (constante du module, jamais une donnée externe).
        replaces_id: ID de la notification à remplacer (0 : nouvelle).
        persistent: True pour le lancement (urgence critique), False pour le
            résultat (urgence normale).

    Returns:
        L'identifiant renvoyé par le serveur de notifications, ou None si
        l'envoi échoue.
    """
    if _is_user_scope(ctx):
        # Destinataire unique (le propriétaire) : envoi direct, sans runuser.
        return _send_to_self(
            ctx, summary, body, persistent=persistent, replaces_id=replaces_id
        )
    uid = session.uid
    urgency = _URGENCY_CRITICAL if persistent else _URGENCY_NORMAL
    # Argv en liste, sans shell : le nom d'utilisateur reste UN seul argument.
    argv = [
        RUNUSER,
        "-u",
        session.user,
        "--",
        ENV_BIN,
        "-i",  # environnement vidé : rien du service root ne passe à l'utilisateur
        f"XDG_RUNTIME_DIR=/run/user/{uid}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
        *_notify_command(ctx, replaces_id, summary, body, urgency),
    ]
    return _deliver(ctx, argv, session.user)


def _read_regular_stamped(
    path: Path, *, max_size: int, owner: int | None = None
) -> tuple[bytes, float] | None:
    """Lit un fichier qui peut venir d'un utilisateur, sans se laisser piéger.

    O_NOFOLLOW refuse un lien symbolique, O_NONBLOCK empêche un FIFO de bloquer
    l'ouverture ; le fichier doit être régulier et d'au plus ``max_size`` octets.

    Args:
        path: Fichier à lire.
        max_size: Taille maximale acceptée, en octets.
        owner: Propriétaire exigé (None : pas de contrôle).

    Returns:
        Les octets lus (au plus ``max_size`` + 1) et la date de modification du
        fichier, ou None si le fichier est absent ou hostile (lien symbolique,
        non régulier, autre propriétaire, trop gros, erreur de lecture).
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or (owner is not None and info.st_uid != owner)
            or info.st_size > max_size
        ):
            return None
        return os.read(fd, max_size + 1), info.st_mtime
    except OSError:
        return None
    finally:
        os.close(fd)


def _read_regular(
    path: Path, *, max_size: int, owner: int | None = None
) -> bytes | None:
    """Comme ``_read_regular_stamped`` mais sans la date de modification."""
    result = _read_regular_stamped(path, max_size=max_size, owner=owner)
    return None if result is None else result[0]


def _read_user_id_stamped(ctx: Ctx, session: Session) -> tuple[int, float] | None:
    """Lit l'ID écrit par l'utilisateur et la date d'écriture du fichier.

    Returns:
        ``(id, mtime)`` si le fichier est valide, sinon None.
    """
    path = _user_id_target(ctx, session.uid).path
    result = _read_regular_stamped(path, max_size=_MAX_ID_FILE_SIZE, owner=session.uid)
    if result is None:
        return None
    notification_id = _parse_id_file(result[0])
    return None if notification_id is None else (notification_id, result[1])


def read_user_notification_id(ctx: Ctx, session: Session) -> int | None:
    """Lit l'ID écrit par l'utilisateur pour la notification « en cours ».

    Args:
        ctx: Dépendances du hook.
        session: Utilisateur propriétaire attendu du fichier.

    Returns:
        L'ID s'il est valide, sinon None (fichier absent ou hostile : lien
        symbolique, non régulier, mauvais propriétaire, trop gros, hors bornes).
    """
    stamped = _read_user_id_stamped(ctx, session)
    return None if stamped is None else stamped[0]


def _parse_id_file(raw: bytes) -> int | None:
    """Valide le contenu du fichier d'ID écrit par l'utilisateur.

    Args:
        raw: Octets lus (au plus ``_MAX_ID_FILE_SIZE`` + 1).

    Returns:
        L'ID s'il s'agit d'un entier décimal entre 1 et 2**32 - 1, sinon None.
    """
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not (text.isascii() and text.isdigit()):
        return None
    value = int(text)
    return value if 1 <= value <= _MAX_NOTIFICATION_ID else None


# ---------------------------------------------------------------------------
# T3 : état, verbes start / end / login, main
# ---------------------------------------------------------------------------

# Chemins relatifs à ``Ctx.root_dir`` (``/`` en production, ``tmp_path`` en test) :
# dérivés de ``owner`` et ``name`` du descripteur.
_BOOT_ID_RELATIVE = Path("proc/sys/kernel/random/boot_id")

_MAX_STATE_SIZE = 4096  # octets : l'état tient en quelques dizaines d'octets
_MAX_SEEN_SIZE = 64
_MAX_BOOT_ID_LENGTH = 64
_BOOT_ID_CHARS = frozenset(string.hexdigits + "-")
_STATUSES = frozenset({"running", "done", "interrupted"})
_OUTCOME_VALUES = frozenset(outcome.value for outcome in Outcome)
ACTIVE_STATES = frozenset({"activating", "active"})
# dnf peut être en train de s'arrêter (ExecStopPost de ``end`` en cours) : run vivant.
WATCHED_RUNNING_STATES = ACTIVE_STATES | {"deactivating"}
_LOCK_WAIT_S = 10  # attente maximale du verrou (s) : le tiers du budget d'un verbe
_LOCK_POLL_S = 0.1  # pas du polling non bloquant (LOCK_NB)
_MAX_ARGS = 2  # verbe + job
_PAIR = 2  # (résumé, corps)
_NOTIFY_REPLY_FIELDS = 2  # réponse de busctl : « u <id> »
_FINGERPRINT_LENGTH = 64  # sha256 en hexadécimal
_MAX_FINGERPRINT_SIZE = 65  # 64 caractères + saut de ligne
_FINGERPRINT_CHARS = frozenset("0123456789abcdef")  # hexadécimal minuscule
_RESTART_NEEDED_RC = 1  # code de ``dnf5 needs-restarting`` : redémarrage requis


class _State(TypedDict):
    """Contenu de ``state.json`` : statut, uid et horodatages seulement."""

    boot_id: str
    started_at: float
    status: str
    outcome: str | None
    delivered: list[int]


class _UnsafePathError(OSError):
    """Chemin d'écriture refusé (lien symbolique ou composant non dossier)."""


@dataclass(frozen=True)
class _Target:
    """Fichier à écrire : ``base / relative / name``, avec ses modes."""

    base: Path
    relative: Path
    name: str
    file_mode: int
    dir_mode: int

    @property
    def path(self) -> Path:
        """Chemin complet du fichier."""
        return self.base / self.relative / self.name


def _env_dir(ctx: Ctx, key: str) -> Path | None:
    """Dossier absolu lu dans ``ctx.env`` (jamais ``Path.home()``), sinon None."""
    value = ctx.env.get(key, "")
    return Path(value) if value and Path(value).is_absolute() else None


def _xdg_state_base(ctx: Ctx) -> Path | None:
    """``$XDG_STATE_HOME``, ou ``$HOME/.local/state`` calculé depuis ``ctx.env``."""
    base = _env_dir(ctx, "XDG_STATE_HOME")
    if base is not None:
        return base
    home = _env_dir(ctx, "HOME")
    return None if home is None else home / ".local" / "state"


def _is_user_scope(ctx: Ctx) -> bool:
    """Indique si le job tourne dans le gestionnaire de l'utilisateur."""
    return _job(ctx).scope == "user"


def _user_dirs_missing(ctx: Ctx) -> bool:
    """Vrai si un dossier XDG (état ou exécution) manque pour le scope user."""
    return _xdg_state_base(ctx) is None or _env_dir(ctx, "XDG_RUNTIME_DIR") is None


def _state_target(ctx: Ctx) -> _Target:
    """Fichier d'état du job, selon le scope.

    Système : ``var/lib/<owner>/<name>/state.json`` (lisible de tous) ; user :
    ``$XDG_STATE_HOME/<owner>/<name>/state.json`` (privé).

    Raises:
        RuntimeError: En scope user sans dossier d'état (``main`` l'écarte avant).
    """
    job = _job(ctx)
    if _is_user_scope(ctx):
        base = _xdg_state_base(ctx)
        if base is None:
            msg = "ni XDG_STATE_HOME ni HOME exploitable"
            raise RuntimeError(msg)
        return _Target(
            base,
            Path(job.owner) / job.name,
            "state.json",
            file_mode=0o600,
            dir_mode=0o700,
        )
    return _Target(
        ctx.root_dir,
        Path("var/lib") / job.owner / job.name,
        "state.json",
        file_mode=0o644,
        dir_mode=0o755,
    )


def _run_relative(ctx: Ctx) -> Path:
    """``run/<owner>/<name>`` (root 0700 : ``ids/``, ``lock``, ``before``)."""
    job = _job(ctx)
    return Path("run") / job.owner / job.name


def _run_target(ctx: Ctx, name: str) -> _Target:
    """Fichier volatil du job, selon le scope.

    Système : sous ``/run/<owner>/<name>`` (root 0700) ; user : sous
    ``$XDG_RUNTIME_DIR/<owner>/<name>``.

    Raises:
        RuntimeError: En scope user sans ``XDG_RUNTIME_DIR`` (``main`` l'écarte avant).
    """
    if not _is_user_scope(ctx):
        return _Target(
            ctx.root_dir, _run_relative(ctx), name, file_mode=0o600, dir_mode=0o700
        )
    base = _env_dir(ctx, "XDG_RUNTIME_DIR")
    if base is None:
        msg = "XDG_RUNTIME_DIR absent"
        raise RuntimeError(msg)
    job = _job(ctx)
    return _Target(
        base, Path(job.owner) / job.name, name, file_mode=0o600, dir_mode=0o700
    )


def _lock_target(ctx: Ctx) -> _Target:
    """Fichier de verrou : dans le dossier 0700 des ID (``/run`` ou XDG)."""
    return _run_target(ctx, "lock")


def _ids_target(ctx: Ctx, uid: int) -> _Target:
    """Fichier de l'ID de notification mémorisé par root pour ``uid``."""
    return _Target(
        ctx.root_dir,
        _run_relative(ctx) / "ids",
        str(uid),
        file_mode=0o600,
        dir_mode=0o700,
    )


def _user_id_target(ctx: Ctx, uid: int) -> _Target:
    """Fichier d'ID écrit par l'utilisateur : ``run/user/<uid>/<owner>/<name>.id``.

    En scope user, c'est l'unique fichier d'ID : ``$XDG_RUNTIME_DIR/<owner>/<name>/id``.
    """
    if _is_user_scope(ctx):
        return _run_target(ctx, "id")
    job = _job(ctx)
    return _Target(
        ctx.root_dir,
        Path("run/user") / str(uid) / job.owner,
        f"{job.name}.id",
        file_mode=0o600,
        dir_mode=0o700,
    )


def _seen_target(ctx: Ctx) -> _Target | None:
    """Fichier ``seen`` de l'utilisateur, ou None sans dossier d'état utilisable."""
    base = _xdg_state_base(ctx)
    if base is None:
        return None
    job = _job(ctx)
    return _Target(
        base,
        Path(job.owner) / job.name,
        "seen",
        file_mode=0o600,
        dir_mode=0o700,
    )


def _ensure_dir(target: _Target) -> Path:
    """Crée le dossier de la cible en refusant tout lien symbolique.

    Args:
        target: Fichier dont on prépare le dossier.

    Returns:
        Le dossier, prêt à recevoir le fichier.

    Raises:
        _UnsafePathError: Si un composant est un lien symbolique ou un fichier.
        OSError: Si la création échoue.
    """
    target.base.mkdir(parents=True, exist_ok=True)
    current = target.base
    for part in target.relative.parts:
        current /= part
        if current.is_symlink():
            msg = f"lien symbolique refusé : {current}"
            raise _UnsafePathError(msg)
        if not current.exists():
            try:
                current.mkdir(mode=target.dir_mode)
            except FileExistsError:
                # Créé entre exists() et mkdir() par un process parallèle
                # (snapshot et compagnon) : on retombe sur les contrôles.
                pass
            else:
                current.chmod(target.dir_mode)
        # Mêmes contrôles qu'avant : un lien ou un fichier arrivé entre-temps
        # reste refusé.
        if current.is_symlink():
            msg = f"lien symbolique refusé : {current}"
            raise _UnsafePathError(msg)
        if not current.is_dir():
            msg = f"pas un dossier : {current}"
            raise _UnsafePathError(msg)
    return current


def _atomic_write(directory: Path, name: str, text: str, mode: int) -> None:
    """Écrit un fichier de façon atomique : temporaire voisin puis ``replace``.

    Le temporaire est créé en O_EXCL|O_NOFOLLOW ; ``replace`` substitue le nom
    sans jamais écrire à travers un lien symbolique posé sur la cible.

    Args:
        directory: Dossier déjà vérifié.
        name: Nom du fichier final.
        text: Contenu.
        mode: Mode du fichier final.

    Raises:
        OSError: Si l'écriture ou le remplacement échoue (le temporaire est
            alors supprimé).
    """
    temporary = directory / f".{name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(temporary, flags, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(text)
        temporary.replace(directory / name)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _persist(ctx: Ctx, target: _Target, text: str) -> bool:
    """Écrit un fichier d'état sans jamais lever.

    Args:
        ctx: Dépendances du hook.
        target: Fichier à écrire.
        text: Contenu.

    Returns:
        True si le fichier est écrit ; sinon False, avec un message sur stderr.
    """
    try:
        _atomic_write(_ensure_dir(target), target.name, text, target.file_mode)
    except OSError as exc:
        _warn(ctx, f"écriture de {target.name} impossible ({exc})")
        return False
    return True


def _is_number(value: object) -> TypeGuard[float]:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_outcome_value(value: object) -> TypeGuard[str | None]:
    return value is None or (isinstance(value, str) and value in _OUTCOME_VALUES)


def _is_uid_list(value: object) -> TypeGuard[list[int]]:
    return isinstance(value, list) and all(
        isinstance(item, int) and not isinstance(item, bool) for item in value
    )


def _validate_state(data: object) -> _State | None:
    """Vérifie le schéma de ``state.json``.

    Args:
        data: Objet issu de ``json.loads``.

    Returns:
        L'état reconstruit champ par champ (aucune clé étrangère conservée),
        ou None si le schéma n'est pas respecté.
    """
    if not isinstance(data, dict):
        return None
    boot_id = data.get("boot_id")
    started_at = data.get("started_at")
    status = data.get("status")
    outcome = data.get("outcome")
    delivered = data.get("delivered")
    if (
        isinstance(boot_id, str)
        and _is_number(started_at)
        and isinstance(status, str)
        and status in _STATUSES
        and _is_outcome_value(outcome)
        and _is_uid_list(delivered)
    ):
        return _State(
            boot_id=boot_id,
            started_at=float(started_at),
            status=status,
            outcome=outcome,
            delivered=list(delivered),
        )
    return None


def _expected_owner(ctx: Ctx) -> int | None:
    """Propriétaire exigé des fichiers d'état : l'utilisateur en scope user."""
    return ctx.geteuid() if _is_user_scope(ctx) else None


def _read_state(ctx: Ctx) -> _State | None:
    """Lit ``state.json`` ; un fichier illisible ou corrompu vaut « pas d'état ».

    Args:
        ctx: Dépendances du hook.

    Returns:
        L'état validé, ou None (fichier absent : silencieux ; sinon message
        sur stderr).
    """
    path = _state_target(ctx).path
    raw = _read_regular(path, max_size=_MAX_STATE_SIZE, owner=_expected_owner(ctx))
    if raw is None:
        if path.is_symlink() or path.exists():
            _warn(ctx, "état illisible, ignoré")
        return None
    try:
        state = _validate_state(json.loads(raw))
    except (ValueError, RecursionError):  # JSONDecodeError et octets invalides
        state = None
    if state is None:
        _warn(ctx, "état corrompu, ignoré")
    return state


def _write_state(ctx: Ctx, state: _State) -> bool:
    """Écrit ``state.json`` (0644, atomique, dossier non lien symbolique)."""
    return _persist(ctx, _state_target(ctx), json.dumps(state))


def _read_boot_id(ctx: Ctx) -> str | None:
    """Lit l'identifiant de démarrage du noyau.

    Args:
        ctx: Dépendances du hook.

    Returns:
        L'identifiant, ou None s'il est illisible ou de forme inattendue.
    """
    try:
        text = (ctx.root_dir / _BOOT_ID_RELATIVE).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    if 0 < len(text) <= _MAX_BOOT_ID_LENGTH and set(text) <= _BOOT_ID_CHARS:
        return text
    return None


def _read_root_id_stamped(ctx: Ctx, uid: int) -> tuple[int, float] | None:
    """Lit l'ID mémorisé par root pour ``uid`` et la date d'écriture du fichier.

    Sans objet en scope user (aucun ID root) : None.
    """
    if _is_user_scope(ctx):
        return None
    result = _read_regular_stamped(
        _ids_target(ctx, uid).path, max_size=_MAX_ID_FILE_SIZE
    )
    if result is None:
        return None
    notification_id = _parse_id_file(result[0])
    return None if notification_id is None else (notification_id, result[1])


def _forget_root_id(ctx: Ctx, uid: int) -> None:
    """Supprime l'ID mémorisé pour ``uid`` (un ID périmé ne doit rien remplacer).

    Sans objet en scope user (aucun ID root).
    """
    if _is_user_scope(ctx):
        return
    with contextlib.suppress(OSError):
        _ids_target(ctx, uid).path.unlink(missing_ok=True)


def _open_lock(ctx: Ctx) -> int | None:
    """Ouvre le fichier de verrou sans suivre de lien symbolique.

    Args:
        ctx: Dépendances du hook.

    Returns:
        Le descripteur (régulier, ``O_NOFOLLOW``, ``O_CLOEXEC``), ou None si le
        dossier ou le fichier est hostile ou inutilisable (message sur stderr).
    """
    target = _lock_target(ctx)
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(_ensure_dir(target) / target.name, flags, target.file_mode)
    except OSError as exc:
        _warn(ctx, f"verrou inutilisable ({exc}), sans verrou")
        return None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        _warn(ctx, "verrou non régulier, sans verrou")
        return None
    return fd


def _acquire_lock(ctx: Ctx, fd: int) -> bool:
    """Prend le ``flock`` exclusif par polling ``LOCK_NB``, dans un délai borné.

    Le délai est ``_LOCK_WAIT_S``, plafonné par ce qui reste du budget du verbe.

    Args:
        ctx: Dépendances du hook.
        fd: Descripteur du fichier de verrou.

    Returns:
        True si le verrou est tenu ; False (message sur stderr) s'il est tenu
        ailleurs au-delà du délai ou si ``flock`` échoue.
    """
    deadline = ctx.monotonic() + _LOCK_WAIT_S
    if ctx.started is not None:
        deadline = min(deadline, ctx.started + TOTAL_BUDGET_S)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass  # tenu par l'autre verbe : on réessaie jusqu'au délai
        except OSError as exc:
            _warn(ctx, f"flock impossible ({exc}), sans verrou")
            return False
        else:
            return True
        if ctx.monotonic() >= deadline:
            _warn(ctx, "verrou occupé, poursuite sans verrou")
            return False
        ctx.sleep(_LOCK_POLL_S)


@contextlib.contextmanager
def _exclusive_lock(ctx: Ctx) -> Iterator[bool]:
    """Sérialise ``start`` et ``end`` ; jamais bloquant, jamais en échec.

    Le verrou est relâché à la fermeture du descripteur, y compris sur exception.

    Args:
        ctx: Dépendances du hook.

    Yields:
        True si le verrou est tenu, False en repli sans verrou.
    """
    fd = _open_lock(ctx)
    if fd is None:
        yield False
        return
    try:
        yield _acquire_lock(ctx, fd)
    finally:
        os.close(fd)


def start(ctx: Ctx) -> None:
    """ExecStartPost du compagnon : état « running » + notification de lancement.

    Le verrou ``flock`` est tenu pendant tout le travail (F17).

    Args:
        ctx: Dépendances du hook.
    """
    with _exclusive_lock(ctx):
        _start_locked(ctx)


def _recipients(ctx: Ctx) -> list[Session]:
    """Destinataires : le propriétaire seul (scope user), sinon les sessions locales."""
    if _is_user_scope(ctx):
        # ``user`` n'est utilisé que par runuser (scope système) : vide ici, plutôt
        # que de détourner le champ avec le propriétaire du job (F12).
        return [Session(uid=ctx.geteuid(), user="")]
    return list_graphical_sessions(ctx)


def _remember_id(ctx: Ctx, session: Session, notification_id: int) -> None:
    """Mémorise l'ID de la notification « en cours » (fichier root ou utilisateur)."""
    target = (
        _user_id_target(ctx, session.uid)
        if _is_user_scope(ctx)
        else _ids_target(ctx, session.uid)
    )
    _persist(ctx, target, f"{notification_id}\n")


def _start_locked(ctx: Ctx) -> None:
    """Corps de ``start`` (état puis notifications), sous verrou."""
    boot_id = _read_boot_id(ctx)
    if boot_id is None:
        _warn(ctx, "boot_id illisible")
    _write_state(
        ctx,
        _State(
            boot_id=boot_id or "",
            started_at=ctx.now(),
            status="running",
            outcome=None,
            delivered=[],
        ),
    )
    for session in _recipients(ctx):
        _forget_root_id(ctx, session.uid)
        notification_id = send_notification(
            ctx,
            session,
            summary=_job(ctx).start_texts[0],
            body=_job(ctx).start_texts[1],
            persistent=True,
        )
        if notification_id is not None:
            _remember_id(ctx, session, notification_id)


def _system_stopping(ctx: Ctx) -> bool:
    """Indique si le poste est en cours d'arrêt (``is-system-running``)."""
    result = _call(ctx, [SYSTEMCTL, "is-system-running"])
    return result is not None and result[1].strip() == "stopping"


def _read_history(ctx: Ctx) -> list[Mapping[str, object]] | None:
    """Lit l'historique de dnf5 ; None (et message) s'il est illisible."""
    result = _call(ctx, [DNF5, "history", "list", "--json"])
    if result is None:
        return None
    data: object = None
    if result[0] == 0:
        try:
            data = json.loads(result[1])
        except (ValueError, RecursionError):
            data = None
    if not isinstance(data, list):
        _warn(ctx, "historique dnf5 illisible")
        return None
    return data


def _reboot_required(output: str) -> bool | None:
    """Lit la sortie JSON de ``dnf5 needs-restarting --json``.

    Forme documentée (man dnf5-needs-restarting) : un tableau d'un objet
    ``{"type": "reboot", "reboot_required": <bool>, ...}``.

    Args:
        output: Sortie standard de la commande.

    Returns:
        La valeur de ``reboot_required``, ou None si la sortie n'a pas la forme
        attendue (vide, texte d'erreur, JSON inattendu).
    """
    try:
        data = json.loads(output)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, list):
        return None
    for item in data:
        if (
            isinstance(item, dict)
            and item.get("type") == "reboot"
            and isinstance(item.get("reboot_required"), bool)
        ):
            return bool(item["reboot_required"])
    return None


def _needs_restart(ctx: Ctx) -> bool:
    """Indique si ``dnf5 needs-restarting`` réclame un redémarrage.

    Le code 1 signifie aussi « dnf5 a échoué » (dépôts injoignables) : il n'est
    donc retenu que si la sortie JSON annonce ``reboot_required``. Code 0, code
    inattendu, sortie illisible ou appel impossible : pas de redémarrage annoncé,
    avec un message sur stderr pour les cas anormaux.
    """
    result = _call(ctx, [DNF5, "needs-restarting", "--json", "--disablerepo=*"])
    if result is None:
        return False
    code, output = result
    if code == 0:
        return False
    if code != _RESTART_NEEDED_RC:
        _warn(ctx, f"needs-restarting a rendu le code {code}, redémarrage inconnu")
        return False
    required = _reboot_required(output)
    if required is None:
        _warn(
            ctx,
            "needs-restarting a rendu le code 1 sans JSON "
            "attendu (erreur dnf5 probable), redémarrage inconnu",
        )
        return False
    return required


def _resolve_dnf5(ctx: Ctx, state: _State | None, *, stopping: bool) -> Outcome:
    """Calcule l'issue du run ; dnf5 n'est interrogé que si elle peut être un succès."""
    service_result = ctx.env.get("SERVICE_RESULT", "")
    started_at = state["started_at"] if state is not None else 0.0
    outcome = compute_dnf5_outcome(
        service_result=service_result,
        system_stopping=stopping,
        transactions=None,
        started_at=started_at,
        needs_restart=False,
    )
    if outcome is not Outcome.DONE_NO_DETAIL:
        return outcome  # échec ou interruption : l'historique n'y change rien
    transactions = _read_history(ctx) if state is not None else None
    if transactions is None:
        return Outcome.DONE_NO_DETAIL
    outcome = compute_dnf5_outcome(
        service_result=service_result,
        system_stopping=stopping,
        transactions=transactions,
        started_at=started_at,
        needs_restart=False,
    )
    if outcome is Outcome.SUCCESS and _needs_restart(ctx):
        return Outcome.SUCCESS_RESTART
    return outcome


def _trusted_binary(ctx: Ctx, path: str) -> bool:
    """Indique si ``path`` est un binaire sûr à lancer en root (échec fermé).

    Un fichier régulier (ni lien, ni dossier), appartenant à root et non
    inscriptible par le groupe ni les autres. Une erreur de ``lstat`` refuse.
    """
    try:
        info = ctx.lstat(path)
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == 0
        and not info.st_mode & _GROUP_OTHERS_WRITE
    )


def _fingerprint(ctx: Ctx) -> str | None:
    """Empreinte sha256 des refs Flatpak système installées (ADR empreinte).

    Les refs ne sont jamais conservées : seule l'empreinte de la liste triée
    est rendue.

    Args:
        ctx: Dépendances du hook.

    Returns:
        L'empreinte en hexadécimal (une liste vide est valide), ou None si
        ``flatpak list`` est inutilisable (message sur stderr).
    """
    argv = list(_job(ctx).probe_argv)
    if not _trusted_binary(ctx, argv[0]):
        _warn(ctx, f"binaire de sonde refusé ({argv[0]}), empreinte indisponible")
        return None
    result = _call(ctx, argv)
    if result is None or result[0] != 0:
        _warn(ctx, "flatpak list illisible, empreinte indisponible")
        return None
    lines = sorted(line.strip() for line in result[1].splitlines() if line.strip())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _before_target(ctx: Ctx) -> _Target:
    """Fichier de l'empreinte d'avant run : dans le dossier 0700 des ID."""
    return _run_target(ctx, "before")


def _forget_before(ctx: Ctx) -> None:
    """Supprime l'empreinte d'avant run (une empreinte périmée ne doit rien servir)."""
    with contextlib.suppress(OSError):
        _before_target(ctx).path.unlink(missing_ok=True)


def _read_before(ctx: Ctx) -> str | None:
    """Lit l'empreinte d'avant run, sans se laisser piéger par un fichier hostile.

    Returns:
        L'empreinte (64 caractères hexadécimaux minuscules), ou None si le
        fichier est absent (en silence) ou hostile (lien, non régulier, trop
        gros, mal formé : message sur stderr).
    """
    path = _before_target(ctx).path
    raw = _read_regular(
        path, max_size=_MAX_FINGERPRINT_SIZE, owner=_expected_owner(ctx)
    )
    if raw is None:
        if path.is_symlink() or path.exists():
            _warn(ctx, "empreinte illisible, ignorée")
        return None
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        text = ""
    if len(text) == _FINGERPRINT_LENGTH and set(text) <= _FINGERPRINT_CHARS:
        return text
    _warn(ctx, "empreinte illisible, ignorée")
    return None


def _snapshot_flatpak(ctx: Ctx) -> None:
    """Écrit l'empreinte d'avant run ; l'ancienne est supprimée d'abord."""
    _forget_before(ctx)
    digest = _fingerprint(ctx)
    if digest is not None:
        _persist(ctx, _before_target(ctx), f"{digest}\n")


def snapshot(ctx: Ctx) -> None:
    """ExecStartPre de flatpak-automatic : empreinte des refs avant le run.

    Sans objet (message, aucune écriture) pour un job qui n'a pas d'instantané.
    Le verbe ne prend pas le ``flock`` : il ne touche que ``before``, que seul
    l'``end`` du même run lit, après ``ExecStart``.

    Args:
        ctx: Dépendances du hook.
    """
    take = _SNAPSHOTS.get(_job(ctx).probe_kind)
    if take is None:
        _warn(ctx, f"snapshot sans objet pour {_job(ctx).name}")
        return
    take(ctx)


def _resolve_flatpak(ctx: Ctx, state: _State | None, *, stopping: bool) -> Outcome:
    """Calcule l'issue du run Flatpak ; ne consulte jamais dnf5."""
    service_result = ctx.env.get("SERVICE_RESULT", "")
    before = _read_before(ctx) if state is not None else None
    after = None
    if not stopping and service_result == "success" and before is not None:
        after = _fingerprint(ctx)
    return compute_flatpak_outcome(
        service_result=service_result,
        system_stopping=stopping,
        has_state=state is not None,
        before=before,
        after=after,
    )


_MAX_FWUPD_JSON = 1024 * 1024  # plafond (octets) de la sortie de fwupdmgr lue
_UPDATE_STATE_NEEDS_REBOOT = 4  # FwupdUpdateState : en attente de redémarrage
_FWUPD_NO_DEVICE_RC = 2  # ``fwupdmgr get-devices`` : aucun périphérique


def _needs_reboot_in(output: str) -> bool | None:
    """Analyse la sortie JSON de ``fwupdmgr get-devices --json``.

    Seul un booléen est rendu : rien du JSON (numéros de série, noms de
    périphériques) n'est conservé, journalisé ni notifié.

    Args:
        output: Sortie standard de la commande.

    Returns:
        True si un périphérique a ``UpdateState == 4``, False sinon, ou None si
        la sortie est trop grosse ou n'a pas la forme attendue.
    """
    if len(output.encode("utf-8", errors="replace")) > _MAX_FWUPD_JSON:
        return None
    try:
        data = json.loads(output)
    except (ValueError, RecursionError):
        return None
    devices = data.get("Devices") if isinstance(data, dict) else None
    if not isinstance(devices, list):
        return None
    # ``type(x) is int`` exclut les booléens (``True == 1`` en Python).
    return any(
        type(device) is dict
        and type(device.get("UpdateState")) is int
        and device["UpdateState"] == _UPDATE_STATE_NEEDS_REBOOT
        for device in devices
    )


def _pending_update(ctx: Ctx) -> bool | None:
    """Indique si un firmware attend le redémarrage (None si illisible)."""
    if not _trusted_binary(ctx, FWUPDMGR):
        _warn(ctx, f"binaire de sonde refusé ({FWUPDMGR}), état du firmware inconnu")
        return None
    result = _call(ctx, [FWUPDMGR, "get-devices", "--json"])
    if result is None:
        return None
    code, output = result
    if code == _FWUPD_NO_DEVICE_RC:
        return False
    if code != 0:
        _warn(ctx, f"get-devices a rendu le code {code}, état du firmware inconnu")
        return None
    pending = _needs_reboot_in(output)
    if pending is None:
        _warn(ctx, "sortie fwupd illisible")
    return pending


def _resolve_fwupd(ctx: Ctx, state: _State | None, *, stopping: bool) -> Outcome:
    """Calcule l'issue du run fwupd ; fwupd n'est pas interrogé à l'arrêt."""
    del state  # sans instantané : l'état du run n'apporte rien
    pending = None if stopping else _pending_update(ctx)
    return compute_fwupd_outcome(
        service_result=ctx.env.get("SERVICE_RESULT", ""),
        system_stopping=stopping,
        pending=pending,
    )


def _id_to_replace(ctx: Ctx, session: Session, started_at: float | None) -> int:
    """Choisit l'ID de la notification « en cours » à remplacer (0 : aucune).

    Seul un ID écrit après le début du run peut appartenir à ce run, qu'il vienne
    de l'utilisateur (``login``) ou de root (``start``) ; l'ID utilisateur prime.
    Sans ``started_at`` fiable (état invalide), aucun ID n'est réutilisé.
    """
    if started_at is None:
        return 0
    for stamped in (
        _read_user_id_stamped(ctx, session),
        _read_root_id_stamped(ctx, session.uid),
    ):
        if stamped is not None and stamped[1] > started_at:
            return stamped[0]
    return 0


def _notify_end(ctx: Ctx, outcome: Outcome, started_at: float | None) -> list[int]:
    """Notifie le résultat à chaque session ; rend les uid effectivement servis."""
    summary, body = _job(ctx).end_texts[outcome]
    delivered: list[int] = []
    for session in _recipients(ctx):
        replaces_id = _id_to_replace(ctx, session, started_at)
        notification_id = send_notification(
            ctx,
            session,
            summary=summary,
            body=body,
            replaces_id=replaces_id,
            persistent=False,
        )
        if notification_id is not None:
            delivered.append(session.uid)
        _forget_root_id(ctx, session.uid)
    return delivered


def _read_current_run_state(ctx: Ctx) -> _State | None:
    """Lit l'état et ne le garde que s'il décrit le run en cours.

    Args:
        ctx: Dépendances du hook.

    Returns:
        L'état s'il est ``running`` et du boot courant ; None sinon (absent,
        run précédent terminé, autre boot) : son ``started_at`` est périmé.
    """
    state = _read_state(ctx)
    if state is None:
        return None
    if state["status"] != "running" or state["boot_id"] != _read_boot_id(ctx):
        _warn(ctx, "état d'un autre run, ignoré")
        return None
    return state


def end(ctx: Ctx) -> None:
    """ExecStopPost de dnf : arrête le compagnon, calcule l'issue, notifie.

    Le verrou est pris AVANT l'arrêt du compagnon : ``end`` attend la fin de
    ``start``, dont l'écriture « running » ne peut donc plus suivre « done » (F17).

    Args:
        ctx: Dépendances du hook.
    """
    with _exclusive_lock(ctx):
        _end_locked(ctx)


def _end_locked(ctx: Ctx) -> None:
    """Corps de ``end`` (arrêt du compagnon, issue, notification), sous verrou."""
    # Seul l'inhibiteur du compagnon est levé ici (le poste redevient éteignable) ;
    # le ``flock`` reste tenu jusqu'à la fin de ``end``.
    if _job(ctx).lock:  # sans verrou, il n'existe aucun compagnon à arrêter (A-05)
        _call(ctx, _systemctl(ctx, "stop", _job(ctx).guard_unit))
    state = _read_current_run_state(ctx)
    if state is None:
        _warn(ctx, "état de lancement absent, détail inconnu")
    outcome = resolve_outcome(ctx, _job(ctx), state, stopping=_system_stopping(ctx))
    if _job(ctx).probe_kind in _SNAPSHOTS:
        _forget_before(ctx)  # lue (ou inutile) : jamais réutilisée par un autre run
    started_at = state["started_at"] if state is not None else None
    final = _State(
        boot_id=state["boot_id"] if state is not None else _read_boot_id(ctx) or "",
        started_at=started_at if started_at is not None else ctx.now(),
        status="interrupted" if outcome is Outcome.INTERRUPTED else "done",
        outcome=outcome.value,
        delivered=[],
    )
    # E9, F21 : l'état terminal est écrit AVANT de lire les ID à remplacer ; un
    # ``login`` qui écrit son ID après cette lecture relit alors l'état terminal.
    _write_state(ctx, final)
    final["delivered"] = _notify_end(ctx, outcome, started_at)
    # ``delivered`` n'est connu qu'après l'envoi : seconde écriture, même état.
    _write_state(ctx, final)


def _send_to_self(
    ctx: Ctx,
    summary: str,
    body: str,
    *,
    persistent: bool,
    replaces_id: int = 0,
) -> int | None:
    """Notifie l'utilisateur courant : ``busctl --user`` direct, sans runuser."""
    urgency = _URGENCY_CRITICAL if persistent else _URGENCY_NORMAL
    argv = _notify_command(ctx, replaces_id, summary, body, urgency)
    return _deliver(ctx, argv, "l'utilisateur courant")


def _read_seen(ctx: Ctx, target: _Target) -> float:
    """Lit l'horodatage du dernier résultat vu ; ``-inf`` s'il est absent ou hostile."""
    raw = _read_regular(
        target.path, max_size=_MAX_SEEN_SIZE, owner=_expected_owner(ctx)
    )
    if raw is None:
        return -math.inf
    try:
        value = float(raw.decode("ascii"))
    except ValueError:  # UnicodeDecodeError en est une sous-classe
        return -math.inf
    return value if math.isfinite(value) else -math.inf


def _show_unseen(
    ctx: Ctx, state: _State, outcome: Outcome, replaces_id: int = 0
) -> None:
    """Affiche le résultat d'un run une seule fois, puis note qu'il est vu.

    Args:
        ctx: Dépendances du hook.
        state: État du run.
        outcome: Issue à afficher.
        replaces_id: ID de la notification « en cours » de ce ``login`` à
            remplacer (0 : aucune). Elle est alors remplacée même si le résultat
            a déjà été vu : sinon la notification critique resterait orpheline.
    """
    target = _seen_target(ctx)
    if target is None:
        _warn(ctx, "ni XDG_STATE_HOME ni HOME exploitable")
        return
    if replaces_id == 0 and state["started_at"] <= _read_seen(ctx, target):
        return
    summary, body = _job(ctx).end_texts[outcome]
    sent = _send_to_self(ctx, summary, body, persistent=False, replaces_id=replaces_id)
    if sent is not None:
        _persist(ctx, target, f"{state['started_at']!r}\n")


def _run_in_progress(ctx: Ctx, state: _State) -> bool:
    """Indique si le run décrit par l'état tourne encore (même boot, F01).

    Le compagnon ``active``/``activating`` suffit : il est actif même quand dnf
    est encore ``inactive`` à attendre ``network-online``. Sinon dnf lui-même
    ``activating``/``active``/``deactivating``. Sans verrou, il n'y a pas de
    compagnon : seul dnf est interrogé.
    """
    if state["boot_id"] != _read_boot_id(ctx):
        return False
    checks = [(_job(ctx).watched_unit, WATCHED_RUNNING_STATES)]
    if _job(ctx).lock:  # sans verrou, il n'existe aucun compagnon à interroger (F10)
        checks.insert(0, (_job(ctx).guard_unit, ACTIVE_STATES))
    for unit, states in checks:
        result = _call(ctx, _systemctl(ctx, "is-active", unit))
        if result is not None and result[1].strip() in states:
            return True
    return False


def _replace_if_run_ended(ctx: Ctx, notification_id: int) -> None:
    """Remplace « en cours » par le résultat si le run s'est fini pendant l'envoi.

    ``end`` a pu lire l'ID utilisateur avant qu'il soit écrit (F16) : relire
    l'état permet de ne pas laisser une notification critique orpheline.

    Args:
        ctx: Dépendances du hook.
        notification_id: ID de la notification « en cours » qui vient d'être envoyée.
    """
    state = _read_state(ctx)
    if state is None:
        return
    if state["status"] != "running":
        outcome = Outcome(state["outcome"] or Outcome.DONE_NO_DETAIL)
    elif state["boot_id"] != _read_boot_id(ctx):
        outcome = Outcome.INTERRUPTED
    else:
        return
    _show_unseen(ctx, state, outcome, notification_id)


def login(ctx: Ctx) -> None:
    """Autostart utilisateur : rattrape lancement, résultat ou interruption non vus.

    Args:
        ctx: Dépendances du hook (``geteuid`` doit être celui de l'utilisateur).
    """
    uid = ctx.geteuid()
    if uid == 0:
        _warn(ctx, "login ne doit pas tourner en root")
        return
    state = _read_state(ctx)
    if state is None:
        return
    if state["status"] != "running":
        outcome = Outcome(state["outcome"] or Outcome.DONE_NO_DETAIL)
        if uid not in state["delivered"]:
            _show_unseen(ctx, state, outcome)
    elif _run_in_progress(ctx, state):
        notification_id = _send_to_self(ctx, *_job(ctx).start_texts, persistent=True)
        if notification_id is not None:
            # Lu par ``end`` (root) pour remplacer cette notification.
            _persist(ctx, _user_id_target(ctx, uid), f"{notification_id}\n")
            _replace_if_run_ended(ctx, notification_id)
    else:
        _show_unseen(ctx, state, Outcome.INTERRUPTED)  # run interrompu (F-12)


class _Resolver(Protocol):
    """Calcule l'issue du run pour une sonde du catalogue."""

    def __call__(self, ctx: Ctx, state: _State | None, *, stopping: bool) -> Outcome:
        """Rend l'issue du run (``state`` : état de ``start``, None si absent)."""


def _resolve_none(ctx: Ctx, state: _State | None, *, stopping: bool) -> Outcome:
    """Sonde ``none`` : interruption, échec du service, sinon succès."""
    del state  # aucune sonde : l'état n'apporte rien
    if stopping:
        return Outcome.INTERRUPTED
    if ctx.env.get("SERVICE_RESULT", "") != "success":
        return Outcome.FAILURE
    return Outcome.SUCCESS


# Catalogue FERMÉ des sondes : un ``kind`` hors de cette table invalide le descripteur.
_PROBES: Mapping[str, _Resolver] = {
    "none": _resolve_none,
    "fingerprint": _resolve_flatpak,
    "dnf5": _resolve_dnf5,
    "fwupd": _resolve_fwupd,
}
# Sondes qui prennent un instantané avant le run (verbe ``snapshot``).
_SNAPSHOTS: Mapping[str, Callable[[Ctx], None]] = {"fingerprint": _snapshot_flatpak}
# Issues atteignables par sonde : ``end_texts`` doit toutes les couvrir.
_BASE_OUTCOMES = frozenset({Outcome.SUCCESS, Outcome.FAILURE, Outcome.INTERRUPTED})
REACHABLE: Mapping[str, frozenset[Outcome]] = {
    "none": _BASE_OUTCOMES,
    "fingerprint": _BASE_OUTCOMES | {Outcome.NOTHING, Outcome.DONE_NO_DETAIL},
    "dnf5": frozenset(Outcome),
    # Jamais SUCCESS : fwupd prépare sans flasher, l'issue réussie est SUCCESS_RESTART.
    "fwupd": frozenset(Outcome) - {Outcome.SUCCESS},
}


def resolve_outcome(
    ctx: Ctx, descriptor: Descriptor, state: _State | None, *, stopping: bool
) -> Outcome:
    """Rend l'issue du run, calculée par la sonde déclarée dans le descripteur.

    Args:
        ctx: Dépendances du runtime.
        descriptor: Descripteur du job (sa sonde est dans le catalogue fermé).
        state: État écrit par ``start``, ou None s'il est absent ou périmé.
        stopping: Le poste est en cours d'arrêt.

    Returns:
        L'issue à notifier.
    """
    return _PROBES[descriptor.probe_kind](ctx, state, stopping=stopping)


# ---------------------------------------------------------------------------
# Descripteur : lecture sûre et validation stricte (stdlib seule, jamais d'import
# de ``spec.py``). Source UNIQUE des constantes et motifs de validation :
# ``spec.py`` les importe d'ici (F05) ; le sens inverse reste interdit.
# ---------------------------------------------------------------------------

NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
UNIT_RE = re.compile(r"[A-Za-z0-9:_.@-]+\.service")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
WHY_FORBIDDEN_RE = re.compile(r"[\"'%$\\]")
MAX_TEXT_LEN = 200


@dataclass(frozen=True)
class ProbeCommand:
    """Commande de sonde fixée pour un binaire (F26).

    Attributes:
        subcommand: Sous-commande imposée en ``argv[1]``.
        options: Options exactes admises après la sous-commande.
        option_re: Motif des options à valeur admises (``--columns=…``).
    """

    subcommand: str
    options: frozenset[str]
    option_re: re.Pattern[str]


# Catalogue fermé des sondes ``fingerprint`` (F20, F26) : par chemin exact de
# binaire, une sous-commande imposée et des options fermées. Les colonnes admettent
# le suffixe ``:f`` de flatpak (``active:f``). Étendre le catalogue exige un
# amendement (ADR « catalogue de sondes »). Vue en lecture seule : un import ne
# peut pas étendre le catalogue à l'exécution (F37).
PROBE_COMMANDS: Mapping[str, ProbeCommand] = MappingProxyType(
    {
        "/usr/bin/flatpak": ProbeCommand(
            subcommand="list",
            options=frozenset({"--system", "--user", "--app", "--runtime"}),
            option_re=re.compile(
                r"--columns=[a-z]+(?::[a-z]+)?(?:,[a-z]+(?::[a-z]+)?)*"
            ),
        ),
    }
)
DESCRIPTOR_VERSION = 1
_MAX_DESCRIPTOR_SIZE = 16 * 1024
_GROUP_OTHERS_WRITE = 0o022
_DESCRIPTOR_KEYS = frozenset(
    {
        "version",
        "name",
        "owner",
        "watched_unit",
        "scope",
        "start_texts",
        "end_texts",
        "lock",
        "probe",
        "icon",
        "inhibit_why",
        "guard_after",
    }
)
_SCOPES = frozenset({"system", "user"})


class _InvalidDescriptorError(ValueError):
    """Descripteur hors schéma (échec fermé : aucune action)."""


def _invalid(field_name: str) -> NoReturn:
    """Refuse le descripteur en nommant le champ fautif."""
    msg = f"champ invalide : {field_name}"
    raise _InvalidDescriptorError(msg)


def _text(value: object, field_name: str) -> str:
    """Valide un texte affiché : chaîne plafonnée, sans caractère de contrôle."""
    if (
        not isinstance(value, str)
        or len(value) > MAX_TEXT_LEN
        or CONTROL_RE.search(value) is not None
    ):
        _invalid(field_name)
    return value


def _matching(value: object, pattern: re.Pattern[str], field_name: str) -> str:
    """Valide une chaîne qui doit correspondre entièrement à ``pattern``."""
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _invalid(field_name)
    return value


def _text_pair(value: object, field_name: str) -> tuple[str, str]:
    """Valide un couple (résumé, corps)."""
    if not isinstance(value, list) or len(value) != _PAIR:
        _invalid(field_name)
    return _text(value[0], field_name), _text(value[1], field_name)


def _units(value: object, field_name: str) -> tuple[str, ...]:
    """Valide une liste d'unités ``.service``."""
    if not isinstance(value, list):
        _invalid(field_name)
    return tuple(_matching(unit, UNIT_RE, field_name) for unit in value)


def fingerprint_argv_ok(argv: Sequence[str]) -> bool:
    """Indique si ``argv`` est une commande de sonde du catalogue fermé.

    Le binaire est lancé en root : ni une liste noire de lanceurs (F20), ni une
    liste blanche de binaires (F26, ``flatpak uninstall --all``) ne suffisent. Le
    catalogue fixe la commande entière. Source unique, partagée par ``spec.py`` et
    le runtime.

    Args:
        argv: Commande de l'instantané.

    Returns:
        True si ``argv[0]`` est un binaire de ``PROBE_COMMANDS``, ``argv[1]`` sa
        sous-commande imposée, et chaque argument suivant l'une de ses options
        exactes ou une option à valeur conforme à son motif.
    """
    command = PROBE_COMMANDS.get(argv[0]) if argv else None
    return (
        command is not None
        and len(argv) > 1
        and argv[1] == command.subcommand
        and all(
            arg in command.options or command.option_re.fullmatch(arg) is not None
            for arg in argv[2:]
        )
    )


def _probe(value: object) -> tuple[str, tuple[str, ...]]:
    """Valide la sonde : ``kind`` du catalogue fermé, ``argv`` d'une commande fixée."""
    if not isinstance(value, dict) or set(value) != {"kind", "argv"}:
        _invalid("probe")
    kind = value["kind"]
    argv = value["argv"]
    if not isinstance(kind, str) or kind not in _PROBES:
        _invalid("probe.kind")
    if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
        _invalid("probe.argv")
    if kind == "fingerprint":
        if not fingerprint_argv_ok(argv):
            _invalid("probe.argv")
    elif argv:
        _invalid("probe.argv")
    return kind, tuple(argv)


def _end_texts(value: object, kind: str) -> dict[Outcome, tuple[str, str]]:
    """Valide ``end_texts`` : issues connues, et toutes celles de la sonde."""
    if not isinstance(value, dict) or not set(value) <= _OUTCOME_VALUES:
        _invalid("end_texts")
    texts = {Outcome(key): _text_pair(pair, "end_texts") for key, pair in value.items()}
    if not REACHABLE[kind] <= texts.keys():
        _invalid("end_texts")
    return texts


def _inhibit_why(value: object) -> str:
    """Valide le motif d'inhibition (futur contenu d'unité systemd)."""
    if (
        not isinstance(value, str)
        or CONTROL_RE.search(value) is not None
        or WHY_FORBIDDEN_RE.search(value) is not None
    ):
        _invalid("inhibit_why")
    return value


def _build_descriptor(data: Mapping[str, object]) -> Descriptor:
    """Construit le descripteur champ par champ (aucune clé étrangère conservée)."""
    version = data["version"]
    if isinstance(version, bool) or version != DESCRIPTOR_VERSION:
        _invalid("version")
    scope = data["scope"]
    if not isinstance(scope, str) or scope not in _SCOPES:
        _invalid("scope")
    lock = data["lock"]
    if not isinstance(lock, bool):
        _invalid("lock")
    kind, argv = _probe(data["probe"])
    return Descriptor(
        name=_matching(data["name"], NAME_RE, "name"),
        owner=_matching(data["owner"], NAME_RE, "owner"),
        watched_unit=_matching(data["watched_unit"], UNIT_RE, "watched_unit"),
        scope=scope,
        start_texts=_text_pair(data["start_texts"], "start_texts"),
        end_texts=_end_texts(data["end_texts"], kind),
        lock=lock,
        probe_kind=kind,
        probe_argv=argv,
        icon=_text(data["icon"], "icon"),
        inhibit_why=_inhibit_why(data["inhibit_why"]),
        guard_after=_units(data["guard_after"], "guard_after"),
    )


def parse_descriptor(data: object) -> Descriptor | None:
    """Valide un descripteur déjà décodé (schéma strict, échec fermé).

    Args:
        data: Objet issu de ``json.loads``.

    Returns:
        Le descripteur, ou None si le schéma, un motif ou une valeur est refusé.
    """
    if not isinstance(data, dict) or set(data) != _DESCRIPTOR_KEYS:
        return None
    try:
        return _build_descriptor(data)
    except _InvalidDescriptorError:
        return None


def _read_descriptor_file(ctx: Ctx, path: Path) -> bytes | None:
    """Lit le fichier descripteur sans se laisser piéger par un fichier hostile.

    Le fichier doit être régulier (``O_NOFOLLOW`` refuse un lien, ``O_NONBLOCK``
    empêche un FIFO de bloquer), appartenir à un propriétaire de confiance, ne
    pas être inscriptible par le groupe ni les autres, et faire au plus 16 Kio.

    Args:
        ctx: Dépendances du runtime (propriétaires de confiance).
        path: Fichier descripteur.

    Returns:
        Les octets lus, ou None si le fichier est absent ou refusé.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in ctx.trusted_uids
            or info.st_mode & _GROUP_OTHERS_WRITE
            or info.st_size > _MAX_DESCRIPTOR_SIZE
        ):
            return None
        return os.read(fd, _MAX_DESCRIPTOR_SIZE + 1)
    except OSError:
        return None
    finally:
        os.close(fd)


def load_descriptor(ctx: Ctx) -> Descriptor | None:
    """Lit et valide ``<script>.json`` ; None si absent ou invalide (échec fermé).

    Args:
        ctx: Dépendances du runtime (``script`` situe le fichier).

    Returns:
        Le descripteur, ou None avec un message sur stderr (le runtime n'agit alors
        pas).
    """
    raw = _read_descriptor_file(ctx, ctx.script.with_suffix(".json"))
    if raw is None:
        _warn(
            ctx, "descripteur absent ou invalide (lien, propriétaire, droits, taille)"
        )
        return None
    try:
        descriptor = parse_descriptor(json.loads(raw))
    except (ValueError, RecursionError):  # JSONDecodeError et octets invalides
        descriptor = None
    if descriptor is None:
        _warn(ctx, "descripteur invalide (schéma ou valeurs)")
    return descriptor


_VERBS: Mapping[str, Callable[[Ctx], None]] = {
    "start": start,
    "end": end,
    "login": login,
    "snapshot": snapshot,
}


def _dispatch(ctx: Ctx, args: Sequence[str]) -> None:
    """Charge le descripteur, contrôle le verbe et le job, lance le verbe."""
    descriptor = ctx.descriptor or load_descriptor(ctx)
    if descriptor is None:
        return
    ctx.descriptor = descriptor
    handler = _VERBS.get(args[0]) if args and len(args) <= _MAX_ARGS else None
    if handler is None or (len(args) == _MAX_ARGS and args[1] != descriptor.name):
        _warn(
            ctx,
            f"verbe ou job invalide {list(args)!r} "
            f"(start|end|login|snapshot [{descriptor.name}])",
        )
        return
    if descriptor.scope == "user" and _user_dirs_missing(ctx):
        # Échec fermé : sans dossiers XDG ni bus, rien n'est écrit ni notifié.
        _warn(
            ctx, "scope user : XDG_RUNTIME_DIR ou dossier d'état absent, aucune action"
        )
        return
    handler(ctx)


def main(argv: Sequence[str] | None = None, ctx: Ctx | None = None) -> int:
    """Point d'entrée : ``<verbe> [job]``, verbe ``start|end|login|snapshot``.

    Aucune erreur ne remonte : un échec de notification ne doit jamais faire
    échouer le service surveillé (A-07) ; il est écrit sur stderr (journal).
    Sans descripteur valide, ou si ``job`` diffère du ``name`` du descripteur,
    rien n'est fait.

    Args:
        argv: Arguments (verbe, puis job facultatif) ; ``sys.argv[1:]`` par défaut.
        ctx: Dépendances ; contexte réel par défaut.

    Returns:
        Toujours 0 (jamais d'échec propagé au service surveillé).
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if ctx is None:
        ctx = Ctx(runner=default_runner, env=os.environ)
    ctx.started = ctx.monotonic()
    try:
        _dispatch(ctx, args)
    except Exception as exc:  # noqa: BLE001 (A-07 : rien ne remonte au service)
        verb = args[0] if args else "?"
        _warn(ctx, f"{verb} interrompu ({type(exc).__name__}: {exc})")
    return 0


if __name__ == "__main__":  # pragma: no cover — point d'entrée du script installé
    raise SystemExit(main())
