# Note de Besoin — Timer Scope Utilisateur
> **Date :** 2026-08-07
> **Statut :** À valider

---

## Le problème

`TimerDeployer` (module `linuxtools.deploy`) installe le service+timer
systemd exclusivement en mode **système** (`/etc/systemd/system/`, via
`SystemdExecutor`/`LinuxServiceUnitManager`/`LinuxTimerUnitManager`), ce
qui nécessite root. Un outil personnel non-privilégié (ex.
`backup-py-manager`, qui sauvegarde le home de son propre utilisateur)
n'a aucune raison de tourner en root — et le déploiement échoue
purement et simplement sur un poste desktop où l'utilisateur n'a pas
de session root interactive. Constaté en conditions réelles :
`Permission refusée pour écrire
/etc/systemd/system/backup-py-manager-home.service. Exécution en tant
que root requise.`

## Le résultat attendu

`linuxtools.deploy` doit pouvoir installer un `TimerDeploySpec` soit en
mode **système** (comportement actuel, inchangé — nécessaire pour les
serveurs : timers qui doivent survivre à un déconnexion utilisateur,
cibles SSH administrées en root), soit en mode **utilisateur**
(`systemctl --user`, `~/.config/systemd/user/`, sans sudo ni root). Les
deux modes coexistent et sont sélectionnables par l'appelant — aucun
des deux ne remplace l'autre. Les briques bas niveau existent déjà côté
`linuxtools.systemd` (`UserSystemdExecutor`,
`LinuxUserServiceUnitManager`, `LinuxUserTimerUnitManager`) mais ne sont
jamais mobilisées par le module `deploy`.

## Pour qui

Les consommateurs de `linuxtools.deploy` qui déploient un outil
personnel non-privilégié sur poste desktop (cas immédiat :
`backup-py-manager deploy --profile home` sur Fedora local) **et** ceux
qui déploient sur serveur en mode système (cas déjà couvert, à ne pas
casser).

## Pourquoi maintenant

Bloquant réel rencontré à l'instant lors du premier déploiement réel de
`backup-py-manager deploy` sur poste Fedora : la phase `TIMER` échoue
systématiquement en local, sans contournement possible autre que
`sudo` (rejeté — un backup du home ne doit pas s'exécuter en root).

## Critère de succès

C'est réussi si un `Deployer.deploy(config)` avec un `TimerDeploySpec`
en scope utilisateur installe et active un timer via `systemctl --user`
sans aucune élévation de privilèges, et qu'un `TimerDeploySpec` en scope
système continue de fonctionner exactement comme aujourd'hui (aucune
régression sur les consommateurs existants).

## Ce que ce n'est PAS

- L'option CLI côté `backup-py-manager deploy` pour choisir le scope —
  évolution séparée, dans `backup-py-manager` une fois ce besoin livré
  côté `linuxtools`.
- Le support SSH multi-utilisateur avancé (lingering systemd pour les
  timers `--user` qui doivent survivre à une déconnexion sur cible
  distante) — hors périmètre sauf si le CDC en décide autrement.
- Toute modification de `ConfigDeployer`/`SecretsProvisioner` — seul
  `TimerDeployer`/`TimerDeploySpec` sont concernés.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
