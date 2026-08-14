# Changelog

## [1.19.1] - 2026-08-14

### Corrigé
- Dépendance `webapitools` déclarée via URL git directe au lieu d'une
  contrainte de version (`webapitools` n'est publié sur aucun index de
  paquets) — `linuxtools >= 1.19.0` était installable en développement
  local (`uv sync` avec dépôt frère `../webapitools`) mais pas comme
  dépendance externe d'un autre projet (`pip`/`uv` cherchaient
  `webapitools` sur PyPI et échouaient). `[tool.uv.sources]` reste actif
  pour le développement local, inchangé.

## [1.19.0] - 2026-08-14

### Modifié

- `AsusRouterClient` déplacé vers `webapitools` (transport HTTP factorisé
  sur `BaseApiClient`, retry/mapping d'erreurs mutualisés). **`linuxtools`
  gagne ici sa première dépendance de production non-stdlib**
  (`webapitools>=0.11.1`) — jusqu'ici documentée « stdlib uniquement ».
  Ce chantier résout la tension pour le module routeur (le transport qui
  forçait `urllib` pur part vers `webapitools`, qui dépend déjà de
  `requests`) au lieu de l'aggraver.
- `linuxtools.network.router` ne garde que `RouterConfig`,
  `RouterAuthError` et les 3 adaptateurs métier (`AsusRouterScanner`,
  `AsusRouterDhcpManager`, `AsusRouterMacFilterManager`).
  `AsusRouterClient` reste importable depuis `linuxtools.network(.router)`
  (ré-export) — aucun changement pour les consommateurs existants (Q-03
  du CDC cross-repo).
- `webapitools.core.exceptions.AuthError` levée par
  `AsusRouterClient.login()` est traduite en `RouterAuthError` à la
  frontière de chacun des 3 adaptateurs (contrat documenté sur les ABC
  `network/base.py` préservé).
- Le `logger` (ABC `linuxtools.logging.base.Logger`) des 3 adaptateurs
  n'est plus transmis au client `webapitools.AsusRouterClient` : son
  paramètre `logger` attend un `logging.Logger` (stdlib), incompatible
  avec l'ABC maison (méthodes `log_info`/`log_warning`/`log_error` vs
  `info`/`warning`). Chaque adaptateur continue de journaliser lui-même
  via `self._logger` ; seul le logging interne bas niveau du client HTTP
  (`webapitools`) est désormais silencieux côté `linuxtools`.

## [1.18.0] - 2026-08-13

### Ajouté

- **Filtrage MAC Wi-Fi du routeur ASUS** — ABC `MacFilterManager`
  (`network/base.py`), dataclass `MacFilterStatus` (`network/models.py`),
  implémentation `AsusRouterMacFilterManager`
  (`network/router/mac_filter.py`) et `AsusRouterClient.set_mac_filter()`
  (`network/router/client.py`). Même mécanique que
  `AsusRouterDhcpManager`/`RouterDhcpManager` déjà en place pour les
  réservations DHCP, transposée au filtre MAC Wi-Fi (`wl{band}_macmode` /
  `wl{band}_maclist_x`). `mode` et `bands` validés dans la bibliothèque
  elle-même (pas seulement côté appelant).

## [1.17.1] - 2026-08-13

### Corrigé

- **`AsusRouterDhcpManager.read_reservations()` retournait 0 réservation
  alors que le routeur en avait bien** — `_parse_nvram_reservations`
  (`_nvram.py`) ne décodait pas les entités HTML `&#60`/`&#62` (sans `;`
  terminal) que le firmware ASUS utilise pour encoder `<`/`>` dans la
  réponse JSON du hook `nvram_get`. Même décodage littéral déjà appliqué à
  `_parse_custom_clientlist`, désormais répercuté ici. Faux négatif
  découvert en conditions réelles : un `push-dhcp` réussi (12 réservations)
  était rapporté comme vide par `read_reservations()`.

## [1.17.0] - 2026-08-13

### Ajouté

- **`RouterConfig.verify_tls` (défaut `False`)** — `AsusRouterClient`
  construit désormais un contexte SSL permissif par défaut sur ses 4 appels
  HTTPS (`login`, `logout`, `_hook`, `set_static_reservations`), pour
  fonctionner avec le certificat auto-signé des interfaces d'admin des
  routeurs grand public (ASUS/Merlin inclus). L'URL reste restreinte aux
  plages LAN privées par `_validate_router_url()` (protection SSRF
  inchangée). Un déploiement avec certificat valide peut repasser en
  vérification stricte via `verify_tls=True`.

