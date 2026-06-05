# CORRECTIONS AUDIT SÉCURITÉ MODULE COMMANDS — VISIBILITÉ
> **Date :** 2026-02-26 à 00:04
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit sécurité du module `commands/` (4 skills : OWASP, Bandit, safety,
monitoring). Aucune vulnérabilité critique. Trois catégories de points
identifiés dans `runner.py` :

| # | Ligne | Type | Problème |
|---|-------|------|----------|
| 1 | 42 | B404 LOW | `import subprocess` — faux positif Bandit (module d'exécution de commandes, c'est sa raison d'être) |
| 2 | 264 | B603 HIGH | `subprocess.run()` — faux positif (shell=False implicite, args en `List[str]`) |
| 3 | 354 | B603 HIGH | `subprocess.Popen()` — faux positif (même justification) |
| 4 | 272-281 | A09 | `run()` : code retour non-zéro silencieux — `success=False` retourné sans aucune trace log |
| 5 | 380-389 | A09 | `run_streaming()` : même silence sur code retour non-zéro |

Les faux positifs Bandit (B404, B603) sont bruyants et masquent les vrais
problèmes lors d'un `bandit -r`. Les points A09 rendent le diagnostic en
production impossible : si `rsync` ou `systemctl` échoue (exit 1), il n'y a
aucune trace dans les logs — l'appelant peut ignorer l'échec.

### Solution technique retenue

- **Corrections 1-3** : annotations `# nosec B404` et `# nosec B603` avec
  justification inline. Pattern identique aux annotations déjà validées dans
  `scanner.py` (B405, B314) et `router.py` (B310, B110).
- **Corrections 4-5** : ajout de `self._log_error()` (méthode déjà existante,
  ligne 167) quand `proc.returncode != 0`, immédiatement avant le `return
  CommandResult(...)` nominal. La méthode `_log_error` est no-op si
  `self._logger is None` — comportement inchangé pour les appelants sans
  logger.
- **Pas de changement de signature**, pas de nouveau paramètre, pas de
  nouvelle dépendance. Interface `Logger` : `log_info`, `log_warning`,
  `log_error` — on utilise `log_error` (code retour non-zéro = anomalie
  opérationnelle).

### Fichiers impactés

- `linux_python_utils/commands/runner.py` — corrections 1 à 5
- `tests/test_commands.py` — 4 nouveaux tests

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/commands/runner.py`

#### Correction 1 — nosec B404 sur `import subprocess`

**Ligne 42 :**
```python
import subprocess  # nosec B404
```

Justification : Ce module **est** un exécuteur de commandes subprocess.
L'import est intentionnel et constitue la fonctionnalité principale.

---

#### Correction 2 — nosec B603 sur `subprocess.run()`

**Avant (lignes ~264-271) :**
```python
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=effective_env,
                cwd=cwd,
                timeout=effective_timeout,
            )
```

**Après :**
```python
            proc = subprocess.run(  # nosec B603
                command,
                capture_output=True,
                text=True,
                env=effective_env,
                cwd=cwd,
                timeout=effective_timeout,
            )
```

Justification : `shell=False` (défaut de subprocess), `command` est
`List[str]` — pas de concaténation de chaîne, pas d'injection possible.

---

#### Correction 3 — nosec B603 sur `subprocess.Popen()`

**Avant (lignes ~354-361) :**
```python
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=effective_env,
                cwd=cwd,
            ) as proc:
```

**Après :**
```python
            with subprocess.Popen(  # nosec B603
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=effective_env,
                cwd=cwd,
            ) as proc:
```

Justification : Même que correction 2 — shell=False, args List[str].

---

#### Correction 4 — log_error dans `run()` sur code retour non-zéro

**Avant (lignes ~272-281) :**
```python
            duration = time.monotonic() - start
            return CommandResult(
                command=command,
                return_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                success=proc.returncode == 0,
                duration=duration,
                executed_as_root=self._is_root,
            )
```

**Après :**
```python
            duration = time.monotonic() - start
            if proc.returncode != 0:
                self._log_error(
                    f"Code retour {proc.returncode} : "
                    f"{' '.join(command)}"
                )
            return CommandResult(
                command=command,
                return_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                success=proc.returncode == 0,
                duration=duration,
                executed_as_root=self._is_root,
            )
```

Logique :
1. Après le calcul de `duration`, tester `proc.returncode != 0`
2. Si non-zéro : appeler `self._log_error()` (no-op si pas de logger)
3. Le message inclut le code retour et la commande (jamais les sorties —
   elles peuvent contenir des informations sensibles)
4. Retourner `CommandResult` comme avant — comportement inchangé

**Docstring à mettre à jour** sur `run()` — ajouter dans la section Note :

```
        Note:
            Logue une erreur si le code retour est non-nul et qu'un
            logger est configure.
```

---

#### Correction 5 — log_error dans `run_streaming()` sur code retour non-zéro

**Avant (lignes ~380-389) :**
```python
                duration = time.monotonic() - start
                return CommandResult(
                    command=command,
                    return_code=proc.returncode,
                    stdout="\n".join(stdout_lines),
                    stderr=stderr,
                    success=proc.returncode == 0,
                    duration=duration,
                    executed_as_root=self._is_root,
                )
