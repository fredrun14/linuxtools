#!/usr/bin/env python3
"""Tests unitaires pour le module errors."""

import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

from linux_python_utils.errors.base import ErrorHandlerChain
from linux_python_utils.errors.console_handler import ConsoleErrorHandler
from linux_python_utils.errors.context import ErrorContext
from linux_python_utils.errors.exceptions import (
    AppPermissionError,
    ConfigurationError,
    FileConfigurationError,
    InstallationError,
    MissingDependencyError,
    RollbackError,
    ValidationError,
    require_root,
)
from linux_python_utils.errors.logger_handler import LoggerErrorHandler


class TestRequireRoot:
    """Tests pour la fonction require_root."""

    @patch("linux_python_utils.errors.exceptions.os.geteuid", return_value=0)
    def test_passe_si_euid_zero(self, _mock) -> None:
        """require_root() silencieux quand le process est root."""
        require_root()

    @patch("linux_python_utils.errors.exceptions.os.geteuid", return_value=1000)
    def test_leve_si_non_root(self, _mock) -> None:
        """require_root() lève AppPermissionError si euid != 0."""
        with pytest.raises(AppPermissionError):
            require_root()

    @patch("linux_python_utils.errors.exceptions.os.geteuid", return_value=1000)
    def test_message_par_defaut_mentionne_root(self, _mock) -> None:
        """Le message par défaut mentionne les droits root."""
        with pytest.raises(AppPermissionError, match="root"):
            require_root()

    @patch("linux_python_utils.errors.exceptions.os.geteuid", return_value=1000)
    def test_message_personnalise(self, _mock) -> None:
        """require_root() utilise le message personnalisé si fourni."""
        with pytest.raises(AppPermissionError, match="sudo requis"):
            require_root("sudo requis")


class TestConsoleErrorHandler(unittest.TestCase):
    """Tests pour ConsoleErrorHandler."""

    def setUp(self) -> None:
        self.handler = ConsoleErrorHandler()

    @patch("builtins.print")
    def test_handle_missing_dependency(
        self, mock_print: MagicMock
    ) -> None:
        """Vérifie le message pour MissingDependencyError."""
        error = MissingDependencyError("flatpak manquant")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🛑 MissingDependencyError: flatpak manquant",
            file=sys.stderr,
        )
        mock_print.assert_any_call(
            "\n🔧 Solution : Installez les dépendances"
            " manquantes comme indiqué.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_permission_error(self, mock_print: MagicMock) -> None:
        """Vérifie le message pour AppPermissionError."""
        error = AppPermissionError("permission refusée")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🔧 Solution : Exécutez avec sudo ou vérifiez les permissions.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_configuration_error(
        self, mock_print: MagicMock
    ) -> None:
        """Vérifie le message pour ConfigurationError."""
        error = ConfigurationError("config invalide")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🔧 Solution : Vérifiez votre fichier de configuration.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_installation_error(
        self, mock_print: MagicMock
    ) -> None:
        """Vérifie le message pour InstallationError."""
        error = InstallationError("install échouée")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🔧 Solution : Consultez les logs pour plus de détails.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_generic_flatpak_error(
        self, mock_print: MagicMock
    ) -> None:
        """Vérifie le message par défaut pour ValidationError."""
        error = ValidationError("validation échouée")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🔧 Solution : Voir les suggestions ci-dessus.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_subclass_matches_parent(
        self, mock_print: MagicMock
    ) -> None:
        """FileConfigurationError doit matcher ConfigurationError."""
        error = FileConfigurationError("fichier invalide")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n🔧 Solution : Vérifiez votre fichier de configuration.",
            file=sys.stderr,
        )

    @patch("builtins.print")
    def test_handle_unknown_error(self, mock_print: MagicMock) -> None:
        """Vérifie le message pour une erreur inconnue."""
        error = RuntimeError("erreur inconnue")
        self.handler.handle(error)
        mock_print.assert_any_call(
            "\n💥 Erreur inattendue: erreur inconnue", file=sys.stderr
        )
        mock_print.assert_any_call("Type: RuntimeError", file=sys.stderr)


