# Conception — Bascule atomique du venv au déploiement
> **Date :** 2026-09-29
> **Statut :** Validé (2026-09-29) — hypothèses tranchées : réécriture des chemins (`rebase_verification`), pas de rebascule sur échec post-bascule, flags CLI `--atomic-swap`/`--keep-versions` retenus, dry-run statique.
> **Entrée :** CDC-20260929-Bascule-Atomique-Venv-Deploy.md (validé, Q-01..Q-04 tranchées)
> **Projet :** linuxtools 2.2.2 → 2.3.0 (mineure, opt-in)

## 1. Périmètre & impact

| Élément | Impact |
|---|---|
| `deploy/venv_release.py` | **Nouveau** : `VenvReleaser`, `ReleaseOutcome`, `select_versions_to_prune` |
| `deploy/models.py` | `DeployConfig.atomic_swap: bool = False`, `keep_versions: int = 2` (+ `__post_init__` : `ValueError` si < 1) ; `DeployPhase.ACTIVATE` (après `VERIFY`) ; `DeployReport.active_version` / `fallback_version: Path \| None = None` + `format_summary` |
| `deploy/verifier.py` | Nouvelle fonction pure `rebase_verification` |
| `deploy/deployer.py` | Branche `atomic_swap` (install/verify/activate délégués), dry-run, param `releaser` en **dernier** argument de `__init__` (les appels positionnels existants restent valides), `for_target` construit le releaser |
| `deploy/venv_installer.py` | `backup_venv` : échec fermé si `venv_path` est un lien (voir Sécurité) — `install()` réutilisé tel quel |
| `deploy/cli.py` | ✅ validé 2026-09-29 : flags `--atomic-swap` / `--keep-versions` sur `DeployCommand` |
| `deploy/__init__.py`, `linuxtools/__init__.py` | Export `VenvReleaser` |
| Compat. | Consommateurs sans `atomic_swap` : aucun changement de comportement. Python ≥ 3.11, coreutils GNU (`ln -sfn`, `mv -T`, `readlink`, `find -printf`) + `python3` (déjà requis pour `-m venv`) |
| Réemploi | `linuxtools.filesystem` est local-only (pas d'exécuteur) → non réutilisable ici. `VenvInstaller.install(version, src, recreate=True)` construit la version (aucun code de build nouveau) |

Disposition sur l'hôte : `<parent>/venvs/<name>-<YYYYmmdd-HHMMSS-ffffff>/` (versions), `<parent>/venvs/<name>-<ts>-legacy/` (ancien répertoire migré), `<parent>/<name>` → lien **absolu** vers la version active, lien temporaire `<parent>/.<name>.swap-<id>` (même répertoire, donc même FS : rename(2) atomique).

## 2. Modules & interfaces

```python
# venv_release.py
VerifyFn = Callable[[Path], tuple[CheckResult, ...]]

@dataclass(frozen=True)
class ReleaseOutcome:
    success: bool
    phase_reached: DeployPhase          # INSTALL | VERIFY | ACTIVATE | DONE
    checks: tuple[CheckResult, ...] = ()
    active_version: Path | None = None
    fallback_version: Path | None = None
    messages: tuple[str, ...] = ()

class VenvReleaser:
    def __init__(self, executor: CommandExecutor, installer: VenvInstaller,
                 logger: Logger | None = None) -> None: ...
    def release(self, venv_path: Path, source_dir: Path, verify: VerifyFn,
                keep_versions: int = 2) -> ReleaseOutcome: ...
    def activate(self, venv_path: Path, version_path: Path) -> Path | None: ...
        # DeployError ; retourne la cible précédente. Sert aussi de rollback (F-05/F-11)
    @staticmethod
    def planned_steps(venv_path: Path, source_dir: Path,
                      keep_versions: int) -> tuple[str, ...]: ...

def select_versions_to_prune(version_ids: Sequence[str], active_id: str,
                             previous_id: str | None, keep: int) -> tuple[str, ...]: ...

# verifier.py
def rebase_verification(spec: VerificationSpec, cli_bin: str | None, venv_path: Path,
                        version_path: Path) -> tuple[VerificationSpec, str | None]: ...
```

**Ce que l'appelant de `release()` doit savoir** : `venv_path` absolu, `verify` reçoit le chemin de la version à tester, aucune exception (tout passe par `ReleaseOutcome`), le venv actif n'est touché que si `success` ou `phase_reached == ACTIVATE` avec `success=False`, et dans ce dernier cas le lien reste inchangé.

**Séquence de `release()`** :
1. Validation pure des chemins.
2. `readlink venv_path` : lien, sinon `test -d` (legacy), sinon `test -e` (autre → refus), sinon absent. Un lien hors `venvs/<name>-*` est refusé avant tout build.
   > **Avenant 2026-09-30 (F16, revue `revueur-code` passe 3, No-Go)** : cette
   > chaîne suppose que l'échec de `readlink` signifie « ce n'est pas un
   > lien ». Or `test -d`/`test -e` suivent les liens symboliques : un
   > `readlink` en échec **ambigu** (`return_code` ∉ {0, 1} — ex. coupure SSH
   > transitoire, code 255) alors que `venv_path` est toujours un lien géré
   > fait retomber sur `test -d`/`test -e`, qui réussissent quand même (ils
   > suivent le lien) et classent à tort l'état en `"dir"` (migration
   > destructrice sur un lien actif) ou `"other"`/`"absent"` (perte de la
   > protection de `previous_id`). **Correctif retenu** : `return_code == 1`
   > sur `readlink` signifie que la commande s'est exécutée et confirme que
   > `venv_path` n'est pas/plus un lien — seul ce cas autorise la suite de la
   > chaîne (`test -d`, puis `test -e`). Tout autre `return_code` est un état
   > **indéterminé** : `_current_state` ne tente pas `test -d`/`test -e` et
   > signale l'indétermination ; l'appelant (`activate()`/`release()`) refuse
   > par `DeployError` plutôt que de deviner — même posture que le correctif
   > F10 sur `_discard()`.
