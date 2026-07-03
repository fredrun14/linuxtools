# Changelog

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
