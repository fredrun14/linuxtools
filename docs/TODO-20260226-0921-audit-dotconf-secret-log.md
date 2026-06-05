# AUDIT SÉCURITÉ MODULE DOTCONF — FUITE VALEUR EN LOG (A09)
> **Date :** 2026-02-26 à 09:21
> **Complexité estimée :** Faible

---

## Contexte

### Problématique

Audit sécurité du module `dotconf/` (4 skills). Un seul problème identifié dans
`LinuxIniConfigManager.update_section()` :

**Ligne 147 de `dotconf/manager.py` :**
```python
self.logger.log_info(f"Modification : {key} = {new_value}")
```

La **valeur** de chaque clé modifiée est loggée en clair. Si le fichier INI
contient des clés sensibles (`password`, `secret`, `token`, `api_key`,
`passphrase`…), leur nouvelle valeur apparaît en texte clair dans les logs
(fichier log accessible à quiconque peut lire le fichier de log).

**Exemple concret :**
```ini
# /etc/my_app.ini
[database]
password = MonMotDePasseSecret123
```

Après `update_section()`, le log contiendrait :
```
INFO - Modification : password = MonMotDePasseSecret123
```

Impact OWASP A09 : fuite de credential dans les logs.

### Solution technique retenue

Remplacer le log de la valeur par un log uniquement de la clé : confirmer
qu'une modification a eu lieu sans exposer la nouvelle valeur.

**Avant :**
```python
self.logger.log_info(f"Modification : {key} = {new_value}")
```

**Après :**
```python
self.logger.log_info(f"Modification : {key} mis à jour")
```

**Alternative écartée** : liste de clés sensibles à masquer (denylist). Écarté
car une denylist est incomplète par nature (un nom de clé personnalisé peut être
sensible). Logguer uniquement le nom de la clé est suffisant pour l'audit (on
sait QUOI a changé) sans exposer la donnée (on ne sait pas à quoi).

**Alternative écartée** : ne rien logguer. Écarté car le log de la modification
est utile pour l'audit opérationnel — on veut savoir que "password" a été mis
à jour, pas sa valeur.

### Fichiers impactés

- `linux_python_utils/dotconf/manager.py` — ligne 147

---

## Évolutions à mettre en place (Détail Junior)

### `linux_python_utils/dotconf/manager.py`

#### Correction de `update_section()` — ligne 147

**Avant :**
```python
                self.logger.log_info(f"Modification : {key} = {new_value}")
```

**Après :**
```python
                self.logger.log_info(
                    f"Modification : {key} mis à jour"
                )
```

C'est la seule modification de code. Une ligne devient deux (pour le wrapping
à 79 caractères), mais le changement fonctionnel est minime.

#### Docstring de `update_section()` à mettre à jour

Ajouter dans la section Note :
```
        Note:
            Seul le nom des clés modifiées est loggué, pas leur
            valeur, pour éviter d'exposer des données sensibles.
```

#### Conventions PEP

- [x] PEP 8 — Wrapping sur 2 lignes pour respecter 79 caractères
- [x] PEP 257 — Note ajoutée dans la docstring
- [x] PEP 20 — Minimal, une seule raison de changer

---

## Analyse de sécurité

### OWASP Top 10

- [x] A09 Logging Failures — Valeurs sensibles ne sont plus exposées dans les logs
- [x] Audit trail maintenu : le nom de la clé modifiée reste loggué (qui,
    quoi, quand)

### Analyse statique Bandit

- [x] Aucun issue Bandit sur `dotconf/` — confirmé avant et après correction

---

## Principes SOLID

| Principe | Vérification | Statut |
|---|---|------|
| **S** Single Responsibility | Aucun changement d'architecture | ✅ |
| **D** Dependency Inversion | Logger déjà injecté (obligatoire) | ✅ |

---

## Checklist d'implémentation

### Code
- [ ] `manager.py` ligne 147 — remplacer `f"Modification : {key} = {new_value}"`
    par `f"Modification : {key} mis à jour"`
- [ ] `manager.py` — Note dans la docstring de `update_section()`

### Tests (pytest, dans `tests/test_dotconf.py`)
- [ ] `test_update_section_logue_cle_sans_valeur`
    — mock logger, mettre à jour une section, vérifier que `log_info` est
    appelé avec le nom de la clé mais PAS avec la valeur
- [ ] `test_update_section_ne_logue_pas_valeur_sensible`
    — utiliser une clé `"password"` et une valeur `"secret"`, vérifier
    que `"secret"` n'apparaît pas dans les appels à `log_info`

### Validation
- [ ] `pytest tests/test_dotconf.py -v` → tous verts
- [ ] `make test` → zéro régression

---

## Points d'attention

- Les tests existants qui vérifiaient `f"Modification : {key} = {new_value}"`
  dans le message de log devront être mis à jour pour vérifier
  `f"Modification : {key} mis à jour"` à la place.
- Ce changement est non-breaking pour les appelants de `update_section()` —
  uniquement le contenu du log change.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
