# MODULE CREDENTIALS — CORRECTIONS SÉCURITÉ & OPTIMISATION
> **Date :** 2026-06-05 à 14:10
> **Complexité estimée :** Moyenne
> **Verdict revue :** NO-GO (sécurité — fuite de secret)
> **Source :** `PLAN_ACTION_REVUE.md` § credentials

---

## Contexte

### Problématique
Le module dont le rôle est de protéger les secrets en fuit deux manières :
1. `Credential.value` apparaît dans le `repr` par défaut de la dataclass →
   tout `print(cred)`, log d'exception ou traceback expose le secret en clair.
2. Le provider `dotenv` charge le `.env` dans `os.environ` **global** :
   le secret devient visible par tout le process et hérité par les
   sous-processus (`subprocess`).

S'ajoutent : `delete()` keyring qui avale toutes les erreurs, l'absence de
contrôle des permissions du `.env`, et de la duplication interne.

### Solution technique retenue
- Masquer la valeur via `field(repr=False)` (mécanisme standard `dataclasses`,
  pas de `__repr__` manuel à maintenir).
- Utiliser `dotenv_values()` (parse pur, ne mute pas `os.environ`) au lieu de
  `load_dotenv()`.
- Logger avant d'avaler une exception dans `delete()`.

### Fichiers impactés
- `src/linux_python_utils/credentials/models.py` — masquage `value`
- `src/linux_python_utils/credentials/providers/dotenv.py` — isolation env + perms
- `src/linux_python_utils/credentials/providers/keyring.py` — logging delete + DRY import
- `src/linux_python_utils/credentials/chain.py` — DRY `get`/`get_with_source`
- `src/linux_python_utils/credentials/manager.py` — helper `_require_store`
- `tests/test_credentials.py` — tests anti-fuite

---

## Évolutions à mettre en place (Détail Junior)

### `credentials/models.py` — 🔴 BLOQUANT

#### Logique
1. Localiser la dataclass `Credential` (vers la ligne 35).
2. Sur le champ `value`, remplacer la déclaration simple par un `field` qui
   l'exclut du `repr` :

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Credential:
    """Identifiant récupéré depuis un fournisseur de secrets."""

    service: str
    key: str
    value: str = field(repr=False)  # jamais affiché (anti-fuite)
    source: str | None = None
```

3. Ne PAS écrire de `__repr__` manuel : `field(repr=False)` suffit et reste
   maintenable.

#### Vérification attendue
`repr(Credential("svc", "k", "secret"))` ne doit PAS contenir `"secret"`.

---

### `credentials/providers/dotenv.py` — 🔴 BLOQUANT

#### Logique
1. Remplacer l'usage de `load_dotenv(...)` (vers l.66-69) par `dotenv_values(path)`
   qui retourne un `dict` sans toucher `os.environ` :

```python
from dotenv import dotenv_values

# au chargement (méthode load) :
self._values = dotenv_values(self._dotenv_path)  # dict[str, str | None]
```

2. `get()` lit depuis `self._values`, plus depuis `os.environ`.
3. Ajouter un contrôle de permissions au chargement : avertir si le `.env` est
   lisible par d'autres utilisateurs.

```python
import os
import stat

mode = self._dotenv_path.stat().st_mode
if mode & (stat.S_IRWXG | stat.S_IRWXO):  # bits groupe/autres
    self._logger.log_warning(
        f"{self._dotenv_path} accessible par d'autres "
        f"utilisateurs (permissions trop larges)."
    )
```

4. Documenter dans la docstring que `key.upper()` (l.90) normalise les clés.

#### Gestion d'erreurs
| Cas | Condition | Action |
|---|---|---|
| `.env` absent | `not path.exists()` | `get()` retourne `None` (dégradation) |
| `python-dotenv` absent | `ImportError` | log DEBUG + provider indisponible |
| Permissions larges | bits groupe/autres positionnés | `log_warning` (ne pas bloquer) |

---

### `credentials/providers/keyring.py` — 🟠 MAJEUR

#### Logique
1. `delete()` (l.155-156) : avant le `pass`, logger l'exception réelle :

```python
try:
    kr.delete_password(service, key)
    self._logger.log_info(f"Secret supprimé : {service}/{key}")
except Exception as exc:  # nosec B110 - dégradation volontaire
    self._logger.log_warning(
        f"Échec suppression {service}/{key} : {exc}"
    )
```

2. DRY : factoriser les 3 blocs `import keyring` (`_get_keyring`, `is_available`)
   en un seul helper privé `_keyring_importable() -> bool`.

> ⚠️ Ne JAMAIS logger `value` — seulement `service`/`key`.

---

### `credentials/chain.py` — 🟡 MINEUR (optimisation)

#### Logique
1. Extraire un générateur privé qui parcourt les providers une seule fois :

```python
def _find(
    self, service: str, key: str
) -> tuple[CredentialProvider | None, str | None]:
    """Retourne le premier (provider, valeur) trouvé, sinon (None, None)."""
    for provider in self._providers:
        if not provider.is_available():
            continue
        value = provider.get(service, key)
        if value:
            return provider, value
    return None, None
```

2. `get()` et `get_with_source()` délèguent à `_find()`.
3. Passer les logs d'escalade de `INFO` à `DEBUG` (l.86-92).

> ⚠️ Avant de déplacer le logging : vérifier les asserts de logs dans les tests
> (`get` loggait à chaque escalade, pas `get_with_source`). Conserver le
> comportement observable testé.

---

### `credentials/manager.py` — 🟡 MINEUR (optimisation)

#### Logique
Factoriser la garde répétée dans `store()`/`delete()` :

```python
def _require_store(self) -> CredentialStore:
    """Retourne le store ou lève si aucun n'est configuré."""
    if self._store is None:
        raise CredentialStoreError("Aucun store de secrets configuré.")
    return self._store
```

---

## Analyse de sécurité (OWASP / Bandit)

### OWASP
- [x] A02 Cryptographic Failures — secret hors `repr`, hors logs, `.env` 0o600.
- [x] A09 Logging Failures — aucun log ne contient `value`.

### Bandit
- [x] `bandit -r src/linux_python_utils/credentials/ -ll -ii`
- [x] B110 — le `except: pass` de `delete()` est désormais loggé.

---

## Checklist d'implémentation

### Code
- [x] `models.py` — `value: str = field(repr=False)`
- [x] `dotenv.py` — `dotenv_values` + contrôle permissions `.env`
- [x] `keyring.py` — logger dans `delete()` + DRY import
- [x] `chain.py` — `_find()` + logs DEBUG
- [x] `manager.py` — `_require_store()`

### Tests (pytest)
- [x] `test_credential_repr_ne_contient_pas_la_valeur()` 🔴
- [x] `test_chain_get_ne_logue_jamais_la_valeur()` 🔴
- [x] `test_dotenv_ne_pollue_pas_os_environ()` 🔴
- [x] `test_dotenv_avertit_si_env_world_readable()`
- [x] `test_keyring_delete_logue_l_erreur_reelle()`
- [ ] `pytest --cov=src/linux_python_utils/credentials --cov-report=term-missing`

### Documentation
- [ ] Docstrings PEP 257 à jour (normalisation `key.upper()`, dégradation store)

---

## Points d'attention
- L'ordre des secrets recherchés ne doit pas changer (`_find` garde l'ordre).
- `field(repr=False)` exige que `value` reste après les champs sans défaut
  ou que tous suivent la règle des valeurs par défaut des dataclasses.

---

## ⏸ Validation requise
**Aucun code modifié avant approbation.** Répondre **"OK"** pour démarrer.
