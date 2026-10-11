# Conception — Chargeur de clients LAN générique

> **Date :** 2026-10-11 · **CDC :** CDC-20261011-Chargeur-Clients-LAN-Generique.md · **Statut :** Validé

## 1. Impact et voisins

| Dépôt | Fichier | Changement |
|---|---|---|
| linuxtools | `network/clients.py` (**nouveau**) | `LanClient` + `load_lan_clients` |
| linuxtools | `network/__init__.py` | import + `LanClient`, `load_lan_clients` dans `__all__` |
| linuxtools | `CHANGELOG`, bump mineur (v2.6.0) | ajout rétro-compatible |
| webapitools | `apps/pihole_dns.py` | `ClientRecord` supprimé ; `_parse_clients` → appel loader ; `ZoneConfig.clients: tuple[LanClient, ...]` ; validateurs `_dns_label`/`_usable_ip` extraits ; `_usable_address`/`_LABEL_RE` conservés |
| webapitools | `apps/pihole_schedule.py` | `_parse_client_macs` réduit à appel loader + projection `.mac` |
| webapitools | `apps/_shared.py` | `normalize_mac` **supprimé** (absorbé par le loader) |
| webapitools | `cli.py` `_cmd_router_apply` | consomme `LanClient` ; `hostname=c.name or ""` (cf. piège §8) |
| webapitools | pin `linuxtools@v2.6.0` + **3** `--branch` CI | bump obligatoire |

Réemploi : `validate_mac(case="upper")` (déjà dans la lib) est le seul socle ; aucune dépendance nouvelle.

## 2. Composants et interfaces

**`LanClient`** (frozen dataclass, `network/clients.py`) — client LAN *déclaré* (intention), distinct de `NetworkDevice` (*observé*).
- `mac: str` (normalisée majuscules), `name: str | None = None`, `pinned_ip: str | None = None`.
- `__post_init__` : `object.__setattr__(self, "mac", validate_mac(self.mac, case="upper"))` — valide+normalise la MAC, calqué sur `NetworkDevice`. `name`/`pinned_ip` non validés dans le modèle (politique injectée au loader, le modèle reste générique). Le type `mac: str` suffit à mypy ; la garde `isinstance` sur l'entrée non typée reste dans le loader.

**`load_lan_clients`** — chargeur générique :
```python
def load_lan_clients(
    entries: object,
    *,
    name_validator: Callable[[object], str | None] | None = None,
    ip_validator: Callable[[object], str | None] | None = None,
    dedup_names: bool = False,
    require_non_empty: bool = False,
) -> tuple[LanClient, ...]:
```
Contrat (tout ce que l'appelant doit savoir) :
- `entries` doit être une liste ; chaque entrée une table (`dict`), sinon `ValueError` (F-02).
- MAC : lue sous la clé `mac`, garde `isinstance(str)` puis `validate_mac(case="upper")` ; dédoublonnage MAC **toujours actif** → `ValueError` "MAC en doublon : …".
- `name_validator`/`ip_validator`, quand fournis, sont appelés avec la valeur brute **y compris `None`** (`raw.get(...)`), doivent lever `ValueError` si invalide et **retourner la valeur à stocker** (str ou None). Sans validateur : valeur prise telle quelle si c'est une `str`, sinon `None`.
- `dedup_names=True` : `ValueError` si deux `name` identiques (ignore les `None`).
- `require_non_empty=True` : `ValueError` si la liste est vide.
- Retour : `tuple[LanClient, ...]` immuable, ordre d'entrée préservé.

**Verdict « module profond » (Q-01)** — loader = module profond :
- *Suppression* : le retirer fait réapparaître le squelette (check table, garde+validate+normalise+dédup MAC, validation nom/IP, dédup nom, construction) chez `_parse_clients` **et** `_parse_client_macs` **et** transitivement `router apply` → complexité réapparue chez N appelants, le module gagne sa place.
- *Levier* : un appel porte ~7 comportements derrière 4 paramètres ; l'appelant ignore tout du format DNS/IP. Les callbacks portent une vraie logique métier (filtrage sémantique d'IP via `ipaddress`, non exprimable en regex), pas « repasser une regex » → pas d'abstraction superficielle.
- *Fuite* : seul point à documenter explicitement — les validateurs sont invoqués avec `None` et doivent retourner la valeur stockée ; sinon la précondition fuit vers l'appelant.
- *Seam* : les deux `Callable` sont le seam, testables à travers l'interface publique (passer un validateur, asserter levée/retour). Deux comportements réels par seam (validateur Pi-hole **vs** défaut générique) → seam réel, pas abstraction prématurée.

