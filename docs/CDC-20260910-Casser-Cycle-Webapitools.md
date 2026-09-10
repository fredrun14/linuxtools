# Cahier des Charges — Casser le cycle de dépendance vers webapitools
> **Date :** 2026-09-10
> **Statut :** Brouillon
> **Auteur :** Frédéric

---

## 1. Contexte et Problématique

### Problème à résoudre
`linuxtools` déclare `webapitools` comme dépendance **de base**
(`[project.dependencies]`, pas un extra), alors que seuls 4 fichiers isolés
(`network/router/{__init__,dhcp,scanner,mac_filter}.py`,
`updates/checker.py`) en ont réellement besoin. N'importe quel consommateur
qui ne demande qu'un extra sans rapport (`linuxtools[credentials]`, le cas
de `webapitools` lui-même) hérite quand même de cette dépendance — cycle
insoluble par `pip` dès que `webapitools` s'installe depuis sa propre
source non taguée. Bloque aujourd'hui le déploiement réel de
`webapitools/pihole-schedule` sur un hôte distant (`ResolutionImpossible`).
Un ADR du 2026-09-05 (`ADR-20260905-uv-sources-consommateur-externe`) avait
déjà identifié ce cycle pour un symptôme différent et explicitement mis de
côté sa résolution complète comme « structurant, nécessiterait son propre
CDC ».

### Solution envisagée
> ⚠️ HYPOTHÈSE À VALIDER — déduite de la discussion, pas littéralement du
> besoin : déplacer `webapitools @ git+...` de `[project.dependencies]`
> vers un ou plusieurs **extras optionnels** dans `pyproject.toml` de
> `linuxtools`, pour qu'un extra sans rapport (`credentials`) ne l'entraîne
> plus. Alternative explicitement écartée dans la conversation : rapatrier
> `AsusRouterClient`/`ForgejoClient` dans `linuxtools` — reviendrait sur la
> décision actée le 2026-08-14 de garder `linuxtools` sans dépendance
> tierce lourde (cf. `CDC-20260814-0720-Client-Routeur-Asus.md`,
> webapitools).

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] `pyproject.toml` de `linuxtools` : sortir `webapitools` de
      `[project.dependencies]`, le rattacher à un/des extra(s) optionnel(s)
- [ ] Les modules `network/router/*.py` et `updates/checker.py` restent
      fonctionnellement inchangés une fois l'extra installé
- [ ] CI Forgejo de `linuxtools` : les jobs qui testent ces modules
      installent explicitement l'extra concerné
- [ ] Publication d'un nouveau tag `linuxtools` une fois le correctif validé

### Exclu (Out of Scope)
- Rapatriement d'`AsusRouterClient`/`ForgejoClient` dans `linuxtools`
  (option envisagée et écartée)
- Re-pointer `webapitools/pyproject.toml` vers le nouveau tag `linuxtools`
  — évolution séparée, côté `webapitools`, une fois ce CDC livré et taggé
- Toute modification du comportement observable d'`AsusRouterClient`,
  `ForgejoClient`, ou des adaptateurs `network/router`/`updates/checker`

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Frédéric (assisté Claude Code) | Implémente la solution |
| Utilisateur    | Frédéric — projets homelab consommant `linuxtools` (`webapitools`, `scanNetHome`, futurs) | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `pip install "linuxtools[credentials] @ git+...@<tag>"` (ou tout autre extra sans rapport avec le réseau/les mises à jour), lancé sans dépôt frère ni `webapitools` déjà présent, n'entraîne plus aucune résolution de `webapitools`. |
| F-02 | Must have       | `network/router/*.py` et `updates/checker.py` restent utilisables à l'identique dès lors que l'extra `network` (Q-01) est installé — aucune perte de fonctionnalité pour qui en a besoin. Sans l'extra, échec net à l'import (Q-02), pas de dégradation gracieuse. |
| F-03 | Should have     | La CI Forgejo de `linuxtools` continue de tester ces deux modules (installe explicitement l'extra correspondant dans les jobs concernés). |
| F-04 | Won't have      | Re-pointer `webapitools/pyproject.toml` vers le nouveau tag `linuxtools` — suite immédiate mais hors périmètre de ce CDC. |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Sans objet (changement de métadonnées de paquet, aucun chemin d'exécution modifié) |
| Disponibilité   | Usage homelab ponctuel — sans objet |
| Sécurité        | Aucun changement de surface d'attaque (bibliothèque Python, pas de service réseau exposé) |
| Maintenabilité  | `mypy --strict` à 0 erreur (gate bloquant, non négociable — cf. `~/PycharmProjects/CLAUDE.md`) ; couverture de tests existante maintenue |
| Portabilité     | Python 3.11+, Linux — inchangé par rapport à l'existant |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|------------------------------------------------------------|
| Langage       | Python 3.11+                                             |
| Environnement | Local (dev croisé `linuxtools`/`webapitools` via `[tool.uv.sources]`, inchangé) + CI Forgejo — pas d'exposition Internet |
| Dépendances   | Aucune nouvelle dépendance tierce ajoutée — l'objectif est au contraire de retirer une dépendance de base devenue conditionnelle. `platformdirs` (seule autre dépendance de base actuelle) non concerné. |
| Infrastructure| Dépôt Forgejo `linuxtools`, CI bloquante (`test`, `lint`, `mypy --strict` — confirmer les jobs exacts avant implémentation), règle du parc « ouvrir la PR EST l'acte de merge » |
| Données       | Sans objet |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas d'exposition réseau
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] `pip install "linuxtools[credentials] @ git+https://git.ricfasohel.fr/fred/linuxtools.git@<nouveau-tag>"`, depuis une machine sans `webapitools` ni dépôt frère, s'installe sans tenter de résoudre `webapitools`
- [ ] L'extra dédié (nom à trancher, cf. Q-01) installe `webapitools` et rend `network/router/*.py`/`updates/checker.py` pleinement fonctionnels
- [ ] Suite de tests `linuxtools` existante toujours verte
- [ ] `mypy --strict` — 0 erreur
- [ ] Nouveau tag Forgejo publié
- [ ] Documentation (CHANGELOG, hub `linuxtools – Vue d'ensemble`) à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | `pyproject.toml` modifié — `webapitools` déplacé vers l'extra `network` ; aucune garde d'import ajoutée (Q-02 : échec net assumé) | |
| Tests                 | Suite existante adaptée si la garde d'import change un comportement observable | |
| Documentation         | `CHANGELOG.md`, hub `linuxtools – Vue d'ensemble` | |
| Tag Forgejo           | Nouvelle version publiée, consommable par `webapitools` dans une évolution séparée | |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01 | Nom du/des extra(s). | Frédéric | **Tranché 2026-09-10** — extra unique `network`, couvre `router` + `updates/checker`. |
| Q-02 | Comportement si l'extra n'est pas installé. | Frédéric | **Tranché 2026-09-10** — échec net à l'import (`ImportError` non gardée, pas de dégradation gracieuse) : sans `webapitools`, ces modules ne peuvent de toute façon rien faire, contrairement à `credentials` où `keyring`/`python-dotenv` sont réellement optionnels à l'usage. |
| Q-03 | Bump semver. | Frédéric | **Tranché 2026-09-10** — mineure. Nouveau comportement opt-in, aucun consommateur connu ne comptait implicitement sur la fuite de dépendance (`webapitools`/`scanNetHome` installent déjà `linuxtools` explicitement). |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
