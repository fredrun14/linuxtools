"""Tests unitaires pour le module dotconf."""

import configparser
import os
import tempfile
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.dotconf import (
    LinuxIniConfigManager,
    ValidatedSection,
    build_validators,
    parse_validator,
)
from linuxtools.dotconf.base import IniConfig
from linuxtools.logging import FileLogger


# Fixtures


@pytest.fixture
def temp_log_file():
    """Crée un fichier de log temporaire."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def temp_ini_file():
    """Crée un fichier INI temporaire."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def logger(temp_log_file):
    """Crée un logger pour les tests."""
    return FileLogger(temp_log_file)


@pytest.fixture
def manager(logger):
    """Crée un gestionnaire INI pour les tests."""
    return LinuxIniConfigManager(logger)


# Section de test


@dataclass(frozen=True)
class CommandsSectionFixture(ValidatedSection):
    """Section de test pour les commandes."""

    upgrade_type: str = "default"
    download_updates: str = "yes"
    apply_updates: str = "yes"
    random_sleep: str = "300"

    @staticmethod
    def section_name() -> str:
        return "commands"


@dataclass(frozen=True)
class MainSectionFixture(ValidatedSection):
    """Section de test pour main."""

    fastestmirror: str = "true"
    max_parallel_downloads: str = "10"

    @staticmethod
    def section_name() -> str:
        return "main"


# Tests parse_validator


class TestParseValidator:
    """Tests pour la fonction parse_validator."""

    def test_parse_list_validator(self):
        """Teste le parsing d'une liste de valeurs."""
        result = parse_validator(["yes", "no"])
        assert result == ["yes", "no"]

    def test_parse_non_list_raises(self):
        """Teste qu'un string lève une exception."""
        with pytest.raises(ValueError, match="Format de validateur invalide"):
            parse_validator("lambda x: x.isdigit()")

    def test_parse_invalid_validator_raises(self):
        """Teste qu'un validateur invalide lève une exception."""
        with pytest.raises(ValueError, match="Format de validateur invalide"):
            parse_validator("invalid string")


class TestBuildValidators:
    """Tests pour la fonction build_validators."""

    def test_build_list_validators(self):
        """Teste la construction d'un dictionnaire de listes."""
        validators_dict = {
            "field1": ["opt1", "opt2"],
            "field2": ["a", "b", "c"],
        }
        result = build_validators(validators_dict)

        assert result["field1"] == ["opt1", "opt2"]
        assert result["field2"] == ["a", "b", "c"]


# Tests ValidatedSection


class TestValidatedSection:
    """Tests pour ValidatedSection."""

    def setup_method(self):
        """Configure les validators avant chaque test."""
        CommandsSectionFixture.set_validators({
            "upgrade_type": ["default", "security"],
            "download_updates": ["yes", "no"],
            "apply_updates": ["yes", "no"],
            "random_sleep": lambda x: x.isdigit() and 0 <= int(x) <= 86400,
        })

    def teardown_method(self):
        """Nettoie les validators après chaque test."""
        CommandsSectionFixture.clear_validators()

    def test_create_valid_section(self):
        """Teste la création d'une section valide."""
        section = CommandsSectionFixture(
            upgrade_type="default",
            download_updates="yes",
            apply_updates="no",
            random_sleep="600",
        )
        assert section.upgrade_type == "default"
        assert section.download_updates == "yes"
        assert section.apply_updates == "no"
        assert section.random_sleep == "600"

    def test_create_with_defaults(self):
        """Teste la création avec les valeurs par défaut."""
        section = CommandsSectionFixture()
        assert section.upgrade_type == "default"
        assert section.download_updates == "yes"

    def test_invalid_list_value_raises(self):
        """Teste qu'une valeur invalide dans une liste lève une exception."""
        with pytest.raises(ValueError, match="upgrade_type='invalid' invalide"):
            CommandsSectionFixture(upgrade_type="invalid")

    def test_invalid_lambda_value_raises(self):
        """Teste qu'une valeur invalide pour un lambda lève une exception."""
        with pytest.raises(ValueError, match="random_sleep='abc' échoue"):
            CommandsSectionFixture(random_sleep="abc")

    def test_lambda_out_of_range_raises(self):
        """Teste qu'une valeur hors limites lève une exception."""
        with pytest.raises(ValueError, match="random_sleep='100000' échoue"):
            CommandsSectionFixture(random_sleep="100000")

    def test_section_name(self):
        """Teste que section_name retourne le bon nom."""
        section = CommandsSectionFixture()
        assert section.section_name() == "commands"

    def test_to_dict(self):
        """Teste la conversion en dictionnaire."""
        section = CommandsSectionFixture(
            upgrade_type="security",
            download_updates="no",
        )
        result = section.to_dict()
        assert result["upgrade_type"] == "security"
        assert result["download_updates"] == "no"
        assert "apply_updates" in result
        assert "random_sleep" in result

    def test_from_dict(self):
        """Teste la création depuis un dictionnaire."""
        data = {
            "upgrade_type": "security",
            "download_updates": "no",
            "apply_updates": "yes",
            "random_sleep": "100",
        }
        section = CommandsSectionFixture.from_dict(data)
        assert section.upgrade_type == "security"
        assert section.download_updates == "no"

    def test_immutability(self):
        """Teste que la section est immuable (frozen)."""
        section = CommandsSectionFixture()
        with pytest.raises(AttributeError):
            section.upgrade_type = "security"

    def test_without_validators(self):
        """Teste la création sans validators (pas de validation)."""
        CommandsSectionFixture.clear_validators()
        section = CommandsSectionFixture(upgrade_type="anything")
        assert section.upgrade_type == "anything"


