"""Module de vérification d'intégrité.

Compare une source et une destination — checksum de fichier ou clés
d'une section INI — pour confirmer qu'une copie ou une écriture s'est
déroulée sans altération. N'accepte que des algorithmes de hash
cryptographiquement solides (sha256, sha384, sha512, blake2b — MD5 et
SHA1 exclus).

Calcul de checksum:
- ChecksumCalculator: Interface abstraite (calculate)
- HashLibChecksumCalculator: Implémentation via hashlib
- calculate_checksum: Fonction utilitaire
  (HashLibChecksumCalculator par défaut)

Vérification source/destination:
- IntegrityChecker: Interface abstraite (verify)
- SHA256IntegrityChecker: Compare les checksums SHA256 de deux fichiers
- IniSectionIntegrityChecker: Compare les clés d'une section INI

Exemple d'utilisation:
    from linuxtools.integrity import SHA256IntegrityChecker

    checker = SHA256IntegrityChecker(logger=logger)
    if not checker.verify("/tmp/source.tar", "/opt/mon-outil/source.tar"):
        raise IntegrityError("Checksum divergent après copie")

Exemple d'utilisation (fonction utilitaire):
    from linuxtools.integrity import calculate_checksum

    checksum = calculate_checksum("/etc/mon-outil/config.toml")
"""

from linuxtools.integrity.base import (
    ChecksumCalculator,
    HashLibChecksumCalculator,
    IntegrityChecker,
    calculate_checksum,
)
from linuxtools.integrity.ini_checker import IniSectionIntegrityChecker
from linuxtools.integrity.sha256 import SHA256IntegrityChecker

__all__ = [
    "ChecksumCalculator",
    "HashLibChecksumCalculator",
    "IniSectionIntegrityChecker",
    "IntegrityChecker",
    "SHA256IntegrityChecker",
    "calculate_checksum",
]