## [1.16.0] - 2026-08-13

### Changements incompatibles

#### Module `scripts` — `CommandExecutor` injecté

- **`LinuxCliInstaller.__init__` passe de `(logger, checker)` à
  `(checker, executor, logger=None)`** et **`LinuxScriptChecker.__init__`
  de `(logger)` à `(executor, logger=None)`** — les deux classes
  appelaient `subprocess.run` en dur, hors de l'abstraction
  `CommandExecutor` utilisée partout ailleurs (`VenvInstaller` dans
  `deploy`, par exemple). Elles ne pouvaient donc pas cibler un hôte
  distant en SSH. L'appelant construit désormais **un seul** exécuteur et
  le partage entre les deux : `_run_uv_install`, `_find_uv`,
  `check_python`, `check_venv`, `check_script_syntax` et
  `check_dependencies` passent tous par `probe()`/`run()`.
  ⚠ **`backup-py-manager`, seul consommateur externe connu, doit migrer.**
- **Écriture du wrapper bash** — abandon de
  `os.open(O_NOFOLLOW)` + `fchmod` (local uniquement) au profit d'une
  séquence `mktemp` + `tee` + `chmod` + `mv` passée à l'exécuteur : `mv`
  ne suit jamais un lien symbolique en position destination, la garantie
  TOCTOU est équivalente, et le chemin de code devient identique en local
  et en distant.
- Effet de bord : les 5 constats Bandit du module `scripts` tombent à 0,
  plus aucun `subprocess.run` n'y subsistant.

### Nouvelles fonctionnalités

#### Module `deploy` — scope utilisateur pour `TimerDeploySpec`

- **`TimerDeploySpec.scope: Literal["system", "user"] = "system"`** —
  `TimerDeployer` sait désormais installer le service+timer soit en mode
  **système** (`/etc/systemd/system/`, comportement historique inchangé,
  toujours le défaut, nécessite root), soit en mode **utilisateur**
  (`~/.config/systemd/user/`, `systemctl --user`, sans élévation de
  privilèges). Bloquant réel rencontré lors d'un premier déploiement d'un
  outil personnel (`backup-py-manager deploy`) sur poste Fedora : sauvegarder
  son propre home ne doit pas exiger root.
- Les briques utilisateur (`UserSystemdExecutor`,
  `LinuxUserServiceUnitManager`, `LinuxUserTimerUnitManager`) existaient
  déjà dans `linuxtools.systemd` depuis le 2026-07-19 mais n'étaient
  mobilisées par aucun module — `TimerDeployer.deploy()` les câble
  désormais dans une méthode privée dédiée (`_deploy_user`), symétrique de
  `_deploy_system` (copie stricte de l'ancien corps de `deploy()`, aucune
  régression possible sur le chemin système existant).
  ⚠ **`service_timer_installer.py` non modifié, volontairement** :
  `SystemdServiceTimerInstaller` reste typé aux seules ABCs système
  (`ServiceUnitManager`/`TimerUnitManager`) — les classes utilisateur sont
  des classes sœurs, pas des sous-types, et les y faire transiter aurait
  cassé `mypy --strict` ou élargi le risque à une classe partagée par
  d'autres consommateurs de `linuxtools.systemd`. `_deploy_user()` orchestre
  donc directement les 3 étapes (`install_service_unit_with_name` →
  `install_timer_unit` → `enable_timer`) sur les managers utilisateur —
  petite duplication assumée plutôt qu'une abstraction commune prématurée.
- Fonctionne aussi en cible SSH distante (`remote_write` propagé comme côté
  système) — cohérent avec l'agnosticisme local/distant du reste du module.
- Hors périmètre, assumé : `loginctl enable-linger` (survie du timer
  utilisateur après déconnexion) n'est ni automatisé ni signalé — à la
  charge de l'appelant si nécessaire.

### Corrections

#### `RsyncTransport` — création des répertoires parents manquants

- **`extra_options` par défaut passe de `("-a", "--delete")` à
  `("-a", "--delete", "--mkpath")`** — sans `--mkpath`, un premier
  déploiement vers un chemin dont aucun ancêtre n'existait encore sur la
  cible (locale ou distante) échouait avec `mkdir "..." failed: No such
  file or directory (2)`. `--mkpath` (rsync ≥ 3.2.3) crée récursivement les
  répertoires parents manquants de la destination. Bug réel trouvé via
  `backup-py-manager deploy --profile home` sur poste Fedora neuf.

### Outillage

