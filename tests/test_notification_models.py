"""Tests pour les modèles du module notification."""

import pytest

from linuxtools.notification import (
    ExecutionReport,
    Notification,
    Urgency,
)


class TestNotification:
    """Tests pour la dataclass Notification."""

    def test_creation_minimale(self):
        """Vérifie la création avec titre et message."""
        notif = Notification(title="Titre", message="Corps")
        assert notif.urgency is Urgency.NORMAL
        assert notif.icon == ""

    def test_message_multiligne_autorise(self):
        """Vérifie qu'un message multiligne est accepté."""
        notif = Notification(title="Titre", message="l1\nl2")
        assert "\n" in notif.message

    def test_raises_on_empty_title(self):
        """Vérifie l'erreur si le titre est vide."""
        with pytest.raises(ValueError, match="title est requis"):
            Notification(title="", message="Corps")

    def test_raises_on_empty_message(self):
        """Vérifie l'erreur si le message est vide."""
        with pytest.raises(ValueError, match="message est requis"):
            Notification(title="Titre", message="")

    def test_raises_on_multiline_title(self):
        """Vérifie l'erreur si le titre est multiligne."""
        with pytest.raises(ValueError, match="saut de ligne"):
            Notification(title="a\nb", message="Corps")

    def test_is_frozen(self):
        """Vérifie l'immutabilité de la notification."""
        notif = Notification(title="Titre", message="Corps")
        with pytest.raises(AttributeError):
            notif.title = "Autre"


class TestExecutionReport:
    """Tests pour la dataclass ExecutionReport."""

    def test_raises_on_empty_script_name(self):
        """Vérifie l'erreur si script_name est vide."""
        with pytest.raises(ValueError, match="script_name est requis"):
            ExecutionReport(script_name="")

    def test_success_sans_etape(self):
        """Vérifie qu'un rapport vide est un succès."""
        report = ExecutionReport(script_name="demo")
        assert report.success is True

    def test_success_toutes_etapes_ok(self):
        """Vérifie le succès quand toutes les étapes réussissent."""
        report = ExecutionReport(script_name="demo")
        report.add_step("a", success=True)
        report.add_step("b", success=True)
        assert report.success is True

    def test_echec_si_une_etape_echoue(self):
        """Vérifie l'échec dès qu'une étape échoue."""
        report = ExecutionReport(script_name="demo")
        report.add_step("a", success=True)
        report.add_step("b", success=False, message="disque plein")
        assert report.success is False

    def test_echec_si_erreur_globale(self):
        """Vérifie l'échec en présence d'une erreur hors étape."""
        report = ExecutionReport(script_name="demo")
        report.add_error("config introuvable")
        assert report.success is False

    def test_duration_zero_si_non_termine(self):
        """Vérifie la durée nulle avant finish()."""
        report = ExecutionReport(script_name="demo")
        assert report.duration == 0.0

    def test_finish_renseigne_finished_at(self):
        """Vérifie que finish() clôture le rapport."""
        report = ExecutionReport(script_name="demo")
        report.finish()
        assert report.finished_at is not None
        assert report.duration >= 0.0


class TestExecutionReportStep:
    """Tests pour le context manager ExecutionReport.step()."""

    def test_etape_reussie(self):
        """Vérifie l'enregistrement d'une étape sans exception."""
        report = ExecutionReport(script_name="demo")
        with report.step("rsync"):
            pass
        assert report.steps[0].success is True
        assert report.steps[0].name == "rsync"

    def test_etape_en_echec_absorbe_exception(self):
        """Vérifie l'absorption d'exception par défaut."""
        report = ExecutionReport(script_name="demo")
        with report.step("rsync"):
            raise RuntimeError("échec rsync")
        assert report.steps[0].success is False
        assert "échec rsync" in report.steps[0].message

    def test_etape_en_echec_reraise(self):
        """Vérifie la propagation avec reraise=True."""
        report = ExecutionReport(script_name="demo")
        with pytest.raises(RuntimeError):
            with report.step("rsync", reraise=True):
                raise RuntimeError("échec rsync")
        assert report.steps[0].success is False


class TestExecutionReportSummary:
    """Tests pour format_summary() et to_notification()."""

    def test_summary_succes(self):
        """Vérifie le contenu du résumé en succès."""
        report = ExecutionReport(
            script_name="backup", hostname="nas"
        )
        report.add_step("rsync", success=True, duration=1.5)
        report.finish()
        summary = report.format_summary()
        assert "✓ Succès — backup sur nas" in summary
        assert "✓ rsync" in summary

    def test_summary_echec_avec_erreurs(self):
        """Vérifie le contenu du résumé en échec."""
        report = ExecutionReport(script_name="backup")
        report.add_step("rsync", success=False, message="timeout")
        report.add_error("montage NFS absent")
        summary = report.format_summary()
        assert "✗ Échec" in summary
        assert "timeout" in summary
        assert "! montage NFS absent" in summary

    def test_to_notification_succes(self):
        """Vérifie la notification produite en succès."""
        report = ExecutionReport(script_name="backup")
        report.finish()
        notif = report.to_notification()
        assert notif.title == "✓ backup — succès"
        assert notif.urgency is Urgency.NORMAL
        assert notif.icon == "emblem-default"

    def test_to_notification_echec(self):
        """Vérifie la notification produite en échec."""
        report = ExecutionReport(script_name="backup")
        report.add_error("boom")
        notif = report.to_notification()
        assert notif.title == "✗ backup — échec"
        assert notif.urgency is Urgency.CRITICAL
        assert notif.icon == "dialog-error"
