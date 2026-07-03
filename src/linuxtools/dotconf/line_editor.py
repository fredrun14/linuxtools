"""Éditeur ligne-à-ligne préservant formatage des fichiers de configuration."""

import re
from collections.abc import Callable
from pathlib import Path


class SectionAwareEditor:
    """Éditeur ligne-à-ligne pour fichiers de configuration plats ou INI.

    Préserve les commentaires, les lignes vides et le formatage existant.
    Modifie uniquement les lignes strictement nécessaires.

    Supporte :
    - Les fichiers plats sans section (style yt-dlp : --option)
    - Les fichiers INI avec sections (style dnf.conf : [main])
    - La détection et le décommentage de lignes commentées (#option)
    """

    _SECTION_RE: re.Pattern[str] = re.compile(r"^\[([^\]]+)\]")
    _COMMENT_PREFIXES: tuple[str, ...] = ("#", ";")

    def __init__(self, file_path: Path) -> None:
        """Initialise l'éditeur avec le chemin du fichier cible.

        Args:
            file_path: Chemin absolu du fichier à modifier.
                       Le fichier peut ne pas exister (créé si nécessaire).
        """
        self._path = file_path

    @staticmethod
    def _block_lines(content: str) -> list[str]:
        """Retourne les lignes non vides du contenu, stripées."""
        return [ln.strip() for ln in content.splitlines() if ln.strip()]

    def _block_matches(
        self,
        content: str,
        section: str | None,
        predicate: Callable[[str, str], bool],
        lines: list[str] | None = None,
    ) -> bool:
        """Vérifie si toutes les lignes du bloc satisfont le prédicat."""
        if lines is None:
            lines = self._read_lines()
        if not lines:
            return False
        block_lines = self._block_lines(content)
        search_lines = self._get_search_scope(lines, section)
        if search_lines is None:
            return False
        return all(
            any(predicate(fl, bl) for fl in search_lines)
            for bl in block_lines
        )

    def is_block_present(
        self,
        content: str,
        section: str | None = None,
    ) -> bool:
        """Vérifie si toutes les lignes du bloc sont actives dans le fichier.

        Chaque ligne du bloc est recherchée indépendamment — elles n'ont
        pas besoin d'être contiguës dans le fichier.

        Args:
            content: Contenu du bloc (peut être multilignes).
            section: Nom de la section INI, ou None pour les fichiers plats.

        Returns:
            True si toutes les lignes du bloc sont présentes et non commentées.
            False si le fichier n'existe pas ou si une ligne manque.
        """
        return self._block_matches(
            content, section, self._is_active_line
        )

    def is_block_commented(
        self,
        content: str,
        section: str | None = None,
    ) -> bool:
        """Vérifie si les lignes du bloc sont commentées dans le fichier.

        Args:
            content: Contenu du bloc (peut être multilignes).
            section: Nom de la section INI, ou None pour les fichiers plats.

        Returns:
            True si toutes les lignes du bloc existent sous forme commentée.
            False si le fichier n'existe pas ou si les lignes sont absentes.
        """
        return self._block_matches(
            content, section, self._is_commented_line
        )

    def ensure_block(
        self,
        content: str,
        section: str | None = None,
        comment: str = "",
    ) -> bool:
        """Assure la présence du bloc avec préservation des commentaires.

        Comportement selon l'état du fichier :

        1. Bloc actif → aucune modification (retourne False).
        2. Bloc commenté → décommente les lignes concernées (retourne True).
        3. Fichier/bloc absent, section None → appende en fin de fichier.
        4. Bloc absent, section existante → insère avant la section suivante.
        5. Bloc absent, section manquante → ajoute [section] en fin de fichier.

        Args:
            content: Contenu du bloc (une ou plusieurs lignes).
            section: Nom de la section INI cible. None pour les fichiers plats.
            comment: Commentaire à insérer avant le bloc (ex: "# Titre").

        Returns:
            True si modifié, False si aucun changement nécessaire.
        """
        if not content.strip():
            return False

        lines = self._read_lines()

        if self._block_matches(content, section, self._is_active_line, lines):
            return False

        block_lines = self._block_lines(content)

        if self._block_matches(
            content, section, self._is_commented_line, lines
        ):
            lines = self._uncomment_block_lines(lines, block_lines, section)
            self._write_lines(lines)
            return True

        formatted = self._format_block(content, comment)

        if section is None:
            lines.extend(formatted)
            self._write_lines(lines)
            return True

        start, end = self._find_section_range(lines, section)
        if start == -1:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"\n[{section}]\n")
            lines.extend(formatted)
        else:
            for item in reversed(formatted):
                lines.insert(end, item)

        self._write_lines(lines)
        return True

    def list_sections(self) -> list[str]:
        """Retourne la liste des sections INI présentes dans le fichier.

        Returns:
            Liste des noms de sections dans leur ordre d'apparition.
            Liste vide si le fichier n'existe pas ou sans sections.
        """
        return [
            m.group(1)
            for line in self._read_lines()
            if (m := self._SECTION_RE.match(line.strip()))
        ]

    def _read_lines(self) -> list[str]:
        """Lit le fichier et retourne ses lignes avec fins de ligne.

        Returns:
            Liste de lignes (avec \\n), vide si le fichier n'existe pas.
        """
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines(keepends=True)

    def _write_lines(self, lines: list[str]) -> None:
        """Écrit les lignes dans le fichier (crée le dossier parent si besoin).

        Args:
            lines: Lignes à écrire (avec fins de ligne).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("".join(lines), encoding="utf-8")

    def _find_section_range(
        self,
        lines: list[str],
        section: str,
    ) -> tuple[int, int]:
        """Localise une section INI et retourne ses indices de début et fin.

        Args:
            lines: Lignes du fichier.
            section: Nom de la section à localiser.

        Returns:
            Tuple (start, end) où start est l'index de la ligne [section]
            et end est l'index de la première ligne de la section suivante
            (ou len(lines) si c'est la dernière section).
            Retourne (-1, -1) si la section n'existe pas.
        """
        start = -1
        for i, line in enumerate(lines):
            match = self._SECTION_RE.match(line.strip())
            if match:
                if match.group(1) == section:
                    start = i
                elif start != -1:
                    return start, i
        if start == -1:
            return -1, -1
        return start, len(lines)

    def _get_search_scope(
        self,
        lines: list[str],
        section: str | None,
    ) -> list[str] | None:
        """Retourne les lignes dans lesquelles chercher selon la section.

        Args:
            lines: Toutes les lignes du fichier.
            section: Nom de section, ou None pour tout le fichier.

        Returns:
            Sous-liste de lignes, ou None si la section est introuvable.
        """
        if section is None:
            return lines
        start, end = self._find_section_range(lines, section)
        if start == -1:
            return None
        return lines[start:end]

    def _uncomment_block_lines(
        self,
        lines: list[str],
        block_lines: list[str],
        section: str | None,
    ) -> list[str]:
        """Décommente les lignes du bloc dans la plage appropriée.

        Args:
            lines: Toutes les lignes du fichier.
            block_lines: Lignes du bloc à décommenter (stripées).
            section: Nom de la section, ou None.

        Returns:
            Liste de lignes modifiée.
        """
        if section is None:
            start, end = 0, len(lines)
        else:
            start, end = self._find_section_range(lines, section)
            if start == -1:
                return lines

        result = list(lines)
        for i in range(start, end):
            for bl in block_lines:
                if self._is_commented_line(result[i], bl):
                    result[i] = self._uncomment_line(result[i])
                    break
        return result

    def _is_active_line(self, line: str, target: str) -> bool:
        """Vérifie si une ligne correspond à la cible (active, non commentée).

        Args:
            line: Ligne du fichier (avec fin de ligne possible).
            target: Ligne cible à rechercher (stripée).

        Returns:
            True si line.strip() == target.
        """
        return line.strip() == target

    def _is_commented_line(self, line: str, target: str) -> bool:
        """Vérifie si une ligne est la cible commentée.

        Args:
            line: Ligne du fichier.
            target: Ligne cible à rechercher (stripée).

        Returns:
            True si la ligne, dépouillée de son préfixe de commentaire,
            correspond à target.
        """
        stripped = line.strip()
        for prefix in self._COMMENT_PREFIXES:
            if stripped.startswith(prefix):
                candidate = stripped[len(prefix):].strip()
                if candidate == target:
                    return True
        return False

    def _uncomment_line(self, line: str) -> str:
        """Supprime le préfixe de commentaire (#, ;) et l'espace suivant.

        Args:
            line: Ligne commentée (avec fin de ligne possible).

        Returns:
            Ligne décommentée avec \\n final préservé.
        """
        ending = "\n" if line.endswith("\n") else ""
        stripped = line.strip()
        for prefix in self._COMMENT_PREFIXES:
            if stripped.startswith(prefix):
                uncommented = stripped[len(prefix):]
                if uncommented.startswith(" "):
                    uncommented = uncommented[1:]
                return uncommented + ending
        return line

    def _format_block(self, content: str, comment: str) -> list[str]:
        """Formate un bloc de contenu avec commentaire optionnel.

        Args:
            content: Contenu du bloc (peut être multilignes).
            comment: Ligne de commentaire (vide si aucun).

        Returns:
            Liste de lignes formatées prêtes à être insérées (avec \\n).
        """
        result: list[str] = []
        if comment:
            result.append(comment + "\n")
        for line in content.splitlines():
            result.append(line + "\n")
        result.append("\n")
        return result
