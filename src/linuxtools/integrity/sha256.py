"""Vérificateur d'intégrité SHA256 pour fichiers et répertoires."""

from pathlib import Path

from linuxtools.errors.exceptions import IntegrityError
from linuxtools.integrity.base import (
    ChecksumCalculator,
    HashLibChecksumCalculator,
    IntegrityChecker,
)
from linuxtools.logging.base import Logger


class SHA256IntegrityChecker(IntegrityChecker):
    """Vérificateur d'intégrité basé sur SHA256.

    Compare les checksums entre source et destination pour vérifier
    que les fichiers ont été copiés correctement.

    Respecte le principe DIP en acceptant un ChecksumCalculator
    en injection de dépendance, facilitant les tests unitaires.
    """

    def __init__(
        self,
        logger: Logger | None = None,
        algorithm: str = "sha256",
        checksum_calculator: ChecksumCalculator | None = None,
    ) -> None:
        """Initialise le vérificateur d'intégrité.

        Args:
            logger: Instance de Logger pour le logging.
            algorithm: Algorithme de hash (défaut: sha256).
            checksum_calculator: Instance de ChecksumCalculator (optionnel).
                Si non fourni, utilise HashLibChecksumCalculator par défaut.
        """
        self._logger = logger
        self.algorithm = algorithm
        self._calculator = checksum_calculator or HashLibChecksumCalculator()

    def _calculate(self, file_path: str | Path) -> str:
        """Calcule le checksum via l'instance injectée.

        Args:
            file_path: Chemin du fichier.

        Returns:
            Checksum hexadécimal du fichier.
        """
        return self._calculator.calculate(file_path, self.algorithm)

    def verify_file(
        self,
        source_file: str | Path,
        dest_file: str | Path,
    ) -> bool:
        """Vérifie l'intégrité d'un fichier unique.

        Args:
            source_file: Chemin du fichier source.
            dest_file: Chemin du fichier destination.

        Returns:
            True si les checksums correspondent, False sinon.
        """
        try:
            source_checksum = self._calculate(source_file)
            dest_checksum = self._calculate(dest_file)
            if source_checksum != dest_checksum:
                return False
            return True
        except OSError as e:
            if self._logger:
                self._logger.log_error(f"Erreur de vérification: {e}")
            return False

    def _resolve_dest(
        self,
        source_path: Path,
        destination_path: Path,
        dest_subdir: str | None,
    ) -> Path:
        """Résout le répertoire de destination effectif.

        Gère le cas rsync où le source est copié dans un sous-répertoire
        portant son nom.

        Args:
            source_path: Répertoire source.
            destination_path: Répertoire destination de base.
            dest_subdir: Sous-répertoire explicite (prioritaire).

        Returns:
            Chemin de destination effectif.
        """
        if dest_subdir:
            return destination_path / dest_subdir
        actual = destination_path / source_path.name
        if not actual.exists():
            actual = destination_path
        return actual

    def _verify_tree(
        self,
        source_path: Path,
        dest: Path,
    ) -> tuple[bool, int]:
        """Compare chaque fichier de l'arbre source à sa copie destination.

        Args:
            source_path: Répertoire source.
            dest: Répertoire destination effectif.

        Returns:
            Tuple (succès, nombre de fichiers vérifiés).
        """
        count = 0
        for source_file in source_path.rglob("*"):
            if not source_file.is_file():
                continue
            rel_path = source_file.relative_to(source_path)
            dest_file = dest / rel_path
            if not dest_file.exists():
                if self._logger:
                    self._logger.log_error(
                        f"Fichier manquant: {dest_file}"
                    )
                return False, count
            if not self.verify_file(source_file, dest_file):
                if self._logger:
                    self._logger.log_error(
                        f"Checksum différent pour: {rel_path}"
                    )
                return False, count
            count += 1
        return True, count

    def verify(
        self,
        source: str,
        destination: str,
        dest_subdir: str | None = None,
    ) -> bool:
        """Vérifie l'intégrité d'une copie de répertoire.

        Gère automatiquement le cas où rsync crée un sous-répertoire
        avec le nom du source dans la destination.

        Args:
            source: Chemin du répertoire source.
            destination: Chemin du répertoire destination.
            dest_subdir: Sous-répertoire optionnel dans destination.

        Returns:
            True si tous les fichiers correspondent, False sinon.
            Retourne True avec un warning si la source est vide.
        """
        try:
            source_path = Path(source)
            destination_path = Path(destination)
            dest = self._resolve_dest(
                source_path, destination_path, dest_subdir
            )
            if self._logger:
                self._logger.log_info(
                    f"Vérification: {source_path} -> {dest}"
                )
            ok, count = self._verify_tree(source_path, dest)
            if not ok:
                return False
            if count == 0:
                if self._logger:
                    self._logger.log_warning(
                        "Aucun fichier vérifié (source vide ?)."
                    )
            if self._logger:
                self._logger.log_info(
                    f"Vérification terminée : {count}"
                    " fichier(s) vérifié(s)."
                )
            return True
        except (OSError, ValueError) as e:
            if self._logger:
                self._logger.log_error(
                    "Erreur lors de la vérification"
                    f" d'intégrité: {e}"
                )
            return False

    def verify_file_or_raise(
        self,
        source_file: str | Path,
        dest_file: str | Path,
    ) -> None:
        """Vérifie l'intégrité d'un fichier ou lève IntegrityError.

        Contrairement à verify_file, les OSError ne sont pas capturées —
        réservée aux contextes où un échec doit être fatal.

        Args:
            source_file: Chemin du fichier source.
            dest_file: Chemin du fichier destination.

        Raises:
            IntegrityError: Si les checksums source et destination diffèrent.
            OSError: Si un fichier est inaccessible.
        """
        source_checksum = self._calculate(source_file)
        dest_checksum = self._calculate(dest_file)
        if source_checksum != dest_checksum:
            raise IntegrityError(
                path=dest_file,
                expected=source_checksum,
                actual=dest_checksum,
            )

    def verify_or_raise(
        self,
        source: str,
        destination: str,
        dest_subdir: str | None = None,
    ) -> int:
        """Vérifie l'intégrité d'une copie de répertoire ou lève
        IntegrityError.

        Contrairement à verify, ne capture pas les exceptions — le premier
        fichier manquant ou checksum différent lève immédiatement
        IntegrityError (fail-fast).

        Args:
            source: Chemin du répertoire source.
            destination: Chemin du répertoire destination.
            dest_subdir: Sous-répertoire optionnel dans destination.

        Returns:
            Nombre de fichiers vérifiés.

        Raises:
            IntegrityError: Dès le premier fichier manquant ou checksum
                différent.
            OSError: Si un fichier est inaccessible.
        """
        source_path = Path(source)
        destination_path = Path(destination)
        dest = self._resolve_dest(
            source_path, destination_path, dest_subdir
        )
        if self._logger:
            self._logger.log_info(
                f"Vérification: {source_path} -> {dest}"
            )
        count = 0
        for source_file in source_path.rglob("*"):
            if not source_file.is_file():
                continue
            rel_path = source_file.relative_to(source_path)
            dest_file = dest / rel_path
            if not dest_file.exists():
                raise IntegrityError(path=dest_file)
            self.verify_file_or_raise(source_file, dest_file)
            count += 1
        if count == 0 and self._logger:
            self._logger.log_warning(
                "Aucun fichier vérifié (source vide ?)."
            )
        if self._logger:
            self._logger.log_info(
                f"Vérification terminée : {count} fichier(s) vérifié(s)."
            )
        return count

    def get_checksum(self, file_path: str | Path) -> str:
        """Calcule et retourne le checksum d'un fichier.

        Args:
            file_path: Chemin du fichier.

        Returns:
            Checksum hexadécimal.
        """
        checksum = self._calculate(file_path)
        if self._logger:
            self._logger.log_info(f"Checksum de {file_path}: {checksum}")
        return checksum
