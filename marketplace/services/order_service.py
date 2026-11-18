from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from ..domain import (
    MAX_AMOUNT,
    MAX_REASON,
    SYSTEM_ACTOR_ID,
    Action,
    HistoryEntry,
    InvalidInput,
    Order,
    Role,
    Status,
    require_role,
)
from .order_workflow import apply_order_transition, require_actor, require_participant
from .transaction_protocols import OrderTransaction


class OrderService:
    def __init__(self, transaction: Callable[[], AbstractContextManager[OrderTransaction]]):
        self._transaction = transaction

    def create_order(self, actor_id: str, seller_id: str, amount_xof: int) -> Order:
        if type(amount_xof) is not int or not 0 < amount_xof <= MAX_AMOUNT:
            raise InvalidInput("Amount must be a positive integer in XOF.")

        with self._transaction() as transaction:
            buyer = require_actor(transaction, actor_id)
            require_role(buyer, Action.CREATE)
            require_participant(transaction, seller_id, Role.SELLER)
            order = transaction.create_order(buyer.id, seller_id, amount_xof)
            transaction.add_history(
                HistoryEntry(
                    order_id=order.id,
                    actor_id=buyer.id,
                    actor_role=buyer.role,
                    action=Action.CREATE,
                    from_status=None,
                    to_status=order.status,
                    occurred_at=datetime.now(UTC),
                )
            )
            return order

    def apply_action(
        self,
        order_id: int,
        actor_id: str,
        action: Action,
        *,
        courier_id: str | None = None,
        reason: str | None = None,
    ) -> Order:
        if action in (Action.CREATE, Action.CONFIRM_PAYMENT):
            raise InvalidInput("Use the dedicated creation or payment operation.")
        if (courier_id is not None) != (action == Action.ASSIGN):
            raise InvalidInput("A courier ID is required for assignment only.")
        if reason is not None and (len(reason) > MAX_REASON or "\x00" in reason):
            raise InvalidInput(f"Reason must contain at most {MAX_REASON} valid characters.")

        with self._transaction() as transaction:
            actor = require_actor(transaction, actor_id)
            order = transaction.get_order(order_id)
            if action == Action.ASSIGN and courier_id is not None and order.status == Status.READY:
                require_role(actor, action)
                require_participant(transaction, courier_id, Role.COURIER)
                if transaction.find_eligible_courier_id(order.id, courier_id=courier_id) is None:
                    raise InvalidInput("The courier is not eligible for this order.")

            updated = apply_order_transition(
                transaction, order, actor, action, courier_id=courier_id, reason=reason
            )
            if updated.status == Status.READY:
                return self._assign_available_courier(transaction, updated)
            return updated

    @staticmethod
    def _assign_available_courier(transaction: OrderTransaction, order: Order) -> Order:
        courier_id = transaction.find_eligible_courier_id(order.id)
        if courier_id is None:
            return order

        system = require_actor(transaction, SYSTEM_ACTOR_ID)
        return apply_order_transition(
            transaction,
            order,
            system,
            Action.ASSIGN,
            courier_id=courier_id,
            reason="automatic_assignment",
        )

    def get_order(self, order_id: int) -> tuple[Order, list[HistoryEntry]]:
        with self._transaction() as transaction:
            order = transaction.get_order(order_id, shared=True)
            return order, transaction.get_history(order.id)
