# Cahier des Charges — Fichier unique des appareils du LAN
> **Date :** 2026-10-11
> **Statut :** Brouillon
> **Auteur :** Frédéric (brouillon : Claude, depuis `BESOIN-20261011-1400-Fichier-Unique-Appareils-LAN.md`)

---

## 1. Contexte et Problématique

### Problème à résoudre
La liste des appareils du LAN (MAC, nom, IP) existe en deux copies qui dérivent :
`webapitools/config/pihole-dns.toml` (`[[client]]`) et
`scanNetHome/config/reservations.toml` (`[[reservation]]`). Sur le nœud pve, chaque
appli a sa propre copie sous `/opt/<appli>/src/config/`. Un appareil ajouté ou
réactivé d'un seul côté (ex. msiwifi) met Pi-hole, le routeur et scanNetHome en désaccord.

### Solution envisagée
Un seul fichier TOML fait foi pour les appareils du LAN et pour la configuration
LAN/Pi-hole de `pihole-dns.toml` (zone, `lan_subnet`). webapitools et scanNetHome le lisent via le chargeur
de linuxtools, chacun ignorant les sections qui ne le concernent pas.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Un fichier TOML unique : sections de config LAN/Pi-hole de `pihole-dns.toml` + `[[client]]`
- [ ] Schéma commun de `[[client]]` : `mac`, `name`, `ip` (existant) + `enabled`, `note` (nouveaux, optionnels)
- [ ] Lecture par webapitools et par scanNetHome, chemin configurable
- [ ] Fichier versionné par git, déployé sur le nœud pve à un chemin configuré
- [ ] Migration des deux fichiers actuels vers le fichier unique
- [ ] Redéploiement de webapitools et scanNetHome sur pve, en même temps que la mise en service (chantier infra via `nas-plan-chantier`)

### Exclu (Out of Scope)
- Fusion du code des deux applis (seule la source de données est unifiée)
- Commande de synchronisation entre fichiers (il n'y en a plus qu'un)
- Imposer à webapitools les règles strictes de scanNetHome (IP et nom obligatoires)
- `network.toml` de scanNetHome (reste un fichier à part)
- `pihole-schedule*.toml` et `doh-providers.toml` de webapitools (restent à part)

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Claude / Frédéric | Implémente la solution  |
| Utilisateur    | Frédéric     | Poste de dev et nœud pve     |

---

## 4. Objectifs Fonctionnels

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | Un seul fichier TOML contient les appareils du LAN et la config LAN/Pi-hole de `pihole-dns.toml` ; modifier un appareil à un endroit suffit |
| F-02 | Must have       | webapitools et scanNetHome lisent ce fichier ; chacun ignore les sections qui ne le concernent pas |
| F-03 | Must have       | `[[client]]` gagne `enabled` (défaut `true`) et `note` (optionnels), lus via le chargeur linuxtools ; un client `enabled = false` est exclu pour les deux applis |
| F-04 | Must have       | Chemin du fichier configurable pour chaque appli (option CLI et/ou clé de config) |
| F-05 | Must have       | scanNetHome continue d'exiger IP et nom et de valider subnet et doublons, via ses validateurs injectés ; webapitools reste permissif (IP facultative) |
| F-06 | Must have       | Le fichier est versionné par git |
| F-07 | Should have     | Une section inconnue ou une clé inconnue d'une autre appli ne provoque pas d'erreur |
| F-08 | Should have     | Les secrets éventuels ne sont pas versionnés en clair |
| F-09 | Could have      | scanNetHome publie une commande de contrôle de cohérence du fichier |
| F-10 | Won't have      | Synchronisation bidirectionnelle entre l'ancien et le nouveau format |

> ✅ VALIDÉ (Frédéric, 2026-10-11) : `enabled` et `note` sont ajoutés à `LanClient` dans linuxtools
> (champs optionnels, rétrocompatibles) plutôt que lus à part par chaque appli.

---

