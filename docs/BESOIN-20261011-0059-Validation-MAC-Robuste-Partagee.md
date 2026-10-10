# Note de Besoin — Validation MAC robuste et partagée

> **Date :** 2026-10-11
> **Statut :** À valider

---

## Le problème
`webapitools` possède sa propre fonction `normalize_mac` (dans
`apps/_shared.py`) qui valide et normalise une adresse MAC, alors que
`linuxtools.network.validators` expose déjà `validate_mac`. Deux
implémentations divergentes de la même règle vivent donc en parallèle. Pire,
celle de `linuxtools` a un défaut de robustesse : sa regex se termine par `$`,
qui accepte un saut de ligne final — `validate_mac("aa:bb:cc:dd:ee:ff\n")`
réussit et renvoie la chaîne avec le `\n`. Une MAC lue depuis un fichier TOML
pourrait passer la validation avec un caractère parasite. Le même défaut touche
`validate_cidr` et `validate_hostname` (même motif `$`).

## Le résultat attendu
Une seule règle de validation MAC, fiable, hébergée dans `linuxtools` et
réutilisable par tous les projets. `webapitools` n'a plus sa propre regex : sa
`normalize_mac` s'appuie sur `linuxtools`. La validation rejette désormais toute
entrée mal formée, saut de ligne parasite compris. `validate_mac` peut renvoyer
la MAC en minuscules (défaut, inchangé pour les appelants actuels) ou en
majuscules à la demande — la casse attendue par `webapitools`.

## Pour qui
Moi, en local. Développement des outils homelab Python (`linuxtools` comme
socle partagé, `webapitools` comme premier consommateur).

## Pourquoi maintenant
Tâche « À faire » inscrite au hub `webapitools` : dédupliquer `normalize_mac`
vers `linuxtools.validate_mac`. En l'instruisant, le défaut `\n` de la
validation `linuxtools` est apparu — à corriger avant de s'appuyer dessus.

## Critère de succès
C'est réussi si `webapitools.normalize_mac` délègue à `linuxtools`, qu'aucune
regex MAC ne subsiste côté `webapitools`, et qu'une MAC suivie d'un `\n` est
rejetée par `validate_mac` (test de non-régression à l'appui).

## Ce que ce n'est PAS
- **Pas** l'ajout d'un `validate_ipv6` ni l'enrichissement de `validate_hostname`
  (reportés à un besoin dédié).
- **Pas** un changement de comportement par défaut de `validate_mac` : les
  appelants actuels (`network/models.py`) continuent de recevoir des minuscules.
- **Pas** une refonte de l'API de validation réseau — on corrige et on mutualise
  l'existant, sans nouveau module.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
