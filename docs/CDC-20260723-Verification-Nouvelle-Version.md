# Cahier des Charges — Vérification Nouvelle Version
> **Date :** 2026-07-23
> **Statut :** Brouillon
> **Auteur :** Frederic

---

## 1. Contexte et Problématique

### Problème à résoudre
`Deployer.deploy()` transporte et réinstalle systématiquement, sans savoir
si la cible a déjà la dernière version. On redéploie même quand rien n'a
changé, ce qui gaspille du temps et bruite les logs sur les cibles
distantes.

### Solution envisagée
Pouvoir demander, avant ou indépendamment d'un déploiement, si une cible
(locale ou distante) tourne déjà avec la dernière version disponible en
source — en comparant le numéro de version du `pyproject.toml` source
local à celui effectivement installé dans le venv cible. Cette
vérification doit être utilisable en code (en amont de `deploy()`, pour
sauter un déploiement inutile) et en CLI (sous-commande dédiée pour
interroger l'état d'une cible sans déclencher de déploiement).

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Fonction/service retournant si une cible est à jour ou non, avec
      les deux numéros de version en clair (source vs installée)
- [ ] Comparaison basée uniquement sur le numéro de version du
      `pyproject.toml` source vs la version installée dans le venv cible
- [ ] Utilisable en code, en amont de `Deployer.deploy()`
- [ ] Sous-commande CLI dédiée pour interroger l'état d'une cible sans
      déclencher de déploiement
- [ ] Fonctionne sur cible locale et cible distante (SSH)
      > ⚠️ HYPOTHÈSE À VALIDER — déduit du fait que le module `deploy`
      > existant cible déjà des hôtes locaux et distants via
      > `SshCommandExecutor` ; le besoin ne le précise pas explicitement.

### Exclu (Out of Scope)
- Détection basée sur un hash git ou un checksum de fichiers —
  uniquement le numéro de version `pyproject.toml`
- Déclenchement automatique d'un déploiement si la cible est obsolète —
  la fonction informe, elle ne décide pas
- Gestion de plusieurs cibles en une seule commande (fan-out) — une
  cible à la fois, comme le reste du module `deploy`

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | Frederic     | Implémente la solution       |
| Utilisateur    | Frederic     | Utilise le livrable final    |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | Fonction qui renvoie, pour une cible donnée, si elle est à jour ou non par rapport à la version source, avec les deux numéros de version en clair |
| F-02 | Must have       | Utilisable en code, indépendamment de `deploy()`, pour sauter un déploiement inutile |
| F-03 | Should have     | Sous-commande CLI dédiée pour interroger l'état d'une cible sans déclencher de déploiement |
| F-04 | Won't have      | Vérification simultanée de plusieurs cibles (fan-out) |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | [...] |
| Disponibilité   | Usage ponctuel (appel local ou CLI, pas de service continu) > ⚠️ HYPOTHÈSE À VALIDER — cohérent avec le reste du module `deploy`, non précisé dans le besoin |
| Sécurité        | Pas d'exposition réseau nouvelle — réutilise l'exécuteur SSH existant du module `deploy` > ⚠️ HYPOTHÈSE À VALIDER |
| Maintenabilité  | Couverture de tests ≥ 90 % > ⚠️ HYPOTHÈSE À VALIDER — seuil déjà en vigueur sur le module `deploy` (cf. `docs/CHECKLIST-20260719-Module-Deploy.md`) |
| Portabilité     | Linux, Python 3.11+ > ⚠️ HYPOTHÈSE À VALIDER — convention du projet `linuxtools` (`CLAUDE.md`), non répétée dans le besoin |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|-----------------------------------------------------------|
| Langage       | Python 3.11+, stdlib uniquement > ⚠️ HYPOTHÈSE À VALIDER — convention `linuxtools` |
| Environnement | Local et réseau interne homelab (cibles Forgejo, NAS DIY, via SSH) |
| Dépendances   | Lecture du `pyproject.toml` source via `tomllib` (stdlib, read-only) > ⚠️ HYPOTHÈSE À VALIDER — convention projet |
| Infrastructure| Intégration au module `linuxtools.deploy` existant |
| Données       | Numéros de version `pyproject.toml` (source) et version installée dans le venv cible — pas d'autre donnée |

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement** — Pas d'exposition réseau
- [x] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> ⚠️ Case cochée par déduction — le module `deploy` existant opère déjà sur
> des cibles distantes homelab via SSH ; le besoin ne le confirme pas
> explicitement pour cette fonctionnalité.
>
> ⚠️ Si « Réseau interne » ou « Exposé Internet » : activer les skills
> `python-owasp-security`, `python-sast-bandit-security`, `python-security-monitoring`.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] On peut appeler une fonction qui renvoie, pour une cible donnée, si
      elle est à jour ou non par rapport à la version source, avec les
      deux numéros de version en clair
- [ ] Une sous-commande CLI dédiée permet d'interroger l'état d'une
      cible sans déclencher de déploiement
- [ ] Tests unitaires passent avec couverture ≥ 80 %
- [ ] Aucun warning Bandit sévérité MEDIUM ou supérieure
- [ ] Documentation (README, docstrings) à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | Module(s) Python dans `src/linuxtools/deploy/` |             |
| Tests                 | `tests/` avec couverture ≥ 80 %     |             |
| Documentation         | `README.md` + docstrings PEP 257    |             |
| Makefile              | Commandes `make install/test/lint`  |             |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|---------------------------------------|-------------|----------|
| Q-01| Quel nom pour la sous-commande CLI (ex. `deploy check-version`) ?  | Frederic    | Ouvert   |
| Q-02| Comportement attendu si le venv cible n'existe pas encore (jamais déployé) ? | Frederic | Ouvert |
| Q-03| La vérification doit-elle fonctionner sur cible distante (SSH) dès la v1, ou local uniquement pour commencer ? | Frederic | Ouvert |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
