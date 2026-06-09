"""Tests pour le module logging."""

import io
import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linux_python_utils.logging import (
    AnsiColors,
    ConsoleLogger,
    FileLogger,
    Logger,
    TeeStream,
)
from linux_python_utils.logging.security_logger import (
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
)


class TestFileLogger:
    """Tests pour FileLogger."""

    def test_implements_logger_interface(self, tmp_path):
        """Vérifie que FileLogger implémente l'interface Logger."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        assert isinstance(logger, Logger)

    def test_log_info(self, tmp_path):
        """Test du logging info."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        logger.log_info("Test message")

        content = log_file.read_text()
        assert "INFO" in content
        assert "Test message" in content

    def test_log_warning(self, tmp_path):
        """Test du logging warning."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        logger.log_warning("Warning message")

        content = log_file.read_text()
        assert "WARNING" in content
        assert "Warning message" in content

    def test_log_error(self, tmp_path):
        """Test du logging error."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        logger.log_error("Error message")

        content = log_file.read_text()
        assert "ERROR" in content
        assert "Error message" in content

    def test_creates_log_directory(self, tmp_path):
        """Test que le répertoire de log est créé si nécessaire."""
        log_file = tmp_path / "subdir" / "test.log"

        logger = FileLogger(str(log_file))
        logger.log_info("Test")

        assert log_file.exists()

    def test_config_from_dict(self, tmp_path):
        """Test de la configuration depuis un dictionnaire."""
        log_file = tmp_path / "test.log"
        config = {
            "logging": {
                "level": "DEBUG",
                "format": "%(levelname)s - %(message)s"
            }
        }

        logger = FileLogger(str(log_file), config=config)
        logger.log_info("Test")

        content = log_file.read_text()
        assert "INFO - Test" in content

    def test_utf8_encoding(self, tmp_path):
        """Test de l'encodage UTF-8."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        logger.log_info("Message avec accents: éàü")

        content = log_file.read_text(encoding='utf-8')
        assert "éàü" in content

    def test_log_to_file_direct(self, tmp_path):
        """Test de l'écriture directe sans formatage."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))

        logger.log_to_file("Direct message")

        content = log_file.read_text()
        assert "Direct message" in content

    def test_fichier_log_cree_en_0600(self, tmp_path):
        """Le fichier log est créé avec les permissions 0o600."""
        log_file = tmp_path / "secure.log"
        FileLogger(str(log_file))

        mode = stat.S_IMODE(os.stat(str(log_file)).st_mode)
        assert mode == 0o600

    def test_log_refuse_symlink(self, tmp_path):
        """FileLogger lève OSError si le chemin est un symlink (O_NOFOLLOW)."""
        target = tmp_path / "real.log"
        link = tmp_path / "link.log"
        os.symlink(str(target), str(link))

        with pytest.raises(OSError):
            FileLogger(str(link))

    def test_log_level_invalide_leve_valueerror(self, tmp_path):
        """Un niveau de log invalide lève ValueError."""
        log_file = str(tmp_path / "test.log")

        # ConfigurationManager-style : get() accepte la notation pointée
        class ConfigDotNotation:
            """Config avec notation pointée (simule ConfigurationManager)."""
            def get(self, key, default=None):
                return {"logging.level": "VERBOSE"}.get(key, default)

        with pytest.raises(ValueError, match="VERBOSE"):
            FileLogger(log_file, config=ConfigDotNotation())

    def test_accepte_path_en_parametre(self, tmp_path):
        """FileLogger accepte un Path en plus d'un str."""
        log_file = tmp_path / "path_test.log"
        logger = FileLogger(log_file)
        logger.log_info("via Path")
        assert log_file.exists()
        assert "via Path" in log_file.read_text()

    def test_log_success_prefixe_success(self, tmp_path):
        """log_success écrit un message avec préfixe SUCCESS dans le fichier."""
        log_file = tmp_path / "test.log"
        logger = FileLogger(str(log_file))
        logger.log_success("opération réussie")
        content = log_file.read_text()
        assert "SUCCESS: opération réussie" in content


