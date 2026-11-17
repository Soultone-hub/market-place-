from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    COURIER = "COURIER"
    SYSTEM = "SYSTEM"


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


class MarketplaceError(Exception):
    pass


class Forbidden(MarketplaceError):
    pass


class Conflict(MarketplaceError):
    pass


class InvalidInput(MarketplaceError):
    pass


class OrderNotFound(MarketplaceError):
    pass


@dataclass(frozen=True)
class Actor:
    id: str
    role: Role


@dataclass(frozen=True)
class OrderState:
    buyer_id: str
    seller_id: str
    courier_id: str | None
    status: Status
    failed_delivery_attempts: int


@dataclass(frozen=True)
class Transition:
    status: Status
    courier_id: str | None
    failed_delivery_attempts: int
    reason: str | None


ACTION_ROLES = {
    Action.CREATE: Role.BUYER,
    Action.CONFIRM_PAYMENT: Role.SYSTEM,
    Action.CANCEL: Role.BUYER,
    Action.REFUSE: Role.SELLER,
    Action.ACCEPT: Role.SELLER,
    Action.MARK_READY: Role.SELLER,
    Action.ASSIGN: Role.SYSTEM,
    Action.WITHDRAW: Role.COURIER,
    Action.PICK_UP: Role.COURIER,
    Action.DELIVER: Role.COURIER,
    Action.FAIL_DELIVERY: Role.COURIER,
    Action.RETRY_DELIVERY: Role.COURIER,
    Action.CONFIRM_RETURN: Role.COURIER,
}

TRANSITIONS = {
    (Status.PENDING_PAYMENT, Action.CONFIRM_PAYMENT): Status.PAID,
    (Status.PENDING_PAYMENT, Action.CANCEL): Status.CANCELLED,
    (Status.CANCELLED, Action.CONFIRM_PAYMENT): Status.REFUNDED,
    (Status.PAID, Action.CANCEL): Status.REFUNDED,
    (Status.PAID, Action.REFUSE): Status.REFUNDED,
    (Status.PAID, Action.ACCEPT): Status.ACCEPTED,
    (Status.ACCEPTED, Action.MARK_READY): Status.READY,
    (Status.READY, Action.ASSIGN): Status.ASSIGNED,
    (Status.ASSIGNED, Action.WITHDRAW): Status.READY,
    (Status.ASSIGNED, Action.PICK_UP): Status.IN_DELIVERY,
    (Status.IN_DELIVERY, Action.DELIVER): Status.DELIVERED,
    (Status.IN_DELIVERY, Action.FAIL_DELIVERY): Status.RETRY_PENDING,
    (Status.RETRY_PENDING, Action.RETRY_DELIVERY): Status.IN_DELIVERY,
    (Status.RETURN_PENDING, Action.CONFIRM_RETURN): Status.RETURNED,
}


def require_role(actor: Actor, action: Action) -> None:
    expected_role = ACTION_ROLES[action]
    if actor.role != expected_role:
        raise Forbidden(f"{action} requires the {expected_role} role.")


def transition(
    order: OrderState,
    action: Action,
    actor: Actor,
    *,
    assigned_courier_id: str | None = None,
    reason: str | None = None,
) -> Transition:
    require_role(actor, action)
    # Check the state before checking the courier so an unassigned order
    # reports an invalid transition instead of a missing assignment.
    next_status = TRANSITIONS.get((order.status, action))
    if next_status is None:
        raise Conflict(f"{action} is unavailable from {order.status}.")

    participants = {
        Role.BUYER: order.buyer_id,
        Role.SELLER: order.seller_id,
        Role.COURIER: order.courier_id,
    }
    if actor.role in participants and participants[actor.role] != actor.id:
        raise Forbidden(f"The actor is not the {actor.role.lower()} of this order.")

    courier_id = order.courier_id
    failed_attempts = order.failed_delivery_attempts
    if action == Action.ASSIGN:
        if not assigned_courier_id:
            raise InvalidInput("Assignment requires a courier ID.")
        courier_id = assigned_courier_id
    elif action == Action.WITHDRAW:
        courier_id = None
    elif action == Action.FAIL_DELIVERY:
        if failed_attempts >= 2:
            raise Conflict("The delivery attempt limit has been reached.")
        failed_attempts += 1
        if failed_attempts == 2:
            next_status = Status.RETURN_PENDING
        reason = "customer_unreachable"
    elif action == Action.CONFIRM_PAYMENT and next_status == Status.REFUNDED:
        reason = "payment_confirmed_after_cancellation"

    return Transition(next_status, courier_id, failed_attempts, reason)
