# Note de Besoin — Vérification Nouvelle Version
> **Date :** 2026-07-23
> **Statut :** À valider

---

## Le problème
`Deployer.deploy()` transporte et réinstalle systématiquement, sans savoir
si la cible a déjà la dernière version. On redéploie même quand rien n'a
changé, ce qui gaspille du temps et bruite les logs sur les cibles
distantes.

## Le résultat attendu
Pouvoir demander, avant ou indépendamment d'un déploiement, si une cible
(locale ou distante) tourne déjà avec la dernière version disponible en
source — en comparant le numéro de version du `pyproject.toml` source
local à celui effectivement installé dans le venv cible. Cette
vérification doit être utilisable en code (en amont de `deploy()`, pour
sauter un déploiement inutile) et en CLI (sous-commande dédiée pour
interroger l'état d'une cible sans déclencher de déploiement).

## Pour qui
Frederic, en local et sur ses cibles homelab (Forgejo, NAS DIY), pour ses
propres outils CLI déployés via `linuxtools.deploy`.

## Pourquoi maintenant
Le module `deploy` existe déjà et fonctionne, mais chaque appel
redéploie sans condition — le besoin de vérification émerge en usage
courant du module.

## Critère de succès
C'est réussi si on peut appeler une fonction qui renvoie, pour une cible
donnée, si elle est à jour ou non par rapport à la version source, avec
les deux numéros de version en clair.

## Ce que ce n'est PAS
- Pas de détection basée sur un hash git ou un checksum de fichiers —
  uniquement le numéro de version `pyproject.toml`.
- Pas de déclenchement automatique d'un déploiement si obsolète — la
  fonction informe, elle ne décide pas.
- Pas de gestion de plusieurs cibles en une seule commande (fan-out) —
  une cible à la fois, comme le reste du module `deploy`.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