- **`uv.lock` resynchronisé** — le fichier de verrouillage était resté à
  `version = "1.14.0"` après la release 1.15.0, qui n'avait touché que
  `pyproject.toml`. Sans incidence à l'installation (`source = { editable
  = "." }`), mais l'écart laissait un fichier modifié en permanence dans
  l'arbre de travail.

## [1.15.0] - 2026-08-06

### Nouvelles fonctionnalités

#### Module `deploy` — config TOML, secrets et timer systemd

- **`Deployer` gagne trois collaborateurs optionnels** — `ConfigDeployer`,
  `SecretsProvisioner` et `TimerDeployer`, sur le modèle de
  `Transport`/`VenvInstaller`/`InstallVerifier` : **best-effort et non
  transactionnels**, actifs indifféremment sur cible locale ou SSH. Le
  déployeur ne gère donc plus seulement le **code**, mais aussi la config
  runtime, les secrets et la planification.
- **Secrets jamais déposés par le `rsync` du `source_dir`** — fichier
  séparé en `0600` (`KEY=value`), référencé depuis l'unit par
  `EnvironmentFile=`. `ServiceConfig` gagne `environment_file`, rendu
  **avant** les `Environment=` inline : les secrets ne transitent jamais
  par le fichier unit, lisible en `0644`.

Ce chantier a exigé de corriger l'abstraction sous-jacente plutôt que de
contourner localement dans `deploy` (contournement rejeté en revue) :

- **`CommandExecutor.run(stdin: str | None)`** — permet de piper du
  contenu vers une commande distante (`tee`, `chmod`).
- **`SystemdExecutor` / `UserSystemdExecutor`** reçoivent un
  `CommandExecutor` injecté (défaut local, rétrocompatible) au lieu du
  `subprocess.run` codé en dur dans `_run_systemctl` ; nouvelle méthode
  `run_raw()`.
- **`UnitManager` / `UserUnitManager` : drapeau explicite `remote_write`**
  — écriture locale inchangée (TOCTOU-safe, `os.open(O_NOFOLLOW)`),
  écriture distante via l'exécuteur injecté (`tee` + `chmod`).
- **`ConfigurationManager.deploy_via()`** — même schéma pour le dépôt du
  fichier TOML.
- ⚠ **Annotation corrigée** sur `get_status()`, `get_mount_status()`,
  `get_timer_status()` et `get_service_status()` : `str | None` devient
  `str` — `CommandResult.stdout` ne renvoie jamais `None` depuis le
  passage à `CommandExecutor`, et aucun appelant ne testait `is None`.

Toutes les API existantes restent rétrocompatibles.

### Outillage

- **Hook `pre-commit`** (`.githooks/pre-commit`) — bloque le commit local
  sur exactement le même gate que la CI (`make lint` + `make test`), joué
  sur l'arbre `src/`+`tests/` complet et non sur les seuls fichiers
  indexés : un commit vert en local garantit un run de CI vert.
  Contournement explicite : `git commit --no-verify`. Récupéré
  automatiquement via le `core.hooksPath=.githooks` déjà en place sur le
  dépôt (`make hooks`).

### Documentation

- **Docstrings de package harmonisées** — `config`, `errors`,
  `filesystem`, `identity`, `integrity`, `logging`, `scripts` et
  `validation` avaient un docstring de package réduit à une ligne
  (`"""Module de configuration."""` etc.), en retrait du gabarit
  posé par `cli`/`commands`/`dotconf`/`systemd` (résumé, catégories
  d'exports, exemple d'utilisation). Alignées sur ce gabarit. Aucun
  changement de comportement, `make lint`/`make test` inchangés
  (1561 tests, couverture 96.68%).

### Métadonnées

- **`[project.urls]` désignent Forgejo** — les cinq URLs pointaient
  `github.com/fredrun14/linuxtools`, c'est-à-dire la sauvegarde. Or elles
  sont embarquées dans le wheel publié : `Issues` routait les rapports de
  bug vers une forge que personne ne surveille. Elles désignent désormais
  `git.ricfasohel.fr/fred/linuxtools`, la forge de référence. `Changelog`
  a été transposé en `/src/branch/master/CHANGELOG.md` — la syntaxe de
  permalien de Forgejo, `/blob/master/…` y renvoyant un 404. Aucune
  incidence sur l'API : pas de bump de version.

## [1.14.0] - 2026-07-28

### Nouvelles fonctionnalités

#### Module `commands` — façade `probe()`

- **`CommandExecutor.probe()`** — Nouvelle méthode concrète sur l'ABC
  (pas `@abstractmethod`) : pure façade de `run(..., probe=True)`.
  `self._executor.probe(cmd)` remplace `run(cmd, probe=True)` au point
  d'appel — une seule façon évidente d'exprimer une sonde en lecture
  seule, le nom de la méthode porte le contrat, et un drapeau qu'on
  n'écrit plus est un drapeau qu'on ne peut plus apposer par erreur
  sur une commande mutante. `run(probe=...)` reste inchangé, aucune
  rupture.
- **`LinuxCommandExecutor`** et **`SshCommandExecutor`** héritent de
  `probe()` sans redéfinition : la méthode s'exprime entièrement via
  `run()`, qui reste abstraite. Pour `SshCommandExecutor`, l'héritage
  passe par sa propre surcharge de `run()`, qui propage `probe` à
  l'exécuteur local sous-jacent — la substituabilité (LSP) est donc
  préservée.

#### Nouveau module `distro`

- **`linuxtools.distro.fedora_version(executor)`** — Déduplication de
  l'implémentation identique présente jusqu'ici dans
  `package_manager.py` et `repo_manager.py` côté `fedora_post_install`.
  Entorse assumée à l'agnosticisme de la bibliothèque (« pour systèmes
  Linux ») : contenue volontairement dans un module isolé et
  documenté comme tel, extractible d'un bloc si une distribution
  non-RPM entre un jour dans le parc.
  ⚠ **Changement de comportement** par rapport à
  `package_manager._fedora_version` : la version lib retient la
  variante défensive (déjà en place dans `repo_manager._fedora_version`)
  et renvoie `""` sur code retour non nul, là où
  `package_manager._fedora_version` renvoyait la sortie brute de
  `rpm --eval %fedora` sans tester le code retour. Comportement
  strictement identique à `repo_manager`, différent pour
  `package_manager` — voulu, à vérifier chez les appelants qui
  résolvent `${FEDORA_VERSION}`.

## [1.13.0] - 2026-07-28

### Nouvelles fonctionnalités

#### Module `commands` — Sondes en lecture traversant le dry-run

- **`CommandExecutor.run()` / `LinuxCommandExecutor.run()`** — Nouveau
  paramètre `probe: bool = False` (dernière position, rétrocompatible).
  Quand `probe=True`, la commande s'exécute réellement même en mode
  `dry_run` : réservé aux sondes en lecture seule sans effet de bord
  (`rpm -q`, `dnf5 repolist`, `flatpak info`), sur lesquelles le mode
  simulation s'appuie pour décider quoi faire. `run_streaming()` n'est
  pas concerné (réservé aux opérations mutantes).
- **`SshCommandExecutor.run()`** — `probe` propagé tel quel à
  l'exécuteur local sous-jacent, pour rester substituable à
  `LinuxCommandExecutor` (LSP).

## [1.12.0] - 2026-07-25

### Outillage

#### Annotation `config` des loggers fichier

- **`FileLogger`/`RotatingFileLogger`** — Annotation `config` élargie via un
  `Protocol _SupportsGet` (`get()` positionnel-only), alignée sur la
  docstring et `_resolve_config` : `dict[str, Any] | _SupportsGet | None`.
  Un `ConfigurationManager` passe désormais la vérification de types chez
  le consommateur (utile grâce à `py.typed`).

#### CI Forgejo-first et promotion GitHub sur vert

- **Forgejo** devient la forge de référence : `.forgejo/workflows/ci.yml`
  exécute la CI complète (lint, mypy strict, tests, build) ; le hook
  `post-commit` n'y pousse plus qu'elle.
- **GitHub** devient un miroir promu : un job `promote` déclenche la
  synchro d'un miroir de push Forgejo→GitHub une fois la CI verte
  (`lint`/`test`/`build`), et `.github/workflows/release.yml` publie une
  GitHub Release (wheel + sdist) sur tag `v*` — sans publication PyPI.

## [1.11.0] - 2026-07-24

### Outillage

#### Typage exposé (PEP 561) et zéro dette mypy

`linuxtools` était entièrement typé (PEP 484) mais ce typage restait invisible
et non vérifié en amont. Ce chantier l'expose et le verrouille :

- **`py.typed`** — Ajout du marqueur PEP 561 à la racine du paquet. Les
  consommateurs (`backup-py-manager`, `obsidian-vault-tools`,
  `fedora_post_install`, `nas-diy-tools`) bénéficient désormais de la
  vérification mypy sur `linuxtools`.
- **Zéro dette `mypy --strict`** — Correction des 33 erreurs strictes
  latentes (générique non paramétré, retour `Any`, gardes de nullabilité
  manquantes) réparties sur 13 fichiers. Aucun `# type: ignore` ni `cast()`
  ajouté : chaque cause a été corrigée à la source.
