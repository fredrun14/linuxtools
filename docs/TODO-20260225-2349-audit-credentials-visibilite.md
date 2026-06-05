# CORRECTIONS AUDIT SÉCURITÉ MODULE CREDENTIALS — VISIBILITÉ
> **Date :** 2026-02-25 à 23:49
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit sécurité du module `credentials/` (4 skills : OWASP, Bandit, safety,
monitoring). Aucune vulnérabilité critique. Trois trous de visibilité
opérationnels identifiés :

| # | Fichier | Ligne | Problème |
|---|---------|-------|----------|
| 1 | `keyring.py` | 149 | B110 faux positif — `except Exception: pass` dans `delete()` (best-effort intentionnel) |
| 2 | `keyring.py` | 91 | Erreur keyring dans `get()` avalée sans trace — point aveugle si le keyring tombe |
| 3 | `chain.py` | 74-86 | Escalade de provider non loggée — impossible de savoir pourquoi la chaîne est remontée |
| 4 | `manager.py` | 96-100 | `CredentialNotFoundError` levée sans log — échec silencieux du point de vue applicatif |

Ces points n'exposent pas de secrets mais rendent le diagnostic en production
impossible : si le keyring échoue ou qu'un credential est introuvable, il
n'y a aucune trace dans les logs.

### Solution technique retenue

- **Correction 1** : annotation `# nosec B110` sur `delete()` — même
  traitement que `logout()` dans `router.py` (déjà validé).
- **Corrections 2-4** : ajout de `log_warning` / `log_info` via le
  `self._logger` optionnel déjà injecté. Pas de nouveau paramètre, pas
  de nouvelle dépendance. Interface `Logger` : `log_info`, `log_warning`,
  `log_error` (pas de `log_debug`).
- **Pas de `SecurityLogger`** : le module est stdlib-only, `SecurityLogger`
  n'est pas injecté ici — le `Logger` optionnel suffit (cohérent avec
  `router.py`).

### Fichiers impactés

- `linux_python_utils/credentials/providers/keyring.py` — corrections 1 et 2
- `linux_python_utils/credentials/chain.py` — correction 3
- `linux_python_utils/credentials/manager.py` — correction 4
- `tests/test_credentials.py` — 4 nouveaux tests

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/credentials/providers/keyring.py`

#### Correction 1 — nosec B110 sur `delete()`

**Ligne ~149 :**
```python
        except Exception:  # nosec B110
            pass
```
Justification : `delete()` est contractuellement silencieux (docstring :
"Silencieux si le credential est absent"). Pattern identique au
`logout()` de `router.py`.

#### Correction 2 — log_warning dans `get()` sur exception

**Avant (lignes ~87-92) :**
```python
        try:
            kr = self._get_keyring()
            value = kr.get_password(service, key)
            return value if value else None
        except Exception:
            return None
```

**Après :**
```python
        try:
            kr = self._get_keyring()
            value = kr.get_password(service, key)
            return value if value else None
        except Exception as exc:
            if self._logger:
                self._logger.log_warning(
                    f"Erreur keyring get() : "
                    f"service={service!r}, "
                    f"key={key!r} : {exc}"
                )
            return None
```

Logique :
1. Capturer `exc` pour inclure le message dans le log
2. Logger uniquement si `self._logger` est présent (optionnel)
3. Retourner `None` comme avant (comportement inchangé)

**Docstring à mettre à jour** sur `get()` — ajouter dans la section
existante :

```
        Note:
            En cas d'erreur inattendue du keyring, retourne None
            et log un warning si un logger est configure.
```

#### Conventions PEP

- [x] PEP 8 — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring Note mise à jour sur `get()`
- [x] PEP 484 — Signatures inchangées
- [x] PEP 20 — Comportement externe inchangé : `None` retourné comme avant

---

### `linux_python_utils/credentials/chain.py`

#### Correction 3 — log_info sur l'escalade de provider dans `get()`

**Avant (lignes ~74-86) :**
```python
        for provider in self._providers:
            if not provider.is_available():
                continue
            value = provider.get(service, key)
            if value:
                if self._logger:
                    self._logger.log_info(
                        f"Credential trouve via "
                        f"{provider.source_name!r} : "
                        f"service={service!r}, key={key!r}"
                    )
                return value
        return None
```

**Après :**
```python
        for provider in self._providers:
            if not provider.is_available():
                continue
            value = provider.get(service, key)
            if value:
                if self._logger:
                    self._logger.log_info(
                        f"Credential trouve via "
                        f"{provider.source_name!r} : "
                        f"service={service!r}, key={key!r}"
                    )
                return value
            if self._logger:
                self._logger.log_info(
                    f"Credential absent de "
                    f"{provider.source_name!r} : "
                    f"service={service!r}, "
                    f"key={key!r} — escalade"
                )
        return None
```

Logique :
1. Après `if value:` (cas succès, inchangé), ajouter un `if self._logger`
   dans la branche "pas de valeur" pour tracer l'escalade
2. `log_info` (pas `log_warning`) : l'escalade est un flux normal
3. Le message indique clairement le provider qui a échoué et que la
   chaîne continue

**Conventions PEP**

- [x] PEP 8 — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring de `get()` : ajouter une note sur les logs
- [x] PEP 484 — Signatures inchangées
- [x] PEP 20 — Pas de nouvelle logique : ajout minimal d'un log

---

### `linux_python_utils/credentials/manager.py`

#### Correction 4 — log_warning dans `require()` avant CredentialNotFoundError

**Avant (lignes ~95-100) :**
```python
        value = self._chain.get(self._service, key)
        if value is None:
            raise CredentialNotFoundError(
                f"Credential introuvable : "
                f"service={self._service!r}, key={key!r}"
            )
        return value
