# MODULE VALIDATION — RENOMMAGE PEP 8 & CHECK ANTI-SYMLINK
> **Date :** 2026-06-05 à 14:10
> **Complexité estimée :** Faible
> **Verdict revue :** Go conditionnel
> **Source :** `PLAN_ACTION_REVUE.md` § validation

---

## Contexte

### Problématique
- `path_checker_Exist.py` : nom de module non conforme PEP 8 (majuscule).
- `path_checker_world_writable.py:38-42` : `exists()` puis `stat()` (suit les
  symlinks) sur un **check de sécurité** utilisé avant chargement en root →
  TOCTOU + substitution via symlink.
- `path_checker_permission.py:56` : `os.access()` (TOCTOU, ignore les ACL).

### Solution technique retenue
Renommer le module. Rendre le check world-writable atomique/anti-symlink via
`os.lstat` (ne suit pas les liens) ou `os.open(O_NOFOLLOW)` + `os.fstat`.

### Fichiers impactés
- `src/linux_python_utils/validation/path_checker_Exist.py` → `path_checker_exist.py`
- `src/linux_python_utils/validation/path_checker_world_writable.py`
- `src/linux_python_utils/validation/__init__.py`
- `tests/test_validation.py`

---

## Évolutions à mettre en place (Détail Junior)

### Renommage 🟠 MAJEUR
1. `git mv src/linux_python_utils/validation/path_checker_Exist.py \
       src/linux_python_utils/validation/path_checker_exist.py`
2. Mettre à jour l'import dans `validation/__init__.py:4`.
3. Vérifier qu'aucun autre fichier (ni test) n'importe l'ancien nom :
   `grep -rn "path_checker_Exist" src/ tests/`.

### `path_checker_world_writable.py` — 🟠 MAJEUR (anti-symlink)
```python
import os
import stat

def _est_world_writable(self, path: str) -> bool:
    """Teste le bit world-writable sans suivre les symlinks."""
    try:
        st = os.lstat(path)  # lstat : ne suit PAS les liens
    except FileNotFoundError:
        return False
    return bool(st.st_mode & stat.S_IWOTH)
```
Remplacer le `exists()` + `stat()` (l.38-41) par cet appel unique `lstat`.

### Optimisation (🟡)
- [ ] `path_checker_world_writable.py:5` : `Union[str, Path]` → `str | Path`.
- [ ] Harmoniser l'API d'entrée (certains checkers prennent `list[str]`, un autre
      `str | Path`) — documenter ou uniformiser.
- [ ] `path_checker_permission.py` : documenter que `os.access` est préventif
      (message d'erreur), pas une garde de sécurité atomique.

### Gestion d'erreurs
| Cas | Condition | Action |
|---|---|---|
| Chemin absent | `lstat` → `FileNotFoundError` | `return False` |
| Symlink | `lstat` lit le lien, pas la cible | comportement correct |

---

## Analyse de sécurité (Bandit)
- [ ] Check world-writable ne suit plus les symlinks.
- [ ] `.resolve()` anti-traversal conservé sur les autres checkers.
- [ ] `bandit -r src/linux_python_utils/validation/ -ll -ii`

---

## Checklist d'implémentation

### Code
- [x] `git mv` + MAJ `__init__.py`
- [x] `path_checker_world_writable.py` — `os.lstat`
- [x] Typing `str | Path`

### Tests (pytest)
- [x] `test_world_writable_ne_suit_pas_symlink()`
- [x] `test_import_path_checker_exist_nouveau_nom()`
- [x] 12/12 passed, bandit 0 issue

### Documentation
- [x] Note sur la sémantique préventive d'`os.access`

---

## Points d'attention
- Utiliser `git mv` (pas Write+suppression) pour préserver l'historique.
- Le renommage est un **breaking change** si l'ancien nom était importé
  directement par un projet aval → vérifier et documenter dans le CHANGELOG.

---

## ⏸ Validation requise
**Aucun code modifié avant approbation.** Répondre **"OK"** pour démarrer.
