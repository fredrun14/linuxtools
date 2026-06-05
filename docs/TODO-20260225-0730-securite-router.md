# SÉCURITÉ ROUTER.PY — 4 CORRECTIONS OWASP
> **Date :** 2026-02-25 à 07:30
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Quatre failles de sécurité identifiées dans `linux_python_utils/network/router.py`,
exploitables même en contexte LAN (attaquant sur le réseau local, données NVRAM
corrompues, ou appel malveillant depuis le code interne) :

| # | Localisation | Faille | Catégorie OWASP |
|---|---|---|---|
| 1 | `_ip_to_int()` ligne 45 | Pas de validation IPv4 avant conversion → `ValueError` non contrôlé | A03 Injection |
| 2 | `get_nvram()` ligne 466 | Clés NVRAM non filtrées → injection dans la requête hook | A03 Injection |
| 3 | `login()` ligne 308 | Username contenant `:` corrompt le format Basic Auth | A07 Auth Failures |
| 4 | `RouterConfig.__post_init__()` ligne 249 | URL uniquement vérifiée `startswith("http")` → SSRF partiel | A10 SSRF |

### Solution technique retenue

- Ajouter des fonctions/méthodes de validation privées dans `router.py`,
  au plus près de l'usage — pas de nouveau module (opérations non réutilisées
  ailleurs).
- Utiliser `re` (déjà importé), `ipaddress` et `urllib.parse` (déjà importé)
  — aucune dépendance externe.
- Lever des `ValueError` explicites avec message en français (convention projet).

### Fichiers impactés

- `linux_python_utils/network/router.py` — corrections des 4 points
- `tests/test_network_router.py` — nouveaux tests pour chaque correction

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/network/router.py`

#### Imports à ajouter

```python
import ipaddress   # stdlib — déjà disponible, à ajouter en tête
```

`re`, `urllib.parse` sont déjà importés.

---

#### Correction 1 — Validation IPv4 dans `_ip_to_int()`

**Avant (ligne 45) :**
```python
def _ip_to_int(ip: str) -> int:
    parts = [int(o) for o in ip.split(".")]
    return (
        (parts[0] << 24) + (parts[1] << 16)
        + (parts[2] << 8) + parts[3]
    )
```

**Après — ajouter une validation via `ipaddress` :**
```python
def _ip_to_int(ip: str) -> int:
    """Convertit une adresse IPv4 en entier.

    Args:
        ip: Adresse IPv4 au format a.b.c.d.

    Returns:
        Representation entiere.

    Raises:
        ValueError: Si ip n'est pas une adresse IPv4 valide.
    """
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError as exc:
        raise ValueError(
            f"Adresse IPv4 invalide : {ip!r}"
        ) from exc
    return int(addr)
```

**Logique :**
1. `ipaddress.IPv4Address(ip)` valide le format strict (4 octets 0-255)
2. `int(addr)` remplace le calcul manuel de bits
3. `AddressValueError` → `ValueError` avec message explicite

---

#### Correction 2 — Filtrage des clés NVRAM dans `get_nvram()`

**Avant (ligne 466) :**
```python
def get_nvram(self, *keys: str) -> Dict[str, str]:
    hook = ";".join(
        f"nvram_get({k})" for k in keys
    )
    return self._hook(hook)
```

**Après — valider chaque clé avant construction du hook :**
```python
# Constante de module (après _VENDOR_TYPES)
_NVRAM_KEY_RE = re.compile(r'^[a-zA-Z0-9_]{1,64}$')


def get_nvram(self, *keys: str) -> Dict[str, str]:
    """Lit des variables NVRAM du routeur.

    Args:
        *keys: Noms de variables NVRAM.
            Seuls les caractères alphanumeriques et '_'
            sont acceptes (longueur 1-64).

    Returns:
        Dictionnaire {cle: valeur}.

    Raises:
        ValueError: Si une cle contient des caracteres
            non autorises.
    """
    for key in keys:
        if not _NVRAM_KEY_RE.match(key):
            raise ValueError(
                f"Cle NVRAM invalide : {key!r}"
            )
    hook = ";".join(
        f"nvram_get({k})" for k in keys
    )
    return self._hook(hook)
