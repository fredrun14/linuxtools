# Cahier des Charges — Export USB de déploiement (`usb-export`)
> **Date :** 2026-08-16
> **Statut :** Brouillon
> **Auteur :** Fred

---

## 1. Contexte et Problématique

### Problème à résoudre
`fedora_post_install` sait déjà préparer une clé USB permettant d'installer
l'outil sur une machine sans réseau (`UsbExportManager`, deux modes :
`sources` + `uv tool install`, ou `venv` autonome précompilé). Cette
logique ne dépend d'aucune spécificité de `fedora_post_install` mais vit
enfermée dans ce projet — tout autre outil déployé via `linuxtools.deploy`
doit aujourd'hui réimplémenter cette préparation de clé USB à la main, ou
en rester privé.

### Solution envisagée
Porter la capacité dans `linuxtools.deploy` comme une cible de déploiement
supplémentaire, au même titre que le déploiement vers un hôte (transport →
install → vérification → rollback) déjà couvert par `Deployer`. Deux modes
repris dans leur principe : `sources` (copie des sources + `uv tool
install` sur la cible — mode **nominal**) et `venv` (venv Python autonome
précompilé sur la clé — mode **secondaire**, pour les cibles sans réseau).
`linuxtools.deploy` expose déjà les primitives réutilisables identifiées
comme socle commun (`discovery.py` pour la détection de source,
`content_writer.py` pour l'écriture de contenu générée) — le module
`filesystem` expose par ailleurs déjà `copytree_secure`/`write_text_secure`/
`LinuxFileBackup`, utilisés tels quels par l'implémentation d'origine.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Fonction/classe de préparation de clé USB dans `linuxtools.deploy`,
      mode `sources` : copie des sources du projet + binaire `uv` (si
      présent sur le PATH) + linuxtools (si install éditable détectée via
      `find_editable_source`) + génération d'un script d'installation
      utilisant `uv tool install`.
- [ ] Mode `venv` : construction d'un venv Python autonome (build en
      répertoire temporaire local puis copie en déréférençant les
      symlinks — contrainte exFAT/FAT/NTFS déjà identifiée et résolue côté
      `fedora_post_install`) + génération d'un script de lancement.
- [ ] Dry-run : aperçu des opérations sans écriture, cohérent avec le reste
      de `deploy` (`DeployConfig`/`Deployer` supportent déjà ce mode).
- [ ] API Python utilisable directement (sans passer par une CLI), comme
      le reste de `deploy`.
- [ ] Détection automatique du répertoire source du projet consommateur et
      de `linuxtools` en mode éditable, en réutilisant
      `discovery.find_project_source`/`find_editable_source` — pas de
      réimplémentation de cette logique.
- [ ] Reprise explicite des correctifs déjà connus côté
      `fedora_post_install` (à ne pas réintroduire) : script généré
      n'utilise jamais `python3 -m pip install` (PEP 668, Fedora 41+) ;
      construction du venv en `tmpfs`/répertoire temporaire puis copie avec
      déréférencement des symlinks pour compatibilité exFAT/FAT/NTFS.

### Exclu (Out of Scope)
- Le refactor de `fedora_post_install` pour consommer cette nouvelle API
  et supprimer `UsbExportManager` — chantier séparé, plus tard.
- Tout nouveau mode de déploiement (Docker, image bootable complète) —
  seuls les deux modes déjà éprouvés (`sources`, `venv`) sont repris.
- Bascule du pipeline de déploiement hôte-distant existant vers `uv` (PEP
  668 oblige déjà `VenvInstaller` à passer par le pip du venv cible côté
  hôte) — seule la préparation de clé USB privilégie `uv tool install`.
- Intégration CLI dans `linuxtools deploy` (`src/linuxtools/deploy/cli.py`)
  — tranché le 2026-08-16 : API Python seule pour ce lot, chaque projet
  consommateur garde sa propre commande, comme `fedora-post-install
  usb-export` le fait aujourd'hui côté appelant.

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Fred         | Valide les objectifs         |
| Développeur    | Claude Code (agent `assistant-codage`) | Implémente la solution |
| Utilisateur    | Fred (projets consommateurs de `linuxtools.deploy`) | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | Préparer une clé USB en mode `sources` : sources projet + `uv` + linuxtools éditable (si détecté) + script d'installation `uv tool install` |
| F-02 | Must have       | Préparer une clé USB en mode `venv` : venv autonome précompilé + script de lancement, sans dépendance réseau sur la cible |
| F-03 | Must have       | Dry-run : lister les opérations qui seraient effectuées sans rien écrire |
| F-04 | Must have       | Auto-détection du répertoire source du projet et de linuxtools (mode éditable), via `discovery.py` existant — pas de duplication |
| F-05 | Should have     | Copie d'un répertoire de configuration personnalisé vers la clé (équivalent `user_config_dir` de l'implémentation d'origine) |
| F-06 | Should have     | Rapport structuré des chemins créés + avertissements (ex. linuxtools non détecté en mode éditable) |
| F-07 | Won't have      | Sous-commande CLI dans `linuxtools deploy` — tranché le 2026-08-16 : API Python seule pour ce lot, chaque projet consommateur garde sa propre commande |
| F-08 | Won't have      | Intégration/refactor de `fedora_post_install` sur cette nouvelle API |

