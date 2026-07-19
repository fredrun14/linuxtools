# Cahier des Charges — Déployeur/updateur d'outil Python sur hôte

> **Date :** 2026-07-19
> **Statut :** Brouillon
> **Auteur :** Frederic

---

## 1. Contexte et Problématique

### Problème à résoudre
Mettre à jour un outil Python maison sur une machine (poste ou serveur Proxmox)
est un rituel **manuel refait projet par projet** : acheminer le source →
réinstaller dans le venv → vérifier l'install → revenir en arrière si ça casse.
Chaque projet réinvente cette séquence (ex. `install-backup-vpe.sh`), et l'oubli
d'une phase — surtout la vérification post-install et le rollback — casse une prod
**en silence** (build divergent du 2/07 qui n'importait plus `linuxtools`,
invisible sans vérif d'import explicite).

### Solution envisagée
Un composant réutilisable dans `linuxtools` orchestrant les **4 phases**
(transport → (ré)installation venv → vérification déclarative → rollback auto),
utilisable **en local et en SSH**, exposé en **API Python** et en **CLI**, en
s'appuyant sur les briques existantes (`LinuxCommandExecutor`, `CommandBuilder`,
`FileLogger`). Le déployeur gère le **code**, pas la config runtime/les secrets.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Transport du source vers l'hôte cible (local ou distant)
- [ ] (Ré)installation dans un venv cible via pip (deps déléguées à pip)
- [ ] Vérification post-install **déclarative** : imports à tester +
      sous-commandes attendues + hook de non-régression
