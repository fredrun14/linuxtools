# Cahier des Charges — Validation MAC robuste et partagée
> **Date :** 2026-10-11
> **Statut :** Brouillon
> **Auteur :** Frédéric

---

## 1. Contexte et Problématique

### Problème à résoudre
`webapitools` possède sa propre fonction `normalize_mac` (`apps/_shared.py`)
qui duplique la règle de validation MAC déjà portée par
`linuxtools.network.validators.validate_mac`. Deux implémentations divergentes
de la même règle coexistent. De plus, la validation `linuxtools` est fragile :
ses regex se terminent par `$`, qui accepte un saut de ligne final — une MAC
(ou un CIDR, ou un hostname) suivie d'un `\n` passe la validation. Une valeur
lue depuis un TOML pourrait donc être acceptée avec un caractère parasite.

### Solution envisagée
Faire de `linuxtools.network.validators` la source unique de la règle MAC :
corriger le défaut `\n` (ancrage strict), ajouter à `validate_mac` un paramètre
de casse de sortie (défaut inchangé), puis réécrire `webapitools.normalize_mac`
en simple adaptateur qui délègue à `linuxtools`. Corriger au passage le même
défaut `\n` sur `validate_cidr` et `validate_hostname`.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Ancrage strict des regex de `validate_mac`, `validate_cidr`,
      `validate_hostname` (rejet d'un `\n` ou autre caractère final parasite).
- [ ] Paramètre `case="lower"|"upper"` sur `validate_mac` (défaut `"lower"`).
- [ ] Réécriture de `webapitools.normalize_mac` en adaptateur appelant
      `linuxtools.validate_mac(raw, case="upper")`, en conservant le garde
      `isinstance(raw, str)` → `ValueError` (entrée non-`str` issue d'un TOML).
- [ ] Suppression de la constante `_MAC_RE` devenue inutile côté `webapitools`.
- [ ] Publication d'une version patch de `linuxtools` et mise à jour du pin
      dans `webapitools/pyproject.toml`.

### Exclu (Out of Scope)
- Ajout d'un `validate_ipv6` (reporté à un besoin dédié).
- Enrichissement de `validate_hostname` au-delà du fix `\n` (RFC complète, FQDN
      multi-labels).
- Changement du comportement par défaut de `validate_mac` : `network/models.py`
      et tout appelant existant continuent de recevoir des minuscules.
- Création d'un nouveau module de validation (on reste dans
      `network/validators.py`).

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Frédéric (+ assistant-codage) | Implémente la solution |
| Utilisateur    | Frédéric     | Utilise le livrable final    |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `validate_mac` rejette une MAC suivie d'un `\n` (ou tout caractère hors format). |
| F-02 | Must have       | `validate_mac(mac, case="upper")` renvoie la MAC en majuscules ; défaut `"lower"` inchangé. |
| F-03 | Must have       | `validate_cidr` et `validate_hostname` rejettent un `\n` final. |
| F-04 | Must have       | `webapitools.normalize_mac` délègue à `linuxtools.validate_mac` ; plus aucune regex MAC dans `webapitools`. |
| F-05 | Must have       | `normalize_mac` conserve son contrat : entrée non-`str` → `ValueError` ; sortie en MAJUSCULES. |
| F-06 | Should have     | `case=` n'accepte que `"lower"`/`"upper"` ; une autre valeur lève `ValueError`. |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Validation d'une chaîne, négligeable (< 1 ms). |
| Disponibilité   | Usage ponctuel, bibliothèque.                 |
| Sécurité        | Validation d'entrée renforcée (anti-injection d'un caractère parasite dans une valeur de config). |
| Maintenabilité  | `mypy --strict` à zéro ; couverture des branches nouvelles/modifiées ≥ 80 %. |
| Portabilité     | Python 3.11+, aucune dépendance nouvelle (stdlib `re` / `ipaddress`). |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|----------------------------------------------------------|
| Langage       | Python 3.11+                                              |
| Environnement | Local / bibliothèque partagée (`linuxtools`), consommée par `webapitools`. |
| Dépendances   | Aucune nouvelle ; stdlib uniquement. Pin `linuxtools` à bump dans `webapitools`. |
| Infrastructure| Forgejo Actions ; gate `mypy` bloquant des deux côtés.   |
| Données       | Chaînes de configuration (MAC/CIDR/hostname) issues de TOML. |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas d'exposition réseau
- [ ] **Réseau interne**
- [ ] **Exposé Internet**

> Bibliothèque de validation locale. Pas de serveur ni d'I/O réseau ajoutée.

### Exigences de sécurité

| Critère                    | Exigence                                                        |
|----------------------------|-----------------------------------------------------------------|
| Données sensibles          | Aucune (adresses MAC/IP de LAN domestique, non secrètes).       |
| Authentification           | N/A — fonction pure de validation.                              |
| Autorisation               | N/A.                                                            |
| Entrées non fiables        | Chaînes lues depuis des fichiers TOML de config (type non garanti). |
| Surfaces dangereuses       | Aucune (pas de `subprocess`, pas de désérialisation). Le durcissement **réduit** la surface : un `\n` ne franchit plus la validation. |
| Secrets                    | Aucun.                                                          |
| Traçabilité                | N/A.                                                            |

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] `validate_mac("aa:bb:cc:dd:ee:ff\n")` lève `ValueError` (test de non-régression).
- [ ] `validate_mac("aa:bb:cc:dd:ee:ff", case="upper") == "AA:BB:CC:DD:EE:FF"` ;
      sans `case`, retour minuscules inchangé.
- [ ] `validate_cidr(...\n)` et `validate_hostname(...\n)` lèvent `ValueError`.
- [ ] `webapitools.normalize_mac` ne contient plus de regex ; tous ses tests
      existants (`tests/test_apps_shared.py`) passent sans modification de leur intention.
- [ ] `mypy --strict` à zéro des deux côtés ; `ruff` propre.
- [ ] Tests unitaires passent, couverture des lignes touchées ≥ 80 %.
- [ ] Docstrings (`validate_mac`, `normalize_mac`) à jour (casse, ancrage strict).

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|-------------------------------------|-------------|
| Code `linuxtools`     | `network/validators.py` durci + `case=` ; version patch. | — |
| Code `webapitools`    | `apps/_shared.py` : `normalize_mac` en adaptateur, `_MAC_RE` retirée ; pin bumpé. | — |
| Tests                 | Non-régression `\n` (linuxtools) ; tests `normalize_mac` conservés (webapitools). | — |
| Documentation         | Docstrings à jour ; CHANGELOG `linuxtools` si présent. | — |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|---------------------------------------|-------------|----------|
| Q-01| Numéro de version patch `linuxtools` (v2.5.1 présumé) et faut-il un CHANGELOG ? | Frédéric | Ouvert |
| Q-02| Le durcissement `\n` de `validate_cidr`/`validate_hostname` peut-il casser un appelant qui s'appuierait (involontairement) sur l'ancien laxisme ? À vérifier à l'implémentation. | assistant-codage | Ouvert |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
