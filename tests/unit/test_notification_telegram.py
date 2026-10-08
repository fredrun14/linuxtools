"""Tests pour TelegramNotifier (canal Telegram multi-destinataires)."""

import http.client
import io
import json
import socket
import traceback
import urllib.error
import urllib.request
from email.message import Message
from typing import Any, Literal

import pytest

from linuxtools.logging.base import Logger
from linuxtools.notification import (
    Notification,
    NotificationSendError,
    Notifier,
    NotifierChain,
    TelegramNotifier,
)

TOKEN = "123456:SECRET-TOKEN_abc"


class FakeResponse:
    """Réponse HTTP factice (context manager à statut configurable)."""

    def __init__(self, status: int = 200) -> None:
        """Initialise avec le statut à retourner."""
        self.status = status

    def __enter__(self) -> "FakeResponse":
        """Retourne la réponse pour usage en context manager."""
        return self

    def __exit__(self, *args: object) -> Literal[False]:
        """Ne fait rien à la sortie du contexte."""
        return False


class RecordingOpener:
    """Opener factice qui enregistre les requêtes et répond 200."""

    def __init__(self) -> None:
        """Initialise les enregistrements vides."""
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float | None] = []

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: float | None = None,
    ) -> FakeResponse:
        """Enregistre l'appel et retourne une réponse 200."""
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeResponse(status=200)

    def bodies(self) -> list[dict[str, Any]]:
        """Retourne les corps JSON décodés des requêtes reçues."""
        decoded: list[dict[str, Any]] = []
        for request in self.requests:
            assert isinstance(request.data, bytes)
            decoded.append(json.loads(request.data.decode("utf-8")))
        return decoded


