# MIGRATION VERS SRC/ LAYOUT (PyPA)
> **Date :** 2026-02-26 à 19:21
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Le projet utilise actuellement un **flat layout** : le package `linux_python_utils/`
se trouve directement à la racine du dépôt. Cette disposition présente deux
inconvénients documentés par la PyPA :

1. **Import accidentel non installé** : Python ajoute la racine du projet au
   `sys.path` en mode éditable, ce qui permet d'importer le package _non
   installé_ depuis n'importe quel script lancé à la racine. Le comportement
   testé peut donc différer du comportement en production.
2. **Conflits de noms** : un fichier `network.py` ou `logging.py` à la racine
   masquerait le module stdlib correspondant.

### Solution technique retenue

Déplacer le package dans `src/linux_python_utils/` (**src layout**), recommandé
par la PyPA depuis 2020. Cette opération est purement structurelle :

- Aucun import ne change (tous les imports sont absolus).
- Aucune logique applicative ne change.
- Seuls `pyproject.toml`, `Makefile`, et l'installation locale sont impactés.

Alternative écartée — garder le flat layout : acceptable pour un usage interne,
mais non conforme à la référence PyPA et au skill `python-architecture`.

### Fichiers impactés

| Fichier / Répertoire | Rôle dans le changement |
|---|---|
| `linux_python_utils/` | Déplacé vers `src/linux_python_utils/` (git mv) |
| `pyproject.toml` | `where = ["."]` → `where = ["src"]` |
| `Makefile` | Cible `lint` : chemin `linux_python_utils/` → `src/linux_python_utils/` |
| `linux_python_utils.egg-info/` | Supprimé + régénéré lors de la réinstallation |
| `CLAUDE.md` | Table Architecture : mettre à jour le chemin du package |

---

## Évolutions à mettre en place (Détail Junior)

### Étape 1 — Déplacer le package avec `git mv`

```bash
mkdir -p src
git mv linux_python_utils src/linux_python_utils
```

`git mv` préserve l'historique des fichiers. Ne pas utiliser `mv` seul.

### Étape 2 — Mettre à jour `pyproject.toml`

#### Avant

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["linux_python_utils*"]
```

#### Après

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

La ligne `include` est supprimée : `where = ["src"]` restreint déjà la
découverte au contenu de `src/`, rendant le filtre redondant.

### Étape 3 — Mettre à jour le `Makefile`

#### Cible `lint` — Avant

```makefile
lint:
	pycodestyle linux_python_utils/
```

#### Cible `lint` — Après

```makefile
lint:
	pycodestyle src/linux_python_utils/
```

### Étape 4 — Mettre à jour `CLAUDE.md`

Dans la table Architecture, remplacer la colonne "Contenu clé" si elle
référence `linux_python_utils/xxx` par `src/linux_python_utils/xxx`.

_(Vérifier s'il y a des chemins absolus à mettre à jour.)_

### Étape 5 — Supprimer l'ancien egg-info et réinstaller

```bash
rm -rf linux_python_utils.egg-info/
pip install -e .
```

La réinstallation génère un nouveau `linux_python_utils.egg-info/` à la
bonne localisation (peut être dans `src/` selon la version de setuptools).

### Étape 6 — Vérifier que les tests passent

```bash
make test
```

Résultat attendu : **830 passed**.

### Étape 7 — Vérifier le lint

```bash
make lint
```

Résultat attendu : aucune violation PEP 8.

---

## Checklist d'implémentation

### Structure

- [ ] `mkdir -p src`
- [ ] `git mv linux_python_utils src/linux_python_utils`
- [ ] Vérifier que `src/linux_python_utils/__init__.py` est bien présent

### Configuration

- [ ] `pyproject.toml` — `where = ["src"]`, supprimer `include`
- [ ] `Makefile` — cible `lint` : `src/linux_python_utils/`
- [ ] `CLAUDE.md` — vérifier/corriger les chemins référencés

### Installation & validation

- [ ] `rm -rf linux_python_utils.egg-info/`
- [ ] `pip install -e .`
- [ ] `make test` → 830 passed
- [ ] `make lint` → 0 violation
- [ ] `python -c "import linux_python_utils; print(linux_python_utils.__version__)"` → OK

### Dépendances (pyproject.toml modifié)

- [ ] Aucune dépendance tierce ajoutée — vérification non nécessaire.

### Tests

Aucun nouveau test à écrire : la migration est purement structurelle. Les
830 tests existants servent de filet de sécurité.

### Git

- [ ] `git status` — vérifier que seuls les fichiers attendus sont modifiés
- [ ] Commit atomique : `refactor: migrer vers src/ layout (PyPA)`

---

## Points d'attention

| Risque | Probabilité | Mitigation |
|---|---|---|
| Import cassé en mode non-éditable | Faible | `pip install -e .` suffit |
| PyCharm ne trouve plus le package | Moyenne | Marquer `src/` comme *Sources Root* dans les paramètres du projet |
| `linux_python_utils.egg-info/` en double | Faible | Supprimer manuellement avant réinstallation |
| CI/CD utilisant un chemin codé en dur | N/A | Pas de CI configuré actuellement |

**Note PyCharm** : après la migration, aller dans
_File → Project Structure → Sources_ et marquer `src/` comme Sources Root
pour que l'IDE reconnaisse les imports.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