class TestFileLoggerConsole:
    """Tests pour FileLogger avec sortie console et handlers dupliqués."""

    def test_console_output_active(self, tmp_path):
        """FileLogger avec console_output=True crée un StreamHandler."""
        log_file = str(tmp_path / "console.log")
        logger = FileLogger(log_file, console_output=True)
        # Vérifie qu'il y a 2 handlers (fichier + console)
        assert len(logger.logger.handlers) == 2
        logger.log_info("Test console")

    def test_logger_handler_existant_reutilise(self, tmp_path):
        """Crée deux FileLogger sur le même fichier : handler réutilisé."""
        log_file = str(tmp_path / "shared.log")
        # Premier logger : crée les handlers dans le registre logging
        _logger1 = FileLogger(log_file)  # noqa: F841
        # Deuxième logger sur le même fichier : doit réutiliser
        logger2 = FileLogger(log_file)
        # Le handler est récupéré depuis les handlers existants
        assert logger2.handler is not None
        logger2.log_info("Test handler réutilisé")

    def test_config_objet_type_erreur(self, tmp_path):
        """FileLogger avec config dont get() lève TypeError."""
        log_file = str(tmp_path / "type_err.log")

        class ConfigTypeError:
            """Config dont get() lève TypeError pour les clés pointées."""
            def get(self, key, default=None):
                # Simule un objet qui ne gère pas les clés en notation pointée
                if "." in key:
                    raise TypeError("Clé pointée non supportée")
                if key == "logging":
                    return {"level": "INFO", "format": "%(message)s"}
                return default

        config = ConfigTypeError()
        logger = FileLogger(log_file, config=config)
        logger.log_info("Test avec TypeError")
        content = (tmp_path / "type_err.log").read_text(encoding="utf-8")
        assert "Test avec TypeError" in content

    def test_config_sans_methode_get(self, tmp_path):
        """FileLogger avec config sans get() utilise les valeurs par defaut."""
        log_file = str(tmp_path / "test.log")

        class ConfigSansGet:
            """Config sans methode get()."""
            pass

        logger = FileLogger(log_file, config=ConfigSansGet())
        logger.log_info("Test sans get")
        content = (tmp_path / "test.log").read_text(encoding="utf-8")
        assert "Test sans get" in content


