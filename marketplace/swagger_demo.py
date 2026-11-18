from .domain import Action

CREATE_TAG = "1. Création"
PAYMENT_TAG = "2. Paiement"
ACTIONS_TAG = "3. Actions"
HISTORY_TAG = "4. Suivi"

DEMO_TAGS = [
    {"name": CREATE_TAG, "description": "Créer une commande de démonstration."},
    {"name": PAYMENT_TAG, "description": "Confirmer le paiement ou rejouer une notification."},
    {"name": ACTIONS_TAG, "description": "Avancer la commande et suivre son affectation automatique."},
    {"name": HISTORY_TAG, "description": "Vérifier l’état courant et les transitions enregistrées."},
]

DEMO_GUIDE = """## Démo rapide

Ouvre les sections dans l’ordre et clique sur **Execute** pour envoyer chaque requête.

1. **Création** avec `buyer-1`. Conserve l’`id` de la réponse pour les étapes suivantes.
2. **Paiement** avec `system`. Donne une référence unique à cette commande.
   Pour tester un doublon, clique deux fois sur **Execute** avec la même référence.
3. **Actions**. Le menu **Examples** remplit le JSON. Sélectionne aussi l’acteur
   indiqué dans le nom de l’exemple, sous `X-Actor-Id`.
   Enchaîne **Accepter**, **Marquer prête**, **Récupérer**, **Livrer**.
   Après **Marquer prête**, si la réponse est `ASSIGNED`, sélectionne le
   `courier_id` renvoyé comme acteur pour **Récupérer** et **Livrer**.
   Si elle est `READY`, la commande attend un livreur éligible. L’exemple
   **Reprendre une affectation en attente** permet à `system` d’en indiquer un.
4. **Suivi**. Vérifie l’état `DELIVERED` et les transitions, dont l’affectation par `system`.
"""

BUYER_EXAMPLES = {
    "buyer-1": {"summary": "Acheteur · buyer-1", "value": "buyer-1"},
}
SYSTEM_EXAMPLES = {
    "system": {"summary": "Système · system", "value": "system"},
}
ACTION_ACTOR_EXAMPLES = {
    "seller-1": {"summary": "Vendeur · seller-1", "value": "seller-1"},
    **SYSTEM_EXAMPLES,
    "courier-1": {"summary": "Livreur · courier-1", "value": "courier-1"},
    "courier-2": {"summary": "Livreur de remplacement · courier-2", "value": "courier-2"},
    **BUYER_EXAMPLES,
}

CREATE_ORDER_EXAMPLES = {
    "demo_order": {
        "summary": "Commande de 7 500 XOF chez seller-1",
        "value": {"seller_id": "seller-1", "amount_xof": 7500},
    },
}
PAYMENT_EXAMPLES = {
    "demo_payment": {
        "summary": "Confirmer le paiement",
        "description": "Change la référence pour chaque nouvelle commande.",
        "value": {"reference": "mobile-money-001"},
    },
}
ACTION_EXAMPLES = {
    "accept": {
        "summary": "1. Accepter · seller-1",
        "value": {"action": Action.ACCEPT.value},
    },
    "mark_ready": {
        "summary": "2. Marquer prête · seller-1",
        "description": "Le système assigne un livreur éligible et renvoie son identifiant.",
        "value": {"action": Action.MARK_READY.value},
    },
    "pick_up": {
        "summary": "3. Récupérer · livreur affecté",
        "value": {"action": Action.PICK_UP.value},
    },
    "deliver": {
        "summary": "4. Livrer · livreur affecté",
        "value": {"action": Action.DELIVER.value},
    },
    "assign": {
        "summary": "Reprendre une affectation en attente · system",
        "description": "Pour une commande READY, indique un livreur qui ne s’est pas désisté.",
        "value": {"action": Action.ASSIGN.value, "courier_id": "courier-1"},
    },
    "refuse": {
        "summary": "Refuser une commande payée · seller-1",
        "value": {"action": Action.REFUSE.value, "reason": "Article indisponible"},
    },
    "cancel": {
        "summary": "Annuler avant acceptation · buyer-1",
        "value": {"action": Action.CANCEL.value},
    },
    "withdraw": {
        "summary": "Se désister avant la prise en charge · livreur affecté",
        "description": "La réponse indique le remplaçant si un autre livreur est éligible.",
        "value": {"action": Action.WITHDRAW.value},
    },
    "fail_delivery": {
        "summary": "Signaler un échec de livraison · livreur affecté",
        "value": {"action": Action.FAIL_DELIVERY.value},
    },
    "retry_delivery": {
        "summary": "Relancer après le premier échec · livreur affecté",
        "value": {"action": Action.RETRY_DELIVERY.value},
    },
    "confirm_return": {
        "summary": "Confirmer le retour après le second échec · livreur affecté",
        "value": {"action": Action.CONFIRM_RETURN.value},
    },
}
