import pytest

from marketplace.domain import Action, Forbidden, Status


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
