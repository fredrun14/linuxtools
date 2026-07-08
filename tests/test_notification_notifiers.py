"""Tests pour les notifiers concrets du module notification."""

import smtplib
import socket
import urllib.error

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.notification import (
    DesktopNotifier,
    GotifyNotifier,
    JournaldNotifier,
    Notification,
    NotificationSendError,
    SmtpEmailNotifier,
    Urgency,
)


@pytest.fixture
def notif() -> Notification:
    """Notification minimale partagée entre les tests."""
    return Notification(title="Test", message="Corps")


class FakeExecutor(CommandExecutor):
    """Exécuteur factice enregistrant les commandes reçues."""

    def __init__(self, results: list[CommandResult]) -> None:
        """Initialise avec la file de résultats à retourner."""
        self.calls: list[list[str]] = []
        self._results = list(results)

    def _next(self, command: list[str]) -> CommandResult:
        """Enregistre l'appel et retourne le résultat suivant."""
        self.calls.append(command)
        return self._results.pop(0)

    def run(self, command, env=None, cwd=None, timeout=None):
        """Simule l'exécution d'une commande."""
        return self._next(command)

    def run_streaming(
        self, command, env=None, cwd=None, timeout=None,
        merge_stderr=False,
    ):
        """Simule l'exécution en streaming."""
        return self._next(command)


def _result(
    return_code: int = 0, stdout: str = "", stderr: str = ""
) -> CommandResult:
    """Fabrique un CommandResult de test."""
    return CommandResult(
        command=("fake",),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        success=return_code == 0,
        duration=0.0,
    )


class TestDesktopNotifier:
    """Tests pour DesktopNotifier."""

    def test_raises_on_empty_app_name(self):
        """Vérifie l'erreur si app_name est vide."""
        with pytest.raises(ValueError, match="app_name est requis"):
            DesktopNotifier(app_name="")

    def test_session_courante_construit_notify_send(self, notif):
        """Vérifie la commande notify-send en session courante."""
        executor = FakeExecutor([_result()])
        notifier = DesktopNotifier(
            app_name="backup", executor=executor
        )
        notifier.send(notif)
        command = executor.calls[0]
        assert command[0] == "notify-send"
        assert "-u" in command and "normal" in command
        assert "-a" in command and "backup" in command
        assert command[-2:] == ["Test", "Corps"]

    def test_icone_ajoutee_si_presente(self):
        """Vérifie l'option -i quand une icône est fournie."""
        executor = FakeExecutor([_result()])
        notifier = DesktopNotifier(
            app_name="backup", executor=executor
        )
        notifier.send(
            Notification(
                title="T", message="M", icon="dialog-error"
            )
        )
        command = executor.calls[0]
        assert "-i" in command and "dialog-error" in command

    def test_raises_si_notify_send_echoue(self, notif):
        """Vérifie NotificationSendError sur code non nul."""
        executor = FakeExecutor([_result(return_code=1, stderr="ko")])
        notifier = DesktopNotifier(
            app_name="backup", executor=executor
        )
        with pytest.raises(NotificationSendError, match="notify-send"):
            notifier.send(notif)

    def test_all_users_diffuse_via_runuser(self, notif, monkeypatch):
        """Vérifie la diffusion loginctl + runuser en mode all_users."""
        executor = FakeExecutor(
            [
                _result(stdout="1000 fred\n1001 alice\n"),
                _result(),
                _result(),
            ]
        )
        notifier = DesktopNotifier(
            app_name="backup", all_users=True, executor=executor
        )
        monkeypatch.setattr(
            "linuxtools.notification.desktop.Path.is_socket",
            lambda self: True,
        )
        notifier.send(notif)
        assert executor.calls[0][0] == "loginctl"
        assert executor.calls[1][0] == "runuser"
        assert executor.calls[1][2] == "fred"
        assert executor.calls[2][2] == "alice"

    def test_all_users_sans_session_leve_erreur(
        self, notif, monkeypatch
    ):
        """Vérifie l'erreur si aucun bus D-Bus n'est disponible."""
        executor = FakeExecutor(
            [_result(stdout="1000 fred\n")]
        )
        notifier = DesktopNotifier(
            app_name="backup", all_users=True, executor=executor
        )
        monkeypatch.setattr(
            "linuxtools.notification.desktop.Path.is_socket",
            lambda self: False,
        )
        with pytest.raises(
            NotificationSendError, match="Aucun utilisateur"
        ):
            notifier.send(notif)


