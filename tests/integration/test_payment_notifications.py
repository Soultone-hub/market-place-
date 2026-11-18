from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from marketplace.domain import Action, Conflict, Status
from marketplace.persistence.postgres_models import PaymentRecord
from marketplace.persistence.postgres_repository import PostgresTransaction


def test_duplicate_notification_keeps_one_payment_and_one_transition(
    orders, payments, postgres_sessions
):
    order = orders.create_order("buyer-1", "seller-1", 3500)
    reference = "mobile-money-replayed"
    assert payments.confirm_payment(order.id, "system", reference).status is Status.PAID
    assert payments.confirm_payment(order.id, "system", reference).status is Status.PAID
    orders.apply_action(order.id, "seller-1", Action.ACCEPT)
    assert payments.confirm_payment(order.id, "system", reference).status is Status.ACCEPTED

    with postgres_sessions() as session:
        count = session.scalar(
            select(func.count()).select_from(PaymentRecord).where(PaymentRecord.order_id == order.id)
        )
    _, history = orders.get_order(order.id)
    assert count == 1
    assert [entry.to_status for entry in history] == [
        Status.PENDING_PAYMENT, Status.PAID, Status.ACCEPTED
    ]
    with pytest.raises(Conflict):
        payments.confirm_payment(order.id, "system", "another-reference")


def test_late_payment_is_refunded_after_buyer_cancels(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 3500)
    orders.apply_action(order.id, "buyer-1", Action.CANCEL)
    payments.confirm_payment(order.id, "system", "mobile-money-late")
    payments.confirm_payment(order.id, "system", "mobile-money-late")
    current, history = orders.get_order(order.id)
    assert current.status is Status.REFUNDED
    assert [entry.to_status for entry in history] == [
        Status.PENDING_PAYMENT, Status.CANCELLED, Status.REFUNDED
    ]


def test_concurrent_notifications_for_same_order(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    ready = Barrier(2, timeout=5)

    def notify():
        ready.wait()
        return payments.confirm_payment(order.id, "system", "mobile-money-concurrent").status

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(notify)
        second = workers.submit(notify)
        assert first.result(timeout=10) is Status.PAID
        assert second.result(timeout=10) is Status.PAID

    _, history = orders.get_order(order.id)
    assert len(history) == 2


def test_a_reference_cannot_pay_two_orders(orders, payments):
    new_orders = [orders.create_order("buyer-1", "seller-1", 2500) for _ in range(2)]
    ready = Barrier(2, timeout=5)

    def notify(order_id):
        ready.wait()
        try:
            payments.confirm_payment(order_id, "system", "mobile-money-shared")
        except Conflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(notify, (order.id for order in new_orders)))

    assert sorted(results) == [False, True]
    for order, succeeded in zip(new_orders, results):
        current, history = orders.get_order(order.id)
        assert current.status is (Status.PAID if succeeded else Status.PENDING_PAYMENT)
        assert len(history) == (2 if succeeded else 1)


def test_history_write_failure_rolls_back_the_payment(
    orders, payments, postgres_sessions, monkeypatch
):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    reference = "mobile-money-rollback"
    add_history = PostgresTransaction.add_history

    def write_invalid_history(transaction, entry):
        add_history(transaction, replace(entry, assigned_courier_id="courier-1"))

    with monkeypatch.context() as patch:
        patch.setattr(PostgresTransaction, "add_history", write_invalid_history)
        with pytest.raises(IntegrityError) as failed_write:
            payments.confirm_payment(order.id, "system", reference)
    assert failed_write.value.orig.diag.constraint_name == "assignment_records_chosen_courier"

    with postgres_sessions() as session:
        assert session.get(PaymentRecord, reference) is None
    current, history = orders.get_order(order.id)
    assert current.status is Status.PENDING_PAYMENT
    assert [entry.action for entry in history] == [Action.CREATE]
    assert payments.confirm_payment(order.id, "system", reference).status is Status.PAID
