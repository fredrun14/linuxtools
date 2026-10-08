# Conception — Notifier Telegram multi-destinataires
> **Date :** 2026-10-08
> **Statut :** Q-02 tranchée (option B, 2026-10-08) ; Q-01 : 4 personnes / 4 comptes, installation chez les 3 autres à confirmer (recette en deux temps). Les autres recommandations du §9 sont soumises avec le plan.
> **Entrée :** CDC-20261008-Notifier-Telegram-Multi-Destinataires.md
> **Projet :** linuxtools 2.4.0 → 2.5.0 (mineure, ajout d'un canal)
> **Sources Telegram (consultées le 2026-10-08) :** core.telegram.org/bots/api (Bot API 10.3 du 2026-08-24 : « Making requests », `sendMessage`, `ResponseParameters`, `LinkPreviewOptions`, « Formatting options ») · core.telegram.org/bots/faq (« My bot is hitting limits ») · core.telegram.org/bots (« Bots can't start conversations with users ») · telegram.org/faq (chiffrement des cloud chats).

## 1. Périmètre & impact

| Élément | Impact |
|---|---|
| `notification/telegram.py` | **Nouveau** : `TelegramNotifier(Notifier)` |
| `notification/__init__.py`, `linuxtools/__init__.py` | Export de `TelegramNotifier` |
| `chain.py`, `base.py`, `models.py`, `exceptions.py` | **Inchangés** : `NotifierChain` gère déjà l'isolation entre canaux, `NotificationSendError` suffit |
| `tests/unit/test_notification_telegram.py` | **Nouveau** (le volume des tests anti-fuite justifie un fichier à part) |
| Dépendances | Aucune : stdlib uniquement (`urllib`, `json`, `http.client`, `re`) |
| Réemploi | Même schéma que `GotifyNotifier` (opener injectable, `Logger` optionnel). Le token est chargé **côté consommateur** par `CredentialManager.require(...)` (env → .env → keyring), qui ne journalise que le nom de la clé |

Faits Telegram retenus :
- URL imposée : `https://api.telegram.org/bot<token>/METHOD_NAME`. **Le token est dans le chemin**, aucune alternative par en-tête.
- `chat_id` : « Integer or String ».
- `text` : « 1-4096 characters after entities parsing ».
- Débit : au plus 1 msg/s par chat (« eventually you'll begin receiving 429 errors ») ; environ 30 msg/s au total.
- `retry_after` : « the number of seconds left to wait ».
- Un bot ne peut pas écrire en premier : « A user must either add them to a group or send them a message first ».
- Les chats avec un bot sont des cloud chats : chiffrement client-serveur seulement, pas de bout en bout.

Vérifié par essai local (Python 3.14.8) : si le token contient un espace, `urlopen` lève `http.client.InvalidURL` dont le message contient le chemin, donc le token (`str(exc)`). Pour une erreur HTTP, `HTTPError.url` et `HTTPError.filename` contiennent l'URL complète, token compris ; `str(HTTPError)` seul donne `HTTP Error 403: Forbidden`.

## 2. Modules & interfaces

```python
class TelegramNotifier(Notifier):
    def __init__(self, token: str, recipients: Mapping[str, int],
                 timeout: float = 10.0, include_message: bool = True,  # cf. §9 (c)
                 opener: Callable[..., Any] | None = None,
                 logger: Logger | None = None) -> None: ...
    def send(self, notification: Notification) -> None: ...
```

**Ce que l'appelant doit savoir (l'interface) :**
- `recipients` associe un libellé à un `chat_id` (par exemple `{"fred": 123456789, ...}`). L'ordre d'envoi suit l'ordre du mapping.
- Chaque destinataire doit avoir **démarré le bot** au préalable (/start). Sinon, son envoi échoue avec un 403 ou un 400.
- Le constructeur lève `ValueError` dans ces cas, sans jamais reprendre la valeur fautive dans le message : token mal formé, mapping vide, libellé invalide, `chat_id` qui n'est pas un `int` ou vaut `0` (un `bool` est refusé), `chat_id` en double, `timeout` non > 0 (NaN compris).
- `send` tente **tous** les destinataires, sans nouvel essai. Si au moins un échoue, il lève **une seule** `NotificationSendError` qui liste les libellés en échec et la cause de chacun.
- Durée maximale d'un `send` : N × `timeout`. Les envois sont séquentiels.

**Déroulé de `send` :**
1. Le texte est construit une seule fois (§9 b).
2. Pour chaque destinataire, POST JSON `{"chat_id", "text", "link_preview_options": {"is_disabled": true}}`.
3. Une fonction privée renvoie `None` en cas de succès (HTTP 200), sinon une **raison texte**. Elle rattrape `HTTPError` (puis `exc.close()`), `URLError`, `http.client.HTTPException` et `OSError`.
4. La raison est un libellé fixe par code HTTP, ou le nom du **type** d'exception (`type(exc.reason).__name__` pour une `URLError`). Elle ne reprend jamais `str(exc)`, `repr(exc)`, `exc.url`, `exc.filename`, `geturl()` ni le corps de la réponse.
5. Chaque succès est journalisé par libellé.
6. Après la boucle, donc **hors de tout bloc `except`**, `raise NotificationSendError(...)` si au moins un envoi a échoué. Ainsi `__cause__` et `__context__` valent `None`.

**Grille modules profonds :**

| Critère | `TelegramNotifier` (1 notifier, N destinataires) |
|---|---|
| Test de suppression | Sans lui, chaque consommateur réécrit la boucle, l'isolation, l'agrégation et les garde-fous anti-fuite. **Il garde sa place** |
| Levier | 1 constructeur + `send` ; validation, format, troncature, classement des erreurs et anti-fuite restent internes |
| Fuite d'implémentation | Une seule précondition hors code, l'amorçage /start, documentée dans la docstring et le README |
| Surface de test | Tout passe par `send` et l'`opener` injecté (seam existant, déjà utilisé par Gotify) ; les fonctions privées sont testées à travers `send` |
| `TelegramRecipient` (dataclass) | **Échoue au test de suppression** : il ne porterait que la validation, déjà assurée par le constructeur. Un `Mapping[str, int]` garantit aussi l'unicité des libellés gratuitement → écarté |
| Exception dédiée | Aucun appelant n'exploite de données structurées (`NotifierChain` lit `str(exc)`) → `NotificationSendError` suffit |

## 3. SOLID par responsabilité

| Classe/module | S | O | L | I | D |
|---|---|---|---|---|---|
| `TelegramNotifier` | Diffuser une `Notification` vers N chats d'un même bot | Nouveau canal = nouveau `Notifier` (ABC existante, 5 implémentations : seam réel) | Respecte le contrat : `send` ne lève que `NotificationSendError` (rattrapage exhaustif de la liste ci-dessus) | `send` uniquement | `opener` et `logger` injectés ; token et destinataires injectés **en valeurs** (chargés par le consommateur) |
| Mise en forme (fonction privée pure) | `Notification` → texte borné | N/A | N/A | Testée via `send` | Aucune |
| Classement des erreurs (fonction privée) | Exception → raison sûre | N/A | N/A | Testée via `send` | Aucune |
| `NotifierChain` | Inchangée | — | — | — | — |

Pas de `Protocol` HTTP partagé avec Gotify : voir §9 (f).

## 4. Choix de bibliothèques

| Besoin | Retenu | Écarté | Raison |
|---|---|---|---|
| HTTP | `urllib.request` (+ `http.client` pour les exceptions) | `requests`, `python-telegram-bot` | Stdlib uniquement (CLAUDE.md) ; un seul appel POST |
| Sérialisation | `json` | form-urlencoded | Les deux sont acceptés par l'API ; JSON est cohérent avec Gotify et garde `chat_id` en entier |
| Validation | `re.fullmatch` | `re.match` avec `^…$` | `$` accepte un saut de ligne final |

## 5. Décisions structurantes

- 📌 À consigner en ADR : un seul `TelegramNotifier` pour N destinataires (`Mapping[libellé, chat_id]`), isolation par destinataire, une exception agrégée, aucun nouvel essai.
- 📌 À consigner en ADR : le token étant dans le chemin de l'URL, les erreurs sont classées en raisons fixes, levées hors `except`, sans `str(exc)` ni chaînage. Cette règle vaut pour tout futur notifier dont l'URL contient un secret.
- 📌 À consigner en ADR : texte brut sans `parse_mode`, troncature conservatrice (§9 b).
- 📌 À consigner en ADR : pas d'abstraction HTTP commune tant qu'il n'existe pas un 3ᵉ notifier HTTP.

Emplacement : `/home/fred/obsidian-perso/fredvault/1-projets/linuxtools/adr/`.

## 6. Sécurité

CDC §7 : appel sortant vers un cloud tiers, secret (token), données potentiellement sensibles (Q-02). Section obligatoire (A04 *Insecure Design*).

| Menace / surface | Frontière de confiance | Contrôle retenu | Module porteur |
|---|---|---|---|
| **Token dans le chemin de l'URL** : `HTTPError.url`/`.filename`/`geturl()`, message d'`InvalidURL` (vérifié), `Request.full_url`, chaînage visible dans les traces et dans le `{exc}` de `NotifierChain` | Notifier → logs et exceptions du consommateur | Raisons fixes ou noms de type, jamais `str`/`repr`/`url` de l'exception ; `raise` après la boucle, hors `except` (`__cause__`/`__context__` à `None`) ; URL jamais journalisée | `TelegramNotifier` |
| Token mal formé (espace, `/`, `?`, `#`) : `InvalidURL` qui fuit, ou injection dans le chemin | Configuration → URL | `re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+")` à la construction (motif tiré de l'exemple officiel `123456:ABC-DEF…`) ; `ValueError` sans la valeur. ⚠️ HYPOTHÈSE À VALIDER : la doc ne spécifie pas formellement le jeu de caractères ; à vérifier sur le vrai token | `TelegramNotifier` |
| Token visible via `repr` ou `vars` | Objet → logs et débogage | Classe ordinaire (pas une dataclass), attribut privé. Un test vérifie l'absence de la sentinelle dans `repr(notifier)` et bloque une conversion future en dataclass | `TelegramNotifier` |
| Token en clair dans le code ou le transport | Hôte → Internet | Token injecté (chargé par `CredentialManager`) ; base `https://api.telegram.org` **constante**, sans paramètre `base_url`, donc pas de repli en http ; vérification TLS par défaut d'urllib | Consommateur, `TelegramNotifier` |
| Contenu des notifications chez un tiers (Q-02), sans chiffrement de bout en bout | Hôte → cloud Telegram | Aperçu des liens désactivé (`link_preview_options.is_disabled`), pour que Telegram ne visite pas les URL du texte ; le reste dépend de Q-02 (§9 c) | `TelegramNotifier`, README |
| `chat_id` des destinataires (sensible selon l'hypothèse du CDC) | Notifier → logs | Logs et exceptions n'affichent que les **libellés** ; libellés limités à `[A-Za-z0-9_-]{1,32}` par `re.fullmatch` (pas d'injection de saut de ligne dans les logs) | `TelegramNotifier` |
| Texte distant reflété dans les logs | Telegram → logs | Le corps des réponses d'erreur (`description`) n'est **pas** lu | `TelegramNotifier` |
| Une réponse malformée interrompt la boucle | Réseau → boucle | Rattrapage de `HTTPError`, `URLError`, `http.client.HTTPException`, `OSError` ; `HTTPError` fermée | `TelegramNotifier` |
| Script bloqué | Réseau → consommateur | `timeout` > 0 validé (NaN rejeté) ; aucun nouvel essai ; borne N × `timeout` documentée | `TelegramNotifier` |

📌 À consigner en ADR : validation du token et des destinataires au seul constructeur (lieu unique) ; règle « raison fixe, `raise` hors `except` ».

## 7. Risques & points ouverts

- **Q-01 non tranchée** : sans Telegram chez les 3 autres, le critère « 4 destinataires » n'est pas recettable. Prévoir une recette en deux temps (§8).
- **Codes d'erreur non documentés** : la doc officielle ne décrit pas les erreurs 403 « bot bloqué » et 400 « chat introuvable » ; `error_code` « is subject to change ». Seuls les libellés en dépendent, pas le comportement.
- **Résolution DNS hors timeout** : `getaddrinfo` n'est pas borné par le `timeout` d'urllib, donc un `send` peut dépasser N × `timeout` si le DNS est en panne. Accepté et documenté.
- **429 peu probable** : 1 message par chat par notification, 4 chats, bien en dessous des limites. Seul un consommateur qui envoie en rafale vers le même chat (plus d'un message par seconde) le déclencherait.
- **Texte vide côté Telegram** : un titre et un message composés uniquement d'espaces donneraient sans doute un 400. Cas marginal ; `Notification` impose seulement un contenu non vide.
- **Hors périmètre** : défauts de `GotifyNotifier` (pas de rattrapage de `HTTPException`, timeout non validé, `HTTPError` non fermée). Ticket bugfix séparé.

## 8. Impact sur le plan

| # | Tâche | Tags |
|---|---|---|
| 1 | Constructeur : token (`fullmatch`), mapping non vide, libellés (`fullmatch`), `chat_id` (`int` hors `bool`, ≠ 0, sans doublon), `timeout` > 0 et NaN ; messages d'erreur sans les valeurs | [TDD] [SEC] |
| 2 | Mise en forme : `titre\n\nmessage`, troncature au budget UTF-16 sans couper de paire de substitution, suffixe de troncature, `include_message` (si retenu en §9 c) | [TDD] |
| 3 | `send` nominal : URL, payload JSON (`chat_id` entier, `text`, `link_preview_options`), ordre du mapping, log de succès par libellé | [TDD] |
| 4 | Isolation : `HTTPError` 400/401/403/404/429/500 (avec `close()` vérifié), `URLError` (gaierror, refus, SSL), `RemoteDisconnected`, `InvalidURL`, `BadStatusLine`, `TimeoutError`, statut ≠ 200 ; les autres destinataires sont tout de même tentés ; une seule exception agrégée | [TDD] [SEC] |
| 5 | Anti-fuite avec sentinelles (token et `chat_id`) dans `str`/`repr` de l'exception, `repr(notifier)`, `__cause__` et `__context__` à `None`, `traceback.format_exception`, appels au `Logger` mocké, messages des `ValueError` ; opener qui lève une `HTTPError` dont l'`url` contient le token, et une `InvalidURL` qui contient le chemin | [TDD] [SEC] |
| 6 | Intégration avec `NotifierChain` : échec partiel, le log `{exc}` de la chaîne ne contient aucune sentinelle, Gotify continue | [TDD] [SEC] |
| 7 | Exports, `mypy --strict` à 0, `bandit -ll`, couverture ≥ 80 % sur `telegram.py` | — |
| 8 | Documentation : docstrings FR ; README (création du bot via @BotFather, amorçage /start, récupération des `chat_id`, token via `CredentialManager`, avertissement Q-02, débit) ; CHANGELOG ; 2.4.0 → 2.5.0 ; ADR (§5) ; note Obsidian du module notification | — |
| 9 | Recette manuelle avec un vrai bot : (a) Fred seul, serveur Gotify arrêté ; (b) les 3 autres après Q-01 et leur /start ; (c) un destinataire qui a bloqué le bot → 403 signalé, les autres reçoivent | — |

## 9. Décisions à valider

| # | Question | Options | Recommandation motivée |
|---|---|---|---|
| a | Modèle de destinataire | (1) `Mapping[str, int]` libellé → `chat_id` ; (2) dataclass `TelegramRecipient` ; (3) `chat_id` en `int \| str` (@canal) ; (4) un notifier par destinataire ; (5) un groupe Telegram unique (1 `chat_id`) | **(1)**. La dataclass échoue au test de suppression. Le @canal est inutile pour 4 chats privés, et un canal public exposerait le contenu. Avec (4), les logs de la chaîne seraient indiscernables (4 × « TelegramNotifier »), le token serait passé 4 fois et les doublons ne seraient pas détectables. Le groupe (5) est simple, mais il est écarté par la contrainte « un chat_id chacun » et il ferait perdre le signalement par destinataire (F-04). Le notifier accepte N ≥ 1 destinataires : le chiffre 4 relève de la configuration |
| b | Format et troncature | (1) texte brut sans `parse_mode` ; (2) MarkdownV2 (18 caractères à échapper : `_*[]()~`>#+-=\|{}.!`) ; (3) HTML (`<`, `>`, `&` à échapper) | **(1)**. Aucun échappement, donc pas de 400 « can't parse entities » sur un nom d'hôte, un chemin ou un tiret. Le seul coût est un titre non gras. Troncature : la doc dit « 4096 characters » sans préciser l'unité ; on borne à **4096 unités UTF-16**, ce qui reste sûr quelle que soit l'unité réelle, avec un suffixe indiquant la troncature. ⚠️ HYPOTHÈSE À VALIDER si un message de 4096 points de code doit passer intact |
| c | Q-02 (contenu chez un tiers) — **TRANCHÉ le 2026-10-08 : option (2), `include_message=False` par défaut** | (1) documentation seule ; (2) option `include_message=False` : titre seul (`✓/✗ script — succès/échec`), le résumé (hôte, chemins, erreurs) reste sur Gotify ; (3) mise en forme injectable (masquage libre) | Q-02 est à trancher **avant le plan**. Si la réponse est « oui, tout peut transiter » : (1), avec le paramètre retiré de l'interface (YAGNI). Si c'est « titre oui, détail non » : (2), avec `False` **par défaut** (échec fermé). (3) est écarté : un seul cas d'usage, donc une abstraction prématurée. Si c'est « non, rien » : Telegram ne convient pas et le chantier s'arrête. Dans tous les cas, l'aperçu des liens est désactivé et `protect_content` n'est **pas** activé (il empêcherait de transférer une alerte sans réduire l'exposition au cloud) |
| d | Amorçage des destinataires (lié à Q-01) | (1) procédure README : chaque destinataire ouvre `t.me/<bot>` et appuie sur Démarrer, puis Fred lit son `chat_id` une fois via `getUpdates` ; (2) méthode `discover_chat_ids()` dans la lib | **(1)**. (2) ferait entrer la réception dans le périmètre, contre F-05. Le README prévient que l'appel manuel à `getUpdates` met le token dans l'historique du shell et dans la ligne de commande visible par `ps`, et propose de le lire depuis une variable d'environnement. Les messages 403 et 400 rappellent « bot bloqué ou jamais démarré » pour guider la recette |
| e | 429 | (1) aucun nouvel essai, signalé comme les autres échecs ; (2) attendre `retry_after` puis réessayer | **(1)**. Le CDC et l'enseignement 7 excluent les nouveaux essais ; une attente de `retry_after` bloquerait le script consommateur pour une durée fixée par un tiers ; le volume rend le 429 improbable. Le corps de la réponse n'est pas lu, donc `retry_after` n'est pas affiché |
| f | Abstraction partagée avec Gotify | (1) aucune, environ 15 lignes de requête dupliquées ; (2) aide `_post_json` commune | **(1)**. Les politiques d'erreur divergent : Gotify chaîne `from exc` (son token est dans un en-tête, donc pas de fuite) et lève dès le premier échec ; Telegram interdit le chaînage et agrège. Une aide commune devrait soit imposer la règle anti-fuite à Gotify, soit être paramétrée : interface plus large pour peu de levier. À revoir au 3ᵉ notifier HTTP |
| g | Sémantique d'un échec partiel | (1) lever dès qu'au moins un destinataire échoue ; (2) lever seulement si tous échouent et journaliser les échecs partiels | **(1)**, conforme à F-04 (« signalé à l'appelant »). Conséquence : `NotifierChain.send` compte ce canal comme en échec même si 3 destinataires sur 4 ont reçu. Le log de la chaîne montre quels libellés ont échoué. F-04 est encore balisé `⚠️ HYPOTHÈSE À VALIDER` dans le CDC |
| h | `Urgency.LOW` → `disable_notification` | (1) non ; (2) oui | **(1)**. Ce n'est pas dans le CDC, et `ExecutionReport` ne produit que NORMAL ou CRITICAL : l'option n'aurait aucun effet sur les rapports |
