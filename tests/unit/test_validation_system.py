"""Tests unitaires pour SystemCommandValidator."""

# stdlib
from unittest.mock import patch

# third-party
import pytest

# local
from linuxtools.errors.exceptions import MissingDependencyError
from linuxtools.validation.system import SystemCommandValidator


class TestSystemCommandValidator:
    def test_validate_passe_si_toutes_presentes(self) -> None:
        """validate() silencieux si toutes les commandes existent."""
        with patch(
            "linuxtools.validation.system.shutil.which",
            return_value="/usr/bin/cmd",
        ):
            validator = SystemCommandValidator(
                {"cmd": "sudo dnf install cmd"}
            )
            validator.validate()

    def test_validate_leve_si_commande_absente(self) -> None:
        """Lève MissingDependencyError si commande absente."""
        with patch(
            "linuxtools.validation.system.shutil.which",
            return_value=None,
        ):
            validator = SystemCommandValidator(
                {"missing-cmd": "sudo dnf install missing-cmd"}
            )
            with pytest.raises(MissingDependencyError):
                validator.validate()

    def test_message_contient_instruction_installation(self) -> None:
        """Le message d'erreur inclut l'instruction d'installation."""
        with patch(
            "linuxtools.validation.system.shutil.which",
            return_value=None,
        ):
            validator = SystemCommandValidator(
                {"borg": "sudo dnf install borgbackup"}
            )
            with pytest.raises(MissingDependencyError) as exc_info:
                validator.validate()
            assert "borgbackup" in str(exc_info.value)

    def test_validate_partiel_liste_manquants_seulement(self) -> None:
        """Seules les commandes absentes apparaissent dans l'erreur."""
        def which_side_effect(cmd: str) -> str | None:
            return "/usr/bin/borg" if cmd == "borg" else None

        with patch(
            "linuxtools.validation.system.shutil.which",
            side_effect=which_side_effect,
        ):
            validator = SystemCommandValidator({
                "borg": "sudo dnf install borgbackup",
                "rsync": "sudo dnf install rsync",
            })
            with pytest.raises(MissingDependencyError) as exc_info:
                validator.validate()
            assert "rsync" in str(exc_info.value)
            assert "borgbackup" not in str(exc_info.value)

    def test_missing_commands_retourne_liste_vide_si_toutes_presentes(
        self,
    ) -> None:
        """missing_commands() retourne [] si toutes trouvées."""
        with patch(
            "linuxtools.validation.system.shutil.which",
            return_value="/usr/bin/x",
        ):
            validator = SystemCommandValidator({"x": "install x"})
            assert validator.missing_commands() == []

    def test_missing_commands_retourne_commandes_absentes(
        self,
    ) -> None:
        """missing_commands() retourne les noms manquants."""
        with patch(
            "linuxtools.validation.system.shutil.which",
            return_value=None,
        ):
            validator = SystemCommandValidator({
                "a": "install a",
                "b": "install b",
            })
            missing = validator.missing_commands()
            assert sorted(missing) == ["a", "b"]

    def test_requirements_vide_ne_leve_pas(self) -> None:
        """validate() silencieux si requirements={} (rien à vérifier)."""
        validator = SystemCommandValidator({})
        validator.validate()