- [ ] Sauvegarde du venv avant install et **rollback automatique** si une vérif échoue
- [ ] Exécution **locale** (sur l'hôte cible) **et distante via SSH**
- [ ] Exposition **API Python** (appelable depuis le code d'un projet)
- [ ] Exposition **CLI `linuxtools`** autonome
- [ ] Idempotence : rejouable sans casse, ne touche pas la config/les secrets

### Exclu (Out of Scope)
- Gestion de la config runtime et des secrets du service (`EnvironmentFile` systemd, tokens)
- Packaging / publication de release (twine / PyPI) — déploie un source déjà présent
- Orchestration multi-hôtes simultanée (type Ansible) — une cible à la fois

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | Frederic     | Implémente la solution       |
| Utilisateur    | Frederic     | Utilise le livrable (homelab)|

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité    | Description                                                                 |
|------|-------------|-----------------------------------------------------------------------------|
| F-01 | Must have   | Transporter le source local vers l'hôte cible (rsync par défaut)            |
| F-02 | Must have   | (Ré)installer dans un venv existant via pip (`--force-reinstall`)           |
| F-03 | Must have   | Vérifier l'install : liste déclarative d'imports à tester                   |
| F-04 | Must have   | Vérifier l'install : liste déclarative de sous-commandes attendues          |
| F-05 | Must have   | Sauvegarder le venv avant install et **restaurer automatiquement** si KO    |
| F-06 | Must have   | Fonctionner en **local** sur l'hôte cible                                   |
| F-07 | Must have   | Fonctionner en **distant via SSH** (`LinuxCommandExecutor`)                 |
| F-08 | Must have   | Exposer une **API Python** injectable (Logger/Executor)                     |
| F-09 | Should have | Exposer une **sous-commande CLI `linuxtools`**                              |
| F-10 | Should have | Hook de **non-régression** personnalisé (commande projet à rejouer)         |
| F-11 | Must have   | Mode **dry-run** (simulation sans effet de bord) — retenu V1               |
| F-12 | Could have  | Transport alternatif : `git clone/pull` si dépôt accessible                 |
| F-13 | Could have  | Transport alternatif : archive / release                                    |
| F-14 | Could have  | **Recréation propre** du venv en option (au lieu de réinstall en place)     |
| F-15 | Won't have  | Gestion de la config runtime / secrets, packaging PyPI, multi-hôtes         |

> **Arbitrages validés (2026-07-19)** : module nommé `deploy` ; dry-run (F-11)
> retenu en **Must have** ; recréation propre du venv (F-14) laissée en **Could have**.

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                                        |
|-----------------|----------------------------------------------------------------|
| Performance     | Usage ponctuel (déploiement manuel) — pas de contrainte de latence |
| Disponibilité   | Outil CLI/API à la demande, pas de service permanent           |
| Sécurité        | Exécution locale/SSH de confiance ; garde-fou accès réseau pour pip |
| Maintenabilité  | Couverture tests ≥ 80 % ; SOLID (ABC + injection Logger/Executor) |
| Portabilité     | Linux only, Python 3.11+, stdlib uniquement                    |
| Robustesse      | Rollback garanti si une phase de vérif échoue (jamais de prod cassée muette) |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                                       |
|---------------|------------------------------------------------------------------|
| Langage       | Python 3.11+                                                     |
| Environnement | Local sur l'hôte cible **ou** distant via SSH                    |
| Dépendances   | **stdlib uniquement** ; réutilise `LinuxCommandExecutor`, `CommandBuilder`, `FileLogger` |
| Infrastructure| Postes Linux + nœuds Proxmox (homelab) ; rsync + ssh + pip présents sur la cible |
| Données       | Source Python d'un projet (clone local) + venv cible ; pas de BDD |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas d'exposition réseau entrante (l'outil est un client SSH sortant)
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> Outil opérateur (client) : il se connecte en SSH sortant vers une cible de
> confiance, il n'expose aucun service. Pas d'entrée réseau non maîtrisée →
> skills OWASP/SAST/monitoring non requis a priori. Vigilance ponctuelle :
> construction sûre des commandes shell (injection via noms de venv/commandes),
> déjà couverte par `CommandBuilder`.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Un projet CLI peut se déployer/se mettre à jour sur un hôte **local** via l'API
- [ ] Idem sur un hôte **distant via SSH**
- [ ] Une vérif post-install qui échoue déclenche un **rollback automatique** du venv
- [ ] Les vérifications (imports + sous-commandes + hook non-régression) sont **déclaratives**
- [ ] Une sous-commande CLI `linuxtools` couvre le cas d'usage de bout en bout
- [ ] Rejouable (idempotent) sans casse
- [ ] Tests unitaires passent avec couverture ≥ 80 %
- [ ] Aucun warning Bandit sévérité MEDIUM ou supérieure
- [ ] Documentation (README section modules, docstrings français PEP 257) à jour
- [ ] Note Obsidian du module créée/mise à jour

---

## 9. Livrables Attendus

| Livrable              | Description                                    | Échéance |
|-----------------------|------------------------------------------------|----------|
| Code source           | Module `src/linuxtools/deploy/`                 | —        |
| API publique          | Export depuis `src/linuxtools/__init__.py`     | —        |
| CLI                   | Sous-commande intégrée à la CLI linuxtools     | —        |
| Tests                 | `tests/` avec couverture ≥ 80 %                | —        |
| Documentation         | README (Modules disponibles) + docstrings + note Obsidian | — |

---

## 10. Questions Ouvertes

| ID  | Question                                                                 | Responsable | Statut |
|-----|--------------------------------------------------------------------------|-------------|--------|
| Q-01| Nom du module → **`deploy`**                                              | Frederic    | ✅ Tranché |
| Q-02| F-11 (dry-run) → **retenu V1 (Must)**                                     | Frederic    | ✅ Tranché |
| Q-03| Recréation venv (F-14) → **Could have**                                   | Frederic    | ✅ Tranché |
| Q-04| Format de déclaration des vérifs : dataclass, TOML, ou dict Python ?      | Frederic    | Ouvert (→ plan) |
| Q-05| Le hook de non-régression (F-10) : commande shell libre ou callable Python ?| Frederic | Ouvert (→ plan) |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
