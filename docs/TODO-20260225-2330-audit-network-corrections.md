# CORRECTIONS AUDIT SÉCURITÉ MODULE NETWORK
> **Date :** 2026-02-25 à 23:30
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit des 4 skills sécurité (OWASP, Bandit, safety, monitoring) sur
`linux_python_utils/network/` — 7 corrections identifiées dans 3 fichiers :

| # | Fichier | Type | Description |
|---|---------|------|-------------|
| 1–4 | `router.py` | Faux positif | B310 × 4 — `urlopen` : URL validée par `_validate_router_url()` |
| 5 | `router.py:793` | Faux positif | B104 — `== "0.0.0.0"` : comparaison de filtre, pas un bind |
| 6 | `router.py:418` | Faux positif | B110 — `logout()` try/except/pass intentionnel (best-effort) |
| 7 | `scanner.py:315` | Faux positif | B314 — `ET.fromstring` : sortie d'un process local root |
| 8 | `scanner.py:7` | Faux positif | B405 — import `xml.etree.ElementTree` (lié B314) |
| 9 | `dhcp.py:153` | Vrai bug | `_ip_to_int()` sans validation IPv4 — incohérence avec `router.py` |
| 10 | `router.py:login()` | Monitoring | `RouterAuthError` non loggée → point aveugle sécurité |

### Solution technique retenue

- **Faux positifs Bandit** : annotations `# nosec BXXX` avec justification
  inline. Alternative `pyproject.toml [tool.bandit] skips` écartée : trop
  globale, masquerait de vraies futures occurrences.
- **`dhcp._ip_to_int`** : remplacer le parse manuel par
  `ipaddress.IPv4Address` — cohérence avec `router.py` (déjà corrigé).
  L'import `ipaddress` est déjà présent dans `router.py` ; à ajouter dans
  `dhcp.py`.
- **Logging `RouterAuthError`** : appel `self._logger.log_error()` dans le
  bloc `except RouterAuthError` de `login()`. Ne pas utiliser `SecurityLogger`
  (dépendance non injectée dans ce module) — le `Logger` optionnel suffit.

### Fichiers impactés

- `linux_python_utils/network/router.py` — nosec B310×4, B104, B110 + log
- `linux_python_utils/network/scanner.py` — nosec B314, B405
- `linux_python_utils/network/dhcp.py` — correction `_ip_to_int()`
- `tests/test_network_dhcp.py` — tests correction `_ip_to_int()`
- `tests/test_network_router.py` — test log RouterAuthError

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/network/router.py`

#### Correction 1-4 — nosec B310 sur les 4 `urlopen`

Ajouter `# nosec B310` en fin de ligne sur chaque `urlopen`. Justification :
l'URL provient de `RouterConfig.url` validée par `_validate_router_url()`
(scheme `http`/`https`, IP LAN uniquement). Bandit ne peut pas le déduire
statiquement.

**login() — ligne ~384 :**
```python
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
```

**logout() — ligne ~418 :**
```python
            urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            )
```

**_hook() — ligne ~468 :**
```python
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
```

**set_static_reservations() — ligne ~598 :**
```python
            with urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            ) as resp:
```

#### Correction 5 — nosec B104 sur `== "0.0.0.0"`

**_parse_clients() — ligne ~793 :**
```python
            if not ip or ip == "0.0.0.0":  # nosec B104
```
Justification : comparaison de filtre de valeur invalide, pas un bind
réseau.

#### Correction 6 — nosec B110 sur logout()

**logout() — bloc try/except/pass :**
```python
        try:
            urllib.request.urlopen(
                req, timeout=self._config.timeout  # nosec B310
            )
        except Exception:  # nosec B110
            pass
```
Justification : déconnexion best-effort, une erreur réseau à la
déconnexion ne doit pas interrompre le flux appelant.

#### Correction 10 — Log RouterAuthError dans login()

Dans la méthode `login()`, après le `raise RouterAuthError(...)`, ajouter
un log d'erreur **avant** de relever l'exception. Logique :

```python
        except Exception as exc:
            if self._logger:
                self._logger.log_error(
                    f"Echec authentification routeur : {exc}"
                )
            raise RouterAuthError(
                f"Connexion echouee : {exc}"
            ) from exc
```

Et dans la vérification du token absent :

```python
        token = body.get("asus_token")
        if not token:
            if self._logger:
                self._logger.log_error(
                    "Authentification routeur : "
                    "token absent de la reponse"
                )
            raise RouterAuthError(
                "Token absent de la reponse login"
            )
```