class TestLoggerErrorHandler(unittest.TestCase):
    """Tests pour LoggerErrorHandler."""

    def setUp(self) -> None:
        self.mock_logger = MagicMock()
        self.handler = LoggerErrorHandler(self.mock_logger)

    def test_handle_known_error(self) -> None:
        """Vérifie le log pour une erreur connue."""
        error = ConfigurationError("config invalide")
        self.handler.handle(error)
        self.mock_logger.log_error.assert_called_once_with(
            "ConfigurationError: config invalide"
        )

    def test_handle_unknown_error(self) -> None:
        """Vérifie le log pour une erreur inconnue."""
        error = RuntimeError("runtime error")
        self.handler.handle(error)
        self.mock_logger.log_error.assert_called_once_with(
            "Erreur inattendue: RuntimeError: runtime error"
        )


class TestErrorHandlerChain(unittest.TestCase):
    """Tests pour ErrorHandlerChain."""

    def test_handle_calls_all_handlers(self) -> None:
        """Vérifie que tous les handlers sont appelés."""
        chain = ErrorHandlerChain()
        handler1 = MagicMock()
        handler2 = MagicMock()
        chain.add_handler(handler1)
        chain.add_handler(handler2)

        error = RuntimeError("test")
        chain.handle(error)

        handler1.handle.assert_called_once_with(error)
        handler2.handle.assert_called_once_with(error)

    def test_handle_continues_after_handler_failure(self) -> None:
        """Un handler qui lève ne doit pas bloquer les suivants."""
        chain = ErrorHandlerChain()
        handler1 = MagicMock()
        handler1.handle.side_effect = RuntimeError("handler failed")
        handler2 = MagicMock()
        chain.add_handler(handler1)
        chain.add_handler(handler2)

        error = RuntimeError("test")
        chain.handle(error)

        handler1.handle.assert_called_once_with(error)
        handler2.handle.assert_called_once_with(error)

    def test_handle_and_exit(self) -> None:
        """Vérifie que handle_and_exit appelle sys.exit."""
        chain = ErrorHandlerChain()
        handler = MagicMock()
        chain.add_handler(handler)

        error = RuntimeError("test")
        with self.assertRaises(SystemExit) as ctx:
            chain.handle_and_exit(error, exit_code=2)

        self.assertEqual(ctx.exception.code, 2)
        handler.handle.assert_called_once_with(error)


