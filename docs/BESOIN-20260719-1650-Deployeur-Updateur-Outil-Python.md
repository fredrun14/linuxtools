# Note de Besoin — Déployeur/updateur d'outil Python sur hôte

> **Date :** 2026-07-19
> **Statut :** À valider

---

## Le problème
Mettre à jour un outil Python maison sur une machine (poste ou serveur) est
aujourd'hui un rituel **manuel refait projet par projet** : acheminer le
source → réinstaller dans le venv → vérifier que l'install fonctionne → pouvoir
revenir en arrière si ça casse. Chaque projet réinvente cette séquence (ex.
`install-backup-vpe.sh`), et l'oubli d'une phase — surtout la vérification
post-install et le rollback — casse une prod **en silence** (build divergent du
2/07 qui n'importait plus `linuxtools`, invisible sans vérif d'import explicite).

## Le résultat attendu
Un **composant réutilisable dans `linuxtools`** qu'un projet CLI appelle pour se
déployer / se mettre à jour sur un hôte, orchestrant les 4 phases :
**transport du source → (ré)installation dans le venv → vérification déclarative
(imports + sous-commandes + hook de non-régression) → rollback automatique si une
vérif échoue**. Utilisable **en local sur l'hôte cible comme en distant via SSH**,
et exposé à la fois en **API Python** (appelable depuis le code d'un projet) et en
**CLI `linuxtools`** autonome. S'appuie sur les briques existantes
(`LinuxCommandExecutor`, `CommandBuilder`, `FileLogger`).

## Pour qui
Moi, sur mes projets Python homelab (postes et nœuds Proxmox), en local et en SSH.

## Pourquoi maintenant
Déclenché par le chantier du 2026-07-19 (MàJ de `backup-py-manager` v0.1.0 sur le
nœud `pve`) : la séquence des 4 phases + rollback y a été écrite et testée à la
main, elle est mûre pour être factorisée plutôt que dupliquée au projet suivant.

## Critère de succès
C'est réussi si un projet CLI peut se déployer/se mettre à jour sur un hôte (local
ou SSH) via ce composant, avec **vérification post-install et rollback automatique**,
**sans réécrire le rituel** — là où il fallait un script bash spécifique par projet.

## Ce que ce n'est PAS
- **Pas** de gestion de la config runtime ni des secrets du service (ex.
  `EnvironmentFile` systemd du token Gotify) — le déployeur gère le **code**, pas la conf.
- **Pas** un gestionnaire de release/packaging (ce n'est pas twine/PyPI) : il déploie
  un source déjà buildé/clone local, il ne publie pas.
- **Pas** un orchestrateur multi-hôtes type Ansible : une cible à la fois.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
