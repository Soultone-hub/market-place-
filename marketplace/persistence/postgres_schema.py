from sqlalchemy import CheckConstraint, MetaData, Table, column, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.schema import AddConstraint, DropConstraint

from .postgres_models import HistoryRecord


def upgrade_history_action_constraint(connection: Connection) -> None:
    history = HistoryRecord.__table__
    action_type = history.c.action.type
    constraint_name = action_type.name
    allowed_actions = action_type.enums
    schema = connection.schema_for_object(history)
    constraints = inspect(connection).get_check_constraints(history.name, schema=schema)
    for constraint in constraints:
        if constraint["name"] == constraint_name and all(
            f"'{action}'" in constraint["sqltext"] for action in allowed_actions
        ):
            return

    # create_all does not update the check on an existing history table.
    updated_check = CheckConstraint(column("action").in_(allowed_actions), name=constraint_name)
    migration_table = Table(history.name, MetaData(), schema=history.schema)
    migration_table.append_constraint(updated_check)
    connection.execute(DropConstraint(updated_check, if_exists=True))
    connection.execute(AddConstraint(updated_check))
