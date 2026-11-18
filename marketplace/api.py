from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .db import configured_sessions
from .domain import (
    MAX_ACTOR_ID,
    MAX_AMOUNT,
    MAX_REASON,
    MAX_REFERENCE,
    Action,
    Conflict,
    Forbidden,
    InvalidInput,
    MarketplaceError,
    OrderNotFound,
    Role,
    Status,
)
from .persistence.postgres_repository import PostgresRepository
from .services.order_service import OrderService
from .services.payment_service import PaymentService

ActorId = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ACTOR_ID)]
ActorHeader = Annotated[ActorId, Header(alias="X-Actor-Id")]
OrderId = Annotated[int, Path(gt=0, le=MAX_AMOUNT)]


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seller_id: ActorId
    amount_xof: Annotated[int, Field(strict=True, gt=0, le=MAX_AMOUNT)]


class OrderAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        Action.CANCEL, Action.REFUSE, Action.ACCEPT, Action.MARK_READY, Action.ASSIGN,
        Action.WITHDRAW, Action.PICK_UP, Action.DELIVER, Action.FAIL_DELIVERY,
        Action.RETRY_DELIVERY, Action.CONFIRM_RETURN,
    ]
    courier_id: ActorId | None = None
    reason: Annotated[str, StringConstraints(max_length=MAX_REASON)] | None = None


class PaymentNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REFERENCE)
    ]


class OrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    buyer_id: str
    seller_id: str
    courier_id: str | None
    amount_xof: int
    status: Status
    failed_delivery_attempts: int


class HistoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: str
    actor_role: Role
    action: Action
    from_status: Status | None
    to_status: Status
    occurred_at: datetime
    reason: str | None
    assigned_courier_id: str | None


class OrderDetails(BaseModel):
    order: OrderView
    history: list[HistoryView]


class ErrorView(BaseModel):
    detail: str


ERROR_STATUS = {Forbidden: 403, OrderNotFound: 404, Conflict: 409}


def create_app(
    orders: OrderService | None = None,
    payments: PaymentService | None = None,
) -> FastAPI:
    if orders is None and payments is None:
        repository = PostgresRepository(configured_sessions())
        orders = OrderService(repository.transaction)
        payments = PaymentService(repository.transaction)
    elif orders is None or payments is None:
        raise ValueError("Provide both services when configuring the app explicitly.")

    app = FastAPI(title="Cotonou Marketplace")

    @app.exception_handler(MarketplaceError)
    def handle_marketplace_error(_request: Request, error: MarketplaceError) -> JSONResponse:
        if isinstance(error, InvalidInput):
            return JSONResponse(
                status_code=422,
                content={"detail": [{"type": "value_error", "loc": ["body"], "msg": str(error)}]},
            )
        return JSONResponse(
            status_code=ERROR_STATUS[type(error)],
            content={"detail": str(error)},
        )

    @app.post("/orders", status_code=201, response_model=OrderView, responses={403: {"model": ErrorView}})
    def create_order(body: CreateOrder, actor_id: ActorHeader):
        return orders.create_order(actor_id, body.seller_id, body.amount_xof)

    @app.post(
        "/orders/{order_id}/actions",
        response_model=OrderView,
        responses={403: {"model": ErrorView}, 404: {"model": ErrorView}, 409: {"model": ErrorView}},
    )
    def apply_action(order_id: OrderId, body: OrderAction, actor_id: ActorHeader):
        return orders.apply_action(
            order_id, actor_id, Action(body.action), courier_id=body.courier_id, reason=body.reason
        )

    @app.post(
        "/orders/{order_id}/payment-notifications",
        response_model=OrderView,
        responses={403: {"model": ErrorView}, 404: {"model": ErrorView}, 409: {"model": ErrorView}},
    )
    def confirm_payment(order_id: OrderId, body: PaymentNotification, actor_id: ActorHeader):
        return payments.confirm_payment(order_id, actor_id, body.reference)

    @app.get("/orders/{order_id}", response_model=OrderDetails, responses={404: {"model": ErrorView}})
    def get_order(order_id: OrderId):
        order, history = orders.get_order(order_id)
        return {"order": order, "history": history}

    return app
