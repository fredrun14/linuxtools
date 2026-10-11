# Cahier des Charges — Chargeur de clients LAN générique

> **Date :** 2026-10-11
> **Statut :** Validé
> **Auteur :** Frédéric

---

## 1. Contexte et Problématique

### Problème à résoudre
webapitools parse une liste déclarative de « clients LAN » (MAC + nom +
IP optionnelle, lus depuis un TOML) à trois endroits qui se recouvrent :

- `apps/pihole_dns.py::_parse_clients` → `ClientRecord(mac, name, pinned_ip)` :
  entrée = table, MAC validée/normalisée via `normalize_mac`, nom contraint
  à un label DNS (`_LABEL_RE`), IP optionnelle filtrée par `_usable_address`,
  dédoublonnage sur **MAC et nom** ;
- `apps/pihole_schedule.py::_parse_client_macs` → `tuple[str, ...]` : MAC
  seules, dédoublonnage MAC, « au moins un client requis » ;
- `cli.py::_cmd_router_apply` → réutilise déjà `load_zone_config`/`ClientRecord`
  de `pihole_dns` pour fabriquer des `NetworkDevice`.

Le squelette universel (vérifier que l'entrée est une table, valider +
normaliser la MAC, garantir l'unicité, bâtir des enregistrements immuables)
est réécrit ou détourné à chaque fois. `normalize_mac` a déjà été remonté
dans `linuxtools.network.validators` (v2.5.1, PR #135) ; la notion de
« client LAN » — concept réseau générique — reste, elle, dans la couche
applicative de webapitools.

### Solution envisagée
Faire de `linuxtools.network` la source unique du **modèle de client LAN**
et du **chargeur de liste de clients**. Le chargeur porte le travail
universel ; les règles spécifiques (nom = label DNS, filtrage d'IP
exploitable) sont **injectées en paramètres** par l'appelant, pas imposées
par la lib. webapitools consomme ce chargeur dans ses trois points. Seule la
liste de clients est extraite : l'enveloppe propre à Pi-hole (`zone`,
`[[target]]`) et l'ouverture du fichier TOML restent chez l'appelant.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Modèle immuable de client LAN dans `linuxtools.network` (MAC, nom
      optionnel, IP épinglée optionnelle).
- [ ] Chargeur générique d'une **liste** de clients LAN (entrées brutes
      déjà extraites du TOML par l'appelant) : validation de forme, MAC via
      `validate_mac`, unicité, construction des enregistrements.
- [ ] Points d'injection pour les règles spécifiques : validation du nom et
      filtrage/validation de l'IP (le défaut de la lib reste générique).
- [ ] Option « liste non vide requise » (contrat de `pihole_schedule`).
- [ ] Migration des **3** consommateurs webapitools vers ce chargeur, à
      comportement externe inchangé.
- [ ] Bump `linuxtools` (mineur : ajout rétro-compatible), entrée CHANGELOG,
      bump du pin `webapitools` + des 3 `--branch` figés de la CI webapitools.

### Exclu (Out of Scope)
- Extraction de l'enveloppe Pi-hole (`zone`, `[[target]]`) ou de l'ouverture
  du fichier TOML : chaque appelant garde son enveloppe et lit son fichier.
- Nouveau format de déclaration ou champ client supplémentaire : on
  factorise l'existant (MAC, nom, IP), sans enrichir le modèle.
- Tout changement observable pour l'utilisateur des CLI webapitools
  (dry-run, messages, codes de sortie).
- Consommation par d'autres dépôts (scanNetHome, outils NAS) : bénéfice
  futur possible, hors de ce chantier.

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Frédéric (+ assistant-codage) | Implémente la solution |
| Utilisateur    | Frédéric     | Utilise les CLI webapitools  |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité    | Description                                                                 |
|------|-------------|-----------------------------------------------------------------------------|
| F-01 | Must have   | `linuxtools.network` expose un modèle immuable de client LAN (MAC + nom optionnel + IP épinglée optionnelle), MAC normalisée. |
| F-02 | Must have   | Chargeur générique : liste d'entrées brutes → tuple d'enregistrements validés. Rejette une entrée non-table, une MAC absente/invalide, une MAC en doublon. |
| F-03 | Must have   | Le chargeur accepte un **validateur de nom** optionnel (injecté) ; sans lui, le nom est une chaîne libre optionnelle. Dédoublonnage de nom activable. |
| F-04 | Must have   | Le chargeur accepte un **filtre/validateur d'IP** optionnel (injecté) ; sans lui, l'IP est une chaîne libre optionnelle. |
| F-05 | Must have   | Option « au moins un client requis » (défaut : liste vide tolérée). |
| F-06 | Must have   | `pihole_dns`, `pihole_schedule` et `router apply` chargent leurs clients via ce chargeur, règles DNS/IP injectées, comportement externe inchangé. |
| F-07 | Should have | Messages d'erreur du chargeur clairs et testables (type + contenu), au moins aussi informatifs que l'existant. |
| F-08 | Won't have  | Lecture directe d'un fichier TOML par la lib, ou enveloppe zone/cibles générique. |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                                              |
|-----------------|----------------------------------------------------------------------|
| Performance     | Négligeable (quelques dizaines d'entrées, parsing local).            |
| Disponibilité   | Usage ponctuel en ligne de commande.                                 |
| Sécurité        | Validation stricte d'entrées déclaratives (cf. §7) ; aucune E/S réseau dans le chargeur. |
| Maintenabilité  | `mypy --strict` 0 erreur des deux côtés, gate bloquant ; couverture ≥ 80 % des lignes touchées. |
| Portabilité     | Python 3.11+, aucune dépendance nouvelle.                            |
| Compatibilité   | Ajout rétro-compatible dans `linuxtools` : les appelants existants de `validate_mac`/modèles réseau ne cassent pas. |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                                             |
|---------------|------------------------------------------------------------------------|
| Langage       | Python 3.11+                                                          |
| Environnement | Réseau interne (homelab). Le chargeur lui-même est du parsing pur, sans réseau. |
| Dépendances   | Aucune nouvelle. `linuxtools` reste consommé par pin git figé (`@vX.Y.Z`). |
| Infrastructure| Forgejo Actions (CI webapitools clone `linuxtools` par **tag figé** dans 3 jobs `--branch` → à bumper avec le pin). |
| Données       | Entrées = tables TOML déjà décodées par l'appelant (MAC, nom, IP).    |
| Placement     | Module `linuxtools.network` (près de `validators`, `models`, `config`). Export via `__all__`. |

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement** — Pas d'exposition réseau
- [x] **Réseau interne** — Accessible sur le LAN (les CLI appelantes joignent le LAN)
- [ ] **Exposé Internet** — API publique / interface web

> Le **chargeur** est du parsing/validation pur, sans E/S réseau. L'exposition
> réseau est le fait des appelants (ASUS/Pi-hole), déjà couverts ailleurs
> (`require_lan_url`/`lan_session`). Skills sécurité activés par prudence sur
> la validation d'entrées (A03), mais pas de surface réseau nouvelle ici.

### Exigences de sécurité

| Critère                    | Exigence                                                        |
|----------------------------|-----------------------------------------------------------------|
| Données sensibles          | Aucune (MAC/nom/IP de clients LAN, pas de secret).              |
| Authentification           | N/A (parsing local).                                            |
| Autorisation               | N/A.                                                            |
| Entrées non fiables        | Tables issues d'un TOML local (confiance modérée) : valider type, format MAC, unicité ; déléguer nom/IP aux règles injectées. |
| Surfaces dangereuses       | Aucune (`subprocess`, désérialisation, chemins : absents du chargeur). |
| Secrets                    | Aucun manipulé par le chargeur.                                 |
| Traçabilité                | N/A (échec = `ValueError` explicite remontée à la CLI).         |

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] `linuxtools.network` expose le modèle + le chargeur, dans `__all__`.
- [ ] Le chargeur rejette : entrée non-table, MAC absente/invalide, MAC en
      doublon ; et, quand les règles sont injectées, nom invalide, nom en
      doublon, IP invalide.
- [ ] Les 3 consommateurs webapitools utilisent le chargeur ; leurs suites
      de tests existantes restent vertes **sans réécriture de comportement**.
- [ ] `normalize_mac` et les `_parse_clients`/`_parse_client_macs` dupliqués
      sont supprimés ou réduits à un appel au chargeur générique.
- [ ] Tests unitaires `linuxtools` du chargeur, couverture ≥ 80 % des lignes.
- [ ] `mypy --strict` = 0 erreur des deux côtés (gate bloquant).
- [ ] Aucun warning Bandit sévérité ≥ MEDIUM.
- [ ] CHANGELOG `linuxtools`, docstrings PEP 257, pin + 3 `--branch` CI
      webapitools bumpés vers la nouvelle version.

---

## 9. Livrables Attendus

| Livrable              | Description                                      | Échéance |
|-----------------------|--------------------------------------------------|----------|
| Code `linuxtools`     | Modèle + chargeur dans `src/linuxtools/network/` |          |
| Code `webapitools`    | 3 consommateurs migrés, duplication retirée      |          |
| Tests                 | `linuxtools` (chargeur) + suites webapitools vertes |       |
| Documentation         | CHANGELOG `linuxtools`, docstrings, notes vault des 2 projets |  |
| Release               | Bump `linuxtools`, tag, pin + 3 `--branch` CI webapitools |    |

---

## 10. Questions Ouvertes

| ID   | Question                                                                 | Responsable | Statut |
|------|--------------------------------------------------------------------------|-------------|--------|
| Q-01 | Forme de l'injection des règles nom/IP : callbacks (`Callable`) vs options déclaratives (regex/flags) ? Tranché à l'étape conception/plan selon le test « module profond ». | Frédéric | Ouvert |
| Q-02 | Modèle unique portant un nom/IP optionnels **ou** le chargeur renvoie juste les MAC pour `pihole_schedule` (qui n'a ni nom ni IP) ? Impacte si `pihole_schedule` garde son propre type. | Frédéric | Ouvert |
| Q-03 | Nom du modèle/chargeur dans `linuxtools.network` (ex. `LanClient` / `load_lan_clients`) — cohérent avec `NetworkDevice` existant sans le dupliquer. | Frédéric | Ouvert |
| Q-04 | Le dédoublonnage de nom est-il générique (option) ou propre à Pi-hole (reste côté appelant) ? | Frédéric | Ouvert |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
