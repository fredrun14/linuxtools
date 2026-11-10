# CLAUDE.md

## Projet

**linuxtools** — bibliothèque utilitaire Python pour Linux (français).

- Python 3.11+ · stdlib uniquement · Linux only
- Dépendances optionnelles : `pydantic>=2.0`, `python-dotenv`, `keyring`

## Conventions propres au projet

- Ligne max **79** ; docstrings en **français** (modules, classes, fonctions publiques)
- Toutes les classes acceptent un `Logger` optionnel (injection de dépendances)
- `mypy --strict` à zéro et bloquant (règle de `../CLAUDE.md`). Une régression ici ne
  casse pas que ce dépôt : elle redonne aux consommateurs le prétexte « la lib n'est
  pas typée » pour relâcher leur propre configuration. `py.typed` (PEP 561) est
  exposé — ce prétexte doit rester mort.

## Release : répercuter sur les consommateurs

Chaque nouvelle version livrée sur `master` (tag `vX.Y.Z`) **doit être reportée
dans tous les projets qui utilisent linuxtools** — ils l'épinglent par tag Forgejo
(`linuxtools @ git+https://git.ricfasohel.fr/fred/linuxtools.git@vX.Y.Z`), donc
rien ne se propage seul. Après le tag :

1. Simuler : `make bump-consumers TAG=vX.Y.Z ARGS="--dry-run"` (sondes seules,
   rien d'écrit). Restreindre avec `ARGS="--only NOM"` / `--exclude NOM`.
2. Lancer pour de bon : `make bump-consumers TAG=vX.Y.Z`. Pour chaque
   consommateur la commande pousse une branche `chore/pin-linuxtools-X-Y-Z`
   (worktree temporaire, `uv sync --no-sources`, contrôles de son contrat
   `[tool.linuxtools.consumer]`) ; `--no-push` s'arrête au commit. Détail :
   `README.md`, § *Monter le pin des consommateurs*.
3. **Une PR par consommateur, ouverte à la main** : la commande ne crée ni PR,
   ni tag, ni force-push. Un consommateur laissé en retard est un choix assumé
   et consigné, pas un oubli.
   Limites : un projet sans contrat est REFUSÉ ; `scanNetHome` reste BLOQUÉ tant
   que `webapitools` (sa dépendance maison, épinglée par tag) n'a pas de tag
   référençant la nouvelle version : la commande le rapporte sans le contourner,
   et le tag de `webapitools` se crée à la main. Un vert local ne garantit pas la
   CI du consommateur : la CI Forgejo reste juge.
4. Les copies déployées sur le nœud pve (`/opt/<appli>/venv`) ne suivent qu'à
   leur redéploiement.

## Commandes et architecture

Commandes : `Makefile` et `README.md`. Modules : un répertoire par domaine sous
`src/linuxtools/` (README, § *Structure du Projet*) ; API publique exportée
depuis `src/linuxtools/__init__.py`.

## Patterns clés

- **TOCTOU-safe** : `os.open(O_NOFOLLOW)` + `os.fchmod(0o644)` dans les classes de base
- **Validation noms** : regex + anti-traversal dans `systemd/validators.py`
- **UTF-8 explicite** partout (docstrings français)

## Notes Obsidian

Notes pédagogiques (public : développeur junior, apprentissage Python/SOLID/sécurité
Linux), dans `~/obsidian-perso/fredvault/1-projets/linuxtools/` (hors dépôt). À
mettre à jour après tout ajout ou modification d'API publique.