class TestTelegramNotifierConstruction:
    """Validation du constructeur (tranche T1)."""

    @pytest.mark.parametrize(
        "token",
        ["", "abc", "a b", "12:ab/cd", "12:ab?x", "12:ab\n", "SECRET-TOKEN"],
    )
    def test_token_invalide_leve_value_error_sans_la_valeur(
        self, token: str
    ) -> None:
        """Un token mal formé est refusé sans être cité."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(token=token, recipients={"alice": 1})
        assert str(info.value) == "token invalide"

    def test_destinataires_vides_leve_value_error(self) -> None:
        """Un mapping vide est refusé."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(token=TOKEN, recipients={})
        assert str(info.value) == "au moins un destinataire est requis"

    @pytest.mark.parametrize(
        "label", ["a\nb", "a b", "", "x" * 33, "ok\n", "é"]
    )
    def test_libelle_invalide_leve_value_error_sans_la_valeur(
        self, label: str
    ) -> None:
        """Un libellé hors [A-Za-z0-9_-]{1,32} est refusé."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(token=TOKEN, recipients={label: 1})
        assert str(info.value) == "libellé invalide"

    def test_libelle_valide_accepte(self) -> None:
        """Un libellé conforme est accepté (32 caractères compris)."""
        TelegramNotifier(token=TOKEN, recipients={"ok_1-X": 1, "y" * 32: 2})

    @pytest.mark.parametrize("chat_id", [True, 0, "123", 1.5, None])
    def test_chat_id_invalide_cite_le_libelle_pas_la_valeur(
        self, chat_id: object
    ) -> None:
        """Un chat_id non entier, booléen ou nul est refusé."""
        recipients: dict[str, Any] = {"alice": chat_id}
        with pytest.raises(ValueError) as info:
            TelegramNotifier(token=TOKEN, recipients=recipients)
        assert str(info.value) == "chat_id invalide pour alice"

    def test_chat_id_en_double_leve_value_error(self) -> None:
        """Deux libellés ne peuvent pas partager un chat_id."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(
                token=TOKEN, recipients={"alice": 4242, "bob": 4242}
            )
        assert str(info.value) == "chat_id en double"

    def test_chat_id_negatif_accepte(self) -> None:
        """Un identifiant de groupe (négatif) est un entier valide."""
        TelegramNotifier(token=TOKEN, recipients={"groupe": -100123})

    @pytest.mark.parametrize("timeout", [0, -1, 0.0, float("nan")])
    def test_timeout_non_positif_leve_value_error(
        self, timeout: float
    ) -> None:
        """Un timeout nul, négatif ou NaN est refusé."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(
                token=TOKEN, recipients={"alice": 1}, timeout=timeout
            )
        assert str(info.value) == "timeout doit être strictement positif"

    def test_repr_ne_contient_ni_token_ni_chat_id(self) -> None:
        """repr() ne divulgue rien (garde-fou anti-dataclass)."""
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 987654321}
        )
        text = repr(notifier)
        assert "SECRET-TOKEN" not in text
        assert "987654321" not in text
        assert text.startswith("<linuxtools.notification.telegram.Telegram")


class TestFormatage:
    """Mise en forme du texte envoyé (tranche T2)."""

    def test_titre_seul_par_defaut(self) -> None:
        """Par défaut, seul le titre part chez Telegram (Q-02)."""
        opener = RecordingOpener()
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 1}, opener=opener
        )
        notifier.send(
            Notification(title="✗ backup-nas — échec", message="DETAIL")
        )
        assert opener.bodies()[0]["text"] == "✗ backup-nas — échec"

    def test_include_message_joint_titre_et_message(self) -> None:
        """Avec include_message=True : titre, ligne vide, message."""
        opener = RecordingOpener()
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": 1},
            include_message=True,
            opener=opener,
        )
        notifier.send(Notification(title="Titre", message="Ligne 1\nL2"))
        assert opener.bodies()[0]["text"] == "Titre\n\nLigne 1\nL2"

    def _text_envoye(self, title: str) -> str:
        """Envoie un titre et retourne le texte reçu par l'opener."""
        opener = RecordingOpener()
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 1}, opener=opener
        )
        notifier.send(Notification(title=title, message="M"))
        text = opener.bodies()[0]["text"]
        assert isinstance(text, str)
        return text

    def test_texte_de_4096_unites_exactement_inchange(self) -> None:
        """Un texte de 4096 unités UTF-16 pile n'est pas tronqué."""
        assert self._text_envoye("a" * 4096) == "a" * 4096

    def test_texte_de_4097_unites_tronque_avec_ellipse(self) -> None:
        """Au-delà de 4096 unités : 4095 caractères puis « … »."""
        assert self._text_envoye("a" * 4097) == "a" * 4095 + "…"

    def test_emoji_a_la_frontiere_non_coupe_est_conserve(self) -> None:
        """Un emoji (2 unités) qui tient dans le budget est gardé."""
        title = "a" * 4093 + "😀" + "bbb"
        assert self._text_envoye(title) == "a" * 4093 + "😀…"

    def test_emoji_a_la_frontiere_qui_deborde_est_retire(self) -> None:
        """Un emoji qui ferait dépasser le budget est retiré entier."""
        title = "a" * 4094 + "😀" + "bbb"
        assert self._text_envoye(title) == "a" * 4094 + "…"

    def test_emojis_comptes_en_unites_utf16_pas_en_points(self) -> None:
        """2049 emojis = 4098 unités : tronqué à 2047 emojis + « … »."""
        assert self._text_envoye("😀" * 2049) == "😀" * 2047 + "…"


class RecordingLogger(Logger):
    """Logger factice qui conserve tous les messages reçus."""

    def __init__(self) -> None:
        """Initialise les listes de messages."""
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def log_info(self, message: str) -> None:
        """Enregistre un message d'information."""
        self.infos.append(message)

    def log_warning(self, message: str) -> None:
        """Enregistre un avertissement."""
        self.warnings.append(message)

    def log_error(self, message: str) -> None:
        """Enregistre une erreur."""
        self.errors.append(message)

    def all_messages(self) -> list[str]:
        """Retourne tous les messages, tous niveaux confondus."""
        return self.infos + self.warnings + self.errors


