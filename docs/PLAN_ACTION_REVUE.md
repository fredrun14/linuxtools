# Plan d'action — Revue & optimisation par module

> Synthèse des revues de code (4 dimensions, Go/No-Go) et des analyses
> d'optimisation (mode analyse — aucune modification appliquée).
> Généré le 2026-06-05.

## Tableau de bord (décision sécurité par module)

| Module | Fonctionnel | Technique | Sécurité | Tests | Verdict |
|---|---|---|---|---|---|
| **systemd** | ⚠️ | ⚠️ | ❌ | ⚠️ | **NO-GO** |
| **config** | ❌ | ⚠️ | ✅ | ⚠️ | **NO-GO** |
| **credentials** | ⚠️ | ⚠️ | ❌ | ⚠️ | **NO-GO** |
| **logging** | ⚠️ | ⚠️ | ❌ | ⚠️ | **NO-GO** |
| **filesystem** | ⚠️ | ✅ | ❌ | ⚠️ | **NO-GO** |
| **commands** | ⚠️ | ⚠️ | ✅ | ⚠️ | Go conditionnel |
| **network** | ✅ | ⚠️ | ⚠️ | ✅ | Go conditionnel |
| **scripts** | ⚠️ | ⚠️ | ⚠️ | ⚠️ | Go conditionnel |
| **dotconf** | ⚠️ | ⚠️ | ✅ | ✅ | Go conditionnel |
| **errors** | ⚠️ | ⚠️ | ✅ | ✅ | Go conditionnel |
| **validation** | ✅ | ⚠️ | ⚠️ | ✅ | Go conditionnel |
| **notification** | ✅ | ✅ | ⚠️ | ⚠️ | Go conditionnel |
| **identity** | ✅ | ✅ | ⚠️ | ✅ | Go conditionnel |
| **integrity** | ✅ | ✅ | ✅ | ✅ | **GO** |
| **cli** | ✅ | ✅ | ✅ | ✅ | **GO** |

## Suivi d'avancement par module

> Légende : ✅ TODO terminé · 🔄 en cours · ⬜ à faire

### NO-GO — bloquants sécurité (priorité 1)

- [x] ✅ **systemd** — `\n`+TOCTOU+path-traversal ([TODO](TODO-20260605-1410-systemd.md)) — commit `b8287a2` · 2 items PR3 restants (non bloquants)
- [x] ✅ **config** — sérialiseur TOML invalide ([TODO](TODO-20260605-1410-config.md)) · pytest --cov + doc restants
- [x] ✅ **credentials** — fuite `Credential.value` dans repr + `load_dotenv` ([TODO](TODO-20260605-1410-credentials.md)) · bandit + pytest --cov + doc restants
- [x] ✅ **logging** — permissions fichier log `0o600`/`O_NOFOLLOW` ([TODO](TODO-20260605-1410-logging.md)) — commit `d061a29` · bandit + pytest --cov + doc partage logger restants
- [x] ✅ **filesystem** — TOCTOU `open`/`backup` ([TODO](TODO-20260605-1410-filesystem.md)) · bandit + pytest --cov restants

### Go conditionnel (priorité 2)

- [x] ✅ **commands** — fiabilité process, Template Method formatter, immutabilité ([TODO](TODO-20260605-1410-commands.md)) — commit `fbb535b`
- [x] ✅ **network** — écriture atomique, SSRF DNS-rebinding, XML ParseError ([TODO](TODO-20260605-1410-network.md)) — PR1 done
- [x] ✅ **scripts** — validation `config.name` + `O_NOFOLLOW` wrapper ([TODO](TODO-20260605-1410-scripts.md))
- [x] ✅ **dotconf** — `IndexError` content vide, `UnicodeDecodeError`, regex unique ([TODO](TODO-20260605-1410-dotconf.md))
- [x] ✅ **errors** — paramètres injectés morts (`base_error_type`, `solutions`) ([TODO](TODO-20260605-1410-errors.md))
- [x] ✅ **validation** — renommage `path_checker_Exist.py`, `os.lstat` ([TODO](TODO-20260605-1410-validation.md))
- [x] ✅ **notification** — filtrage `\n`/contrôle dans `__post_init__` ([TODO](TODO-20260605-1410-notification.md))
- [x] ✅ **identity** — validation format `name`/`group_name` ([TODO](TODO-20260605-1410-identity.md))

### GO — mineurs uniquement (priorité 3)

