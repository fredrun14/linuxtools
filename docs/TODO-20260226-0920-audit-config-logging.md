# AUDIT SÉCURITÉ MODULE CONFIG — LOGGING (A09)
> **Date :** 2026-02-26 à 09:20
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit sécurité du module `config/` (4 skills). Un seul problème identifié mais
significatif : `ConfigurationManager` dans `manager.py` n'a pas de `Logger`
injecté et utilise `print()` pour signaler les erreurs.

| # | Ligne | Problème | Impact |
|---|-------|----------|--------|
| 1 | 74 | `print(f"Erreur lors du chargement de {self.config_path}: {e}")` | A09 — erreur de chargement de config jamais dans les logs |
| 2 | 75 | `print("Utilisation de la configuration par défaut.")` | A09 — fallback silencieux en production |
| 3 | 79 | `print(f"Fichier non trouvé: {self.config_path}")` | A09 — fichier manquant jamais tracé dans les logs |
| 4 | 203 | `print(f"Configuration créée: {path}")` | Mineur — confirmation sur stdout uniquement |

La classe `ConfigurationManager` respecte SOLID (injection de dépendances via
`config_loader`) mais oublie d'injecter un `Logger`, bien que la convention du
projet l'exige pour toutes les classes (voir CLAUDE.md).

### Solution technique retenue

1. Ajouter `logger: Optional[Logger] = None` dans `__init__` de
   `ConfigurationManager` (optionnel, conserve la compatibilité).
2. Remplacer les 4 `print()` par `self._log_warning()` / `self._log_info()`
   (méthodes privées no-op si `logger is None`).
3. Pas de changement sur les signatures publiques `get()`, `get_section()`, etc.

**Alternative écartée** : rendre le Logger obligatoire. Écarté car
`ConfigurationManager` est utilisé en standalone (scripts, tests) sans logger.
`Optional[Logger]` avec no-op est le pattern standard du projet.

### Fichiers impactés

- `linux_python_utils/config/manager.py` — ajout logger + remplacement print()

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/config/manager.py`

#### Imports à ajouter

```python
# Ajouter en tête des imports locaux (après les imports config)
from linux_python_utils.logging.base import Logger
```

#### Signature de `__init__` modifiée

**Avant :**
```python
    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        default_config: Optional[Dict[str, Any]] = None,
        search_paths: Optional[List[Union[str, Path]]] = None,
        config_loader: Optional[ConfigLoader] = None
    ) -> None:
```

**Après :**
```python
    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        default_config: Optional[Dict[str, Any]] = None,
        search_paths: Optional[List[Union[str, Path]]] = None,
        config_loader: Optional[ConfigLoader] = None,
        logger: Optional[Logger] = None,
    ) -> None:
```

#### Corps de `__init__` — ajout de `self._logger`

Après `self._loader = config_loader or FileConfigLoader()`, ajouter :
```python
        self._logger = logger
```

#### Méthodes privées à ajouter (après `__init__`)

```python
    def _log_warning(self, message: str) -> None:
        """Logue un avertissement si un logger est configuré.

        Args:
            message: Message à logguer.
        """
        if self._logger:
            self._logger.log_warning(message)

    def _log_info(self, message: str) -> None:
        """Logue un message informatif si un logger est configuré.

        Args:
            message: Message à logguer.
        """
        if self._logger:
            self._logger.log_info(message)
```

#### Correction de `_load_config()` — remplacer print() par logger

**Avant :**
```python
    def _load_config(self) -> Dict[str, Any]:
        if self.config_path and self.config_path.exists():
            try:
                user_config = self._loader.load(self.config_path)
                base = self.default_config.copy()
                return self._deep_merge(base, user_config)
            except Exception as e:
                print(f"Erreur lors du chargement de {self.config_path}: {e}")
                print("Utilisation de la configuration par défaut.")
                return self.default_config.copy()
        else:
            if self.config_path:
                print(f"Fichier non trouvé: {self.config_path}")
            return self.default_config.copy()