class TestSendNominal:
    """Envoi nominal vers tous les destinataires (tranche T3)."""

    def test_requete_url_methode_entetes_et_corps(self) -> None:
        """Une requête par destinataire, au format de l'API Telegram."""
        opener = RecordingOpener()
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 4242}, opener=opener
        )
        notifier.send(Notification(title="Titre", message="M"))
        request = opener.requests[0]
        assert request.full_url == (
            "https://api.telegram.org/bot123456:SECRET-TOKEN_abc/sendMessage"
        )
        assert request.get_method() == "POST"
        assert request.get_header("Content-type") == "application/json"
        assert opener.bodies()[0] == {
            "chat_id": 4242,
            "text": "Titre",
            "link_preview_options": {"is_disabled": True},
        }

    def test_ordre_du_mapping_et_timeout_transmis(self) -> None:
        """Un envoi par destinataire, dans l'ordre, avec le timeout."""
        opener = RecordingOpener()
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"zoe": 30, "alice": 10, "bob": 20},
            timeout=7.5,
            opener=opener,
        )
        notifier.send(Notification(title="T", message="M"))
        assert [b["chat_id"] for b in opener.bodies()] == [30, 10, 20]
        assert opener.timeouts == [7.5, 7.5, 7.5]

    def test_succes_journalise_par_libelle_sans_chat_id(self) -> None:
        """Chaque succès est loggé avec le libellé, jamais le chat_id."""
        logger = RecordingLogger()
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": 987654321, "bob": 123123123},
            opener=RecordingOpener(),
            logger=logger,
        )
        notifier.send(Notification(title="T", message="M"))
        assert logger.infos == [
            "Telegram : envoyé à alice",
            "Telegram : envoyé à bob",
        ]
        assert logger.warnings == []


class ScriptedOpener:
    """Opener factice dont la réponse dépend du chat_id destinataire."""

    def __init__(self, outcomes: dict[int, int | BaseException]) -> None:
        """Initialise avec un statut ou une exception par chat_id."""
        self._outcomes = outcomes
        self.chat_ids: list[int] = []

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: float | None = None,
    ) -> FakeResponse:
        """Lève l'exception prévue ou retourne le statut prévu."""
        assert isinstance(request.data, bytes)
        chat_id = json.loads(request.data.decode("utf-8"))["chat_id"]
        self.chat_ids.append(chat_id)
        outcome = self._outcomes.get(chat_id, 200)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(status=outcome)


def make_http_error(
    code: int, fp: io.BytesIO | None = None
) -> urllib.error.HTTPError:
    """Construit une HTTPError dont l'URL contient le token."""
    return urllib.error.HTTPError(
        "https://api.telegram.org/bot123456:SECRET-TOKEN_abc/sendMessage",
        code,
        "msg SECRET-TOKEN",
        Message(),
        fp,
    )


