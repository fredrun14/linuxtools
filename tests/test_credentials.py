"""Tests unitaires pour le module credentials.

Couvre EnvCredentialProvider, DotEnvCredentialProvider,
KeyringCredentialProvider, CredentialChain et CredentialManager.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linuxtools.credentials.base import (
    CredentialProvider,
    CredentialStore,
)
from linuxtools.credentials.chain import CredentialChain
from linuxtools.credentials.exceptions import (
    CredentialNotFoundError,
    CredentialProviderUnavailableError,
    CredentialStoreError,
)
from linuxtools.credentials.manager import CredentialManager
from linuxtools.credentials.models import (
    Credential,
    CredentialKey,
)
from linuxtools.credentials.providers.dotenv import (
    DotEnvCredentialProvider,
)
from linuxtools.credentials.providers.env import (
    EnvCredentialProvider,
)
from linuxtools.credentials.providers.keyring import (
    KeyringCredentialProvider,
)


# ---------------------------------------------------------------------------
# Tests CredentialKey et Credential
# ---------------------------------------------------------------------------

class TestCredentialKey:
    """Tests de la dataclass CredentialKey."""

    def test_creation_valide(self) -> None:
        """Cree une cle valide."""
        ck = CredentialKey(service="monapp", key="MON_SECRET")
        assert ck.service == "monapp"
        assert ck.key == "MON_SECRET"

    def test_service_vide_leve_erreur(self) -> None:
        """Un service vide leve ValueError."""
        with pytest.raises(ValueError, match="service"):
            CredentialKey(service="", key="MON_SECRET")

    def test_service_espaces_leve_erreur(self) -> None:
        """Un service compose uniquement d'espaces leve ValueError."""
        with pytest.raises(ValueError, match="service"):
            CredentialKey(service="   ", key="MON_SECRET")

    def test_key_vide_leve_erreur(self) -> None:
        """Une cle vide leve ValueError."""
        with pytest.raises(ValueError, match="key"):
            CredentialKey(service="monapp", key="")

    def test_immuabilite(self) -> None:
        """La dataclass est immuable (frozen)."""
        ck = CredentialKey(service="monapp", key="SECRET")
        with pytest.raises(AttributeError):
            ck.service = "autre"  # type: ignore[misc]


class TestCredential:
    """Tests de la dataclass Credential."""

    def test_creation_valide(self) -> None:
        """Cree un credential valide."""
        c = Credential(
            service="monapp",
            key="MON_SECRET",
            value="s3cr3t",
            source="env",
        )
        assert c.value == "s3cr3t"
        assert c.source == "env"

    def test_source_vide_par_defaut(self) -> None:
        """La source est vide par defaut."""
        c = Credential(
            service="monapp", key="SECRET", value="val"
        )
        assert c.source == ""

    def test_repr_ne_contient_pas_la_valeur(self) -> None:
        """repr(Credential) ne doit jamais exposer la valeur secrète."""
        c = Credential(service="svc", key="k", value="super_secret")
        assert "super_secret" not in repr(c)

    def test_credential_key_property(self) -> None:
        """La propriete credential_key retourne un CredentialKey."""
        c = Credential(
            service="monapp", key="SECRET", value="val"
        )
        ck = c.credential_key
        assert isinstance(ck, CredentialKey)
        assert ck.service == "monapp"
        assert ck.key == "SECRET"

    def test_service_vide_leve_erreur(self) -> None:
        """Un service vide leve ValueError."""
        with pytest.raises(ValueError, match="service"):
            Credential(service="", key="K", value="v")

    def test_key_vide_leve_erreur(self) -> None:
        """Une cle vide leve ValueError."""
        with pytest.raises(ValueError, match="key"):
            Credential(service="s", key="", value="v")


# ---------------------------------------------------------------------------
# Tests EnvCredentialProvider
# ---------------------------------------------------------------------------