class FakeHttpResponse:
    """Réponse HTTP factice pour GotifyNotifier."""

    def __init__(self, status: int = 200) -> None:
        """Initialise avec le statut à retourner."""
        self.status = status

    def __enter__(self):
        """Retourne la réponse pour usage en context manager."""
        return self

    def __exit__(self, *args):
        """Ne fait rien à la sortie du contexte."""
        return False


class TestGotifyNotifier:
    """Tests pour GotifyNotifier."""

    def test_raises_on_bad_url(self):
        """Vérifie l'erreur si l'URL n'est pas http(s)."""
        with pytest.raises(ValueError, match="http"):
            GotifyNotifier(base_url="ftp://nas", token="t")

    def test_raises_on_empty_token(self):
        """Vérifie l'erreur si le token est vide."""
        with pytest.raises(ValueError, match="token est requis"):
            GotifyNotifier(base_url="https://nas", token="")

    def test_envoie_requete_message(self, notif):
        """Vérifie l'URL, le token et la priorité envoyés."""
        requests = []

        def opener(request, timeout=None):
            requests.append(request)
            return FakeHttpResponse(status=200)

        notifier = GotifyNotifier(
            base_url="https://gotify.lan/",
            token="secret",
            opener=opener,
        )
        notifier.send(notif)
        request = requests[0]
        assert request.full_url == "https://gotify.lan/message"
        assert request.get_header("X-gotify-key") == "secret"
        assert b'"priority": 5' in request.data

    def test_priorite_critical(self):
        """Vérifie la priorité Gotify pour une urgence critique."""
        requests = []

        def opener(request, timeout=None):
            requests.append(request)
            return FakeHttpResponse(status=200)

        notifier = GotifyNotifier(
            base_url="https://gotify.lan",
            token="secret",
            opener=opener,
        )
        notifier.send(
            Notification(
                title="T", message="M", urgency=Urgency.CRITICAL
            )
        )
        assert b'"priority": 8' in requests[0].data

    def test_raises_sur_erreur_http(self, notif):
        """Vérifie NotificationSendError sur HTTPError."""

        def opener(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", {}, None
            )

        notifier = GotifyNotifier(
            base_url="https://gotify.lan",
            token="secret",
            opener=opener,
        )
        with pytest.raises(NotificationSendError, match="401"):
            notifier.send(notif)

    def test_raises_sur_serveur_injoignable(self, notif):
        """Vérifie NotificationSendError sur URLError."""

        def opener(request, timeout=None):
            raise urllib.error.URLError("refused")

        notifier = GotifyNotifier(
            base_url="https://gotify.lan",
            token="secret",
            opener=opener,
        )
        with pytest.raises(
            NotificationSendError, match="injoignable"
        ):
            notifier.send(notif)


class FakeSmtp:
    """Client SMTP factice enregistrant les appels."""

    instances: list["FakeSmtp"] = []

    def __init__(self, host, port, timeout=None) -> None:
        """Initialise et s'enregistre dans instances."""
        self.host = host
        self.port = port
        self.tls_started = False
        self.logged_in: tuple[str, str] | None = None
        self.sent: list = []
        self.fail_send = False
        FakeSmtp.instances.append(self)

    def __enter__(self):
        """Retourne le client pour usage en context manager."""
        return self

    def __exit__(self, *args):
        """Ne fait rien à la sortie du contexte."""
        return False

    def starttls(self, context=None):
        """Simule la négociation STARTTLS."""
        self.tls_started = True

    def login(self, username, password):
        """Simule l'authentification."""
        self.logged_in = (username, password)

    def send_message(self, message):
        """Simule l'envoi, avec échec optionnel."""
        if self.fail_send:
            raise smtplib.SMTPException("refusé")
        self.sent.append(message)