3. `test -L venvs` → refus ; puis `mkdir -p venvs`.
4. `installer.install(version, src, recreate=True)`.
5. `verify(version)`.
6. Échec en 4 ou 5 → `rm -rf -- version` après garde-fou, résultat `INSTALL`/`VERIFY`, venv actif intact, aucun rollback (F-02).
7. `activate()`.
8. Purge best-effort, après avoir relu le lien.

**Séquence de `activate()`** :
- Lien ou absent : `ln -sfn <version> <tmp>` puis `mv -T <tmp> <venv_path>` ; en cas d'échec, `rm -f <tmp>` puis `DeployError`.
- Répertoire réel (migration F-04) : `ln -sfn` puis **un seul** processus `<version>/bin/python -I -c <SCRIPT constant> <venv_path> <legacy> <tmp>`. Le script fait `rename(venv, legacy)` puis `rename(tmp, venv)`. Si le second échoue, il fait `rename(legacy, venv)` et sort en code non nul. Justification : via SSH, deux `run()` = deux connexions ssh → fenêtre de 0,1 à 1 s au lieu de ~µs.

**Cohérence legacy** : les shebangs du legacy visent `venv_path/bin/python`. Python repère `pyvenv.cfg` sans résoudre le lien, donc `sys.prefix = venv_path`. Quand le lien vise le legacy (rollback), tout résout dans le legacy : c'est cohérent. Quand le lien vise une autre version, les scripts du legacy tourneraient sur l'autre version, mais personne ne les appelle directement. En revanche, **le legacy ne peut pas être vérifié via son chemin réel** : on ne peut le vérifier qu'une fois le lien rebasculé sur lui. À documenter dans la docstring d'`activate`.

**Grille modules profonds — où placer le seam :**

| Critère | `VenvReleaser` (nouveau module) | Extension de `VenvInstaller` |
|---|---|---|
| Test de suppression | Supprimé → machine à 3 états, garde-fous, migration, purge réapparaissent dans `Deployer` et dans la future CLI F-11 → **il gagne sa place** | — |
| Levier | 1 méthode principale : build + gating + discard + migration + bascule + purge | 4 → 8 méthodes publiques, deux cycles de vie mélangés (copie en place / lien versionné), ordre d'appel imposé à `Deployer` → fuite |
| Fuite d'implémentation | Aucune : disposition, ids, lien tmp internes | L'appelant séquence stage/activate/prune |
| Surface de test | Tout via `release()`/`activate()` sur `CommandExecutor` mocké ; `VenvInstaller` **réel** injecté (pas de seam supplémentaire) | — |
| Seam | Réutilise le seam existant `CommandExecutor` ; aucun `Protocol` | — |
| Évolution Q-01 | Quand `atomic_swap` deviendra le défaut, retirer le mode en place = supprimer `backup/restore/prune_backup` sans toucher au releaser | Retrait chirurgical dans une classe mixte |

→ **Nouveau module.** Les deux fonctions pures (`select_versions_to_prune`, `rebase_verification`) ont chacune leur interface propre (entrées → sorties, beaucoup de cas limites) et sont testées directement. Elles sont publiques dans leur module mais non exportées par le paquet, sauf `VenvReleaser`.

## 3. SOLID par responsabilité

