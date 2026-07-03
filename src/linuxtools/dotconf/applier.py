"""Application d'un ConfigSpec sur un fichier de configuration cible."""

from pathlib import Path

from linuxtools.dotconf.line_editor import SectionAwareEditor
from linuxtools.dotconf.spec import ConfigBlock, ConfigSpec
from linuxtools.logging.base import Logger


class ConfigApplier:
    """Applique un ConfigSpec sur un fichier de configuration cible.

    Utilise SectionAwareEditor pour toutes les modifications de fichier,
    garantissant la préservation des commentaires et du formatage existant.

    Attributes:
        _logger: Logger optionnel pour tracer chaque action.

    Example:
        >>> from pathlib import Path
        >>> applier = ConfigApplier()
        >>> spec = ConfigSpec(
        ...     file_path=Path("/tmp/test.conf"),
        ...     blocks=[ConfigBlock(content="key = value")],
        ... )
        >>> actions = applier.apply(spec)
        >>> actions
        ['Appended: key = value']
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise l'applier avec un logger optionnel.

        Args:
            logger: Instance de Logger. Si None, aucun log n'est émis.
        """
        self._logger = logger

    def apply(self, spec: ConfigSpec) -> list[str]:
        """Applique tous les blocs de la spec sur le fichier cible.

        Si le fichier n'existe pas, il est créé avec tous les blocs.
        Sinon, chaque bloc est traité individuellement : ajout, décommentage
        ou ignoré s'il est déjà présent.

        Args:
            spec: ConfigSpec contenant le chemin cible et les blocs.

        Returns:
            Liste des actions effectuées. Liste vide si aucune modification.

        Raises:
            PermissionError: Si l'écriture sur le fichier est refusée.
        """
        target = spec.file_path

        if not target.exists():
            effective = [b for b in spec.blocks if b.content.strip()]
            if not effective:
                return []
            return self._create_file(target, effective)

        actions: list[str] = []
        for block in spec.blocks:
            action = self._apply_block(target, block)
            if action is not None:
                actions.append(action)

        if actions:
            target.chmod(0o644)

        return actions

    def _apply_block(
        self,
        target: Path,
        block: ConfigBlock,
    ) -> str | None:
        """Applique un bloc individuel sur le fichier existant.

        Args:
            target: Fichier cible existant.
            block: Bloc à appliquer.

        Returns:
            Message d'action si le fichier a été modifié, None sinon.
        """
        if not block.content.strip():
            return None

        editor = SectionAwareEditor(target)

        if editor.is_block_present(block.content, block.section):
            return None

        was_commented = editor.is_block_commented(
            block.content, block.section
        )
        editor.ensure_block(block.content, block.section, block.comment)

        first_line = block.content.splitlines()[0][:50]
        if was_commented:
            action = f"Uncommented: {first_line}"
        elif block.section:
            action = f"Added to [{block.section}]: {first_line}"
        else:
            action = f"Appended: {first_line}"

        if self._logger is not None:
            self._logger.log_info(f"{action} in {target}")

        return action

    def _create_file(
        self,
        target: Path,
        blocks: list[ConfigBlock],
    ) -> list[str]:
        """Crée le fichier et y écrit tous les blocs.

        Args:
            target: Chemin du fichier à créer.
            blocks: Blocs à écrire dans l'ordre.

        Returns:
            Liste contenant l'unique message de création.
        """
        target.parent.mkdir(parents=True, mode=0o755, exist_ok=True)

        editor = SectionAwareEditor(target)
        for block in blocks:
            editor.ensure_block(block.content, block.section, block.comment)

        target.chmod(0o644)
        action = f"Created: {target} ({len(blocks)} blocks)"

        if self._logger is not None:
            self._logger.log_info(action)

        return [action]
