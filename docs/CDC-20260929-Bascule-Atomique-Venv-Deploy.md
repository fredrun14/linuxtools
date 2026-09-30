# Cahier des Charges — Bascule atomique du venv au déploiement
> **Date :** 2026-09-29
> **Statut :** Validé (2026-09-29)
> **Auteur :** Frédéric

> Besoin reformulé et validé en conversation le 2026-09-29 (pas de
> `BESOIN-*.md` séparé). Les points déduits et non encore tranchés par
> l'utilisateur sont balisés `⚠️ HYPOTHÈSE À VALIDER`.

---

## 1. Contexte et Problématique

### Problème à résoudre
`linuxtools.deploy` réinstalle le venv cible **en place**. Avec
`recreate_venv=True`, `VenvInstaller.install()` enchaîne `rm -rf <venv>` →
`python3 -m venv <venv>` → `pip install --force-reinstall` : pendant plusieurs
dizaines de secondes, `<venv>/bin/<cli>` n'existe pas ou est incomplet. Sans
`recreate_venv`, `pip install --force-reinstall` en place ouvre la même fenêtre
(désinstallation puis réinstallation des fichiers).

Tout service systemd qui s'exécute pendant cette fenêtre échoue. Incident
constaté le **2026-09-29 16:25:07** : `webapitools-asus-block-blocage-reseaux-soir-tel.service`
(timer toutes les 5 min, venv partagé `/opt/webapitools/venv`) a échoué en
`203/EXEC` — « Unable to locate executable » — pendant un redéploiement
webapitools, déclenchant une alerte Gotify. Le problème se reproduit à chaque
déploiement d'un outil dont un timer tombe dans la fenêtre.

