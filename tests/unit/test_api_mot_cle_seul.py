"""Non-régression de l'interface : les booléens sont en mot-clé seul."""

import dataclasses
import importlib
import inspect
import pkgutil
import sys
import types
from collections.abc import Callable, Iterable
from pathlib import Path
from types import ModuleType
from typing import (
    Annotated,
    Any,
    Literal,
    NamedTuple,
    Optional,
    Self,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import pytest

import linuxtools
from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.deployer import Deployer
from linuxtools.devtools.cli import ExecutorFactory
from linuxtools.logging.file_logger import FileLogger
from linuxtools.systemd.base import MountUnitManager
from linuxtools.systemd.config_loaders.mount_loader import AutomountSettings
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


# --------------------------------------------------------------------------
# Import des modules du paquet
# --------------------------------------------------------------------------

_PAQUET = "linuxtools"


# Extras optionnels dont l'absence est tolérée (noms d'import) : webapitools
# (extra ``network``), pydantic (``validation``), dotenv et keyring
# (``credentials``). Tout autre import tiers manquant est une faute, pas un extra.
_EXTRAS_CONNUS = frozenset({"webapitools", "pydantic", "dotenv", "keyring"})


def _est_extra_absent(exc: BaseException) -> bool:
    """Indique si l'exception signale l'absence d'un extra optionnel connu.

    Python nomme la racine quand un paquet est absent : un sous-module introuvable
    (``keyring.backends``) signale un extra installé mais cassé, donc une faute.
    """
    return (
        isinstance(exc, ModuleNotFoundError)
        and exc.name is not None
        and exc.name in _EXTRAS_CONNUS
    )


def _importer_modules(
    chemin: Iterable[str], prefixe: str
) -> tuple[list[ModuleType], list[str]]:
    """Importe tous les modules d'un paquet et rapporte ceux qui sont cassés.

    Retourne ``(modules importés, échecs)``. Seule l'absence d'un extra optionnel
    connu (``_EXTRAS_CONNUS``) est tolérée, sans échec. Tout autre échec d'import
    (import tiers inconnu, symbole manquant, import circulaire, module du paquet
    introuvable) est consigné, une fois par module, pour que
    ``test_modules_du_paquet_s_importent`` échoue avec un message clair, au lieu de
    masquer des API publiques.
    """
    modules: list[ModuleType] = []
    echecs: dict[str, str] = {}

    def noter(nom: str) -> None:
        exc = sys.exception()
        if exc is None or _est_extra_absent(exc):
            return
        # ``walk_packages`` signale un sous-paquet cassé, puis il est réimporté.
        echecs.setdefault(nom, f"{nom} : {type(exc).__name__} : {exc}")

    for info in pkgutil.walk_packages(chemin, prefixe, onerror=noter):
        # Un ``__main__`` s'exécuterait à l'import et fausserait ``runpy``.
        if info.name.endswith(".__main__"):
            continue
        try:
            modules.append(importlib.import_module(info.name))
        except ImportError:
            noter(info.name)
    return modules, list(echecs.values())


MODULES, ECHECS_IMPORT = _importer_modules(linuxtools.__path__, f"{_PAQUET}.")

# --------------------------------------------------------------------------
# Définition unique du « booléen public »
# --------------------------------------------------------------------------

# Formes textuelles reconnues quand l'annotation en chaîne ne se résout pas (nom
# importé sous ``TYPE_CHECKING``) : comparaison exacte, jamais de sous-chaîne,
# car ``Callable[..., bool]`` contient « bool » sans être un booléen. Seules les
# formes qui s'appuient sur ``typing`` figurent ici : ``bool``, ``bool | None`` et
# ``None | bool`` n'emploient que des builtins, toujours résolus, donc jamais en repli.
_FORMES_TEXTE_BOOLEENNES = frozenset(
    {
        "Optional[bool]",
        "Union[bool,None]",
        "Union[None,bool]",
    }
)


def _est_type_booleen(type_: object) -> bool:
    """Indique si un type résolu est ``bool`` (``None``, ``Literal`` booléen inclus)."""
    origine = get_origin(type_)
    if type_ is bool:
        return True
    if origine is Annotated:
        return _est_type_booleen(get_args(type_)[0])
    if origine is Literal:
        return all(isinstance(valeur, bool) for valeur in get_args(type_))
    if origine in (Union, types.UnionType):
        membres = [a for a in get_args(type_) if a is not type(None)]
        return bool(membres) and all(_est_type_booleen(a) for a in membres)
    return False


def _est_annotation_booleenne(fonction: Callable[..., Any], annotation: object) -> bool:
    """Indique si l'annotation désigne ``bool`` ou ``bool | None``.

    Les annotations en chaîne (modules ``from __future__ import annotations``)
    sont résolues dans les globaux de la fonction : ``Optional[bool]``,
    ``Annotated[bool, ...]``, ``Literal[True]`` et les alias (``Flag = bool``)
    sont donc reconnus. Sans résolution possible, repli sur la forme textuelle
    exacte.
    """
    if isinstance(annotation, str):
        brouillon = types.SimpleNamespace(__annotations__={"p": annotation})
        try:
            resolue = get_type_hints(brouillon, globalns=fonction.__globals__)["p"]
        except (NameError, AttributeError, TypeError, SyntaxError):
            return "".join(annotation.split()) in _FORMES_TEXTE_BOOLEENNES
        return _est_type_booleen(resolue)
    return _est_type_booleen(annotation)


def _est_booleen_public(
    fonction: Callable[..., Any], parametre: inspect.Parameter
) -> bool:
    """Indique si le paramètre est un booléen (annotation exacte ou défaut)."""
    return _est_annotation_booleenne(fonction, parametre.annotation) or isinstance(
        parametre.default, bool
    )


def _surcharges_a_booleen_mot_cle_seul() -> list[tuple[str, str, str]]:
    """Liste (classe, méthode, paramètre) à contrôler sur chaque surcharge.

    Une surcharge est une méthode redéfinie par une classe de ``linuxtools``
    alors qu'une de ses bases (dans ``linuxtools``) la définit déjà. Le
    contrôle porte sur chaque booléen que la base rend mot-clé seul.
    """
    classes = {
        c
        for module in MODULES
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
                    fonction_base = getattr(base, nom)
                    sig_base = inspect.signature(fonction_base)
                    sig_surcharge = inspect.signature(getattr(classe, nom))
                    # Une surcharge qui n'expose pas le paramètre (ex.
                    # ``LinuxMountUnitManager.__init__``, sans ``remote_write``)
                    # ne peut pas le rendre positionnel : hors périmètre.
                    cas.extend(
                        (f"{classe.__module__}.{classe.__qualname__}", nom, p.name)
                        for p in sig_base.parameters.values()
                        if p.kind is inspect.Parameter.KEYWORD_ONLY
                        and _est_booleen_public(fonction_base, p)
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
        ("linuxtools.systemd.executor.UserSystemdExecutor", "_run_systemctl", "probe"),
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


# --------------------------------------------------------------------------
# Collecte de la surface publique
# --------------------------------------------------------------------------


def _est_namedtuple(classe: type) -> bool:
    """Indique si la classe est un ``NamedTuple`` (ou ``namedtuple``)."""
    return issubclass(classe, tuple) and hasattr(classe, "_fields")


def _methode_generee(classe: type, nom: str, fonction: Callable[..., Any]) -> bool:
    """Indique si ``fonction`` est le code généré d'une dataclass ou d'un NamedTuple.

    Décision 4a (CHANGELOG 3.0.0) : la construction positionnelle des champs de
    dataclass et de ``NamedTuple`` est inchangée. Seuls sont exemptés le
    ``__init__`` généré d'une dataclass et le ``__new__`` généré d'un
    ``NamedTuple`` : le code généré n'a pas de fichier source (``<string>``), donc
    un ``__init__`` ou ``__new__`` écrit à la main reste contrôlé, et un
    ``__init__`` produit par ``exec`` hors dataclass aussi.
    """
    if fonction.__code__.co_filename != "<string>":
        return False
    return (nom == "__init__" and dataclasses.is_dataclass(classe)) or (
        nom == "__new__" and _est_namedtuple(classe)
    )


# Méthodes spéciales qui font partie de l'API publique (appel, construction).
_SPECIALES_PUBLIQUES = frozenset({"__init__", "__new__", "__call__"})


def _fonctions_publiques_de_classe(
    classe: type, vues: set[type] | None = None, prefixe: str = _PAQUET
) -> list[Callable[..., Any]]:
    """Liste les fonctions publiques définies dans ``linuxtools`` par la classe.

    Sont retenus : ``__init__``, ``__new__``, ``__call__``, les méthodes sans
    ``_`` initial (``staticmethod`` et ``classmethod`` compris), celles des bases
    du MRO définies dans ``linuxtools`` (même non exportées) et celles des
    classes imbriquées publiques.
    """
    vues = set() if vues is None else vues
    if classe in vues:
        return []
    vues.add(classe)
    fonctions: list[Callable[..., Any]] = []
    for base in classe.__mro__:
        if not base.__module__.startswith(prefixe):
            continue
        for nom, attribut in vars(base).items():
            if nom.startswith("_") and nom not in _SPECIALES_PUBLIQUES:
                continue
            if inspect.isclass(attribut) and attribut.__qualname__.startswith(
                f"{base.__qualname__}."
            ):
                fonctions.extend(
                    _fonctions_publiques_de_classe(attribut, vues, prefixe)
                )
                continue
            fonction = (
                attribut.__func__
                if isinstance(attribut, staticmethod | classmethod)
                else attribut
            )
            if inspect.isfunction(fonction) and not _methode_generee(
                base, nom, fonction
            ):
                fonctions.append(fonction)
    return fonctions


def _objets_publics_du_module(module: ModuleType) -> list[object]:
    """Liste les fonctions et classes publiques définies dans le module."""
    return [
        objet
        for nom, objet in vars(module).items()
        if not nom.startswith("_")
        and (inspect.isfunction(objet) or inspect.isclass(objet))
        and objet.__module__ == module.__name__
    ]


def _surface_publique(modules: Iterable[ModuleType]) -> list[object]:
    """Objets publics : ``__all__``, ou les objets définis dans un module sans.

    Un module sans ``__all__`` n'est exploré que si son paquet parent n'en a pas
    non plus (``linuxtools.devtools`` : ses modules sont l'API). Un extra
    optionnel connu absent (``_EXTRAS_CONNUS``) fait ignorer l'export concerné ;
    tout autre ``ModuleNotFoundError`` remonte.
    """
    objets: list[object] = []
    for module in modules:
        if hasattr(module, "__all__"):
            for nom in module.__all__:
                try:
                    objets.append(getattr(module, nom))
                except ModuleNotFoundError as exc:
                    if not _est_extra_absent(exc):
                        raise
            continue
        parent_nom = module.__name__.rpartition(".")[0]
        parent = sys.modules.get(parent_nom)
        if parent is not None and not hasattr(parent, "__all__"):
            objets.extend(_objets_publics_du_module(module))
    return objets


def _collecter_booleens_publics(
    objets: Iterable[object],
) -> dict[str, inspect.Parameter]:
    """Associe ``module.qualname.parametre`` à son ``inspect.Parameter``."""
    fonctions: dict[int, Callable[..., Any]] = {}
    for objet in objets:
        candidates: list[Callable[..., Any]]
        if inspect.isfunction(objet):
            candidates = [objet]
        elif inspect.isclass(objet):
            candidates = _fonctions_publiques_de_classe(objet)
        else:
            continue
        fonctions.update({id(f): f for f in candidates})
    return {
        f"{fonction.__module__}.{fonction.__qualname__}.{parametre.name}": parametre
        for fonction in fonctions.values()
        for parametre in inspect.signature(fonction).parameters.values()
        if _est_booleen_public(fonction, parametre)
    }


BOOLEENS_PUBLICS = _collecter_booleens_publics(
    _surface_publique([linuxtools, *MODULES])
)

# Dérogations justifiées : identifiant ``module.qualname.parametre`` -> raison.
# Vide : tout booléen public est mot-clé seul (champs de dataclass et de
# NamedTuple exemptés, cf. ``_methode_generee``).
EXCEPTIONS: dict[str, str] = {}


def _exceptions_invalides(
    exceptions: dict[str, str], booleens: dict[str, inspect.Parameter]
) -> list[str]:
    """Liste les dérogations sans raison, périmées ou inutiles."""
    problemes: list[str] = []
    for identifiant, raison in sorted(exceptions.items()):
        if not raison.strip():
            problemes.append(f"{identifiant} : raison vide")
        if identifiant not in booleens:
            problemes.append(f"{identifiant} : exception périmée (booléen disparu)")
        elif booleens[identifiant].kind is inspect.Parameter.KEYWORD_ONLY:
            problemes.append(f"{identifiant} : exception inutile (déjà mot-clé seul)")
    return problemes


@pytest.mark.parametrize(
    "identifiant",
    sorted(BOOLEENS_PUBLICS),
)
def test_booleens_publics_sont_mot_cle_seul(identifiant: str) -> None:
    """Tout booléen d'API publique est KEYWORD_ONLY, sauf dérogation justifiée."""
    # Arrange
    if identifiant in EXCEPTIONS:
        pytest.skip(EXCEPTIONS[identifiant])

    # Act
    kind = BOOLEENS_PUBLICS[identifiant].kind

    # Assert
    assert kind is inspect.Parameter.KEYWORD_ONLY


def test_modules_du_paquet_s_importent() -> None:
    """Un module du paquet qui ne s'importe pas fait échouer, il n'est pas ignoré."""
    # Assert
    assert ECHECS_IMPORT == []


def test_exceptions_sont_justifiees_et_utiles() -> None:
    """Chaque dérogation a une raison, existe encore et sert encore."""
    # Act
    problemes = _exceptions_invalides(EXCEPTIONS, BOOLEENS_PUBLICS)

    # Assert
    assert problemes == []


# --------------------------------------------------------------------------
# Tests du mécanisme (prédicat, collecte, exemptions, garde-fous)
# --------------------------------------------------------------------------

_Drapeau = bool  # alias : ``Flag = bool`` dans le code applicatif


def _modele(p: object) -> None:
    """Fonction modèle : seule l'annotation de ``p`` est remplacée par les tests."""


def _parametre(
    annotation: object,
    *,
    defaut: object = inspect.Parameter.empty,
    globales: dict[str, Any] | None = None,
) -> tuple[Callable[..., Any], inspect.Parameter]:
    """Fabrique une fonction à un paramètre ``p`` d'annotation et défaut donnés."""
    fonction = types.FunctionType(
        _modele.__code__,
        globals() if globales is None else globales,
        "modele",
        None if defaut is inspect.Parameter.empty else (defaut,),
    )
    fonction.__annotations__ = {"p": annotation}
    return fonction, inspect.signature(fonction).parameters["p"]


# (annotation en objet ou en chaîne, est-ce un booléen ?)
FORMES: list[tuple[object, bool]] = [
    (bool, True),
    (bool | None, True),
    (Optional[bool], True),  # noqa: UP045 -- la forme Optional est le cas testé
    (Union[bool, None], True),  # noqa: UP007 -- la forme Union est le cas testé
    (Annotated[bool, "x"], True),
    (Literal[True], True),
    (Literal[True, False] | None, True),
    (_Drapeau, True),
    (Callable[..., bool], False),
    (bool | int, False),
    (int, False),
    (Optional[int], False),  # noqa: UP045 -- idem
    (Literal[1], False),
    (Literal[True, 1], False),  # tous les membres doivent être booléens
    (None, False),
]
FORMES_EN_CHAINE: list[tuple[object, bool]] = [
    ("bool", True),
    ("bool | None", True),
    ("None | bool", True),
    ("Optional[bool]", True),
    ("Union[bool, None]", True),
    ("Annotated[bool, 'x']", True),
    ("Literal[True]", True),
    ("_Drapeau", True),
    ("'bool'", True),
    ("Callable[..., bool]", False),
    ("bool | int", False),
    ("Optional[int]", False),
    ("Literal[1]", False),
]


@pytest.mark.parametrize(
    ("annotation", "attendu"),
    [*FORMES, *FORMES_EN_CHAINE],
    ids=[str(a) for a, _ in [*FORMES, *FORMES_EN_CHAINE]],
)
def test_forme_d_annotation_reconnue_comme_booleen(
    annotation: object, attendu: bool
) -> None:
    # Arrange
    fonction, parametre = _parametre(annotation)

    # Act
    resultat = _est_booleen_public(fonction, parametre)

    # Assert
    assert resultat is attendu


@pytest.mark.parametrize(
    ("annotation", "attendu"),
    [
        ("bool", True),
        ("bool | None", True),
        ("Optional[bool]", True),
        ("Union[bool, None]", True),
        ("None | bool", True),
        ("Union[None, bool]", True),
        ("Callable[..., bool]", False),  # contient « bool » : pas une sous-chaîne
        ("Rappel | bool", False),
        ("Optional[int]", False),
        # annotations invalides : le repli remplace l'exception, jamais un échec
        ("bool |", False),  # SyntaxError
        ("bool | 3", False),  # TypeError
        ("bool.fantome", False),  # AttributeError
    ],
)
def test_annotation_non_resoluble_compare_la_forme_textuelle_exacte(
    annotation: str, attendu: bool
) -> None:
    # Arrange : globaux vides, ni ``Optional`` ni ``Callable`` ne se résolvent.
    # ``bool``, ``bool | None`` et ``None | bool`` n'emploient que des builtins : ils
    # passent par la résolution, pas par le repli textuel (hors de ce test).
    fonction, parametre = _parametre(annotation, globales={})

    # Act
    resultat = _est_booleen_public(fonction, parametre)

    # Assert
    assert resultat is attendu


@pytest.mark.parametrize(
    ("annotation", "defaut", "attendu"),
    [
        (object, True, True),
        (object, False, True),
        (object, None, False),
        (int, 0, False),
    ],
)
def test_defaut_booleen_suffit_a_faire_un_booleen(
    annotation: object, defaut: object, attendu: bool
) -> None:
    # Arrange
    fonction, parametre = _parametre(annotation, defaut=defaut)

    # Act
    resultat = _est_booleen_public(fonction, parametre)

    # Assert
    assert resultat is attendu


# --- Exemptions : code généré par dataclass ou NamedTuple -------------------


@dataclasses.dataclass
class _ExempleDataclass:
    """Dataclass d'essai : booléen positionnel via le ``__init__`` généré."""

    actif: bool = False


@dataclasses.dataclass
class _ExempleDataclassInitManuel:
    """Dataclass d'essai : le ``__init__`` écrit à la main est contrôlé."""

    def __init__(self, actif: bool = False) -> None:
        self.actif = actif


class _ExempleNamedTuple(NamedTuple):
    """NamedTuple d'essai : booléen positionnel via le ``__new__`` généré."""

    actif: bool = False


class _ExempleNamedTupleNewManuel(NamedTuple):
    """NamedTuple d'essai : ``fabrique`` manuelle, contrôlée."""

    actif: bool = False

    @classmethod
    def fabrique(cls, actif: bool = False) -> "_ExempleNamedTupleNewManuel":
        return cls(actif)


def _classe_init_exec() -> type:
    """Classe ordinaire dont ``__init__`` est produit par ``exec`` (``<string>``)."""
    espace: dict[str, Any] = {}
    exec("def __init__(self, actif=False):\n    self.actif = actif", espace)  # noqa: S102 -- produire du code sans fichier source
    return type("_ExempleInitExec", (), {"__init__": espace["__init__"]})


def _classe_new_exec() -> type:
    """Classe ordinaire (pas un NamedTuple) dont ``__new__`` vient de ``exec``."""
    espace: dict[str, Any] = {}
    exec(  # noqa: S102 -- produire du code sans fichier source
        "def __new__(cls, actif=False):\n    return object.__new__(cls)", espace
    )
    return type("_ExempleNewExec", (), {"__new__": espace["__new__"]})


class _ExempleClasse:
    """Classe d'essai : ``__init__`` ordinaire."""

    def __init__(self, actif: bool = False) -> None:
        self.actif = actif


def test_code_genere_est_exempte_et_le_code_manuel_non() -> None:
    # Arrange
    cas = [
        (_ExempleDataclass, "__init__"),
        (_ExempleDataclassInitManuel, "__init__"),
        (_ExempleNamedTuple, "__new__"),
        (_ExempleNamedTupleNewManuel, "fabrique"),
        (_ExempleClasse, "__init__"),
        (_classe_init_exec(), "__init__"),
        (_classe_new_exec(), "__new__"),
    ]

    # Act
    generes = [_methode_generee(c, n, getattr(c, n)) for c, n in cas]

    # Assert
    assert generes == [True, False, True, False, False, False, False]


def test_champs_de_namedtuple_reel_exemptes_comme_les_dataclasses() -> None:
    """``AutomountSettings`` (NamedTuple) : ``with_automount`` reste positionnel."""
    # Arrange
    ids = [i for i in BOOLEENS_PUBLICS if "AutomountSettings" in i]

    # Assert
    assert ids == []
    assert _methode_generee(AutomountSettings, "__new__", AutomountSettings.__new__)


# --- Collecte des fonctions d'une classe -----------------------------------


class _BasePrivee:
    """Base non exportée : ses méthodes publiques sont héritées."""

    def methode_heritee(self, drapeau: bool = False) -> None:
        """Méthode héritée par une classe exportée."""


class _Exportee(_BasePrivee):
    """Classe d'essai couvrant chaque catégorie de fonctions publiques."""

    def __new__(cls, drapeau: bool = False) -> Self:
        return super().__new__(cls)

    def __call__(self, drapeau: bool = False) -> None:
        """Appel de l'instance."""

    def __repr__(self) -> str:
        return "ignorée : méthode spéciale hors API"

    def _privee(self, drapeau: bool = False) -> None:
        """Méthode privée : hors API."""

    @staticmethod
    def statique(drapeau: bool = False) -> None:
        """Méthode statique."""

    @classmethod
    def de_classe(cls, drapeau: bool = False) -> None:
        """Méthode de classe."""

    class Imbriquee:
        """Classe imbriquée publique."""

        def methode(self, drapeau: bool = False) -> None:
            """Méthode d'une classe imbriquée."""


def test_fonctions_publiques_couvrent_chaque_categorie() -> None:
    # Act
    noms = sorted(
        f.__qualname__
        for f in _fonctions_publiques_de_classe(_Exportee, prefixe=__name__)
    )

    # Assert
    assert noms == [
        "_BasePrivee.methode_heritee",
        "_Exportee.Imbriquee.methode",
        "_Exportee.__call__",
        "_Exportee.__new__",
        "_Exportee.de_classe",
        "_Exportee.statique",
    ]


def test_fonctions_publiques_ignorent_les_bases_hors_du_paquet() -> None:
    # Act
    noms = [f.__qualname__ for f in _fonctions_publiques_de_classe(_Exportee)]

    # Assert : le préfixe par défaut est ``linuxtools`` : rien ici n'en relève
    assert noms == []


# --- Sentinelles par catégorie sur la vraie surface ------------------------

SENTINELLES = {
    "fonction libre": "linuxtools.logging.retention.purge_old_logs.dry_run",
    "__init__": "linuxtools.deploy.deployer.Deployer.__init__.dry_run",
    "méthode": "linuxtools.commands.builder.CommandBuilder.with_option_if.condition",
    "classmethod": "linuxtools.deploy.deployer.Deployer.for_target.dry_run",
    "base non exportée": (
        "linuxtools.systemd.base._BaseUnitManagerMixin.disable.ignore_errors"
    ),
    "__call__": "linuxtools.devtools.cli.ExecutorFactory.__call__.dry_run",
    "module sans __all__": "linuxtools.devtools.bumper.ConsumerBumper.__init__.dry_run",
}


@pytest.mark.parametrize("identifiant", SENTINELLES.values(), ids=SENTINELLES.keys())
def test_sentinelle_de_chaque_categorie_est_collectee(identifiant: str) -> None:
    """Une régression de la collecte (catégorie perdue) ne passe plus inaperçue."""
    # Assert
    assert identifiant in BOOLEENS_PUBLICS


def test_collecte_booleens_publics_n_est_pas_aveugle() -> None:
    """Garde-fou de volume : 64 booléens distincts mesurés, seuil à 50."""
    # Assert
    assert len(BOOLEENS_PUBLICS) > 50


# --- Dérogations ------------------------------------------------------------


def _parametre_positionnel() -> inspect.Parameter:
    return inspect.Parameter("p", inspect.Parameter.POSITIONAL_OR_KEYWORD)


def _parametre_mot_cle() -> inspect.Parameter:
    return inspect.Parameter("p", inspect.Parameter.KEYWORD_ONLY)


def test_exception_valide_n_est_pas_un_probleme() -> None:
    # Act
    problemes = _exceptions_invalides(
        {"a.f.p": "décision 4a"}, {"a.f.p": _parametre_positionnel()}
    )

    # Assert
    assert problemes == []


@pytest.mark.parametrize(
    ("exceptions", "attendu"),
    [
        ({"a.f.p": " "}, "a.f.p : raison vide"),
        ({"a.g.q": "raison"}, "a.g.q : exception périmée (booléen disparu)"),
        ({"a.h.p": "raison"}, "a.h.p : exception inutile (déjà mot-clé seul)"),
    ],
    ids=["raison vide", "périmée", "inutile"],
)
def test_exception_sans_raison_perimee_ou_inutile_est_signalee(
    exceptions: dict[str, str], attendu: str
) -> None:
    # Arrange
    booleens = {
        "a.f.p": _parametre_positionnel(),
        "a.h.p": _parametre_mot_cle(),
    }

    # Act
    problemes = _exceptions_invalides(exceptions, booleens)

    # Assert
    assert problemes == [attendu]


# --- Import des modules et surface -----------------------------------------


def _creer_paquet(racine: Path, nom: str, modules: dict[str, str]) -> None:
    paquet = racine / nom
    paquet.mkdir()
    (paquet / "__init__.py").write_text("")
    for module, source in modules.items():
        (paquet / f"{module}.py").write_text(source)


def test_import_tolere_un_extra_absent_et_signale_un_module_casse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    nom = "paquet_essai_booleens"
    _creer_paquet(
        tmp_path,
        nom,
        {
            "bon": "X = 1\n",
            "extra": "import keyring\n",
            "tiers": "import tiers_inconnu_xyz\n",
            "casse": f"import {nom}.fantome\n",
            "circulaire": "from paquet_essai_booleens.bon import ABSENT\n",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(sys.modules, "keyring", None)  # extra connu « absent »
    try:
        # Act
        modules, echecs = _importer_modules([str(tmp_path / nom)], f"{nom}.")
    finally:
        for cle in [c for c in sys.modules if c.startswith(nom)]:
            del sys.modules[cle]

    # Assert
    assert [m.__name__ for m in modules] == [f"{nom}.bon"]
    assert sorted(e.split(" : ")[0] for e in echecs) == [
        f"{nom}.casse",
        f"{nom}.circulaire",
        f"{nom}.tiers",
    ]


def test_import_signale_une_seule_fois_un_sous_paquet_casse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    nom = "paquet_essai_sous_paquet"
    _creer_paquet(tmp_path, nom, {})
    sous = tmp_path / nom / "sous"
    sous.mkdir()
    (sous / "__init__.py").write_text('raise ImportError("sous-paquet cassé")\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        # Act
        _, echecs = _importer_modules([str(tmp_path / nom)], f"{nom}.")
    finally:
        for cle in [c for c in sys.modules if c.startswith(nom)]:
            del sys.modules[cle]

    # Assert
    assert echecs == [f"{nom}.sous : ImportError : sous-paquet cassé"]


@pytest.mark.parametrize(
    ("exception", "attendu"),
    [
        (ModuleNotFoundError(name="webapitools"), True),
        (ModuleNotFoundError(name="pydantic"), True),
        (ModuleNotFoundError(name="dotenv"), True),
        (ModuleNotFoundError(name="keyring"), True),
        # sous-module introuvable d'un extra installé : faute, pas une absence d'extra
        (ModuleNotFoundError(name="keyring.backends"), False),
        (ModuleNotFoundError(name="requests"), False),
        (ModuleNotFoundError(name="linuxtools.fantome"), False),
        (ModuleNotFoundError(), False),
        (ImportError("symbole manquant", name="keyring"), False),
    ],
    ids=lambda v: getattr(v, "name", None) or str(v),
)
def test_seuls_les_extras_connus_sont_toleres(
    exception: ImportError, attendu: bool
) -> None:
    # Act
    resultat = _est_extra_absent(exception)

    # Assert
    assert resultat is attendu


class _ModuleParesseux(ModuleType):
    """Module dont l'export ``objet`` lève l'exception donnée (extra absent...)."""

    def __init__(self, nom: str, exception: Exception) -> None:
        super().__init__(nom)
        self.__all__ = ["objet"]
        self._exception = exception

    def __getattr__(self, nom: str) -> object:
        raise self._exception


def test_export_d_un_extra_absent_est_ignore() -> None:
    # Arrange
    module = _ModuleParesseux(
        "linuxtools.fictif", ModuleNotFoundError(name="webapitools")
    )

    # Act
    objets = _surface_publique([module])

    # Assert
    assert objets == []


@pytest.mark.parametrize("nom", ["linuxtools.fantome", "tiers_inconnu_xyz"])
def test_export_d_un_module_introuvable_hors_extras_remonte(nom: str) -> None:
    # Arrange
    module = _ModuleParesseux("linuxtools.fictif", ModuleNotFoundError(name=nom))

    # Act / Assert
    with pytest.raises(ModuleNotFoundError):
        _surface_publique([module])


def _fonction_definie_dans(nom_module: str) -> Callable[..., None]:
    def publique() -> None:
        """Fonction publique d'essai."""

    publique.__module__ = nom_module
    return publique


def _module_avec(nom: str, **contenu: object) -> ModuleType:
    module = ModuleType(nom)
    vars(module).update(contenu)
    return module


def test_module_sans_all_dans_un_paquet_sans_all_est_explore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas de ``linuxtools.devtools`` : pas de ``__all__``, ses modules sont l'API."""
    # Arrange
    publique = _fonction_definie_dans("pk_sans_all.mod")
    importee = _fonction_definie_dans("autre_module")
    enfant = _module_avec(
        "pk_sans_all.mod", publique=publique, importee=importee, _privee=publique
    )
    monkeypatch.setitem(sys.modules, "pk_sans_all", ModuleType("pk_sans_all"))

    # Act
    objets = _surface_publique([enfant])

    # Assert : ni l'objet importé d'ailleurs, ni le nom privé
    assert objets == [publique]


def test_module_sans_all_dans_un_paquet_avec_all_n_est_pas_explore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hors ``__all__`` d'un paquet qui en déclare un : interne par choix."""
    # Arrange
    interne = _fonction_definie_dans("pk_avec_all.mod")
    enfant = _module_avec("pk_avec_all.mod", interne=interne)
    parent = _module_avec("pk_avec_all", __all__=[])
    monkeypatch.setitem(sys.modules, "pk_avec_all", parent)

    # Act
    objets = _surface_publique([enfant])

    # Assert
    assert objets == []


def test_module_avec_all_exporte_exactement_ses_noms() -> None:
    # Arrange
    exporte = _fonction_definie_dans("m")
    module = _module_avec("m", __all__=["exporte"], exporte=exporte, autre=exporte)

    # Act
    objets = _surface_publique([module])

    # Assert
    assert objets == [exporte]
