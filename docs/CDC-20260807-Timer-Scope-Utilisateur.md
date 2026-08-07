# Cahier des Charges — Timer Scope Utilisateur
> **Date :** 2026-08-07
> **Statut :** Validé
> **Auteur :** Frederic

---

## 1. Contexte et Problématique

### Problème à résoudre

`TimerDeployer` (module `linuxtools.deploy`, `timer_deployer.py`) installe le
service+timer systemd exclusivement en mode **système**
(`/etc/systemd/system/`, via `SystemdExecutor` / `LinuxServiceUnitManager` /
`LinuxTimerUnitManager`), ce qui nécessite root. Un outil personnel
non-privilégié (ex. `backup-py-manager`, qui sauvegarde le home de son
propre utilisateur) n'a aucune raison de tourner en root — et le
déploiement échoue purement et simplement sur un poste desktop où
l'utilisateur n'a pas de session root interactive. Constaté en conditions
réelles le 2026-08-07 : `Permission refusée pour écrire
/etc/systemd/system/backup-py-manager-home.service. Exécution en tant que
root requise.`

### Solution envisagée

`linuxtools.deploy` doit pouvoir installer un `TimerDeploySpec` soit en
mode **système** (comportement actuel, inchangé — nécessaire pour les
serveurs : timers qui doivent survivre à une déconnexion utilisateur,
cibles SSH administrées en root), soit en mode **utilisateur**
(`systemctl --user`, `~/.config/systemd/user/`, sans sudo ni root). Les
deux modes coexistent, sélectionnables par l'appelant. Les briques bas
niveau existent déjà côté `linuxtools.systemd` (`UserSystemdExecutor`,
`LinuxUserServiceUnitManager`, `LinuxUserTimerUnitManager`) mais ne sont
jamais mobilisées par le module `deploy`.

> ⚠️ HYPOTHÈSE À VALIDER : le besoin ne précise pas le mécanisme exact de
> sélection du scope. Proposition : un champ `scope: Literal["system",
> "user"] = "system"` sur `TimerDeploySpec`, défaut `"system"` pour
> préserver le comportement actuel de tous les consommateurs existants
> sans rien casser. À trancher en Q-01.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Nouveau champ de scope sur `TimerDeploySpec` (nom exact à trancher, Q-01)
- [ ] `TimerDeployer.deploy()` construit les collaborateurs corrects
      (`SystemdExecutor`/`LinuxServiceUnitManager`/`LinuxTimerUnitManager`
      en mode système, `UserSystemdExecutor`/`LinuxUserServiceUnitManager`/
      `LinuxUserTimerUnitManager` en mode utilisateur) selon le scope demandé
- [ ] `SystemdServiceTimerInstaller` (ou son point d'appel dans
      `TimerDeployer`) accepte les deux familles de managers — décision de
      conception à trancher (Q-02, cf. incompatibilité de typage relevée)
- [ ] Tests couvrant les deux scopes (système existant non régressé, nouveau
      scope utilisateur)
- [ ] Mise à jour de la doc vault `linuxtools – Module deploy –
      Fonctionnement/Utilisation` et `linuxtools – Module systemd` si impacté

### Exclu (Out of Scope)
- L'option CLI côté `backup-py-manager deploy` pour choisir le scope —
  évolution séparée, dans `backup-py-manager`, une fois ce besoin livré
  côté `linuxtools`.
- Le support `loginctl enable-linger` (timer utilisateur qui doit survivre
  à une déconnexion sur cible distante) — sauf si Q-03 en décide autrement.
- Toute modification de `ConfigDeployer`/`SecretsProvisioner` — seuls
  `TimerDeployer`/`TimerDeploySpec` sont concernés.