class TestErrorContext(unittest.TestCase):
    """Tests pour ErrorContext."""

    def setUp(self) -> None:
        self.mock_logger = MagicMock()
        self.context = ErrorContext(self.mock_logger)

    def test_add_rollback_action(self) -> None:
        """Vérifie l'ajout d'une action de rollback."""
        action = MagicMock()
        self.context.add_rollback_action(action, "test action")
        self.context.execute_rollback()
        action.assert_called_once()

    def test_execute_rollback_success(self) -> None:
        """Vérifie l'exécution réussie du rollback."""
        action = MagicMock()
        self.context.add_rollback_action(action, "action test")

        self.context.execute_rollback()

        action.assert_called_once()
        self.mock_logger.log_info.assert_any_call(
            "Rollback réussi: action test"
        )

    def test_execute_rollback_reversed_order(self) -> None:
        """Vérifie que les actions sont exécutées en ordre inverse."""
        call_order: list[int] = []
        self.context.add_rollback_action(
            lambda: call_order.append(1), "action 1"
        )
        self.context.add_rollback_action(
            lambda: call_order.append(2), "action 2"
        )

        self.context.execute_rollback()

        self.assertEqual(call_order, [2, 1])

    def test_execute_rollback_raises_on_failure(self) -> None:
        """Vérifie que RollbackError est levé en cas d'échec."""
        action = MagicMock(side_effect=RuntimeError("rollback failed"))
        self.context.add_rollback_action(action, "failing action")

        with self.assertRaises(RollbackError):
            self.context.execute_rollback()

    def test_execute_rollback_continues_after_failure(self) -> None:
        """Vérifie que toutes les actions sont tentées malgré un échec."""
        action1 = MagicMock(side_effect=RuntimeError("fail"))
        action2 = MagicMock()
        self.context.add_rollback_action(action1, "failing")
        self.context.add_rollback_action(action2, "succeeding")

        with self.assertRaises(RollbackError):
            self.context.execute_rollback()

        # Les deux actions doivent avoir été appelées (ordre inversé)
        action1.assert_called_once()
        action2.assert_called_once()

    def test_handle_error_with_rollback(self) -> None:
        """Vérifie handle_error_with_rollback exécute le rollback."""
        action = MagicMock()
        self.context.add_rollback_action(action, "rollback action")

        error = ConfigurationError("test error")
        self.context.handle_error_with_rollback(error)

        action.assert_called_once()

    def test_handle_error_with_rollback_catches_rollback_error(
        self,
    ) -> None:
        """RollbackError ne doit pas se propager hors de la méthode."""
        action = MagicMock(side_effect=RuntimeError("fail"))
        self.context.add_rollback_action(action, "failing action")

        error = ConfigurationError("test error")
        # Ne doit pas lever RollbackError
        self.context.handle_error_with_rollback(error)

    def test_handle_error_without_rollback_actions(self) -> None:
        """Vérifie le comportement sans actions de rollback."""
        error = ConfigurationError("test error")
        self.context.handle_error_with_rollback(error)

        self.mock_logger.log_info.assert_called_with(
            "Aucune action de rollback nécessaire."
        )

    def test_clear_rollback_actions(self) -> None:
        """Vérifie la suppression de toutes les actions."""
        action = MagicMock()
        self.context.add_rollback_action(action, "action")
        self.context.clear_rollback_actions()
        self.context.execute_rollback()
        action.assert_not_called()


class TestConsoleErrorHandlerInjectees(unittest.TestCase):
    """Tests de routage via les paramètres injectés."""

    @patch("builtins.print")
    def test_console_handler_route_selon_base_error_type(
        self, mock_print: MagicMock
    ) -> None:
        """base_error_type injecté contrôle le routage known/unknown."""
        class MonErreur(Exception):
            pass

        handler = ConsoleErrorHandler(
            base_error_type=MonErreur,
            solutions={},
        )
        handler.handle(MonErreur("connue"))
        self.assertTrue(
            any("🛑" in str(c) for c in mock_print.call_args_list)
        )

        mock_print.reset_mock()
        handler.handle(RuntimeError("inconnue"))
        self.assertTrue(
            any("💥" in str(c) for c in mock_print.call_args_list)
        )

    @patch("builtins.print")
    def test_console_handler_utilise_solutions_injectees(
        self, mock_print: MagicMock
    ) -> None:
        """Le dictionnaire solutions injecté est consulté."""
        class MonErreur(Exception):
            pass

        handler = ConsoleErrorHandler(
            base_error_type=MonErreur,
            solutions={MonErreur: "\n🔧 Ma solution personnalisée."},
        )
        handler.handle(MonErreur("test"))
        mock_print.assert_any_call(
            "\n🔧 Ma solution personnalisée.", file=sys.stderr
        )


class TestLoggerErrorHandlerInjecte(unittest.TestCase):
    """Tests de routage via base_error_type injecté."""

    def test_logger_handler_route_selon_base_error_type(self) -> None:
        """base_error_type contrôle le routage dans LoggerErrorHandler."""
        class MonErreur(Exception):
            pass

        mock_logger = MagicMock()
        handler = LoggerErrorHandler(mock_logger, base_error_type=MonErreur)

        handler.handle(MonErreur("connue"))
        mock_logger.log_error.assert_called_with("MonErreur: connue")

        mock_logger.reset_mock()
        handler.handle(RuntimeError("inconnue"))
        mock_logger.log_error.assert_called_with(
            "Erreur inattendue: RuntimeError: inconnue"
        )


if __name__ == '__main__':
    unittest.main()
