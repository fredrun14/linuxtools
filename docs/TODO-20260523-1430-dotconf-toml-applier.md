# INTÉGRATION TOML CONFIG APPLIER DANS DOTCONF
> **Date :** 2026-05-23 à 14:30
> **Complexité estimée :** Moyenne

---

## Contexte

### Problématique
Le module `dotconf` de `linux_python_utils` fournit `SectionAwareEditor` pour éditer
des fichiers `.conf` ligne par ligne en préservant commentaires et formatage. Mais il
n'existe aucun composant permettant de décrire ces modifications de façon déclarative
via un fichier TOML et de les appliquer automatiquement. Cette capacité est actuellement
dispersée dans le projet applicatif `config-file-manager`.

### Solution technique retenue
Ajouter trois nouveaux fichiers dans `dotconf/` sans toucher à l'existant :

| Fichier | Rôle |
|---------|------|
| `spec.py` | Modèles de données purs : `ConfigBlock` + `ConfigSpec` |
| `toml_spec_loader.py` | `TomlSpecLoader` : lit un TOML → produit un `ConfigSpec`, résout les chemins |
| `applier.py` | `ConfigApplier` : applique un `ConfigSpec` sur un fichier cible via `SectionAwareEditor` |

**Alternatives écartées :**
- Porter la logique dans `manager.py` : `LinuxIniConfigManager` utilise `configparser`
  qui détruit les commentaires — incompatible avec les fichiers plats (yt-dlp style).
- Ajouter un paramètre TOML à `SectionAwareEditor` : violerait SRP (l'éditeur ne doit
  pas connaître le format de spécification).

**Format TOML retenu (`target`, clé générique anglaise) :**
```toml
[target]
file_path = "~/.config/yt-dlp/config"

[[target.content]]
comment = "# Quality"
content = '-f "bestvideo*+bestaudio/best"'

[[target.content]]
section = "main"
comment = "# Fastestmirror"
content = "fastestmirror=True"
```

### Fichiers impactés
- `src/linux_python_utils/dotconf/spec.py` — NOUVEAU : dataclasses pures
- `src/linux_python_utils/dotconf/toml_spec_loader.py` — NOUVEAU : loader TOML
- `src/linux_python_utils/dotconf/applier.py` — NOUVEAU : applier via SectionAwareEditor
- `src/linux_python_utils/dotconf/__init__.py` — MODIFIÉ : exports des nouveaux symboles
- `tests/test_dotconf_spec.py` — NOUVEAU : tests ConfigBlock + ConfigSpec
- `tests/test_dotconf_toml_spec_loader.py` — NOUVEAU : tests TomlSpecLoader
- `tests/test_dotconf_applier.py` — NOUVEAU : tests ConfigApplier

---

## Évolutions à mettre en place (Détail Junior)

---

### `src/linux_python_utils/dotconf/spec.py` (NOUVEAU)

#### Imports à ajouter
```python
# stdlib
from dataclasses import dataclass, field
from pathlib import Path
```

#### Signatures
```python
@dataclass
class ConfigBlock:
    """Représente un bloc de configuration issu d'une spec TOML.

    Attributes:
        content: Ligne(s) de configuration active(s).
        comment: Ligne de commentaire précédant le bloc (vide si absent).
        section: Nom de la section INI cible. None pour les fichiers plats.
    """
    content: str
    comment: str = ""
    section: str | None = None


@dataclass
class ConfigSpec:
    """Spécification complète d'une application de configuration.

    Attributes:
        file_path: Chemin absolu résolu du fichier cible.
        blocks: Liste ordonnée des blocs à appliquer.
    """
    file_path: Path
    blocks: list[ConfigBlock] = field(default_factory=list)
```

#### Logique détaillée
1. `ConfigBlock` — dataclass simple, pas de méthodes. `content` obligatoire,
   `comment` et `section` optionnels avec valeurs par défaut.
2. `ConfigSpec` — dataclass simple. `file_path` est un `Path` déjà résolu
   (la résolution `~`/`$VAR` est faite par `TomlSpecLoader`).
3. Pas d'imports de modules `linux_python_utils` — ce fichier doit rester sans
   dépendances internes pour être importable partout.