class TestEnvCredentialProvider:
    """Tests du provider de variables d'environnement."""

    def test_get_retourne_valeur_existante(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get() retourne la valeur si la variable existe."""
        monkeypatch.setenv("MON_SECRET", "valeur_test")
        provider = EnvCredentialProvider()
        assert provider.get("monapp", "MON_SECRET") == "valeur_test"

    def test_get_normalise_cle_majuscule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get() normalise la cle en majuscules."""
        monkeypatch.setenv("MON_SECRET", "valeur_test")
        provider = EnvCredentialProvider()
        assert provider.get("monapp", "mon_secret") == "valeur_test"

    def test_get_retourne_none_si_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get() retourne None si la variable est absente."""
        monkeypatch.delenv("VARIABLE_INEXISTANTE", raising=False)
        provider = EnvCredentialProvider()
        assert provider.get("monapp", "VARIABLE_INEXISTANTE") is None

    def test_get_retourne_none_si_vide(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get() retourne None si la variable est vide."""
        monkeypatch.setenv("MON_SECRET", "")
        provider = EnvCredentialProvider()
        assert provider.get("monapp", "MON_SECRET") is None

    def test_is_available_toujours_true(self) -> None:
        """is_available() retourne toujours True."""
        provider = EnvCredentialProvider()
        assert provider.is_available() is True

    def test_source_name(self) -> None:
        """source_name retourne 'env'."""
        provider = EnvCredentialProvider()
        assert provider.source_name == "env"

    def test_implements_abc(self) -> None:
        """EnvCredentialProvider est bien un CredentialProvider."""
        provider = EnvCredentialProvider()
        assert isinstance(provider, CredentialProvider)


# ---------------------------------------------------------------------------
# Tests DotEnvCredentialProvider
# ---------------------------------------------------------------------------

class TestDotEnvCredentialProvider:
    """Tests du provider de fichier .env."""

    def test_load_charge_le_fichier(
        self, tmp_path: Path
    ) -> None:
        """load() charge les variables dans le dict interne."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SECRET_DOTENV=valeur_dotenv\n")
        provider = DotEnvCredentialProvider(dotenv_path=dotenv_file)

        mock_dotenv = MagicMock()
        mock_dotenv.dotenv_values.return_value = {
            "SECRET_DOTENV": "valeur_dotenv"
        }
        with patch.dict("sys.modules", {"dotenv": mock_dotenv}):
            result = provider.load()
        assert result is True
        assert provider._values == {"SECRET_DOTENV": "valeur_dotenv"}

    def test_dotenv_ne_pollue_pas_os_environ(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get() ne doit jamais injecter de variables dans os.environ."""
        monkeypatch.delenv("SECRET_ISOLE", raising=False)
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SECRET_ISOLE=valeur_privee\n")
        provider = DotEnvCredentialProvider(dotenv_path=dotenv_file)

        mock_dotenv = MagicMock()
        mock_dotenv.dotenv_values.return_value = {
            "SECRET_ISOLE": "valeur_privee"
        }
        with patch.dict("sys.modules", {"dotenv": mock_dotenv}):
            result = provider.get("monapp", "SECRET_ISOLE")

        assert result == "valeur_privee"
        assert "SECRET_ISOLE" not in os.environ

    def test_get_retourne_valeur_depuis_dotenv(
        self, tmp_path: Path
    ) -> None:
        """get() retourne la valeur depuis le dict interne (pas os.environ)."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SECRET_GET=valeur_get\n")
        provider = DotEnvCredentialProvider(dotenv_path=dotenv_file)

        mock_dotenv = MagicMock()
        mock_dotenv.dotenv_values.return_value = {"SECRET_GET": "valeur_get"}
        with patch.dict("sys.modules", {"dotenv": mock_dotenv}):
            result = provider.get("monapp", "SECRET_GET")
        assert result == "valeur_get"

    def test_dotenv_avertit_si_env_world_readable(
        self, tmp_path: Path
    ) -> None:
        """load() log un warning si le .env est lisible par d'autres."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("KEY=val\n")
        dotenv_file.chmod(0o644)
        mock_logger = MagicMock()
        provider = DotEnvCredentialProvider(
            dotenv_path=dotenv_file, logger=mock_logger
        )
        mock_dotenv = MagicMock()
        mock_dotenv.dotenv_values.return_value = {"KEY": "val"}
        with patch.dict("sys.modules", {"dotenv": mock_dotenv}):
            provider.load()
        mock_logger.log_warning.assert_called()
        calls_str = " ".join(
            str(c) for c in mock_logger.log_warning.call_args_list
        )
        assert "accessible" in calls_str

    def test_load_retourne_false_si_fichier_absent(
        self, tmp_path: Path
    ) -> None:
        """load() retourne False si le fichier n'existe pas."""
        provider = DotEnvCredentialProvider(
            dotenv_path=tmp_path / "inexistant.env"
        )
        assert provider.load() is False

    def test_is_available_false_si_fichier_absent(
        self, tmp_path: Path
    ) -> None:
        """is_available() retourne False si le fichier .env est absent."""
        provider = DotEnvCredentialProvider(
            dotenv_path=tmp_path / "inexistant.env"
        )
        assert provider.is_available() is False

    def test_is_available_true_si_fichier_existe(
        self, tmp_path: Path
    ) -> None:
        """is_available() retourne True si le fichier existe."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("KEY=val\n")
        provider = DotEnvCredentialProvider(dotenv_path=dotenv_file)
        with patch.dict("sys.modules", {"dotenv": MagicMock()}):
            assert provider.is_available() is True

    def test_is_available_false_si_dotenv_absent(
        self, tmp_path: Path
    ) -> None:
        """is_available() retourne False si python-dotenv absent."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("KEY=val\n")
        provider = DotEnvCredentialProvider(dotenv_path=dotenv_file)
        with patch.dict(
            "sys.modules", {"dotenv": None}
        ):
            assert provider.is_available() is False

    def test_load_log_warning_si_fichier_absent_avec_logger(
        self, tmp_path: Path
    ) -> None:
        """load() log un warning si le fichier est absent et logger fourni."""
        mock_logger = MagicMock()
        provider = DotEnvCredentialProvider(
            dotenv_path=tmp_path / "inexistant.env",
            logger=mock_logger,
        )
        mock_dotenv = MagicMock()
        with patch.dict("sys.modules", {"dotenv": mock_dotenv}):
            result = provider.load()
        assert result is False
        mock_logger.log_warning.assert_called_once()

    def test_source_name(self, tmp_path: Path) -> None:
        """source_name retourne 'dotenv'."""
        provider = DotEnvCredentialProvider(
            dotenv_path=tmp_path / ".env"
        )
        assert provider.source_name == "dotenv"


# ---------------------------------------------------------------------------
# Tests KeyringCredentialProvider
# ---------------------------------------------------------------------------

class TestKeyringCredentialProvider:
    """Tests du provider keyring avec backend mocke."""

    def _make_backend(
        self,
        stored: dict | None = None,
    ) -> MagicMock:
        """Cree un backend keyring mocke."""
        backend = MagicMock()
        _store: dict = stored if stored is not None else {}
        backend.get_password.side_effect = (
            lambda svc, key: _store.get((svc, key))
        )
        backend.set_password.side_effect = (
            lambda svc, key, val: _store.update({(svc, key): val})
        )
        backend.delete_password.side_effect = (
            lambda svc, key: _store.pop((svc, key), None)
        )
        return backend

    def test_get_retourne_valeur(self) -> None:
        """get() retourne la valeur depuis le backend."""
        backend = self._make_backend({("monapp", "user"): "s3cr3t"})
        provider = KeyringCredentialProvider(keyring_backend=backend)
        assert provider.get("monapp", "user") == "s3cr3t"

    def test_get_retourne_none_si_absent(self) -> None:
        """get() retourne None si le credential est absent."""
        backend = self._make_backend()
        provider = KeyringCredentialProvider(keyring_backend=backend)
        assert provider.get("monapp", "absent") is None

    def test_set_stocke_le_credential(self) -> None:
        """set() stocke le credential via le backend."""
        store: dict = {}
        backend = self._make_backend(store)
        provider = KeyringCredentialProvider(keyring_backend=backend)
        provider.set("monapp", "user", "nouveau_mdp")
        assert store.get(("monapp", "user")) == "nouveau_mdp"

    def test_set_leve_credential_store_error(self) -> None:
        """set() leve CredentialStoreError si le backend echoue."""
        backend = MagicMock()
        backend.set_password.side_effect = Exception("erreur keyring")
        provider = KeyringCredentialProvider(keyring_backend=backend)
        with pytest.raises(CredentialStoreError, match="erreur keyring"):
            provider.set("monapp", "user", "mdp")

    def test_delete_supprime_credential(self) -> None:
        """delete() supprime le credential du backend."""
        store = {("monapp", "user"): "mdp"}
        backend = self._make_backend(store)
        provider = KeyringCredentialProvider(keyring_backend=backend)
        provider.delete("monapp", "user")
        assert ("monapp", "user") not in store

    def test_delete_silencieux_si_absent(self) -> None:
        """delete() est silencieux si le credential est absent."""
        backend = MagicMock()
        backend.delete_password.side_effect = Exception("absent")
        provider = KeyringCredentialProvider(keyring_backend=backend)
        provider.delete("monapp", "absent")  # ne leve pas d'exception

    def test_is_available_true_avec_backend(self) -> None:
        """is_available() retourne True si un backend est injecte."""
        backend = MagicMock()
        provider = KeyringCredentialProvider(keyring_backend=backend)
        assert provider.is_available() is True

    def test_is_available_false_sans_keyring(self) -> None:
        """is_available() retourne False si keyring n'est pas installe."""
        provider = KeyringCredentialProvider()
        with patch.dict("sys.modules", {"keyring": None}):
            assert provider.is_available() is False

    def test_source_name(self) -> None:
        """source_name retourne 'keyring'."""
        backend = MagicMock()
        provider = KeyringCredentialProvider(keyring_backend=backend)
        assert provider.source_name == "keyring"

    def test_implements_credential_store(self) -> None:
        """KeyringCredentialProvider est un CredentialStore."""
        backend = MagicMock()
        provider = KeyringCredentialProvider(keyring_backend=backend)
        assert isinstance(provider, CredentialStore)

    def test_get_keyring_retourne_module_si_installe(self) -> None:
        """_get_keyring() retourne le module keyring si installe."""
        provider = KeyringCredentialProvider()
        mock_keyring = MagicMock()
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = provider._get_keyring()
        assert result is mock_keyring

    def test_get_keyring_leve_erreur_sans_keyring_installe(self) -> None:
        """_get_keyring() leve l'erreur si keyring est absent."""
        provider = KeyringCredentialProvider()
        with (
            patch.dict("sys.modules", {"keyring": None}),
            pytest.raises(CredentialProviderUnavailableError),
        ):
            provider._get_keyring()

    def test_get_retourne_none_si_provider_indisponible(self) -> None:
        """get() retourne None si is_available() est False."""
        provider = KeyringCredentialProvider()
        with patch.dict("sys.modules", {"keyring": None}):
            result = provider.get("svc", "key")
        assert result is None

    def test_get_retourne_none_sur_exception_get_password(self) -> None:
        """get() retourne None si get_password leve une exception."""
        backend = MagicMock()
        backend.get_password.side_effect = Exception("erreur inattendue")
        provider = KeyringCredentialProvider(keyring_backend=backend)
        result = provider.get("svc", "key")
        assert result is None

    def test_get_log_warning_sur_exception_keyring(self) -> None:
        """get() log un warning si get_password leve une exception."""
        backend = MagicMock()
        backend.get_password.side_effect = Exception("bus D-Bus indisponible")
        mock_logger = MagicMock()
        provider = KeyringCredentialProvider(
            keyring_backend=backend, logger=mock_logger
        )
        result = provider.get("svc", "KEY")
        assert result is None
        mock_logger.log_warning.assert_called_once()

    def test_get_retourne_none_sans_log_si_pas_de_logger(self) -> None:
        """get() retourne None sans erreur si pas de logger."""
        backend = MagicMock()
        backend.get_password.side_effect = Exception("erreur")
        provider = KeyringCredentialProvider(keyring_backend=backend)
        result = provider.get("svc", "KEY")
        assert result is None

    def test_set_log_info_avec_logger(self) -> None:
        """set() log un message info si logger fourni et stockage reussi."""
        mock_logger = MagicMock()
        store: dict = {}
        backend = self._make_backend(store)
        provider = KeyringCredentialProvider(
            keyring_backend=backend, logger=mock_logger
        )
        provider.set("svc", "key", "valeur")
        mock_logger.log_info.assert_called_once()

    def test_set_leve_store_error_si_keyring_indisponible(self) -> None:
        """set() leve CredentialStoreError si keyring non installe."""
        provider = KeyringCredentialProvider()
        with (
            patch.dict("sys.modules", {"keyring": None}),
            pytest.raises(CredentialStoreError),
        ):
            provider.set("svc", "key", "valeur")

    def test_delete_retourne_si_provider_indisponible(self) -> None:
        """delete() retourne silencieusement si is_available() est False."""
        provider = KeyringCredentialProvider()
        with patch.dict("sys.modules", {"keyring": None}):
            provider.delete("svc", "key")  # ne doit pas lever d'exception

    def test_delete_log_info_avec_logger(self) -> None:
        """delete() log un message info si logger fourni."""
        mock_logger = MagicMock()
        store = {("svc", "key"): "val"}
        backend = self._make_backend(store)
        provider = KeyringCredentialProvider(
            keyring_backend=backend, logger=mock_logger
        )
        provider.delete("svc", "key")
        mock_logger.log_info.assert_called_once()

    def test_delete_logue_erreur_reelle(self) -> None:
        """delete() log l'exception réelle via log_warning."""
        mock_logger = MagicMock()
        backend = MagicMock()
        backend.delete_password.side_effect = Exception("erreur D-Bus")
        provider = KeyringCredentialProvider(
            keyring_backend=backend, logger=mock_logger
        )
        provider.delete("svc", "key")  # ne doit pas lever
        mock_logger.log_warning.assert_called_once()
        assert "erreur D-Bus" in str(
            mock_logger.log_warning.call_args
        )

    def test_is_available_true_avec_keyring_installe(self) -> None:
        """is_available() retourne True si keyring est installe."""
        provider = KeyringCredentialProvider()
        with patch.dict("sys.modules", {"keyring": MagicMock()}):
            assert provider.is_available() is True


# ---------------------------------------------------------------------------
# Tests CredentialChain
# ---------------------------------------------------------------------------

def _make_provider(
    value: str | None,
    available: bool = True,
    source: str = "mock",
) -> MagicMock:
    """Cree un CredentialProvider mocke."""
    provider = MagicMock(spec=CredentialProvider)
    provider.get.return_value = value
    provider.is_available.return_value = available
    provider.source_name = source
    return provider


class TestCredentialChain:
    """Tests de la chaine de priorite."""

    def test_retourne_valeur_du_premier_provider(self) -> None:
        """get() retourne la valeur du premier provider qui repond."""
        p1 = _make_provider("valeur_p1", source="p1")
        p2 = _make_provider("valeur_p2", source="p2")
        chain = CredentialChain([p1, p2])
        assert chain.get("svc", "KEY") == "valeur_p1"
        p2.get.assert_not_called()

    def test_passe_au_provider_suivant_si_none(self) -> None:
        """get() passe au provider suivant si le premier retourne None."""
        p1 = _make_provider(None, source="p1")
        p2 = _make_provider("valeur_p2", source="p2")
        chain = CredentialChain([p1, p2])
        assert chain.get("svc", "KEY") == "valeur_p2"

    def test_retourne_none_si_aucun_provider_repond(self) -> None:
        """get() retourne None si tous les providers retournent None."""
        p1 = _make_provider(None, source="p1")
        p2 = _make_provider(None, source="p2")
        chain = CredentialChain([p1, p2])
        assert chain.get("svc", "KEY") is None

    def test_ignore_providers_indisponibles(self) -> None:
        """get() ignore les providers dont is_available() est False."""
        p1 = _make_provider("valeur_p1", available=False, source="p1")
        p2 = _make_provider("valeur_p2", available=True, source="p2")
        chain = CredentialChain([p1, p2])
        assert chain.get("svc", "KEY") == "valeur_p2"
        p1.get.assert_not_called()

    def test_get_with_source_retourne_credential(self) -> None:
        """get_with_source() retourne un Credential avec la source."""
        p1 = _make_provider(None, source="env")
        p2 = _make_provider("valeur", source="keyring")
        chain = CredentialChain([p1, p2])
        result = chain.get_with_source("svc", "KEY")
        assert result is not None
        assert isinstance(result, Credential)
        assert result.value == "valeur"
        assert result.source == "keyring"

    def test_get_with_source_retourne_none_si_absent(self) -> None:
        """get_with_source() retourne None si aucun provider repond."""
        p1 = _make_provider(None, source="env")
        chain = CredentialChain([p1])
        assert chain.get_with_source("svc", "KEY") is None

    def test_is_available_true_si_un_provider_disponible(self) -> None:
        """is_available() retourne True si au moins un provider l'est."""
        p1 = _make_provider(None, available=False)
        p2 = _make_provider(None, available=True)
        chain = CredentialChain([p1, p2])
        assert chain.is_available() is True

    def test_is_available_false_si_aucun_disponible(self) -> None:
        """is_available() retourne False si aucun provider n'est disponible."""
        p1 = _make_provider(None, available=False)
        p2 = _make_provider(None, available=False)
        chain = CredentialChain([p1, p2])
        assert chain.is_available() is False

    def test_source_name(self) -> None:
        """source_name retourne 'chain'."""
        chain = CredentialChain([])
        assert chain.source_name == "chain"

    def test_default_cree_chaine_sans_dotenv(self) -> None:
        """default() cree la chaine env -> keyring sans dotenv_path."""
        chain = CredentialChain.default()
        assert len(chain._providers) == 2  # noqa: PLR2004
        assert chain._providers[0].source_name == "env"
        assert chain._providers[1].source_name == "keyring"

    def test_default_cree_chaine_avec_dotenv(
        self, tmp_path: Path
    ) -> None:
        """default() cree la chaine env -> dotenv -> keyring."""
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("KEY=val\n")
        chain = CredentialChain.default(dotenv_path=dotenv_path)
        assert len(chain._providers) == 3  # noqa: PLR2004
        assert chain._providers[0].source_name == "env"
        assert chain._providers[1].source_name == "dotenv"
        assert chain._providers[2].source_name == "keyring"

    def test_get_log_info_avec_logger(self) -> None:
        """get() log l'info de source quand un logger est fourni."""
        mock_logger = MagicMock()
        p1 = _make_provider("valeur", source="env")
        chain = CredentialChain([p1], logger=mock_logger)
        result = chain.get("svc", "KEY")
        assert result == "valeur"
        mock_logger.log_info.assert_called_once()

    def test_get_log_info_escalade_provider(self) -> None:
        """get() log l'escalade quand un provider ne trouve pas."""
        mock_logger = MagicMock()
        p1 = _make_provider(None, source="env")
        p2 = _make_provider("valeur", source="keyring")
        chain = CredentialChain([p1, p2], logger=mock_logger)
        result = chain.get("svc", "KEY")
        assert result == "valeur"
        calls = [str(c) for c in mock_logger.log_info.call_args_list]
        assert any("escalade" in c for c in calls)

    def test_get_ne_logue_jamais_la_valeur(self) -> None:
        """get() ne doit jamais écrire la valeur secrète dans les logs."""
        mock_logger = MagicMock()
        p1 = _make_provider("valeur_secrete", source="env")
        chain = CredentialChain([p1], logger=mock_logger)
        chain.get("svc", "KEY")
        for call in mock_logger.mock_calls:
            assert "valeur_secrete" not in str(call)

    def test_get_with_source_ignore_providers_indisponibles(self) -> None:
        """get_with_source() ignore les providers indisponibles."""
        p1 = _make_provider("valeur_p1", available=False, source="env")
        p2 = _make_provider("valeur_p2", available=True, source="keyring")
        chain = CredentialChain([p1, p2])
        result = chain.get_with_source("svc", "KEY")
        assert result is not None
        assert result.source == "keyring"
        p1.get.assert_not_called()


# ---------------------------------------------------------------------------
# Tests CredentialManager
# ---------------------------------------------------------------------------

class TestCredentialManager:
    """Tests de la facade CredentialManager."""

    def _make_chain(self, value: str | None) -> CredentialChain:
        """Cree une chaine mockee retournant une valeur fixe."""
        chain = MagicMock(spec=CredentialChain)
        chain.get.return_value = value
        chain.source_name = "chain"
        return chain

    def _make_store(self) -> MagicMock:
        """Cree un store mocke."""
        return MagicMock(spec=CredentialStore)

    def test_get_retourne_valeur(self) -> None:
        """get() retourne la valeur via la chaine."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain("s3cr3t"),
        )
        assert manager.get("KEY") == "s3cr3t"

    def test_get_retourne_default_si_absent(self) -> None:
        """get() retourne default si le credential est absent."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
        )
        assert manager.get("KEY", default="vide") == "vide"

    def test_get_retourne_chaine_vide_par_defaut(self) -> None:
        """get() retourne '' si absent et aucun default fourni."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
        )
        assert manager.get("KEY") == ""

    def test_require_retourne_valeur(self) -> None:
        """require() retourne la valeur si presente."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain("secret"),
        )
        assert manager.require("KEY") == "secret"

    def test_require_leve_erreur_si_absent(self) -> None:
        """require() leve CredentialNotFoundError si absent."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
        )
        with pytest.raises(CredentialNotFoundError, match="KEY"):
            manager.require("KEY")

    def test_require_log_warning_si_absent(self) -> None:
        """require() log un warning avant de lever CredentialNotFoundError."""
        mock_logger = MagicMock()
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
            logger=mock_logger,
        )
        with pytest.raises(CredentialNotFoundError):
            manager.require("KEY")
        mock_logger.log_warning.assert_called_once()

    def test_store_delegue_au_store(self) -> None:
        """store() appelle store.set() avec le bon service."""
        store = self._make_store()
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
            store=store,
        )
        manager.store("KEY", "valeur")
        store.set.assert_called_once_with("svc", "KEY", "valeur")

    def test_store_leve_erreur_sans_store(self) -> None:
        """store() leve CredentialStoreError si aucun store configure."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
        )
        with pytest.raises(CredentialStoreError):
            manager.store("KEY", "valeur")

    def test_delete_delegue_au_store(self) -> None:
        """delete() appelle store.delete() avec le bon service."""
        store = self._make_store()
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
            store=store,
        )
        manager.delete("KEY")
        store.delete.assert_called_once_with("svc", "KEY")

    def test_delete_leve_erreur_sans_store(self) -> None:
        """delete() leve CredentialStoreError si aucun store configure."""
        manager = CredentialManager(
            service="svc",
            chain=self._make_chain(None),
        )
        with pytest.raises(CredentialStoreError):
            manager.delete("KEY")

    def test_from_dotenv_cree_manager(
        self, tmp_path: Path
    ) -> None:
        """from_dotenv() cree un CredentialManager operationnel."""
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("API_KEY=test_value\n")
        manager = CredentialManager.from_dotenv(
            service="monapp",
            dotenv_path=dotenv_file,
        )
        assert manager._service == "monapp"
        assert manager._store is not None
        assert isinstance(manager._store, KeyringCredentialProvider)
