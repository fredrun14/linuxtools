"""Tests de comportement de ErrorContext, avec et sans logger."""

from unittest.mock import MagicMock

import pytest

from linuxtools.errors.context import ErrorContext
from linuxtools.errors.exceptions import RollbackError
from linuxtools.logging.base import Logger


def _echec() -> None:
    """Action de rollback qui échoue."""
    raise RuntimeError("boum")


def test_rollback_sans_logger_execute_les_actions_en_ordre_inverse() -> None:
    """Sans logger, les actions s'exécutent en LIFO sans erreur."""
    ordre: list[str] = []
    ctx = ErrorContext()
    ctx.add_rollback_action(lambda: ordre.append("a"), "a")
    ctx.add_rollback_action(lambda: ordre.append("b"), "b")

    ctx.execute_rollback()

    assert ordre == ["b", "a"]


def test_rollback_sans_logger_signale_les_actions_en_echec() -> None:
    """Sans logger, un échec d'action lève RollbackError après les autres."""
    ordre: list[str] = []
    ctx = ErrorContext()
    ctx.add_rollback_action(lambda: ordre.append("a"), "a")
    ctx.add_rollback_action(_echec, "b")

    with pytest.raises(RollbackError, match="1 action"):
        ctx.execute_rollback()

    assert ordre == ["a"]


def test_gestion_d_erreur_sans_logger_lance_le_rollback() -> None:
    """Sans logger, l'erreur déclenche le rollback et l'échec est absorbé."""
    appel = MagicMock()
    ctx = ErrorContext()
    ctx.add_rollback_action(appel, "a")
    ctx.add_rollback_action(_echec, "b")

    ctx.handle_error_with_rollback(ValueError("x"))

    appel.assert_called_once_with()


def test_gestion_d_erreur_sans_logger_ni_action_ne_fait_rien() -> None:
    """Sans logger ni action enregistrée, la gestion d'erreur est silencieuse."""
    ErrorContext().handle_error_with_rollback(ValueError("x"))


def test_gestion_d_erreur_avec_logger_sans_action_le_precise() -> None:
    """Avec logger et sans action, l'absence de rollback est tracée."""
    logger = MagicMock(spec=Logger)

    ErrorContext(logger).handle_error_with_rollback(ValueError("x"))

    logger.log_info.assert_called_once_with("Aucune action de rollback nécessaire.")