#### Conventions PEP
- [x] PEP 8  — Imports ordonnés (stdlib uniquement ici)
- [x] PEP 8  — Nommage : `PascalCase` classes, `snake_case` champs
- [x] PEP 8  — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstrings Google Style sur chaque dataclass
- [x] PEP 484 — Type hints complets sur tous les champs
- [x] PEP 20  — Simple : deux dataclasses, aucune logique

#### Principes SOLID
| Principe | Statut |
|----------|--------|
| **S** Single Responsibility | `ConfigBlock` = données d'un bloc. `ConfigSpec` = données d'une spec. Une raison de changer chacune. ✅ |
| **O** Open/Closed | Dataclasses figées, extension via sous-classes si besoin ✅ |
| **L** Liskov | Pas d'héritage ✅ |
| **I** Interface Segregation | Pas d'interface superflue ✅ |
| **D** Dependency Inversion | Zéro dépendance ✅ |

---

### `src/linux_python_utils/dotconf/toml_spec_loader.py` (NOUVEAU)

#### Imports à ajouter
```python
# stdlib
import os
from pathlib import Path
from typing import Any

# local
from linux_python_utils.config import FileConfigLoader
from linux_python_utils.config.base import ConfigLoader
from linux_python_utils.dotconf.spec import ConfigBlock, ConfigSpec
```

#### Signatures
```python
class TomlSpecLoader:
    """Charge un fichier TOML de spécification et produit un ConfigSpec.

    Le format TOML attendu :

        [target]
        file_path = "~/.config/app/config"

        [[target.content]]
        comment = "# Section title"
        content = "key = value"
        section = "main"   # optionnel

    Attributes:
        _loader: Chargeur de configuration injectable.
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

    def _resolve_path(self, raw_path: str) -> Path:
        """Résout ~, $VAR, ${VAR} et retourne un Path absolu.

        Args:
            raw_path: Chemin brut avec éventuels tilde et variables.

        Returns:
            Path absolu après expansion et résolution.
        """

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
```

#### Logique détaillée

**`__init__`**
1. Stocker `loader or FileConfigLoader()` dans `self._loader`.

**`load`**
1. Appeler `self._loader.load(spec_path)` → `data: dict[str, Any]`
   (FileConfigLoader lève `FileNotFoundError` si absent, gère TOML nativement).
