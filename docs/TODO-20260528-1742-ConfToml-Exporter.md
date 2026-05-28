# CONFTOMLEXPORTER — EXPORT CONF → TOML
> **Date :** 2026-05-28 à 17:42
> **Complexité estimée :** Faible

---

## Contexte

### Problématique
Il n'existe pas de moyen de capturer un fichier de configuration existant
(`.zshrc`, `.vimrc`, `dnf.conf`…) en TOML pour pouvoir le réappliquer via
`ConfigApplier`. La chaîne "lecture/restore" est déjà complète côté TOML→fichier,
mais la direction inverse (fichier→TOML) manque.

### Solution technique retenue
Nouvelle classe `ConfTomlExporter` dans `dotconf/conf_toml_exporter.py`.
Méthode publique unique `export(source, dest)` qui :

1. lit le fichier source ligne par ligne ;
2. détecte automatiquement le format (INI ou plat) ;
3. construit des `ConfigBlock` en associant les commentaires consécutifs
   au bloc de contenu suivant ;
4. sérialise en TOML au format attendu par `TomlSpecLoader`.

Pas de dépendance externe (`tomli-w` non nécessaire, génération manuelle
comme partout dans le projet).

### Fichiers impactés
- `src/linux_python_utils/dotconf/conf_toml_exporter.py` — classe à créer
- `src/linux_python_utils/dotconf/__init__.py` — ajouter l'export public
- `tests/test_dotconf_conf_toml_exporter.py` — tests unitaires

---

## Évolutions à mettre en place (Détail Junior)

### `src/linux_python_utils/dotconf/conf_toml_exporter.py`

#### Imports
```python
# stdlib
import re
from pathlib import Path

# local
from linux_python_utils.dotconf.spec import ConfigBlock
```

#### Signature de classe
```python
class ConfTomlExporter:
    """Exporte un fichier conf existant vers un TOML TomlSpecLoader.

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
```

#### Logique détaillée de `export`
1. **Validation** — `if not source.exists(): raise FileNotFoundError(source)`
2. **Lecture** — `lines = source.read_text(encoding="utf-8").splitlines()`
3. **Résolution chemin** — `abs_path = source.resolve()`
4. **Parsing** — `blocks = self._parse(lines)`
5. **Rendu TOML** — `content = self._render_toml(abs_path, blocks)`
6. **Écriture** — `dest.parent.mkdir(parents=True, exist_ok=True)` puis `dest.write_text(content, encoding="utf-8")`

---

#### Méthode privée `_parse`

```python
def _parse(self, lines: list[str]) -> list[ConfigBlock]:
    """Parse les lignes du fichier en liste de ConfigBlock.

    Args:
        lines: Lignes du fichier source (sans retour chariot).

    Returns:
        Liste de ConfigBlock dans l'ordre de lecture.
    """
```

**Logique détaillée :**

1. **Détection INI** — appelle `self._is_ini(lines)` → bool `is_ini`
2. **Init** — `current_section: str | None = None`, `pending: list[str] = []`,
   `blocks: list[ConfigBlock] = []`
3. **Itération ligne par ligne** :
   - `stripped = line.strip()`
   - Si `stripped` est vide → `pending.clear()` ; continuer
   - Si `is_ini` ET `stripped` correspond à `^\[([^\]]+)\]$` :
     - `current_section = match.group(1)`
     - `pending.clear()` ; continuer
   - Si `stripped` commence par `#` ou `;` :
     - `pending.append(stripped)` ; continuer
   - Sinon (ligne de contenu) :
     - `comment = "\n".join(pending)` (vide si aucun commentaire)
     - Ajouter `ConfigBlock(content=stripped, comment=comment, section=current_section if is_ini else None)`
     - `pending.clear()`
4. **Retourner** `blocks`

---

#### Méthode privée `_is_ini` (statique)

```python
@staticmethod
def _is_ini(lines: list[str]) -> bool:
    """Retourne True si les lignes contiennent un en-tête de section INI.

    Args:
        lines: Lignes du fichier source.

    Returns:
        True si au moins une ligne correspond à `[section_name]`.
    """
```

**Logique :** `return any(re.match(r'^\s*\[([^\]]+)\]\s*$', l) for l in lines)`

---

#### Méthode privée `_render_toml`

```python
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
```

**Logique :**
```python
parts = [
    "[target]",
    f'file_path = "{self._toml_escape(str(file_path))}"',
    "",
]
for block in blocks:
    parts.append("[[target.content]]")
    if block.comment:
        parts.append(f'comment = "{self._toml_escape(block.comment)}"')
    parts.append(f'content = "{self._toml_escape(block.content)}"')
    if block.section is not None:
        parts.append(f'section = "{self._toml_escape(block.section)}"')
    parts.append("")
return "\n".join(parts)
```

---

#### Méthode privée `_toml_escape` (statique)

```python
@staticmethod
def _toml_escape(value: str) -> str:
    """Échappe une valeur pour une chaîne TOML basique (guillemets doubles).

    Args:
        value: Chaîne brute à insérer dans le TOML.

    Returns:
        Chaîne avec backslash, guillemets, et retours ligne échappés.
    """
```

