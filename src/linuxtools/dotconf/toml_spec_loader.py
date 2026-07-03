"""Chargement d'un fichier TOML de spécification vers ConfigSpec.

Format TOML attendu :

    [target]
    file_path = "~/.config/app/config"

    [[target.content]]
    comment = "# Section title"
    content = "key = value"
    section = "main"   # optionnel
"""

import os
from pathlib import Path
from typing import Any

from linuxtools.config import ConfigLoader, FileConfigLoader
from linuxtools.dotconf.spec import ConfigBlock, ConfigSpec


class TomlSpecLoader:
    """Charge un fichier TOML de spécification et produit un ConfigSpec.

    Attributes:
        _loader: Chargeur de configuration injectable.

    Example:
        >>> loader = TomlSpecLoader()
        >>> spec = loader.load(Path("myapp.toml"))
        >>> spec.file_path
        PosixPath('/home/user/.config/myapp/config')
    """

    def __init__(
        self,
        loader: ConfigLoader | None = None,
    ) -> None:
        """Initialise avec un ConfigLoader injectable.

        Args:
            loader: Implémentation de ConfigLoader. Utilise
                FileConfigLoader par défaut.
        """
        self._loader: ConfigLoader = loader or FileConfigLoader()

    def load(self, spec_path: Path) -> ConfigSpec:
        """Charge un TOML et retourne un ConfigSpec prêt à l'emploi.

        Args:
            spec_path: Chemin vers le fichier .toml.

        Returns:
            ConfigSpec avec file_path absolu résolu et blocs parsés.

        Raises:
            FileNotFoundError: Si spec_path n'existe pas.
            KeyError: Si la clé 'target' ou 'file_path' est absente.
            ValueError: Si un bloc ne contient pas de clé 'content'.
        """
        data: dict[str, Any] = self._loader.load(spec_path)
        target: dict[str, Any] = data["target"]
        file_path = self._resolve_path(str(target["file_path"]))
        blocks = self._parse_blocks(target)
        return ConfigSpec(file_path=file_path, blocks=blocks)

    def _resolve_path(self, raw_path: str) -> Path:
        """Résout ~, $VAR, ${VAR} et retourne un Path absolu.

        Args:
            raw_path: Chemin brut avec éventuels tilde et variables.

        Returns:
            Path absolu après expansion et résolution.
        """
        with_vars = os.path.expandvars(raw_path)
        return Path(with_vars).expanduser().resolve()

    def _parse_blocks(
        self,
        target: dict[str, Any],
    ) -> list[ConfigBlock]:
        """Parse la liste [[target.content]] en ConfigBlock.

        Args:
            target: Dictionnaire de la section [target] du TOML.

        Returns:
            Liste de ConfigBlock dans l'ordre du fichier TOML.

        Raises:
            ValueError: Si un item manque la clé 'content'.
        """
        raw_blocks: list[dict[str, Any]] = target.get("content", [])
        blocks: list[ConfigBlock] = []

        for i, item in enumerate(raw_blocks):
            content = item.get("content")
            if not content:
                raise ValueError(
                    f"Bloc #{i + 1} sans clé 'content' dans la spec TOML"
                )
            blocks.append(
                ConfigBlock(
                    content=str(content),
                    comment=str(item.get("comment", "")),
                    section=item.get("section"),
                )
            )

        return blocks
