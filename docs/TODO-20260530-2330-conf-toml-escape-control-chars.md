# FIX — ConfTomlExporter : échapper les caractères de contrôle
> **Date :** 2026-05-30 à 23:30
> **Complexité estimée :** Faible

---

## Contexte

### Problématique
`ConfTomlExporter._toml_escape` échappe `\`, `"`, `\n`, `\r`, `\t` mais
**pas les autres caractères de contrôle** (0x00–0x1F, ex. ESC `\x1b`).
Or TOML **interdit les caractères de contrôle bruts** dans une chaîne
basique. Conséquence : un fichier contenant des séquences ANSI (prompts
zsh colorés : `\x1b[32m…`) produit un TOML **invalide**, et `tomllib`
plante à la relecture :

```
tomllib.TOMLDecodeError: Illegal character '\x1b'
```

### Solution technique retenue
Après les remplacements existants, convertir tout caractère de contrôle
restant en séquence `\uXXXX` (forme acceptée par TOML). Round-trip
préservé : `tomllib` redécode `` → ESC, `ConfigApplier` réécrit
l'octet original.

### Fichiers impactés
- `src/linux_python_utils/dotconf/conf_toml_exporter.py` — `_toml_escape`
- `tests/test_dotconf_conf_toml_exporter.py` — cas ANSI/contrôle

---

## Évolutions à mettre en place

### `conf_toml_exporter.py`
`re` est déjà importé. Ajouter une regex module-level :
```python
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
```
(exclut 0x09 `\t`, 0x0a `\n`, 0x0d `\r`, déjà gérés)

`_toml_escape` :
```python
@staticmethod
def _toml_escape(value: str) -> str:
    value = (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return _CONTROL_CHARS.sub(
        lambda m: f"\\u{ord(m.group()):04x}", value
    )
```
> L'ordre est correct : l'échappement du backslash est fait en premier ;
> les `\n/\r/\t` deviennent des séquences 2 caractères (plus des
> caractères de contrôle) avant l'application de la regex.

#### Conventions
- [x] PEP 8 / 257 / 484 — inchangé sur la signature
- [x] PEP 20 — une regex unique, round-trip garanti

---

## Checklist d'implémentation

### Code
- [ ] `_CONTROL_CHARS` (module-level)
- [ ] `_toml_escape` : sub des caractères de contrôle → `\uXXXX`

### Tests (`tests/test_dotconf_conf_toml_exporter.py`)
- [ ] `test_export_echappe_esc_ansi` : source avec `\x1b[..m` → TOML
      **parseable** par `tomllib`
- [ ] round-trip : la valeur décodée contient bien `\x1b`
- [ ] non-régression : `\n/\t/"` toujours corrects

### Documentation
- [ ] (aucune — fix interne)

---

## Points d'attention

- **TOML produit déjà sur disque** (ex. `/tmp/zsh_toml/zsh/spectrum.zsh.toml`)
  contient l'ESC brut : invalide. Après le fix, **re-exporter**
  (`rm -rf` + `zsh-export`) pour régénérer des TOML valides.
- **`fedora_post_install`** consomme la lib en éditable : fix immédiat.
- Ne pas toucher au reste de l'exporter (parsing, rendu) — seul
  l'échappement est en cause.

---

## ⏸ Validation requise

**Ce plan doit être validé explicitement avant toute modification du code source.**
Répondre **"OK"** pour démarrer l'implémentation.