```

**Après :**
```python
        value = self._chain.get(self._service, key)
        if value is None:
            if self._logger:
                self._logger.log_warning(
                    f"Credential introuvable dans toute "
                    f"la chaine : "
                    f"service={self._service!r}, "
                    f"key={key!r}"
                )
            raise CredentialNotFoundError(
                f"Credential introuvable : "
                f"service={self._service!r}, key={key!r}"
            )
        return value
```

Logique :
1. Avant le `raise`, tester `self._logger` (optionnel)
2. `log_warning` : une clé introuvable après toute la chaîne est
   anormale et mérite une alerte
3. Le message est distinct de l'exception : log = contexte opérationnel,
   exception = information pour le code appelant

**Docstring à mettre à jour** sur `require()` — ajouter :

```
        Note:
            Logue un warning si un logger est configure et que
            le credential est absent.
```

**Conventions PEP**

- [x] PEP 8 — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring Note ajoutée sur `require()`
- [x] PEP 484 — Signatures inchangées
- [x] PEP 20 — Log avant raise, pas après (une seule façon)

---

## Analyse de sécurité

### OWASP Top 10 — Points de vigilance

- [x] A09 Logging Failures — Erreur keyring `get()` maintenant loggée
- [x] A09 Logging Failures — Escalade de provider tracée dans la chaîne
- [x] A09 Logging Failures — `CredentialNotFoundError` loggée avant propagation
- [x] A02 Cryptographic Failures — Valeur du credential jamais loggée (seulement
    `service` et `key` dans les messages)

### Analyse statique Bandit

- [x] B110 — `except Exception: pass` dans `delete()` : faux positif annoté
    `# nosec B110`
- [x] `bandit -r linux_python_utils/credentials/ -ll -ii` → 0 issue après
    correction

### Monitoring et surveillance

- [x] Erreurs keyring loggées (visibilité si le service Secret Service tombe)
- [x] Escalade de provider tracée (diagnostic de la source effective)
- [x] Credential introuvable loggé avant exception (corrélable dans les logs)
- [x] Aucune valeur secrète dans les messages de log (PII-safe)

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | Chaque classe conserve sa responsabilité unique | ✅ |
| **O** Open/Closed | Comportement étendu sans changer les interfaces | ✅ |
| **L** Liskov | Sous-classes non impactées | ✅ |
| **I** Interface Segregation | `Logger` optionnel injecté, interface inchangée | ✅ |
| **D** Dependency Inversion | `Logger` déjà injecté via `__init__` | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `keyring.py` — `# nosec B110` sur `except Exception: pass` dans `delete()`
- [ ] `keyring.py` — `except Exception as exc:` + `log_warning` dans `get()`
- [ ] `keyring.py` — docstring `get()` : note sur le comportement en cas d'erreur
- [ ] `chain.py` — `log_info` escalade dans `get()` (branche `value` absent)
- [ ] `chain.py` — docstring `get()` : note sur les logs d'escalade
- [ ] `manager.py` — `log_warning` avant `raise CredentialNotFoundError` dans `require()`
- [ ] `manager.py` — docstring `require()` : note sur le warning

### Tests (pytest, dans `tests/test_credentials.py`)
- [ ] `TestKeyringCredentialProvider::test_get_log_warning_sur_exception_keyring`
    — mock `kr.get_password` levant une exception, vérifier `logger.log_warning` appelé
- [ ] `TestKeyringCredentialProvider::test_get_retourne_none_et_log_sur_exception`
    — vérifier que `get()` retourne `None` (comportement inchangé)
- [ ] `TestCredentialChain::test_get_log_info_escalade_provider`
    — deux providers, premier retourne `None`, vérifier `log_info` avec "escalade"
- [ ] `TestCredentialManager::test_require_log_warning_si_absent`
    — chain retourne `None`, vérifier `logger.log_warning` avant `CredentialNotFoundError`

### Validation
- [ ] `pytest tests/test_credentials.py -v` → tous verts
- [ ] `bandit -r linux_python_utils/credentials/` → 0 issue (B110 noté nosec)
- [ ] `make test` → 808+ tests passent

---

## Points d'attention

- Les **valeurs** de credentials ne doivent **jamais** apparaître dans les
  messages de log — seuls `service` et `key` sont loggués.
- `log_info` pour l'escalade dans `chain.get()` (flux normal) ;
  `log_warning` pour l'erreur keyring et `require()` (anomalies).
- Les tests existants de `keyring.get()` (`test_get_retourne_none_sur_exception_get_password`)
  ne doivent pas régresser : le comportement retourne toujours `None`.
- `get_with_source()` dans `chain.py` n'est **pas** modifiée : elle appelle
  `provider.get()` mais ne peut pas logger l'escalade sans dupliquer la
  logique. Périmètre limité aux 4 corrections identifiées.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