- Le mode « clé USB » (`usb-export`, chantier séparé déjà identifié dans la
  doc vault comme idée non menée).

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | assistant-codage | Implémente la solution   |
| Utilisateur    | Frederic (via `backup-py-manager` et futurs consommateurs de `linuxtools.deploy`) | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `TimerDeploySpec` porte un champ de scope (système/utilisateur), défaut système — comportement actuel inchangé par défaut. |
| F-02 | Must have       | En scope utilisateur, `TimerDeployer.deploy()` installe et active le service+timer via `systemctl --user`, sans aucune élévation de privilèges (pas de `sudo`, pas de vérification root). |
| F-03 | Must have       | En scope système, `TimerDeployer.deploy()` conserve exactement le comportement actuel — aucune régression sur les consommateurs existants (dont `backup-py-manager` en mode SSH root). |
| F-04 | Must have       | Cible SSH distante : le scope utilisateur fonctionne aussi via `SshCommandExecutor` (mêmes garanties d'agnosticisme local/distant que le reste du module). |
| F-05 | Should have     | Message d'erreur explicite si le scope utilisateur est demandé mais que la cible ne supporte pas `systemctl --user` (ex. session utilisateur sans bus D-Bus actif). |
| F-06 | Won't have      | `loginctl enable-linger` automatique — hors périmètre (cf. Q-03). |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Aucun impact — même volumétrie de commandes qu'aujourd'hui. |
| Disponibilité   | Usage ponctuel (déploiement), pas de service continu. |
| Sécurité        | Scope utilisateur = aucune élévation de privilèges requise ; scope système = comportement root actuel inchangé, pas de nouveau `sudo` implicite. |
| Maintenabilité  | `mypy --strict` = 0 erreur (gate bloquant existant, non négociable). Couverture ≥ 90 % sur le code nouveau/modifié (cohérent avec le seuil `linuxtools`). |
| Portabilité     | Linux avec systemd (utilisateur **et** système), Python 3.11+ — inchangé. |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|-----------------------------------------------------------|
| Langage       | Python 3.11+, stdlib uniquement pour `linuxtools` (cf. CLAUDE.md du repo) |
| Environnement | Local (poste Fedora) et réseau interne (SSH homelab) — cible existante inchangée |
| Dépendances   | Aucune nouvelle dépendance — réutilise `UserSystemdExecutor`/`LinuxUserServiceUnitManager`/`LinuxUserTimerUnitManager` déjà présents dans `linuxtools.systemd` |
| Infrastructure| Forgejo Actions (CI), pas de changement d'infra |
| Données       | Aucune donnée persistante nouvelle — fichiers unit systemd, comme aujourd'hui |

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement** — Pas d'exposition réseau
- [x] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> ⚠️ HYPOTHÈSE À VALIDER : coché « Réseau interne » car `TimerDeployer`
> reste utilisable via `DeployTarget(host=...)` (SSH homelab), comme le
> reste du module `deploy` — même choix que le CDC
> `Deploy-Config-Secrets-Timer` original de `backup-py-manager`. Si ce
> chantier reste strictement local (F-04 optionnelle), ce cochage peut
> être révisé.

> ⚠️ Skills sécurité actifs : `python-owasp-security`,
> `python-sast-bandit-security`, `python-security-monitoring`.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Un `TimerDeploySpec` en scope système déployé en local ou SSH produit
      exactement le même résultat qu'avant ce chantier (non-régression).
- [ ] Un `TimerDeploySpec` en scope utilisateur déployé en local installe et
      active un timer `systemctl --user` sans élévation de privilèges,
      vérifiable par `systemctl --user status <unit>.timer`.
- [ ] `mypy --strict src/` → 0 erreur (gate bloquant).
- [ ] Tests unitaires passent, couverture ≥ 90 % sur le code
      nouveau/modifié, aucune régression sur la suite existante
      (`tests/test_deploy_*.py`, `tests/test_systemd_*.py`).
- [ ] Aucun warning Bandit sévérité MEDIUM ou supérieure.
- [ ] `ruff check` sans nouvelle alerte.
- [ ] Documentation vault (`linuxtools – Module deploy –
      Fonctionnement/Utilisation`) à jour sur le nouveau champ de scope.
- [ ] `CHANGELOG.md` de `linuxtools` mis à jour, nouveau tag de version
      envisagé pour que `backup-py-manager` (et futurs consommateurs)
      puissent l'épingler.

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | `models.py` (champ scope), `timer_deployer.py` (branchement), éventuel ajustement `service_timer_installer.py`/`base.py` selon Q-02 | |
| Tests                 | `tests/test_deploy_timer_deployer.py` (ou existant étendu) — scope système + utilisateur, ≥ 90 % | |
| Documentation         | `README.md`, docstrings PEP 257 français, notes vault `linuxtools – Module deploy` | |
| CHANGELOG             | Entrée `linuxtools/CHANGELOG.md` + tag de version | |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01| Nom et forme exacte du champ de scope sur `TimerDeploySpec`. | Frederic | **Résolu** — `scope: Literal["system", "user"] = "system"`. Défaut système = aucune régression pour les consommateurs existants. |
| Q-02| Comment `TimerDeployer`/l'installer doivent-ils accepter les deux familles de managers (système/utilisateur, classes sœurs sans héritage commun) sans casser `mypy --strict` ? | Frederic | **Résolu** — deux chemins de code distincts dans `TimerDeployer.deploy()` : selon `spec.scope`, construction du couple concret (executor + service_manager + timer_manager + installer) système ou utilisateur. Aucun changement dans `service_timer_installer.py` ni dans les ABCs partagées par d'autres consommateurs de `linuxtools.systemd`. |
| Q-03| `loginctl enable-linger` (survie du timer `--user` après déconnexion) : hors périmètre ou avertissement minimal ? | Frederic | **Résolu** — hors périmètre. `linuxtools.deploy` n'automatise ni ne loggue rien à ce sujet ; à documenter côté appelant (ex. `backup-py-manager`) si besoin. |
| Q-04| Le scope utilisateur doit-il fonctionner aussi en cible SSH distante ? | Frederic | **Résolu** — oui, dès cette itération. Cohérent avec l'agnosticisme local/distant du module : `SshCommandExecutor` gère déjà `systemctl --user` via la même mécanique `_wrap()`, aucun surcoût de conception à l'inclure maintenant. |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
