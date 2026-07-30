# CLAUDE.md

## Projet

**linuxtools** — bibliothèque utilitaire Python pour Linux (français).

- Python 3.11+ · stdlib uniquement · Linux only
- Dépendances optionnelles : `pydantic>=2.0`, `python-dotenv`, `keyring`

## Conventions

- **PEP 8** : max-line-length = 79
- **PEP 257** : docstrings en **français** — modules, classes, fonctions publiques
- **PEP 484** : type hints obligatoires sur toutes les signatures
- **SOLID** : ABCs + injection de dépendances · toutes les classes acceptent un `Logger` optionnel
- 🚨 **`mypy --strict` = 0 erreur, BLOQUANT** (`make lint` + CI). Obligatoire dans
  tous les projets Python (cf. `../CLAUDE.md`) ; ici c'est **acquis** depuis la
  v1.11.0 — 0 sur 132 fichiers, après un passage de 33 → 0 sur 13 fichiers.
  Toute régression ici ne casse pas que ce dépôt : elle redonne aux 8
  consommateurs le prétexte « la lib n'est pas typée » pour relâcher leur propre
  configuration. `py.typed` (PEP 561) est exposé — ce prétexte doit rester mort.

## Commandes

```bash
make test          # lancer les tests
make lint          # vérifier PEP 8
make all           # lint + tests + build
pytest tests/test_foo.py::TestBar::test_baz -v  # test ciblé
```

## Architecture

Voir `src/linuxtools/` et `README.md` (section "Modules disponibles") — un répertoire par domaine :
`logging`, `config`, `filesystem`, `systemd`, `commands`, `scripts`,
`notification`, `integrity`, `dotconf`, `validation`, `errors`,
`credentials`, `network`.

API publique exportée depuis `src/linuxtools/__init__.py`.

## Patterns clés

- **TOCTOU-safe** : `os.open(O_NOFOLLOW)` + `os.fchmod(0o644)` dans les classes de base
- **Validation noms** : regex + anti-traversal dans `systemd/validators.py`
- **UTF-8 explicite** partout (docstrings français)

## Notes Obsidian

Notes pédagogiques (public : développeur junior, apprentissage Python/SOLID/sécurité Linux).
Une note par module + une vue d'ensemble. À mettre à jour après tout ajout/modification d'API publique.

> Documentation tenue dans un vault Obsidian personnel, **hors dépôt**.