# FIX — TESTS commands : migrer les mocks subprocess.run → Popen
> **Date :** 2026-05-30 à 21:50
> **Complexité estimée :** Faible (tests uniquement)

---

## Contexte

### Problématique
`LinuxCommandExecutor.run()` a été refactoré pour utiliser
`subprocess.Popen` + `communicate()` (gestion propre de
`KeyboardInterrupt`/timeout). Plusieurs tests de `test_commands.py`
mockent toujours `subprocess.run` :

- ceux qui inspectent `mock_run.call_args` échouent (`None` car run n'est
  jamais appelé → `TypeError: 'NoneType' object is not subscriptable`) ;
- ceux qui posent `mock_run.return_value` exécutent en réalité la vraie
  commande (ralentit la suite : `sleep 100`, `ls`, `false`…).

8 tests échouent. Le **code de production est correct** — seuls les mocks
sont périmés.

### Solution technique retenue
Migrer les mocks concernés de `subprocess.run` vers `subprocess.Popen`,
avec un helper qui configure le context manager (`__enter__` →
proc.communicate()/returncode). Tests redeviennent de vrais tests
unitaires (aucune commande réelle), plus rapides et déterministes.

### Fichiers impactés
- `tests/test_commands.py` — 8 tests + helper de mock Popen

### Hors scope
Le code `runner.py` n'est pas modifié (il est correct). Les tests qui
passent déjà en exécutant de vraies commandes (`test_run_timeout`,
`test_run_commande_introuvable`, `test_run_log_commande`,
`test_run_pas_log_erreur_si_code_retour_zero`, `test_dry_run_pas_execution`)
ne sont pas requis pour ce fix ; on peut les laisser tels quels.

---

## Évolutions à mettre en place

### `tests/test_commands.py`

#### Helper de mock Popen (au niveau module)
```python
def _setup_popen(mock_popen, returncode=0, stdout="", stderr=""):
    """Configure un mock subprocess.Popen utilisé en context manager.

    Args:
        mock_popen: Le mock retourné par @patch(...Popen).
        returncode: Code retour simulé du process.
        stdout: Sortie standard simulée.
        stderr: Sortie d'erreur simulée.

    Returns:
        Le mock du process (proc) pour assertions éventuelles.
    """
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    mock_popen.return_value.__enter__.return_value = proc
    return proc
```

#### Tests à migrer (8)
Pour chacun : remplacer
`@patch("linux_python_utils.commands.runner.subprocess.run")` par
`@patch("linux_python_utils.commands.runner.subprocess.Popen")`, puis
configurer via `_setup_popen(...)` et adapter les assertions.

| Test | Adaptation |
|---|---|
| `test_run_commande_reussie` | `_setup_popen(m, 0, "sortie", "")` ; assertions inchangées |
| `test_run_commande_echouee` | `_setup_popen(m, 1, "", "erreur")` |
| `test_run_avec_cwd` | `_setup_popen(m, 0)` ; `m.call_args[1]["cwd"] == "/tmp"` |
| `test_run_sans_logger` | `_setup_popen(m, 0, "ok", "")` |
| `test_run_logue_erreur_si_code_retour_non_zero` | `_setup_popen(m, 2, "", "echec")` ; assertions log inchangées |
| `test_default_env_fusionne` | `_setup_popen(m)` ; `m.call_args[1]["env"]` |
| `test_env_appel_prioritaire` | `_setup_popen(m)` ; `m.call_args[1]["env"]` |
| `test_aucun_env_passe_none` | `_setup_popen(m)` ; `m.call_args[1]["env"] is None` |

> Le nom du paramètre mock passe de `mock_run` à `mock_popen` dans les
> signatures concernées.

#### Conventions
- [x] PEP 8 — lignes ≤ 79
- [x] PEP 257 — docstring du helper
- [x] PEP 20 — un helper unique, pas de duplication du setup Popen

---

## Checklist d'implémentation

### Tests
- [ ] Ajouter `_setup_popen(...)` (module-level)
- [ ] Migrer les 5 tests `TestLinuxCommandExecutorRun` en échec
- [ ] Migrer les 3 tests `TestLinuxCommandExecutorEnv` en échec
- [ ] `pytest tests/test_commands.py -q` : 0 échec
- [ ] `pytest -q` (suite complète) : aucune régression, suite plus rapide

### Documentation
- [ ] Docstring du helper (PEP 257)

---

## Points d'attention

- **`communicate(timeout=...)`** : le code passe `timeout=effective_timeout`
  à `proc.communicate`. Le mock l'ignore (MagicMock accepte les kwargs).
- **Context manager** : `run()` fait `with subprocess.Popen(...) as _proc`.
  Le mock doit exposer `__enter__` → proc. `_setup_popen` s'en charge.
- **Vérifier la cible de patch** : `linux_python_utils.commands.runner.subprocess.Popen`
  (le module importe `subprocess`, donc patch sur l'attribut du module runner).
- **Ne pas toucher `runner.py`** — production correcte.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