```

**Logique :**
1. `_NVRAM_KEY_RE` : regex stricte `^[a-zA-Z0-9_]{1,64}$` — lettres, chiffres, underscore uniquement
2. Boucle sur toutes les clés avant de construire le hook
3. `ValueError` si une clé ne correspond pas

---

#### Correction 3 — Validation du username dans `login()`

**Avant (ligne 308) :**
```python
credentials = base64.b64encode(
    f"{username}:{password}".encode("ascii")
).decode("ascii")
```

**Après — vérifier l'absence de `:` dans le username :**
```python
def login(
    self, username: str, password: str
) -> None:
    """Authentifie la session sur le routeur.

    Args:
        username: Nom d'utilisateur (ne doit pas
            contenir ':').
        password: Mot de passe.

    Raises:
        ValueError: Si username contient ':'.
        RouterAuthError: Si l'authentification echoue.
    """
    if ":" in username:
        raise ValueError(
            "Le nom d'utilisateur ne doit pas "
            "contenir ':'"
        )
    credentials = base64.b64encode(
        f"{username}:{password}".encode("ascii")
    ).decode("ascii")
    # ... reste inchangé
```

**Logique :**
1. Vérification `":" in username` avant tout traitement
2. `ValueError` explicite si la contrainte est violée
3. Le reste de la méthode est inchangé

---

#### Correction 4 — Validation URL anti-SSRF dans `RouterConfig`

**Avant (ligne 249) :**
```python
def __post_init__(self) -> None:
    if not self.url.startswith("http"):
        raise ValueError(
            f"URL invalide : {self.url!r}"
        )
    if self.timeout <= 0:
        raise ValueError(
            f"Timeout invalide : {self.timeout}"
        )
