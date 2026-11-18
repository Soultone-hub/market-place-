from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ..domain import Action, Actor, HistoryEntry, Order, OrderNotFound, Role, Status
from .postgres_models import ActorRecord, HistoryRecord, OrderRecord, PaymentRecord


class PostgresRepository:
    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions

    @contextmanager
    def transaction(self) -> Iterator[PostgresTransaction]:
        with self._sessions.begin() as session:
            yield PostgresTransaction(session)


class PostgresTransaction:
    def __init__(self, session: Session):
        self._session = session

    def find_actor(self, actor_id: str) -> Actor | None:
        record = self._session.get(ActorRecord, actor_id)
        return Actor(record.id, record.role) if record is not None else None

    def find_eligible_courier_id(
        self, order_id: int, *, courier_id: str | None = None
    ) -> str | None:
        # Include a withdrawal recorded earlier in the same transaction.
        self._session.flush()
        withdrew_from_order = (
            select(HistoryRecord.id)
            .where(
                HistoryRecord.order_id == order_id,
                HistoryRecord.action == Action.WITHDRAW,
                HistoryRecord.actor_id == ActorRecord.id,
            )
            .exists()
        )
        last_returning_courier = (
            select(HistoryRecord.actor_id)
            .where(
                HistoryRecord.order_id == order_id,
                HistoryRecord.action == Action.CONFIRM_RETURN,
            )
            .order_by(HistoryRecord.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        eligible_couriers = select(ActorRecord.id).where(
            ActorRecord.role == Role.COURIER,
            ~withdrew_from_order,
            ActorRecord.id.is_distinct_from(last_returning_courier),
        )
        if courier_id is not None:
            eligible_couriers = eligible_couriers.where(ActorRecord.id == courier_id)
        return self._session.scalar(eligible_couriers.order_by(ActorRecord.id).limit(1))

    def create_order(self, buyer_id: str, seller_id: str, amount_xof: int) -> Order:
        record = OrderRecord(
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount_xof=amount_xof,
            status=Status.PENDING_PAYMENT,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_order(record)

    def get_order(self, order_id: int, *, shared: bool = False) -> Order:
        record = self._session.scalar(
            select(OrderRecord)
            .where(OrderRecord.id == order_id)
            .with_for_update(read=shared)
        )
        if record is None:
            raise OrderNotFound("Order does not exist.")
        return self._to_order(record)

    def update_order(self, order: Order) -> None:
        self._session.execute(
            update(OrderRecord)
            .where(OrderRecord.id == order.id)
            .values(
                status=order.status,
                courier_id=order.courier_id,
                failed_delivery_attempts=order.failed_delivery_attempts,
            )
        )

    def add_history(self, entry: HistoryEntry) -> None:
        self._session.add(
            HistoryRecord(
                order_id=entry.order_id,
                actor_id=entry.actor_id,
                actor_role=entry.actor_role,
                action=entry.action,
                from_status=entry.from_status,
                to_status=entry.to_status,
                occurred_at=entry.occurred_at,
                reason=entry.reason,
                assigned_courier_id=entry.assigned_courier_id,
            )
        )

    def get_history(self, order_id: int) -> list[HistoryEntry]:
        records = self._session.scalars(
            select(HistoryRecord)
            .where(HistoryRecord.order_id == order_id)
            .order_by(HistoryRecord.id)
        )
        return [
            HistoryEntry(
                id=record.id,
                order_id=record.order_id,
                actor_id=record.actor_id,
                actor_role=record.actor_role,
                action=record.action,
                from_status=record.from_status,
                to_status=record.to_status,
                occurred_at=record.occurred_at,
                reason=record.reason,
                assigned_courier_id=record.assigned_courier_id,
            )
            for record in records
        ]

    def payment_order_id(self, reference: str) -> int | None:
        return self._session.scalar(
            select(PaymentRecord.order_id).where(PaymentRecord.reference == reference)
        )

    def order_has_payment(self, order_id: int) -> bool:
        reference = self._session.scalar(
            select(PaymentRecord.reference).where(PaymentRecord.order_id == order_id)
        )
        return reference is not None

    def insert_payment(self, order_id: int, reference: str, received_at: datetime) -> bool:
        inserted_reference = self._session.scalar(
            insert(PaymentRecord)
            .values(reference=reference, order_id=order_id, received_at=received_at)
            .on_conflict_do_nothing()
            .returning(PaymentRecord.reference)
        )
        return inserted_reference is not None

    @staticmethod
    def _to_order(record: OrderRecord) -> Order:
        return Order(
            id=record.id,
            buyer_id=record.buyer_id,
            seller_id=record.seller_id,
            courier_id=record.courier_id,
            amount_xof=record.amount_xof,
            status=record.status,
            failed_delivery_attempts=record.failed_delivery_attempts,
        )
