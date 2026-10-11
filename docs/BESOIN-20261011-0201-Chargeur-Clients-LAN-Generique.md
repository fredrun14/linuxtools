# Note de Besoin — Chargeur de clients LAN générique

> **Date :** 2026-10-11
> **Statut :** À valider

---

## Le problème

webapitools parse une liste déclarative de « clients LAN » (MAC + nom +
IP optionnelle, lus depuis un TOML) à trois endroits, avec trois bouts de
code qui se recouvrent : `pihole_dns._parse_clients` (enregistrement
complet : MAC, nom, IP, dédoublonnage MAC **et** nom), `pihole_schedule.
_parse_client_macs` (MAC seules + dédoublonnage) et la commande
`router apply` (qui réutilise déjà le loader de `pihole_dns`). Le même
travail universel — vérifier que chaque entrée est une table, valider et
normaliser la MAC, garantir l'unicité, construire des enregistrements
immuables — est réécrit ou détourné à chaque fois. `normalize_mac` a déjà
été remonté dans `linuxtools` ; la notion de « client LAN » elle-même,
qui est un concept réseau générique, reste coincée dans la couche
applicative de webapitools.

## Le résultat attendu

`linuxtools.network` expose un **modèle de client LAN** et un **chargeur
de liste de clients** génériques, qui deviennent la source unique de ce
parsing. webapitools consomme ce chargeur dans ses trois points, sans
plus réécrire le squelette de validation : la contrainte « nom = label
DNS » et le filtrage d'IP exploitable propres à Pi-hole sont **injectés**
en paramètres, pas imposés par la lib. On supprime la duplication tout en
gardant chaque appelant maître de ses règles métier.

## Pour qui

Moi, en local. Consommateur immédiat : webapitools (3 points). Bénéficiaire
futur potentiel : tout outil homelab qui déclare des clients LAN
(scanNetHome, outils NAS).

## Pourquoi maintenant

La dédup `normalize_mac` → `linuxtools.validate_mac` vient d'être livrée
(v2.5.1, PR #135) ; elle a laissé visible la duplication voisine, de plus
gros grain, du parsing de clients. C'est la suite logique, pendant que le
contexte cross-repo est frais et que la section « À faire » du hub
webapitools la liste explicitement.

## Critère de succès

C'est réussi si les trois points de webapitools (`pihole_dns`,
`pihole_schedule`, `router apply`) chargent leurs clients LAN via le
chargeur unique de `linuxtools.network`, sans squelette de parsing
dupliqué, à comportement externe inchangé (mêmes validations, mêmes
erreurs côté utilisateur).

## Ce que ce n'est PAS

- Pas d'extraction de l'enveloppe spécifique Pi-hole (`zone`, `[[target]]`)
  ni de l'ouverture du fichier TOML : seule la **liste de clients** est
  générique ; chaque appelant garde son enveloppe et lit son fichier.
- Pas de nouveau format de déclaration ni de champ client supplémentaire :
  on factorise l'existant (MAC, nom, IP), on n'enrichit pas le modèle.
- Pas de changement de comportement observable pour l'utilisateur des CLI
  webapitools (dry-run, messages, codes de sortie inchangés).

---

## ⏸ Validation requise

**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