---

### `linux_python_utils/network/scanner.py`

#### Correction 7-8 — nosec B314 et B405

**Import — ligne 7 :**
```python
import xml.etree.ElementTree as ET  # nosec B405
```
Justification : XML analysé depuis stdout de nmap (process local exécuté
en root). Pas de données réseau non fiables directes. Le projet est
stdlib-only, `defusedxml` est exclu.

**`_parse_xml_output()` — ligne ~315 :**
```python
        root = ET.fromstring(stdout)  # nosec B314
```
Même justification que B405.

---

### `linux_python_utils/network/dhcp.py`

#### Import à ajouter

```python
import dataclasses
import ipaddress   # ← ajouter (stdlib)
from typing import List, Optional, Set
```

#### Correction 9 — `_ip_to_int()` avec `ipaddress.IPv4Address`

**Avant :**
```python
    @staticmethod
    def _ip_to_int(ip: str) -> int:
        """Convertit une adresse IP en entier.

        Args:
            ip: Adresse IPv4.

        Returns:
            Representation entiere de l'IP.
        """
        parts = [int(o) for o in ip.split(".")]
        return (
            (parts[0] << 24)
            + (parts[1] << 16)
            + (parts[2] << 8)
            + parts[3]
        )
```

**Après :**
```python
    @staticmethod
    def _ip_to_int(ip: str) -> int:
        """Convertit une adresse IPv4 en entier.

        Args:
            ip: Adresse IPv4 au format a.b.c.d.

        Returns:
            Representation entiere.

        Raises:
            ValueError: Si ip n'est pas une adresse IPv4
                valide.
        """
        try:
            addr = ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError as exc:
            raise ValueError(
                f"Adresse IPv4 invalide : {ip!r}"
            ) from exc
        return int(addr)
```

Logique :
1. `ipaddress.IPv4Address(ip)` valide strictement (4 octets 0-255)
2. `AddressValueError` → `ValueError` avec message explicite
3. `int(addr)` remplace le calcul manuel de bits

---

#### Conventions PEP

- [x] PEP 8 — Imports ordonnés : `ipaddress` dans le bloc stdlib
- [x] PEP 8 — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstring mise à jour sur `_ip_to_int()`
- [x] PEP 484 — Signatures inchangées (déjà typées)
- [x] PEP 20 — Pas de complexité inutile : `int(addr)` plus simple
    que le calcul bit à bit

---

#### Analyse de sécurité

- [x] A03 Injection — B310 × 4 : URL validée, `# nosec` justifié
- [x] A03 Injection — B314/B405 : XML depuis process local, `# nosec`
    justifié
- [x] A07 Auth Failures — Echecs d'auth loggés dans `login()`
- [x] A09 Logging Failures — `RouterAuthError` désormais tracée

---

## Checklist d'implémentation

### Code
- [ ] `router.py` — `# nosec B310` sur les 4 `urlopen`
- [ ] `router.py` — `# nosec B104` sur `== "0.0.0.0"`
- [ ] `router.py` — `# nosec B110` sur `except Exception: pass`
- [ ] `router.py` — log `RouterAuthError` dans `login()`
- [ ] `scanner.py` — `# nosec B405` sur l'import ET
- [ ] `scanner.py` — `# nosec B314` sur `ET.fromstring`
- [ ] `dhcp.py` — `import ipaddress`
- [ ] `dhcp.py` — `_ip_to_int()` utilise `ipaddress.IPv4Address`

### Tests (pytest)
- [ ] `tests/test_network_dhcp.py` — `test_ip_to_int_valide`
- [ ] `tests/test_network_dhcp.py` — `test_ip_to_int_invalide_leve_valueerror`
- [ ] `tests/test_network_router.py` — `test_login_echec_logue_erreur`
- [ ] `pytest tests/test_network_dhcp.py tests/test_network_router.py -v`
- [ ] `make test` → 801+ tests passent

### Validation Bandit post-correction
- [ ] `bandit -r linux_python_utils/network/ -ll -ii` → 0 issue sans nosec

---

## Points d'attention

- Les `# nosec` doivent rester sur la **même ligne** que l'instruction
  signalée, pas sur la ligne suivante.
- `_ip_to_int` dans `dhcp.py` est appelé uniquement avec des IPs
  déjà validées par `DhcpRange.__post_init__()` : la correction est
  défensive, pas critique. Les tests existants ne doivent pas régresser.
- Ne pas toucher `_int_to_ip()` dans `dhcp.py` : entrée interne, pas
  de risque.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
