# Marketplace

API d’exercice technique pour suivre le cycle de vie d’une commande. Le projet utilise Python, FastAPI, SQLAlchemy et PostgreSQL. Le paiement et l’identité des acteurs sont simulés.

## Règles métier

- L’acheteur crée sa commande auprès d’un vendeur. Le système confirme le paiement à partir d’une référence unique. Le rejeu de la même notification renvoie l’état courant de la commande et conserve une seule écriture de paiement.
- Le vendeur peut accepter ou refuser une commande payée. L’acheteur peut l’annuler jusqu’à l’acceptation. Le refus d’une commande payée, son annulation ou une confirmation de paiement reçue après l’annulation déclenchent un remboursement simulé.
- Quand le vendeur déclare la commande prête, le système choisit un livreur. Si le livreur se désiste avant la prise en charge, le système cherche un remplaçant parmi les livreurs qui ne se sont pas déjà désistés de cette commande. Sans candidat, la commande attend en `READY`.
- Chaque envoi autorise deux tentatives au maximum. Après le second échec, le livreur confirme le retour de la commande au vendeur.
- Après la remise, le vendeur peut réexpédier la même commande avec un autre livreur et un compteur d’échecs à zéro, ou l’annuler avec un remboursement simulé. La référence de paiement et l’historique restent liés à la commande.
- Chaque transition ajoute une entrée d’historique avec l’acteur, son rôle, la date et l’heure, les états de départ et d’arrivée et, le cas échéant, le motif ou le livreur affecté.

La [note de conception](DESIGN.md) détaille les transitions, les rôles autorisés, le modèle de données, les hypothèses et le diagramme Mermaid.

## Démarrage local

Il faut **Python 3.11 ou plus récent** et un serveur **PostgreSQL** démarré. Les commandes suivantes s’exécutent depuis la racine du dépôt.

### Préparer la base et la connexion

Utilise une base PostgreSQL existante et un compte autorisé à y créer les tables. La commande suivante crée une base locale appelée `market place`.

```sh
createdb -U postgres "market place"
```

Crée un fichier `.env` à la racine du dépôt avec l’URL de ta base. Remplace les valeurs d’exemple par celles de ton installation.

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:TON_MOT_DE_PASSE@localhost:5432/market%20place
```

Encode les espaces du nom de la base en `%20` et les caractères réservés du mot de passe, par exemple `@` en `%40`. Une variable `DATABASE_URL` déjà définie dans le terminal prend la priorité sur `.env`. Git ignore ce fichier.

### Installer et lancer l’application

Sur **Windows**, lance ces commandes dans PowerShell.

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv\Scripts\python.exe -m marketplace.db
& .\.venv\Scripts\python.exe -m uvicorn marketplace.api:create_app --factory
```

Si Windows bloque le binaire fourni avec Psycopg, ajoute le dossier `bin` de ton installation PostgreSQL au `PATH` et sélectionne l’implémentation Python du pilote. Exécute les deux lignes suivantes avant l’initialisation et le lancement, en adaptant le numéro de version.

```powershell
$env:PATH = 'C:\Program Files\PostgreSQL\18\bin;' + $env:PATH
$env:PSYCOPG_IMPL = 'python'
```