# Tests LinuxIniConfigManager


class TestLinuxIniConfigManager:
    """Tests pour LinuxIniConfigManager."""

    def setup_method(self):
        """Configure les validators."""
        CommandsSectionFixture.set_validators({
            "upgrade_type": ["default", "security"],
            "download_updates": ["yes", "no"],
            "apply_updates": ["yes", "no"],
            "random_sleep": lambda x: x.isdigit() and 0 <= int(x) <= 86400,
        })
        MainSectionFixture.set_validators({
            "fastestmirror": ["true", "false"],
            "max_parallel_downloads": lambda x: x.isdigit() and 1 <= int(x) <= 20,
        })

    def teardown_method(self):
        """Nettoie les validators."""
        CommandsSectionFixture.clear_validators()
        MainSectionFixture.clear_validators()

    def test_write_and_read_section(self, manager, temp_ini_file):
        """Teste l'écriture et la lecture d'une section."""
        path = Path(temp_ini_file)
        section = CommandsSectionFixture(upgrade_type="security")

        manager.write_section(path, section)
        result = manager.read(path)

        assert "commands" in result
        assert result["commands"]["upgrade_type"] == "security"

    def test_read_nonexistent_file_raises(self, manager):
        """Teste que la lecture d'un fichier inexistant lève une exception."""
        with pytest.raises(FileNotFoundError):
            manager.read(Path("/nonexistent/file.conf"))

    def test_update_section_with_changes(self, manager, temp_ini_file):
        """Teste la mise à jour d'une section avec modifications."""
        path = Path(temp_ini_file)
        section1 = CommandsSectionFixture(upgrade_type="default")
        manager.write_section(path, section1)

        section2 = CommandsSectionFixture(upgrade_type="security")
        updated = manager.update_section(path, section2)

        assert updated is True
        result = manager.read(path)
        assert result["commands"]["upgrade_type"] == "security"

    def test_update_section_no_changes(self, manager, temp_ini_file):
        """Teste la mise à jour sans modifications."""
        path = Path(temp_ini_file)
        section = CommandsSectionFixture()
        manager.write_section(path, section)

        updated = manager.update_section(path, section)
        assert updated is False

    def test_section_to_ini(self, manager):
        """Teste la génération du contenu INI d'une section."""
        section = CommandsSectionFixture(upgrade_type="security")
        ini_content = manager.section_to_ini(section)

        assert "[commands]" in ini_content
        assert "upgrade_type = security" in ini_content

    def test_multiple_sections(self, manager, temp_ini_file):
        """Teste l'écriture de plusieurs sections."""
        path = Path(temp_ini_file)

        section1 = CommandsSectionFixture(upgrade_type="security")
        section2 = MainSectionFixture(fastestmirror="true")

        manager.write_section(path, section1)
        manager.write_section(path, section2)

        result = manager.read(path)
        assert "commands" in result
        assert "main" in result
        assert result["commands"]["upgrade_type"] == "security"
        assert result["main"]["fastestmirror"] == "true"

    def test_write_config(self, manager, temp_ini_file):
        """Teste write() avec un IniConfig complet."""
        path = Path(temp_ini_file)

        class SimpleConfig(IniConfig):
            def sections(self):
                return [CommandsSectionFixture(upgrade_type="security")]

            def to_ini(self) -> str:
                return manager.config_to_ini(self)

            @classmethod
            def from_file(cls, path):
                raise NotImplementedError

        config = SimpleConfig()
        manager.write(path, config)
        result = manager.read(path)
        assert "commands" in result
        assert result["commands"]["upgrade_type"] == "security"

    def test_config_to_ini(self, manager):
        """Teste config_to_ini() avec plusieurs sections."""
        class SimpleConfig(IniConfig):
            def sections(self):
                return [
                    CommandsSectionFixture(upgrade_type="security"),
                    MainSectionFixture(fastestmirror="true"),
                ]

            def to_ini(self) -> str:
                return manager.config_to_ini(self)

            @classmethod
            def from_file(cls, path):
                raise NotImplementedError

        config = SimpleConfig()
        ini = manager.config_to_ini(config)
        assert "[commands]" in ini
        assert "[main]" in ini
        assert "upgrade_type = security" in ini

    def test_update_section_fichier_inexistant(self, manager, tmp_path):
        """update_section() sur un fichier inexistant cree la section."""
        path = tmp_path / "new_config.conf"
        section = CommandsSectionFixture(upgrade_type="security")
        updated = manager.update_section(path, section)
        assert updated is True
        result = manager.read(path)
        assert result["commands"]["upgrade_type"] == "security"


