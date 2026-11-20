"""Non-régression de l'interface : les booléens sont en mot-clé seul."""

import dataclasses
import importlib
import inspect
import pkgutil
import types
from collections.abc import Callable
from types import ModuleType
from typing import Any, Union, get_args, get_origin

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


def _est_annotation_booleenne(annotation: object) -> bool:
    """Indique si l'annotation est exactement ``bool`` ou ``bool | None``.

    Comparaison exacte, pas de sous-chaîne : ``Callable[..., bool]`` n'est pas
    un booléen, c'est un appelable qui renvoie un booléen.
    """
    if annotation is bool:
        return True
    if isinstance(annotation, str):
        morceaux = {m.strip() for m in annotation.split("|")}
    elif get_origin(annotation) in (Union, types.UnionType):
        morceaux = {
            "bool" if a is bool else "None" if a is type(None) else "?"
            for a in get_args(annotation)
        }
    else:
        return False
    return morceaux in ({"bool"}, {"bool", "None"})


def _est_booleen_public(parametre: inspect.Parameter) -> bool:
    """Indique si le paramètre est un booléen (annotation exacte ou défaut)."""
    return _est_annotation_booleenne(parametre.annotation) or isinstance(
        parametre.default, bool
    )


def _init_genere_par_dataclass(classe: type, init: Callable[..., Any]) -> bool:
    """Indique si ``init`` est le ``__init__`` généré d'une dataclass.

    Le code généré par ``dataclasses`` n'a pas de fichier source (``<string>``) ;
    un ``__init__`` écrit à la main dans une dataclass reste donc contrôlé.
    """
    return dataclasses.is_dataclass(classe) and init.__code__.co_filename == "<string>"


def _fonctions_publiques_de_classe(classe: type) -> list[Callable[..., Any]]:
    """Liste ``__init__`` et les méthodes publiques définies dans ``linuxtools``.

    Les bases du MRO définies dans ``linuxtools`` sont parcourues : une méthode
    héritée d'une base non exportée reste ainsi contrôlée.
    """
    fonctions: list[Callable[..., Any]] = []
    for base in classe.__mro__:
        if not base.__module__.startswith("linuxtools"):
            continue
        for nom, attribut in vars(base).items():
            if nom != "__init__" and nom.startswith("_"):
                continue
            if isinstance(attribut, staticmethod | classmethod):
                attribut = attribut.__func__  # noqa: PLW2901
            if not inspect.isfunction(attribut):
                continue
            if nom == "__init__" and _init_genere_par_dataclass(base, attribut):
                continue
            fonctions.append(attribut)
    return fonctions


def _booleens_de_fonction(fonction: Callable[..., Any]) -> list[tuple[str, str]]:
    """Liste (identifiant, paramètre) des booléens de la signature."""
    identifiant = f"{fonction.__module__}.{fonction.__qualname__}"
    return [
        (identifiant, p.name)
        for p in inspect.signature(fonction).parameters.values()
        if _est_booleen_public(p)
    ]


def _surface_publique() -> list[object]:
    """Objets exportés par ``__all__`` de ``linuxtools`` et de ses sous-paquets."""
    return [
        getattr(module, nom)
        for module in [linuxtools, *_modules_linuxtools()]
        for nom in getattr(module, "__all__", ())
    ]


def _collecter_booleens_publics() -> dict[str, inspect.Parameter]:
    """Associe ``module.qualname.parametre`` à son ``inspect.Parameter``."""
    fonctions: dict[int, Callable[..., Any]] = {}
    for objet in _surface_publique():
        candidates: list[Callable[..., Any]]
        if inspect.isfunction(objet):
            candidates = [objet]
        elif inspect.isclass(objet):
            candidates = _fonctions_publiques_de_classe(objet)
        else:
            continue
        fonctions.update({id(f): f for f in candidates})
    booleens: dict[str, inspect.Parameter] = {}
    for fonction in fonctions.values():
        parametres = inspect.signature(fonction).parameters
        for identifiant, nom in _booleens_de_fonction(fonction):
            booleens[f"{identifiant}.{nom}"] = parametres[nom]
    return booleens


BOOLEENS_PUBLICS = _collecter_booleens_publics()

# Dérogations justifiées : identifiant ``module.qualname.parametre`` -> raison.
# Vide : tout booléen public est mot-clé seul (champs de dataclass exemptés).
EXCEPTIONS: dict[str, str] = {}


@pytest.mark.parametrize(
    "identifiant",
    sorted(BOOLEENS_PUBLICS),
)
def test_booleens_publics_sont_mot_cle_seul(identifiant: str) -> None:
    """Tout booléen d'API publique est KEYWORD_ONLY, sans dérogation tacite."""
    # Arrange / Act
    kind = BOOLEENS_PUBLICS[identifiant].kind

    # Assert
    if identifiant in EXCEPTIONS:
        pytest.skip(EXCEPTIONS[identifiant])
    assert kind is inspect.Parameter.KEYWORD_ONLY


def test_collecte_booleens_publics_n_est_pas_aveugle() -> None:
    """Garde-fou : une collecte quasi vide rendrait le test global aveugle.

    Mesure du 2026-11-20 : 60 booléens distincts (fonctions et méthodes
    uniques, hors champs de dataclass) ; 135 en comptant chaque ré-export.
    """
    # Assert
    assert len(BOOLEENS_PUBLICS) > 50


def test_exceptions_vide() -> None:
    """Aucune dérogation tacite : l'ajout d'une exception se voit en revue."""
    # Assert
    assert EXCEPTIONS == {}


def test_exceptions_ne_sont_pas_perimees() -> None:
    """Chaque exception désigne un booléen public qui existe encore."""
    # Act
    perimees = sorted(set(EXCEPTIONS) - set(BOOLEENS_PUBLICS))

    # Assert
    assert perimees == []


@dataclasses.dataclass
class _ExempleDataclass:
    """Dataclass d'essai : booléen positionnel via le ``__init__`` généré."""

    actif: bool = False


@dataclasses.dataclass
class _ExempleDataclassInitManuel:
    """Dataclass d'essai : le ``__init__`` écrit à la main est contrôlé."""

    def __init__(self, actif: bool = False) -> None:
        self.actif = actif


class _ExempleClasse:
    """Classe d'essai : ``__init__`` ordinaire."""

    def __init__(self, actif: bool = False) -> None:
        self.actif = actif


def test_init_genere_de_dataclass_est_exempte() -> None:
    """Seul le ``__init__`` généré est exempté, pas un ``__init__`` manuel."""
    # Act
    generes = [
        _init_genere_par_dataclass(c, c.__init__)
        for c in (_ExempleDataclass, _ExempleDataclassInitManuel, _ExempleClasse)
    ]

    # Assert
    assert generes == [True, False, False]


def test_annotation_exacte_callable_vers_bool_n_est_pas_un_booleen() -> None:
    """``Callable[..., bool]`` renvoie un booléen sans en être un."""

    # Arrange
    def fonction(
        a: Callable[..., bool], b: bool, c: bool | None, d: "bool", e: "bool | None"
    ) -> None:
        pass

    # Act
    est_booleen = [
        _est_booleen_public(p) for p in inspect.signature(fonction).parameters.values()
    ]

    # Assert
    assert est_booleen == [False, True, True, True, True]