class TestIsolation:
    """Un échec n'empêche pas les autres envois (tranche T4)."""

    def test_http_403_sur_alice_bob_quand_meme_servi(self) -> None:
        """403 pour alice : bob reçoit, une erreur agrégée est levée."""
        opener = ScriptedOpener({10: make_http_error(403)})
        logger = RecordingLogger()
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": 10, "bob": 20},
            opener=opener,
            logger=logger,
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == (
            "Échec Telegram : alice (bot bloqué ou jamais démarré par le "
            "destinataire)"
        )
        assert opener.chat_ids == [10, 20]
        assert logger.infos == ["Telegram : envoyé à bob"]
        assert logger.warnings == [
            "Telegram : échec pour alice (bot bloqué ou jamais démarré "
            "par le destinataire)"
        ]

    @pytest.mark.parametrize(
        ("code", "reason"),
        [
            (
                400,
                "requête refusée (chat introuvable ou bot jamais démarré ?)",
            ),
            (401, "token invalide"),
            (403, "bot bloqué ou jamais démarré par le destinataire"),
            (404, "token ou méthode inconnus"),
            (429, "trop de messages (limite de débit)"),
            (500, "HTTP 500"),
        ],
    )
    def test_raison_fixe_par_code_http_sans_nouvel_essai(
        self, code: int, reason: str
    ) -> None:
        """Chaque code HTTP donne sa raison fixe, en un seul appel."""
        opener = ScriptedOpener({10: make_http_error(code)})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == f"Échec Telegram : alice ({reason})"
        assert opener.chat_ids == [10]

    def test_http_error_est_fermee(self) -> None:
        """La réponse d'erreur est fermée (pas de fuite de socket)."""
        body = io.BytesIO(b'{"description": "SECRET-TOKEN"}')
        opener = ScriptedOpener({10: make_http_error(403, fp=body)})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(NotificationSendError):
            notifier.send(Notification(title="T", message="M"))
        assert body.closed

    def test_url_error_donne_le_type_de_la_cause(self) -> None:
        """URLError : seul le nom du type de la cause est repris."""
        error = urllib.error.URLError(socket.gaierror("SECRET-TOKEN"))
        opener = ScriptedOpener({10: error})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == (
            "Échec Telegram : alice (serveur injoignable (gaierror))"
        )

    @pytest.mark.parametrize(
        "error",
        [
            http.client.InvalidURL("/bot123456:SECRET-TOKEN_abc/x"),
            http.client.BadStatusLine("SECRET-TOKEN"),
            http.client.RemoteDisconnected("SECRET-TOKEN"),
        ],
    )
    def test_reponse_malformee_donne_reponse_invalide(
        self, error: http.client.HTTPException
    ) -> None:
        """Les erreurs du protocole HTTP donnent « réponse invalide »."""
        opener = ScriptedOpener({10: error})
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": 10, "bob": 20},
            opener=opener,
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == "Échec Telegram : alice (réponse invalide)"
        assert opener.chat_ids == [10, 20]

    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (TimeoutError("SECRET-TOKEN"), "erreur réseau (TimeoutError)"),
            (
                ConnectionRefusedError("SECRET-TOKEN"),
                "erreur réseau (ConnectionRefusedError)",
            ),
        ],
    )
    def test_os_error_donne_le_nom_du_type(
        self, error: OSError, reason: str
    ) -> None:
        """Les erreurs système ne donnent que le nom de leur type."""
        opener = ScriptedOpener({10: error})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == f"Échec Telegram : alice ({reason})"

    def test_statut_inattendu_est_un_echec(self) -> None:
        """Un statut 200 est requis : 202 est signalé."""
        opener = ScriptedOpener({10: 202})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == (
            "Échec Telegram : alice (réponse inattendue (HTTP 202))"
        )

    def test_plusieurs_echecs_agreges_dans_l_ordre_du_mapping(self) -> None:
        """Les échecs sont listés dans une seule erreur, bob réussit."""
        opener = ScriptedOpener(
            {10: make_http_error(401), 30: make_http_error(404)}
        )
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": 10, "bob": 20, "carol": 30},
            opener=opener,
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        assert str(info.value) == (
            "Échec Telegram : alice (token invalide), "
            "carol (token ou méthode inconnus)"
        )
        assert opener.chat_ids == [10, 20, 30]

    def test_exception_inattendue_est_propagee(self) -> None:
        """Un bug (ici RuntimeError) n'est pas masqué en échec réseau."""
        opener = ScriptedOpener({10: RuntimeError("bug")})
        notifier = TelegramNotifier(
            token=TOKEN, recipients={"alice": 10}, opener=opener
        )
        with pytest.raises(RuntimeError):
            notifier.send(Notification(title="T", message="M"))


SENTINELLE_CHAT_ID = 987654321


def _cas_d_echec() -> list[tuple[str, BaseException | int]]:
    """Retourne chaque cas d'échec, avec des sentinelles dans l'erreur."""
    return [
        ("http-400", make_http_error(400)),
        ("http-401", make_http_error(401)),
        ("http-403", make_http_error(403)),
        ("http-404", make_http_error(404)),
        ("http-429", make_http_error(429)),
        ("http-500", make_http_error(500)),
        (
            "url-error",
            urllib.error.URLError(socket.gaierror("SECRET-TOKEN")),
        ),
        (
            "invalid-url",
            http.client.InvalidURL("/bot123456:SECRET-TOKEN_abc/x"),
        ),
        ("bad-status", http.client.BadStatusLine("SECRET-TOKEN")),
        ("remote-disc", http.client.RemoteDisconnected("SECRET-TOKEN")),
        ("timeout", TimeoutError("SECRET-TOKEN")),
        ("statut-202", 202),
    ]


