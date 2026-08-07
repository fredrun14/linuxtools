# Cahier des Charges — CommandExecutor pour LinuxCliInstaller
> **Date :** 2026-08-06
> **Statut :** Brouillon
> **Auteur :** Frederic

---

## 1. Contexte et Problématique

### Problème à résoudre
`LinuxCliInstaller` (`linuxtools.scripts.installer`) déploie un CLI Python
via `uv tool install`, mais uniquement en local : `_run_uv_install()` appelle
`subprocess.run` en dur, sans passer par l'abstraction `CommandExecutor`
qu'utilise le reste de `linuxtools`. Il ne peut donc pas cibler un hôte
distant en SSH, alors que le module `deploy` (`VenvInstaller`) le peut déjà
— mais celui-ci réinstalle via `pip install --force-reinstall` dans un venv
géré à la main, pas via `uv`.

### Solution envisagée
Injecter un `CommandExecutor` dans `LinuxCliInstaller`, comme c'est déjà fait
pour `VenvInstaller`, et faire passer l'appel à `uv tool install` par cet
exécuteur plutôt que par `subprocess.run`. Le même `CommandExecutor` (local
`LinuxCommandExecutor` ou distant `SshCommandExecutor`) déterminera la cible,
sans notion de "target" propre à `LinuxCliInstaller`.

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] `CommandExecutor` injecté dans le constructeur de `LinuxCliInstaller`
      (obligatoire, jamais instancié en dur — cohérent avec les conventions
      DI du projet).
- [ ] `_run_uv_install()` exécute la commande `uv tool install` via
      l'exécuteur injecté plutôt que via `subprocess.run`.
- [ ] Localisation de l'exécutable `uv` (`_find_uv()`) fonctionnelle aussi
      bien en local qu'à distance — recherché sur l'hôte cible via
      l'exécuteur, pas sur la machine locale d'où tourne `linuxtools`.
      Confirmé par Frederic le 2026-08-07.
- [ ] Vérifications de précondition de `ScriptChecker` (`check_python`,
      `check_dependencies`, `check_venv`) exécutées via le `CommandExecutor`
      injecté, pour une cohérence complète en déploiement distant.
      Confirmé par Frederic le 2026-08-07 (réponse à Q-01).
- [ ] Génération/écriture du wrapper bash (`_write_wrapper`, `_open_secure`)
      exécutée via l'exécuteur injecté, pour fonctionner aussi bien en local
      qu'à distance. Confirmé par Frederic le 2026-08-07 (réponse à Q-02).

### Exclu (Out of Scope)
- Backup/rollback autour de `uv tool install` — explicitement écarté par le
  besoin pour cette évolution.
- Fusion ou remplacement du module `deploy` (`VenvInstaller`) — les deux
  mécanismes de déploiement CLI restent séparés et coexistent.
- Migration de `backup-py-manager install` vers un nouveau flux — seule
  l'API de `linuxtools` évolue ici, pas ses consommateurs.

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | Frederic (via assistant-codage) | Implémente la solution |
| Utilisateur    | Frederic, consommateurs de `linuxtools` | Utilise le livrable final |

---

## 4. Objectifs Fonctionnels

> Ce que le système **doit faire**.

| ID   | Priorité        | Description                                   |
|------|-----------------|-----------------------------------------------|
| F-01 | Must have       | `LinuxCliInstaller.__init__` accepte un `CommandExecutor` injecté (paramètre obligatoire, pas de valeur par défaut instanciée en dur). |
| F-02 | Must have       | `_run_uv_install()` exécute la commande `uv tool install` (user/system, avec les mêmes options qu'aujourd'hui — `--force --editable`, ou `--python .../ --editable` + éventuel `sudo` côté system) via l'exécuteur injecté, et non plus `subprocess.run`. |
| F-03 | Should have     | `_find_uv()` localise `uv` via l'exécuteur injecté (PATH, `~/.local/bin/uv`, `~/.cargo/bin/uv`), pour fonctionner identiquement en local et à distance. |
| F-04 | Won't have      | Backup/rollback autour de `uv tool install` — hors périmètre v1. |
| F-05 | Must have       | Les vérifications de précondition (`check_python`, `check_dependencies`, `check_venv` de `ScriptChecker`) s'exécutent via le `CommandExecutor` injecté, pour rester cohérentes en déploiement distant. |
| F-06 | Must have       | La génération/écriture du wrapper bash (`_write_wrapper`, `_open_secure`) s'exécute via le `CommandExecutor` injecté (plus de dépendance à `os.open`/`os.fchmod` locaux quand la cible est distante). |

