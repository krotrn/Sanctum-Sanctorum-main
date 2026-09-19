from datetime import datetime

import pytest

from tests.conftest import START


def create_member(client, **overrides):
    payload = {"name": "Stephen Strange", "email": "stephen@sanctum.org"}
    payload.update(overrides)
    return client.post("/members", json=payload)


class TestCreateMember:
    def test_create_returns_201_with_member(self, client):
        response = create_member(client, tier="master")
        assert response.status_code == 201
        body = response.json()
        assert isinstance(body["id"], int)
        assert body["name"] == "Stephen Strange"
        assert body["email"] == "stephen@sanctum.org"
        assert body["tier"] == "master"

    def test_tier_defaults_to_apprentice(self, client):
        assert create_member(client).json()["tier"] == "apprentice"

    @pytest.mark.parametrize("tier", ["apprentice", "adept", "master", "supreme"])
    def test_every_tier_is_accepted(self, client, tier):
        response = create_member(client, tier=tier)
        assert response.status_code == 201
        assert response.json()["tier"] == tier

    def test_unknown_tier_returns_422(self, client):
        assert create_member(client, tier="grandmaster").status_code == 422

    def test_created_at_is_current_clock_time(self, client):
        response = create_member(client)
        assert datetime.fromisoformat(response.json()["created_at"]) == START

    def test_created_at_follows_the_clock(self, client, clock):
        clock.advance(days=3, hours=2)
        response = create_member(client)
        assert datetime.fromisoformat(response.json()["created_at"]) == clock.current

    def test_name_is_stripped(self, client):
        assert create_member(client, name="  Wong  ").json()["name"] == "Wong"

    def test_name_of_100_chars_is_allowed(self, client):
        assert create_member(client, name="a" * 100).status_code == 201

    @pytest.mark.parametrize("name", ["", "    ", "a" * 101])
    def test_invalid_name_returns_422(self, client, name):
        assert create_member(client, name=name).status_code == 422

    def test_email_is_stripped_and_lowercased(self, client):
        response = create_member(client, email="  Stephen.Strange@Sanctum.ORG  ")
        assert response.status_code == 201
        assert response.json()["email"] == "stephen.strange@sanctum.org"

    @pytest.mark.parametrize(
        "email",
        [
            "",
            "plainaddress",
            "@sanctum.org",
            "wong@",
            "wong@sanctum",
            "wong@sanctum.",
            "wong@@sanctum.org",
            "wong strange@sanctum.org",
        ],
    )
    def test_invalid_email_returns_422(self, client, email):
        assert create_member(client, email=email).status_code == 422

    def test_duplicate_email_returns_409(self, client):
        assert create_member(client).status_code == 201
        assert create_member(client, name="Someone Else").status_code == 409

    def test_duplicate_email_is_case_insensitive(self, client):
        assert create_member(client, email="wong@sanctum.org").status_code == 201
        assert create_member(client, email="WONG@Sanctum.org").status_code == 409


class TestGetMember:
    def test_get_existing_member(self, client, make_member):
        member = make_member()
        response = client.get(f"/members/{member['id']}")
        assert response.status_code == 200
        assert response.json() == member

    def test_get_missing_member_returns_404(self, client):
        assert client.get("/members/9999").status_code == 404


class TestMemberStats:
    def test_new_member_has_zero_stats(self, client, make_member):
        member = make_member()
        response = client.get(f"/members/{member['id']}/stats")
        assert response.status_code == 200
        assert response.json() == {
            "member_id": member["id"],
            "orders_paid": 0,
            "total_spent_cents": 0,
            "active_loans": 0,
            "overdue_loans": 0,
            "late_fees_cents": 0,
        }

    def test_order_stats_count_only_paid_orders(self, client, make_member, make_book):
        member = make_member(tier="supreme")  # 15% discount
        book = make_book(price_cents=1000, stock=10)

        def order(quantity):
            body = {"member_id": member["id"], "items": [{"book_id": book["id"], "quantity": quantity}]}
            response = client.post("/orders", json=body)
            assert response.status_code == 201
            return response.json()["id"]

        client.post(f"/orders/{order(2)}/pay")  # total 1700
        client.post(f"/orders/{order(1)}/pay")  # total 850
        order(3)  # stays pending
        client.post(f"/orders/{order(4)}/cancel")

        stats = client.get(f"/members/{member['id']}/stats").json()
        assert stats["orders_paid"] == 2
        assert stats["total_spent_cents"] == 2550

    def test_loan_stats(self, client, clock, make_member, make_book):
        member = make_member(tier="supreme")
        returned_late = make_book(price_cents=1000)
        overdue = make_book()
        active = make_book()

        def borrow(book):
            body = {"member_id": member["id"], "book_id": book["id"]}
            response = client.post("/loans", json=body)
            assert response.status_code == 201
            return response.json()["id"]

        late_loan = borrow(returned_late)  # due START + 14d
        borrow(overdue)  # due START + 14d
        clock.advance(days=10)
        borrow(active)  # due START + 24d
        clock.advance(days=10)  # now START + 20d
        assert client.post(f"/loans/{late_loan}/return").status_code == 200  # 6 days late

        stats = client.get(f"/members/{member['id']}/stats").json()
        assert stats["active_loans"] == 2
        assert stats["overdue_loans"] == 1
        assert stats["late_fees_cents"] == 150

    def test_loan_due_exactly_now_counts_as_active_not_overdue(self, client, clock, make_member, make_book):
        member = make_member()
        book = make_book()
        body = {"member_id": member["id"], "book_id": book["id"]}
        assert client.post("/loans", json=body).status_code == 201  # due START + 14d
        clock.advance(days=14)  # now == due_at exactly

        stats = client.get(f"/members/{member['id']}/stats").json()
        assert stats["active_loans"] == 1
        assert stats["overdue_loans"] == 0

    def test_stats_for_missing_member_returns_404(self, client):
        assert client.get("/members/9999/stats").status_code == 404
