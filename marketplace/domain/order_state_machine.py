from .actors import Actor, Role
from .errors import Conflict, Forbidden, InvalidInput
from .orders import Action, OrderState, Status, Transition

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
    Action.RESHIP: Role.SELLER,
    Action.CANCEL_RETURNED: Role.SELLER,
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
    (Status.RETURNED, Action.RESHIP): Status.READY,
    (Status.RETURNED, Action.CANCEL_RETURNED): Status.REFUNDED,
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
    elif action == Action.RESHIP:
        courier_id = None
        failed_attempts = 0
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
