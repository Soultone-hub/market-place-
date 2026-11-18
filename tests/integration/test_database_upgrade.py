from sqlalchemy import CheckConstraint, MetaData, Table, column, inspect
from sqlalchemy.schema import AddConstraint, DropConstraint

from marketplace.db import initialize
from marketplace.domain import Action, Status


def test_initialize_upgrades_legacy_history_actions_without_losing_orders(
    orders, payments, postgres_sessions
):
    history_table = Table("order_history", MetaData())
    old_actions = [
        action.value for action in Action if action not in (Action.RESHIP, Action.CANCEL_RETURNED)
    ]
    old_check = CheckConstraint(column("action").in_(old_actions), name="history_action")
    history_table.append_constraint(old_check)
    with postgres_sessions.begin() as session:
        session.execute(DropConstraint(old_check))
        session.execute(AddConstraint(old_check))

    order = orders.create_order("buyer-1", "seller-1", 2500)
    reference = "mobile-money-before-database-upgrade"
    payments.confirm_payment(order.id, "system", reference)
    orders.apply_action(order.id, "seller-1", Action.ACCEPT)
    assigned = orders.apply_action(order.id, "seller-1", Action.MARK_READY)
    for action in (
        Action.PICK_UP, Action.FAIL_DELIVERY, Action.RETRY_DELIVERY,
        Action.FAIL_DELIVERY, Action.CONFIRM_RETURN,
    ):
        orders.apply_action(order.id, assigned.courier_id, action)
    returned, previous_history = orders.get_order(order.id)
    assert returned.status is Status.RETURNED

    initialize(postgres_sessions)
    initialize(postgres_sessions)
    assert orders.get_order(order.id) == (returned, previous_history)

    with postgres_sessions.begin() as session:
        connection = session.connection()
        schema = connection.schema_for_object(history_table)
        checks = inspect(connection).get_check_constraints(history_table.name, schema=schema)
        action_check = next(check["sqltext"] for check in checks if check["name"] == "history_action")
        assert "'reship'" in action_check
        assert "'cancel_returned'" in action_check

    refunded = orders.apply_action(order.id, "seller-1", Action.CANCEL_RETURNED)
    assert refunded.status is Status.REFUNDED
    assert payments.confirm_payment(order.id, "system", reference) == refunded
    assert orders.get_order(order.id)[1][:-1] == previous_history
