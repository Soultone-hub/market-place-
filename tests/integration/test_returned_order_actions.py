import pytest

from marketplace.domain import Action, Conflict, Forbidden, InvalidInput, Status
from marketplace.persistence.postgres_models import PaymentRecord


RETURN_STEPS = [
    (Action.PICK_UP, Status.IN_DELIVERY),
    (Action.FAIL_DELIVERY, Status.RETRY_PENDING),
    (Action.RETRY_DELIVERY, Status.IN_DELIVERY),
    (Action.FAIL_DELIVERY, Status.RETURN_PENDING),
    (Action.CONFIRM_RETURN, Status.RETURNED),
]


@pytest.fixture
def assigned_order(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    reference = f"mobile-money-return-{order.id}"
    payments.confirm_payment(order.id, "system", reference)
    orders.apply_action(order.id, "seller-1", Action.ACCEPT)
    assigned = orders.apply_action(order.id, "seller-1", Action.MARK_READY)
    assert (assigned.status, assigned.courier_id) == (Status.ASSIGNED, "courier-1")
    return assigned, reference


def complete_return(orders, order):
    current = order
    for action, status in RETURN_STEPS:
        current = orders.apply_action(order.id, order.courier_id, action)
        assert current.status is status
    return current


@pytest.fixture
def returned_order(orders, assigned_order):
    assigned, reference = assigned_order
    return complete_return(orders, assigned), reference


def test_return_after_two_failed_deliveries_preserves_payment(
    orders, returned_order, postgres_sessions
):
    returned, reference = returned_order
    current, history = orders.get_order(returned.id)
    assert current == returned
    assert current.status is Status.RETURNED
    assert current.courier_id == "courier-1"
    assert current.failed_delivery_attempts == 2
    assert [(entry.action, entry.to_status) for entry in history[-len(RETURN_STEPS):]] == (
        RETURN_STEPS
    )
    failures = [entry for entry in history if entry.action is Action.FAIL_DELIVERY]
    assert [entry.reason for entry in failures] == ["customer_unreachable"] * 2

    with pytest.raises(Conflict):
        orders.apply_action(current.id, "system", Action.ASSIGN, courier_id="courier-2")
    with pytest.raises(Forbidden):
        orders.apply_action(current.id, "seller-1", Action.CANCEL)
    assert orders.get_order(current.id) == (current, history)

    with postgres_sessions() as session:
        assert session.get(PaymentRecord, reference).order_id == current.id


def test_reship_uses_a_different_courier_and_a_fresh_attempt_budget(
    orders, payments, returned_order
):
    returned, reference = returned_order
    _, original_history = orders.get_order(returned.id)

    reshipped = orders.apply_action(returned.id, "seller-1", Action.RESHIP)

    assert reshipped.id == returned.id
    assert (reshipped.status, reshipped.courier_id) == (Status.ASSIGNED, "courier-2")
    assert reshipped.failed_delivery_attempts == 0
    assert payments.confirm_payment(reshipped.id, "system", reference) == reshipped

    _, history = orders.get_order(reshipped.id)
    assert history[:-2] == original_history
    reship, assignment = history[-2:]
    assert (reship.action, reship.actor_id) == (Action.RESHIP, "seller-1")
    assert (reship.from_status, reship.to_status) == (Status.RETURNED, Status.READY)
    assert (assignment.action, assignment.actor_id) == (Action.ASSIGN, "system")
    assert (assignment.from_status, assignment.to_status) == (Status.READY, Status.ASSIGNED)
    assert assignment.assigned_courier_id == "courier-2"

    returned_again = complete_return(orders, reshipped)
    assert returned_again.status is Status.RETURNED
    assert returned_again.failed_delivery_attempts == 2


def test_reship_waits_for_an_eligible_courier(orders, assigned_order):
    assigned, _ = assigned_order
    replacement = orders.apply_action(assigned.id, "courier-1", Action.WITHDRAW)
    assert replacement.courier_id == "courier-2"
    returned = complete_return(orders, replacement)

    waiting = orders.apply_action(returned.id, "seller-1", Action.RESHIP)

    assert (waiting.status, waiting.courier_id, waiting.failed_delivery_attempts) == (
        Status.READY, None, 0
    )
    _, history = orders.get_order(waiting.id)
    assert history[-1].action is Action.RESHIP
    for courier in ("courier-1", "courier-2"):
        with pytest.raises(InvalidInput):
            orders.apply_action(waiting.id, "system", Action.ASSIGN, courier_id=courier)
    assert orders.get_order(waiting.id) == (waiting, history)


def test_seller_can_refund_a_returned_order(
    orders, payments, returned_order, postgres_sessions
):
    returned, reference = returned_order
    _, return_history = orders.get_order(returned.id)
    reason = "customer chose to cancel"

    refunded = orders.apply_action(
        returned.id, "seller-1", Action.CANCEL_RETURNED, reason=reason
    )

    assert refunded.id == returned.id
    assert refunded.status is Status.REFUNDED
    assert payments.confirm_payment(refunded.id, "system", reference) == refunded
    with pytest.raises(Conflict):
        orders.apply_action(refunded.id, "seller-1", Action.CANCEL_RETURNED)

    current, history = orders.get_order(refunded.id)
    assert current == refunded
    assert history[:-1] == return_history
    refund = history[-1]
    assert (refund.action, refund.actor_id) == (Action.CANCEL_RETURNED, "seller-1")
    assert (refund.from_status, refund.to_status) == (Status.RETURNED, Status.REFUNDED)
    assert refund.reason == reason
    with postgres_sessions() as session:
        assert session.get(PaymentRecord, reference).order_id == refunded.id
