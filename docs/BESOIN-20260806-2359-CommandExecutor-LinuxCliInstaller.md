# Note de Besoin — CommandExecutor pour LinuxCliInstaller
> **Date :** 2026-08-06
> **Statut :** À valider

---

## Le problème
`LinuxCliInstaller` (`linuxtools.scripts.installer`) déploie un CLI Python via
`uv tool install`, mais uniquement en local : `_run_uv_install()` appelle
`subprocess.run` en dur, sans passer par l'abstraction `CommandExecutor`
qu'utilise le reste de `linuxtools`. Il ne peut donc pas cibler un hôte
distant en SSH, alors que le module `deploy` (`VenvInstaller`) le peut déjà —
mais celui-ci réinstalle via `pip install --force-reinstall` dans un venv
géré à la main, pas via `uv`.

## Le résultat attendu
Pouvoir déployer un CLI Python via `uv tool install` aussi bien en local
qu'à distance (SSH), en injectant un `CommandExecutor` dans
`LinuxCliInstaller` comme c'est déjà fait pour `VenvInstaller`.

## Pour qui
Moi, pour les consommateurs de `linuxtools` qui déploient un CLI via
`uv tool install` — aujourd'hui `backup-py-manager install` en local,
potentiellement d'autres projets à distance ensuite.

## Pourquoi maintenant
Identifié en discutant du déploiement de `backup-py-manager` : deux
mécanismes de déploiement CLI coexistent dans `linuxtools`
(`LinuxCliInstaller`/`uv tool install` local-only, `Deployer`/`VenvInstaller`
pip+SSH avec rollback) et aucun ne cumule `uv tool install` + support
distant.

## Critère de succès
`LinuxCliInstaller.install()` peut déployer un CLI via `uv tool install` sur
une cible distante SSH, avec le même `CommandExecutor` injecté que le reste
de la bibliothèque.

## Ce que ce n'est PAS
- Pas de backup/rollback pour cette évolution — hors périmètre pour l'instant,
  contrairement à `VenvInstaller`.
- Pas de fusion avec le module `deploy` — les deux mécanismes restent
  séparés et coexistent, chacun avec son cas d'usage (`uv tool install` vs
  pip+venv géré).
- Pas de migration de `backup-py-manager install` vers un nouveau flux —
  seule l'API de `linuxtools` évolue ici.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
