# Note de Besoin — Notifier Telegram multi-destinataires
> **Date :** 2026-10-08
> **Statut :** À valider

---

## Le problème
Les alertes des outils n'arrivent aujourd'hui que par Gotify (app, web,
WebSocket). Si l'app est fermée ou si le serveur Gotify est en panne,
l'alerte n'est pas vue. Un projet de canal SMS a été abandonné (destinataires
chez RED by SFR, aucune API SMS exploitable pour un particulier).

## Le résultat attendu
Recevoir chaque notification aussi sur Telegram, en parallèle de Gotify, pour
**4 destinataires**, sans dépendre du serveur Gotify ni de l'opérateur mobile
de chacun. Le canal envoie **toutes** les notifications (succès compris), pas
seulement les échecs.

## Pour qui
Moi et 3 autres personnes (4 destinataires au total), chacune avec son
téléphone.

## Pourquoi maintenant
Le chantier SMS est abandonné ; Telegram est la piste retenue pour un deuxième
canal indépendant de Gotify.

## Critère de succès
C'est réussi si une même notification arrive sur Telegram chez les 4
destinataires, même quand le serveur Gotify est éteint.

## Ce que ce n'est PAS
- Pas un remplacement de Gotify : le push Gotify reste en place.
- Pas de réception ni de commandes (envoi seul, le bot ne répond à rien).
- Pas de canal de secours conditionnel : Telegram est envoyé à chaque fois,
  comme canal à part entière.

## À confirmer (non tranché dans la conversation)
- Telegram est-il déjà installé chez les 3 autres destinataires ?
- Le contenu des notifications (noms de machines, chemins, messages d'erreur)
  peut-il transiter par un cloud tiers ? Les messages d'un bot Telegram ne sont
  pas chiffrés de bout en bout.

---

## ⏸ Validation requise
**Réponds "OK" si cette note reflète bien ton besoin.**
Ensuite j'enchaîne sur `generate-requirements-doc` pour le cahier des charges.
