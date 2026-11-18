# Marketplace

Exercice technique sur le cycle d’une commande, de sa création au paiement puis à la livraison ou au retour chez le vendeur.

## Démarrage

Il faut Python 3.11 ou plus récent et un serveur PostgreSQL. Utilise la base locale `market place` et un compte PostgreSQL autorisé à y créer les tables. Pour créer la base si nécessaire, exécute `createdb -U postgres "market place"`.

Crée ou complète le fichier `.env` à la racine du projet.

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:TON_MOT_DE_PASSE@localhost:5432/market%20place
```

Adapte le compte, le mot de passe, l’hôte et le port à ton installation. Dans l’URL, l’espace dans `market place` s’écrit `%20`. Encode aussi les caractères spéciaux du mot de passe, par exemple `@` en `%40`. Une variable `DATABASE_URL` déjà définie dans le terminal prend la priorité sur le fichier.

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt

python -m marketplace.db
python -m uvicorn marketplace.api:create_app --factory
```

Sous Linux ou macOS, active l’environnement avec `source .venv/bin/activate`.

`python -m marketplace.db` crée les tables du projet et les identités de démonstration. Tu peux relancer cette commande pour compléter l’initialisation.

Si Windows bloque le binaire de Psycopg, utilise la bibliothèque fournie avec ton installation PostgreSQL. Adapte le chemin au dossier `bin` de ta version.

```powershell
$env:PATH = 'C:\Program Files\PostgreSQL\18\bin;' + $env:PATH
$env:PSYCOPG_IMPL = 'python'
```

## Essayer l’API

Ouvre [Swagger UI sur /docs](http://127.0.0.1:8000/docs). Les requêtes qui modifient une commande utilisent l’en-tête `X-Actor-Id`.

| Requête | Données et identité |
| --- | --- |
| `POST /orders` | `{"seller_id":"seller-1","amount_xof":7500}` avec `buyer-1`. La réponse contient l’ID de la commande. |
| `POST /orders/{id}/payment-notifications` | `{"reference":"mobile-money-001"}` avec `system`. Choisis une nouvelle référence pour chaque nouvelle commande. Pour simuler un doublon, renvoie la même référence à la même commande. |
| `POST /orders/{id}/actions` | `{"action":"accept"}` avec `seller-1`, puis `mark_ready` avec le même vendeur. |
| `POST /orders/{id}/actions` | `{"action":"assign","courier_id":"courier-1"}` avec `system`, puis `pick_up` et `deliver` avec `courier-1`. |
| `GET /orders/{id}` | Renvoie la commande et son historique dans l’ordre des transitions. |

Le service déduit le rôle depuis l’identité de démonstration enregistrée en base. Le livreur `courier-2` permet d’essayer une réaffectation après `withdraw`. Les actions acceptent un champ `reason` facultatif. Le service enregistre automatiquement `customer_unreachable` pour `fail_delivery`.

## Tests

Crée une base PostgreSQL dédiée, par exemple `market place test`, et donne au compte de test le droit d’y créer des schémas. La suite crée un schéma temporaire dans cette base, puis le supprime à la fin.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres:mot-de-passe@localhost:5432/market%20place%20test'
python -m pytest -q
```

Sous Linux ou macOS, configure `TEST_DATABASE_URL` avec `export`. La commande `python -m pytest -q tests/unit` exécute les tests de la machine à états. Les tests dans `tests/integration` couvrent l’API, les notifications de paiement, l’historique et les actions concurrentes. Ils sont ignorés quand `TEST_DATABASE_URL` est absent.

## Structure

- `marketplace/domain/` contient les types métier et la machine à états de la commande.
- `marketplace/services/` contient le service des commandes, le service de paiement et le code partagé qui applique une transition et écrit son historique. Les services reçoivent leurs transactions via les interfaces de `transaction_protocols.py`.
- `marketplace/persistence/` contient les modèles SQLAlchemy et le dépôt PostgreSQL qui exécute les requêtes et gère les transactions.
- `marketplace/db.py` configure la connexion, initialise le schéma et ajoute les acteurs de démonstration.
- `marketplace/api.py` expose les opérations en HTTP. Les tests d’intégration appellent aussi le service directement.

Le tableau des transitions et les hypothèses métier figurent dans [DESIGN.md](DESIGN.md).
