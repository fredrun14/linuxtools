"""Tests pour la chaîne de diffusion NotifierChain."""

import pytest

from linuxtools.logging.base import Logger
from linuxtools.notification import (
    ExecutionReport,
    Notification,
    NotificationSendError,
    Notifier,
    NotifierChain,
)


@pytest.fixture
def notif() -> Notification:
    """Notification minimale partagée entre les tests."""
    return Notification(title="Test", message="Corps")


class RecordingNotifier(Notifier):
    """Notifier factice enregistrant les notifications reçues."""

    def __init__(self, fail: bool = False) -> None:
        """Initialise avec un mode d'échec optionnel."""
        self.fail = fail
        self.received: list[Notification] = []

    def send(self, notification: Notification) -> None:
        """Enregistre ou échoue selon le mode configuré."""
        if self.fail:
            raise NotificationSendError("canal indisponible")
        self.received.append(notification)


class RecordingLogger(Logger):
    """Logger factice accumulant les messages."""

    def __init__(self) -> None:
        """Initialise les listes de messages."""
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def log_info(self, message: str) -> None:
        """Accumule un message d'information."""
        self.infos.append(message)

    def log_warning(self, message: str) -> None:
        """Accumule un avertissement."""
        self.warnings.append(message)

    def log_error(self, message: str) -> None:
        """Accumule une erreur."""
        self.errors.append(message)


class TestNotifierChain:
    """Tests pour NotifierChain."""

    def test_chaine_vide_retourne_false(self, notif):
        """Vérifie qu'une chaîne vide n'a rien livré."""
        chain = NotifierChain()
        assert chain.send(notif) is False

    def test_diffuse_a_tous_les_notifiers(self, notif):
        """Vérifie la diffusion à tous les canaux."""
        first = RecordingNotifier()
        second = RecordingNotifier()
        chain = NotifierChain()
        chain.add_notifier(first)
        chain.add_notifier(second)
        assert chain.send(notif) is True
        assert first.received == [notif]
        assert second.received == [notif]

    def test_continue_apres_echec(self, notif):
        """Vérifie le best-effort quand un canal échoue."""
        logger = RecordingLogger()
        failing = RecordingNotifier(fail=True)
        working = RecordingNotifier()
        chain = NotifierChain(logger=logger)
        chain.add_notifier(failing)
        chain.add_notifier(working)
        assert chain.send(notif) is True
        assert working.received == [notif]
        assert any(
            "RecordingNotifier" in msg for msg in logger.errors
        )

    def test_retourne_false_si_tous_echouent(self, notif):
        """Vérifie le retour False si aucun canal ne réussit."""
        chain = NotifierChain()
        chain.add_notifier(RecordingNotifier(fail=True))
        chain.add_notifier(RecordingNotifier(fail=True))
        assert chain.send(notif) is False

    def test_send_report_convertit_le_rapport(self):
        """Vérifie la conversion et la diffusion d'un rapport."""
        report = ExecutionReport(script_name="backup")
        report.add_step("rsync", success=True)
        report.finish()
        recorder = RecordingNotifier()
        chain = NotifierChain()
        chain.add_notifier(recorder)
        assert chain.send_report(report) is True
        sent = recorder.received[0]
        assert sent.title == "✓ backup — succès"
        assert "rsync" in sent.message
