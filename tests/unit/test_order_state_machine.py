import pytest

from marketplace.domain import (
    Action, Actor, Conflict, Forbidden, OrderState, Role, Status, transition,
)

BUYER = Actor("buyer-1", Role.BUYER)
SELLER = Actor("seller-1", Role.SELLER)
SYSTEM = Actor("system", Role.SYSTEM)
COURIER = Actor("courier-1", Role.COURIER)


def order_in(status: Status, courier: str | None = None, failures: int = 0) -> OrderState:
    return OrderState(BUYER.id, SELLER.id, courier, status, failures)


def test_seller_refuses_paid_order():
    result = transition(order_in(Status.PAID), Action.REFUSE, SELLER, reason="out of stock")

    assert result.status is Status.REFUNDED
    assert result.reason == "out of stock"


def test_accepted_order_cannot_be_cancelled_by_buyer():
    with pytest.raises(Conflict):
        transition(order_in(Status.ACCEPTED), Action.CANCEL, BUYER)


def test_buyer_cannot_accept_an_order():
    with pytest.raises(Forbidden):
        transition(order_in(Status.PAID), Action.ACCEPT, BUYER)


def test_unassigned_courier_cannot_pick_up_order():
    order = order_in(Status.ASSIGNED, courier=COURIER.id)
    other_courier = Actor("courier-2", Role.COURIER)
    with pytest.raises(Forbidden):
        transition(order, Action.PICK_UP, other_courier)


def test_second_failure_requires_return():
    first = transition(order_in(Status.IN_DELIVERY, COURIER.id), Action.FAIL_DELIVERY, COURIER)
    assert first.status is Status.RETRY_PENDING
    assert first.failed_delivery_attempts == 1

    retry = transition(
        order_in(first.status, COURIER.id, first.failed_delivery_attempts),
        Action.RETRY_DELIVERY,
        COURIER,
    )
    assert retry.status is Status.IN_DELIVERY

    second = transition(
        order_in(retry.status, COURIER.id, retry.failed_delivery_attempts),
        Action.FAIL_DELIVERY,
        COURIER,
    )
    assert second.status is Status.RETURN_PENDING
    assert second.failed_delivery_attempts == 2
    assert second.reason == "customer_unreachable"

    returning = order_in(second.status, COURIER.id, second.failed_delivery_attempts)
    with pytest.raises(Conflict):
        transition(returning, Action.RETRY_DELIVERY, COURIER)
    assert transition(returning, Action.CONFIRM_RETURN, COURIER).status is Status.RETURNED


def test_payment_confirmed_after_cancellation_is_refunded():
    result = transition(order_in(Status.CANCELLED), Action.CONFIRM_PAYMENT, SYSTEM)

    assert result.status is Status.REFUNDED
    assert result.reason == "payment_confirmed_after_cancellation"
