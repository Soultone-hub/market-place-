import pytest

from marketplace.domain import Action, Forbidden, Status
from marketplace.persistence.postgres_models import PaymentRecord


def test_wrong_role_leaves_history_unchanged(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    payments.confirm_payment(order.id, "system", "mobile-money-forbidden")
    with pytest.raises(Forbidden):
        orders.apply_action(order.id, "buyer-1", Action.ACCEPT)
    current, history = orders.get_order(order.id)
    assert current.status is Status.PAID
    assert len(history) == 2


def test_seller_refusal_is_recorded_as_a_refund(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    payments.confirm_payment(order.id, "system", "mobile-money-refusal")
    orders.apply_action(order.id, "seller-1", Action.REFUSE, reason="out of stock")

    current, history = orders.get_order(order.id)
    assert current.status is Status.REFUNDED
    refund = history[-1]
    assert refund.action is Action.REFUSE
    assert refund.from_status is Status.PAID
    assert refund.to_status is Status.REFUNDED
    assert refund.actor_id == "seller-1"
    assert refund.reason == "out of stock"


def test_return_after_two_failed_deliveries_preserves_payment(
    orders, payments, postgres_sessions
):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    reference = "mobile-money-return"
    payments.confirm_payment(order.id, "system", reference)
    orders.apply_action(order.id, "seller-1", Action.ACCEPT)
    orders.apply_action(order.id, "seller-1", Action.MARK_READY)
    orders.apply_action(order.id, "system", Action.ASSIGN, courier_id="courier-1")

    steps = [
        (Action.PICK_UP, Status.IN_DELIVERY),
        (Action.FAIL_DELIVERY, Status.RETRY_PENDING),
        (Action.RETRY_DELIVERY, Status.IN_DELIVERY),
        (Action.FAIL_DELIVERY, Status.RETURN_PENDING),
        (Action.CONFIRM_RETURN, Status.RETURNED),
    ]
    for action, status in steps:
        assert orders.apply_action(order.id, "courier-1", action).status is status

    current, history = orders.get_order(order.id)
    assert current.failed_delivery_attempts == 2
    assert [entry.to_status for entry in history[-len(steps):]] == [
        status for _, status in steps
    ]
    failures = [entry for entry in history if entry.action is Action.FAIL_DELIVERY]
    assert [entry.reason for entry in failures] == ["customer_unreachable"] * 2

    with postgres_sessions() as session:
        assert session.get(PaymentRecord, reference).order_id == order.id