class TestUpdateSectionLogSansValeur:
    """Tests pour la confidentialité des logs dans update_section()."""

    def test_update_section_logue_cle_sans_valeur(
        self, manager, temp_ini_file
    ):
        """update_section() logue le nom de la clé mais pas sa valeur."""
        mock_logger = MagicMock()
        mgr = LinuxIniConfigManager(mock_logger)
        section = CommandsSectionFixture(upgrade_type="security")

        mgr.update_section(Path(temp_ini_file), section)

        log_calls = [
            call[0][0] for call in mock_logger.log_info.call_args_list
        ]
        assert any("upgrade_type" in msg for msg in log_calls)
        assert not any("security" in msg for msg in log_calls)

    def test_update_section_ne_logue_pas_valeur_sensible(
        self, temp_ini_file
    ):
        """update_section() ne logue pas la valeur d'une clé sensible."""
        mock_logger = MagicMock()
        mgr = LinuxIniConfigManager(mock_logger)

        @dataclass(frozen=True)
        class CredSection(ValidatedSection):
            password: str = "MonMotDePasseSecret123"

            @staticmethod
            def section_name() -> str:
                return "database"

        section = CredSection()
        mgr.update_section(Path(temp_ini_file), section)

        log_calls = [
            call[0][0] for call in mock_logger.log_info.call_args_list
        ]
        assert not any(
            "MonMotDePasseSecret123" in msg for msg in log_calls
        )


class TestLinuxIniConfigManagerChmod:
    """Tests permissions fichier après écriture."""

    def test_write_section_cree_fichier_en_0644(self, tmp_path):
        """write_section() positionne les permissions à 0o644."""
        mgr = LinuxIniConfigManager(MagicMock())
        path = tmp_path / "out.conf"
        mgr.write_section(
            path, CommandsSectionFixture(upgrade_type="default")
        )
        assert oct(os.stat(path).st_mode & 0o777) == oct(0o644)

    def test_update_section_cree_fichier_en_0644(self, tmp_path):
        """update_section() positionne les permissions à 0o644."""
        mgr = LinuxIniConfigManager(MagicMock())
        path = tmp_path / "out.conf"
        mgr.update_section(
            path, CommandsSectionFixture(upgrade_type="default")
        )
        assert oct(os.stat(path).st_mode & 0o777) == oct(0o644)


class TestValidatedSectionEdgeCases:
    """Tests pour les cas limites de ValidatedSection."""

    def test_section_name_not_implemented(self):
        """section_name() leve NotImplementedError si non redefini."""
        with pytest.raises(NotImplementedError):
            ValidatedSection.section_name()

    def test_private_field_skipped_in_validation(self):
        """Les champs prives (commencant par _) sont ignores."""
        @dataclass(frozen=True)
        class SectionWithPrivate(ValidatedSection):
            public: str = "val"
            _private: str = dataclass_field(default="priv", init=False)

            @staticmethod
            def section_name() -> str:
                return "test"

        SectionWithPrivate.set_validators({
            "public": ["val", "other"],
        })
        try:
            section = SectionWithPrivate()
            assert section.public == "val"
        finally:
            SectionWithPrivate.clear_validators()


class TestIsSectionConfigured:
    """Tests pour LinuxIniConfigManager.is_section_configured()."""

    def test_retourne_false_si_fichier_absent(
        self, manager: LinuxIniConfigManager, tmp_path: Path
    ) -> None:
        """Retourne False si le fichier n'existe pas."""
        section = CommandsSectionFixture()

        result = manager.is_section_configured(tmp_path / "absent.conf", section)

        assert result is False

    def test_retourne_false_si_section_absente(
        self, manager: LinuxIniConfigManager, tmp_path: Path
    ) -> None:
        """Retourne False si la section est absente du fichier."""
        conf = tmp_path / "test.conf"
        parser = configparser.ConfigParser()
        parser["autre_section"] = {"key": "value"}
        with open(conf, "w") as f:
            parser.write(f)

        result = manager.is_section_configured(conf, CommandsSectionFixture())

        assert result is False

    def test_retourne_true_si_valeurs_identiques(
        self, manager: LinuxIniConfigManager, tmp_path: Path
    ) -> None:
        """Retourne True si toutes les valeurs attendues sont présentes."""
        section = CommandsSectionFixture()
        conf = tmp_path / "test.conf"
        parser = configparser.ConfigParser()
        parser[section.section_name()] = section.to_dict()
        with open(conf, "w") as f:
            parser.write(f)

        result = manager.is_section_configured(conf, section)

        assert result is True

    def test_retourne_false_si_valeur_differente(
        self, manager: LinuxIniConfigManager, tmp_path: Path
    ) -> None:
        """Retourne False si au moins une valeur diffère."""
        section = CommandsSectionFixture()
        conf = tmp_path / "test.conf"
        values = section.to_dict()
        values["apply_updates"] = "no"
        parser = configparser.ConfigParser()
        parser[section.section_name()] = values
        with open(conf, "w") as f:
            parser.write(f)

        result = manager.is_section_configured(conf, section)

        assert result is False
