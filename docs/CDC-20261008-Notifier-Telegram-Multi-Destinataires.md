# Cahier des Charges — Notifier Telegram multi-destinataires
> **Date :** 2026-10-08
> **Statut :** Validé (Q-02 tranchée le 2026-10-08 ; Q-01 : recette en deux temps)
> **Auteur :** Frederic
> **Source :** `docs/BESOIN-20261008-1910-Notifier-Telegram-Multi-Destinataires.md`

---

## 1. Contexte et Problématique

### Problème à résoudre
Les alertes des outils n'arrivent aujourd'hui que par Gotify (app, web,
WebSocket). Si l'app est fermée ou si le serveur Gotify est en panne,
l'alerte n'est pas vue. Un projet de canal SMS a été abandonné (destinataires
chez RED by SFR, aucune API SMS exploitable pour un particulier).

### Solution envisagée
Recevoir chaque notification aussi sur Telegram, en parallèle de Gotify, pour
4 destinataires, sans dépendre du serveur Gotify ni de l'opérateur mobile de
chacun. Le canal envoie toutes les notifications (succès compris).

---

## 2. Périmètre

### Inclus (In Scope)
- [ ] Envoi de chaque notification sur Telegram vers 4 destinataires
- [ ] Fonctionnement en parallèle de Gotify, indépendant de son serveur
- [ ] Toutes les notifications, succès compris (pas de filtre par urgence)

### Exclu (Out of Scope)
- Remplacement de Gotify (le push Gotify reste en place)
- Réception de messages ou commandes (envoi seul)
- Canal de secours conditionnel : Telegram est envoyé à chaque fois

---

## 3. Parties Prenantes

| Rôle           | Nom / Équipe | Responsabilité               |
|----------------|--------------|------------------------------|
| Commanditaire  | Frederic     | Valide les objectifs         |
| Développeur    | Frederic     | Implémente la solution       |
| Utilisateur    | Frederic + 3 autres personnes | Reçoivent les alertes sur leur téléphone |

---

## 4. Objectifs Fonctionnels

| ID   | Priorité    | Description                                              |
|------|-------------|----------------------------------------------------------|
| F-01 | Must have   | Envoyer une même notification sur Telegram à 4 destinataires, chacun avec son propre téléphone |
| F-02 | Must have   | Envoyer toutes les notifications, succès compris, sans filtre |
| F-03 | Must have   | Fonctionner en parallèle de Gotify et sans dépendre de son serveur |
| F-04 | Should have | L'échec d'envoi vers un destinataire n'empêche pas les autres, et est signalé à l'appelant (une seule `NotificationSendError` agrégée) |
| F-05 | Won't have  | Réception de messages ou de commandes par le bot |
| F-06 | Must have   | Par défaut, **seul le titre** de la notification part sur Telegram (ex. `✗ backup-nas — échec`) ; le résumé détaillé (machine, chemins, messages d'erreur) reste sur les autres canaux (décision Q-02, option B) |

---

## 5. Objectifs Non-Fonctionnels

| Critère         | Exigence                                      |
|-----------------|-----------------------------------------------|
| Performance     | [...]                                         |
| Disponibilité   | Indépendant du serveur Gotify (cf. F-03)      |
| Sécurité        | cf. section 7                                 |
| Maintenabilité  | [...]                                         |
| Portabilité     | [...]                                         |

---

## 6. Contraintes Techniques

| Type          | Contrainte                                               |
|---------------|----------------------------------------------------------|
| Langage       | [...]                                                    |
| Environnement | [...]                                                    |
| Dépendances   | [...]                                                    |
| Infrastructure| [...]                                                    |
| Données       | [...]                                                    |

> Les contraintes propres au dépôt (`CLAUDE.md` de `linuxtools`) ne sont pas
> dans la note de besoin : elles sont reprises à l'étape conception.

---

## 7. Exposition et Surface d'Attaque

- [ ] **Local uniquement** — Pas d'exposition réseau
- [x] **Réseau : appel sortant** — Appel HTTPS sortant vers l'API Telegram (aucune exposition entrante)
- [ ] **Réseau interne** — Accessible sur le LAN
- [ ] **Exposé Internet** — API publique / interface web

> Confirmé : l'envoi Telegram est un appel sortant vers un service cloud
> tiers, donc une I/O réseau. Les skills suivants sont activés :
> `python-owasp-security`, `python-sast-bandit-security`,
> `python-security-monitoring`.

### Exigences de sécurité

| Critère                    | Exigence                                                        |
|----------------------------|-----------------------------------------------------------------|
| Données sensibles          | Token du bot (ne doit jamais fuiter dans logs ou exceptions) ; identifiants de conversation des destinataires (sensibles : n'apparaissent ni dans les logs ni dans les exceptions) ; contenu des notifications : le détail ne part pas chez le tiers, seul le titre (Q-02 B, F-06) |
| Authentification           | [...]                                                           |
| Autorisation               | [...]                                                           |
| Entrées non fiables        | [...]                                                           |
| Surfaces dangereuses       | [...]                                                           |
| Secrets                    | Token du bot : jamais en dur ; lieu de stockage [...]           |
| Traçabilité                | [...]                                                           |

---

## 8. Critères d'Acceptation

> La fonctionnalité est **terminée** quand :

- [ ] Une même notification arrive sur Telegram chez les 4 destinataires, même quand le serveur Gotify est éteint (critère de succès du besoin)
- [ ] Toutes les notifications sont envoyées, succès comme échecs
- [ ] Le token du bot n'apparaît dans aucun log ni aucun message d'exception
- [ ] Tests unitaires passent avec couverture ≥ 80 %
- [ ] Aucun warning Bandit sévérité MEDIUM ou supérieure
- [ ] Documentation (README, docstrings) à jour

---

## 9. Livrables Attendus

| Livrable              | Description                         | Échéance    |
|-----------------------|-------------------------------------|-------------|
| Code source           | Module(s) Python dans `src/`        |             |
| Tests                 | `tests/` avec couverture ≥ 80 %     |             |
| Documentation         | `README.md` + docstrings PEP 257    |             |

---

## 10. Questions Ouvertes

| ID  | Question                                                                 | Responsable | Statut |
|-----|--------------------------------------------------------------------------|-------------|--------|
| Q-01| Telegram est-il déjà installé chez les 3 autres destinataires ?          | Frederic    | **Partiel** : 4 destinataires = 4 personnes, 4 comptes distincts (un téléphone + un PC du même compte = 1 destinataire). Installé chez Frederic (téléphone et PC) ; l'installation chez les 3 autres reste à confirmer avant la recette (recette en deux temps) |
| Q-02| Le contenu des notifications (noms de machines, chemins, messages d'erreur) peut-il transiter par un cloud tiers ? Les messages d'un bot ne sont pas chiffrés de bout en bout. | Frederic | **Tranché (option B, 2026-10-08)** : seul le titre part sur Telegram, le détail reste sur Gotify (F-06) |

---

## ⏸ Validation requise

**Ce cahier des charges doit être validé avant le démarrage.**
Répondre **"OK"** pour passer à l'étape suivante (`python-plan-todo`).