- **`credentials.chain.CredentialChain`** — `get()` et `get_with_source()`
  gardent désormais explicitement `provider is not None` en complément de
  `value is not None` (comportement inchangé, type prouvé par mypy).
- **Verrouillage CI** — `mypy src/linuxtools/` intégré à `make lint` et à un
  nouveau step « Type check (mypy strict) » du job `test` de la CI, pour
  empêcher toute régression future du typage.

## [1.10.0] - 2026-07-19

### Nouvelles fonctionnalités

#### Module `deploy` — Déploiement/mise à jour d'un outil Python sur hôte

Nouveau module factorisant le rituel de déploiement d'un outil Python maison sur un
hôte (poste ou serveur), en local ou à distance via SSH. Orchestre **4 phases** —
transport → (ré)installation venv → vérification post-install → **rollback
automatique** — auparavant réécrites à la main projet par projet. **stdlib
uniquement**, injection de dépendances systématique, exposé en API Python et en
`CliCommand`. Le déployeur gère le **code**, pas la config runtime ni les secrets.

- **`Deployer`** — Orchestrateur des 4 phases. `Deployer.for_target(target)` fabrique
  les collaborateurs standards ; `deploy(config)` retourne un `DeployReport`. Rollback
  automatique du venv si l'installation ou une vérification échoue et qu'un backup
  existe.
