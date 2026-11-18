from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from ..domain import MAX_REFERENCE, Action, Conflict, InvalidInput, Order, require_role
from .order_workflow import apply_order_transition, require_actor
from .transaction_protocols import PaymentTransaction


class PaymentService:
    def __init__(self, transaction: Callable[[], AbstractContextManager[PaymentTransaction]]):
        self._transaction = transaction

    def confirm_payment(self, order_id: int, actor_id: str, reference: str) -> Order:
        reference = reference.strip()
        if not reference or len(reference) > MAX_REFERENCE or "\x00" in reference:
            raise InvalidInput(f"Reference must contain 1 to {MAX_REFERENCE} valid characters.")

        with self._transaction() as transaction:
            actor = require_actor(transaction, actor_id)
            require_role(actor, Action.CONFIRM_PAYMENT)
            order = transaction.get_order(order_id)

            paid_order_id = transaction.payment_order_id(reference)
            if paid_order_id is not None:
                if paid_order_id == order.id:
                    return order
                raise Conflict("Payment reference already belongs to another order.")
            if transaction.order_has_payment(order.id):
                raise Conflict("The order already has a payment.")

            received_at = datetime.now(UTC)
            if not transaction.insert_payment(order.id, reference, received_at):
                raise Conflict("Payment reference already belongs to another order.")

            return apply_order_transition(
                transaction, order, actor, Action.CONFIRM_PAYMENT, occurred_at=received_at
            )