```

**Après :**
```python
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier via le loader injecté."""
        if self.config_path and self.config_path.exists():
            try:
                user_config = self._loader.load(self.config_path)
                base = self.default_config.copy()
                return self._deep_merge(base, user_config)
            except Exception as e:
                self._log_warning(
                    f"Erreur lors du chargement de {self.config_path}: {e}"
                    " — utilisation de la configuration par défaut."
                )
                return self.default_config.copy()
        else:
            if self.config_path:
                self._log_warning(
                    f"Fichier de configuration non trouvé : "
                    f"{self.config_path} — "
                    "utilisation de la configuration par défaut."
                )
            return self.default_config.copy()
```

#### Correction de `create_default_config()` — remplacer print()

**Avant (ligne ~203) :**
```python
        print(f"Configuration créée: {path}")
```

**Après :**
```python
        self._log_info(f"Configuration créée : {path}")
```

#### Docstring de `__init__` à mettre à jour

Ajouter dans la section Args :
```
            logger: Logger optionnel pour tracer les erreurs de
                chargement. Si None, les erreurs sont silencieuses.
```

#### Conventions PEP

- [x] PEP 8 — Ligne ≤ 79 caractères, trailing comma sur le nouveau paramètre
- [x] PEP 257 — Docstring Google Style sur `_log_warning()` et `_log_info()`
- [x] PEP 484 — `Optional[Logger]` sur le paramètre
- [x] PEP 20 — Pattern no-op identique à tous les autres modules du projet

---

## Analyse de sécurité

### OWASP Top 10

- [x] A09 Logging Failures — Erreurs de chargement de config maintenant
    loggées via logger injecté
- [x] Pas de secrets exposés : le message logue le chemin et l'exception,
    jamais le contenu de la configuration

### Analyse statique Bandit

- [x] Aucun issue Bandit sur `config/` — confirmé avant et après correction

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | Logger optionnel ajouté sans changer la responsabilité | ✅ |
| **D** Dependency Inversion | Logger injecté via `__init__` (pattern standard du projet) | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `manager.py` — import `Logger` depuis `linux_python_utils.logging.base`
- [ ] `manager.py` — paramètre `logger: Optional[Logger] = None` dans `__init__`
- [ ] `manager.py` — `self._logger = logger` dans `__init__`
- [ ] `manager.py` — méthode `_log_warning()`
- [ ] `manager.py` — méthode `_log_info()`
- [ ] `manager.py` — `_load_config()` : remplacer les 2 `print()` par `_log_warning()`
- [ ] `manager.py` — `create_default_config()` : remplacer `print()` par `_log_info()`
- [ ] `manager.py` — docstring `__init__` mise à jour (Args: logger)

### Tests (pytest, dans `tests/test_config.py`)
- [ ] `test_load_config_logue_warning_si_fichier_introuvable`
    — passer un chemin inexistant + mock logger → vérifier `log_warning` appelé
- [ ] `test_load_config_logue_warning_si_erreur_chargement`
    — mock `_loader.load` lançant une exception → vérifier `log_warning` appelé
- [ ] `test_load_config_sans_logger_pas_d_erreur`
    — sans logger, chemin invalide → ne lève pas d'exception
- [ ] `test_load_config_retourne_defaut_si_fichier_manquant_avec_logger`
    — avec logger, fichier manquant → retourne `default_config`

### Validation
- [ ] `pytest tests/test_config.py -v` → tous verts (dont tests existants)
- [ ] `make test` → zéro régression

---

## Points d'attention

- `ConfigurationManager.__init__` appelle `self._load_config()` avant la fin
  de l'initialisation. Le `self._logger` doit être assigné **avant**
  l'appel à `_load_config()` — sinon `_log_warning()` lèverait `AttributeError`.
  Vérifier l'ordre dans `__init__` : d'abord `self._logger = logger`, ensuite
  `self.config = self._load_config()`.
- Les tests existants de `ConfigurationManager` ne passent pas de logger →
  comportement inchangé (no-op), pas de régression.
- Ne pas supprimer le `print()` de `create_default_config()` si les tests
  existants vérifient stdout — adapter les tests d'abord.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
