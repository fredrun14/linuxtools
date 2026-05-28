"""Export d'un fichier de configuration existant vers un TOML TomlSpecLoader."""

import re
from pathlib import Path

from linux_python_utils.dotconf.spec import ConfigBlock


class ConfTomlExporter:
    """Exporte un fichier conf existant vers un TOML compatible TomlSpecLoader.

    Lit un fichier de configuration (format plat ou INI) et produit
    un fichier TOML compatible avec TomlSpecLoader / ConfigApplier,
    permettant de ré-appliquer le contenu sur une autre machine.

    Le format TOML produit est :

        [target]
        file_path = "/chemin/absolu/vers/fichier"

        [[target.content]]
        comment = "# commentaire précédant"
        content = "ligne de configuration"
        section = "main"   # uniquement pour fichiers INI

    Attributes:
        Aucun attribut public — classe sans état.

    Example:
        >>> exporter = ConfTomlExporter()
        >>> exporter.export(Path("/etc/dnf/dnf.conf"), Path("/tmp/dnf.toml"))
    """

    def export(self, source: Path, dest: Path) -> None:
        """Lit source et écrit dest au format TOML TomlSpecLoader.

        Args:
            source: Chemin du fichier conf à lire (résolu en absolu).
            dest: Chemin du fichier TOML de sortie à écrire.

        Raises:
            FileNotFoundError: Si source n'existe pas.
        """
        if not source.exists():
            raise FileNotFoundError(source)
        lines = source.read_text(encoding="utf-8").splitlines()
        abs_path = source.resolve()
        blocks = self._parse(lines)
        content = self._render_toml(abs_path, blocks)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    def _parse(self, lines: list[str]) -> list[ConfigBlock]:
        """Parse les lignes du fichier en liste de ConfigBlock.

        Les commentaires consécutifs (#, ;) sont associés au bloc
        de contenu suivant. Les lignes vides et les commentaires
        sans contenu suivant sont ignorés.

        Args:
            lines: Lignes du fichier source (sans retour chariot).

        Returns:
            Liste de ConfigBlock dans l'ordre de lecture.
        """
        is_ini = self._is_ini(lines)
        current_section: str | None = None
        pending: list[str] = []
        blocks: list[ConfigBlock] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                pending.clear()
                continue
            if is_ini:
                m = re.match(r'^\[([^\]]+)\]$', stripped)
                if m:
                    current_section = m.group(1)
                    pending.clear()
                    continue
            if stripped.startswith("#") or stripped.startswith(";"):
                pending.append(stripped)
                continue
            comment = "\n".join(pending)
            blocks.append(
                ConfigBlock(
                    content=stripped,
                    comment=comment,
                    section=current_section if is_ini else None,
                )
            )
            pending.clear()

        return blocks

    @staticmethod
    def _is_ini(lines: list[str]) -> bool:
        """Retourne True si les lignes contiennent un en-tête de section INI.

        Args:
            lines: Lignes du fichier source.

        Returns:
            True si au moins une ligne correspond à ``[section_name]``.
        """
        return any(
            re.match(r'^\s*\[([^\]]+)\]\s*$', line) for line in lines
        )

    def _render_toml(
        self,
        file_path: Path,
        blocks: list[ConfigBlock],
    ) -> str:
        """Sérialise file_path et blocks en texte TOML TomlSpecLoader.

        Args:
            file_path: Chemin absolu du fichier source (déjà résolu).
            blocks: Blocs à sérialiser.

        Returns:
            Texte TOML complet, terminé par un saut de ligne.
        """
        parts = [
            "[target]",
            f'file_path = "{self._toml_escape(str(file_path))}"',
            "",
        ]
        for block in blocks:
            parts.append("[[target.content]]")
            if block.comment:
                parts.append(
                    f'comment = "{self._toml_escape(block.comment)}"'
                )
            parts.append(
                f'content = "{self._toml_escape(block.content)}"'
            )
            if block.section is not None:
                parts.append(
                    f'section = "{self._toml_escape(block.section)}"'
                )
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _toml_escape(value: str) -> str:
        """Échappe une valeur pour une chaîne TOML basique.

        Args:
            value: Chaîne brute à insérer entre guillemets doubles TOML.

        Returns:
            Chaîne avec backslash, guillemets et retours ligne échappés.
        """
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
