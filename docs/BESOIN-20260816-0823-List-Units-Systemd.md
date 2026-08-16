# Note de Besoin — `list_units()` générique dans `systemd`
> **Date :** 2026-08-16
> **Statut :** À valider

---

## Le problème

`linuxtools.systemd` sait lister les timers (`list_timers()`, via
`_TimerOperationsMixin`, `systemctl list-timers --output=json` avec
fallback texte) mais n'a aucun équivalent générique pour lister les
unités systemd quel que soit leur type (services, sockets, mounts,
etc.). L'API du module est asymétrique : on peut introspecter les
timers installés, pas le reste. Ce n'est pas un blocage vécu par un
consommateur aujourd'hui — c'est une incomplétude d'API relevée en
revue le 2026-07-23 et laissée en `📋 À faire`.

## Le résultat attendu

`UnitManager`/`UserUnitManager` exposent une méthode `list_units()`
qui retourne l'état des unités systemd installées, côté système et
utilisateur, sur le même modèle que `list_timers()` (structure de
retour cohérente, dégradation propre si `systemctl` ne supporte pas
`--output=json`).

## Pour qui

Fred, en local — usage direct (introspection/diagnostic) et usage
futur par d'éventurs consommateurs de `linuxtools.systemd` qui
voudraient un jour lister leurs unités sans écrire leur propre appel
`systemctl list-units`.

## Pourquoi maintenant

Aucun déclencheur concret : confirmé avec l'utilisateur, c'est de la
complétude d'API (symétrie avec `list_timers()`), pas une réponse à un
besoin consommateur identifié. Reste en `📋 À faire` du hub depuis le
2026-07-23 sans avoir été retenu jusqu'ici — traité maintenant faute
d'un autre chantier prioritaire en attente sur `linuxtools`.

## Critère de succès

C'est réussi si `UnitManager`/`UserUnitManager` exposent `list_units()`
qui retourne l'état des unités systemd (au minimum nom, état
`active`/`inactive`, type), avec le même niveau de robustesse
(fallback texte) que `list_timers()`.

## Ce que ce n'est PAS

- Ce n'est **pas** un filtrage par type d'unité (`--type=service`) ni
  un système de requête avancé — juste l'équivalent générique de
  `list_timers()`, périmètre à préciser au CDC.
- Ce n'est **pas** l'ajout de nouveaux types d'unités gérés
  (`.socket`/`.path` — cf. item de backlog séparé) : `list_units()`
  liste ce que systemd rapporte, indépendamment de ce que
  `linuxtools.systemd` sait *créer*.
- Ce n'est **pas** motivé par un besoin consommateur précis — si un
  vrai besoin apparaît en cours de route, il vaut mieux le documenter
  ici plutôt que de le découvrir seulement au CDC.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
