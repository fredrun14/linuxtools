"""Tests de `linuxtools._lazy.make_lazy_getattr`."""

import sys
import types
from collections.abc import Iterator

import pytest

from linuxtools._lazy import make_lazy_getattr

_NOM_HOTE = "faux_paquet_hote_lazy"


@pytest.fixture
def paquet_hote() -> Iterator[types.ModuleType]:
    """Module hôte factice enregistré dans `sys.modules`."""
    module = types.ModuleType(_NOM_HOTE)
    sys.modules[_NOM_HOTE] = module
    yield module
    del sys.modules[_NOM_HOTE]


def test_make_lazy_getattr_nom_declare_resolu_et_mis_en_cache(
    paquet_hote: types.ModuleType,
) -> None:
    """Un nom déclaré est résolu depuis sa cible puis mis en cache."""
    # Arrange
    paquet_hote.__getattr__ = make_lazy_getattr(  # type: ignore[method-assign]
        _NOM_HOTE, {"dumps": "json"}
    )

    # Act
    valeur = paquet_hote.dumps

    # Assert
    assert valeur([1]) == "[1]"
    assert paquet_hote.__dict__["dumps"] is valeur


def test_make_lazy_getattr_nom_inconnu_leve_attribute_error() -> None:
    """Un nom non déclaré lève `AttributeError` citant le paquet."""
    # Arrange
    getattr_paresseux = make_lazy_getattr("mon_paquet", {"a": "json"})

    # Act / Assert
    with pytest.raises(AttributeError, match="mon_paquet.*inconnu"):
        getattr_paresseux("inconnu")
