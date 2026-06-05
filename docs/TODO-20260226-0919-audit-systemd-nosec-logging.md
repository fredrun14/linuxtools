# AUDIT SÉCURITÉ MODULE SYSTEMD — NOSEC ET LOGGING
> **Date :** 2026-02-26 à 09:19
> **Complexité estimée :** Moyenne

---

## Contexte

### Problématique

Audit sécurité complet du module `systemd/` (4 skills : OWASP, Bandit, safety,
monitoring). Deux catégories de points identifiés :

**Catégorie 1 — 13 faux positifs Bandit (B404, B603, B607) dans 3 fichiers :**

| # | Fichier | Ligne | Code | Justification |
|---|---------|-------|------|---------------|
| 1 | `executor.py` | 3 | B404 | `import subprocess` — module dont systemctl est la raison d'être |
| 2 | `executor.py` | 44 | B603 | `subprocess.run(cmd, ...)` — shell=False, `cmd` = liste hardcodée + args validés |
| 3 | `executor.py` | 285 | B603 | Idem, `UserSystemdExecutor._run_systemctl` |
| 4 | `timer.py` | 4 | B404 | Idem — import justifié |
| 5 | `timer.py` | 139 | B607 | `["systemctl", "list-timers", ...]` — chemin partiel : `systemctl` est binaire système standard `/usr/bin/systemctl` |
| 6 | `timer.py` | 139 | B603 | Idem — shell=False, args hardcodés |
| 7 | `timer.py` | 187 | B607 | Idem — fallback texte |
| 8 | `timer.py` | 187 | B603 | Idem |
| 9 | `user_timer.py` | 4 | B404 | Idem — import justifié |
| 10 | `user_timer.py` | 187 | B607 | `["systemctl", "--user", "list-timers", ...]` |
| 11 | `user_timer.py` | 187 | B603 | Idem |
| 12 | `user_timer.py` | 235 | B607 | Fallback texte |
| 13 | `user_timer.py` | 235 | B603 | Idem |

**Catégorie 2 — A09 : return value de `disable_*()` ignoré dans les méthodes
`remove_*()` de 5 fichiers :**

Les méthodes `remove_service_unit()`, `remove_timer_unit()`, `remove_mount_unit()` appellent
`disable_service()` / `disable_timer()` / `disable_mount()` sans vérifier leur
valeur de retour ni logguer un avertissement si elles échouent. Le disable peut
échouer (unité déjà inactive, permission refusée) sans aucune trace.

### Solution technique retenue

- **Catégorie 1** : annotations `# nosec B404`, `# nosec B603`, `# nosec B607`
  inline sur la première ligne de chaque appel. Même pattern que `runner.py`,
  `scanner.py`, `router.py`.
- **Catégorie 2** : dans chaque `remove_*()`, capturer le retour de `disable_*()`
  et appeler `self.logger.log_warning()` si False. Le disable échoué ne bloque
  PAS la suppression du fichier unit (comportement actuel conservé).

### Fichiers impactés

- `linux_python_utils/systemd/executor.py` — nosec B404, B603×2
- `linux_python_utils/systemd/timer.py` — nosec B404, B607×2, B603×2
- `linux_python_utils/systemd/user_timer.py` — nosec B404, B607×2, B603×2
- `linux_python_utils/systemd/base.py` — log_warning dans remove_service_unit
  et remove_timer_unit (méthodes héritées)
- `linux_python_utils/systemd/mount.py` — log_warning dans remove_mount_unit
- `linux_python_utils/systemd/user_service.py` — log_warning dans
  remove_service_unit
- `linux_python_utils/systemd/user_timer.py` — log_warning dans
  remove_timer_unit (en plus des nosec)

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/systemd/executor.py`

#### Correction nosec B404 (ligne 3)

```python
import subprocess  # nosec B404
```

#### Correction nosec B603 (ligne 44)

```python
        cmd = ["systemctl"] + args
        return subprocess.run(  # nosec B603
            cmd, check=check, capture_output=True, text=True
        )