- [ ] ⬜ **integrity** — `verify()` source vide, whitelist algos, typing ([TODO](TODO-20260605-1410-integrity.md))
- [ ] ⬜ **cli** — documenter `register(subparsers: Any)` ([TODO](TODO-20260605-1410-cli.md))

## Top priorités transverses (bloquants sécurité)

1. **Fuite de secret** — `Credential.value` exposé dans le `repr` par défaut → `field(repr=False)`.
2. **Sérialiseur TOML invalide** — `config/manager.py:245-264` produit du TOML cassé (listes, échappement). Déléguer à `dotconf.ConfTomlExporter` (déjà corrigé, commit cc5d062).
3. **Injection de directives unit** — aucun filtrage `\n` sur les champs sérialisés systemd → `_reject_newline` centralisé.
4. **TOCTOU/symlink** — pattern `os.open(O_NOFOLLOW)+fchmod` absent dans `filesystem`, `logging`, `systemd/unit_porter`, `dotconf/manager`. Candidat : helper unique dans `filesystem/`.
5. **Permissions fichier log** — `0o600`/`O_NOFOLLOW` à la création (`file_logger.py`).
6. **`dotenv` pollue `os.environ`** global → `dotenv_values()`.

---

## systemd — NO-GO (sécurité)

**Revue — bloquants :**
- 🔴 Filtrer `\n`/contrôle sur TOUS les champs sérialisés (`to_unit_file`, `unit_porter.to_ini`) — seul `Environment=` est protégé aujourd'hui.
- 🔴 `unit_porter.restore` (l.298-300) : écriture sans `O_NOFOLLOW` + `unit_name` non validé (déduit du stem TOML) → TOCTOU + path traversal dans `/etc/systemd/system`.
- 🔴 `executor.py` : `validate_unit_name` ne valide que le radical (`rsplit(".",1)[0]`), extension passée brute → valider l'unité complète + whitelist d'extensions.

**Revue — majeurs :**
- `config_loaders/base.py` : fichier entièrement commenté (code mort) → supprimer.
- `mount_loader.py:146` : f-string sans préfixe `f` → message d'erreur cassé.
- `service.py:46`/`user_service.py:95` : nom de service dérivé via `split()`+`replace(".","-")` → fragile (espaces dans chemin). Utiliser `shlex.split` ou exiger un nom explicite.
- `subprocess.run` direct (timer/user_timer/unit_porter) contourne l'executor injecté (viole DIP projet).

**Optimisation (gain/effort) :**
- 🥇 **Mixins `_ServiceOperationsMixin`/`_TimerOperationsMixin`** (gain très élevé) : start/stop/restart/enable/disable/status identiques entre versions système et user → ~150-200 lignes supprimées.
- 🥈 Factoriser `_write_unit_file`/`_remove_unit_file` dupliqués `UnitManager`↔`UserUnitManager` (~80 lignes).
- 🥉 Scinder `base.py` (1237 l.) → `base_config.py` (dataclasses) + `base.py` (ABCs), réexport via `__init__.py`.
- Helper `_simple_action` dans `executor.py` (~80 lignes de boilerplate try/except).
- Helper unique `path_to_unit_name` (dupliqué 3×) ; supprimer import `replace` mort ; imports locaux `os`/`Path` → tête de fichier.
- ⚠️ Unifier `generate_service_unit` vs `to_unit_file` (flag `include_user`) = **change le comportement** → tests dédiés avant.

---

## config — NO-GO (fonctionnel : TOML invalide)

**Revue — bloquants/majeurs :**
- 🔴 `manager.py:245-264` `_write_toml_section` : `str(list)` → `['a','b']` (TOML invalide), strings non échappées → **déléguer à `ConfTomlExporter`**.
- `manager.py:96` : `except Exception` trop large sur le repli config → restreindre (`OSError`, `TOMLDecodeError`, `JSONDecodeError`, `ValueError`).
- `loader.py:146` : deux hiérarchies parallèles (`ConfigLoader` vs `ConfigFileLoader`) → documenter/unifier.
- `xdg.py` : `init_config_file` check-then-write → `open(...,'x')` atomique ; `chmod 0o600` si secrets.

**Optimisation :**
- 🥇 P0 trivial : supprimer code mort commenté `loader.py:260-285` (24 lignes) ; moderniser typing `Dict/Union` → `dict`/`X | None`.
- 🥈 `_write_toml*` : déléguer à `ConfTomlExporter` (corrige le bug + supprime un exporteur divergent).

