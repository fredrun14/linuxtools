"""Tests de comportement complémentaires pour le module dotconf."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.dotconf import ConfTomlExporter, LinuxIniConfigManager
from linuxtools.dotconf.applier import ConfigApplier
from linuxtools.dotconf.base import IniConfig, IniSection
from linuxtools.dotconf.line_editor import SectionAwareEditor
from linuxtools.dotconf.spec import ConfigBlock, ConfigSpec
from linuxtools.logging.base import Logger


class _Section(IniSection):
    """Section INI de test portant un dictionnaire fixe."""

    def __init__(self, valeurs: dict[str, str]) -> None:
        """Mémorise les valeurs de la section."""
        self._valeurs = valeurs

    @staticmethod
    def section_name() -> str:
        """Retourne le nom de la section."""
        return "main"

    def to_dict(self) -> dict[str, str]:
        """Retourne les valeurs de la section."""
        return dict(self._valeurs)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "_Section":
        """Reconstruit la section depuis un dictionnaire."""
        return cls(data)


class _Config(IniConfig):
    """Configuration INI de test à section unique."""

    def __init__(self, section: IniSection) -> None:
        """Mémorise la section."""
        self._section = section

    def sections(self) -> list[IniSection]:
        """Retourne la section unique."""
        return [self._section]

    def to_ini(self) -> str:
        """Sérialise la configuration (non utilisé par ces tests)."""
        return ""

    @classmethod
    def from_file(cls, path: Path) -> "_Config":
        """Charge la configuration depuis un fichier."""
        valeurs = LinuxIniConfigManager().read(path)["main"]
        return cls(_Section(valeurs))


# --- LinuxIniConfigManager sans logger ---


def test_lecture_ini_sans_logger_renvoie_les_sections(tmp_path: Path) -> None:
    """Sans logger, la lecture d'un INI renvoie son contenu."""
    fichier = tmp_path / "a.ini"
    fichier.write_text("[main]\nk = v\n", encoding="utf-8")

    assert LinuxIniConfigManager().read(fichier) == {"main": {"k": "v"}}


def test_ecriture_ini_sans_logger_produit_le_fichier(tmp_path: Path) -> None:
    """Sans logger, l'écriture d'une configuration crée le fichier."""
    fichier = tmp_path / "a.ini"

    LinuxIniConfigManager().write(fichier, _Config(_Section({"k": "v"})))

    assert LinuxIniConfigManager().read(fichier) == {"main": {"k": "v"}}


def test_ecriture_de_section_sans_logger_produit_le_fichier(tmp_path: Path) -> None:
    """Sans logger, l'écriture d'une section l'ajoute au fichier."""
    fichier = tmp_path / "a.ini"

    LinuxIniConfigManager().write_section(fichier, _Section({"k": "v"}))

    assert LinuxIniConfigManager().read(fichier) == {"main": {"k": "v"}}


def test_mise_a_jour_de_section_sans_logger_applique_les_changements(
    tmp_path: Path,
) -> None:
    """Sans logger, une valeur différente est écrite et la mise à jour signalée."""
    fichier = tmp_path / "a.ini"
    fichier.write_text("[main]\nk = ancien\n", encoding="utf-8")

    modifie = LinuxIniConfigManager().update_section(fichier, _Section({"k": "neuf"}))

    assert modifie is True
    assert LinuxIniConfigManager().read(fichier) == {"main": {"k": "neuf"}}


def test_mise_a_jour_de_section_sans_logger_ni_changement_ne_modifie_rien(
    tmp_path: Path,
) -> None:
    """Sans logger, des valeurs déjà conformes ne donnent aucune modification."""
    fichier = tmp_path / "a.ini"
    fichier.write_text("[main]\nk = v\n", encoding="utf-8")
    avant = fichier.read_bytes()

    modifie = LinuxIniConfigManager().update_section(fichier, _Section({"k": "v"}))

    assert modifie is False
    assert fichier.read_bytes() == avant


# --- ConfigApplier ---


def test_application_sur_fichier_existant_journalise_l_action(
    tmp_path: Path,
) -> None:
    """Avec logger, l'action appliquée à un fichier existant est tracée."""
    cible = tmp_path / "a.conf"
    cible.write_text("--existant\n", encoding="utf-8")
    logger = MagicMock(spec=Logger)
    spec = ConfigSpec(file_path=cible, blocks=[ConfigBlock(content="--nouveau")])

    actions = ConfigApplier(logger).apply(spec)

    assert actions == ["Appended: --nouveau"]
    logger.log_info.assert_called_once_with(f"Appended: --nouveau in {cible}")


# --- ConfTomlExporter ---


def test_export_d_une_table_vide_ne_produit_que_son_en_tete() -> None:
    """Un sous-dictionnaire vide donne un en-tête de section sans contenu."""
    assert ConfTomlExporter().export_mapping({"vide": {}}) == "\n[vide]"


def test_export_d_une_valeur_inconnue_la_serialise_en_chaine() -> None:
    """Une valeur hors types TOML usuels est écrite comme chaîne."""
    assert ConfTomlExporter().export_mapping({"chemin": Path("/etc/app")}) == (
        'chemin = "/etc/app"'
    )


# --- SectionAwareEditor ---


def test_remplacement_de_la_derniere_ligne_sans_fin_de_ligne(tmp_path: Path) -> None:
    """Remplacer une clé en dernière ligne sans saut final n'en ajoute pas."""
    fichier = tmp_path / "a.conf"
    fichier.write_text("autre = 0\nkey = 1", encoding="utf-8")

    assert SectionAwareEditor(fichier).ensure_block("key = 2") is True

    assert fichier.read_text(encoding="utf-8") == "autre = 0\nkey = 2"


def test_decommentage_d_une_ligne_commentee_par_point_virgule(
    tmp_path: Path,
) -> None:
    """Une ligne commentée avec « ; » est réactivée."""
    fichier = tmp_path / "a.conf"
    fichier.write_text("; --option\n", encoding="utf-8")

    assert SectionAwareEditor(fichier).ensure_block("--option") is True

    assert fichier.read_text(encoding="utf-8") == "--option\n"


def test_decommentage_limite_a_la_section_demandee(tmp_path: Path) -> None:
    """Seule la ligne commentée de la section visée est réactivée."""
    fichier = tmp_path / "a.conf"
    fichier.write_text("[a]\n# k = 1\n[b]\n# k = 1\n", encoding="utf-8")

    assert SectionAwareEditor(fichier).ensure_block("k = 1", section="b") is True

    assert fichier.read_text(encoding="utf-8") == "[a]\n# k = 1\n[b]\nk = 1\n"


@pytest.mark.parametrize(
    ("avant", "apres"),
    [
        (b"  # a\r\n", b"  a\r\n"),
        (b"  ; a\r\n", b"  a\r\n"),
        (b"\t# a\n", b"\ta\n"),
        (b"# a", b"a"),
    ],
)
def test_decommentage_conserve_indentation_et_fin_de_ligne(
    tmp_path: Path, avant: bytes, apres: bytes
) -> None:
    """Réactiver une ligne garde son indentation et sa fin de ligne d'origine."""
    fichier = tmp_path / "a.conf"
    fichier.write_bytes(avant)

    assert SectionAwareEditor(fichier).ensure_block("a") is True

    assert fichier.read_bytes() == apres
