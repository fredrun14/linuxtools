# Cahier des Charges — Secrets multi-services dans le pipeline deploy
> **Date :** 2026-09-10
> **Statut :** Validé
> **Auteur :** Frédéric

---

## 1. Contexte et Problématique

### Problème à résoudre
`SecretsProvisioner.provision()` (`linuxtools/deploy/secrets_provisioner.py`)
résout toutes les clés d'une `SecretsSpec` via un seul `CredentialManager`
injecté au constructeur — `SecretsSpec.service` (un champ unique pour toute
la spec) n'est en réalité jamais lu, c'est du code mort. `Deployer.for_target()`
ne construit qu'un seul `SecretsProvisioner` à partir d'un seul
`credential_manager: CredentialManager | None`. Ça bloque le déploiement réel
de `webapitools/pihole-schedule` : sa `SecretsSpec` mélange des clés
`PIHOLE_*_APP_PASSWORD` (service `pihole`) et `GOTIFY_PIHOLE_SCHEDULE_TOKEN`
(stocké délibérément sous service `gotify` dans KeePassXC). Découvert au
8e essai du chantier de déploiement (2026-09-10), une fois tous les bugs
précédents (SSH, cycle de dépendance, mkdir parent) corrigés.

### Solution envisagée
> ⚠️ HYPOTHÈSE À VALIDER — déduite de la discussion, pas littéralement du
> besoin : remplacer l'injection d'un `CredentialManager` unique dans
> `SecretsProvisioner`/`Deployer.for_target` par une **factory**
> (`Callable[[str], CredentialManager]`), et remplacer `SecretsSpec.service`
> (`str` unique) + `keys` (`tuple[str, ...]` plate) par des paires
> `(service, clé)` — chaque clé porte son propre service. `webapitools`
> pourrait passer directement `CredentialManager.from_dotenv` comme factory
> (signature déjà compatible : `service` est son seul paramètre sans
> défaut). Alternative écartée : garder `SecretsSpec.service` global et
> imposer un `CredentialManager` par outil déployable (contournement côté
> `webapitools` — stocker le token Gotify sous service `pihole`) — rejetée
> dans le besoin (« Ce que ce n'est PAS »), reviendrait sur une convention
> de nommage déjà établie ailleurs dans le code.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] `linuxtools/deploy/models.py` — `SecretsSpec` : remplacer `service` +
      `keys` par un champ portant le couple (service, clé) par entrée
- [ ] `linuxtools/deploy/secrets_provisioner.py` — `SecretsProvisioner` :
      constructeur prenant une factory `Callable[[str], CredentialManager]`
      au lieu d'un `CredentialManager` unique ; `provision()` résout chaque
      clé via le manager de **son** service
- [ ] `linuxtools/deploy/deployer.py` — `Deployer.for_target()` : paramètre
      `credential_manager` remplacé par une factory équivalente
- [ ] Tests unitaires existants de ces trois modules adaptés au nouveau
      contrat

### Exclu (Out of Scope)
- Consommation côté `webapitools` (`registry.py`, `deploy/pihole_schedule.py`,
  `cli.py::_cmd_deploy`) — évolution séparée, côté `webapitools`, une fois
  ce CDC livré et taggé (comme pour le cassage de cycle de dépendance
  précédent dans cette même session)
- Reprise du chantier de déploiement `pihole-schedule` lui-même — hors
  périmètre, suite immédiate une fois le correctif consommé côté
  `webapitools`
- Modification de la commande locale `pihole schedule apply`
  (`webapitools/cli.py:269-270`), déjà correcte

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Frédéric (assisté Claude Code) | Implémente la solution |
| Utilisateur    | `webapitools` (déploiement `pihole-schedule`), futurs outils déployables `linuxtools.deploy` | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | Une `SecretsSpec` dont les clés appartiennent à des services `CredentialManager` différents est provisionnée avec succès — chaque clé résolue sous son propre service. |
| F-02 | Must have       | `SecretsProvisioner`/`Deployer.for_target` reçoivent une factory de résolution (`Callable[[str], CredentialManager]`), pas un manager pré-résolu pour un seul service. |
| F-03 | Should have     | Le comportement d'échec reste inchangé : clé introuvable dans son service → `False` + message d'erreur explicite (service + clé), rien n'est écrit. |
| F-04 | Won't have      | Adapter `webapitools` au nouveau contrat — suite immédiate, hors périmètre de ce CDC. |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Sans objet (changement de contrat d'API, aucun chemin d'exécution coûteux modifié) |
| Disponibilité   | Usage homelab ponctuel — sans objet |
| Sécurité        | Aucune valeur de secret ne doit apparaître dans un message d'erreur ou un log (invariant déjà en place dans `SecretsProvisioner._log_error`, à préserver) |
| Maintenabilité  | `mypy --strict` à 0 erreur (gate bloquant, non négociable) ; couverture de tests existante maintenue |
| Portabilité     | Python 3.11+, Linux — inchangé par rapport à l'existant |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|------------------------------------------------------------|
| Langage       | Python 3.11+                                             |
| Environnement | Local (exécution de `linuxtools.deploy` toujours locale, pilote une cible via SSH) + CI Forgejo — pas d'exposition Internet |
| Dépendances   | Aucune nouvelle dépendance tierce — `credentials` reste une dépendance optionnelle de `linuxtools` (`extra`), inchangé |
| Infrastructure| Dépôt Forgejo `linuxtools`, CI bloquante (`test`, `lint`, `mypy --strict`), règle du parc « ouvrir la PR EST l'acte de merge » |
| Données       | Sans objet |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas d'exposition réseau
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Un test reproduit le cas `pihole-schedule` (2 clés `pihole`, 1 clé
      `gotify`) et vérifie que chaque clé est résolue via le bon manager
- [ ] Un test vérifie qu'un échec de résolution sur une clé n'entraîne
      aucun appel de résolution superflu et un message d'erreur qui nomme
      le service et la clé en cause (sans jamais exposer la valeur)
- [ ] Suite de tests `linuxtools` existante toujours verte
- [ ] `mypy --strict` — 0 erreur
- [ ] Nouveau tag Forgejo publié
- [ ] Documentation (CHANGELOG, hub `linuxtools – Vue d'ensemble`) à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | `SecretsSpec`, `SecretsProvisioner`, `Deployer.for_target` adaptés au contrat multi-services | |
| Tests                 | Suite existante adaptée + nouveaux cas multi-services | |
| Documentation         | `CHANGELOG.md`, hub `linuxtools – Vue d'ensemble` | |
| Tag Forgejo           | Nouvelle version publiée, consommable par `webapitools` dans une évolution séparée | |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01 | Forme exacte du champ multi-services dans `SecretsSpec`. | Frédéric | **Tranché 2026-09-10** — paires `tuple[tuple[str, str], ...]` (service, clé), diff minimal par rapport au tuple plat actuel, ordre de résolution préservé. |
| Q-02 | `DeployableTool.credential_service` (webapitools) devient-il inutile une fois chaque clé porteuse de son service ? | Frédéric | **Tranché 2026-09-10** — retiré. Chaque clé porte son propre service dans `SecretsSpec` ; garder `credential_service` en parallèle recréerait une ambiguïté (deux façons de désigner le service) et un champ mort potentiel comme l'actuel `SecretsSpec.service`. |
| Q-03 | Bump semver. | Frédéric | **Tranché 2026-09-10** — mineure. Cohérent avec le bump `2.0.1`→`2.1.0` du cassage de cycle (contrat non rétrocompatible, mais consommateur unique connu — `webapitools` — pas encore repointé). |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