class TestAntiFuite:
    """Le token et le chat_id ne fuient jamais (tranche T5)."""

    @pytest.mark.parametrize(
        "outcome",
        [cas[1] for cas in _cas_d_echec()],
        ids=[cas[0] for cas in _cas_d_echec()],
    )
    def test_aucune_sentinelle_nulle_part(
        self, outcome: BaseException | int
    ) -> None:
        """Aucune sentinelle dans l'erreur, sa trace, les logs, repr."""
        logger = RecordingLogger()
        notifier = TelegramNotifier(
            token=TOKEN,
            recipients={"alice": SENTINELLE_CHAT_ID},
            opener=ScriptedOpener({SENTINELLE_CHAT_ID: outcome}),
            logger=logger,
        )
        with pytest.raises(NotificationSendError) as info:
            notifier.send(Notification(title="T", message="M"))
        exc = info.value
        assert exc.__cause__ is None
        assert exc.__context__ is None
        surfaces = [
            str(exc),
            repr(exc),
            "".join(traceback.format_exception(exc)),
            repr(notifier),
            *logger.all_messages(),
        ]
        for surface in surfaces:
            assert "SECRET-TOKEN" not in surface
            assert "123456:" not in surface
            assert str(SENTINELLE_CHAT_ID) not in surface

    @pytest.mark.parametrize(
        ("token", "recipients"),
        [
            ("SECRET-TOKEN", {"alice": 1}),
            (TOKEN, {"SECRET-TOKEN x": 1}),
            (TOKEN, {"alice": "SECRET-TOKEN"}),
            (TOKEN, {"alice": 5, "bob": 5}),
        ],
    )
    def test_value_error_du_constructeur_sans_sentinelle(
        self, token: str, recipients: dict[str, Any]
    ) -> None:
        """Les ValueError du constructeur ne citent pas la valeur."""
        with pytest.raises(ValueError) as info:
            TelegramNotifier(token=token, recipients=recipients)
        assert "SECRET-TOKEN" not in str(info.value)


class FakeNotifier(Notifier):
    """Notifier factice : réussit ou échoue, et mémorise ses envois."""

    def __init__(self, fails: bool = False) -> None:
        """Initialise le comportement du faux canal."""
        self._fails = fails
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        """Mémorise l'envoi ou lève NotificationSendError."""
        if self._fails:
            raise NotificationSendError("Gotify indisponible")
        self.sent.append(notification)


class TestDansNotifierChain:
    """Intégration avec NotifierChain (tranche T6)."""

    def test_gotify_en_panne_telegram_livre_le_titre(self) -> None:
        """Gotify en échec : Telegram envoie, la chaîne renvoie True."""
        opener = RecordingOpener()
        chain = NotifierChain()
        chain.add_notifier(FakeNotifier(fails=True))
        chain.add_notifier(
            TelegramNotifier(
                token=TOKEN, recipients={"alice": 10}, opener=opener
            )
        )
        delivered = chain.send(
            Notification(title="✗ backup-nas — échec", message="DETAIL")
        )
        assert delivered is True
        assert [b["text"] for b in opener.bodies()] == ["✗ backup-nas — échec"]

    def test_echec_partiel_log_de_la_chaine_sans_sentinelle(self) -> None:
        """Échec d'alice : log exact, aucune fuite, Gotify continue."""
        logger = RecordingLogger()
        gotify = FakeNotifier()
        chain = NotifierChain(logger=logger)
        chain.add_notifier(
            TelegramNotifier(
                token=TOKEN,
                recipients={"alice": SENTINELLE_CHAT_ID, "bob": 20},
                opener=ScriptedOpener(
                    {SENTINELLE_CHAT_ID: make_http_error(403)}
                ),
            )
        )
        chain.add_notifier(gotify)
        delivered = chain.send(Notification(title="T", message="M"))
        assert delivered is True
        assert len(gotify.sent) == 1
        assert logger.errors == [
            "Échec de l'envoi via TelegramNotifier : Échec Telegram : "
            "alice (bot bloqué ou jamais démarré par le destinataire)"
        ]
        for message in logger.all_messages():
            assert "SECRET-TOKEN" not in message
            assert str(SENTINELLE_CHAT_ID) not in message
