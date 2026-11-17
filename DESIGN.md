# Note de conception de la place de marché

Une commande relie un acheteur à un vendeur. Le système confirme le paiement mobile money et assigne un livreur une fois la commande prête. Chaque transition validée est enregistrée dans l’historique.

## États et transitions

| Action | État de départ | État d’arrivée | Rôle autorisé et condition |
| --- | --- | --- | --- |
| Créer la commande | — | `PENDING_PAYMENT` | Acheteur qui passe la commande |
| Confirmer le paiement | `PENDING_PAYMENT` | `PAID` | Système, à la réception de la notification de succès |
| Annuler avant paiement | `PENDING_PAYMENT` | `CANCELLED` | Acheteur de la commande |
| Traiter un paiement arrivé après l’annulation | `CANCELLED` | `REFUNDED` | Système, à la réception d’une première notification de succès |
| Annuler après paiement | `PAID` | `REFUNDED` | Acheteur de la commande |
| Refuser | `PAID` | `REFUNDED` | Vendeur de la commande |
| Accepter | `PAID` | `ACCEPTED` | Vendeur de la commande |
| Déclarer la commande prête | `ACCEPTED` | `READY` | Vendeur de la commande |
| Assigner un livreur | `READY` | `ASSIGNED` | Système, avec l’identifiant du livreur |
| Se désister | `ASSIGNED` | `READY` | Livreur assigné. L’affectation est effacée. |
| Récupérer la commande | `ASSIGNED` | `IN_DELIVERY` | Livreur assigné |
| Confirmer la livraison | `IN_DELIVERY` | `DELIVERED` | Livreur assigné |
| Signaler un premier échec | `IN_DELIVERY` | `RETRY_PENDING` | Livreur assigné. Le client est injoignable. |
| Relancer la livraison | `RETRY_PENDING` | `IN_DELIVERY` | Même livreur, pour l’unique nouvelle tentative |
| Signaler un second échec | `IN_DELIVERY` | `RETURN_PENDING` | Livreur assigné. Le client est toujours injoignable. |
| Confirmer la remise au vendeur | `RETURN_PENDING` | `RETURNED` | Livreur assigné |

`REFUNDED`, `DELIVERED` et `RETURNED` sont des états finaux. Chaque action vérifie le rôle de l’acteur. Pour une commande existante, l’identité d’un acheteur, d’un vendeur ou d’un livreur doit aussi correspondre à celle enregistrée sur la commande. Une action hors tableau est rejetée sans modification ni ajout à l’historique.

## Modèle de données

| Table | Données et contraintes |
| --- | --- |
| `orders` | `id` (clé primaire), `buyer_id`, `seller_id`, `courier_id` (nullable), `amount_xof` (entier positif), `status`, `failed_delivery_attempts` (de 0 à 2, initialisé à 0) |
| `payments` | `reference` (clé primaire), `order_id` (clé étrangère unique), `received_at` (UTC) |
| `order_history` | `id` (clé primaire), `order_id` (clé étrangère), `actor_id`, `actor_role`, `action`, `from_status` (vide à la création), `to_status`, `occurred_at` (UTC), `reason` (facultatif) |

L’historique est ajouté au fil des transitions et se lit par ordre croissant d’identifiant. L’action permet notamment de distinguer un remboursement après annulation d’un remboursement après refus. Le motif `customer_unreachable` est enregistré à chaque échec de livraison.

## Traitement des notifications répétées

SQLite garantit l’unicité de `payments.reference`. Le système ouvre une transaction avec `BEGIN IMMEDIATE` avant de rechercher la référence et de lire l’état courant. Si la référence est déjà associée à cette commande, il renvoie l’état courant avec succès sans modifier la commande ni son historique. Une référence associée à une autre commande ou une seconde référence pour la même commande donne lieu à un conflit.

Pour une nouvelle référence valide, le système enregistre le paiement, change l’état de la commande et ajoute l’entrée d’historique dans la même transaction. Si une étape échoue, la transaction entière est annulée. SQLite sérialise les écritures, ce qui couvre deux notifications simultanées et les actions concurrentes comme accepter et annuler.

## Hypothèses métier

- Une commande a un seul paiement intégral. La notification simulée confirme le succès du paiement pour le montant attendu. La référence est unique sur la plateforme.
- Une annulation avant confirmation passe à `CANCELLED`. Si le paiement est confirmé plus tard, la commande passe directement à `REFUNDED`. Une annulation après paiement ou un refus du vendeur produit aussi un remboursement simulé en un changement d’état.
- Une commande libérée par un livreur revient à `READY`, disponible pour une nouvelle affectation par le système. Après la prise en charge, le même livreur effectue la nouvelle tentative puis, si nécessaire, rapporte la commande au vendeur.
- Le retour est considéré comme terminé quand le livreur confirme la remise au vendeur. L’énoncé laisse ouverte la suite financière de ce retour. Le modèle conserve le paiement enregistré à cette étape.
