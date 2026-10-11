# Note de Besoin — Fichier unique des appareils du LAN
> **Date :** 2026-10-11
> **Statut :** À valider

---

## Le problème
La liste des appareils du LAN (MAC, nom, IP) existe en deux copies qui dérivent :
`webapitools/config/pihole-dns.toml` (`[[client]]`) et
`scanNetHome/config/reservations.toml` (`[[reservation]]`). Sur le nœud pve, chaque
appli a sa propre copie sous `/opt/<appli>/src/config/`. Un appareil ajouté ou
réactivé d'un côté seulement (ex. msiwifi) laisse Pi-hole, le routeur et
scanNetHome en désaccord.

## Le résultat attendu
Un seul fichier TOML fait foi pour les appareils du LAN **et** pour la configuration
Pi-hole de webapitools (sections `[lan]`, `[pihole]`, `[[client]]`…). webapitools et
scanNetHome le lisent tous les deux, chacun ignorant les sections qui ne le
concernent pas. Modifier un appareil à un seul endroit suffit.

## Pour qui
Moi, sur le nœud pve (où webapitools et scanNetHome tournent déjà, `/opt/*`) et en
poste de dev.

## Pourquoi maintenant
Le chargeur `load_lan_clients` (linuxtools v2.6.0) a unifié la lecture côté
webapitools ; scanNetHome est encore sur son chargeur local et `linuxtools@v2.0.1`.

## Critère de succès
C'est réussi si un appareil modifié dans le fichier unique est vu à l'identique
par `webapitools router apply` et par `scannethome reservations`, sans second fichier à tenir à jour.

## Ce que ce n'est PAS
- Pas une fusion du code des deux applis, seulement de leur source de données.
- Pas de nouvelle commande de synchronisation entre deux fichiers : il n'y en a plus qu'un.
- Les règles strictes de scanNetHome (IP et nom obligatoires) restent appliquées
  par scanNetHome, pas imposées à webapitools.

## Décisions déjà prises (Frédéric, 2026-10-11)
- Fichier à un **chemin configuré** sur le nœud, **versionné par git**.
- **Tout** dans le fichier unique (appareils + config Pi-hole).
- `enabled` et `note` rejoignent le schéma commun de `[[client]]`.

> ⚠️ HYPOTHÈSE À VALIDER : le dépôt git pourrait être `config-nas`
> (`/opt/config-nas` sur pve, Forgejo, déjà équipé de `sops` pour les secrets) plutôt
> qu'un nouveau dépôt. À trancher en conception.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
