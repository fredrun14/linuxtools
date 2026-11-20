"""Tests de comportement complémentaires pour le provider .env."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from linuxtools.credentials.providers.dotenv import DotEnvCredentialProvider


def test_load_renvoie_false_sans_la_dependance_python_dotenv(
    tmp_path: Path,
) -> None:
    """Sans python-dotenv installé, le chargement échoue sans exception."""
    fichier = tmp_path / ".env"
    fichier.write_text("CLE=valeur\n", encoding="utf-8")
    provider = DotEnvCredentialProvider(fichier)

    with patch.dict(sys.modules, {"dotenv": None}):
        assert provider.load() is False


def test_get_ne_recharge_pas_un_env_deja_charge(tmp_path: Path) -> None:
    """Une seconde lecture réutilise les valeurs déjà chargées."""
    fichier = tmp_path / ".env"
    fichier.write_text("CLE=valeur\n", encoding="utf-8")
    fichier.chmod(0o600)
    faux_dotenv = MagicMock()
    faux_dotenv.dotenv_values.return_value = {"CLE": "valeur"}
    provider = DotEnvCredentialProvider(fichier)

    with patch.dict(sys.modules, {"dotenv": faux_dotenv}):
        premier = provider.get("svc", "cle")
        second = provider.get("svc", "cle")

    assert (premier, second) == ("valeur", "valeur")
    faux_dotenv.dotenv_values.assert_called_once()
