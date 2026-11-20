"""Non-régression de l'interface : les booléens sont en mot-clé seul."""

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

import linuxtools
from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.deployer import Deployer
from linuxtools.devtools.cli import ExecutorFactory
from linuxtools.logging.file_logger import FileLogger
from linuxtools.systemd.base import MountUnitManager
from linuxtools.systemd.mount import LinuxMountUnitManager

# (callable public, nom du paramètre booléen)
CAS: list[tuple[Callable[..., Any], str]] = [
    (MountUnitManager.enable_mount, "with_automount"),
    (LinuxMountUnitManager.enable_mount, "with_automount"),
    (Deployer.__init__, "dry_run"),
    (FileLogger.__init__, "console_output"),
    (CommandExecutor.run, "probe"),
]


@pytest.mark.parametrize(
    ("fonction", "parametre"),
    CAS,
    ids=[f"{f.__qualname__}.{p}" for f, p in CAS],
)
def test_booleens_sont_mot_cle_seul(
    fonction: Callable[..., Any], parametre: str
) -> None:
    """Le paramètre booléen doit être KEYWORD_ONLY (pas d'appel positionnel)."""
    # Arrange / Act
    kind = inspect.signature(fonction).parameters[parametre].kind

    # Assert
    assert kind is inspect.Parameter.KEYWORD_ONLY


def _modules_linuxtools() -> list[ModuleType]:
    """Importe tous les modules de ``linuxtools`` (extras absents ignorés)."""
    modules: list[ModuleType] = []
    for info in pkgutil.walk_packages(linuxtools.__path__, "linuxtools."):
        # Un ``__main__`` s'exécuterait à l'import et fausserait ``runpy``.
        if info.name.endswith(".__main__"):
            continue
        try:
            modules.append(importlib.import_module(info.name))
        except ModuleNotFoundError as exc:
            # Seul un extra optionnel absent est toléré ; un vrai ImportError
            # (symbole manquant, import circulaire) doit faire échouer.
            if exc.name is None or exc.name.startswith("linuxtools"):
                raise
    return modules


def _est_booleen(parametre: inspect.Parameter) -> bool:
    """Indique si le paramètre est un booléen (annotation ou défaut)."""
    return parametre.annotation in (bool, "bool") or isinstance(parametre.default, bool)


def _surcharges_a_booleen_mot_cle_seul() -> list[tuple[str, str, str]]:
    """Liste (classe, méthode, paramètre) à contrôler sur chaque surcharge.

    Une surcharge est une méthode redéfinie par une classe de ``linuxtools``
    alors qu'une de ses bases (dans ``linuxtools``) la définit déjà. Le
    contrôle porte sur chaque booléen que la base rend mot-clé seul.
    """
    classes = {
        c
        for module in _modules_linuxtools()
        for _, c in inspect.getmembers(module, inspect.isclass)
        if c.__module__.startswith("linuxtools")
    }
    cas: list[tuple[str, str, str]] = []
    for classe in classes:
        for nom, attribut in vars(classe).items():
            # ``__init__`` est inclus : il porte ``remote_write`` (gestionnaires
            # d'unités) et les booléens des loggers/notifiers.
            if not (
                inspect.isfunction(attribut)
                or isinstance(attribut, staticmethod | classmethod)
            ):
                continue
            for base in classe.__mro__[1:]:
                if nom in vars(base) and base.__module__.startswith("linuxtools"):
                    sig_base = inspect.signature(getattr(base, nom))
                    sig_surcharge = inspect.signature(getattr(classe, nom))
                    # Une surcharge qui n'expose pas le paramètre (ex.
                    # ``LinuxMountUnitManager.__init__``, sans ``remote_write``)
                    # ne peut pas le rendre positionnel : hors périmètre.
                    cas.extend(
                        (f"{classe.__module__}.{classe.__qualname__}", nom, p.name)
                        for p in sig_base.parameters.values()
                        if p.kind is inspect.Parameter.KEYWORD_ONLY
                        and _est_booleen(p)
                        and p.name in sig_surcharge.parameters
                    )
                    break
    return sorted(cas)