**Tests :** ajouter cas TOML adversariaux (valeurs avec `"`, `\n`, listes) re-parsés par `tomllib` ; test repli sur fichier corrompu.

---

## credentials — NO-GO (sécurité : fuite secret)

**Revue — bloquants/majeurs :**
- 🔴 `models.py:35-50` : `Credential.value` dans le `repr` par défaut → fuite dans logs/tracebacks. `field(repr=False)` ou `__repr__` custom.
- 🔴 `providers/dotenv.py:66-69` : `load_dotenv()` mute `os.environ` global (fuite vers sous-process) → `dotenv_values()`.
- `providers/keyring.py:155-156` : `delete()` avale toute exception (`# nosec B110`) → logger avant d'avaler.
- `providers/dotenv.py:59` : pas de vérif permissions `.env` (warning si world-readable).
- `key.upper()` implicite (`env.py:51`, `dotenv.py:90`) → documenter la normalisation.

**Optimisation :**
- `chain.py` : extraire `_find(service, key) -> (provider, value)` ; `get`/`get_with_source` deviennent des wrappers (vérifier les asserts de logs avant — `get` log à chaque escalade, pas `get_with_source`).
- `keyring.py` : unifier les 3 blocs `import keyring` en un helper.
- `manager.py` : extraire `_require_store()` (aligné sur `_require_root()`).
- Logs d'escalade `chain` → `DEBUG` (verbeux + info-leak léger en INFO).

**Tests :** **manque le test anti-fuite central** → `assert secret not in repr(cred)` et absent des logs après `chain.get`/`require`.

---

## logging — NO-GO (sécurité : permissions fichier log)

**Revue — bloquants/majeurs :**
- 🔴 `file_logger.py:107` & `:150-158` : fichier log créé en `0o644` (umask), sans `O_NOFOLLOW` → lisible par tous + vuln symlink. Forcer `0o600`/`0o640` via `os.open(...O_NOFOLLOW, 0o600)`.
- `security_logger.py:91-101` : `details` sérialisé sans redaction → masquer clés sensibles (`password`,`token`,`secret`,`key`,`authorization`).
- `file_logger.py:101,124-125` : logger global par chemin → 2e instance ignore silencieusement sa config (`console_output`, `log_level`). Documenter ou nom unique.
- `tee_stream.py:70-79` : `__getattr__` délègue à `_original` → `close()` ne ferme jamais `_log_fh`. Définir `close()` explicite.
- `file_logger.py:98` : `getattr(logging, level)` accepte n'importe quoi → valider via set blanc.

**Optimisation :** `severity` → `StrEnum`/`Literal` ; moderniser typing ; remonter `import datetime` local ; supprimer `hasattr(self,'handler')` mort.

**Tests :** ajouter test de permissions (`os.stat`), test unitaire `TeeStream`, test `log_level` invalide.

---

## filesystem — NO-GO (sécurité : TOCTOU)

**Revue — bloquants/majeurs :**
- 🔴 `linux.py:37` : `open(path,'w')` sans `O_NOFOLLOW`/`fchmod` → pattern TOCTOU-safe projet non respecté.
- 🔴 `backup.py:65,94` : `exists()`→`copy2()` (suit symlinks) = TOCTOU sur source/dest.
- `backup.py:65` : `backup()` silencieux si source absente alors que docstring promet une sauvegarde → retourner `bool`/lever + documenter.
- `base.py` : ABC `FileManager` incomplète (`read_file`/`delete_file` implémentés mais non déclarés).
- `linux.py:41,77,97` : `except Exception` avalé → `False` masque la cause (préférer `OSError`).

**Note archi :** le helper TOCTOU-safe (`os.open O_NOFOLLOW` + `fchmod 0o644`) devrait vivre ici et être réutilisé par systemd/logging/dotconf.

---

## commands — Go conditionnel

**Revue — majeurs :**
- `runner.py:287-294` : anti-pattern `type("ProcResult",...)` (vestige migration Popen) → lire directement `_stdout/_stderr/_proc.returncode`.
- `runner.py:268-279` : `TimeoutExpired` dans `run()` ne `kill()` pas le process avant remontée (contrairement à `run_streaming`) → zombie possible.
- `runner.py:394-410` : deadlock stderr possible en streaming (buffer 64 Ko) → `stderr=STDOUT` ou drain concurrent, a minima documenter.
- Sécurité ✅ : pas de `shell=True`, argv liste, `# nosec` justifiés.