```

**Après :**
```python
                duration = time.monotonic() - start
                if proc.returncode != 0:
                    self._log_error(
                        f"Code retour {proc.returncode} : "
                        f"{' '.join(command)}"
                    )
                return CommandResult(
                    command=command,
                    return_code=proc.returncode,
                    stdout="\n".join(stdout_lines),
                    stderr=stderr,
                    success=proc.returncode == 0,
                    duration=duration,
                    executed_as_root=self._is_root,
                )
```

Logique : identique à la correction 4, dans le bloc `with subprocess.Popen`
après `proc.wait()` et `stderr = proc.stderr.read()`.

**Docstring à mettre à jour** sur `run_streaming()` — même note que `run()`.

#### Conventions PEP

- [x] PEP 8 — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring Note mise à jour sur `run()` et `run_streaming()`
- [x] PEP 484 — Signatures inchangées
- [x] PEP 20 — Comportement externe inchangé : `CommandResult` retourné comme avant

---

## Analyse de sécurité

### Analyse statique Bandit

- [x] B404 — `import subprocess` : faux positif annoté `# nosec B404`
    (condition : module dont subprocess est le cœur de métier)
- [x] B603 — `subprocess.run` et `subprocess.Popen` sans shell : faux positifs
    annotés `# nosec B603` (shell=False + List[str] = sécurisé par construction)
- [x] `bandit -r linux_python_utils/commands/ -ll -ii` → 0 issue après corrections

### OWASP Top 10 — Points de vigilance

- [x] A09 Logging Failures — Code retour non-zéro de `run()` maintenant loggué
- [x] A09 Logging Failures — Code retour non-zéro de `run_streaming()` maintenant
    loggué
- [x] A03 Injection — `command` est `List[str]`, shell=False : pas de risque
    d'injection de commande (inchangé, confirmé)
- [x] Valeur stdout/stderr jamais loggée lors de l'échec : seuls `returncode`
    et les tokens de la commande (PII-safe)

### Monitoring et surveillance

- [x] Échecs de commandes désormais visibles dans les logs (A09)
- [x] Timeouts déjà loggués (inchangé)
- [x] Erreurs OSError déjà loggées (inchangé)
- [x] Aucun contenu de sortie dans les logs d'erreur (pas de fuite)

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | `LinuxCommandExecutor` conserve sa responsabilité unique | ✅ |
| **O** Open/Closed | Comportement étendu sans changer les interfaces | ✅ |
| **L** Liskov | `CommandExecutor` ABC non impacté | ✅ |
| **I** Interface Segregation | `Logger` optionnel injecté, interface inchangée | ✅ |
| **D** Dependency Inversion | `Logger` déjà injecté via `__init__` | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `runner.py` — `# nosec B404` sur `import subprocess` (ligne 42)
- [ ] `runner.py` — `# nosec B603` sur `subprocess.run()` (ligne ~264)
- [ ] `runner.py` — `# nosec B603` sur `subprocess.Popen()` (ligne ~354)
- [ ] `runner.py` — `log_error` sur `returncode != 0` dans `run()` (après ligne ~272)
- [ ] `runner.py` — `log_error` sur `returncode != 0` dans `run_streaming()` (après ligne ~380)
- [ ] `runner.py` — docstring `run()` : note sur le log d'erreur
- [ ] `runner.py` — docstring `run_streaming()` : note sur le log d'erreur

### Tests (pytest, dans `tests/test_commands.py`)
- [ ] `TestLinuxCommandExecutorRun::test_run_logue_erreur_si_code_retour_non_zero`
    — mock `subprocess.run` avec `returncode=1`, vérifier `logger.log_error`
    appelé avec le code retour et la commande
- [ ] `TestLinuxCommandExecutorRun::test_run_pas_log_erreur_si_code_retour_zero`
    — mock `subprocess.run` avec `returncode=0`, vérifier `logger.log_error`
    NOT appelé
- [ ] `TestLinuxCommandExecutorRunStreaming::test_streaming_logue_erreur_si_code_retour_non_zero`
    — mock `subprocess.Popen` avec `returncode=1`, vérifier `logger.log_error`
    appelé
- [ ] `TestLinuxCommandExecutorRunStreaming::test_streaming_pas_log_erreur_si_code_retour_zero`
    — mock `subprocess.Popen` avec `returncode=0`, vérifier `logger.log_error`
    NOT appelé

### Validation
- [ ] `pytest tests/test_commands.py -v` → tous verts
- [ ] `bandit -r linux_python_utils/commands/` → 0 issue (B404, B603 notés nosec)
- [ ] `make test` → 812+ tests passent

---

## Points d'attention

- Le message de `log_error` inclut `proc.returncode` et `' '.join(command)`.
  Ne jamais inclure `proc.stdout` ou `proc.stderr` dans le message — ils
  peuvent contenir des mots de passe ou des données sensibles.
- `_log_error()` est une méthode existante (ligne 167) qui est no-op si
  `self._logger is None` — aucun changement de comportement pour les
  appelants qui n'injectent pas de logger.
- Les tests existants `test_run_commande_echouee` et
  `test_streaming_capture_sortie` ne doivent pas régresser : ils testent
  `success=False` et `return_code`, pas les logs.
- Les `# nosec` sont sur la première ligne du call (`subprocess.run(` /
  `subprocess.Popen(`), pas sur les lignes d'arguments.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
