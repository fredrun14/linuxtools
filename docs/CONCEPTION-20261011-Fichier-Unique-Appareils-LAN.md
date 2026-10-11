# Conception — Fichier unique des appareils du LAN

> **Date :** 2026-10-11 · **CDC :** CDC-20261011-Fichier-Unique-Appareils-LAN.md · **BESOIN :** BESOIN-20261011-1400-Fichier-Unique-Appareils-LAN.md · **Statut :** Validée le 2026-10-11 (casse et règle « actif prioritaire » tranchées par Frédéric ; chemin, `[[target]]`, v2.7.0 et 0700 validés)

## 0. Constats mesurés (conditionnent la conception)

| Constat | Conséquence |
|---|---|
| `webapitools/config/pihole-dns.toml` est **suivi par git** (5 commits, dont `e56b857`) avec des modifications locales non commitées — il n'est pas « non versionné » | Ne jamais committer le contenu ; le sortir de l'index (`git rm --cached`) après la migration |
| Données : 36 clients (w) / 33 réservations (r) ; 33 MAC communes, 3 seulement dans w, 0 seulement dans r → **36 clients fusionnés, 35 actifs** | Critère « sans perte » vérifiable par comptage |
| Divergences sur MAC commune : noms 14 (**11 de casse seule**, majuscules côté r = labels DNS refusés par `_dns_label`), 3 noms réellement différents ; IP 2 (absentes de w) ; `enabled` 1 (actif w, désactivé r) ; `note` 33 (r) ; table `[meta]` (r) | « r gagne » appliqué tel quel casse `load_zone_config` (cf. §7 point bloquant) |
| Après fusion, les 36 ont IP + nom, 0 IP hors `lan_subnet` | Règles strictes de scanNetHome satisfaites aujourd'hui |
| scanNetHome garde les `enabled = false` : drift `STALE_DISABLED`, dédup IP **entrées désactivées comprises**, filtrage au seul push (F-19) | Le chargeur ne doit **pas** filtrer |
| pve : services root (pas de `User=`), `/opt/config-nas` 0755 root (1 commit), sops ne couvre que `*.env`/`secrets/**` ; `router-lan` jamais déployé (`/etc/webapitools` sans `pihole-dns.toml` ni `router-lan.env`) ; `scannethome.timer` = `reservations --notify` quotidien | Lecture en place, droits par répertoire ; retrait du dépôt de config de `router-lan` sans risque |

## 1. Périmètre & impact

| Dépôt | Fichier | Changement |
|---|---|---|
| linuxtools | `network/clients.py` | `LanClient` + `enabled: bool = True`, `note: str \| None = None` ; schéma `[[client]]` fermé ; CHANGELOG, **v2.7.0** |
| webapitools | `apps/pihole_dns.py` | `load_zone_config` : ne garde que les clients actifs, exige ≥ 1 client actif |
| webapitools | `deploy/router_lan.py` | retrait de `config_deploy` (le fichier vient de config-nas, pas de 2ᵉ copie) |
| webapitools | `config/` | `git rm --cached pihole-dns.toml`, `.gitignore`, `lan-clients.example.toml` (MAC fictives), README |
| webapitools | `pyproject.toml` + 3 `--branch` CI | pin `@v2.7.0` |
| scanNetHome | `pyproject.toml` | pin `@v2.0.1` → `@v2.7.0` (PR dédiée, cf. §8) |
| scanNetHome | `config/reservations.py` | `load_reservations` lit `[[client]]` via `load_lan_clients` ; `[[reservation]]` refusée |
| scanNetHome | `config/reservations.example.toml` | converti en `[[client]]` |
| config-nas | `lan/lan-clients.toml` (**nouveau**) | fichier unique (✅ VALIDÉ (Frédéric, 2026-10-11) : nom/chemin) |

Réemploi : `load_lan_clients`, `validate_mac`, `validate_ipv4`, `ConfTomlExporter.export_mapping` (sait les `[[...]]` depuis 2.2.1, booléens compris) pour le script de migration. Aucune dépendance nouvelle. Hors périmètre : `push-dhcp` (écrit depuis `devices.json`, 3ᵉ écrivain DHCP, cf. §7).

