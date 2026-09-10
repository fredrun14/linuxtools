# Note de Besoin — Secrets multi-services dans le pipeline deploy
> **Date :** 2026-09-10
> **Statut :** Validé

---

## Le problème
`SecretsProvisioner.provision()` (`linuxtools/deploy/secrets_provisioner.py`)
résout toutes les clés d'une `SecretsSpec` via un seul `CredentialManager`
injecté au constructeur — `SecretsSpec.service` (un champ unique pour toute
la spec) n'est en réalité jamais lu, c'est du code mort. Ça bloque le
déploiement réel de `webapitools/pihole-schedule` : sa `SecretsSpec` mélange
des clés `PIHOLE_*_APP_PASSWORD` (service `pihole`) et
`GOTIFY_PIHOLE_SCHEDULE_TOKEN` (stocké délibérément sous service `gotify`
dans KeePassXC). `webapitools/cli.py:_cmd_deploy` ne construit qu'un seul
`CredentialManager(service=tool.credential_service)` pour toute la commande
`deploy`, donc la résolution du token Gotify échoue
(`CredentialNotFoundError`, cherché sous `pihole` au lieu de `gotify`).
Découvert au 8e essai du chantier de déploiement (2026-09-10), une fois tous
les bugs précédents (SSH, cycle de dépendance, mkdir parent) corrigés — la
phase `config` passe désormais, nouvel échec en phase `secrets`.

## Le résultat attendu
Un outil déployable dont les secrets viennent de plusieurs services
`CredentialManager` distincts (comme `pihole-schedule`, qui a besoin de
`pihole` et `gotify`) doit pouvoir les déclarer et les voir résolus
correctement par `SecretsProvisioner`, sans contournement côté appelant.

## Pour qui
`webapitools` (déploiement de `pihole-schedule`) au premier chef, et tout
futur outil déployable enregistré dans `linuxtools.deploy` qui aurait le
même besoin — `SecretsSpec`/`SecretsProvisioner` sont conçus comme une
primitive partagée, pas un point d'appel unique.

## Pourquoi maintenant
Bloque la reprise du chantier de déploiement réel de
`webapitools/pihole-schedule` (code livré depuis le 2026-08-05, jamais
déployé) — c'est le dernier obstacle identifié avant les étapes 7-8 du
chantier (vérification sur le nœud, déclenchement manuel).

## Critère de succès
C'est réussi si `webapitools deploy pihole-schedule --apply` provisionne
avec succès les trois secrets (2× `PIHOLE_*_APP_PASSWORD` sous `pihole`,
1× `GOTIFY_PIHOLE_SCHEDULE_TOKEN` sous `gotify`) sur le nœud cible.

## Ce que ce n'est PAS
- Ne change pas la commande locale `pihole schedule apply`
  (`webapitools/cli.py:269-270`), déjà correcte avec ses deux managers
  explicites.
- Ne déplace pas le token Gotify vers le service `pihole` dans KeePassXC
  pour contourner le problème — le stockage sous `gotify` est délibéré
  (cohérent avec les autres outils qui notifient via Gotify).
- Ne relance pas le chantier de déploiement lui-même — suite immédiate mais
  hors périmètre de ce besoin, une fois le correctif livré et taggé.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
