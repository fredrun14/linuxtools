# Changelog

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
