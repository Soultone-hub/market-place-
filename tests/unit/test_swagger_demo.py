from marketplace.api import CreateOrder, OrderAction, PaymentNotification, create_app
from marketplace.services.order_service import OrderService
from marketplace.services.payment_service import PaymentService


def body_examples(operation):
    return operation["requestBody"]["content"]["application/json"]["examples"]


def actor_examples(operation):
    actor_header = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "header" and parameter["name"] == "X-Actor-Id"
    )
    return {name: example["value"] for name, example in actor_header["examples"].items()}


def test_swagger_exposes_examples_for_the_order_demo():
    def unexpected_transaction():
        raise AssertionError("Generating the OpenAPI schema should not use the database.")

    paths = create_app(
        orders=OrderService(unexpected_transaction),
        payments=PaymentService(unexpected_transaction),
    ).openapi()["paths"]

    create_order = paths["/orders"]["post"]
    assert actor_examples(create_order)["buyer-1"] == "buyer-1"
    assert CreateOrder(seller_id="seller-1", amount_xof=7500) in [
        CreateOrder.model_validate(example["value"])
        for example in body_examples(create_order).values()
    ]

    confirm_payment = paths["/orders/{order_id}/payment-notifications"]["post"]
    assert actor_examples(confirm_payment)["system"] == "system"
    payment_examples = body_examples(confirm_payment)
    assert payment_examples
    for example in payment_examples.values():
        PaymentNotification.model_validate(example["value"])

    order_actions = paths["/orders/{order_id}/actions"]["post"]
    example_actors = actor_examples(order_actions)
    for actor in ("buyer-1", "seller-1", "system", "courier-1", "courier-2"):
        assert example_actors[actor] == actor

    actions = {
        name: OrderAction.model_validate(example["value"])
        for name, example in body_examples(order_actions).items()
    }
    for action in ("accept", "mark_ready", "assign", "pick_up", "deliver"):
        assert actions[action].action == action
    assert actions["assign"].courier_id == "courier-1"