---

## 5. Objectifs Non-Fonctionnels

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Pas de contrainte de temps forte — opération manuelle, ponctuelle |
| Disponibilité   | Sans objet (usage local, ponctuel) |
| Sécurité        | Écritures TOCTOU-safe (réutilise `copytree_secure`/`write_text_secure`, déjà O_NOFOLLOW côté `filesystem`) ; aucun secret déposé sur la clé sans action explicite de l'appelant |
| Maintenabilité  | Couverture tests ≥ 80 %, cohérente avec le reste de `deploy` ; `mypy --strict` = 0 erreur (gate bloquant du dépôt) |
| Portabilité     | Linux uniquement (cohérent avec le reste de `linuxtools`) ; supports de destination exFAT/FAT/NTFS (clés USB) à couvrir explicitement pour le mode `venv` |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|----------------------------------------------------------|
| Langage       | Python 3.11+                                              |
| Environnement | Local uniquement — écriture sur un support monté localement (ex. `/run/media/user/USB`), jamais via SSH |
| Dépendances   | `uv` doit être présent sur le PATH de la machine source pour le mode `venv` (construction du venv) ; optionnel mais recommandé pour le mode `sources` (copié sur la clé si présent, sinon avertissement) |
| Infrastructure | S'intègre dans `src/linuxtools/deploy/`, réutilise `filesystem/backup.py` (`copytree_secure`, `LinuxFileBackup`) et `filesystem/linux.py` (`write_text_secure`) déjà en place |
| Données       | Aucune donnée sensible par défaut ; si un répertoire de config utilisateur contient des secrets, la responsabilité de ne pas les exposer sur la clé reste à l'appelant (hors périmètre de ce lot) |

---

## 7. Exposition et Surface d'Attaque

- [x] **Local uniquement** — Pas d'exposition réseau
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> Local uniquement : les skills sécurité réseau (`python-owasp-security`,
> `python-sast-bandit-security`, `python-security-monitoring`) ne
> s'activent pas pour ce lot. La vigilance TOCTOU/symlink reste de mise
> (réutilisation des primitives déjà auditées de `filesystem`).

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Un mode `sources` fonctionnel produit une clé USB installable via
      `uv tool install`, testé (dry-run + écriture réelle en tests avec
      `tmp_path`)
- [ ] Un mode `venv` fonctionnel produit un venv autonome copié sans
      symlinks résiduels (test explicite de déréférencement)
- [ ] Aucune régression des correctifs déjà connus : pas de
      `python3 -m pip install` dans les scripts générés, construction du
      venv déréférencée pour compatibilité FAT
- [ ] `discovery.find_project_source`/`find_editable_source` réutilisés
      tels quels, pas de logique de détection dupliquée
- [ ] Tests unitaires passent avec couverture ≥ 80 %
- [ ] `mypy --strict` = 0 erreur (gate bloquant du dépôt)
- [ ] Documentation (README, docstrings, doc vault module `deploy`) à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | Nouveau(x) module(s) dans `src/linuxtools/deploy/` |             |
| Tests                 | `tests/` avec couverture ≥ 80 %     |             |
| Documentation         | `README.md` + docstrings PEP 257 + notes vault `deploy` |             |
| CHANGELOG             | Entrée versionnée (MINOR — nouvelle capacité publique) |             |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|----------------------------------------|-------------|----------|
| Q-01| ~~Sous-commande CLI en V1, ou API Python seule (F-07) ?~~ | Fred | Tranché 2026-08-16 : API Python seule |
| Q-02| Forme d'intégration : nouveau module autonome (ex. `usb_export.py`) avec ses propres dataclasses, ou extension de `DeployTarget`/`DeployConfig` existants ? — relève du *comment*, à trancher en plan-todo, mais conditionne le périmètre des tests d'intégration avec `Deployer` | Fred / plan-todo | Ouvert |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
