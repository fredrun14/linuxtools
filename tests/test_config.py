"""Tests pour le module config."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linux_python_utils.config import FileConfigLoader, ConfigurationManager


class TestLoadConfig:
    """Tests pour la fonction load_config."""

    def setup_method(self):
        """Initialise le loader avant chaque test."""
        self.loader = FileConfigLoader()

    def test_load_json(self, tmp_path):
        """Test du chargement d'un fichier JSON."""
        config_file = tmp_path / "config.json"
        config_data = {"key": "value", "nested": {"a": 1}}
        config_file.write_text(json.dumps(config_data))

        result = self.loader.load(config_file)

        assert result == config_data

    def test_load_toml(self, tmp_path):
        """Test du chargement d'un fichier TOML."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('[section]\nkey = "value"\n')

        result = self.loader.load(config_file)

        assert result["section"]["key"] == "value"

    def test_file_not_found(self):
        """Test avec fichier inexistant."""
        with pytest.raises(FileNotFoundError):
            self.loader.load("/nonexistent/config.toml")

    def test_unsupported_extension(self, tmp_path):
        """Test avec extension non supportée."""
        config_file = tmp_path / "config.xml"
        config_file.write_text("<config></config>")

        with pytest.raises(ValueError, match="Extension non supportée"):
            self.loader.load(config_file)


class TestConfigurationManager:
    """Tests pour ConfigurationManager."""

    def test_get_dotted_path(self, tmp_path):
        """Test de l'accès par chemin pointé."""
        config_file = tmp_path / "config.json"
        config_data = {
            "level1": {
                "level2": {
                    "value": "found"
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigurationManager(config_file)

        assert manager.get("level1.level2.value") == "found"
        assert manager.get("nonexistent", "default") == "default"

    def test_deep_merge(self, tmp_path):
        """Test de la fusion profonde avec config par défaut."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"a": {"b": 2}}')

        default = {"a": {"b": 1, "c": 3}, "d": 4}
        manager = ConfigurationManager(config_file, default_config=default)

        assert manager.get("a.b") == 2  # Écrasé par le fichier
        assert manager.get("a.c") == 3  # Conservé du défaut
        assert manager.get("d") == 4    # Conservé du défaut

    def test_get_profile(self, tmp_path):
        """Test de la récupération de profils."""
        config_file = tmp_path / "config.json"
        config_data = {
            "profiles": {
                "test": {
                    "source": "~/source",
                    "destination": "/dest"
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigurationManager(config_file)
        profile = manager.get_profile("test")

        assert "source" in profile
        assert profile["destination"] == "/dest"

    def test_profile_not_found(self, tmp_path):
        """Test avec profil inexistant."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"profiles": {}}')

        manager = ConfigurationManager(config_file)

        with pytest.raises(ValueError, match="non trouvé"):
            manager.get_profile("nonexistent")

    def test_list_profiles(self, tmp_path):
        """Test de la liste des profils."""
        config_file = tmp_path / "config.json"
        config_data = {
            "profiles": {
                "profile1": {},
                "profile2": {}
            }
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigurationManager(config_file)

        assert set(manager.list_profiles()) == {"profile1", "profile2"}

    def test_get_section(self, tmp_path):
        """Test de la récupération d'une section complète."""
        config_file = tmp_path / "config.json"
        config_data = {
            "logging": {
                "level": "DEBUG",
                "format": "%(message)s"
            },
            "other": {"key": "value"}
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigurationManager(config_file)
        section = manager.get_section("logging")

        assert section == {"level": "DEBUG", "format": "%(message)s"}
        assert manager.get_section("nonexistent") == {}

    def test_create_default_config_json(self, tmp_path):
        """Test de la création d'un fichier de config JSON par défaut."""
        default = {"key": "value", "nested": {"a": 1}}
        manager = ConfigurationManager(default_config=default)

        output_file = tmp_path / "output.json"
        manager.create_default_config(output_file)

        assert output_file.exists()
        loader = FileConfigLoader()
        result = loader.load(output_file)
        assert result == default

    def test_create_default_config_toml(self, tmp_path):
        """Test de la création d'un fichier de config TOML par défaut."""
        default = {
            "simple": "value",
            "number": 42,
            "enabled": True,
            "section": {
                "nested_key": "nested_value"
            }
        }
        manager = ConfigurationManager(default_config=default)

        output_file = tmp_path / "output.toml"
        manager.create_default_config(output_file)

        assert output_file.exists()
        loader = FileConfigLoader()
        result = loader.load(output_file)
        assert result["simple"] == "value"
        assert result["number"] == 42
        assert result["enabled"] is True
        assert result["section"]["nested_key"] == "nested_value"

    def test_search_paths(self, tmp_path):
        """Test de la recherche dans plusieurs emplacements."""
        # Créer un fichier de config dans le deuxième chemin
        config_file = tmp_path / "found.toml"
        config_file.write_text('[test]\nfound = true\n')

        search_paths = [
            tmp_path / "nonexistent.toml",
            config_file,
            tmp_path / "another.toml"
        ]

        manager = ConfigurationManager(search_paths=search_paths)

        assert manager.get("test.found") is True


class TestConfigurationManagerLogger:
    """Tests pour le logger optionnel de ConfigurationManager."""

    def test_load_config_logue_warning_si_fichier_introuvable(
        self, tmp_path
    ):
        """ConfigurationManager logue un warning si le fichier est introuvable."""
        logger = MagicMock()
        chemin_inexistant = tmp_path / "inexistant.json"

        manager = ConfigurationManager(
            config_path=chemin_inexistant,
            logger=logger
        )

        logger.log_warning.assert_called_once()
        assert "inexistant.json" in logger.log_warning.call_args[0][0]

    def test_load_config_logue_warning_si_erreur_chargement(
        self, tmp_path
    ):
        """ConfigurationManager logue un warning si le chargement échoue."""
        from unittest.mock import patch
        logger = MagicMock()
        config_file = tmp_path / "config.json"
        config_file.write_text('{"key": "value"}')
        mock_loader = MagicMock()
        mock_loader.load.side_effect = ValueError("JSON invalide")

        manager = ConfigurationManager(
            config_path=config_file,
            config_loader=mock_loader,
            logger=logger
        )

        logger.log_warning.assert_called_once()

    def test_load_config_sans_logger_pas_d_erreur(self, tmp_path):
        """ConfigurationManager sans logger ne lève pas d'exception."""
        chemin_inexistant = tmp_path / "inexistant.json"

        manager = ConfigurationManager(config_path=chemin_inexistant)

        assert manager.config == {}

    def test_load_config_retourne_defaut_si_fichier_manquant_avec_logger(
        self, tmp_path
    ):
        """ConfigurationManager retourne default_config si fichier manquant."""
        logger = MagicMock()
        default = {"cle": "valeur_defaut"}
        chemin_inexistant = tmp_path / "inexistant.json"

        manager = ConfigurationManager(
            config_path=chemin_inexistant,
            default_config=default,
            logger=logger
        )

        assert manager.get("cle") == "valeur_defaut"


class TestTomlSerialiseur:
    """Tests de sécurité et de validité du sérialiseur TOML."""

    def test_write_toml_liste_produit_tableau_valide(self, tmp_path):
        """Liste Python → tableau TOML parseable par tomllib (round-trip)."""
        import tomllib
        default = {"tags": ["alpha", "beta", "gamma"]}
        manager = ConfigurationManager(default_config=default)
        output_file = tmp_path / "output.toml"

        manager.create_default_config(output_file)

        with open(output_file, "rb") as f:
            result = tomllib.load(f)
        assert result["tags"] == ["alpha", "beta", "gamma"]

    def test_write_toml_echappe_guillemets_et_newline(self, tmp_path):
        """Caractères spéciaux dans une chaîne : round-trip TOML correct."""
        import tomllib
        valeur = 'avec "guillemets" et\nnewline'
        default = {"description": valeur}
        manager = ConfigurationManager(default_config=default)
        output_file = tmp_path / "output.toml"

        manager.create_default_config(output_file)

        with open(output_file, "rb") as f:
            result = tomllib.load(f)
        assert result["description"] == valeur

    def test_load_config_fichier_corrompu_repli_defaut(self, tmp_path):
        """TOML invalide → log_warning + retour config par défaut."""
        logger = MagicMock()
        default = {"cle": "defaut"}
        config_file = tmp_path / "config.toml"
        config_file.write_text("clé = invalide ][", encoding="utf-8")

        manager = ConfigurationManager(
            config_path=config_file,
            default_config=default,
            logger=logger,
        )

        logger.log_warning.assert_called_once()
        assert manager.get("cle") == "defaut"
