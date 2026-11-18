from asyncio import run

from httpx import ASGITransport, AsyncClient

from marketplace.api import create_app


def test_delivery_via_api_keeps_every_assignment(orders, payments):
    run(check_delivery_via_api(orders, payments))


async def check_delivery_via_api(orders, payments):
    transport = ASGITransport(app=create_app(orders, payments))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/docs")).status_code == 200
        created = await client.post(
            "/orders",
            json={"seller_id": "seller-1", "amount_xof": 7500},
            headers={"X-Actor-Id": "buyer-1"},
        )
        assert created.status_code == 201
        order_id = created.json()["id"]
        paid = await client.post(
            f"/orders/{order_id}/payment-notifications",
            json={"reference": "mobile-money-delivery"},
            headers={"X-Actor-Id": "system"},
        )
        assert paid.status_code == 200

        steps = [
            ("seller-1", "accept", "ACCEPTED", None),
            ("seller-1", "mark_ready", "ASSIGNED", "courier-1"),
            ("courier-1", "withdraw", "ASSIGNED", "courier-2"),
            ("courier-2", "pick_up", "IN_DELIVERY", "courier-2"),
            ("courier-2", "deliver", "DELIVERED", "courier-2"),
        ]
        for actor, action, status, courier in steps:
            result = await client.post(
                f"/orders/{order_id}/actions",
                json={"action": action},
                headers={"X-Actor-Id": actor},
            )
            assert result.status_code == 200, result.text
            assert result.json()["status"] == status
            assert result.json()["courier_id"] == courier

        details = (await client.get(f"/orders/{order_id}")).json()
        assert details["order"]["courier_id"] == "courier-2"
        history = details["history"]
        assert [(entry["action"], entry["to_status"], entry["actor_id"]) for entry in history] == [
            ("create", "PENDING_PAYMENT", "buyer-1"),
            ("confirm_payment", "PAID", "system"),
            ("accept", "ACCEPTED", "seller-1"),
            ("mark_ready", "READY", "seller-1"),
            ("assign", "ASSIGNED", "system"),
            ("withdraw", "READY", "courier-1"),
            ("assign", "ASSIGNED", "system"),
            ("pick_up", "IN_DELIVERY", "courier-2"),
            ("deliver", "DELIVERED", "courier-2"),
        ]
        assignments = [entry for entry in history if entry["action"] == "assign"]
        assert [entry["assigned_courier_id"] for entry in assignments] == [
            "courier-1", "courier-2"
        ]
        assert all(entry["actor_role"] == "SYSTEM" for entry in assignments)
        assert all(entry["reason"] == "automatic_assignment" for entry in assignments)


def test_assignment_without_courier_returns_validation_error(orders, payments):
    async def check_assignment():
        transport = ASGITransport(app=create_app(orders, payments))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/orders/1/actions",
                json={"action": "assign"},
                headers={"X-Actor-Id": "system"},
            )
        assert response.status_code == 422
        assert response.json()["detail"] == [
            {
                "type": "value_error",
                "loc": ["body"],
                "msg": "A courier ID is required for assignment only.",
            }
        ]

    run(check_assignment())
