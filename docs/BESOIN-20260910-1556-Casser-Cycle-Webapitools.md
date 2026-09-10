# Note de Besoin — Casser le cycle de dépendance vers webapitools
> **Date :** 2026-09-10
> **Statut :** À valider

---

## Le problème

`linuxtools` déclare `webapitools` comme dépendance **de base**
(`[project.dependencies]`, pas un extra), alors que seuls 4 fichiers isolés
(`network/router/*.py`, `updates/checker.py`) en ont réellement besoin.
Résultat : n'importe quel consommateur qui ne demande qu'un extra sans
rapport (`linuxtools[credentials]`, le cas de `webapitools` lui-même)
hérite quand même de cette dépendance — ce qui crée un cycle insoluble par
`pip` dès que `webapitools` s'installe depuis sa propre source non taguée.
C'est ce qui bloque aujourd'hui le déploiement réel de `pihole-schedule`
sur un hôte distant (`ResolutionImpossible`).

## Le résultat attendu

Installer `linuxtools[credentials]` (ou tout autre extra sans rapport avec
le réseau) sur une machine qui n'a pas déjà `webapitools` en local ne doit
plus jamais tenter de résoudre `webapitools`. Un `pip install` nu, sur un
hôte distant quelconque, doit pouvoir installer `linuxtools[credentials]`
seul.

## Pour qui

Tout projet homelab qui consomme `linuxtools` sans avoir besoin du module
réseau ASUS ni du vérificateur de mise à jour — au premier chef
`webapitools` lui-même (déploiement distant), potentiellement d'autres
consommateurs futurs.

## Pourquoi maintenant

Bloque le chantier de déploiement réel de `webapitools/pihole-schedule`
(2026-09-10) — code livré depuis le 2026-08-05, jamais déployé, désormais
prêt côté `webapitools` (tag `linuxtools` épinglé, PR #17 mergée) mais
arrêté par ce cycle côté `linuxtools`. Un ADR du 2026-09-05
(`ADR-20260905-uv-sources-consommateur-externe`) avait déjà repéré ce cycle
pour un symptôme différent et explicitement mis de côté sa résolution
complète comme « structurant, nécessiterait son propre CDC ».

## Critère de succès

C'est réussi si `pip install "linuxtools[credentials] @
git+https://git.ricfasohel.fr/fred/linuxtools.git@<nouveau-tag>"`, lancé
depuis une machine sans `webapitools` ni dépôt frère local, s'installe sans
tenter de résoudre `webapitools`.

## Ce que ce n'est PAS

- Ne retire pas le lien fonctionnel `network/router` ↔ `AsusRouterClient`
  ni `updates/checker` ↔ `ForgejoClient` — ces usages restent, seulement
  rendus optionnels à l'installation.
- Ne rapatrie pas `AsusRouterClient`/`ForgejoClient` dans `linuxtools`
  (option envisagée et écartée dans la conversation : reviendrait sur la
  décision actée le 2026-08-14 de garder `linuxtools` sans dépendance
  tierce lourde — cf. `CDC-20260814-0720-Client-Routeur-Asus.md`,
  webapitools).
- Ne re-pointe pas `webapitools/pyproject.toml` vers le nouveau tag
  `linuxtools` — évolution séparée, côté `webapitools`, une fois ce besoin
  livré et taggé ici.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