class TestSmtpEmailNotifier:
    """Tests pour SmtpEmailNotifier."""

    def setup_method(self):
        """Réinitialise les instances SMTP factices."""
        FakeSmtp.instances = []

    def test_raises_on_empty_recipients(self):
        """Vérifie l'erreur sans destinataire."""
        with pytest.raises(ValueError, match="destinataire"):
            SmtpEmailNotifier(
                host="smtp.lan", sender="a@b", recipients=[]
            )

    def test_envoi_avec_tls_et_login(self, notif):
        """Vérifie STARTTLS, login et contenu du message."""
        notifier = SmtpEmailNotifier(
            host="smtp.lan",
            sender="nas@lan",
            recipients=["fred@lan"],
            username="nas",
            password="pw",
            smtp_factory=FakeSmtp,
        )
        notifier.send(notif)
        smtp = FakeSmtp.instances[0]
        assert smtp.tls_started is True
        assert smtp.logged_in == ("nas", "pw")
        message = smtp.sent[0]
        assert message["Subject"] == "Test"
        assert message["From"] == "nas@lan"
        assert message["To"] == "fred@lan"

    def test_sans_tls_ni_login(self, notif):
        """Vérifie l'envoi sans TLS ni authentification."""
        notifier = SmtpEmailNotifier(
            host="smtp.lan",
            sender="nas@lan",
            recipients=["fred@lan"],
            use_tls=False,
            smtp_factory=FakeSmtp,
        )
        notifier.send(notif)
        smtp = FakeSmtp.instances[0]
        assert smtp.tls_started is False
        assert smtp.logged_in is None

    def test_raises_sur_echec_smtp(self, notif):
        """Vérifie NotificationSendError sur SMTPException."""

        def factory(host, port, timeout=None):
            smtp = FakeSmtp(host, port, timeout=timeout)
            smtp.fail_send = True
            return smtp

        notifier = SmtpEmailNotifier(
            host="smtp.lan",
            sender="nas@lan",
            recipients=["fred@lan"],
            use_tls=False,
            smtp_factory=factory,
        )
        with pytest.raises(NotificationSendError, match="smtp.lan"):
            notifier.send(notif)


class TestJournaldNotifier:
    """Tests pour JournaldNotifier."""

    def test_raises_on_empty_app_name(self):
        """Vérifie l'erreur si app_name est vide."""
        with pytest.raises(ValueError, match="app_name est requis"):
            JournaldNotifier(app_name="")

    def test_encode_field_simple(self):
        """Vérifie la sérialisation d'un champ monoligne."""
        data = JournaldNotifier._encode_field("PRIORITY", "5")
        assert data == b"PRIORITY=5\n"

    def test_encode_field_multiligne(self):
        """Vérifie la sérialisation binaire d'un champ multiligne."""
        data = JournaldNotifier._encode_field("MESSAGE", "a\nb")
        expected = (
            b"MESSAGE\n"
            + (3).to_bytes(8, "little")
            + b"a\nb\n"
        )
        assert data == expected

    def test_envoi_sur_socket(self, tmp_path):
        """Vérifie l'envoi du datagramme sur un socket réel."""
        socket_path = str(tmp_path / "journal.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(socket_path)
        try:
            notifier = JournaldNotifier(
                app_name="backup", socket_path=socket_path
            )
            notifier.send(
                Notification(
                    title="Titre",
                    message="l1\nl2",
                    urgency=Urgency.CRITICAL,
                )
            )
            payload = server.recv(4096)
        finally:
            server.close()
        assert b"PRIORITY=3\n" in payload
        assert b"SYSLOG_IDENTIFIER=backup\n" in payload
        assert b"NOTIFICATION_TITLE=Titre\n" in payload
        assert b"l1\nl2" in payload

    def test_raises_si_socket_absent(self, tmp_path):
        """Vérifie NotificationSendError si le socket n'existe pas."""
        notifier = JournaldNotifier(
            app_name="backup",
            socket_path=str(tmp_path / "absent.sock"),
        )
        with pytest.raises(NotificationSendError, match="journald"):
            notifier.send(Notification(title="T", message="M"))
