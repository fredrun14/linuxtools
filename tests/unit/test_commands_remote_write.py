"""Tests pour la primitive `build_remote_write_command`.

Fonction pure construisant `install -m <mode> -T /dev/stdin <dest>` —
seule commande validée pour écrire un fichier sur une cible distante
(invariant projet, voir CONTEXT.md). Verrouille le gabarit partagé par
les deux appelants (`deploy/destinations.py`, `systemd/base.py`).
"""

import inspect

import pytest

from linuxtools.commands.remote_write import build_remote_write_command


def test_build_remote_write_command_cas_nominal() -> None:
    """Cas nominal : mode 0o644 sur un chemin de config."""
    # Arrange
    mode = 0o644
    dest = "/etc/app/config.toml"

    # Act
    command = build_remote_write_command(mode, dest)

    # Assert
    assert command == [
        "install",
        "-m",
        "644",
        "-T",
        "/dev/stdin",
        "/etc/app/config.toml",
    ]


@pytest.mark.parametrize(
    "mode,expected",
    [
        (0o600, "600"),
        (0o644, "644"),
        (0o755, "755"),
        (0o400, "400"),
    ],
)
def test_build_remote_write_command_formate_le_mode_en_octal_3_chiffres(
    mode: int, expected: str
) -> None:
    """Le mode POSIX est formaté en octal 3 chiffres pour `-m`.

    Mêmes valeurs que
    `test_deploy_destinations.py::test_remote_formate_le_mode_pour_install`
    — couvre exactement les modes réellement utilisés dans le projet :
    secrets (0600), config (0644), scripts USB (0755), lecture seule
    (0400).
    """
    command = build_remote_write_command(mode, "/tmp/x")

    assert command[2] == expected


def test_build_remote_write_command_place_dest_en_dernier() -> None:
    """Cas limite : un `dest` contenant des espaces reste un seul
    élément de la liste, pas éclaté — garantit que la commande reste
    sûre en liste (pas de split shell possible)."""
    # Arrange
    dest = "/tmp/mon dossier/x"

    # Act
    command = build_remote_write_command(0o644, dest)

    # Assert
    assert command[-1] == dest
    assert len(command) == 6


def test_build_remote_write_command_ne_contient_jamais_le_contenu() -> None:
    """Verrouille l'absence de paramètre `content` dans la signature :
    rien ne peut faire fuiter du contenu dans la commande — le
    contenu doit toujours transiter par `stdin`, jamais par argument
    (`ps` l'exposerait sinon)."""
    parametres = inspect.signature(build_remote_write_command).parameters

    assert set(parametres) == {"mode", "dest"}
