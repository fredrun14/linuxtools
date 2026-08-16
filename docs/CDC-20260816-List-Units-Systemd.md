# Cahier des Charges — `list_units()` générique dans `systemd`
> **Date :** 2026-08-16
> **Statut :** Brouillon
> **Auteur :** Fred

---

## 1. Contexte et Problématique

### Problème à résoudre
`linuxtools.systemd` sait lister les timers (`list_timers()`, via
`_TimerOperationsMixin`, `systemctl list-timers --output=json` avec
fallback texte si JSON non supporté) mais n'a aucun équivalent
générique pour lister les unités systemd quel que soit leur type
(services, sockets, mounts, etc.). L'API du module est asymétrique.
Confirmé avec l'utilisateur : ce n'est pas la réponse à un besoin
consommateur identifié, mais une complétude d'API relevée en revue le
2026-07-23 (cf. `docs/BESOIN-20260816-0823-List-Units-Systemd.md`).

### Solution envisagée
Ajouter `list_units()` sur `SystemdExecutor` (et donc hérité par
`UserSystemdExecutor`), plutôt que sur `_BaseUnitManagerMixin`/
`UnitManager` : le listage n'est lié à aucun type d'unité particulier,
alors que les managers (`UnitManager`, `TimerUnitManager`, …) sont
typés par nature. C'est la piste déjà retenue en revue de code (2026-
07-23, note vault `Module systemd – Utilisation`), pas une hypothèse
nouvelle de ce CDC — cf. section 10 pour la confirmer avant plan-todo.
Réutilise `systemctl list-units --output=json` avec le même schéma de
dégradation que `list_timers()` (fallback texte si JSON indisponible).

> ⚠️ HYPOTHÈSE À VALIDER — l'extraction du parsing de secours (texte)
> aujourd'hui privé à `_TimerOperationsMixin` (`_list_timers_text_fallback`)
> vers un point partagé consommé par `list_timers()` **et** `list_units()`
> est une piste, pas une obligation : le CDC n'impose pas de refactor de
> `list_timers()` existant, seulement l'absence de duplication de logique
> neuve. Le *comment* exact (extraction vs réimplémentation ciblée) relève
> du plan-todo.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] `list_units()` générique, disponible côté système (`SystemdExecutor`)
      **et** utilisateur (`UserSystemdExecutor`, par héritage).
- [ ] Retour structuré cohérent avec `list_timers()` (liste de
      dictionnaires), avec au minimum : nom d'unité, type, état actif/
      inactif, description.
- [ ] Fallback texte si `systemctl list-units --output=json` n'est pas
      supporté par la version de systemd installée (même robustesse
      que `list_timers()`).
- [ ] Fonctionne local **et** via un `CommandExecutor` distant (SSH) —
      hérité gratuitement de l'agnosticisme déjà en place sur
      `SystemdExecutor`, pas une fonctionnalité neuve à concevoir.

### Exclu (Out of Scope)
- Filtrage par type d'unité (`--type=service`) ou système de requête
  avancé — périmètre minimal, symétrique à `list_timers()`.
- Ajout de nouveaux types d'unités gérés (`.socket`/`.path` —
  `SocketConfig`/`SocketUnitManager`) : item de backlog séparé,
  `list_units()` liste ce que systemd rapporte, indépendamment de ce
  que `linuxtools.systemd` sait *créer*.
- Toute CLI ou sous-commande consommant `list_units()` — reste une
  méthode d'API Python, comme `list_timers()` aujourd'hui.

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Fred         | Valide les objectifs         |
| Développeur    | Claude Code (agent `assistant-codage`) | Implémente la solution |
| Utilisateur    | Fred (et projets consommateurs de `linuxtools.systemd`, usage futur) | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `list_units()` sur `SystemdExecutor` — liste les unités système via `systemctl list-units --output=json` |
| F-02 | Must have       | `list_units()` hérité et fonctionnel sur `UserSystemdExecutor` sans réimplémentation |
| F-03 | Must have       | Fallback texte si `--output=json` non supporté, sans exception levée pour ce seul motif |
| F-04 | Should have     | Structure de retour documentée et testée (nom, type, état, description au minimum) |
| F-05 | Won't have      | Filtrage par type/état, pagination, ou toute option au-delà du listage brut |
| F-06 | Won't have      | Sous-commande CLI ou nouveaux types d'unités gérés — hors périmètre |

---

## 5. Objectifs Non-Fonctionnels

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Pas de contrainte forte — appel ponctuel, une seule commande `systemctl` |
| Disponibilité   | Sans objet (usage local/SSH ponctuel, pas de service exposé) |
| Sécurité        | Lecture seule (`list-units` ne modifie aucun état) ; aucune surface d'attaque nouvelle — réutilise l'exécuteur déjà audité de `systemd` |
| Maintenabilité  | Couverture tests ≥ 80 % sur le code neuf ; `mypy --strict` = 0 erreur (gate bloquant du dépôt) |
| Portabilité     | Linux avec systemd ; dégradation propre sur les versions de systemd sans support JSON pour `list-units` |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|----------------------------------------------------------|
| Langage       | Python 3.11+ |
| Environnement | Local ou distant (SSH) — hérité de l'agnosticisme existant de `SystemdExecutor`, aucun mode nouveau à couvrir explicitement |
| Dépendances   | `systemctl` présent sur l'hôte cible (déjà une contrainte de tout le module `systemd`) |
| Infrastructure | S'intègre dans `src/linuxtools/systemd/executor.py` |
| Données       | Aucune donnée sensible — sortie de `systemctl list-units`, informations publiques sur l'hôte |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas de nouvelle exposition réseau (la
      capacité SSH existante de `SystemdExecutor` n'est pas modifiée
      ni étendue par cette fonctionnalité)
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> Lecture seule, aucune donnée sensible, aucune nouvelle surface —
> les skills sécurité réseau (`python-owasp-security`,
> `python-sast-bandit-security`, `python-security-monitoring`) ne
> s'activent pas pour ce lot.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] `SystemdExecutor.list_units()` retourne une liste structurée
      des unités, testée sur un cas nominal (JSON disponible)
- [ ] Fallback texte testé explicitement (JSON non supporté simulé)
- [ ] `UserSystemdExecutor` hérite `list_units()` sans code dupliqué,
      testé
- [ ] Aucune régression sur `list_timers()` existant
- [ ] Tests unitaires passent avec couverture ≥ 80 % sur le code neuf
- [ ] `mypy --strict` = 0 erreur (gate bloquant du dépôt)
- [ ] Documentation à jour (docstrings PEP 257, note vault `systemd`)

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | `list_units()` dans `src/linuxtools/systemd/executor.py` |             |
| Tests                 | `tests/test_systemd_executor.py` (ou fichier dédié), couverture ≥ 80 % |             |
| Documentation         | Docstrings PEP 257 + note vault `systemd` (hub + Utilisation) |             |
| CHANGELOG             | Entrée versionnée (MINOR — nouvelle capacité publique) |             |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01| Confirmer l'emplacement `SystemdExecutor` (piste déjà retenue en revue 2026-07-23) plutôt que `_BaseUnitManagerMixin` — ou trancher explicitement au plan-todo si un doute subsiste | Fred / plan-todo | Ouvert |
| Q-02| Structure exacte du dictionnaire retourné (clés au-delà de nom/type/état/description) — relève du *comment*, à trancher en plan-todo | Fred / plan-todo | Ouvert |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
