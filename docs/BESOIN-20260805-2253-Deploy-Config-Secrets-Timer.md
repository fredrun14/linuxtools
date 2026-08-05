# Note de Besoin — Deploy Config Secrets Timer
> **Date :** 2026-08-05
> **Statut :** À valider

---

## Le problème
`Deployer` (module `deploy` de `linuxtools`) livre aujourd'hui le code d'un
outil (transport → venv → verify → rollback) sur une cible locale ou SSH,
mais s'arrête là. Pour qu'un service planifié tourne réellement, il faut
ensuite déposer sa config TOML, ses secrets et installer/activer son
service+timer systemd — une suite d'étapes manuelles, refaites à chaque
projet consommateur, comme le montre le pattern déjà en place
(`borg-passphrase`/`notifications.env` sur `backup-tank-data`) que
`webapitools` (pihole-schedule) s'apprête à reproduire via un chantier
infra séparé.

## Le résultat attendu
Un seul appel `deployer.deploy(config)` qui, en plus du code, provisionne
si demandé : la config TOML, les secrets (injectés dans l'unité systemd via
`Environment=`/`EnvironmentFile=`, jamais via le rsync du source), et le
service+timer systemd — sur la cible locale ou SSH déjà résolue par
`Deployer`. Chaque phase reste optionnelle (no-op si non configurée), sur
le modèle des collaborateurs déjà injectés (`Transport`, `VenvInstaller`,
`InstallVerifier`).

## Pour qui
Les projets consommateurs de `linuxtools` qui déploient un service
planifié : `backup-py-manager`, `webapitools` (pihole-schedule),
`fedora_post_install` — en remplacement de l'étape manuelle actuellement
réalisée via un chantier infra séparé (`nas-plan-chantier`) pour chaque
déploiement.

## Pourquoi maintenant
`webapitools` vient de finaliser le code de `pihole-schedule`
(2026-08-05) ; son déploiement (unités systemd, fichier de secrets sur le
nœud) est la prochaine étape et referait à la main exactement ce que
`backup-tank-data` a déjà fait pour `pihole-dns`. C'est l'occasion
concrète de généraliser ce provisioning dans `linuxtools` plutôt que de le
refaire manuellement une troisième fois.

## Critère de succès
Un déploiement configuré avec config+secrets+timer livre, en un seul appel
`deploy()`, un service systemd opérationnel sur une cible fraîche (locale
ou SSH), sans intervention manuelle supplémentaire après coup.

## Ce que ce n'est PAS
- Ne génère pas le contenu métier du TOML applicatif — celui-ci reste
  fourni par l'appelant.
- Ne remplace pas `nas-plan-chantier` pour les décisions d'infra (quel
  nœud, quelle topologie, quels domaines à bloquer) — seulement
  l'exécution mécanique du dépôt sur une cible déjà décidée.
- Ne couvre pas la rotation ou la génération des secrets eux-mêmes (reste
  le rôle de `CredentialManager`/keyring en amont) — seulement leur
  provisioning vers l'unité systemd cible.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
