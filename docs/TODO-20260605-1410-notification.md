# MODULE NOTIFICATION — VALIDATION CARACTÈRES DE CONTRÔLE
> **Date :** 2026-06-05 à 14:10
> **Complexité estimée :** Faible
> **Verdict revue :** Go conditionnel
> **Source :** `PLAN_ACTION_REVUE.md` § notification

---

## Contexte

### Problématique
`config.py` génère du **code shell** (`to_bash_function`, l.86). Les champs
`title`/`message` ne sont validés que « non vides » : un saut de ligne ou un
caractère de contrôle dans la source n'est pas neutralisé en amont (même si
`to_bash_call_*` utilise correctement `shlex.quote()`). De plus, le nom d'app
`"Flatpak"` est codé en dur dans un module générique.

### Solution technique retenue
Interdire les caractères de contrôle dans `__post_init__` (cohérent avec le fix
récent `ConfTomlExporter`). Externaliser le nom d'application.

### Fichiers impactés
- `src/linux_python_utils/notification/config.py`
- `tests/test_notification.py`

---

## Évolutions à mettre en place (Détail Junior)

### `config.py` — 🟠 MAJEUR (validation source)
Dans `__post_init__` (l.53-64), après le contrôle « non vide » :
```python
for champ, valeur in (("title", self.title), ("message", self.message)):
    if any(ord(c) < 32 for c in valeur):
        raise ValueError(
            f"Caractère de contrôle interdit dans '{champ}'."
        )
```

### `config.py` — 🟡 MINEUR (externaliser l'app)
Remplacer le `"Flatpak"` codé en dur (l.102) par un attribut de la dataclass
(ex. `app_name: str = "Flatpak"`) utilisé dans `to_bash_function`.

### Gestion d'erreurs
| Cas | Condition | Action |
|---|---|---|
| Champ vide | `not valeur.strip()` | `raise ValueError` (déjà présent) |
| Caractère de contrôle | `ord(c) < 32` | `raise ValueError` |

---

## Analyse de sécurité (OWASP / Bandit)
- [ ] A03 Injection — `shlex.quote` conservé + source nettoyée.
- [ ] B604/B605 — pas de `shell=True` côté Python (génération de texte bash).
- [ ] `bandit -r src/linux_python_utils/notification/ -ll -ii`

---

## Checklist d'implémentation

### Code
- [x] `config.py` — rejet caractères de contrôle dans `__post_init__`
- [x] `config.py` — attribut `app_name`

### Tests (pytest)
- [x] `test_title_avec_newline_leve_valueerror()`
- [x] `test_message_avec_caractere_controle_leve_valueerror()`
- [x] `test_to_bash_call_echappe_entree_hostile()`
- [x] `test_app_name_defaut_flatpak()` + `test_app_name_personnalise_dans_bash_function()`
- [x] 19/19 passed, bandit 0 issue

### Documentation
- [x] Docstring : contrat sur les caractères autorisés

---

## Points d'attention
- Conserver `shlex.quote` (défense en profondeur, en plus de la validation source).
- Module générant du code exécuté ailleurs → traiter les entrées comme non fiables.

---

## ⏸ Validation requise
**Aucun code modifié avant approbation.** Répondre **"OK"** pour démarrer.
