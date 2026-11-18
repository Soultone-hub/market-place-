import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from marketplace.db import initialize, make_sessions
from marketplace.persistence.postgres_repository import PostgresRepository
from marketplace.services.order_service import OrderService
from marketplace.services.payment_service import PaymentService


@pytest.fixture(scope="module")
def postgres_sessions():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")

    base_sessions = make_sessions(database_url)
    with base_sessions() as session:
        engine = session.get_bind()
    schema = f"test_{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))

    try:
        engine_for_test = engine.execution_options(schema_translate_map={None: schema})
        test_sessions = sessionmaker(engine_for_test, expire_on_commit=False)
        initialize(test_sessions)
        yield test_sessions
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def orders(postgres_sessions):
    return OrderService(PostgresRepository(postgres_sessions).transaction)


@pytest.fixture
def payments(postgres_sessions):
    return PaymentService(PostgresRepository(postgres_sessions).transaction)
