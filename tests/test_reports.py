import pytest


@pytest.fixture
def buy(client, make_member):
    """Place an order for (book, quantity) pairs and optionally pay or cancel it."""
    member = make_member()

    def _buy(*items, status="paid"):
        body = {
            "member_id": member["id"],
            "items": [{"book_id": book["id"], "quantity": qty} for book, qty in items],
        }
        response = client.post("/orders", json=body)
        assert response.status_code == 201, response.text
        order_id = response.json()["id"]
        if status == "paid":
            assert client.post(f"/orders/{order_id}/pay").status_code == 200
        elif status == "cancelled":
            assert client.post(f"/orders/{order_id}/cancel").status_code == 200

    return _buy


def top_books(client, **params):
    return client.get("/reports/top-books", params=params)


class TestTopBooks:
    def test_no_orders_returns_empty_list(self, client, make_book):
        make_book()
        response = top_books(client)
        assert response.status_code == 200
        assert response.json() == []

    def test_counts_paid_orders(self, client, make_book, buy):
        book = make_book(title="Book of Vishanti")
        buy((book, 2))
        buy((book, 3))
        assert top_books(client).json() == [
            {"book_id": book["id"], "title": "Book of Vishanti", "copies_sold": 5}
        ]

    def test_pending_and_cancelled_orders_are_excluded(self, client, make_book, buy):
        paid = make_book(title="Paid")
        pending = make_book(title="Pending")
        cancelled = make_book(title="Cancelled")
        buy((paid, 1), (pending, 1), (cancelled, 1))
        buy((pending, 5), status="pending")
        buy((cancelled, 5), status="cancelled")
        buy((paid, 1), status="pending")
        result = {row["title"]: row["copies_sold"] for row in top_books(client).json()}
        assert result == {"Paid": 1, "Pending": 1, "Cancelled": 1}

    def test_books_with_only_unpaid_orders_are_omitted(self, client, make_book, buy):
        paid = make_book(title="Paid")
        pending = make_book(title="Pending")
        buy((paid, 1))
        buy((pending, 3), status="pending")
        assert [row["book_id"] for row in top_books(client).json()] == [paid["id"]]

    def test_sorted_by_copies_desc_then_title_asc(self, client, make_book, buy):
        charlie = make_book(title="Charlie")
        alpha = make_book(title="Alpha")
        bravo = make_book(title="Bravo")
        delta = make_book(title="Delta")
        buy((charlie, 2), (alpha, 2), (bravo, 1), (delta, 3))
        titles = [row["title"] for row in top_books(client).json()]
        assert titles == ["Delta", "Alpha", "Charlie", "Bravo"]

    def test_default_limit_is_5(self, client, make_book, buy):
        books = [make_book() for _ in range(6)]
        buy(*[(book, 1) for book in books])
        assert len(top_books(client).json()) == 5

    def test_limit_parameter(self, client, make_book, buy):
        low = make_book(title="Low")
        high = make_book(title="High")
        mid = make_book(title="Mid")
        buy((low, 1), (high, 3), (mid, 2))
        assert [row["title"] for row in top_books(client, limit=2).json()] == ["High", "Mid"]

    @pytest.mark.parametrize("limit", [1, 50])
    def test_limit_bounds_are_accepted(self, client, limit):
        assert top_books(client, limit=limit).status_code == 200

    @pytest.mark.parametrize("limit", [0, 51])
    def test_out_of_range_limit_returns_422(self, client, limit):
        assert top_books(client, limit=limit).status_code == 422
