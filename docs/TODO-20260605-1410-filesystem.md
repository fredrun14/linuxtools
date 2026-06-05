# MODULE FILESYSTEM — PATTERN TOCTOU-SAFE
> **Date :** 2026-06-05 à 14:10
> **Complexité estimée :** Moyenne
> **Verdict revue :** NO-GO (sécurité — TOCTOU/symlink)
> **Source :** `PLAN_ACTION_REVUE.md` § filesystem

---

## Contexte

### Problématique
Le module n'applique pas le pattern TOCTOU-safe imposé par le projet
(`os.open(O_NOFOLLOW)` + `os.fchmod(0o644)`) :
- `linux.py:37` : `open(path, "w")` suit les symlinks, permissions par umask ;
- `backup.py:65,94` : `os.path.exists()` puis `shutil.copy2()` → fenêtre TOCTOU,
  `copy2` suit les symlinks (substitution source/dest possible) ;
- `backup.py:65` : `backup()` ne fait rien si la source est absente mais le
  retourne comme un succès silencieux (illusion de sauvegarde).

### Solution technique retenue
Créer **un helper TOCTOU-safe réutilisable dans ce module** (`filesystem`), car
4 autres modules (logging, systemd/unit_porter, dotconf) ont le même besoin.
Ce module devient la source de vérité du pattern.

### Fichiers impactés
- `src/linux_python_utils/filesystem/linux.py` — écriture sécurisée + helper
- `src/linux_python_utils/filesystem/backup.py` — copie sûre + contrat clair
- `src/linux_python_utils/filesystem/base.py` — compléter l'ABC
- `tests/test_filesystem.py` — tests symlink

---

## Évolutions à mettre en place (Détail Junior)

### `filesystem/linux.py` — 🔴 BLOQUANT

#### Étape 1 — Créer le helper d'écriture sécurisée
```python
import os

def write_text_secure(
    path: str,
    content: str,
    mode: int = 0o644,
    *,
    encoding: str = "utf-8",
) -> None:
    """Écrit un fichier sans suivre les symlinks, avec permissions fixées.

    Args:
        path: Chemin cible.
        content: Contenu texte à écrire.
        mode: Permissions appliquées via fchmod (défaut 0o644).
        encoding: Encodage (défaut UTF-8).

    Raises:
        OSError: Si la cible est un symlink (O_NOFOLLOW) ou erreur d'E/S.
    """
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(path, flags, mode)
    try:
        os.fchmod(fd, mode)  # force le mode même si le fichier existait
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
    except BaseException:
        os.close(fd)  # uniquement si fdopen n'a pas pris la main
        raise
```

> Attention : une fois `os.fdopen(fd)` réussi, c'est le `with` qui ferme le fd.
> Le `os.close(fd)` du `except` ne doit s'exécuter que si l'erreur survient
> AVANT `fdopen`. Structurer le code en conséquence (deux try imbriqués).

#### Étape 2 — `create_file` utilise ce helper
Remplacer `open(file_path, "w")` (l.37) par `write_text_secure(...)`.

#### Étape 3 — Préciser les except
`linux.py:41,77,97` : remplacer `except Exception` par `except OSError` et ne
pas masquer la cause (logger `exc`).

---

### `filesystem/backup.py` — 🔴 BLOQUANT

#### Logique
1. Remplacer `shutil.copy2` par une copie qui ne suit pas les symlinks :
   ouvrir source en `O_RDONLY|O_NOFOLLOW`, dest via `write_text_secure` (ou
   copie binaire fd→fd). Pour des fichiers binaires, lire/écrire par blocs.
2. Clarifier le contrat de `backup()` quand la source est absente :

```python
def backup(self, source: Path) -> bool:
    """Sauvegarde un fichier. Retourne False si la source est absente."""
    if not source.exists():
        self._logger.log_warning(f"Source absente, aucune sauvegarde : {source}")
        return False
    ...
    return True
```

#### Gestion d'erreurs
| Cas | Condition | Action |
|---|---|---|
| Source absente | `not source.exists()` | log warning + `return False` |
| Cible = symlink | `O_NOFOLLOW` → `OSError` | propager |
| Erreur E/S | `OSError` pendant copie | logger + propager |

---

### `filesystem/base.py` — 🟡 MINEUR
Ajouter `read_file` et `delete_file` à l'ABC `FileManager` (déjà implémentés
dans `LinuxFileManager` mais non déclarés → contrat incomplet, viole LSP).

---

## Analyse de sécurité (OWASP / Bandit)
- [x] A01 / TOCTOU — toutes les écritures via `O_NOFOLLOW`.
- [x] `bandit -r src/linux_python_utils/filesystem/ -ll -ii`

---

## Checklist d'implémentation

### Code
- [x] `linux.py` — helper `write_text_secure` 🔴
- [x] `linux.py` — `create_file` utilise le helper + except `OSError`
- [x] `backup.py` — copie anti-symlink + contrat `bool` 🔴
- [x] `base.py` — compléter l'ABC

### Tests (pytest)
- [x] `test_create_file_refuse_symlink()` 🔴
- [x] `test_create_file_fixe_permissions_0644()`
- [x] `test_backup_source_absente_retourne_false()`
- [x] `test_backup_refuse_symlink()`
- [ ] `pytest --cov=src/linux_python_utils/filesystem --cov-report=term-missing`

### Documentation
- [x] Docstring du helper (réutilisable par logging/systemd/dotconf)

---

## Points d'attention
- Ce helper est **réutilisé** par les TODO logging, systemd, dotconf. L'implémenter
  proprement ici en premier ; les autres modules l'importeront.
- Gestion fine du `fd` : ne pas double-fermer (cf. note Étape 1).

---

## ⏸ Validation requise
**Aucun code modifié avant approbation.** Répondre **"OK"** pour démarrer.
