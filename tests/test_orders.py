from datetime import datetime, timedelta

import pytest

from tests.conftest import START


def place_order(client, member_id, *items):
    """items: (book_id, quantity) pairs."""
    body = {
        "member_id": member_id,
        "items": [{"book_id": book_id, "quantity": quantity} for book_id, quantity in items],
    }
    return client.post("/orders", json=body)


def stock_of(client, book):
    return client.get(f"/books/{book['id']}").json()["stock"]


class TestCreateOrder:
    def test_create_returns_201_pending_order(self, client, make_member, make_book):
        member = make_member()
        book = make_book(price_cents=1200)
        response = place_order(client, member["id"], (book["id"], 2))
        assert response.status_code == 201
        body = response.json()
        assert isinstance(body["id"], int)
        assert body["member_id"] == member["id"]
        assert body["status"] == "pending"
        assert body["items"] == [
            {"book_id": book["id"], "quantity": 2, "unit_price_cents": 1200, "line_total_cents": 2400}
        ]
        assert body["subtotal_cents"] == 2400
        assert body["discount_percent"] == 0
        assert body["discount_cents"] == 0
        assert body["total_cents"] == 2400

    def test_created_at_is_current_clock_time(self, client, clock, make_member, make_book):
        clock.advance(days=2)
        response = place_order(client, make_member()["id"], (make_book()["id"], 1))
        assert datetime.fromisoformat(response.json()["created_at"]) == START + timedelta(days=2)

    def test_items_keep_submitted_order(self, client, make_member, make_book):
        first = make_book(price_cents=100)
        second = make_book(price_cents=300)
        response = place_order(client, make_member()["id"], (second["id"], 1), (first["id"], 2))
        body = response.json()
        assert [item["book_id"] for item in body["items"]] == [second["id"], first["id"]]
        assert [item["line_total_cents"] for item in body["items"]] == [300, 200]
        assert body["subtotal_cents"] == 500

    def test_order_can_be_fetched(self, client, make_member, make_book):
        created = place_order(client, make_member()["id"], (make_book()["id"], 1)).json()
        response = client.get(f"/orders/{created['id']}")
        assert response.status_code == 200
        assert response.json() == created

    def test_get_missing_order_returns_404(self, client):
        assert client.get("/orders/9999").status_code == 404


class TestOrderPricing:
    @pytest.mark.parametrize(
        "tier, percent, total",
        [("apprentice", 0, 1000), ("adept", 5, 950), ("master", 10, 900), ("supreme", 15, 850)],
    )
    def test_tier_discount(self, client, make_member, make_book, tier, percent, total):
        member = make_member(tier=tier)
        book = make_book(price_cents=1000)
        body = place_order(client, member["id"], (book["id"], 1)).json()
        assert body["subtotal_cents"] == 1000
        assert body["discount_percent"] == percent
        assert body["discount_cents"] == 1000 - total
        assert body["total_cents"] == total

    def test_bulk_discount_at_exactly_10_copies(self, client, make_member, make_book):
        book = make_book(price_cents=100, stock=20)
        body = place_order(client, make_member()["id"], (book["id"], 10)).json()
        assert body["discount_percent"] == 5
        assert body["discount_cents"] == 50
        assert body["total_cents"] == 950

    def test_no_bulk_discount_at_9_copies(self, client, make_member, make_book):
        book = make_book(price_cents=100, stock=20)
        body = place_order(client, make_member()["id"], (book["id"], 9)).json()
        assert body["discount_percent"] == 0
        assert body["total_cents"] == 900

    def test_bulk_threshold_counts_quantity_across_items(self, client, make_member, make_book):
        a = make_book(price_cents=100)
        b = make_book(price_cents=100)
        body = place_order(client, make_member()["id"], (a["id"], 4), (b["id"], 6)).json()
        assert body["discount_percent"] == 5

    def test_tier_and_bulk_discounts_add_up(self, client, make_member, make_book):
        book = make_book(price_cents=100, stock=20)
        body = place_order(client, make_member(tier="supreme")["id"], (book["id"], 10)).json()
        assert body["discount_percent"] == 20
        assert body["discount_cents"] == 200
        assert body["total_cents"] == 800

    def test_discount_is_rounded_down(self, client, make_member, make_book):
        book = make_book(price_cents=999)
        body = place_order(client, make_member(tier="adept")["id"], (book["id"], 1)).json()
        # 999 * 5 / 100 = 49.95 -> 49
        assert body["discount_cents"] == 49
        assert body["total_cents"] == 950

    def test_unit_price_is_frozen_at_order_time(self, client, make_member, make_book):
        book = make_book(price_cents=1000)
        order = place_order(client, make_member()["id"], (book["id"], 2)).json()
        client.patch(f"/books/{book['id']}", json={"price_cents": 5000})
        fetched = client.get(f"/orders/{order['id']}").json()
        assert fetched["items"][0]["unit_price_cents"] == 1000
        assert fetched["total_cents"] == 2000


