"""Tests pour la validation Pydantic optionnelle de FileConfigLoader."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, TypeVar, overload
from unittest.mock import patch

from pydantic import BaseModel, field_validator

from linuxtools.config import ConfigLoader, FileConfigLoader

# TypeVar local au module, pour les @overload de _StubLoader.load()
# (miroir de _TSchema dans linuxtools.config.loader).
_TSchema = TypeVar("_TSchema")


class SampleConfig(BaseModel):
    """Modele Pydantic de test."""
    name: str
    count: int

    model_config = {"extra": "forbid"}


class NestedConfig(BaseModel):
    """Modele avec validation personnalisee."""
    path: str

    @field_validator("path")
    @classmethod
    def must_be_absolute(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("Le chemin doit etre absolu")
        return v


class SectionedConfig(BaseModel):
    """Modele avec sous-sections."""
    paths: NestedConfig
    app: SampleConfig


class TestFileConfigLoaderWithSchema(unittest.TestCase):
    """Tests FileConfigLoader.load() avec schema Pydantic."""

    def setUp(self) -> None:
        self.loader = FileConfigLoader()

    def _write_json(self, data: dict[str, object]) -> str:
        """Ecrit un fichier JSON temporaire et retourne le chemin."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_without_schema_returns_dict(self) -> None:
        """Sans schema, load() retourne un dict brut."""
        path = self._write_json({"name": "test", "count": 42})
        result = self.loader.load(path)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "test")

    def test_load_with_valid_schema(self) -> None:
        """Avec schema valide, retourne une instance du modele."""
        path = self._write_json({"name": "test", "count": 42})
        result = self.loader.load(path, schema=SampleConfig)
        assert isinstance(result, SampleConfig)
        self.assertEqual(result.name, "test")
        self.assertEqual(result.count, 42)

    def test_load_with_invalid_data_raises(self) -> None:
        """Donnees invalides levent pydantic.ValidationError."""
        from pydantic import ValidationError
        path = self._write_json({"name": "test", "count": "pas_un_int"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_extra_fields_raises(self) -> None:
        """Champs inconnus avec extra=forbid levent une erreur."""
        from pydantic import ValidationError
        path = self._write_json(
            {"name": "test", "count": 1, "extra": "interdit"}
        )
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_missing_fields_raises(self) -> None:
        """Champs requis manquants levent une erreur."""
        from pydantic import ValidationError
        path = self._write_json({"name": "test"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_nested_model(self) -> None:
        """Modele imbrique fonctionne correctement."""
        data = {
            "paths": {"path": "/usr/bin"},
            "app": {"name": "test", "count": 1}
        }
        path = self._write_json(data)
        result = self.loader.load(path, schema=SectionedConfig)
        assert isinstance(result, SectionedConfig)
        self.assertEqual(result.paths.path, "/usr/bin")

    def test_load_with_field_validator(self) -> None:
        """Les field_validators Pydantic sont executes."""
        from pydantic import ValidationError
        path = self._write_json({"path": "relatif/pas/absolu"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=NestedConfig)

    def test_load_non_basemodel_raises_type_error(self) -> None:
        """Passer un type non-BaseModel leve TypeError."""
        path = self._write_json({"key": "value"})
        with self.assertRaises(TypeError):
            self.loader.load(path, schema=dict)

    def test_load_with_string_schema_raises_type_error(self) -> None:
        """Passer une string comme schema leve TypeError."""
        path = self._write_json({"key": "value"})
        with self.assertRaises(TypeError):
            # Passage volontaire d'un type incorrect (str au lieu de
            # type | None) : ce test vérifie la garde runtime destinée
            # aux appelants non typés, documentée dans
            # ConfigLoader.validate. Code d'erreur
            # mypy [call-overload] (et non [arg-type]) depuis l'ajout
            # des @overload sur load() : aucun overload ne matche un
            # schema de type str, ce qui est précisément le cas testé.
            self.loader.load(
                path,
                schema="SampleConfig",  # type: ignore[call-overload]
            )


class TestFileConfigLoaderWithoutPydantic(unittest.TestCase):
    """Tests quand pydantic n'est pas installe."""

    def setUp(self) -> None:
        self.loader = FileConfigLoader()

    def _write_json(self, data: dict[str, object]) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_without_schema_works_without_pydantic(self) -> None:
        """Sans schema, load() fonctionne meme sans pydantic."""
        path = self._write_json({"key": "value"})
        result = self.loader.load(path)
        self.assertEqual(result, {"key": "value"})

    @patch.dict("sys.modules", {"pydantic": None})
    def test_load_with_schema_raises_import_error(self) -> None:
        """Schema fourni sans pydantic leve ImportError."""
        path = self._write_json({"name": "test", "count": 1})
        with self.assertRaises(ImportError) as ctx:
            self.loader.load(path, schema=SampleConfig)
        self.assertIn("pydantic", str(ctx.exception))


class TestConfigurationManagerValidate(unittest.TestCase):
    """Tests pour ConfigurationManager.validate()."""

    def test_validate_retourne_instance_modele(self) -> None:
        """validate() retourne une instance du modèle Pydantic."""
        from linuxtools.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test", "count": 42}
        )
        result = cfg.validate(SampleConfig)
        self.assertIsInstance(result, SampleConfig)
        self.assertEqual(result.name, "test")
        self.assertEqual(result.count, 42)

    def test_validate_config_invalide_leve_validation_error(self) -> None:
        """Config invalide lève pydantic.ValidationError."""
        from pydantic import ValidationError
        from linuxtools.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test", "count": "pas_un_int"}
        )
        with self.assertRaises(ValidationError):
            cfg.validate(SampleConfig)

    def test_validate_schema_non_basemodel_leve_type_error(self) -> None:
        """Schema non-BaseModel lève TypeError."""
        from linuxtools.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test"}
        )
        with self.assertRaises(TypeError):
            cfg.validate(dict)


class _StubLoader(ConfigLoader):
    """Loader minimal qui trace l'appel à validate() pour vérifier
    que ConfigurationManager.validate() délègue bien au loader
    injecté plutôt qu'à un détail interne de FileConfigLoader."""

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: None = None,
    ) -> dict[str, Any]: ...

    @overload
    def load(
        self,
        config_path: str | Path,
        schema: type[_TSchema],
    ) -> _TSchema: ...

    def load(
        self, config_path: str | Path, schema: type | None = None
    ) -> dict[str, Any] | Any:  # noqa: ANN401
        return {}

    @staticmethod
    def validate(data: dict[str, Any], schema: object) -> Any:  # noqa: ANN401
        return "sentinelle-stub-loader"


class TestConfigurationManagerValidateDelegation(unittest.TestCase):
    """Verrouille la délégation de ConfigurationManager.validate() vers
    le loader injecté (self._loader.validate), pas vers une
    implémentation statique figée sur FileConfigLoader."""

    def test_validate_delegue_au_loader_injecte(self) -> None:
        """validate() retourne le résultat du loader injecté."""
        from linuxtools.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"a": 1}, config_loader=_StubLoader()
        )

        result = cfg.validate(SampleConfig)

        self.assertEqual(result, "sentinelle-stub-loader")


if __name__ == "__main__":
    unittest.main()