Sur **Linux ou macOS**, active l’environnement virtuel avant de lancer le serveur.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m marketplace.db
python -m uvicorn marketplace.api:create_app --factory
```

`python -m marketplace.db` crée les tables manquantes, met à jour la contrainte des actions d’historique et ajoute les acteurs de démonstration. Sur une base déjà initialisée, relance cette commande avant de démarrer cette version pour activer les actions après retour. Ouvre ensuite [Swagger UI](http://127.0.0.1:8000/docs). Le contrat OpenAPI est disponible sur [`/openapi.json`](http://127.0.0.1:8000/openapi.json).

## Acteurs de démonstration

| Rôle | Identifiant |
| --- | --- |
| Acheteur | `buyer-1` |
| Vendeur | `seller-1` |
| Livreurs | `courier-1`, `courier-2` |
| Système | `system` |

Les opérations d’écriture utilisent l’en-tête `X-Actor-Id`. Le service retrouve le rôle de cet acteur en base et vérifie son identité quand l’action est réservée à un participant de la commande. Pour utiliser un autre acheteur, vendeur ou livreur, ajoute son identifiant unique et l’un des rôles `BUYER`, `SELLER` ou `COURIER` dans la table `actors`.

## Démonstration dans Swagger

Les routes sont présentées dans l’ordre **Création**, **Paiement**, **Actions**, **Suivi**. Le menu **Examples** remplit le corps JSON. Sélectionne l’exemple correspondant à l’acteur dans `X-Actor-Id`, puis clique sur **Execute**.

1. **Créer.** Ouvre `POST /orders` avec `buyer-1`. Choisis l’exemple de 7 500 XOF avec `seller-1`. La réponse `201` indique `PENDING_PAYMENT`. Copie son `id` dans `order_id` pour les étapes suivantes.
2. **Payer.** Ouvre `POST /orders/{order_id}/payment-notifications` avec `system`. Utilise une référence neuve, par exemple `demo-commande-42` si la commande porte l’identifiant 42. La réponse indique `PAID`. Réexécute l’appel avec le même identifiant et la même référence pour montrer l’idempotence.
3. **Accepter et préparer.** Dans `POST /orders/{order_id}/actions`, sélectionne **Accepter** (`accept`), puis **Marquer prête** (`mark_ready`), avec `seller-1`. Le système déclenche l’affectation. Si la réponse est `ASSIGNED`, relève le `courier_id` retourné.
4. **Récupérer et confirmer la livraison.** Sélectionne **Récupérer** (`pick_up`), puis **Confirmer la livraison** (`deliver`), avec le livreur indiqué dans `courier_id`. La commande passe à `IN_DELIVERY`, puis à `DELIVERED`.
5. **Consulter le suivi.** Ouvre `GET /orders/{order_id}`. Vérifie l’état final, la présence d’une seule transition de paiement et les deux événements distincts `ACCEPTED → READY` par le vendeur et `READY → ASSIGNED` par le système.

Avec les acteurs initialisés par le projet, le système choisit d’abord `courier-1`. Pour montrer une réaffectation, utilise **Se désister** (`withdraw`) avant **Récupérer**. La réponse indique le remplaçant si un autre livreur est éligible. L’historique conserve les affectations successives.

Si la réponse indique `READY` et `courier_id: null`, la commande attend un livreur. L’exemple **Reprendre une affectation en attente** permet à `system` d’indiquer un livreur éligible, par exemple après son ajout en base. La sélection automatique se fait par ordre d’identifiant. Le système écarte les livreurs qui se sont déjà désistés de cette commande et, après un retour, celui qui a effectué la dernière remise au vendeur.

### Retour au vendeur

Crée une nouvelle commande et avance jusqu’à **Récupérer**. Avec le même livreur, sélectionne **Signaler un échec de livraison** (`fail_delivery`), **Relancer après le premier échec** (`retry_delivery`), puis signale un second échec. Une fois la commande en `RETURN_PENDING`, sélectionne **Confirmer la remise au vendeur** (`confirm_return`). Elle passe à `RETURNED`.

Avec `seller-1`, choisis une suite pour cette commande.

- **Réexpédier la commande retournée** (`reship`). Garde le même `order_id`. Vérifie que `failed_delivery_attempts` vaut `0`. Si le système répond `ASSIGNED`, utilise le nouveau `courier_id` pour **Récupérer**. S’il répond `READY`, la commande attend un autre livreur éligible.
- **Annuler la commande retournée** (`cancel_returned`). La commande passe à `REFUNDED` et l’historique identifie le vendeur qui a demandé le remboursement simulé.

Pour essayer les deux décisions, utilise deux commandes arrivées à `RETURNED`.

## Contrat HTTP

| Route | Entrée et résultat |
| --- | --- |
| `POST /orders` | Acheteur. Corps avec `seller_id` et `amount_xof`, montant entier positif en XOF. Renvoie la commande créée avec le statut HTTP `201`. |
| `POST /orders/{order_id}/payment-notifications` | Système. Corps avec `reference`. Renvoie la commande courante avec le statut HTTP `200`, y compris lors d’un rejeu valide. |
| `POST /orders/{order_id}/actions` | Acteur autorisé pour l’action. Corps avec `action`, `reason` facultatif et `courier_id` requis pour `assign`. Renvoie l’état de la commande à l’issue de l’action avec le statut HTTP `200`. |
| `GET /orders/{order_id}` | Renvoie la commande et son historique ordonné dans `order` et `history`. |

L’API utilise `403` pour une action non autorisée, `404` pour une commande introuvable, `409` pour un conflit de transition ou de paiement et `422` pour une entrée invalide.

## Architecture

| Partie | Responsabilité |
| --- | --- |
| [`marketplace/domain/`](marketplace/domain/) | Modèles métier, rôles et machine à états en Python. |
| [`marketplace/services/`](marketplace/services/) | Services de commande et de paiement. Les services utilisent des interfaces de transaction ciblées. |
| [`marketplace/persistence/`](marketplace/persistence/) | Modèles SQLAlchemy, requêtes et transactions PostgreSQL. |
| [`marketplace/db.py`](marketplace/db.py) | Connexion, initialisation des tables et insertion des acteurs de démonstration. |
| [`marketplace/api.py`](marketplace/api.py) et [`marketplace/swagger_demo.py`](marketplace/swagger_demo.py) | Routes FastAPI, réponses HTTP et exemples de démonstration Swagger. |

Le verrou de ligne PostgreSQL sérialise les actions concurrentes portant sur une même commande. Les contraintes d’unicité empêchent qu’une référence soit utilisée sur deux commandes ou qu’une commande reçoive deux paiements. La transaction valide ensemble les écritures de paiement, l’état de la commande et les entrées d’historique.

## Tests

Les tests unitaires couvrent la machine à états et les exemples OpenAPI. Les tests d’intégration vérifient notamment la livraison, l’affectation et la réaffectation, les décisions du vendeur après retour, le remboursement, les rôles, l’idempotence, les actions concurrentes et le rollback en cas d’échec d’écriture de l’historique.

Pour les tests d’intégration, utilise une base dédiée telle que `market place test` et un compte PostgreSQL qui peut y créer des schémas. Les fixtures créent des schémas temporaires et les suppriment après les tests. Définis `TEST_DATABASE_URL` dans le terminal.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres:TON_MOT_DE_PASSE@localhost:5432/market%20place%20test'
& .\.venv\Scripts\python.exe -m pytest -q
```

Sous Linux ou macOS, utilise `export TEST_DATABASE_URL='…'` et `python -m pytest -q` depuis l’environnement virtuel activé. Pour exécuter uniquement les tests sans base de données, ajoute `tests/unit` à la commande pytest. La suite ignore les tests d’intégration quand `TEST_DATABASE_URL` est absente.

## Utilisation de l’IA

Le projet a commencé par un travail approfondi de conception. Les états et les transitions, les rôles, les hypothèses sur les paiements tardifs et les remboursements, ainsi que les garanties d’idempotence et de concurrence ont été discutés et consignés dans [`DESIGN.md`](DESIGN.md) avant l’implémentation.

J’ai ensuite utilisé **Codex** pour mettre cette conception en code. Il a généré et révisé la machine à états, les services Python, la persistance PostgreSQL et les routes FastAPI. Il a aussi aidé à écrire les tests pytest, à réorganiser les modules par responsabilité et à préparer la démo Swagger. Le code a été relu et vérifié par des tests unitaires et des tests d’intégration avec PostgreSQL.