2. Accéder à `data["target"]` (lève `KeyError` si absent — l'appelant gère).
3. Appeler `self._resolve_path(target["file_path"])` → `Path`.
4. Appeler `self._parse_blocks(target)` → `list[ConfigBlock]`.
5. Retourner `ConfigSpec(file_path=resolved, blocks=blocks)`.

**`_resolve_path`**
1. `os.path.expandvars(raw_path)` → résout `$VAR` et `${VAR}`.
2. `Path(result).expanduser()` → résout `~`.
3. `.resolve()` → chemin absolu canonique.
4. Retourner le `Path`.
> Note : pas de validation de zone ici (responsabilité du projet appelant).

**`_parse_blocks`**
1. `raw_blocks = target.get("content", [])`.
2. Pour chaque `item` avec son index `i` :
   - `content = item.get("content")`.
   - Si `content` est vide/None → `raise ValueError(f"Bloc #{i+1} sans clé 'content'")`.
   - Créer `ConfigBlock(content=str(content), comment=str(item.get("comment", "")), section=item.get("section"))`.
3. Retourner la liste.

#### Gestion d'erreurs
| Cas | Condition | Action |
|-----|-----------|--------|
| Fichier TOML absent | `spec_path` inexistant | `FileConfigLoader` lève `FileNotFoundError` — propager |
| Clé `target` manquante | `data["target"]` absent | `KeyError` naturelle — propager |
| `file_path` manquant | `target["file_path"]` absent | `KeyError` naturelle — propager |
| Bloc sans `content` | `item.get("content")` falsy | `raise ValueError(f"Bloc #{i+1} sans clé 'content'")` |

#### Conventions PEP
- [x] PEP 8  — Imports ordonnés : stdlib → local
- [x] PEP 8  — `snake_case` méthodes, `PascalCase` classe
- [x] PEP 257 — Docstrings Google Style avec Args/Returns/Raises
- [x] PEP 484 — Tous les paramètres et retours typés
- [x] PEP 20  — Pas de logique de validation de zone (YAGNI ici)

#### Principes SOLID
| Principe | Statut |
|----------|--------|
| **S** Single Responsibility | Une seule tâche : TOML → ConfigSpec ✅ |
| **O** Open/Closed | `ConfigLoader` injectable → extensible sans modifier la classe ✅ |
| **D** Dependency Inversion | `loader: ConfigLoader` injecté via `__init__`, pas instancié en dur ✅ |

---

### `src/linux_python_utils/dotconf/applier.py` (NOUVEAU)

#### Imports à ajouter
```python
# stdlib
from pathlib import Path

# local
from linux_python_utils.dotconf.line_editor import SectionAwareEditor
from linux_python_utils.dotconf.spec import ConfigBlock, ConfigSpec
from linux_python_utils.logging.base import Logger
```

#### Signatures
```python
class ConfigApplier:
    """Applique un ConfigSpec sur un fichier de configuration cible.

    Utilise SectionAwareEditor pour toutes les modifications de fichier,
    garantissant la préservation des commentaires et du formatage existant.

    Attributes:
        _logger: Logger optionnel pour tracer chaque action.
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise l'applier avec un logger optionnel.

        Args:
            logger: Instance de Logger. Si None, aucun log n'est émis.
        """

    def apply(self, spec: ConfigSpec) -> list[str]:
        """Applique tous les blocs de la spec sur le fichier cible.

        Si le fichier n'existe pas, il est créé avec tous les blocs.
        Sinon, chaque bloc est traité individuellement (ajout, décommentage
        ou ignoré s'il est déjà présent).

        Args:
            spec: ConfigSpec contenant le chemin cible et les blocs.

        Returns:
            Liste des actions effectuées. Liste vide si aucune modification.

        Raises:
            PermissionError: Si l'écriture sur le fichier est refusée.
        """

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
```

#### Logique détaillée

**`__init__`**
1. `self._logger = logger`.

**`apply`**
1. `target = spec.file_path`.
2. Si `not target.exists()` → appeler `self._create_file(target, spec.blocks)` et retourner.
3. Sinon, pour chaque `block` dans `spec.blocks` :
   - `action = self._apply_block(target, block)`
   - Si `action` non None → l'ajouter à `actions`.
4. Si `actions` non vide → `target.chmod(0o644)`.
5. Retourner `actions`.

**`_apply_block`**
1. `editor = SectionAwareEditor(target)`.
2. Si `editor.is_block_present(block.content, block.section)` → retourner `None` (déjà présent).
3. `was_commented = editor.is_block_commented(block.content, block.section)`.
4. `editor.ensure_block(block.content, block.section, block.comment)` → modifie le fichier.
5. `first_line = block.content.splitlines()[0][:50]`.
6. Construire le message :
   - Si `was_commented` → `f"Uncommented: {first_line}"`
   - Sinon si `block.section` → `f"Added to [{block.section}]: {first_line}"`
   - Sinon → `f"Appended: {first_line}"`
7. Si `self._logger` → `self._logger.log_info(f"{action} in {target}")`.
8. Retourner le message.

**`_create_file`**
1. `target.parent.mkdir(parents=True, mode=0o755, exist_ok=True)`.
2. Pour chaque `block` dans `blocks` :
   - `SectionAwareEditor(target).ensure_block(block.content, block.section, block.comment)`.
3. `target.chmod(0o644)`.
4. `action = f"Created: {target} ({len(blocks)} blocks)"`.
5. Si `self._logger` → `self._logger.log_info(action)`.
6. Retourner `[action]`.

#### Gestion d'erreurs
| Cas | Condition | Action |
|-----|-----------|--------|
| Fichier inaccessible | `PermissionError` lors de l'écriture | Propager (`SectionAwareEditor._write_lines` lève nativement) |
| Bloc vide | `block.content` vide | `SectionAwareEditor.ensure_block` retourne `False` sans modifier — `_apply_block` retourne `None` |

#### Conventions PEP
- [x] PEP 8  — Imports ordonnés : stdlib → local
- [x] PEP 257 — Docstrings Google Style
- [x] PEP 484 — Tous les types annotés, `Logger | None`
- [x] PEP 20  — Pas de sanitisation (responsabilité du caller), pas de path traversal check (idem)

#### Principes SOLID
| Principe | Statut |
|----------|--------|
| **S** Single Responsibility | Applique des blocs sur un fichier. Ne lit pas le TOML, ne résout pas les chemins. ✅ |
| **O** Open/Closed | `SectionAwareEditor` injectable si besoin (évolution future possible) ✅ |
| **D** Dependency Inversion | `Logger` injecté via `__init__`, pas instancié en dur ✅ |

---

### `src/linux_python_utils/dotconf/__init__.py` (MODIFIÉ)

#### Ajouts à la fin du bloc d'imports et de `__all__`

Ajouter après les imports existants :
```python
from linux_python_utils.dotconf.applier import ConfigApplier
from linux_python_utils.dotconf.spec import ConfigBlock, ConfigSpec
from linux_python_utils.dotconf.toml_spec_loader import TomlSpecLoader
```

Ajouter dans `__all__` :
```python
    # Nouvelles classes — spec TOML + applier
    "ConfigBlock",
    "ConfigSpec",
    "TomlSpecLoader",
    "ConfigApplier",
```

---

## Checklist d'implémentation

### Code
- [ ] Créer `src/linux_python_utils/dotconf/spec.py`
- [ ] Créer `src/linux_python_utils/dotconf/toml_spec_loader.py`
- [ ] Créer `src/linux_python_utils/dotconf/applier.py`
- [ ] Modifier `src/linux_python_utils/dotconf/__init__.py`

### Tests (pytest)
- [ ] Créer `tests/test_dotconf_spec.py`
  - `test_config_block_default_values` — comment="" et section=None par défaut
  - `test_config_block_with_all_fields` — tous les champs assignés correctement
  - `test_config_spec_default_blocks` — blocks=[] par défaut
  - `test_config_spec_with_blocks` — file_path + blocks stockés correctement
- [ ] Créer `tests/test_dotconf_toml_spec_loader.py`
  - `test_load_flat_file_spec_returns_config_spec` — fichier sans section
  - `test_load_ini_file_spec_returns_blocks_with_section` — fichier avec section
  - `test_load_resolves_tilde_in_file_path` — `~` → chemin absolu réel
  - `test_load_resolves_env_var_in_file_path` — `$HOME` → chemin absolu réel
  - `test_load_raises_key_error_if_target_missing` — clé `target` absente
  - `test_load_raises_key_error_if_file_path_missing` — clé `file_path` absente
  - `test_load_raises_value_error_if_content_missing` — bloc sans `content`
  - `test_load_raises_file_not_found_if_toml_missing` — fichier TOML absent
- [ ] Créer `tests/test_dotconf_applier.py`
  - `test_apply_creates_new_file_when_absent` — fichier créé, action retournée
  - `test_apply_creates_parent_dirs_when_missing` — dossiers parents créés
  - `test_apply_appends_missing_block_to_existing_file` — bloc ajouté
  - `test_apply_uncomments_commented_block` — bloc décommenté, action "Uncommented"
  - `test_apply_skips_already_present_block` — retourne liste vide
  - `test_apply_adds_block_to_ini_section` — insertion dans section INI
  - `test_apply_returns_empty_list_when_no_changes` — idempotence
  - `test_apply_calls_logger_when_provided` — logger.log_info appelé
  - `test_apply_no_logger_does_not_raise` — fonctionne sans logger
  - `test_apply_sets_chmod_644_after_modification` — permissions vérifiées

### Documentation
- [ ] Vérifier que le module docstring de `__init__.py` mentionne les nouvelles classes
- [ ] `CHANGELOG.md` : ajouter entrée `feat(dotconf): TomlSpecLoader + ConfigApplier`

---

## Points d'attention

1. **`ConfigLoader` vs `FileConfigLoader`** — `TomlSpecLoader.__init__` accepte
   `ConfigLoader | None` (l'ABC de `linux_python_utils.config.base`). Vérifier
   que `ConfigLoader` est bien exporté par `linux_python_utils.config`.

2. **`Logger` importé depuis `base`** — utiliser
   `from linux_python_utils.logging.base import Logger` (l'ABC), pas une
   implémentation concrète, pour respecter DIP.

3. **mypy strict** — `list[ConfigBlock] = field(default_factory=list)` doit
   passer mypy strict. Vérifier que les dataclasses sont correctement annotées.

4. **Idempotence** — `apply()` appelé deux fois sur le même fichier doit
   retourner `[]` au second appel. C'est garanti par `SectionAwareEditor.is_block_present`.

5. **`target.chmod(0o644)`** — uniquement si des modifications ont été faites.
   Si aucun bloc modifié, ne pas toucher aux permissions.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