## 3. Résolution Q-01 → Q-04

- **Q-01 — Callable, pas déclaratif.** La règle IP (`_usable_address` : loopback/link-local/multicast/réservée) n'est pas exprimable en regex/flags ; la décliner en options déclaratives élargirait l'interface du loader avec des concepts DNS/IP Pi-hole, cassant la généricité exigée (besoin : « règles injectées, pas imposées »). Les callbacks ont du levier et gardent le loader ignorant du métier. Deux callbacks seulement (`name_validator`, `ip_validator`), keyword-only.
- **Q-02 — Modèle unique `LanClient`, pas de type séparé pour `pihole_schedule`.** `name`/`pinned_ip` optionnels couvrent le cas « MAC seules ». `pihole_schedule` appelle le loader puis projette `tuple(c.mac for c in clients)` → `client_macs` reste `tuple[str, ...]` inchangé en aval. Son entrée (liste de MAC nues) est adaptée au contrat table par un wrap trivial `[{"mac": m} for m in raw]` au point d'appel : le loader garde une **seule** forme d'entrée (liste de tables), interface étroite préservée.
- **Q-03 — `LanClient` / `load_lan_clients` dans un nouveau module `network/clients.py`.** Pas `models.py` (réservé aux appareils découverts, dataclasses pures sans loader) ni `config.py` (dataclasses de config sans loader). Modèle *déclaré* + son chargeur = une unité cohésive. Export via `__all__`.
- **Q-04 — Dédup nom = option générique du loader (`dedup_names`), défaut `False`.** Politique réutilisable (unicité d'un champ optionnel) ; la garder dans le loader évite à l'appelant de re-parcourir les enregistrements et profite du set déjà tenu. Dédup MAC reste inconditionnel (les 3 appelants l'exigent).

**`LanClient` vs `NetworkDevice` : distincts, mapping au point d'usage.** `NetworkDevice` exige `ip`, porte 11 champs d'observation (vendor, device_type, first_seen…) ; `LanClient` n'exige que `mac`. Responsabilités différentes (déclaré vs découvert). `router apply` **mappe** `LanClient → NetworkDevice` (déjà le cas aujourd'hui) ; aucune fusion, aucune duplication.

## 4. SOLID par responsabilité

| Classe/module | S (responsabilité unique) | O (extension) | L (substitution) | I (interface) | D (dépendances injectées) |
|---|---|---|---|---|---|
| `LanClient` | Porter un client LAN déclaré validé (immuable) | Champs stables ; enrichissement hors périmètre | N/A — pas d'héritage (frozen dataclass) | 3 attributs, aucune méthode superflue | `validate_mac` (import lib) |
| `load_lan_clients` | Valider une liste brute → enregistrements uniques | Politiques nom/IP/dédup/non-vide **injectées**, loader fermé à la modification | N/A — fonction | 4 kwargs ciblés ; aucun concept DNS/IP dans la signature | `name_validator`/`ip_validator` (Callable, seam réel : 2 comportements) |
| `_dns_label`/`_usable_ip` (webapitools) | 1 règle métier chacune | — | — | 1 entrée → 1 sortie | `_LABEL_RE` / `_usable_address` |

**Garde-fou anti sur-design** : pas de `Protocol`/`ABC` — l'injection se fait par `Callable` nu, deux comportements réels existent (validateur Pi-hole + défaut lib) donc le seam est justifié, sans sur-abstraire.

## 5. Sécurité

Surface réseau : **aucune** dans le périmètre (le loader est du parsing/validation pur ; TOML déjà décodé par l'appelant ; pas de `subprocess`, désérialisation, chemins, secrets). L'exposition LAN est le fait des appelants, déjà couverte (`require_lan_url`/`lan_session`).

| Menace / surface | Frontière de confiance | Contrôle retenu | Module porteur |
|---|---|---|---|
| Entrée TOML malformée (A03/A04, confiance modérée) | Appelant (TOML) → loader | Validation à l'entrée : type liste, entrée = table, MAC `isinstance`+`validate_mac` (`re.fullmatch`, motif fixe, pas de ReDoS), unicité | `load_lan_clients` |
| Règles métier nom/IP (label DNS, IP exploitable) | loader → validateur injecté | Échec fermé : valeur invalide ou absente → `ValueError` remontée à la CLI | `_dns_label`/`_usable_ip` (webapitools) |

Pas de menace hors CDC. Aucun contrôle structurant nouveau (le lieu de validation — « à l'entrée, côté loader » — est acté §7 ADR).

## 6. Bibliothèques

Stdlib uniquement : `dataclasses`, `collections.abc.Callable`, et `re` (déjà via `validate_mac`). **Aucune dépendance nouvelle** — confirmé (contrainte §6 CDC respectée).

## 7. Décisions pour ADR

- 📌 **À consigner en ADR** : « Modèle de client LAN générique (`LanClient`) + chargeur `load_lan_clients` dans `linuxtools.network`, politiques nom/IP injectées par `Callable` — la lib reste ignorante des règles DNS/Pi-hole. » (Pivot consommé par 3 modules webapitools, bénéficiaires futurs scanNetHome/NAS.)
- 📌 **À consigner en ADR** : « `LanClient` (déclaré) distinct de `NetworkDevice` (découvert) ; mapping au point d'usage, jamais de fusion. »

## 8. Impact sur le plan

Ordre imposé (linuxtools d'abord, release, puis webapitools) :

1. `[TDD][SEC]` linuxtools : `LanClient` + `load_lan_clients` dans `network/clients.py` (tests : table/MAC/dédup MAC, validateurs injectés levant/retournant, `dedup_names`, `require_non_empty`, liste non-liste). Couverture ≥ 80 %.
2. linuxtools : export `__all__`, CHANGELOG, bump mineur **v2.6.0**, tag.
3. webapitools : bump pin `@v2.6.0` **+ les 3 `--branch`** figés de la CI (piège : oublier un job → clone d'un tag sans le symbole → échec import).
4. `[TDD]` webapitools `pihole_dns` : extraire `_dns_label`/`_usable_ip`, `_parse_clients` → loader, `ZoneConfig.clients: tuple[LanClient, ...]`, supprimer `ClientRecord`.
5. `[TDD]` webapitools `pihole_schedule` : `_parse_client_macs` → `load_lan_clients([{"mac": m} for m in raw], require_non_empty=True)` + projection `.mac`.
6. webapitools `cli._cmd_router_apply` : `hostname=c.name or ""` (piège mypy : `LanClient.name` est `str | None` alors que `ClientRecord.name` était `str` et `NetworkDevice.hostname` est `str`).
7. webapitools `_shared.py` : supprimer `normalize_mac` (+ tests associés), vérifier aucun autre importeur.

Pièges à baliser dans le plan :
- **Messages d'erreur** : le loader porte des messages génériques (« au moins un client LAN requis », « nom en doublon : … »). `pihole_schedule`/`pihole_dns` ont des libellés propres (« au moins un client requis », « nom de client en doublon »). Si une suite de tests webapitools asserte la chaîne exacte, ajuster l'assertion (ValueError + clarté préservés, F-07) — ce n'est pas un changement de comportement utilisateur.
- **`pihole_schedule` entrée non-liste** : parité avec l'actuel (itération de chaîne / TypeError sur non-itérable), ne pas « corriger » le comportement sans le vouloir.
- **mypy --strict des deux côtés, gate bloquant** : zéro `# type: ignore`, zéro `ignore_missing_imports` (linuxtools expose `py.typed`).

## 9. Écarts assumés à l'implémentation (revue passe 1 → F01, F02, F05)

- **Clé d'entrée IP = `ip`** (clé TOML existante de `pihole_dns`), stockée dans `LanClient.pinned_ip`. Clés lues : `mac`, `name`, `ip`. (F01)
- **Messages d'erreur compatibles webapitools** (CDC §2/§8 : aucun changement observable) : le loader reprend les libellés existants (`client doit être une liste de tables`, `entrée de client invalide`, `MAC invalide`, `MAC en doublon`, `nom de client en doublon`, `au moins un client requis`). Le piège « messages génériques à ajuster » du §8 est **périmé** : aucune assertion webapitools à modifier. (F02)
- **MAC validée avant les validateurs nom/IP** (ordre des erreurs identique à l'existant). Les validateurs sont appelés avec `None` : `_usable_ip(None)` doit renvoyer `None`.
- **Export racine** `linuxtools.__init__` en plus de `linuxtools.network`. (F05)