**Optimisation :**
- 🥇 Helper `_result(...)` (construction `CommandResult` dupliquée 6×, ~70 lignes).
- 🥈 Helper `_emit()` (motif log+console dupliqué 3×).
- `formatter.py` : Template Method `_decorate()` pour dédupliquer Plain/Ansi (préfixes, textes).
- `shlex.join` dans les logs ; `command: tuple[str,...]` pour vraie immutabilité.

**Tests :** nettoyage process sur timeout, `KeyboardInterrupt`, sortie console via `capsys`.

---

## network — Go conditionnel

**Revue — majeurs :**
- `repository.py:74` : écriture non atomique → `os.replace` + perms explicites.
- `repository.py:54` : `json.loads` sans `try/except JSONDecodeError`.
- `router.py:262` : validation SSRF accepte les hostnames sans résolution (DNS rebinding) → résoudre + vérifier contre `_LAN_NETWORKS`, ou rejeter les hostnames.
- `scanner.py:315` : `ET.fromstring` sur sortie nmap sans `try/except ParseError` (hostnames non fiables).
- `dhcp.py:119` : allocation IP O(n²).

**Optimisation :**
- 🥇 Extraire `network/vendors.py` : `_VENDOR_TYPES` + `_infer_type_from_vendor` dupliqués à l'identique router↔scanner (~40 lignes).
- 🥈 `dns.py` : `generate_dns_names` dupliqué + accès à `_generate_name` privé d'une autre classe → classe de base `_BaseDnsManager`.
- Centraliser `_ip_to_int`/`_int_to_ip`/`_next_available_ip` (router/dhcp/scanner).
- `router.py` (1084 l.) : scinder en `client.py` / `_nvram.py` / `scanner.py` / `dhcp.py` — **en dernier**, après les déduplications.
- Réduire `_parse_clients` (CC ~12) en helpers `_resolve_ip/_resolve_hostname/_resolve_fixed_ip`.
- `validators.py:22` : baser `validate_ipv4` sur `ipaddress` (cohérence + rigueur).

---

## scripts — Go conditionnel

**Revue — majeurs :**
- 🔴 `config.py:158` : valider `config.name` (regex anti-traversal) au point d'entrée — sinon `name="../../etc/cron.d/x"` en install system → écriture hors périmètre.
- 🔴 `installer.py:469-470` : wrapper écrit via `write_text` (suit symlink) avant le `fchmod O_NOFOLLOW` → `os.open(O_NOFOLLOW|O_EXCL)`.
- `installer.py:374-377` : `OSError` de `_write_wrapper` remonte au lieu de retourner `InstallReport(success=False)`.
- `installer.py` : incohérence wrapper (`APP_DIR/venv`) jamais peuplé par `uv tool install`.
- `checker.py:394-405` : `importlib.metadata` interroge le process courant, pas le venv cible → n'utiliser que si `venv_path is None`.
- `checker.py:302,316-317` : lignes > 79 col.

**Optimisation :**
- 🥇 Helpers `_fail_report`/`_success_report` (`InstallReport` construit 4-5×).
- 🥇 Helper `_run()` dans `checker.py` (motif `subprocess.run+check+log` 4×) ; `import json` en tête.
- 🥈 Décomposer `install()` (116 l.) : `_check_prerequisites`/`_handle_wrapper`/`_confirm_wrapper`.
- `_PYTHON_EXEC` dupliqué (installer/checker) → constante partagée.
- `timeout` sur tous les `subprocess.run`.

**Tests :** `_run_uv_install` (uv introuvable), branches `_is_installed`.

---

## dotconf — Go conditionnel

**Revue — majeurs :**
- `applier.py:93` : `content.splitlines()[0]` → `IndexError` si content vide. Garde `if not block.content.strip(): return None`.
- `conf_toml_exporter.py:50` : `read_text` sans `UnicodeDecodeError` (fichiers `/etc` legacy).
- `manager.py:82,104,152` : `open(...,'w')` configparser sans `chmod(0o644)` (incohérent avec applier).
- `conf_toml_exporter.py:81,112` : deux regex de section divergentes → `_SECTION_RE` unique.
- `line_editor.py:43` : sémantique « lignes non contiguës » de `is_block_present` à documenter.
- Sécurité ✅ : échappement TOML correct et testé.