- **`SshCommandExecutor` (`CommandExecutor`)** — Exécute à distance en enveloppant
  chaque commande dans `ssh [opts] user@host -- <cmd>` (interpolation `shlex`-safe),
  déléguant l'exécution locale du binaire `ssh` à un `LinuxCommandExecutor`. Rend
  `Deployer`, `VenvInstaller` et `InstallVerifier` agnostiques local/distant.
- **`Transport` (ABC) + `RsyncTransport`** — Acheminement du source via `rsync`
  (local → local ou local → `user@host:`), toujours lancé en local.
- **`VenvInstaller`** — Sauvegarde du venv (`.bak-<horodatage>`), (ré)installation via
  le `pip` du venv (`--force-reinstall`), restauration et purge. Le backup est pris
  **avant** toute installation ; son échec lève `DeployError` (pas d'install sans filet).
- **`InstallVerifier` + `VerificationSpec`** — Vérifications déclaratives : imports à
  tester, sous-commandes attendues (`<cli_bin> <sub> --help`), commande de
  non-régression optionnelle rejouée sur l'hôte.
- **`DeployCommand` (`CliCommand`)** — Sous-commande `deploy` prête à enregistrer dans
  le `CliApplication` d'un projet consommateur, avec mode `--dry-run`.
- **Auto-détection du source** — `find_project_source()` (remontée robuste vers
  `pyproject.toml`) et `find_editable_source()` (`direct_url.json` d'une install
  éditable) ; `DeployConfig.source_dir` est optionnel.
- **Modèles** — `DeployConfig`, `DeployTarget`, `DeployReport` (`format_summary()`),
  `CheckResult`, enum `DeployPhase`, exception `DeployError`.

Sécurité : interpolation `ssh`/`rsync` via `shlex.quote`/`shlex.join` ; jamais de
`pip` système (pas de heurt PEP 668 sur Fedora 41+) ; mypy `--strict` et Bandit sans
alerte. Couverture du module ≥ 99 % (110 tests dédiés).

## [1.9.0] - 2026-07-14

### Nouvelles fonctionnalités

#### Module `systemd` — Installateurs TOML service+timer et mount+automount

- **`SystemdServiceTimerInstaller`** — Installe un couple service + timer sans script
  wrapper, avec `install()` et `install_from_toml()`.
- **`SystemdAutomountInstaller`** — Installe un couple mount + automount (NFS/CIFS)
  avec `install()` et `install_from_toml()`.
- **`ServiceConfigLoader`** lit désormais les directives de durcissement
  (`no_new_privileges`, `protect_system`, …) depuis le TOML.
- **`MountConfigLoader.load_with_automount()`** + `AutomountSettings` pour piloter le
  montage automatique.

## [1.8.0] - 2026-07-13

### Nouvelles fonctionnalités

#### Module `systemd` — Directives de durcissement sur `ServiceConfig`

`ServiceConfig` expose désormais cinq champs optionnels de durcissement, rendus
dans `to_unit_file()` uniquement s'ils sont activés (rétro-compatible : sans
surcharge, le fichier `.service` produit est identique aux versions ≤ 1.7.0) :

