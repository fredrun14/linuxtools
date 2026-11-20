"""Tests de comportement complémentaires pour le module identity (sans logger)."""

from unittest.mock import MagicMock, patch

from linuxtools.identity.group import LinuxGroupManager
from linuxtools.identity.user import LinuxUserManager


def _commandes(executeur: MagicMock) -> list[list[str]]:
    """Liste les commandes passées à l'exécuteur."""
    return [c.args[0] for c in executeur.run.call_args_list]


def _entree(**champs: int | list[str]) -> MagicMock:
    """Fausse entrée grp/pwd portant les champs donnés."""
    entree = MagicMock()
    for nom, valeur in champs.items():
        setattr(entree, nom, valeur)
    return entree


# --- LinuxGroupManager ---


def test_groupe_au_mauvais_gid_est_corrige_sans_logger(executeur: MagicMock) -> None:
    """Sans logger, un GID divergent déclenche groupmod."""
    with patch(
        "linuxtools.identity.group.grp.getgrnam", return_value=_entree(gr_gid=1)
    ):
        LinuxGroupManager(executor=executeur).ensure_group("equipe", 1042)

    assert _commandes(executeur) == [["groupmod", "--gid", "1042", "equipe"]]


def test_groupe_deja_conforme_ne_lance_rien_sans_logger(executeur: MagicMock) -> None:
    """Sans logger, un groupe au bon GID ne déclenche aucune commande."""
    with patch(
        "linuxtools.identity.group.grp.getgrnam", return_value=_entree(gr_gid=1042)
    ):
        LinuxGroupManager(executor=executeur).ensure_group("equipe", 1042)

    assert _commandes(executeur) == []


def test_groupe_absent_est_cree_sans_logger(executeur: MagicMock) -> None:
    """Sans logger, un groupe inconnu est créé par groupadd."""
    with patch("linuxtools.identity.group.grp.getgrnam", side_effect=KeyError):
        LinuxGroupManager(executor=executeur).ensure_group("equipe", 1042)

    assert _commandes(executeur) == [["groupadd", "--gid", "1042", "equipe"]]


# --- LinuxUserManager ---


def test_utilisateur_au_mauvais_uid_est_corrige_sans_logger(
    executeur: MagicMock,
) -> None:
    """Sans logger, un UID divergent déclenche usermod."""
    with patch("linuxtools.identity.user.pwd.getpwnam", return_value=_entree(pw_uid=1)):
        LinuxUserManager(executor=executeur).ensure_user(
            "svc", 1042, "/bin/false", "c", create_home=False
        )

    assert _commandes(executeur) == [["usermod", "--uid", "1042", "svc"]]


def test_utilisateur_deja_conforme_ne_lance_rien_sans_logger(
    executeur: MagicMock,
) -> None:
    """Sans logger, un utilisateur à l'UID attendu ne déclenche aucune commande."""
    with patch(
        "linuxtools.identity.user.pwd.getpwnam", return_value=_entree(pw_uid=1042)
    ):
        LinuxUserManager(executor=executeur).ensure_user(
            "svc", 1042, "/bin/false", "c", create_home=False
        )

    assert _commandes(executeur) == []


def test_utilisateur_absent_est_cree_sans_logger(executeur: MagicMock) -> None:
    """Sans logger, un utilisateur inconnu est créé par useradd."""
    with patch("linuxtools.identity.user.pwd.getpwnam", side_effect=KeyError):
        LinuxUserManager(executor=executeur).ensure_user(
            "svc", 1042, "/bin/false", "c", create_home=True
        )

    assert _commandes(executeur) == [
        [
            "useradd",
            "--uid",
            "1042",
            "--shell",
            "/bin/false",
            "--comment",
            "c",
            "--create-home",
            "svc",
        ]
    ]


def test_groupes_secondaires_sans_logger_ajoute_les_manquants(
    executeur: MagicMock,
) -> None:
    """Sans logger, seuls les groupes dont l'utilisateur est absent sont ajoutés."""

    def _groupe(nom: str) -> MagicMock:
        if nom == "inconnu":
            raise KeyError(nom)
        return _entree(gr_mem=["svc"] if nom == "deja" else [])

    with patch("linuxtools.identity.user.grp.getgrnam", side_effect=_groupe):
        LinuxUserManager(executor=executeur).ensure_user_groups(
            "svc", ["inconnu", "deja", "neuf"]
        )

    commande = _commandes(executeur)[0]
    assert commande[0] == "usermod"
    assert commande[commande.index("--groups") + 1] == "neuf"


def test_groupes_secondaires_deja_membre_ne_lance_rien_sans_logger(
    executeur: MagicMock,
) -> None:
    """Sans logger, un utilisateur déjà membre de tout ne déclenche rien."""
    with patch(
        "linuxtools.identity.user.grp.getgrnam",
        return_value=_entree(gr_mem=["svc"]),
    ):
        LinuxUserManager(executor=executeur).ensure_user_groups("svc", ["a"])

    assert _commandes(executeur) == []
