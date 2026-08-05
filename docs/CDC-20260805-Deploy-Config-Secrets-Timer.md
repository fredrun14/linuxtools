# Cahier des Charges — Deploy Config Secrets Timer
> **Date :** 2026-08-05
> **Statut :** Brouillon
> **Auteur :** Frederic

---

## 1. Contexte et Problématique

### Problème à résoudre
`Deployer` (module `deploy` de `linuxtools`) livre aujourd'hui le code d'un
outil (transport → venv → verify → rollback) sur une cible locale ou SSH,
mais s'arrête là. Pour qu'un service planifié tourne réellement, il faut
ensuite déposer sa config TOML, ses secrets et installer/activer son
service+timer systemd — une suite d'étapes manuelles, refaites à chaque
projet consommateur (pattern `borg-passphrase`/`notifications.env` sur
`backup-tank-data`, sur le point d'être reproduit à la main pour
`webapitools`/pihole-schedule).

### Solution envisagée
Étendre `Deployer` avec des phases optionnelles supplémentaires — sur le
modèle des collaborateurs déjà injectés (`Transport`, `VenvInstaller`,
`InstallVerifier`) — pour déposer la config TOML, provisionner les secrets
(injectés dans l'unité systemd via `Environment=`/`EnvironmentFile=`,
jamais via le rsync du `source_dir`) et installer/activer le couple
service+timer systemd, en réutilisant les modules existants `config`,
`credentials` et `systemd` sur la cible déjà résolue (locale ou SSH).

> ⚠️ HYPOTHÈSE À VALIDER — noms de classes déduits par cohérence avec le
> style du module (`ConfigDeployer`, `SecretsProvisioner`, `TimerDeployer`),
> non imposés par le besoin ; à confirmer/ajuster au `python-plan-todo`.

**Correction de périmètre (analyse technique du 2026-08-05)** : la lecture
de `systemd/executor.py`, `systemd/base.py` et `config/manager.py` a
montré que `SystemdServiceTimerInstaller` (subprocess local en dur,
écriture de fichier via `os.open()` local) et `ConfigurationManager`
(écriture via `path.write_text()` locale) ne peuvent **pas** être
réutilisés tels quels sur une cible SSH — ils n'utilisent jamais
l'abstraction `CommandExecutor` que `deploy` utilise pour rester
agnostique local/SSH. Plutôt que de contourner cette limite par du code
dupliqué dans `deploy` (rsync de fichier isolé, etc.), la décision prise
est de **corriger l'abstraction à la source** :
- `CommandExecutor.run()` gagne un paramètre optionnel
  `input: str | None = None` (rétrocompatible), propagé jusqu'à
  `subprocess.Popen(...).communicate(input=...)` dans
  `LinuxCommandExecutor`. `SshCommandExecutor` n'a rien à réimplémenter :
  il transmet déjà toute commande à son `LinuxCommandExecutor` interne
  (composition, pas héritage — les deux sont des implémentations
  indépendantes de `CommandExecutor`), donc `input` traverse
  gratuitement le tunnel SSH.
- `SystemdExecutor.__init__` reçoit un `CommandExecutor` **optionnel**
  (défaut : un `LinuxCommandExecutor()` local — comportement identique à
  aujourd'hui, ne casse pas l'usage documenté `SystemdExecutor(logger)`
  du `README`). `_run_systemctl` appelle `self._executor.run(["systemctl",
  *args])` au lieu de `subprocess.run` en dur.
- `UnitManager._write_unit_file`/`_remove_unit_file` **gardent** l'écriture
  locale TOCTOU-safe (`os.open(O_NOFOLLOW)`, pattern clé cité dans
  `CLAUDE.md`) pour la cible locale, et utilisent le nouveau chemin
  `executor.run([...], input=content)` uniquement pour la cible distante
  (décision (a) — pas de régression de sécurité locale, la conscience
  locale/distant reste confinée à cet unique endroit au lieu d'être
  dupliquée dans les nouveaux collaborateurs de `deploy`).