- `no_new_privileges: bool` → `NoNewPrivileges=true`
- `protect_system: str` (`""` | `true` | `full` | `strict`, validé) → `ProtectSystem=`
- `protect_home: bool` → `ProtectHome=true`
- `private_tmp: bool` → `PrivateTmp=true`
- `read_write_paths: tuple[str, ...]` → `ReadWritePaths=` (chemins espacés,
  filtrés contre l'injection de caractères de contrôle)

## [1.7.0] - 2026-07-08

### Nouvelles fonctionnalités

#### Module `notification` — Notifications multi-canaux et comptes rendus

Extension du module `notification` (jusqu'ici limité au générateur bash
`NotificationConfig`) avec une API Python d'envoi de notifications multi-canaux et
de comptes rendus de fin d'exécution de scripts (backup, post-install…). **stdlib
uniquement**, injection de dépendances systématique, `NotifierChain` best-effort
calquée sur `ErrorHandlerChain`.

- **`Notifier` (ABC)** — Interface d'un canal de diffusion : `send(notification)`.
- **`NotifierChain`** — Diffuse une notification/un rapport à tous les notifiers
  enregistrés en best-effort : l'échec d'un canal n'empêche pas les suivants.
- **Modèles** — `Notification` (immuable, validée), `Urgency` (`LOW`/`NORMAL`/
  `CRITICAL`), `StepResult`, et `ExecutionReport` (accumulation d'étapes + résumé,
  `to_notification()`, context manager `step()` qui chronomètre et absorbe les
  exceptions par défaut).
- **Notifiers concrets** :
  - `DesktopNotifier` — `notify-send`, mode session courante ou `all_users=True`
    (portage Python de la boucle `loginctl`/`runuser` pour timers systemd en root).
  - `GotifyNotifier` — push vers un serveur Gotify auto-hébergé (`urllib`).
  - `SmtpEmailNotifier` — email SMTP avec STARTTLS par défaut (`smtplib`).
  - `JournaldNotifier` — écriture sur le socket natif journald (multiligne géré) ;
    consultation via `journalctl -t <app_name>`.
- **Exceptions** — `NotificationError` / `NotificationSendError`, rattachées à
  `ApplicationError`.

Le token Gotify et le mot de passe SMTP se chargent via `CredentialChain` — jamais
en dur.

```python
report = ExecutionReport(script_name="backup-nas")
with report.step("rsync documents"):
    executor.run([...])
report.finish()

chain = NotifierChain(logger=logger)
chain.add_notifier(GotifyNotifier(base_url="https://gotify.lan", token=token))
chain.add_notifier(JournaldNotifier(app_name="backup-nas"))
chain.send_report(report)
```

## [1.4.0] - 2026-04-05

### Nouvelles fonctionnalités

#### Module `cli` — Framework CLI Command Pattern

- **`CliCommand` (ABC)** — Interface abstraite pour les sous-commandes CLI. Méthodes abstraites : `name` (property), `register(subparsers)`, `execute(args)`.
- **`CliApplication`** — Orchestrateur CLI basé sur le Command Pattern. Prend une liste de `CliCommand`, construit le parser argparse, et dispatche vers la commande sélectionnée via `run()`.

```python
class SyncCommand(CliCommand):
    @property
    def name(self) -> str:
        return "sync"

    def register(self, subparsers: Any) -> None:
        subparsers.add_parser(self.name, help="Synchronise les données")

    def execute(self, args: argparse.Namespace) -> None:
        print("sync exécuté")

app = CliApplication(
    prog="mon-outil",
    description="Mon outil CLI",
    commands=[SyncCommand()],
)
app.run()
```

#### Module `logging` — `ConsoleLogger`

- **`ConsoleLogger`** — Implémentation légère de `Logger` écrivant sur stdout/stderr sans créer de fichier. Les `log_info()` vont sur stdout, `log_warning()` et `log_error()` sur stderr. Idéal pour les dry-run, scripts légers et tests.

```python
from linuxtools import ConsoleLogger

logger = ConsoleLogger()
logger.log_info("Démarrage...")      # → stdout
logger.log_warning("Absent")        # → stderr : WARNING: Absent
logger.log_error("Échec")           # → stderr : ERROR: Échec
```

### Corrections

- **`__init__.py`** : `ConsoleLogger`, `SecurityLogger`, `SecurityEvent`, `SecurityEventType` ajoutés aux exports publics du package.
- **`__init__.py`** : `PathCheckerPermission` et `PathCheckerWorldWritable` étaient dans `__all__` mais pas importés (bug NameError) — corrigé.

---

## [1.3.0] - 2026-02-21

### Nouvelles fonctionnalités

#### Module `commands` — Distinction root/user dans les logs et la console

- **`CommandFormatter` (ABC)** — Interface abstraite de formatage des messages de commandes (nouveau fichier `commands/formatter.py`). Méthodes : `format_start()`, `format_start_streaming()`, `format_dry_run()`, `format_line()`.
- **`PlainCommandFormatter`** — Formateur texte brut pour les logs fichier : préfixe `[ROOT]` pour les exécutions root (uid=0), préfixe `[user]` pour les utilisateurs standard. Aucun code ANSI : compatible avec `grep`, éditeurs de texte et fichiers de log.
- **`AnsiCommandFormatter`** — Formateur ANSI coloré pour la console : jaune-or gras (`\033[1;33m`) pour root, vert (`\033[0;32m`) pour user, gris (`\033[0;90m`) pour dry-run. Désactivé automatiquement hors TTY (pipes, redirections).
- **`CommandResult.executed_as_root`** — Nouveau champ `bool` (défaut `False`) indiquant si la commande a été exécutée avec les privilèges root. Utile pour les appelants souhaitant adapter leur comportement.
- **`LinuxCommandExecutor`** — Nouveau paramètre `console_formatter: Optional[CommandFormatter]`. Détecte automatiquement `os.getuid() == 0` à l'initialisation. Utilise `PlainCommandFormatter` pour tous les messages logger (logs fichier propres), et le `console_formatter` fourni pour l'affichage console coloré indépendant.

### Utilisation

```python
# Logs fichier avec préfixe [ROOT]/[user] (comportement par défaut)
executor = LinuxCommandExecutor(logger=logger)

# Console colorée + logs fichier
executor = LinuxCommandExecutor(
    logger=FileLogger("/var/log/app.log"),  # sans console_output=True
    console_formatter=AnsiCommandFormatter(),
)

# Accéder au contexte d'exécution
result = executor.run(["systemctl", "restart", "nginx"])
print(result.executed_as_root)  # True si lancé en root
```

### Tests

- +40 nouveaux tests dans `test_commands.py` (34 → 74) :
  - `TestCommandResultExecutedAsRoot` : valeur par défaut, immutabilité, assignation explicite
  - `TestPlainCommandFormatter` : préfixes [ROOT]/[user], absence de codes ANSI, format_line
  - `TestAnsiCommandFormatter` : styles ANSI avec/sans TTY, dry-run en gris, héritage ABC
  - `TestLinuxCommandExecutorPrefixeLogs` : préfixes dans les messages de log (root et user)
  - `TestLinuxCommandExecutorConsoleFormatter` : appels formatter sur run/streaming/dry-run
  - `TestLinuxCommandExecutorExecutedAsRoot` : valeur dans tous les résultats (succès, échec, dry-run)
- Total : 474 tests (était 310 avant l'ajout du module network et de cette version)

---

## [1.2.0] - 2026-02-16

### Sécurité

- **MOYENNE** : Élimination TOCTOU dans `_write_unit_file()` — remplacement du pattern `islink()` + `open()` par `os.open(O_NOFOLLOW)` qui refuse atomiquement les liens symboliques. Pas de fenêtre de course exploitable.
- **MOYENNE** : Élimination TOCTOU dans `_remove_unit_file()` — remplacement du pattern `exists()` + `remove()` par `try/except FileNotFoundError`.
- **MOYENNE** : Permissions explicites 0o644 sur les fichiers unit — `os.fchmod(fd, 0o644)` après création, indépendant du umask.
- **MOYENNE** : Validation des noms d'unités dans `SystemdExecutor` — tous les noms passés à `enable_unit()`, `disable_unit()`, `start_unit()`, `stop_unit()`, `restart_unit()`, `get_status()` et `is_enabled()` sont validés via `validate_unit_name()`.
- **MOYENNE** : Validation des noms dans les méthodes timer — `enable_timer()`, `disable_timer()`, `remove_timer_unit()`, `get_timer_status()` valident via `validate_unit_name()` dans `timer.py` et `user_timer.py`.
- **MOYENNE** : Validation des noms dans les méthodes service — `start_service()`, `stop_service()`, `restart_service()`, `enable_service()`, `disable_service()`, `remove_service_unit()`, `get_service_status()`, `is_service_enabled()` valident via `validate_service_name()` dans `service.py` et `user_service.py`.
- **BASSE** : Réduction des `except Exception` dans `executor.py` — `get_status()` et `is_enabled()` capturent désormais `(subprocess.SubprocessError, OSError)` au lieu de `Exception`.
- **BASSE** : Validation de `ServiceConfig.type` — restreint aux 7 types systemd connus (`simple`, `exec`, `forking`, `oneshot`, `dbus`, `notify`, `idle`).
- **BASSE** : Validation de `ServiceConfig.restart` — restreint aux 7 politiques connues (`no`, `always`, `on-success`, `on-failure`, `on-abnormal`, `on-abort`, `on-watchdog`).
- **BASSE** : Protection contre l'injection via `Environment=` dans `ServiceConfig` — les clés contenant `=` ou `\n` et les valeurs contenant `\n` sont rejetées.

### Refactoring

- **DRY** : Factorisation de `_write_unit_file()` et `_remove_unit_file()` dans les classes de base `UnitManager` et `UserUnitManager` (`base.py`). Suppression des 5 copies dupliquées dans `service.py`, `timer.py`, `mount.py`, `user_service.py` et `user_timer.py`.
- **DRY** : Factorisation de `_ensure_unit_directory()` dans `UserUnitManager` (`base.py`). Suppression des copies dans `user_service.py` et `user_timer.py`.
- **LSP** : Les méthodes `install_service_unit()` et `install_service_unit_with_name()` capturent désormais `ValueError` des validators et retournent `False` avec un log d'erreur, respectant le contrat `bool` de l'ABC.

### Tests

- 310 tests (était 276) — ajout de 34 tests couvrant :
  - Validation `ServiceConfig.type`, `ServiceConfig.restart` et `ServiceConfig.environment`
  - Protection anti-symlink TOCTOU de `_write_unit_file()`
  - Permissions 0o644 des fichiers unit créés
  - Suppression idempotente via `_remove_unit_file()`
  - Validation des noms dans `SystemdExecutor` et `UserSystemdExecutor`
  - Validation dans `start_service()`, `stop_service()`, `enable_service()`
  - Contrat LSP : `install_service_unit()` retourne `False` sur nom invalide

## [1.1.0] - 2026-02-15

### Sécurité

- **CRITIQUE** : Suppression de `eval()` dans `dotconf/section.py` — `parse_validator()` n'accepte plus que des listes de valeurs autorisées. Les validateurs callable doivent être passés directement en Python via `set_validators()`.
- **HAUTE** : Échappement des paramètres bash dans `notification/config.py` — utilisation de `shlex.quote()` dans `to_bash_call_success()` et `to_bash_call_failure()` pour prévenir les injections de commandes.
- **HAUTE** : Utilisation du context manager `with` pour `subprocess.Popen` dans `commands/runner.py` — garantit la fermeture des pipes en cas d'erreur.
- **HAUTE** : Protection anti-symlink dans les modules systemd — vérification `os.path.islink()` avant l'écriture des fichiers unit dans `service.py`, `timer.py`, `mount.py`, `user_service.py` et `user_timer.py`.
- **MOYENNE** : Validation des noms d'unités systemd — nouveau module `validators.py` avec `validate_unit_name()` et `validate_service_name()` (regex + anti-traversée).
- **MOYENNE** : Validation de `MountConfig` — `where` doit être absolu, `what` validé selon le type de montage (NFS, CIFS, device).
- **BASSE** : Réduction des `except Exception` dans `sha256.py` — `verify_file()` et `verify()` capturent `OSError` au lieu de `Exception`.
- **BASSE** : Parsing robuste de `list_timers()` — utilisation de `--output=json` avec fallback texte, gestion `FileNotFoundError`/`OSError`.

### Changements incompatibles

- `parse_validator()` n'accepte plus de strings lambda. Seules les listes `list[str]` sont acceptées.
- `set_validators()` accepte désormais directement des callables Python en plus des listes.
- Le format de sortie de `to_bash_call_success()` et `to_bash_call_failure()` utilise `shlex.quote()` au lieu de doubles quotes manuelles.
- `ServiceConfig` lève `ValueError` si `type` ou `restart` contient une valeur non reconnue par systemd.
- `ServiceConfig` lève `ValueError` si une clé d'environnement contient `=` ou `\n`, ou si une valeur contient `\n`.