SURCHARGES = _surcharges_a_booleen_mot_cle_seul()


def test_surcharges_sont_collectees() -> None:
    """Garde-fou : la collecte ne doit pas être vide (sinon test aveugle)."""
    # Assert
    assert len(SURCHARGES) > 10


# Ensemble figé : si une base ET sa surcharge redeviennent positionnelles, le
# cas disparaît de la collecte ; ce test échoue alors au lieu de l'ignorer.
# Tout ajout/retrait légitime se fait ici, à la main.
SURCHARGES_ATTENDUES: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("linuxtools.commands.formatter.AnsiCommandFormatter", "_decorate", "dry"),
        ("linuxtools.commands.formatter.AnsiCommandFormatter", "_decorate", "is_root"),
        ("linuxtools.commands.formatter.PlainCommandFormatter", "_decorate", "dry"),
        ("linuxtools.commands.formatter.PlainCommandFormatter", "_decorate", "is_root"),
        ("linuxtools.commands.runner.LinuxCommandExecutor", "run", "probe"),
        (
            "linuxtools.commands.runner.LinuxCommandExecutor",
            "run_streaming",
            "merge_stderr",
        ),
        ("linuxtools.deploy.ssh_executor.SshCommandExecutor", "run", "probe"),
        (
            "linuxtools.deploy.ssh_executor.SshCommandExecutor",
            "run_streaming",
            "merge_stderr",
        ),
        ("linuxtools.identity.user.LinuxUserManager", "ensure_user", "create_home"),
        (
            "linuxtools.scripts.installer.LinuxCliInstaller",
            "install",
            "confirm_wrapper",
        ),
        (
            "linuxtools.systemd.automount_installer.SystemdAutomountInstaller",
            "install",
            "with_automount",
        ),
        ("linuxtools.systemd.base.UserUnitManager", "__init__", "remote_write"),
        (
            "linuxtools.systemd.mount.LinuxMountUnitManager",
            "enable_mount",
            "with_automount",
        ),
        (
            "linuxtools.systemd.mount.LinuxMountUnitManager",
            "install_mount_unit",
            "with_automount",
        ),
        (
            "linuxtools.systemd.service.LinuxServiceUnitManager",
            "__init__",
            "remote_write",
        ),
        ("linuxtools.systemd.timer.LinuxTimerUnitManager", "__init__", "remote_write"),
        (
            "linuxtools.systemd.user_service.LinuxUserServiceUnitManager",
            "__init__",
            "remote_write",
        ),
        (
            "linuxtools.systemd.user_timer.LinuxUserTimerUnitManager",
            "__init__",
            "remote_write",
        ),
    }
)


def test_surcharges_collectees_egalent_ensemble_attendu() -> None:
    """Aucun cas ne disparaît (ni n'apparaît) sans mise à jour explicite."""
    # Assert
    assert frozenset(SURCHARGES) == SURCHARGES_ATTENDUES


@pytest.mark.parametrize(
    ("classe", "methode", "parametre"),
    SURCHARGES,
    ids=[".".join(c) for c in SURCHARGES],
)
def test_surcharge_garde_booleen_mot_cle_seul(
    classe: str, methode: str, parametre: str
) -> None:
    """Une surcharge ne rend pas positionnel un booléen mot-clé seul de la base."""
    # Arrange
    module_nom, _, classe_nom = classe.rpartition(".")
    cls = getattr(importlib.import_module(module_nom), classe_nom)

    # Act
    parametres = inspect.signature(getattr(cls, methode)).parameters
    if parametre not in parametres:
        pytest.fail(f"{classe}.{methode} n'a plus le paramètre {parametre!r}")

    # Assert
    assert parametres[parametre].kind is inspect.Parameter.KEYWORD_ONLY


def test_executor_factory_dry_run_est_mot_cle_seul() -> None:
    """``ExecutorFactory.__call__`` reçoit ``dry_run`` en mot-clé seul."""
    # Act
    kind = inspect.signature(ExecutorFactory.__call__).parameters["dry_run"].kind

    # Assert
    assert kind is inspect.Parameter.KEYWORD_ONLY
