"""Helpers spécifiques à une distribution.

⚠ Seul module de linuxtools lié à une distribution précise. Isolé ici
volontairement : le reste de la bibliothèque est distro-agnostique, et
ce module doit rester extractible d'un bloc.

Fedora / RPM:
- fedora_version: version Fedora courante via ``rpm --eval %fedora``
"""

from linuxtools.distro.fedora import fedora_version

__all__ = [
    "fedora_version",
]
