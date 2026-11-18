from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..domain import MAX_ACTOR_ID, MAX_REASON, MAX_REFERENCE, Action, Role, Status


class Base(DeclarativeBase):
    pass


class ActorRecord(Base):
    __tablename__ = "actors"

    id: Mapped[str] = mapped_column(String(MAX_ACTOR_ID), primary_key=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="actor_role", native_enum=False, create_constraint=True)
    )


class OrderRecord(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_xof > 0", name="positive_order_amount"),
        CheckConstraint(
            "failed_delivery_attempts BETWEEN 0 AND 2", name="delivery_attempt_limit"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    seller_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    courier_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
    amount_xof: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[Status] = mapped_column(
        Enum(Status, name="order_status", native_enum=False, create_constraint=True)
    )
    failed_delivery_attempts: Mapped[int] = mapped_column(default=0, server_default="0")


class PaymentRecord(Base):
    __tablename__ = "payments"

    reference: Mapped[str] = mapped_column(String(MAX_REFERENCE), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HistoryRecord(Base):
    __tablename__ = "order_history"
    __table_args__ = (
        CheckConstraint(
            "(action = 'assign') = (assigned_courier_id IS NOT NULL)",
            name="assignment_records_chosen_courier",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"))
    actor_role: Mapped[Role] = mapped_column(
        Enum(Role, name="history_role", native_enum=False, create_constraint=True)
    )
    action: Mapped[Action] = mapped_column(
        Enum(
            Action,
            name="history_action",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda actions: [action.value for action in actions],
        )
    )
    from_status: Mapped[Status | None] = mapped_column(
        Enum(Status, name="history_from_status", native_enum=False, create_constraint=True)
    )
    to_status: Mapped[Status] = mapped_column(
        Enum(Status, name="history_to_status", native_enum=False, create_constraint=True)
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(MAX_REASON))
    assigned_courier_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"))
