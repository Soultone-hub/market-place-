# Note de conception de la place de marché

Une commande relie un acheteur à un vendeur. Le système confirme le paiement mobile money et assigne un livreur une fois la commande prête. Chaque transition validée est enregistrée dans l’historique.

## États et transitions

| Action | État de départ | État d’arrivée | Rôle autorisé et condition |
| --- | --- | --- | --- |
| Créer la commande | — | `PENDING_PAYMENT` | Acheteur qui passe la commande |
| Confirmer le paiement | `PENDING_PAYMENT` | `PAID` | Système, à la réception de la notification de succès |
| Annuler avant confirmation du paiement | `PENDING_PAYMENT` | `CANCELLED` | Acheteur de la commande |
| Traiter une confirmation reçue après l’annulation | `CANCELLED` | `REFUNDED` | Système, à la réception d’une première notification de succès |
| Annuler après confirmation du paiement | `PAID` | `REFUNDED` | Acheteur de la commande |
| Refuser la commande | `PAID` | `REFUNDED` | Vendeur de la commande |
| Accepter la commande | `PAID` | `ACCEPTED` | Vendeur de la commande |
| Déclarer la commande prête | `ACCEPTED` | `READY` | Vendeur de la commande |
| Assigner un livreur | `READY` | `ASSIGNED` | Système, avec l’identifiant du livreur |
| Se désister | `ASSIGNED` | `READY` | Livreur assigné. L’affectation est effacée. |
| Récupérer la commande | `ASSIGNED` | `IN_DELIVERY` | Livreur assigné |
| Confirmer la livraison | `IN_DELIVERY` | `DELIVERED` | Livreur assigné |
| Signaler un premier échec | `IN_DELIVERY` | `RETRY_PENDING` | Livreur assigné. Le client est injoignable. |
| Relancer la livraison | `RETRY_PENDING` | `IN_DELIVERY` | Même livreur, pour l’unique nouvelle tentative |
| Signaler un second échec | `IN_DELIVERY` | `RETURN_PENDING` | Livreur assigné. Le client est toujours injoignable. |
| Confirmer la remise au vendeur | `RETURN_PENDING` | `RETURNED` | Livreur assigné |

L’acheteur peut annuler depuis `PENDING_PAYMENT` ou `PAID`. Dès que le vendeur accepte la commande (`ACCEPTED`), l’annulation par l’acheteur est interdite.

`REFUNDED`, `DELIVERED` et `RETURNED` sont des états finaux. Chaque action vérifie le rôle de l’acteur. Pour une commande existante, l’identité d’un acheteur, d’un vendeur ou d’un livreur doit aussi correspondre à celle enregistrée sur la commande. Une action hors tableau est rejetée sans modification ni ajout à l’historique.

## Modèle de données

Les données sont stockées dans PostgreSQL. Les acheteurs (`BUYER`), les vendeurs (`SELLER`) et les livreurs (`COURIER`) partagent la table `actors`, car ils ont les mêmes champs dans cet exercice. Chaque identité de démonstration possède un rôle. Une identité technique `SYSTEM` permet aussi d’attribuer au système ses actions dans l’historique.

| Table | Données et contraintes |
| --- | --- |
| `actors` | `id` (primary key), `role` (`BUYER`, `SELLER`, `COURIER`, or `SYSTEM`) |
| `orders` | `id` (primary key), `buyer_id`, `seller_id`, `courier_id` (foreign keys to `actors`, with only `courier_id` nullable), `amount_xof` (positive integer), `status`, `failed_delivery_attempts` (0 to 2, defaults to 0) |
| `payments` | `reference` (primary key), `order_id` (unique foreign key to `orders`), `received_at` (UTC) |
| `order_history` | `id` (primary key), `order_id` (foreign key to `orders`), `actor_id` (foreign key to `actors`), `actor_role` (role at the time of the action), `action`, `from_status` (null on creation), `to_status`, `occurred_at` (UTC), `reason` (optional), `assigned_courier_id` (foreign key to `actors`, required for assignment events and null otherwise) |

