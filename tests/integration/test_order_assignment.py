import pytest

from marketplace.domain import Action, InvalidInput, Role, Status
from marketplace.persistence.postgres_models import ActorRecord


def test_exhausted_couriers_leave_order_ready_until_system_assigns_replacement(
    orders, payments, postgres_sessions
):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    payments.confirm_payment(order.id, "system", "mobile-money-assignment")
    orders.apply_action(order.id, "seller-1", Action.ACCEPT)

    first = orders.apply_action(order.id, "seller-1", Action.MARK_READY)
    assert (first.status, first.courier_id) == (Status.ASSIGNED, "courier-1")
    second = orders.apply_action(order.id, "courier-1", Action.WITHDRAW)
    assert (second.status, second.courier_id) == (Status.ASSIGNED, "courier-2")
    waiting = orders.apply_action(order.id, "courier-2", Action.WITHDRAW)
    assert (waiting.status, waiting.courier_id) == (Status.READY, None)

    _, waiting_history = orders.get_order(order.id)
    assert waiting_history[-1].action is Action.WITHDRAW
    assert waiting_history[-1].to_status is Status.READY
    for previous_courier in ("courier-1", "courier-2"):
        with pytest.raises(InvalidInput):
            orders.apply_action(order.id, "system", Action.ASSIGN, courier_id=previous_courier)
    assert orders.get_order(order.id) == (waiting, waiting_history)

    with postgres_sessions.begin() as session:
        session.add(ActorRecord(id="courier-3", role=Role.COURIER))

    replacement = orders.apply_action(
        order.id,
        "system",
        Action.ASSIGN,
        courier_id="courier-3",
        reason="New courier available",
    )
    assert (replacement.status, replacement.courier_id) == (Status.ASSIGNED, "courier-3")
    _, history = orders.get_order(order.id)
    assert history[:-1] == waiting_history
    event = history[-1]
    assert event.action is Action.ASSIGN
    assert event.from_status is Status.READY
    assert event.to_status is Status.ASSIGNED
    assert event.actor_id == "system"
    assert event.actor_role is Role.SYSTEM
    assert event.assigned_courier_id == "courier-3"
    assert event.reason == "New courier available"