class TestOrderStock:
    def test_stock_is_reserved_on_creation(self, client, make_member, make_book):
        book = make_book(stock=10)
        place_order(client, make_member()["id"], (book["id"], 3))
        assert stock_of(client, book) == 7

    def test_ordering_entire_stock_is_allowed(self, client, make_member, make_book):
        book = make_book(stock=4)
        assert place_order(client, make_member()["id"], (book["id"], 4)).status_code == 201
        assert stock_of(client, book) == 0

    def test_insufficient_stock_returns_409(self, client, make_member, make_book):
        book = make_book(stock=2)
        assert place_order(client, make_member()["id"], (book["id"], 3)).status_code == 409

    def test_reserved_stock_is_unavailable_to_later_orders(self, client, make_member, make_book):
        book = make_book(stock=5)
        member = make_member()
        assert place_order(client, member["id"], (book["id"], 4)).status_code == 201
        assert place_order(client, member["id"], (book["id"], 2)).status_code == 409

    def test_insufficient_stock_is_all_or_nothing(self, client, make_member, make_book):
        member = make_member()
        plenty = make_book(stock=5)
        scarce = make_book(stock=1)
        response = place_order(client, member["id"], (plenty["id"], 2), (scarce["id"], 2))
        assert response.status_code == 409
        assert stock_of(client, plenty) == 5
        assert stock_of(client, scarce) == 1
        assert client.get(f"/members/{member['id']}/orders").json() == []


class TestOrderValidation:
    def test_empty_items_returns_422(self, client, make_member):
        assert place_order(client, make_member()["id"]).status_code == 422

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_quantity_below_one_returns_422(self, client, make_member, make_book, quantity):
        response = place_order(client, make_member()["id"], (make_book()["id"], quantity))
        assert response.status_code == 422

    def test_duplicate_book_returns_422(self, client, make_member, make_book):
        book = make_book()
        response = place_order(client, make_member()["id"], (book["id"], 1), (book["id"], 2))
        assert response.status_code == 422

    def test_missing_member_returns_404(self, client, make_book):
        assert place_order(client, 9999, (make_book()["id"], 1)).status_code == 404

    def test_missing_book_returns_404(self, client, make_member, make_book):
        response = place_order(client, make_member()["id"], (make_book()["id"], 1), (9999, 1))
        assert response.status_code == 404

    @pytest.mark.parametrize("tier", ["apprentice", "adept"])
    def test_restricted_book_below_master_returns_403(self, client, make_member, make_book, tier):
        book = make_book(restricted=True)
        response = place_order(client, make_member(tier=tier)["id"], (book["id"], 1))
        assert response.status_code == 403
        assert stock_of(client, book) == 10

    @pytest.mark.parametrize("tier", ["master", "supreme"])
    def test_restricted_book_allowed_for_master_and_above(self, client, make_member, make_book, tier):
        book = make_book(restricted=True)
        response = place_order(client, make_member(tier=tier)["id"], (book["id"], 1))
        assert response.status_code == 201

    def test_422_checked_before_missing_member(self, client, make_book):
        book = make_book()
        assert place_order(client, 9999, (book["id"], 1), (book["id"], 1)).status_code == 422

    def test_404_checked_before_restricted(self, client, make_member, make_book):
        restricted = make_book(restricted=True)
        member = make_member(tier="apprentice")
        response = place_order(client, member["id"], (restricted["id"], 1), (9999, 1))
        assert response.status_code == 404

    def test_403_checked_before_insufficient_stock(self, client, make_member, make_book):
        restricted = make_book(restricted=True, stock=1)
        response = place_order(client, make_member()["id"], (restricted["id"], 5))
        assert response.status_code == 403


