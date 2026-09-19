"""Tests de l'import paresseux des noms dépendant de l'extra `network`.

Le blocage de `webapitools` se fait dans un sous-processus : ainsi
`sys.modules` du processus de test n'est jamais pollué.
"""

import subprocess
import sys

import pytest

# Bloque `webapitools` : `import webapitools` lève `ImportError`.
_BLOCAGE = "import sys; sys.modules['webapitools'] = None\n"


def _executer_sans_webapitools(
    code: str,
) -> subprocess.CompletedProcess[str]:
    """Exécute `code` dans un sous-processus où `webapitools` est bloqué."""
    return subprocess.run(
        [sys.executable, "-c", _BLOCAGE + code],
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_linuxtools_sans_webapitools_reussit() -> None:
    """`import linuxtools` n'exige plus l'extra `network` (webapitools)."""
    # Act
    resultat = _executer_sans_webapitools("import linuxtools")

    # Assert
    assert resultat.returncode == 0, resultat.stderr


@pytest.mark.parametrize(
    "module",
    ["linuxtools.cli", "linuxtools.config", "linuxtools.network"],
)
def test_import_sous_modules_non_reseau_sans_webapitools_reussit(
    module: str,
) -> None:
    """Les sous-modules sans lien avec le routeur s'importent sans l'extra."""
    # Act
    resultat = _executer_sans_webapitools(f"import {module}")

    # Assert
    assert resultat.returncode == 0, resultat.stderr


@pytest.mark.parametrize(
    "code",
    [
        "import linuxtools; linuxtools.AsusRouterClient",
        "import linuxtools.network as n; n.AsusRouterScanner",
    ],
)
def test_acces_nom_routeur_sans_webapitools_leve_import_error(
    code: str,
) -> None:
    """Accéder à un nom routeur sans l'extra lève `ImportError` (Q-02)."""
    # Act
    resultat = _executer_sans_webapitools(code)

    # Assert
    assert resultat.returncode != 0
    assert (
        "ModuleNotFoundError" in resultat.stderr
    )  # sous-classe d'ImportError
    assert "webapitools" in resultat.stderr


def test_acces_nom_updates_sans_webapitools_leve_import_error() -> None:
    """Accéder à `check_for_update` sans l'extra lève `ImportError`."""
    # Act
    resultat = _executer_sans_webapitools(
        "import linuxtools; linuxtools.check_for_update"
    )

    # Assert
    assert resultat.returncode != 0
    assert (
        "ModuleNotFoundError" in resultat.stderr
    )  # sous-classe d'ImportError
    assert "webapitools" in resultat.stderr


@pytest.mark.parametrize(
    "module", ["linuxtools.network.router", "linuxtools.updates"]
)
def test_import_direct_router_et_updates_sans_webapitools_leve_import_error(
    module: str,
) -> None:
    """L'import direct de ces modules échoue toujours sans l'extra (Q-02)."""
    # Act
    resultat = _executer_sans_webapitools(f"import {module}")

    # Assert
    assert resultat.returncode != 0
    assert (
        "ModuleNotFoundError" in resultat.stderr
    )  # sous-classe d'ImportError
    assert "webapitools" in resultat.stderr


def test_attribut_inconnu_leve_attribute_error() -> None:
    """Un attribut inexistant lève `AttributeError` ; `hasattr` -> False."""
    # Arrange
    import linuxtools

    # Act / Assert
    with pytest.raises(AttributeError, match="n_existe_pas"):
        linuxtools.n_existe_pas  # noqa: B018
    assert not hasattr(linuxtools, "n_existe_pas")


def test_tous_les_noms_de_all_resolvent_avec_l_extra() -> None:
    """Avec l'extra, tout nom de `__all__` se résout."""
    # Arrange
    pytest.importorskip("webapitools")
    import linuxtools

    # Act / Assert
    for nom in linuxtools.__all__:
        assert getattr(linuxtools, nom) is not None, nom


def test_asusrouterclient_reexporte_est_celui_de_webapitools() -> None:
    """`linuxtools.AsusRouterClient` est la classe de `webapitools`."""
    # Arrange
    webapitools = pytest.importorskip("webapitools")
    import linuxtools

    # Act / Assert
    assert linuxtools.AsusRouterClient is webapitools.AsusRouterClient  # type: ignore[attr-defined]