**Logique (ordre strict) :**
```python
return (
    value
    .replace("\\", "\\\\")   # doit être en premier
    .replace('"', '\\"')
    .replace("\n", "\\n")
    .replace("\r", "\\r")
    .replace("\t", "\\t")
)
```

---

### `src/linux_python_utils/dotconf/__init__.py`

#### Modifications
Ajouter l'import et l'entrée `__all__` :

```python
from linux_python_utils.dotconf.conf_toml_exporter import ConfTomlExporter

__all__ = [
    # ... existants ...
    "ConfTomlExporter",
]
```

---

## Conventions PEP

- [x] PEP 8  — Imports ordonnés : stdlib → local
- [x] PEP 8  — Nommage : `snake_case` méthodes, `PascalCase` classe
- [x] PEP 8  — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring Google Style sur chaque méthode publique et privée
- [x] PEP 484 — Type hints complets
- [x] PEP 20  — Une seule méthode publique ; parse et render séparés mais co-localisés

## Principes SOLID

| Principe | Question clé | Statut |
|---|---|---|
| **S** Single Responsibility | `ConfTomlExporter` ne fait qu'exporter conf→TOML | ✅ |
| **O** Open/Closed | Extension du parseur = sous-classe ou nouvelle méthode `_parse_*` | ✅ |
| **L** Liskov Substitution | Pas d'héritage | N/A |
| **I** Interface Segregation | Une seule méthode publique ciblée | ✅ |
| **D** Dependency Inversion | Pas de dépendances externes injectables nécessaires | ✅ |

---

## Tests — `tests/test_dotconf_conf_toml_exporter.py`

### Fixtures
```python
@pytest.fixture
def exporter() -> ConfTomlExporter:
    return ConfTomlExporter()
```

### Cas à couvrir

| Test | Scenario | Assert |
|---|---|---|
| `test_export_flat_file_produces_content_blocks` | `.zshrc` avec 2 lignes | TOML contient `file_path` + 2 blocs `[[target.content]]` |
| `test_export_flat_file_no_section_field` | fichier plat | aucun `section =` dans TOML |
| `test_export_comment_attached_to_next_block` | `# alias\nalias ll=…` | `comment = "# alias"` dans le bloc `alias ll=…` |
| `test_export_empty_lines_ignored` | contenu avec lignes vides | pas de bloc vide |
| `test_export_orphan_comment_ignored` | commentaire en fin de fichier sans contenu suivant | pas de bloc avec contenu vide |
| `test_export_ini_file_section_field_present` | `dnf.conf` avec `[main]` | `section = "main"` dans les blocs |
| `test_export_ini_section_header_not_in_content` | `[main]` dans source | `[main]` n'apparaît pas comme `content =` |
| `test_export_special_chars_escaped` | contenu avec `\` et `"` | séquences `\\` et `\"` dans TOML |
| `test_export_file_path_is_absolute` | source relative (via `tmp_path`) | `file_path` dans TOML est absolu |
| `test_export_source_not_found_raises` | source inexistante | `pytest.raises(FileNotFoundError)` |
| `test_export_creates_dest_parent_dirs` | dest dans sous-répertoire inexistant | fichier créé sans erreur |
| `test_round_trip_with_toml_spec_loader` | export puis rechargement via `TomlSpecLoader` | `spec.file_path` == `source.resolve()`, `len(spec.blocks)` correct |

---

## Checklist d'implémentation

### Code
- [ ] Créer `src/linux_python_utils/dotconf/conf_toml_exporter.py`
- [ ] Modifier `src/linux_python_utils/dotconf/__init__.py`

### Tests (pytest)
- [ ] Créer `tests/test_dotconf_conf_toml_exporter.py` avec les 12 cas ci-dessus
- [ ] `pytest tests/test_dotconf_conf_toml_exporter.py -v`
- [ ] Couverture ≥ 95 %

### Documentation
- [ ] Docstrings PEP 257 complètes
- [ ] `__init__.py` — docstring module mise à jour

---

## Points d'attention

- **Ordre d'échappement** : `\\` doit être remplacé EN PREMIER dans `_toml_escape`,
  sinon les autres remplacements introduiraient de faux `\\`.
- **Section header INI** : la ligne `[main]` ne doit PAS devenir un bloc de contenu ;
  elle met à jour `current_section` uniquement.
- **Commentaires orphelins** : un commentaire sans contenu suivant (fin de fichier ou
  suivi d'une ligne vide) est silencieusement ignoré — comportement intentionnel.
- **Fichiers avec BOM** : `read_text(encoding="utf-8")` gère le BOM utf-8-sig si
  présent sur certains fichiers Windows.
- **Multi-ligne dans `comment`** : plusieurs commentaires consécutifs sont joints par
  `\n` → encodé `\\n` dans le TOML → rechargé comme un seul champ multi-ligne.
  `ConfigApplier` insère ce texte verbatim avant le bloc, ce qui est correct.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