class TestPayOrder:
    def test_pay_pending_order(self, client, make_member, make_book):
        order = place_order(client, make_member()["id"], (make_book()["id"], 1)).json()
        response = client.post(f"/orders/{order['id']}/pay")
        assert response.status_code == 200
        assert response.json() == {**order, "status": "paid"}
        assert client.get(f"/orders/{order['id']}").json()["status"] == "paid"

    def test_pay_keeps_stock_reserved(self, client, make_member, make_book):
        book = make_book(stock=10)
        order = place_order(client, make_member()["id"], (book["id"], 3)).json()
        client.post(f"/orders/{order['id']}/pay")
        assert stock_of(client, book) == 7

    def test_pay_twice_returns_409(self, client, make_member, make_book):
        order = place_order(client, make_member()["id"], (make_book()["id"], 1)).json()
        client.post(f"/orders/{order['id']}/pay")
        assert client.post(f"/orders/{order['id']}/pay").status_code == 409

    def test_pay_cancelled_order_returns_409(self, client, make_member, make_book):
        order = place_order(client, make_member()["id"], (make_book()["id"], 1)).json()
        client.post(f"/orders/{order['id']}/cancel")
        assert client.post(f"/orders/{order['id']}/pay").status_code == 409
        assert client.get(f"/orders/{order['id']}").json()["status"] == "cancelled"

    def test_pay_missing_order_returns_404(self, client):
        assert client.post("/orders/9999/pay").status_code == 404


class TestCancelOrder:
    def test_cancel_pending_order(self, client, make_member, make_book):
        order = place_order(client, make_member()["id"], (make_book()["id"], 1)).json()
        response = client.post(f"/orders/{order['id']}/cancel")
        assert response.status_code == 200
        assert response.json() == {**order, "status": "cancelled"}

    def test_cancel_restores_stock_of_every_item(self, client, make_member, make_book):
        a = make_book(stock=10)
        b = make_book(stock=5)
        order = place_order(client, make_member()["id"], (a["id"], 3), (b["id"], 5)).json()
        client.post(f"/orders/{order['id']}/cancel")
        assert stock_of(client, a) == 10
        assert stock_of(client, b) == 5

    def test_cancel_twice_returns_409_and_does_not_restore_again(self, client, make_member, make_book):
        book = make_book(stock=10)
        order = place_order(client, make_member()["id"], (book["id"], 3)).json()
        client.post(f"/orders/{order['id']}/cancel")
        assert client.post(f"/orders/{order['id']}/cancel").status_code == 409
        assert stock_of(client, book) == 10

    def test_cancel_paid_order_returns_409(self, client, make_member, make_book):
        book = make_book(stock=10)
        order = place_order(client, make_member()["id"], (book["id"], 3)).json()
        client.post(f"/orders/{order['id']}/pay")
        assert client.post(f"/orders/{order['id']}/cancel").status_code == 409
        assert stock_of(client, book) == 7
        assert client.get(f"/orders/{order['id']}").json()["status"] == "paid"

    def test_cancel_missing_order_returns_404(self, client):
        assert client.post("/orders/9999/cancel").status_code == 404


class TestMemberOrders:
    def test_lists_member_orders_by_id_with_any_status(self, client, make_member, make_book):
        member = make_member()
        other = make_member()
        book = make_book()
        first = place_order(client, member["id"], (book["id"], 1)).json()
        place_order(client, other["id"], (book["id"], 1))
        second = place_order(client, member["id"], (book["id"], 2)).json()
        third = place_order(client, member["id"], (book["id"], 1)).json()
        client.post(f"/orders/{first['id']}/pay")
        client.post(f"/orders/{second['id']}/cancel")

        response = client.get(f"/members/{member['id']}/orders")
        assert response.status_code == 200
        body = response.json()
        assert [o["id"] for o in body] == [first["id"], second["id"], third["id"]]
        assert [o["status"] for o in body] == ["paid", "cancelled", "pending"]
        assert body[2] == third

    def test_member_without_orders_gets_empty_list(self, client, make_member):
        member = make_member()
        response = client.get(f"/members/{member['id']}/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_missing_member_returns_404(self, client):
        assert client.get("/members/9999/orders").status_code == 404