## 5. Objectifs Non-Fonctionnels

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | [...]                                         |
| Disponibilité   | Usage ponctuel + timers sur pve ; un fichier invalide doit échouer avant toute écriture routeur/Pi-hole |
| Sécurité        | Voir § 7                                      |
| Maintenabilité  | `mypy --strict` à 0 et couverture ≥ 80 % dans les trois projets ; gate mypy bloquant |
| Portabilité     | Fedora (poste) et Proxmox/Debian (nœud pve), Python 3.11+ |
| Compatibilité   | Rétrocompatibilité du chargeur linuxtools pour les consommateurs actuels (v2.6.x) |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|----------------------------------------------------------|
| Langage       | Python 3.11+ (`tomllib` en lecture seule)                |
| Environnement | Réseau interne                                           |
| Dépendances   | linuxtools (pin par tag Forgejo dans chaque projet ; CI de webapitools clone linuxtools par tag figé) |
| Infrastructure| Forgejo-first ; nœud pve : `/opt/webapitools`, `/opt/scannethome`, venvs dédiés |
| Données       | ~36 clients ; fichier actuel non versionné dans webapitools (`config/pihole-dns.toml`) |

> Constaté sur pve (2026-10-11) : webapitools embarque linuxtools 2.3.0, scanNetHome
> `@v2.0.1`. Le redéploiement des deux est fait en même temps que la mise en service
> du fichier unique (Q-05).

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement**
- [x] **Réseau interne** — le fichier pilote des écritures sur le routeur (NVRAM DHCP, liste blanche MAC) et Pi-hole
- [ ] **Exposé Internet**

### Exigences de sécurité

| Critère                    | Exigence                                                        |
|----------------------------|-----------------------------------------------------------------|
| Données sensibles          | MAC/IP/noms d'appareils du foyer (vie privée) ; [...] secrets Pi-hole/routeur : à confirmer |
| Authentification           | N/A (fichier local)                                             |
| Autorisation               | Droits fichier restrictifs sur pve (0600 aujourd'hui) ; dépôt git privé |
| Entrées non fiables        | Le TOML (édité à la main) : MAC, noms, IP, chemins validés avant toute écriture |
| Surfaces dangereuses       | Écritures routeur/Pi-hole pilotées par le fichier : un fichier erroné fait perdre le Wi-Fi à des appareils (liste blanche) |
| Secrets                    | [...] jamais en clair dans le dépôt (`sops`, déjà en place dans `config-nas`) |
| Traçabilité                | L'historique git du fichier tient lieu de journal des changements |

---

## 8. Critères d'Acceptation

- [ ] Un appareil modifié dans le fichier unique est vu à l'identique par `webapitools router apply` (dry-run) et par `scannethome reservations`
- [ ] Aucun second fichier d'appareils n'est lu par l'une ou l'autre appli
- [ ] Un client `enabled = false` est ignoré par les deux applis
- [ ] scanNetHome rejette toujours une entrée sans IP ou sans nom, ou hors subnet ; webapitools accepte une entrée sans IP
- [ ] Les sections propres à l'autre appli sont ignorées sans erreur
- [ ] Les deux fichiers actuels sont migrés sans perte (36 clients webapitools, 33 réservations scanNetHome, rapprochés par MAC) ; en cas de divergence sur un MAC, la valeur de `reservations.toml` l'emporte
- [ ] Tests unitaires ≥ 80 % de couverture, `mypy --strict` à 0 dans linuxtools, webapitools, scanNetHome
- [ ] Aucun warning Bandit MEDIUM ou plus
- [ ] README, docstrings, notes du vault à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|-------------------------------------|-------------|
| linuxtools            | `LanClient` étendu (`enabled`, `note`), nouvelle version taguée | [...] |
| webapitools           | Lecture du fichier unique, pin + 3 `--branch` CI du tag linuxtools | [...] |
| scanNetHome           | Migration vers `load_lan_clients`, pin linuxtools relevé (v2.0.1 → v2.x), lecture de la config réseau depuis le fichier unique | [...] |
| Fichier unique        | Versionné dans `config-nas` (Forgejo) | [...] |
| Chantier pve          | Redéploiement des deux applis + dépôt du fichier unique sur le nœud | [...] |
| Documentation         | README, CONTEXT.md, ADR, notes vault | [...] |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|---------------------------------------|-------------|----------|
| Q-01| Dépôt git du fichier | Frédéric | **Tranché : `config-nas`** |
| Q-02| `network.toml` de scanNetHome dans le fichier unique ? | Frédéric | **Tranché : non** |
| Q-03| `pihole-schedule*.toml` et `doh-providers.toml` dans le fichier unique ? | Frédéric | **Tranché : non** |
| Q-04| Divergence sur un même MAC à la migration | Frédéric | **Tranché : `reservations.toml` l'emporte** |
| Q-05| Redéploiement des applis sur pve | Frédéric | **Tranché : en même temps** que la mise en service |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (conception puis `python-plan-todo`).
