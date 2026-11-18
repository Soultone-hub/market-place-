from dataclasses import replace
from datetime import UTC, datetime

from ..domain import (
    MAX_ACTOR_ID,
    Action,
    Actor,
    Forbidden,
    HistoryEntry,
    InvalidInput,
    Order,
    Role,
    transition,
)
from .transaction_protocols import OrderChanges


def _find_actor(transaction: OrderChanges, actor_id: str) -> Actor | None:
    if not 0 < len(actor_id) <= MAX_ACTOR_ID or "\x00" in actor_id:
        return None
    return transaction.find_actor(actor_id)


def require_actor(transaction: OrderChanges, actor_id: str) -> Actor:
    actor = _find_actor(transaction, actor_id)
    if actor is None:
        raise Forbidden("Unknown actor.")
    return actor


def require_participant(transaction: OrderChanges, actor_id: str, role: Role) -> None:
    actor = _find_actor(transaction, actor_id)
    if actor is None or actor.role != role:
        raise InvalidInput(f"Actor {actor_id!r} must have the {role} role.")


def apply_order_transition(
    transaction: OrderChanges,
    order: Order,
    actor: Actor,
    action: Action,
    *,
    courier_id: str | None = None,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> Order:
    result = transition(order, action, actor, assigned_courier_id=courier_id, reason=reason)
    if courier_id is not None:
        require_participant(transaction, courier_id, Role.COURIER)

    updated = replace(
        order,
        status=result.status,
        courier_id=result.courier_id,
        failed_delivery_attempts=result.failed_delivery_attempts,
    )
    transaction.update_order(updated)
    transaction.add_history(
        HistoryEntry(
            order_id=order.id,
            actor_id=actor.id,
            actor_role=actor.role,
            action=action,
            from_status=order.status,
            to_status=updated.status,
            occurred_at=occurred_at or datetime.now(UTC),
            reason=result.reason,
            assigned_courier_id=courier_id,
        )
    )
    return updated