- `ConfigurationManager` gagne un chemin d'écriture basé sur un
  `CommandExecutor` injecté (même mécanisme `input=`), en plus de
  l'écriture locale directe existante — sans changer le comportement des
  appelants qui n'injectent pas d'executor.

Cette correction élargit le périmètre du lot : il touche désormais
`commands`, `systemd` et `config`, pas seulement `deploy`. Tous les
changements sont rétrocompatibles (paramètres optionnels à valeur par
défaut préservant le comportement actuel).

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Nouvelle phase optionnelle : dépôt d'un fichier TOML de config vers
      un chemin cible (local ou SSH), via `ConfigurationManager`, sans
      passer par le rsync de `source_dir`.
- [ ] Nouvelle phase optionnelle : provisioning de secrets (lus via
      `CredentialManager`) vers la cible, sous une forme injectable dans
      l'unité systemd (`EnvironmentFile=`, fichier 0600) et/ou
      `Environment=`.
- [ ] Nouvelle phase optionnelle : installation/activation d'un couple
      service+timer systemd sur la cible (locale ou SSH), en réutilisant
      `SystemdServiceTimerInstaller` (désormais capable de cibler une
      cible SSH grâce au `CommandExecutor` injecté).
- [ ] Chaque phase reste no-op si sa configuration n'est pas fournie —
      aucun changement de comportement pour les appelants existants.
- [ ] `DeployReport`/`DeployPhase` reflètent les nouvelles phases.
- [ ] `CommandExecutor.run()` (`linuxtools.commands`) gagne un paramètre
      optionnel `input: str | None = None`, implémenté dans
      `LinuxCommandExecutor` et propagé sans changement dans
      `SshCommandExecutor`.
- [ ] `SystemdExecutor`/`UserSystemdExecutor` (`linuxtools.systemd`)
      reçoivent un `CommandExecutor` optionnel injecté (défaut : local,
      comportement inchangé) au lieu d'appeler `subprocess.run` en dur.
- [ ] `UnitManager._write_unit_file`/`_remove_unit_file` : écriture locale
      TOCTOU-safe préservée (`os.open(O_NOFOLLOW)`) ; écriture distante via
      `executor.run([...], input=content)`.
- [ ] `ConfigurationManager` (`linuxtools.config`) gagne un chemin
      d'écriture basé sur un `CommandExecutor` injecté, en plus de
      l'écriture locale directe existante.

