"""Contrat de sécurité du runtime ``jobnotify/runtime.py`` (T5, [SEC]).

Le runtime est copié puis exécuté EN ROOT par ``/usr/bin/python3 -I``, hors
venv : ces tests lisent son code source (analyse ``ast``, sans l'importer) et
vérifient les propriétés qui ne doivent jamais régresser : stdlib seule, aucun
code dynamique, binaires en chemins absolus, ``subprocess`` confiné au runner.

Les ``Outcome`` de ``spec.py`` et du runtime sont le même objet (F05) :
``test_parite_spec_runtime.py::test_spec_n_a_qu_une_source_de_constantes`` le
vérifie. L'exécution réelle isolée est dans
``tests/integration/test_runtime_isole.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import linuxtools.jobnotify.runtime as runtime_module

_RUNTIME_PATH = Path(runtime_module.__file__)
_FORBIDDEN_NAMES = frozenset({"exec", "eval", "compile", "__import__", "importlib"})
_ARGV_SINKS = frozenset({"_call", "_deliver"})  # fonctions qui lancent un argv
_RUNNER_FUNCTION = "default_runner"


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    """Arbre syntaxique du runtime."""
    return ast.parse(_RUNTIME_PATH.read_text(encoding="utf-8"))


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Constantes de module de type ``NOM = "texte"``."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _enclosing_functions(
    tree: ast.Module,
) -> dict[ast.AST, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Associe chaque nœud à la fonction qui le contient (la plus interne)."""
    owners: dict[ast.AST, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for func in ast.walk(tree):
        if isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            for child in ast.walk(func):
                owners[child] = func
    return owners


def test_runtime_n_importe_que_la_stdlib(tree: ast.Module) -> None:
    """Seuls des modules de la stdlib sont importés (aucun linuxtools, aucun tiers)."""
    importes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            importes += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # Un import relatif (level > 0) vise le paquet : refusé.
            importes.append(node.module or "" if node.level == 0 else f".{node.module}")

    hors_stdlib = sorted(
        nom for nom in importes if nom.split(".")[0] not in sys.stdlib_module_names
    )
    assert importes, "aucun import détecté : l'analyse ne lit plus le runtime"
    assert hors_stdlib == []


def test_runtime_sans_exec_eval_ni_import_dynamique(tree: ast.Module) -> None:
    """Aucun ``exec``, ``eval``, ``compile`` (builtin), ``__import__``, importlib."""
    trouves: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            trouves.append(f"{node.id} (ligne {node.lineno})")
        elif isinstance(node, ast.Import | ast.ImportFrom):
            noms = [a.name for a in node.names]
            if isinstance(node, ast.ImportFrom):
                noms.append(node.module or "")
            trouves += [
                f"import {nom} (ligne {node.lineno})"
                for nom in noms
                if nom.split(".")[0] == "importlib"
            ]
        elif isinstance(node, ast.Attribute) and node.attr == "import_module":
            trouves.append(f"import_module (ligne {node.lineno})")
    assert trouves == []


def _head_problems(
    node: ast.expr,
    scope: ast.AST,
    constants: dict[str, str],
    functions: dict[str, ast.FunctionDef],
    depth: int = 0,
) -> list[str]:
    """Liste les raisons pour lesquelles la tête d'un argv n'est pas prouvée absolue.

    Args:
        node: Expression de l'argv (liste littérale, nom de variable, appel).
        scope: Fonction contenant l'appel (pour résoudre les variables locales).
        constants: Constantes de module chaînes.
        functions: Fonctions de module, par nom.
        depth: Profondeur de résolution (garde-fou contre les boucles).

    Returns:
        Les problèmes trouvés ; liste vide si la tête est un chemin absolu.
    """
    if depth > 5:
        return ["résolution trop profonde"]
    suite = (scope, constants, functions, depth + 1)
    if isinstance(node, ast.List | ast.Tuple):
        return _element_problems(node.elts[0] if node.elts else None, constants)
    if isinstance(node, ast.Name):
        valeurs = [
            sub.value
            for sub in ast.walk(scope)
            if isinstance(sub, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == node.id for t in sub.targets)
        ]
        # Sans affectation : paramètre de la fonction, contrôlé chez ses appelants.
        return [p for valeur in valeurs for p in _head_problems(valeur, *suite)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        resolu = _call_head_problems(node, functions, suite)
        if resolu is not None:
            return resolu
    if isinstance(node, ast.Attribute) and node.attr == "probe_argv":
        # Argv de la sonde : validé en chemin absolu à la lecture du descripteur.
        return _probe_validation_problems()
    return [f"tête d'argv non résolue ({ast.unparse(node)})"]


def _call_head_problems(
    node: ast.Call,
    functions: dict[str, ast.FunctionDef],
    suite: tuple[ast.AST, dict[str, str], dict[str, ast.FunctionDef], int],
) -> list[str] | None:
    """Résout un argv produit par un appel (fonction du module ou ``list(...)``)."""
    assert isinstance(node.func, ast.Name)
    _, constants, _, depth = suite
    if node.func.id in functions:  # ex. _notify_command : lire ses `return`
        cible = functions[node.func.id]
        retours = [
            sub.value
            for sub in ast.walk(cible)
            if isinstance(sub, ast.Return) and sub.value is not None
        ]
        return [
            p
            for retour in retours
            for p in _head_problems(retour, cible, constants, functions, depth)
        ]
    if node.func.id == "list" and node.args:
        return _head_problems(node.args[0], *suite)
    return None


def _element_problems(head: ast.expr | None, constants: dict[str, str]) -> list[str]:
    """Vérifie qu'un premier élément d'argv est un chemin absolu."""
    if head is None:
        return ["argv vide"]
    if isinstance(head, ast.Constant) and isinstance(head.value, str):
        texte: str | None = head.value
    elif isinstance(head, ast.Name):
        texte = constants.get(head.id)
    else:
        return [f"tête d'argv dynamique ({ast.unparse(head)})"]
    if texte is None or not texte.startswith("/"):
        return [f"binaire non absolu ({ast.unparse(head)} = {texte!r})"]
    return []


def _probe_validation_problems() -> list[str]:
    """La validation du descripteur doit refuser un ``argv[0]`` hors catalogue.

    Appelle réellement ``fingerprint_argv_ok`` (et non plus une recherche de
    texte dans son code) : un binaire relatif doit être refusé, la commande
    ``/usr/bin/flatpak list`` du catalogue fermé acceptée.
    """
    problemes = [
        f"argv[0] relatif accepté : {relatif!r}"
        for relatif in ("flatpak", "./flatpak", "usr/bin/flatpak")
        if runtime_module.fingerprint_argv_ok([relatif, "list"])
    ]
    if not runtime_module.fingerprint_argv_ok(["/usr/bin/flatpak", "list"]):
        problemes.append("commande du catalogue refusée")
    return problemes


def test_runtime_binaires_en_chemins_absolus(tree: ast.Module) -> None:
    """Tout argv lancé a pour tête un chemin absolu (jamais de résolution $PATH)."""
    constants = _module_constants(tree)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    owners = _enclosing_functions(tree)

    # Les constantes de binaires connues sont absolues.
    for nom in ("LOGINCTL", "RUNUSER", "ENV_BIN", "BUSCTL", "SYSTEMCTL", "DNF5"):
        assert constants.get(nom, "").startswith("/"), nom

    appels = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in _ARGV_SINKS
        and len(n.args) >= 2
    ]
    assert len(appels) >= 5, "les points de lancement ne sont plus détectés"

    problemes: list[str] = []
    for appel in appels:
        scope = owners.get(appel, tree)
        problemes += [
            f"ligne {appel.lineno}: {p}"
            for p in _head_problems(appel.args[1], scope, constants, functions)
        ]
    assert problemes == []


def test_runtime_subprocess_confine_au_runner(tree: ast.Module) -> None:
    """``subprocess`` n'est utilisé que dans ``default_runner``, jamais en shell."""
    owners = _enclosing_functions(tree)
    hors_runner: list[str] = []
    shell: list[str] = []
    for node in ast.walk(tree):
        proprietaire = owners.get(node)
        dans_runner = proprietaire is not None and (
            proprietaire.name == _RUNNER_FUNCTION
        )
        # Usage de subprocess.<x>, hors exception captée (subprocess.SubprocessError
        # ne lance rien) et hors import.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "subprocess"
            and node.attr not in {"SubprocessError", "TimeoutExpired"}
            and not dans_runner
        ):
            hors_runner.append(f"subprocess.{node.attr} (ligne {node.lineno})")
        # Autres moyens de lancer un programme.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr.startswith(
                ("system", "popen", "spawn", "exec", "posix_spawn")
            )
        ):
            hors_runner.append(f"os.{node.attr} (ligne {node.lineno})")
        if isinstance(node, ast.keyword) and node.arg == "shell":
            shell.append(f"shell= (ligne {node.value.lineno})")
    # `from subprocess import …` contournerait la détection par attribut.
    imports_from = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "subprocess"
    ]
    assert hors_runner == []
    assert shell == []
    assert imports_from == []
    assert _RUNNER_FUNCTION in {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