class TestSecurityLogger:
    """Tests pour SecurityLogger et SecurityEvent."""

    def test_log_event_info(self):
        """log_event avec severity='info' appelle log_info."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.AUTH_SUCCESS,
            resource="/api/login",
            severity="info",
        )
        sec_logger.log_event(event)
        mock_logger.log_info.assert_called_once()
        call_arg = mock_logger.log_info.call_args[0][0]
        assert "auth.success" in call_arg

    def test_log_event_warning(self):
        """log_event avec severity='warning' appelle log_warning."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.RATE_LIMIT_HIT,
            resource="/api/upload",
            severity="warning",
        )
        sec_logger.log_event(event)
        mock_logger.log_warning.assert_called_once()

    def test_log_event_error(self):
        """log_event avec severity='error' appelle log_error."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.ACCESS_DENIED,
            resource="/admin",
            severity="error",
        )
        sec_logger.log_event(event)
        mock_logger.log_error.assert_called_once()

    def test_log_event_critical(self):
        """log_event avec severity='critical' appelle log_error."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            resource="/hack",
            severity="critical",
        )
        sec_logger.log_event(event)
        mock_logger.log_error.assert_called_once()

    def test_log_event_avec_user_id(self):
        """log_event inclut user_id dans le payload JSON."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.CONFIG_CHANGE,
            resource="/etc/app.conf",
            severity="warning",
            user_id="admin",
        )
        sec_logger.log_event(event)
        call_arg = mock_logger.log_warning.call_args[0][0]
        payload = json.loads(call_arg)
        assert payload["user_id"] == "admin"

    def test_log_event_sans_user_id_pas_dans_payload(self):
        """log_event sans user_id n'inclut pas user_id dans le payload."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.DATA_EXPORT,
            severity="info",
        )
        sec_logger.log_event(event)
        call_arg = mock_logger.log_info.call_args[0][0]
        payload = json.loads(call_arg)
        assert "user_id" not in payload

    def test_log_event_avec_details(self):
        """log_event inclut les détails dans le payload JSON."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.DATA_MODIFICATION,
            resource="/db/users",
            details={"table": "users", "rows": 5},
            severity="info",
        )
        sec_logger.log_event(event)
        call_arg = mock_logger.log_info.call_args[0][0]
        payload = json.loads(call_arg)
        assert payload["details"]["table"] == "users"

    def test_log_event_debug_route_vers_log_info(self):
        """log_event avec severity='debug' est routé vers log_info."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.AUTH_SUCCESS,
            severity="debug",
        )
        sec_logger.log_event(event)
        mock_logger.log_info.assert_called_once()
        mock_logger.log_warning.assert_not_called()
        mock_logger.log_error.assert_not_called()

    def test_log_event_severite_inconnue_route_vers_log_info(self):
        """Une sévérité inconnue est routée vers log_info sans lever."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.DATA_EXPORT,
            severity="verbose",
        )
        sec_logger.log_event(event)
        mock_logger.log_info.assert_called_once()

    def test_security_logger_masque_les_cles_sensibles(self):
        """Les clés sensibles dans details sont remplacées par '***'."""
        mock_logger = MagicMock()
        sec_logger = SecurityLogger(mock_logger)
        event = SecurityEvent(
            event_type=SecurityEventType.AUTH_FAILURE,
            details={
                "password": "s3cr3t",
                "token": "abc123",
                "user": "alice",
                "api_key": "key-xyz",
            },
            severity="warning",
        )
        sec_logger.log_event(event)
        call_arg = mock_logger.log_warning.call_args[0][0]
        payload = json.loads(call_arg)
        assert payload["details"]["password"] == "***"
        assert payload["details"]["token"] == "***"
        assert payload["details"]["api_key"] == "***"
        assert payload["details"]["user"] == "alice"


class TestConsoleLogger:
    """Tests pour ConsoleLogger."""

    def test_est_instance_de_logger(self) -> None:
        """ConsoleLogger implémente l'interface Logger."""
        assert isinstance(ConsoleLogger(), Logger)

    def test_log_info_ecrit_sur_stdout(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_info écrit sur stdout."""
        ConsoleLogger().log_info("message info")
        assert "message info" in capsys.readouterr().out

    def test_log_warning_ecrit_sur_stderr(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_warning écrit sur stderr avec préfixe WARNING."""
        ConsoleLogger().log_warning("alerte")
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "alerte" in captured.err

    def test_log_error_ecrit_sur_stderr(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_error écrit sur stderr avec préfixe ERROR."""
        ConsoleLogger().log_error("erreur critique")
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "erreur critique" in captured.err

    def test_log_info_contient_code_bleu(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_info entoure le message du code ANSI bleu."""
        ConsoleLogger().log_info("info colorée")
        assert AnsiColors.BLUE in capsys.readouterr().out

    def test_log_warning_contient_code_orange(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_warning entoure le message du code ANSI orange."""
        ConsoleLogger().log_warning("alerte colorée")
        assert AnsiColors.ORANGE in capsys.readouterr().err

    def test_log_error_contient_code_rouge(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_error entoure le message du code ANSI rouge."""
        ConsoleLogger().log_error("erreur colorée")
        assert AnsiColors.RED in capsys.readouterr().err

    def test_log_success_contient_code_vert(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """log_success entoure le message du code ANSI vert."""
        ConsoleLogger().log_success("succès coloré")
        assert AnsiColors.GREEN in capsys.readouterr().out


class TestFileLoggerColored:
    """Tests pour FileLogger avec colored_console."""

    def test_colored_console_ajoute_code_ansi(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """FileLogger(colored_console=True) colore la sortie console."""
        log_file = str(tmp_path / "colored.log")
        logger = FileLogger(
            log_file, console_output=True, colored_console=True
        )
        logger.log_info("message coloré")
        captured = capsys.readouterr()
        assert AnsiColors.BLUE in captured.err

    def test_fichier_log_sans_codes_ansi(self, tmp_path: Path) -> None:
        """Le fichier log ne contient jamais de codes ANSI."""
        log_file = str(tmp_path / "plain.log")
        logger = FileLogger(
            log_file, console_output=True, colored_console=True
        )
        logger.log_info("contenu fichier")
        content = (tmp_path / "plain.log").read_text(encoding="utf-8")
        assert AnsiColors.BLUE not in content
        assert "contenu fichier" in content

    def test_colored_console_false_pas_de_codes_ansi(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Par défaut colored_console=False : pas de codes ANSI en console."""
        log_file = str(tmp_path / "plain_console.log")
        logger = FileLogger(log_file, console_output=True)
        logger.log_info("sans couleur")
        captured = capsys.readouterr()
        assert AnsiColors.BLUE not in captured.err


class TestTeeStream:
    """Tests pour TeeStream."""

    def test_write_ecrit_dans_flux_original(self) -> None:
        """write() écrit dans le flux original."""
        original = io.StringIO()
        log_fh = io.StringIO()
        tee = TeeStream(original, log_fh)

        tee.write("bonjour")

        assert original.getvalue() == "bonjour"

    def test_write_ecrit_dans_log_fh(self) -> None:
        """write() écrit dans le fichier log."""
        original = io.StringIO()
        log_fh = io.StringIO()
        tee = TeeStream(original, log_fh)

        tee.write("bonjour")

        assert log_fh.getvalue() == "bonjour"

    def test_write_retourne_longueur(self) -> None:
        """write() retourne len(data)."""
        result = TeeStream(io.StringIO(), io.StringIO()).write("hello")

        assert result == 5

    def test_flush_vide_les_deux_flux(self) -> None:
        """flush() appelle flush() sur les deux flux."""
        original = MagicMock()
        log_fh = MagicMock()
        tee = TeeStream(original, log_fh)

        tee.flush()

        original.flush.assert_called_once()
        log_fh.flush.assert_called_once()

    def test_getattr_delegue_au_flux_original(self) -> None:
        """__getattr__ délègue les attributs inconnus au flux original."""
        original = io.StringIO()
        tee = TeeStream(original, io.StringIO())

        assert tee.encoding == original.encoding

    def test_tee_stdout_capture_print(self, tmp_path: Path) -> None:
        """TeeStream sur sys.stdout capture les print() dans le log."""
        log_file = tmp_path / "out.log"
        log_fh = log_file.open("a", encoding="utf-8")
        original_stdout = sys.stdout
        sys.stdout = TeeStream(original_stdout, log_fh)

        try:
            print("ligne capturée")
        finally:
            sys.stdout = original_stdout
            log_fh.close()

        assert "ligne capturée" in log_file.read_text(encoding="utf-8")

    def test_close_ferme_log_pas_stdout(self) -> None:
        """close() ferme _log_fh mais ne ferme pas le flux original."""
        original = MagicMock()
        log_fh = MagicMock()
        tee = TeeStream(original, log_fh)

        tee.close()

        log_fh.flush.assert_called_once()
        log_fh.close.assert_called_once()
        original.close.assert_not_called()

    def test_tee_stderr_capture_erreurs(self, tmp_path: Path) -> None:
        """TeeStream sur sys.stderr capture les erreurs dans le log."""
        log_file = tmp_path / "err.log"
        log_fh = log_file.open("a", encoding="utf-8")
        original_stderr = sys.stderr
        sys.stderr = TeeStream(original_stderr, log_fh)

        try:
            print("erreur capturée", file=sys.stderr)
        finally:
            sys.stderr = original_stderr
            log_fh.close()

        assert "erreur capturée" in log_file.read_text(encoding="utf-8")
