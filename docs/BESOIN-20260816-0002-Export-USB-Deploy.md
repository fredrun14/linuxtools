# Note de Besoin — Export USB de déploiement (`usb-export`)
> **Date :** 2026-08-16
> **Statut :** À valider

---

## Le problème

`fedora_post_install` sait déjà préparer une clé USB permettant d'installer
l'outil sur une machine sans réseau (`UsbExportManager`, deux modes :
`sources` + `uv tool install`, ou `venv` autonome précompilé). Cette logique
est réutilisable — elle ne dépend d'aucune spécificité de
`fedora_post_install` — mais elle vit enfermée dans ce projet. Tout autre
outil déployé via `linuxtools.deploy` (le module de déploiement générique du
socle) doit aujourd'hui réimplémenter cette préparation de clé USB à la
main, ou en rester privé du besoin « déploiement offline ».

## Le résultat attendu

`linuxtools.deploy` expose une capacité générique de préparation de clé USB,
au même titre que le déploiement vers un hôte (transport → install →
vérification → rollback) qu'il sait déjà faire. Deux modes repris tels
quels dans leur principe : `sources` (copie des sources + `uv tool install`
sur la cible — mode **nominal**, réseau requis sur la cible) et `venv`
(venv Python autonome précompilé sur la clé — mode **secondaire**, aucun
réseau requis, réservé aux cibles sans accès PyPI). N'importe quel projet
consommateur de `linuxtools.deploy` (pas seulement `fedora_post_install`)
peut alors préparer une clé USB pour son propre outil sans dupliquer la
logique.

## Pour qui

Fred, en local — tout projet Python du socle homelab qui utilise
`linuxtools.deploy` et doit un jour être installé sur une machine sans
réseau fiable.

## Pourquoi maintenant

Le module `deploy` V1 (déploiement vers un hôte) est livré et stabilisé
(`discovery.py`, `venv_installer.py`, `content_writer.py` existent déjà) —
c'était le prérequis explicitement posé le 2026-07-19 pour cette migration.
`discovery.py` documente d'ailleurs déjà sa logique comme « inspirée
d'`UsbExportManager` » : le socle commun est prêt, il ne reste qu'à porter
la partie spécifique (copie sur clé, construction du venv autonome,
scripts `install.sh`/`run.sh`).

## Critère de succès

C'est réussi si un projet consommateur de `linuxtools.deploy` peut préparer
une clé USB bootable (mode `sources` ou `venv`) via l'API `deploy`, sans
écrire lui-même de logique de détection de source, de copie ou de script —
en réutilisant `discovery.py` et `content_writer.py` déjà en place.

## Ce que ce n'est PAS

- Ce n'est **pas** le refactor de `fedora_post_install` pour consommer
  cette nouvelle API et supprimer `UsbExportManager` — chantier séparé,
  plus tard, une fois cette capacité livrée et stabilisée dans `linuxtools`.
- Ce n'est **pas** un nouveau mode de déploiement (ex. Docker, image
  bootable complète) — seuls les deux modes déjà éprouvés (`sources`,
  `venv`) sont repris.
- Ce n'est **pas** une bascule complète de tout `deploy` vers `uv` (le
  pipeline hôte-distant garde `pip` dans le venv cible, PEP 668 oblige côté
  hôte) — seule la préparation de clé USB privilégie `uv tool install`
  quand c'est possible.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