**Optimisation :**
- 🥇 `line_editor.py` : extraire `_block_matches(content, section, predicate)` (`is_block_present`/`is_block_commented` quasi identiques).
- 🥇 `manager.py` : helpers `_load_parser`/`_save_parser`/`_parser_to_str` (pattern configparser répété 5×).
- `ensure_block` : extraire `_insert_block` (CC ~9) ; helper `_block_lines` (triplé).

---

## errors — Go conditionnel

**Revue — majeurs (paramètres injectés morts = viole SOLID projet) :**
- `console_handler.py:46` : `isinstance(error, ApplicationError)` en dur ignore `self.base_error_type` injecté.
- `console_handler.py:38,62-79` : `solutions` injecté jamais consulté (cascade `isinstance` codée en dur).
- `logger_handler.py:17-26` : `base_error_type` accepté mais jamais stocké ni utilisé.
- `console_handler.py:18` : fuite `FlatpakAutoUpdateError` (nom projet aval) dans une lib générique.

**Optimisation :** moderniser typing (`collections.abc.Callable`, `Callable[[],None]`) ; `-> None` manquants ; nettoyer `pass` redondants, `class X():`.

**Tests :** injecter `base_error_type`/`solutions` → révèle les params morts.

---

## validation — Go conditionnel

**Revue :**
- 🟠 `path_checker_Exist.py` : nom de module non PEP 8 → renommer `path_checker_exist.py` + MAJ `__init__.py:4`.
- `path_checker_world_writable.py:38-42` : `exists()`→`stat()` (suit symlink) sur un check de sécurité → `os.lstat`/`O_NOFOLLOW`.
- `path_checker_permission.py:56` : `os.access()` TOCTOU/ne reflète pas ACL → préventif uniquement.
- ✅ `.resolve()` anti-traversal présent sur les 3 checkers.
- Typing `Union` → `str | Path`. API asymétrique (`list[str]` vs `Union[str,Path]`).

---

## notification — Go conditionnel

**Revue :**
- 🟠 `config.py:53-64` : `to_bash_function()` génère du shell ; `title`/`message` validés « non vides » seulement → interdire `\n`/contrôle dans `__post_init__` (cohérent avec fix ConfTomlExporter). Bon point : `to_bash_call_*` utilise `shlex.quote()`.
- `config.py:102` : `"Flatpak"` codé en dur dans un module générique → attribut.

**Tests :** cas d'échappement adverse (`title='a"; rm -rf /'`).

---

## identity — Go conditionnel

**Revue :**
- ✅ Sécurité injection : `CommandBuilder` → argv sans `shell`.
- 🟡 `user.py`/`group.py` : valider format `name`/`group_name` (regex de `systemd/validators.py`) ou séparateur `--` (sinon nom interprété comme option par `useradd`).
- `user.py:80` `ensure_user_groups` : best-effort silencieux si tous groupes absents → documenter.

---

## integrity — GO

**Revue :** ✅ toutes dimensions. Mineurs : `verify()` retourne `True` si source vide (signaler 0 fichier) ; whitelist d'algos (MD5/SHA1 via `getattr`) ; typing `Union` → `str | Path`.

**Optimisation :** découper `verify()` (l.99-167) en `_resolve_dest` + `_verify_tree` (CC ~8→<5) ; statuer sur `calculate_checksum` statique (redondant, viole DIP injecté).

---

## cli — GO

**Revue :** ✅ toutes dimensions. Command Pattern propre, couverture exemplaire. Mineur : `register(subparsers: Any)` documenté.

---

## Séquencement recommandé

1. **Vague sécurité (bloquants)** : credentials repr, config TOML, systemd `\n`+TOCTOU, logging perms, filesystem TOCTOU. → un helper TOCTOU-safe central dans `filesystem/` d'abord.
2. **Quick wins optimisation** (zéro risque, gros gain lignes) : code mort `config/loader`, helpers `_result`/`_fail_report`, `vendors.py`, `_block_matches`.
3. **Refactorings structurels** : mixins systemd, scission `base.py`/`router.py`.
4. **Paramètres morts errors** + renommage `path_checker_Exist.py`.

> Prérequis avant tout refactoring : `make test` vert + couverture confirmée
> sur les chemins d'erreur (timeout, exceptions, branches `_is_installed`).
> Règle projet : zéro code avant validation explicite de ce plan.