```

**Après — ajouter `_validate_router_url()` et l'appeler depuis `__post_init__` :**

Ajouter une fonction module-level (privée) après les helpers existants :

```python
def _validate_router_url(url: str) -> None:
    """Valide l'URL du routeur.

    Verifie que :
    - Le scheme est http ou https.
    - L'host se resout en une adresse IP privee LAN.
      Adresses acceptees : 10.0.0.0/8, 172.16.0.0/12,
      192.168.0.0/16. Adresses de loopback (127.x) et
      link-local (169.254.x) refusees.

    Args:
        url: URL du routeur a valider.

    Raises:
        ValueError: Si le scheme n'est pas http/https
            ou si l'adresse n'appartient pas a un
            reseau prive LAN autorise.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Scheme non autorise : {parsed.scheme!r}"
            " (http ou https requis)"
        )
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL sans hostname")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Hostname non-IP (ex. "router.asus.com") :
        # accepte sans resolution DNS pour eviter
        # une dependance reseau a l'initialisation.
        return
    _LAN_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]
    if not any(addr in net for net in _LAN_NETWORKS):
        raise ValueError(
            f"Adresse non autorisee : {hostname!r}. "
            "Seules les adresses LAN privees sont "
            "acceptees."
        )
```

Dans `RouterConfig.__post_init__` :
```python
def __post_init__(self) -> None:
    """Valide la configuration.

    Raises:
        ValueError: Si url est invalide ou si timeout
            est inferieur ou egal a zero.
    """
    _validate_router_url(self.url)
    if self.timeout <= 0:
        raise ValueError(
            f"Timeout invalide : {self.timeout}"
        )
```

**Logique :**
1. `urlparse` extrait le scheme et l'hostname
2. Scheme : seuls `http` / `https` acceptés
3. Si l'hostname est une IP : vérification qu'elle est dans les plages LAN (10/8, 172.16/12, 192.168/16)
4. Si l'hostname est un nom DNS : accepté tel quel (pas de résolution DNS à l'init)

---

#### Conventions PEP

- [x] PEP 8  — Imports : `ipaddress` ajouté dans le bloc stdlib
- [x] PEP 8  — Lignes ≤ 79 caractères
- [x] PEP 257 — Docstrings en français sur chaque élément modifié
- [x] PEP 484 — Signatures inchangées (déjà typées)
- [x] PEP 20  — Validations explicites, pas de devinette sur le format

---

#### Principes SOLID

| Principe | Vérification | Statut |
|---|---|---|
| **S** Single Responsibility | `RouterConfig` valide sa config, `AsusRouterClient` gère HTTP | ✅ |
| **O** Open/Closed | Pas de changement d'interface publique | ✅ |
| **L** Liskov | Pas d'héritage impacté | ✅ |
| **I** Interface Segregation | Pas de nouveau protocole | ✅ |
| **D** Dependency Inversion | Validateurs comme fonctions privées, pas injectées (usage unique) | ✅ |

---

#### Analyse de sécurité OWASP

- [x] A03 Injection — Clés NVRAM filtrées par regex `^[a-zA-Z0-9_]{1,64}$`
- [x] A03 Injection — IPv4 validée par `ipaddress.IPv4Address` (pas de split manuel)
- [x] A07 Auth Failures — Username sans `:` garanti avant encodage Basic Auth
- [x] A10 SSRF — URLs routeur restreintes aux plages LAN privées

---

### `tests/test_network_router.py`

Ajouter une nouvelle classe de test :

```python
class TestSecuriteRouter:
    """Tests des corrections de securite dans router.py."""

    # --- _ip_to_int ---
    def test_ip_to_int_ip_valide(self):
        assert _ip_to_int("192.168.1.1") == 3232235777

    def test_ip_to_int_ip_invalide_leve_valueerror(self):
        with pytest.raises(ValueError, match="IPv4"):
            _ip_to_int("256.0.0.1")

    def test_ip_to_int_chaine_vide_leve_valueerror(self):
        with pytest.raises(ValueError):
            _ip_to_int("")

    # --- get_nvram ---
    def test_get_nvram_cle_valide(self):
        client = AsusRouterClient(RouterConfig())
        client._token = "tok"
        with patch.object(client, "_hook", return_value={}) as mock:
            client.get_nvram("dhcp_start")
            mock.assert_called_once_with("nvram_get(dhcp_start)")

    def test_get_nvram_cle_invalide_leve_valueerror(self):
        client = AsusRouterClient(RouterConfig())
        client._token = "tok"
        with pytest.raises(ValueError, match="NVRAM"):
            client.get_nvram("dhcp_start);evil(")

    # --- login ---
    def test_login_username_avec_colon_leve_valueerror(self):
        client = AsusRouterClient(RouterConfig())
        with pytest.raises(ValueError, match=":"):
            client.login("admin:evil", "password")

    # --- RouterConfig URL ---
    def test_router_config_url_loopback_refusee(self):
        with pytest.raises(ValueError):
            RouterConfig(url="http://127.0.0.1")

    def test_router_config_url_link_local_refusee(self):
        with pytest.raises(ValueError):
            RouterConfig(url="http://169.254.169.254")

    def test_router_config_url_lan_acceptee(self):
        cfg = RouterConfig(url="http://192.168.1.1")
        assert cfg.url == "http://192.168.1.1"

    def test_router_config_url_scheme_invalide(self):
        with pytest.raises(ValueError, match="Scheme"):
            RouterConfig(url="ftp://192.168.1.1")

    def test_router_config_url_hostname_dns_accepte(self):
        cfg = RouterConfig(url="http://router.local")
        assert cfg.url == "http://router.local"
```

---

## Checklist d'implémentation

### Code
- [ ] Ajouter `import ipaddress` dans `router.py`
- [ ] Ajouter constante `_NVRAM_KEY_RE` après `_VENDOR_TYPES`
- [ ] Ajouter fonction `_validate_router_url()` après les helpers privés
- [ ] Modifier `_ip_to_int()` — utiliser `ipaddress.IPv4Address`
- [ ] Modifier `get_nvram()` — filtrage des clés
- [ ] Modifier `login()` — vérification du `:` dans username
- [ ] Modifier `RouterConfig.__post_init__()` — appel `_validate_router_url()`

### Tests
- [ ] Ajouter `class TestSecuriteRouter` dans `tests/test_network_router.py`
- [ ] `pytest tests/test_network_router.py -v` → tous verts
- [ ] `make test` → 788+ tests passent

---

## Points d'attention

- `RouterConfig.url` a une valeur par défaut `"http://192.168.50.1"` (IP LAN 192.168/16) :
  elle doit continuer à passer la validation.
- Les tests existants de `RouterConfig` ne doivent pas régresser.
- `_int_to_ip()` n'est pas modifiée : elle n'accepte pas d'entrées externes,
  c'est une transformation interne depuis des entiers déjà validés.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