## 2. Modules & interfaces

**(1) `LanClient` étendu** — champs ajoutés **en fin** avec défaut (construction positionnelle et égalité des tests existants inchangées). `note` brute, non interprétée. Pas de validation dans `__post_init__` (contrat inchangé : garde de type sur l'entrée non typée = chargeur).

**`load_lan_clients`** — signature **inchangée**. Contrat ajouté :
- clés admises `{mac, name, ip, enabled, note}` ; toute autre clé → `ValueError` « clé(s) inconnue(s) … — clés admises : … » (vérifiée juste après le contrôle « table ») ;
- `enabled` absent → `True` ; sinon **`bool` strict** (`"false"` refusé, échec fermé) ; `note` absente → `None`, sinon `str` ;
- **aucun filtrage** : les entrées désactivées sont rendues, comptent pour la dédup MAC, `dedup_names` et `require_non_empty`. Filtrer appartient à l'appelant (une ligne, sémantique propre à chaque appli).

**(2) Clé d'entrée : `[[client]]` unique.** `[[reservation]]` disparaît ; scanNetHome lève `ReservationsConfigError` explicite si la table est présente (« renommer en `[[client]]` ») — sinon un ancien fichier passerait pour une liste vide.

**(3) Sections non-client** — racine **ouverte** (chaque appli ignore ce qu'elle ne lit pas : F-07), `[[client]]` **fermée** (schéma commun, une faute de frappe sur `enabled` ne passe plus). Raison : une clé propre à une appli dans `[[client]]` serait rejetée par l'autre ; le schéma commun est donc le seul cohérent, son évolution passe par linuxtools. Contenu racine : `zone`, `lan_subnet`, `[[target]]` (lus par webapitools ; ✅ VALIDÉ (Frédéric, 2026-10-11) : `[[target]]` inclus comme « config Pi-hole »), `[[client]]` (les deux). `[meta]` de r non migrée (commentaire d'en-tête). Garde-fous contre une faute de frappe de table : webapitools « ≥ 1 client actif » ; scanNetHome `require_non_empty=True` + refus `[[reservation]]`. scanNetHome garde son subnet dans `network.toml` (`network.cidr`, Q-02) et ignore `lan_subnet`.

| Module | Rôle | Interface (ce que l'appelant doit savoir) | Grille |
|---|---|---|---|
| `load_lan_clients` | liste brute → `LanClient` uniques | + schéma fermé, `enabled`/`note` typés, pas de filtrage | Suppression : la garde clés/types réapparaîtrait chez 2 applis → gagne sa place. Levier accru sans paramètre nouveau |
| `load_zone_config` (w) | TOML → `ZoneConfig` | `clients` = **actifs seulement** | Filtrer ici (et pas via `active_clients`) évite la fuite : `router apply` ne peut pas oublier le filtre et blanchir une MAC désactivée |
| `load_reservations` (s) | TOML → `list[Reservation]` | **signature inchangée** ; validateurs `_required_name`, `_ipv4_in(subnet)` injectés ; dédup IP après chargement (`_check_no_duplicate`, désactivées comprises) | `Reservation` survit au test de suppression : `name`/`ip` typés `str`, MAC minuscule alignée sur `NetworkDevice` (drift), `to_device()` |

**(5) Migration** — script ponctuel **hors dépôts** (scratchpad), `python -I`, lecture seule des deux fichiers locaux : rapprochement par MAC normalisée (`validate_mac(case="upper")`), r gagne sur `name`/`ip`/`note` (casse seule : forme minuscule gardée) ; **`enabled` : l'actif est prioritaire** (`enabled = w ∨ r`), clients w seuls repris tels quels, sortie via `ConfTomlExporter` + en-tête commenté. Il imprime un **rapport de divergences** (par MAC, au terminal, jamais commité) et refuse d'écrire si un des deux chargeurs réels (`load_zone_config`, `load_reservations` avec `network.cidr`) rejette la sortie.

## 3. SOLID par responsabilité

| Classe/module | S | O | L | I | D |
|---|---|---|---|---|---|
| `LanClient` | porter un client déclaré immuable | champs optionnels à défaut | N/A (frozen, pas d'héritage) | 5 attributs, 0 méthode | `validate_mac` |
| `load_lan_clients` | valider la forme commune | politiques nom/IP injectées (inchangé) | N/A (fonction) | aucun kwarg ajouté | `Callable` (seam réel existant) |
| `load_zone_config` (w) | config DNS/routeur active | — | N/A | inchangée | chargeur lib |
| `load_reservations` (s) | réservations strictes | règles via validateurs | N/A | inchangée | `_required_name`, `_ipv4_in` |

Garde-fou anti sur-design : **pas** de `Protocol`, pas de lecteur de fichier commun dans la lib (chaque appli garde son `tomllib.load`, une seule implémentation par appli), pas de kwarg `active_only`/`dedup_ips` (un seul appelant, déjà couvert côté appli).

## 4. Bibliothèques

Stdlib (`tomllib`, `ipaddress`, `dataclasses`) + linuxtools. Aucune lib nouvelle.

## 5. Décisions structurantes

- 📌 À consigner en ADR : « Fichier commun `[[client]]` : schéma fermé dans linuxtools (`mac, name, ip, enabled, note`), racine ouverte ; le chargeur ne filtre jamais `enabled`, chaque appli filtre selon sa sémantique (w au chargement, s au seul push). »
- 📌 À consigner en ADR : « Le fichier commun obéit au consommateur le plus strict : IP+nom de fait obligatoires (scanNetHome), noms = labels DNS (webapitools) ; la permissivité de webapitools n'est qu'une tolérance de lecture. »
- 📌 À consigner en ADR : « Une seule copie sur pve, lue en place depuis config-nas ; aucun dépôt de configuration par `deploy` pour ce fichier. »

## 6. Sécurité

| Menace / surface | Frontière de confiance | Contrôle retenu | Module porteur |
|---|---|---|---|
| TOML édité à la main pilotant routeur/Pi-hole | humain → chargeurs | validation **complète avant tout appel réseau** (existant), schéma fermé, `enabled` booléen strict (échec fermé) | `load_lan_clients` |
| Table mal nommée → 0 client → `--prune` DNS total / whitelist vide | TOML → appli | ≥ 1 client actif (w), `require_non_empty` + refus `[[reservation]]` (s) | `load_zone_config`, `load_reservations` |
| `enabled = false` retire la MAC de la whitelist (perte Wi-Fi) | décision humaine | rapport de migration listant les MAC actif→inactif ; dry-run des deux applis avant tout `--apply` ; sauvegarde NVRAM (s, existant) | script / chantier |
| Vie privée (MAC/IP/noms) | dépôt, disque pve | config-nas privé ; sortie de l'index webapitools + exemple fictif ; pve : répertoire de lecture 0700 root (git ne conserve pas 0600) — ✅ VALIDÉ (Frédéric, 2026-10-11) au chantier | webapitools repo, chantier |
| Secrets | dépôt | aucun secret dans le fichier (mots de passe via `CredentialManager`/`.env` sops) ; gitleaks en CI config-nas ; pas de règle sops `.toml` | config-nas |
| Dérive par 2ᵉ copie | deploy | `router-lan` ne dépose plus de config | `deploy/router_lan.py` |

📌 À consigner en ADR : lieu de validation = chargeurs, avant toute écriture (déjà acté ADR `lan-client-loader-politiques-injectees`, étendu au schéma fermé).

## 7. Risques & points ouverts

- ✅ **Tranché (Frédéric, 2026-10-11) — casse** : dérogation acceptée ; **actif prioritaire** sur `enabled` en cas de divergence (l'appareil actif côté w et désactivé côté r reste actif, donc dans la whitelist). Point initial : 11 noms r ne diffèrent que par la casse (majuscules → refusés par `_dns_label`). Recommandé : le script garde la forme minuscule pour une divergence **de casse seule** (dérogation bornée à Q-04) — DNS inchangé (FQDN déjà minuscule), hostname routeur = ce que pousse déjà `router apply`. Alternative écartée : `_dns_label` insensible à la casse (exige une dédup de nom insensible à la casse, sinon collision FQDN silencieuse).
- 3 noms réellement différents → 3 nouveaux FQDN (anciens conservés sauf `--prune`) ; 1 MAC divergente sur `enabled` reste **active** (règle « actif prioritaire »), donc aucune perte de Wi-Fi ; elle est listée au rapport ; 2 clients gagnent une IP épinglée. Tous listés dans le rapport.
- Schéma fermé = validation plus stricte en mineure (2.7.0) : les 2 consommateurs actuels ne lisent que `mac/name/ip` (vérifié : fichiers réels et tests) — ✅ VALIDÉ (Frédéric, 2026-10-11) : mineure plutôt que majeure.
- Message d'erreur scanNetHome moins précis (perte de « entrée #n (libellé) » sur les erreurs levées par le chargeur ; la MAC fautive reste citée).
- Bump scanNetHome 2.0.1 → 2.7.0 : webapitools passé en extra `network` (2.1.0) — sans effet, scanNetHome déclare `webapitools@v0.13.0`, même tag que l'extra ; `SecretsSpec` multi-services (2.2.1) non utilisé ; `backup_venv` refuse un venv lien (2.3.x) — `/opt/scannethome/venv` est un vrai répertoire ; `fullmatch` (2.5.1) plus strict. **`scripts/deploy_noeud.py` est hors du périmètre mypy CI** (`scan_net_home/ tests/`) : le passer à `mypy --strict` une fois.
- Tests webapitools construisant une config sans `[[client]]` : à adapter (≥ 1 client actif).
- Deux sources de subnet (`network.cidr` / `lan_subnet`) égales aujourd'hui ; CDC §9 « config réseau depuis le fichier unique » lu comme « `[[client]]` », Q-02 prévalant.
- Hors CDC : `push-dhcp` (inventaire) reste un 3ᵉ écrivain DHCP ; historique git webapitools (et miroir GitHub privé) contient les données réelles — purge non prévue.

## 8. Impact sur le plan

1. `[TDD][SEC]` linuxtools : `enabled`/`note` (défauts, bool strict, `note` str), schéma fermé (message listant les clés admises), non-filtrage des désactivées (dédup MAC/nom, `require_non_empty`) ; README, CONTEXT.md (invariant « le chargeur ne filtre pas `enabled` »).
2. linuxtools : CHANGELOG (Ajouté + Modifié : schéma fermé), **v2.7.0**, tag — PR 1.
3. `[TDD][SEC]` webapitools PR 2 : pin `@v2.7.0` **+ 3 `--branch`** ; `load_zone_config` filtre les actifs + « au moins un client actif requis » ; `router apply`/`pihole apply` testés avec un client désactivé (absent de la whitelist, du DNS, des réservations).
4. `[SEC]` webapitools PR 3 : `git rm --cached config/pihole-dns.toml` (copie locale conservée jusqu'à la fin de la migration), `.gitignore`, `lan-clients.example.toml`, README ; `router_lan` sans `config_deploy` (+ test).
5. scanNetHome branche 1 : bump `@v2.7.0` seul, tests + `mypy --strict scan_net_home/ tests/ scripts/` à 0, aucune fonctionnalité.
6. `[TDD][SEC]` scanNetHome branche 2 : `load_reservations` → `[[client]]` via `load_lan_clients` (`_required_name`, `_ipv4_in(subnet)`, `require_non_empty=True`), mapping `LanClient → Reservation` (narrowing explicite de `name`/`pinned_ip`, sans `# type: ignore` ni `assert`), dédup IP désactivées comprises, refus `[[reservation]]`, exemple converti, README.
7. `[SEC]` Script de migration ponctuel (hors dépôts) : fusion par MAC, règle de casse validée au §7, rapport de divergences, validation par les deux chargeurs réels avant écriture ; contrôle 36 clients / 35 actifs.
8. config-nas : PR `lan/lan-clients.toml` (gitleaks vert) ; optionnel : job CI de parse TOML.
9. Chantier pve (`nas-plan-chantier`, hors code) : pull config-nas, répertoire 0700, redéploiement des deux applis, `paths.reservations` de `network.toml` → chemin config-nas, dry-run `router apply` + `scannethome reservations` avant tout `--apply`, suppression des anciennes copies.