### Exclu (Out of Scope)
- Génération du contenu métier du TOML applicatif (fourni par l'appelant).
- Décisions d'infra (topologie, choix du nœud/hôte cible) — reste le rôle
  de `nas-plan-chantier` en amont.
- Rotation ou génération des secrets eux-mêmes (reste `CredentialManager`
  / keyring en amont) — ce lot ne couvre que leur provisioning vers la
  cible.

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|-------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | Frederic (via `assistant-codage`) | Implémente la solution |
| Utilisateur    | Projets consommateurs (`backup-py-manager`, `webapitools`, `fedora_post_install`) | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `Deployer` accepte une configuration optionnelle décrivant un fichier TOML source à déployer vers un chemin cible (local ou SSH). |
| F-02 | Must have       | `Deployer` accepte une configuration optionnelle décrivant des secrets à provisionner vers la cible sous forme injectable dans l'unité systemd (fichier `EnvironmentFile=` en 0600 et/ou `Environment=`). |
| F-03 | Must have       | `Deployer` accepte une configuration optionnelle décrivant un service+timer systemd et l'installe/active sur la cible en réutilisant `SystemdServiceTimerInstaller`. |
| F-04 | Must have       | Chaque nouvelle phase (config/secrets/timer) est no-op si sa configuration n'est pas fournie — rétrocompatibilité totale avec les appels `deploy()` existants. |
| F-05 | Should have     | `DeployReport.format_summary()` reste lisible et reflète les nouvelles phases (messages, éventuels `CheckResult`). |
| F-06 | Should have     | Le mode dry-run (`DryRunContext`) couvre aussi ces nouvelles phases sans effet de bord. |
| F-07 | Won't have (v1) | Rotation ou génération des secrets — hors périmètre (cf. § 2). |
| F-08 | Must have       | `CommandExecutor.run()` accepte un paramètre optionnel `input: str | None = None` pour envoyer du contenu au processus lancé (fichier via `input=`, sans fichier temporaire ni argument CLI), implémenté dans `LinuxCommandExecutor` et transmis tel quel par `SshCommandExecutor`. |
| F-09 | Must have       | `SystemdExecutor`/`UserSystemdExecutor` acceptent un `CommandExecutor` optionnel injecté (défaut : local, comportement identique à l'existant) et l'utilisent pour `_run_systemctl` au lieu de `subprocess.run` codé en dur. |
| F-10 | Must have       | `UnitManager` écrit les fichiers d'unité en TOCTOU-safe local (`os.open(O_NOFOLLOW)`) quand la cible est locale, et via l'`executor` injecté (`input=`) quand elle est distante — sans régression sur le cas local existant. |
| F-11 | Must have       | `ConfigurationManager` expose un chemin d'écriture basé sur un `CommandExecutor` injecté (local ou SSH), en plus de l'écriture locale directe existante (comportement des appelants actuels inchangé). |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Aucune contrainte forte — usage ponctuel/déclenché par timer, pas de chemin critique en latence. |
| Disponibilité   | Usage ponctuel (outillage homelab), pas de service continu. |
| Sécurité        | Fichier de secrets déposé en 0600 ; jamais logué en clair ; jamais transporté via le rsync de `source_dir` ; transport chiffré (SSH déjà en place). |
| Maintenabilité  | `mypy --strict` = 0 erreur, gate bloquant (acquis sur `linuxtools`, cf. `CLAUDE.md`) ; couverture ≥ 90 % (`fail_under = 90` déjà configuré). |
| Portabilité     | Linux, Python 3.11+, stdlib uniquement pour le cœur (`linuxtools` = stdlib-only + dépendances optionnelles existantes `pydantic`/`python-dotenv`/`keyring`). |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|------------------------------------------------------------|
| Langage       | Python 3.11+                                              |
| Environnement | Local ou distant via SSH (réutilise `DeployTarget`/`SshCommandExecutor` existants). |
| Dépendances   | Aucune nouvelle dépendance externe — réutilise et modifie `commands`, `config`, `credentials`, `systemd` déjà présents dans `linuxtools`. |
| Rétrocompatibilité | Tout ajout de paramètre sur une API publique existante (`CommandExecutor.run`, `SystemdExecutor.__init__`, `ConfigurationManager`) doit être optionnel à valeur par défaut préservant le comportement actuel — les 8 consommateurs de `linuxtools` et le `README` ne doivent pas casser. |
| Infrastructure| Forgejo Actions, `mypy` bloquant en CI (déjà en place). |
| Données       | Fichiers TOML de config, secrets textuels (pas de base de données). |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — pour la cible locale
- [x] **Réseau interne** — cible distante via SSH sur le LAN/homelab
- [ ] **Exposé Internet** — API publique / interface web

> ⚠️ « Réseau interne » coché (déploiement SSH vers des hôtes du homelab) →
> activer `python-owasp-security` et `python-sast-bandit-security` sur les
> nouveaux collaborateurs, en particulier la manipulation des secrets.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Un `deploy()` configuré avec config+secrets+timer livre un service
      systemd actif sur une cible fraîche (locale ou SSH), sans étape
      manuelle supplémentaire.
- [ ] Le fichier de secrets déposé sur la cible est en permissions 0600,
      et n'apparaît à aucun moment dans le rsync du `source_dir`.
- [ ] Aucune valeur de secret n'apparaît dans les logs (`self._log`) ni
      dans `DeployReport.messages`.
- [ ] Un `deploy()` sans configuration config/secrets/timer se comporte
      exactement comme avant ce lot (non-régression).
- [ ] `SystemdExecutor(logger)` et `ConfigurationManager(...)` sans
      executor injecté se comportent exactement comme avant ce lot
      (non-régression sur l'usage documenté dans le `README`).
- [ ] L'écriture locale d'une unité systemd reste TOCTOU-safe
      (`os.open(O_NOFOLLOW)`) — aucune régression de sécurité sur le cas
      local existant.
- [ ] `mypy --strict` = 0 erreur sur les fichiers modifiés/ajoutés
      (`deploy`, `commands`, `systemd`, `config`).
- [ ] Tests unitaires sur les nouveaux collaborateurs, les nouvelles
      branches de `Deployer.deploy()`, et les modifications de
      `commands`/`systemd`/`config`, couverture globale ≥ 90 %.
- [ ] Aucun avertissement Bandit sévérité MEDIUM ou supérieure.
- [ ] Documentation à jour (docstrings PEP 257 FR, `README.md`, notes
      Obsidian des modules `deploy`, `systemd`, `config`).

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | Nouveaux collaborateurs dans `src/linuxtools/deploy/` + extension de `models.py`/`deployer.py`/`__init__.py` ; modification de `commands/base.py`, `commands/runner.py`, `deploy/ssh_executor.py`, `systemd/executor.py`, `systemd/base.py`, `config/manager.py` | |
| Tests                 | `tests/test_deploy_*.py` étendus + `tests/test_commands_*.py`, `tests/test_systemd_*.py`, `tests/test_config_*.py` étendus, couverture ≥ 90 % | |
| Documentation         | `README.md` + docstrings PEP 257 + notes Obsidian « Module deploy », « Module systemd », « Module config » | |
| Makefile              | Inchangé (cibles existantes suffisent) | |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01| Format de la config secrets dans `DeployConfig` : liste de clés `CredentialManager` (+ nom de service) à résoudre à l'envoi, ou mapping clé→valeur déjà résolu fourni par l'appelant ? | Frederic | **Résolu** — `SecretsProvisioner` reçoit un `CredentialManager` **injecté** (comme `Logger`/`CommandExecutor` ailleurs dans le projet) + une liste de clés à résoudre. Les valeurs en clair ne transitent jamais par `DeployConfig` (dataclass figée, risque de log/repr accidentel) — elles sont résolues à l'exécution par le collaborateur injecté. |
| Q-02| Le dépôt du TOML de config passe-t-il par une simple copie (fichier local → cible), ou par `ConfigurationManager` pour validation/réécriture avant dépôt ? | Frederic | **Résolu** — passe par `ConfigurationManager` (validation/réécriture avant dépôt), pas une simple copie de fichier. |
| Q-03| Installation du service+timer : uniquement via `install_from_toml` (un fichier TOML `[service]`/`[timer]`), ou aussi via des dataclasses `ServiceConfig`/`TimerConfig` construites par l'appelant ? | Frederic | **Résolu** — via des dataclasses `ServiceConfig`/`TimerConfig` construites en Python par l'appelant (pas `install_from_toml`). |
| Q-04| Le rollback existant (restauration du venv) doit-il s'étendre à config/secrets/timer, ou ces nouvelles phases restent-elles best-effort/non transactionnelles (documenté comme tel dans `DeployReport`) ? | Frederic | **Résolu** — best-effort/non transactionnel pour ces trois phases (contrairement au venv) ; en cas d'échec, `Deployer` s'arrête et rapporte la phase atteinte sans tenter de restaurer l'ancien état. Ces opérations sont idempotentes : rejouer `deploy()` après correction écrase proprement. À documenter explicitement dans les docstrings de `DeployReport`/`DeployPhase`. |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
