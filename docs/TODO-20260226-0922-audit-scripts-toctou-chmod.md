# AUDIT SÉCURITÉ MODULE SCRIPTS — TOCTOU CHMOD
> **Date :** 2026-02-26 à 09:22
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit sécurité du module `scripts/` (4 skills). Un problème TOCTOU identifié
dans `BashScriptInstaller._set_executable()` :

**Séquence actuelle dans `install()` :**
```
1. file_manager.create_file(path, content)   → crée le fichier
2. os.chmod(path, self._default_mode)         → chmod par chemin (TOCTOU)
```

Entre les étapes 1 et 2, une fenêtre de temps (étroite mais réelle) permet à un
attaquant local avec accès au répertoire de :
- Remplacer le fichier par un lien symbolique vers `/etc/shadow` ou un autre
  fichier sensible
- Le `os.chmod()` suivant appliquera alors le mode 0o755 sur le fichier cible
  du symlink, potentiellement rendant readable un fichier normalement protégé

Le risque est **LOW** en pratique (nécessite un accès local + timing précis),
mais la correction est triviale et suit le pattern TOCTOU-safe déjà utilisé
dans le module `systemd/` (O_NOFOLLOW + fchmod).

**Contexte d'utilisation :** `BashScriptInstaller` installe des scripts sous
`/usr/local/bin/` ou des répertoires systemd. Les scripts sont souvent installés
par root — ce qui amplifie l'impact si le TOCTOU est exploité.

### Solution technique retenue

Remplacer `os.chmod(path, mode)` par une séquence fd-safe :
1. `fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` — ouvre par fd, refuse
   les symlinks
2. `os.fchmod(fd, mode)` — chmod via fd (pas de TOCTOU)
3. `os.close(fd)` — ferme le fd

**Alternative écartée** : modifier `FileManager.create_file()` pour retourner
un fd. Écarté car cela changerait l'API publique de `FileManager` et sortirait
du périmètre de ce module.

**Alternative écartée** : utiliser `pathlib.Path.chmod()`. Écarté car
`Path.chmod()` appelle `os.chmod()` par chemin — même TOCTOU.

### Fichiers impactés

- `linux_python_utils/scripts/installer.py` — méthode `_set_executable()`

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/scripts/installer.py`

#### Imports — aucun changement

`import os` est déjà présent en ligne 16.

#### Correction de `_set_executable()` — pattern fd-safe

**Avant :**
```python
    def _set_executable(self, path: str) -> bool:
        """Rend le script exécutable.

        Args:
            path: Chemin du script.

        Returns:
            True si l'opération a réussi, False sinon.
        """
        try:
            os.chmod(path, self._default_mode)
            return True
        except OSError as e:
            self._logger.log_error(
                f"Impossible de rendre le script exécutable : {e}"
            )
            return False
```

**Après :**
```python
    def _set_executable(self, path: str) -> bool:
        """Rend le script exécutable via fd (TOCTOU-safe).

        Utilise O_NOFOLLOW pour refuser les liens symboliques,
        puis fchmod pour appliquer les permissions via le fd.

        Args:
            path: Chemin du script.

        Returns:
            True si l'opération a réussi, False sinon.
        """
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fchmod(fd, self._default_mode)
            finally:
                os.close(fd)
            return True
        except OSError as e:
            self._logger.log_error(
                f"Impossible de rendre le script exécutable : {e}"
            )
            return False
```

**Logique détaillée :**
1. `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` — ouvre le fichier par fd.
   `O_NOFOLLOW` : si `path` est un symlink, lève `OSError(ELOOP)` et refuse
   l'opération → protection anti-TOCTOU.
2. `os.fchmod(fd, self._default_mode)` — applique les permissions directement
   sur le fd, sans passer par le chemin → pas de fenêtre de race condition.
3. `finally: os.close(fd)` — ferme toujours le fd, même si `fchmod` échoue.
4. `except OSError as e` — capture toutes les erreurs (ELOOP, EPERM, etc.) et
   les logue via `log_error` comme avant.

#### Docstring — Note à ajouter dans `install()`

```
        Note:
            La permission d'exécution est appliquée via os.fchmod()
            (fd-safe, TOCTOU-safe) pour éviter les attaques par
            substitution de lien symbolique.
```

#### Conventions PEP

- [x] PEP 8 — Indentation, lignes ≤ 79 caractères
- [x] PEP 257 — Docstring `_set_executable()` mise à jour
- [x] PEP 484 — Signature inchangée
- [x] PEP 20 — `try/finally` explicite pour garantir la fermeture du fd

---

## Analyse de sécurité

### OWASP Top 10

- [x] A01 Broken Access Control — TOCTOU sur chmod corrigé (O_NOFOLLOW + fchmod)
- [x] A04 Insecure Design — Pattern fd-safe cohérent avec `systemd/base.py`

### Analyse statique Bandit

- [x] Aucun issue Bandit sur `scripts/` — confirmé avant et après correction

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | `_set_executable()` reste responsable uniquement du chmod | ✅ |
| **D** Dependency Inversion | Logger injecté (inchangé) | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `installer.py` — `_set_executable()` : remplacer `os.chmod(path, mode)`
    par `fd = os.open(..., O_RDONLY | O_NOFOLLOW)` + `os.fchmod(fd, mode)` +
    `finally: os.close(fd)`
- [ ] `installer.py` — docstring `_set_executable()` : mention TOCTOU-safe
- [ ] `installer.py` — Note dans docstring de `install()`

### Tests (pytest, dans `tests/test_scripts.py`)
- [ ] `test_set_executable_refuse_les_symlinks`
    — créer un lien symbolique, appeler `_set_executable()`, vérifier que
    `log_error` est appelé (ELOOP) et que False est retourné
- [ ] `test_set_executable_applique_le_mode_correct`
    — créer un vrai fichier, appeler `_set_executable()`, vérifier le mode
    résultant avec `os.stat()`

### Validation
- [ ] `pytest tests/test_scripts.py -v` → tous verts
- [ ] `make test` → zéro régression

---

## Points d'attention

- Sur certains systèmes de fichiers (FAT32, NTFS via samba), `O_NOFOLLOW`
  peut ne pas être disponible. Sur Linux standard (ext4, xfs, btrfs),
  `O_NOFOLLOW` est toujours supporté (depuis kernel 2.1.126).
- `os.O_NOFOLLOW` est disponible en stdlib Python (`os` module) depuis Python
  3.3. Aucune dépendance supplémentaire.
- Le test de symlink nécessite `tmp_path` pytest et `os.symlink()`.
  Vérifier que le test ne crée pas de symlink dans un répertoire protégé.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