### Solution envisagée
Ne plus jamais modifier le venv en service. Chaque déploiement construit un
**nouveau venv dans un emplacement versionné**, l'installe et le **vérifie
là**, puis rend ce venv actif par la **bascule atomique d'un lien
symbolique** à l'emplacement `venv_path` attendu par les consommateurs
(unités systemd, scripts). Les venvs précédents sont conservés en nombre
limité ; le rollback consiste à rebasculer le lien. Les timers ne sont
jamais arrêtés ni relancés.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Construction du venv dans un répertoire versionné, à son emplacement
      définitif (un venv n'est pas relocalisable : shebangs absolus)
- [ ] Vérifications post-install exécutées sur le venv versionné **avant**
      bascule
- [ ] Bascule atomique du lien `venv_path` vers le nouveau venv
- [ ] Rollback par rebascule du lien vers la version précédente
- [ ] Rétention des N dernières versions, purge des plus anciennes
- [ ] Migration d'un `venv_path` existant qui est un **répertoire réel**
- [ ] Dry-run reflétant les nouvelles étapes
- [ ] Rapport de déploiement (`DeployReport`) indiquant la version active et
      la version de repli

### Exclu (Out of Scope)
- Arrêt / relance / mise en pause des timers ou services systemd
- Modification des unités systemd des consommateurs (elles continuent
  d'appeler `<venv_path>/bin/<cli>`)
- Mise à jour des 5 projets consommateurs (chacun fera l'objet d'une petite
  modif séparée : bump linuxtools + activation éventuelle)
- Déploiement par export USB (`usb_export.py`)

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frédéric     | Valide les objectifs         |
| Développeur    | Claude (assistant-codage) | Implémente la solution |
| Utilisateur    | webapitools, backup-py-manager, fedora_post_install, nas-diy-tools, nas-diy-update | Consomment `linuxtools.deploy` |

---

## 4. Objectifs Fonctionnels

| ID   | Priorité    | Description |
|------|-------------|-------------|
| F-01 | Must have   | Le déploiement construit le venv dans un répertoire versionné neuf (ex. `/opt/<app>/venvs/<horodatage>/`), y installe le source, sans toucher au venv actif. |
| F-02 | Must have   | Les vérifications post-install (imports, sous-commandes) s'exécutent sur le venv versionné ; en cas d'échec, le venv actif reste inchangé et le venv versionné raté est supprimé — aucun rollback nécessaire. |
| F-03 | Must have   | Après vérification réussie, `venv_path` est basculé vers le nouveau venv par une opération atomique (création d'un lien temporaire puis `rename(2)` — `ln -sfn` + `mv -T`) : à aucun instant `<venv_path>/bin/<cli>` n'est absent. |
| F-04 | Must have   | Migration : si `venv_path` est un répertoire réel (état actuel de tous les hôtes), il est déplacé dans le répertoire des versions puis remplacé par le lien. La fenêtre résiduelle (deux `rename` consécutifs) est bornée et documentée. |
| F-05 | Must have   | Rollback : si une phase postérieure à la bascule échoue et déclenche aujourd'hui un rollback, le lien est rebasculé vers la version précédente (plus de copie `cp -a`). |
| F-06 | Must have   | Rétention : seules les N dernières versions sont conservées (la version active incluse), les plus anciennes sont purgées en best-effort après bascule réussie. La version active **et la version précédente (repli)** ne sont jamais purgées, y compris avec N=1 (avenant du 2026-09-29, cf. Q-05 — protège le rollback juste après un déploiement). |
| F-07 | Must have   | Le dry-run liste les étapes réelles du nouveau mode (construction versionnée, vérification, bascule, purge, migration le cas échéant). |
| F-08 | Should have | `DeployReport` expose le chemin de la version activée et celui de la version de repli. |
| F-09 | Should have | Fonctionne à l'identique avec un exécuteur local (`LinuxCommandExecutor`) et distant (`SshCommandExecutor`). |
| F-10 | Could have  | N configurable par le consommateur (défaut 2). |
| F-11 | Won't have  | Commande CLI dédiée « rollback manuel vers la version X » (prévu plus tard si besoin). |

---

## 5. Objectifs Non-Fonctionnels

| Critère         | Exigence |
|-----------------|----------|
| Disponibilité   | Zéro fenêtre d'absence de `<venv_path>/bin/<cli>` en régime établi ; fenêtre de migration unique et de l'ordre de la microseconde. |
| Performance     | Durée de déploiement inchangée à ± quelques secondes (plus de `cp -a` du venv pour le backup : attendu plus rapide). |
| Espace disque   | Au plus N venvs complets par outil sur l'hôte. |
| Maintenabilité  | `mypy --strict` 0 erreur ; TDD ; couverture ≥ 80 % sur les modules touchés. |
| Compatibilité   | Les consommateurs qui ne changent rien continuent de fonctionner (cf. Q-01). |
| Portabilité     | Linux (Fedora, Debian/Proxmox), Python ≥ 3.11 ; commandes coreutils standard (`ln`, `mv -T`, `readlink`). |

---

## 6. Contraintes Techniques

| Type          | Contrainte |
|---------------|------------|
| Langage       | Python ≥ 3.11 (`requires-python` du projet) |
| Environnement | Réseau interne (déploiement SSH vers les hôtes du homelab) |
| Dépendances   | Aucune nouvelle ; commandes passées par le `CommandExecutor` injecté (jamais instancié en dur) |
| Infrastructure| Forgejo Actions ; gate `mypy --strict` bloquant ; lib exposant `py.typed` |
| Données       | Aucune ; seul l'état du système de fichiers de l'hôte cible |

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement**
- [x] **Réseau interne** — commandes exécutées sur les hôtes du LAN via SSH
- [ ] **Exposé Internet**

### Exigences de sécurité

| Critère                    | Exigence |
|----------------------------|----------|
| Données sensibles          | Aucune nouvelle (les secrets restent gérés par `secrets_provisioner`, hors périmètre) |
| Authentification           | Inchangée (SSH existant) |
| Autorisation               | Opérations sous `/opt/<app>/` avec les droits déjà requis aujourd'hui |
| Entrées non fiables        | `venv_path` et le nom de version viennent de la config du consommateur et de l'horodatage — ⚠️ HYPOTHÈSE À VALIDER : à traiter comme non fiables pour les commandes de suppression |
| Surfaces dangereuses       | `rm -rf` de purge : ne doit jamais viser autre chose qu'un sous-répertoire du répertoire des versions, ni la version active, ni la cible du lien ; commandes passées en liste d'arguments (pas de shell) |
| Secrets                    | N/A |
| Traçabilité                | Logs du `Logger` injecté : version construite, bascule (ancienne → nouvelle cible), purge, rollback |

---

## 8. Critères d'Acceptation

- [ ] Pendant un déploiement réel, une boucle qui exécute `<venv_path>/bin/<cli> --help` en continu ne constate **aucun** échec (hors fenêtre de migration unique du premier déploiement)
- [ ] Un échec de vérification post-install laisse `venv_path` pointer sur l'ancienne version, et supprime la version ratée
- [ ] Un premier déploiement sur un hôte où `venv_path` est un répertoire réel aboutit à un lien vers une version, l'ancien répertoire étant conservé comme version de repli
- [ ] Après 3 déploiements successifs avec N=2, seules 2 versions restent ; la version active en fait partie
- [ ] Le rollback rebascule le lien vers la version précédente sans copie
- [ ] Le dry-run affiche les nouvelles étapes et n'exécute rien
- [ ] Tests unitaires TDD sur exécuteur mocké (local et SSH) ; couverture ≥ 80 %
- [ ] `mypy --strict` 0 erreur ; aucun warning Bandit ≥ MEDIUM
- [ ] Docstrings, `README`/doc du module `deploy` et `CHANGELOG` à jour ; version linuxtools incrémentée

---

## 9. Livrables Attendus

| Livrable       | Description | Échéance |
|----------------|-------------|----------|
| Code source    | `src/linuxtools/deploy/` (installer, deployer, models, dry-run) | |
| Tests          | `tests/` avec couverture ≥ 80 % | |
| Documentation  | Docstrings PEP 257, doc module deploy, `CHANGELOG.md` | |
| Release        | Tag linuxtools (mineure) | |

---

## 10. Questions Ouvertes

| ID   | Question | Responsable | Statut |
|------|----------|-------------|--------|
| Q-01 | Défaut ou opt-in ? → **Opt-in** (`DeployConfig.atomic_swap=True`) en version mineure ; passage en défaut quand les 5 consommateurs l'auront adopté. | Frédéric | Tranché |
| Q-02 | Emplacement des versions → `<venv_path.parent>/venvs/`. | Frédéric | Tranché |
| Q-03 | `recreate_venv` → sans objet en mode `atomic_swap` (chaque version est neuve). | Frédéric | Tranché |
| Q-04 | N par défaut → **2** (active + 1 repli). | Frédéric | Tranché |
| Q-05 | Avenant 2026-09-29 (F02, revue `revueur-code`, No-Go) : contradiction CDC/conception sur N=1. La précédente est-elle purgée (CDC initial) ou protégée à vie (conception) ? → **Protégée à vie**, quel que soit N. Avec N=1, l'hôte conserve donc en pratique 2 versions (active + repli), N=1 se comportant comme N=2. | Frédéric | Tranché |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (conception
`conseiller-architectural`, puis `python-plan-todo`).