```

#### Correction nosec B603 (UserSystemdExecutor, ligne ~285)

Même correction — `subprocess.run(  # nosec B603` sur le call correspondant.

---

### `linux_python_utils/systemd/timer.py`

#### Correction nosec B404 (ligne 4)

```python
import subprocess  # nosec B404
```

#### Correction nosec B607 + B603 sur `list-timers` JSON (ligne ~139)

```python
            result = subprocess.run(  # nosec B603 B607
                ["systemctl", "list-timers", "--no-pager",
                 "--output=json"],
                capture_output=True,
                text=True,
                check=False
            )
```

Justification B607 : `"systemctl"` est un binaire système Linux standard,
toujours disponible via `$PATH` (`/usr/bin/systemctl`). Arguments hardcodés,
aucune interpolation.

#### Correction nosec B607 + B603 sur `list-timers` texte (ligne ~187)

```python
            result = subprocess.run(  # nosec B603 B607
                ["systemctl", "list-timers", "--no-pager",
                 "--plain"],
                capture_output=True,
                text=True,
                check=False
            )
```

---

### `linux_python_utils/systemd/user_timer.py`

#### Correction nosec B404 (ligne 4)

```python
import subprocess  # nosec B404
```

#### Correction nosec B607 + B603 (deux occurrences)

Même pattern que `timer.py` — `subprocess.run(  # nosec B603 B607` sur les
deux appels `list-timers`.

#### Correction A09 dans `remove_timer_unit()` (ligne ~147)

**Avant :**
```python
    def remove_timer_unit(self, timer_name: str) -> bool:
        validate_unit_name(timer_name)
        self.disable_timer(timer_name)
        if not self._remove_unit_file(f"{timer_name}.timer"):
            return False
        self.reload_systemd()
        self.logger.log_info(...)
        return True
```

**Après :**
```python
    def remove_timer_unit(self, timer_name: str) -> bool:
        validate_unit_name(timer_name)
        if not self.disable_timer(timer_name):
            self.logger.log_warning(
                f"disable_timer échoué pour {timer_name!r} "
                "(unité peut-être déjà inactive) — "
                "suppression du fichier unit quand même"
            )
        if not self._remove_unit_file(f"{timer_name}.timer"):
            return False
        self.reload_systemd()
        self.logger.log_info(...)
        return True
```

---

### `linux_python_utils/systemd/base.py`

#### Correction A09 dans `remove_service_unit()` (méthode dans UnitManager)

Même pattern : capturer le retour de `self.disable_service(service_name)` et
`self.logger.log_warning(...)` si False.

#### Correction A09 dans `remove_timer_unit()` (méthode dans UnitManager)

Même pattern avec `self.disable_timer(timer_name)`.

---

### `linux_python_utils/systemd/mount.py`

#### Correction A09 dans `remove_mount_unit()`

```python
    def remove_mount_unit(self, mount_path: str) -> bool:
        unit_name = self.path_to_unit_name(mount_path)
        if not self.disable_mount(mount_path):
            self.logger.log_warning(
                f"disable_mount échoué pour {mount_path!r} "
                "(montage peut-être déjà inactif) — "
                "suppression des fichiers unit quand même"
            )
        ...
```

---

### `linux_python_utils/systemd/user_service.py`

#### Correction A09 dans `remove_service_unit()`

Même pattern avec `self.disable_service(service_name)`.

---

## Analyse de sécurité

### Analyse statique Bandit

- [x] B404 — `import subprocess` : faux positif ×3 (executor, timer, user_timer)
    — module dont systemctl est le cœur de métier
- [x] B603 — `subprocess.run` sans shell : faux positif ×6 — shell=False (défaut),
    tous les args sont des listes d'éléments hardcodés ou validés via
    `validate_unit_name()` / `validate_service_name()`
- [x] B607 — Chemin partiel `"systemctl"` : faux positif ×4 — binaire système
    standard, toujours dans `$PATH` sous Linux, non interpolé
- [x] A03 Injection — Tous les noms d'unités validés avant subprocess via
    `validate_unit_name()` (regex `^[a-zA-Z0-9][a-zA-Z0-9:._-]*$` + anti-traversal)

### OWASP Top 10

- [x] A09 Logging — disable_*() return values capturés et loggués (log_warning)
- [x] A03 Injection — Aucun changement nécessaire (validation déjà en place)

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | Logging ajouté dans les classes existantes | ✅ |
| **O** Open/Closed | Comportement étendu (log) sans changer les signatures | ✅ |
| **D** Dependency Inversion | Logger déjà injecté dans toutes les classes | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `executor.py` — `# nosec B404` sur `import subprocess`
- [ ] `executor.py` — `# nosec B603` sur `subprocess.run()` (×2)
- [ ] `timer.py` — `# nosec B404` sur `import subprocess`
- [ ] `timer.py` — `# nosec B603 B607` sur `subprocess.run()` (×2)
- [ ] `user_timer.py` — `# nosec B404` sur `import subprocess`
- [ ] `user_timer.py` — `# nosec B603 B607` sur `subprocess.run()` (×2)
- [ ] `base.py` — `log_warning` dans `remove_service_unit()` si disable échoue
- [ ] `base.py` — `log_warning` dans `remove_timer_unit()` si disable échoue
- [ ] `mount.py` — `log_warning` dans `remove_mount_unit()` si disable échoue
- [ ] `user_service.py` — `log_warning` dans `remove_service_unit()` si disable échoue
- [ ] `user_timer.py` — `log_warning` dans `remove_timer_unit()` si disable échoue

### Tests (pytest, dans `tests/test_systemd_*.py`)
- [ ] `test_remove_service_unit_logue_warning_si_disable_echoue`
    — mock `disable_service` retournant False, vérifier `log_warning` appelé
- [ ] `test_remove_timer_unit_logue_warning_si_disable_echoue`
    — mock `disable_timer` retournant False, vérifier `log_warning` appelé
- [ ] `test_remove_mount_unit_logue_warning_si_disable_echoue`
    — mock `disable_mount` retournant False, vérifier `log_warning` appelé
- [ ] `test_remove_service_unit_pas_de_warning_si_disable_reussit`
    — mock `disable_service` retournant True, vérifier `log_warning` NOT appelé

### Validation
- [ ] `bandit -r linux_python_utils/systemd/` → 0 issue après annotations
- [ ] `pytest tests/test_systemd_*.py -v` → tous verts
- [ ] `make test` → 820+ tests passent

---

## Points d'attention

- Le retour de `disable_*()` est `bool`. Un False signifie que systemd a signalé
  une erreur (unité inconnue, permission refusée). La suppression du fichier unit
  doit quand même avoir lieu — le log_warning est informatif, pas bloquant.
- Les annotations `# nosec` vont sur la **première ligne** du call
  (`subprocess.run(  # nosec B603 B607`), pas sur les lignes d'arguments.
- Vérifier avec `bandit -r linux_python_utils/systemd/ -ll -ii` après correction
  pour confirmer 0 issue résiduelle.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
