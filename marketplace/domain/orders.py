from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .actors import Role

MAX_REFERENCE = 120
MAX_REASON = 500
MAX_AMOUNT = 2**63 - 1


class Status(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    ACCEPTED = "ACCEPTED"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    IN_DELIVERY = "IN_DELIVERY"
    RETRY_PENDING = "RETRY_PENDING"
    RETURN_PENDING = "RETURN_PENDING"
    DELIVERED = "DELIVERED"
    RETURNED = "RETURNED"


class Action(StrEnum):
    CREATE = "create"
    CONFIRM_PAYMENT = "confirm_payment"
    CANCEL = "cancel"
    REFUSE = "refuse"
    ACCEPT = "accept"
    MARK_READY = "mark_ready"
    ASSIGN = "assign"
    WITHDRAW = "withdraw"
    PICK_UP = "pick_up"
    DELIVER = "deliver"
    FAIL_DELIVERY = "fail_delivery"
    RETRY_DELIVERY = "retry_delivery"
    CONFIRM_RETURN = "confirm_return"
    RESHIP = "reship"
    CANCEL_RETURNED = "cancel_returned"


@dataclass(frozen=True)
class OrderState:
    buyer_id: str
    seller_id: str
    courier_id: str | None
    status: Status
    failed_delivery_attempts: int


@dataclass(frozen=True)
class Order(OrderState):
    id: int
    amount_xof: int


@dataclass(frozen=True)
class HistoryEntry:
    order_id: int
    actor_id: str
    actor_role: Role
    action: Action
    from_status: Status | None
    to_status: Status
    occurred_at: datetime
    reason: str | None = None
    assigned_courier_id: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class Transition:
    status: Status
    courier_id: str | None
    failed_delivery_attempts: int
    reason: str | None
