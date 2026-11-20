"""Verrouille le contrat de typage de FileConfigLoader.load().

Ce test ne vérifie rien à l'exécution via `typing.assert_type` : cette
fonction est un no-op runtime, elle sert uniquement de marqueur que
mypy --strict évalue statiquement (voir `make lint`). Une régression
qui repasserait le retour de `load()` à `Any` (perte des `@overload`
de `src/linuxtools/config/loader.py`) romprait ce fichier en CI mypy,
sans forcément faire échouer les tests d'exécution existants.

Chaque test contient donc aussi une assertion runtime (`isinstance`)
pour ne pas être vide de sens si on l'exécutait sans mypy.
"""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, assert_type

from linuxtools.config import FileConfigLoader
from tests.unit.test_config_validation import SampleConfig


def _write_json(data: dict[str, object], dossier: Path) -> Path:
    """Écrit un fichier JSON dans ``dossier`` et retourne son chemin.

    Args:
        data: Contenu à sérialiser en JSON.
        dossier: Dossier de destination (nettoyé par l'appelant).

    Returns:
        Chemin du fichier créé.
    """
    fichier = dossier / "config.json"
    fichier.write_text(json.dumps(data), encoding="utf-8")
    return fichier


class TestFileConfigLoaderTyping(unittest.TestCase):
    """Verrouille le type de retour de FileConfigLoader.load()."""

    def setUp(self) -> None:
        """Crée un dossier temporaire supprimé en fin de test."""
        racine = tempfile.TemporaryDirectory()
        self.addCleanup(racine.cleanup)
        self._dossier = Path(racine.name)

    def test_load_without_schema_returns_dict_type(self) -> None:
        """Sans schema, mypy doit voir un retour dict[str, Any]."""
        path = _write_json({"name": "test", "count": 42}, self._dossier)
        loader = FileConfigLoader()

        result = loader.load(path)

        assert_type(result, dict[str, Any])
        assert isinstance(result, dict)

    def test_load_with_schema_returns_schema_type(self) -> None:
        """Avec schema, mypy doit voir un retour du type du schema."""
        path = _write_json({"name": "test", "count": 42}, self._dossier)
        loader = FileConfigLoader()

        result = loader.load(path, SampleConfig)

        assert_type(result, SampleConfig)
        assert isinstance(result, SampleConfig)


if __name__ == "__main__":
    unittest.main()