---

## 5. Objectifs Non-Fonctionnels

> Ce que le système **doit être**.

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | Pas de contrainte spécifique — usage ponctuel (déploiement manuel). |
| Disponibilité   | Usage ponctuel, pas de service continu. |
| Sécurité        | Aucune commande construite par interpolation de chaîne (liste d'arguments, comme le reste du projet) ; pas de nouveau vecteur d'injection introduit. |
| Maintenabilité  | Cohérence stricte avec le pattern DI déjà en place dans `VenvInstaller`/`deploy` ; `mypy --strict` = 0 erreur ; couverture ≥ seuil du projet (90 %). |
| Portabilité     | Linux uniquement, Python 3.11+, stdlib — pas de nouvelle dépendance externe (`uv` reste un outil externe déjà requis, pas une lib Python). |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|-----------------------------------------------------------|
| Langage       | Python 3.11+                                              |
| Environnement | Local (comportement actuel) ou distant SSH (nouveau), homelab. |
| Dépendances   | `linuxtools.commands.base.CommandExecutor` (interne, déjà présent) ; aucune nouvelle dépendance externe. |
| Infrastructure| Aucune modification CI/CD requise a priori. |
| Données       | Aucune donnée persistante nouvelle. |

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement** — Pas d'exposition réseau
- [x] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> ⚠️ HYPOTHÈSE À VALIDER — coché "Réseau interne" car la cible distante est
> un hôte SSH du homelab (même modèle de menace que le module `deploy`
> existant), pas une exposition publique.

> ⚠️ Si « Réseau interne » ou « Exposé Internet » : activer les skills
> `python-owasp-security`, `python-sast-bandit-security`,
> `python-security-monitoring`.

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] `LinuxCliInstaller` accepte un `CommandExecutor` injecté et l'utilise
      pour lancer `uv tool install` (local ou distant SSH).
- [ ] Le comportement local existant (options `--force --editable` user,
      `--python ... --editable` + `sudo` system) est préservé à
      l'identique pour un `LinuxCommandExecutor`.
- [ ] Tests unitaires couvrant le cas local ET le cas distant (mock de
      `CommandExecutor`), couverture ≥ 90 %.
- [ ] `mypy --strict` = 0 erreur.
- [ ] Aucun warning Bandit sévérité MEDIUM ou supérieure.
- [ ] Documentation (docstrings PEP 257 + note Obsidian du module `scripts`)
      à jour.

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|--------------------------------------|-------------|
| Code source           | `LinuxCliInstaller` modifié dans `src/linuxtools/scripts/installer.py` | |
| Tests                 | `tests/` avec couverture ≥ 90 %     |             |
| Documentation         | Docstrings PEP 257 + note Obsidian `linuxtools – Module scripts` | |

---

## 10. Questions Ouvertes

| ID  | Question                              | Responsable | Statut   |
|-----|---------------------------------------|-------------|----------|
| Q-01| Les vérifications de précondition de `ScriptChecker` (`check_python`, `check_dependencies`, `check_venv`) doivent-elles aussi devenir exécutées via le `CommandExecutor` pour un déploiement distant cohérent, ou reste-t-on sur des vérifications strictement locales (la précondition est vérifiée sur la machine qui lance le déploiement, pas sur la cible) ? | Frederic | Résolu — cf. F-05 |
| Q-02| La génération/écriture du wrapper bash (`_write_wrapper`, `_open_secure`) doit-elle aussi passer par l'exécuteur pour un déploiement distant, ou reste-t-elle hors périmètre (le wrapper n'est écrit que si aucun `[project.scripts]` n'est déclaré — cas jugé secondaire) ? | Frederic | Résolu — cf. F-06 |

### Note (hors périmètre F-05, points restant strictement locaux)

F-05 couvre les vérifications de précondition exécutées via le
`CommandExecutor` (donc potentiellement sur une cible distante), mais deux
points de résolution restent **strictement locaux** même après cette
évolution, et le demeurent volontairement :

- `read_pyproject()` : lit `pyproject.toml` via `open()` sur la machine qui
  lance le déploiement, jamais sur la cible.
- `ScriptPaths` : résout les chemins `~/.local/...` via `Path.home()` local,
  pas celui de la cible distante.

Ces deux points seront documentés dans les docstrings de
`LinuxCliInstaller`/`LinuxScriptChecker`, pas corrigés dans ce chantier.

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
