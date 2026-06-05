"""Tests pour le module notification."""

import shlex

import pytest

from linux_python_utils.notification import NotificationConfig


class TestNotificationConfig:
    """Tests pour la dataclass NotificationConfig."""

    def test_creation_with_required_fields(self):
        """Vérifie la création avec les champs requis."""
        config = NotificationConfig(
            title="Test",
            message_success="Succès",
            message_failure="Échec"
        )
        assert config.title == "Test"
        assert config.message_success == "Succès"
        assert config.message_failure == "Échec"

    def test_default_icons(self):
        """Vérifie les icônes par défaut."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        assert config.icon_success == "software-update-available"
        assert config.icon_failure == "dialog-error"

    def test_custom_icons(self):
        """Vérifie les icônes personnalisées."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO",
            icon_success="emblem-ok",
            icon_failure="emblem-error"
        )
        assert config.icon_success == "emblem-ok"
        assert config.icon_failure == "emblem-error"

    def test_raises_on_empty_title(self):
        """Vérifie que __post_init__ lève une erreur si title est vide."""
        with pytest.raises(ValueError, match="title est requis"):
            NotificationConfig(
                title="",
                message_success="OK",
                message_failure="KO"
            )

    def test_raises_on_empty_message_success(self):
        """Vérifie l'erreur si message_success est vide."""
        with pytest.raises(ValueError, match="message_success est requis"):
            NotificationConfig(
                title="Test",
                message_success="",
                message_failure="KO"
            )

    def test_raises_on_empty_message_failure(self):
        """Vérifie l'erreur si message_failure est vide."""
        with pytest.raises(ValueError, match="message_failure est requis"):
            NotificationConfig(
                title="Test",
                message_success="OK",
                message_failure=""
            )

    def test_is_frozen(self):
        """Vérifie que la dataclass est immutable."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        with pytest.raises(AttributeError):
            config.title = "Nouveau titre"


class TestNotificationConfigToBashFunction:
    """Tests pour NotificationConfig.to_bash_function()."""

    def test_contains_function_definition(self):
        """Vérifie la présence de la définition de fonction."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        result = config.to_bash_function()
        assert "send_notification()" in result

    def test_contains_local_variables(self):
        """Vérifie la présence des variables locales."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        result = config.to_bash_function()
        assert 'local title="$1"' in result
        assert 'local message="$2"' in result
        assert 'local icon="$3"' in result

    def test_contains_loginctl_command(self):
        """Vérifie la présence de loginctl pour lister les utilisateurs."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        result = config.to_bash_function()
        assert "loginctl list-users" in result

    def test_contains_notify_send(self):
        """Vérifie la présence de notify-send."""
        config = NotificationConfig(
            title="Test",
            message_success="OK",
            message_failure="KO"
        )
        result = config.to_bash_function()
        assert "notify-send" in result


class TestNotificationConfigToBashCalls:
    """Tests pour les méthodes to_bash_call_*()."""

    def test_to_bash_call_success(self):
        """Vérifie la génération de l'appel pour le succès."""
        config = NotificationConfig(
            title="Flatpak",
            message_success="Mise à jour OK",
            message_failure="Échec",
            icon_success="emblem-ok"
        )
        result = config.to_bash_call_success()
        assert "send_notification" in result
        assert "Flatpak" in result
        assert "Mise à jour OK" in result
        assert "emblem-ok" in result

    def test_to_bash_call_failure(self):
        """Vérifie la génération de l'appel pour l'échec."""
        config = NotificationConfig(
            title="Flatpak",
            message_success="OK",
            message_failure="Mise à jour échouée",
            icon_failure="dialog-error"
        )
        result = config.to_bash_call_failure()
        assert "send_notification" in result
        assert "Flatpak" in result
        assert "Mise à jour échouée" in result
        assert "dialog-error" in result


class TestNotificationConfigValidationControle:
    """Tests de rejet des caractères de contrôle dans __post_init__."""

    def test_title_avec_newline_leve_valueerror(self):
        """title contenant \\n lève ValueError."""
        with pytest.raises(ValueError, match="Caractère de contrôle"):
            NotificationConfig(
                title="titre\nmalicieux",
                message_success="OK",
                message_failure="KO",
            )

    def test_message_avec_caractere_controle_leve_valueerror(self):
        """message_success contenant un char de contrôle (\\x01) lève ValueError."""
        with pytest.raises(ValueError, match="Caractère de contrôle"):
            NotificationConfig(
                title="Titre",
                message_success="msg\x01malicieux",
                message_failure="KO",
            )

    def test_message_failure_avec_tab_leve_valueerror(self):
        """message_failure contenant \\t lève ValueError."""
        with pytest.raises(ValueError, match="Caractère de contrôle"):
            NotificationConfig(
                title="Titre",
                message_success="OK",
                message_failure="msg\tmalicieux",
            )

    def test_to_bash_call_echappe_entree_hostile(self):
        """shlex.quote neutralise les entrées hostiles dans to_bash_call_success."""
        config = NotificationConfig(
            title='a"; rm -rf /',
            message_success="OK",
            message_failure="KO",
        )
        result = config.to_bash_call_success()
        # shlex.quote place le titre entre apostrophes → injection neutralisée
        assert shlex.quote('a"; rm -rf /') in result


class TestNotificationConfigAppName:
    """Tests pour l'attribut app_name."""

    def test_app_name_defaut_flatpak(self):
        """app_name vaut 'Flatpak' par défaut."""
        config = NotificationConfig(
            title="T", message_success="OK", message_failure="KO"
        )
        assert config.app_name == "Flatpak"

    def test_app_name_personnalise_dans_bash_function(self):
        """app_name personnalisé apparaît dans to_bash_function()."""
        config = NotificationConfig(
            title="T", message_success="OK", message_failure="KO",
            app_name="MonApp",
        )
        result = config.to_bash_function()
        assert "MonApp" in result
        assert "Flatpak" not in result
