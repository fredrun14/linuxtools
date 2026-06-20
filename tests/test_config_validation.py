"""Tests pour la validation Pydantic optionnelle de FileConfigLoader."""

import json
import tempfile
import unittest
from unittest.mock import patch

from pydantic import BaseModel, field_validator

from linux_python_utils.config import FileConfigLoader


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

    def setUp(self):
        self.loader = FileConfigLoader()

    def _write_json(self, data: dict) -> str:
        """Ecrit un fichier JSON temporaire et retourne le chemin."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_without_schema_returns_dict(self):
        """Sans schema, load() retourne un dict brut."""
        path = self._write_json({"name": "test", "count": 42})
        result = self.loader.load(path)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "test")

    def test_load_with_valid_schema(self):
        """Avec schema valide, retourne une instance du modele."""
        path = self._write_json({"name": "test", "count": 42})
        result = self.loader.load(path, schema=SampleConfig)
        self.assertIsInstance(result, SampleConfig)
        self.assertEqual(result.name, "test")
        self.assertEqual(result.count, 42)

    def test_load_with_invalid_data_raises(self):
        """Donnees invalides levent pydantic.ValidationError."""
        from pydantic import ValidationError
        path = self._write_json({"name": "test", "count": "pas_un_int"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_extra_fields_raises(self):
        """Champs inconnus avec extra=forbid levent une erreur."""
        from pydantic import ValidationError
        path = self._write_json(
            {"name": "test", "count": 1, "extra": "interdit"}
        )
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_missing_fields_raises(self):
        """Champs requis manquants levent une erreur."""
        from pydantic import ValidationError
        path = self._write_json({"name": "test"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=SampleConfig)

    def test_load_with_nested_model(self):
        """Modele imbrique fonctionne correctement."""
        data = {
            "paths": {"path": "/usr/bin"},
            "app": {"name": "test", "count": 1}
        }
        path = self._write_json(data)
        result = self.loader.load(path, schema=SectionedConfig)
        self.assertIsInstance(result, SectionedConfig)
        self.assertEqual(result.paths.path, "/usr/bin")

    def test_load_with_field_validator(self):
        """Les field_validators Pydantic sont executes."""
        from pydantic import ValidationError
        path = self._write_json({"path": "relatif/pas/absolu"})
        with self.assertRaises(ValidationError):
            self.loader.load(path, schema=NestedConfig)

    def test_load_non_basemodel_raises_type_error(self):
        """Passer un type non-BaseModel leve TypeError."""
        path = self._write_json({"key": "value"})
        with self.assertRaises(TypeError):
            self.loader.load(path, schema=dict)

    def test_load_with_string_schema_raises_type_error(self):
        """Passer une string comme schema leve TypeError."""
        path = self._write_json({"key": "value"})
        with self.assertRaises(TypeError):
            self.loader.load(path, schema="SampleConfig")


class TestFileConfigLoaderWithoutPydantic(unittest.TestCase):
    """Tests quand pydantic n'est pas installe."""

    def setUp(self):
        self.loader = FileConfigLoader()

    def _write_json(self, data: dict) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_without_schema_works_without_pydantic(self):
        """Sans schema, load() fonctionne meme sans pydantic."""
        path = self._write_json({"key": "value"})
        result = self.loader.load(path)
        self.assertEqual(result, {"key": "value"})

    @patch.dict("sys.modules", {"pydantic": None})
    def test_load_with_schema_raises_import_error(self):
        """Schema fourni sans pydantic leve ImportError."""
        path = self._write_json({"name": "test", "count": 1})
        with self.assertRaises(ImportError) as ctx:
            self.loader.load(path, schema=SampleConfig)
        self.assertIn("pydantic", str(ctx.exception))


class TestConfigurationManagerValidate(unittest.TestCase):
    """Tests pour ConfigurationManager.validate()."""

    def test_validate_retourne_instance_modele(self):
        """validate() retourne une instance du modèle Pydantic."""
        from linux_python_utils.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test", "count": 42}
        )
        result = cfg.validate(SampleConfig)
        self.assertIsInstance(result, SampleConfig)
        self.assertEqual(result.name, "test")
        self.assertEqual(result.count, 42)

    def test_validate_config_invalide_leve_validation_error(self):
        """Config invalide lève pydantic.ValidationError."""
        from pydantic import ValidationError
        from linux_python_utils.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test", "count": "pas_un_int"}
        )
        with self.assertRaises(ValidationError):
            cfg.validate(SampleConfig)

    def test_validate_schema_non_basemodel_leve_type_error(self):
        """Schema non-BaseModel lève TypeError."""
        from linux_python_utils.config import ConfigurationManager
        cfg = ConfigurationManager(
            default_config={"name": "test"}
        )
        with self.assertRaises(TypeError):
            cfg.validate(dict)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
