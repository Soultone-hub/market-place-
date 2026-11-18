from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from marketplace.domain import Action, Conflict, Status


def test_acceptance_and_cancellation_cannot_both_succeed(orders, payments):
    order = orders.create_order("buyer-1", "seller-1", 2500)
    payments.confirm_payment(order.id, "system", "mobile-money-race")
    ready = Barrier(2, timeout=5)

    def apply(actor_id, action):
        ready.wait()
        try:
            return orders.apply_action(order.id, actor_id, action).status
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        accept = workers.submit(apply, "seller-1", Action.ACCEPT)
        cancel = workers.submit(apply, "buyer-1", Action.CANCEL)
        results = (accept.result(timeout=10), cancel.result(timeout=10))

    assert results in [(Status.ACCEPTED, None), (None, Status.REFUNDED)]
    current, history = orders.get_order(order.id)
    assert current.status is (results[0] or results[1])
    assert len(history) == 3