Le service lit le rôle depuis `actors` à partir de l’identifiant simulé. Il vérifie aussi le rôle du vendeur à la création et celui du livreur à l’affectation.

La création de la commande et chaque changement d’état validé ajoutent une entrée à `order_history` dans la même transaction que l’écriture de la commande. Chaque entrée indique l’identifiant et le rôle de l’acteur. L’acheteur est identifié lorsqu’il crée ou annule la commande, et le vendeur lorsqu’il l’accepte, la refuse ou la déclare prête. L’historique se lit par ordre croissant d’identifiant. L’action distingue notamment un remboursement après annulation d’un remboursement après refus. Le motif `customer_unreachable` est enregistré à chaque échec de livraison.

Pour une affectation, l’entrée identifie le système dans `actor_id` et le livreur choisi dans `assigned_courier_id`. En cas de désistement, `orders.courier_id` est vidé et le désistement est tracé. Les entrées d’affectation conservent le livreur et l’heure de chaque affectation successive.

## Idempotence des notifications de paiement

Pour toute action qui peut modifier une commande existante, le service ouvre une transaction `READ COMMITTED` et verrouille la ligne avec `SELECT ... FOR UPDATE` avant de vérifier l’état. Deux actions sur la même commande sont ainsi traitées l’une après l’autre. Si l’acceptation est validée en premier, l’annulation voit l’état `ACCEPTED` et est rejetée. [Documentation PostgreSQL sur les verrous de ligne](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS)

Pour une notification de paiement, le système recherche la référence avant de vérifier si la transition est encore possible. Si elle est déjà associée à cette commande, il renvoie l’état courant avec succès sans écrire dans l’historique. Les contraintes d’unicité de `payments.reference` et de `payments.order_id` empêchent de réutiliser la même référence pour deux commandes ou d’enregistrer deux références pour une seule commande. Ces cas donnent lieu à un conflit, même en cas d’insertions simultanées.

Pour une nouvelle référence valide, l’enregistrement du paiement, la mise à jour de la commande et l’ajout à l’historique sont validés dans la même transaction. Si une étape échoue, toutes ces écritures sont annulées.

## Hypothèses métier

- Une commande a un seul paiement intégral. La notification simulée confirme le succès du paiement pour le montant attendu. La référence est unique sur la plateforme.
- Une annulation avant confirmation passe à `CANCELLED`. Si le paiement est confirmé plus tard, la commande passe directement à `REFUNDED`. Une annulation après paiement ou un refus du vendeur produit aussi un remboursement simulé en un changement d’état.
- Une commande libérée par un livreur revient à `READY`, disponible pour une nouvelle affectation par le système. Après la prise en charge, le même livreur effectue la nouvelle tentative puis, si nécessaire, rapporte la commande au vendeur.
- Le retour est considéré comme terminé quand le livreur confirme la remise au vendeur. L’énoncé laisse ouverte la suite financière de ce retour. Le modèle conserve le paiement enregistré à cette étape.

## Diagramme des états

```mermaid
stateDiagram-v2
    [*] --> PENDING_PAYMENT : Créer la commande
    PENDING_PAYMENT --> PAID : Confirmer le paiement
    PENDING_PAYMENT --> CANCELLED : Annuler
    CANCELLED --> REFUNDED : Confirmer le paiement en retard
    PAID --> REFUNDED : Annuler ou refuser
    PAID --> ACCEPTED : Accepter
    ACCEPTED --> READY : Déclarer prête
    READY --> ASSIGNED : Assigner
    ASSIGNED --> READY : Se désister
    ASSIGNED --> IN_DELIVERY : Récupérer la commande
    IN_DELIVERY --> DELIVERED : Confirmer la livraison
    IN_DELIVERY --> RETRY_PENDING : Premier échec
    RETRY_PENDING --> IN_DELIVERY : Relancer la livraison
    IN_DELIVERY --> RETURN_PENDING : Second échec
    RETURN_PENDING --> RETURNED : Confirmer la remise au vendeur
    REFUNDED --> [*]
    DELIVERED --> [*]
    RETURNED --> [*]
```