| Classe/module | S | O | L | I | D |
|---|---|---|---|---|---|
| `VenvReleaser` | Cycle de vie des versions de venv sur l'hôte | Pas d'abstraction — une seule implémentation | N/A | 3 méthodes publiques, `activate` réutilisée pour le rollback | `CommandExecutor`, `VenvInstaller`, `Logger` injectés |
| `select_versions_to_prune` | Politique de rétention (pure) | N/A | N/A | Ids → ids | Aucune |
| `rebase_verification` | Redirection des chemins de vérification (pure) | N/A | N/A | Spec → spec | Aucune |
| `Deployer` | Ordre des phases (inchangé) | Branche `if config.atomic_swap` : pas de `Protocol` de stratégie, le mode en place est transitoire (Q-01) | N/A | Un param optionnel de plus | `releaser` injecté ; `None` + `atomic_swap` → rapport d'échec propre (même motif que config/secrets/timer) |
| `VenvInstaller` | Inchangée (+ refus du lien) | — | — | — | Inchangé |

## 4. Choix de bibliothèques

| Besoin | Retenu | Écarté | Raison |
|---|---|---|---|
| Bascule en régime établi | `ln -sfn` + `mv -T` (coreutils) | `os.replace` local | Doit passer par l'exécuteur (local/SSH) ; décidé au CDC |
| Migration (2 renames) | `python -I -c` constant, chemins en argv | 2 × `mv -T` ; `sh -c` | Fenêtre SSH ; pas de shell (script constant, `-I` isole de l'environnement) |
| Listage des versions | `find <venvs> -mindepth 1 -maxdepth 1 -type d -printf '%f\n'` | `ls` | `-type d` ignore les liens, sortie stable |
| Nouvelle dépendance | Aucune | — | CDC §6 |

## 5. Décisions structurantes

- 📌 À consigner en ADR : bascule par lien symbolique absolu + versions nommées `<name>-<ts>` sous `<parent>/venvs/`, opt-in `atomic_swap` (Q-01..Q-04).
- 📌 À consigner en ADR : nouveau module `VenvReleaser` plutôt qu'une extension de `VenvInstaller` ; pas de `Protocol` de stratégie (mode en place transitoire).
- 📌 À consigner en ADR : migration en un seul processus distant `python -I -c` (dérogation « coreutils seuls » justifiée par la latence SSH), avec compensation.
- 📌 À consigner en ADR : `rebase_verification` (réécriture des chemins sous `venv_path`) plutôt qu'un rejet — ✅ validé 2026-09-29.
- 📌 À consigner en ADR : pas de verrou de concurrence ; purge sûre par construction (§6/§7).

Emplacement : `/home/fred/obsidian-perso/fredvault/1-projets/linuxtools/adr/`.

## 6. Sécurité

CDC §7 : réseau interne, `rm -rf` sur l'hôte, entrées de config → section obligatoire (A04 Insecure Design).

| Menace / surface | Frontière de confiance | Contrôle retenu | Module porteur |
|---|---|---|---|
| `rm -rf` hors du répertoire des versions (`venv_path` relatif, avec `..`, parent `/`) | Config consommateur → commande sur l'hôte | Validation pure **avant toute commande** : absolu, normalisé, parent ≠ `/`, nom non vide → `DeployError` | `VenvReleaser` |
| Purge de la version active, de la cible du lien ou d'un autre outil partageant le parent | État FS de l'hôte | Ids namespacés `<name>-<ts>[-legacy]`, regex `re.escape(name)` ; chemin **reconstruit en Python** `venvs / id` (jamais depuis la sortie brute) ; `readlink` relu juste avant purge ; jamais active, précédente ou id ≥ active | `select_versions_to_prune`, `VenvReleaser` |
| `venv_path` = lien vers une cible non gérée, ou fichier | FS de l'hôte | Échec fermé avant build | `VenvReleaser` |
| `venvs/` est un lien (redirection de la purge) | FS de l'hôte | `test -L` → refus | `VenvReleaser` |
| Injection via les chemins | Config → `SshCommandExecutor` | argv uniquement, script python constant, `rm -rf --` (quoting `shlex.join` existant côté SSH) | tous |
| Retour au mode en place sur un `venv_path` lien : `cp -a` copie le lien, `pip` modifie la version active | Config consommateur | `backup_venv` : `test -L` → `DeployError` | `VenvInstaller` |
| Migration interrompue → `venv_path` absent | Hôte | Compensation dans le même processus + message explicite | `VenvReleaser` |
| Traçabilité | — | Logs : version construite, migration, bascule `A → B`, purge, discard | `VenvReleaser` |

📌 À consigner en ADR : la validation des chemins se fait en Python avant toute commande (lieu de validation unique).

## 7. Risques & points ouverts

- **Faux vert de vérification** : `cli_bin` absolu (backup-py-manager) et `regression_command` en `{venv_path}/bin/…` (nas-diy-tools, nas-diy-update) viseraient le venv actif. `rebase_verification` est obligatoire, sinon rejet (✅ validé 2026-09-29).
- **F-05 sans déclencheur** : aujourd'hui seuls INSTALL/VERIFY déclenchent un rollback, et ils ont lieu avant la bascule ; CONFIG/SECRETS/TIMER n'en déclenchent aucun. En mode atomique, `rolled_back` reste toujours `False` et le rollback = `activate(fallback_version)` (primitive testée, sans appel dans `Deployer`). ✅ validé 2026-09-29 : ne pas rebasculer sur un échec post-bascule (comportement actuel conservé).
- **Concurrence** : webapitools déploie ses groupes **à la suite** dans le même processus, donc aucune concurrence. Mais 5 groupes = 5 builds, et avec N=2 la version de repli est celle du groupe précédent (même code). Il faudrait construire une seule fois côté consommateur (hors périmètre, à signaler au bump). Deux processus parallèles : pas de verrou (un `flock` ne survit pas entre deux `run()` SSH ; un verrou `mkdir` laisse des verrous orphelins après crash). Le dernier `mv -T` gagne, la purge ne touche jamais une version ≥ active, et le `fallback_version` rapporté peut être inexact : accepté, hors périmètre.
- **Processus longs** : une version est figée par son shebang absolu. Un démon lancé il y a deux déploiements peut voir sa version purgée (N=2). Faible pour des timers oneshot, à documenter.
- `recreate_venv=True` + `atomic_swap` : ignoré avec un message dans le rapport (Q-03), pas de `ValueError` (webapitools le passe à `True`).
- Hypothèse `sys.prefix` non résolu (cohérence legacy) : à confirmer par test d'intégration réel.
- Durée : chaque déploiement = build complet (équivalent à `recreate_venv=True`) ; le `cp -a` disparaît. Disque : N versions + 1 build en cours.
- Dry-run statique (aucune commande distante, comme aujourd'hui) : la migration apparaît en « si `venv_path` est un répertoire réel » (✅ validé 2026-09-29).

## 8. Impact sur le plan

| # | Tâche | Tags |
|---|---|---|
| 1 | `models` : `atomic_swap`, `keep_versions` + validation, `DeployPhase.ACTIVATE`, `active_version`/`fallback_version` + `format_summary` | [TDD] |
| 2 | Validation pure des chemins + format/regex des ids namespacés | [TDD] [SEC] |
| 3 | `select_versions_to_prune` (active, précédente, id ≥ active, legacy le plus ancien, ids étrangers ignorés, N=1) | [TDD] [SEC] |
| 4 | `rebase_verification` (cli_bin relatif/absolu, regression_command, chemins hors venv inchangés) | [TDD] |
| 5 | `VenvReleaser.activate` : lien / absent / legacy (processus unique + compensation) / lien non géré / fichier / nettoyage du tmp | [TDD] [SEC] |
| 6 | `VenvReleaser.release` : build via `VenvInstaller` réel sur exécuteur mocké, gating de verify, discard gardé, purge best-effort avec relecture du lien, `test -L venvs` | [TDD] [SEC] |
| 7 | `planned_steps` + branche dry-run de `Deployer` | [TDD] |
| 8 | Branche `atomic_swap` de `Deployer` (+ `releaser` None, `recreate_venv` ignoré, rapport), `for_target` | [TDD] |
| 9 | `backup_venv` refuse un `venv_path` lien | [TDD] [SEC] |
| 10 | Parité SSH : `SshCommandExecutor` sur local mocké (quoting du `-c` et des argv) (F-09) | [TDD] |
| 11 | Test d'intégration `tmp_path` réel : `activate`/purge/migration, `python3 -m venv` sans pip, `sys.prefix` via le lien | — |
| 12 | `DeployCommand` : `--atomic-swap` / `--keep-versions` (si validé) | [TDD] |
| 13 | Exports, docstrings, README deploy, CHANGELOG, 2.2.2 → 2.3.0, ADR (§5) | — |
| 14 | Recette manuelle : boucle `<venv_path>/bin/<cli> --help` pendant un déploiement réel (critère CDC §8), après le bump d'un consommateur | — |

Gates : `mypy --strict` 0, couverture ≥ 80 % sur `venv_release.py`, `deployer.py`, `verifier.py`, `models.py`, Bandit < MEDIUM.
