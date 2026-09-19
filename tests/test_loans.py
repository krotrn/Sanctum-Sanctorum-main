from datetime import datetime, timedelta

import pytest

from tests.conftest import START


def borrow(client, member, book):
    return client.post("/loans", json={"member_id": member["id"], "book_id": book["id"]})


def return_loan(client, loan):
    return client.post(f"/loans/{loan['id']}/return")


def stock_of(client, book):
    return client.get(f"/books/{book['id']}").json()["stock"]


class TestBorrow:
    def test_borrow_returns_201_with_loan(self, client, make_member, make_book):
        member = make_member()
        book = make_book()
        response = borrow(client, member, book)
        assert response.status_code == 201
        loan = response.json()
        assert isinstance(loan["id"], int)
        assert loan["member_id"] == member["id"]
        assert loan["book_id"] == book["id"]
        assert datetime.fromisoformat(loan["borrowed_at"]) == START
        assert datetime.fromisoformat(loan["due_at"]) == START + timedelta(days=14)
        assert loan["returned_at"] is None
        assert loan["late_fee_cents"] == 0
        assert loan["status"] == "active"

    def test_borrow_uses_current_clock_time(self, client, clock, make_member, make_book):
        clock.advance(days=5, hours=3)
        loan = borrow(client, make_member(), make_book()).json()
        assert datetime.fromisoformat(loan["borrowed_at"]) == clock.current
        assert datetime.fromisoformat(loan["due_at"]) == clock.current + timedelta(days=14)

    def test_borrow_decrements_stock(self, client, make_member, make_book):
        book = make_book(stock=3)
        borrow(client, make_member(), book)
        assert stock_of(client, book) == 2

    def test_loan_can_be_fetched(self, client, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        response = client.get(f"/loans/{loan['id']}")
        assert response.status_code == 200
        assert response.json() == loan

    def test_get_missing_loan_returns_404(self, client):
        assert client.get("/loans/9999").status_code == 404

    def test_missing_member_returns_404(self, client, make_book):
        response = client.post("/loans", json={"member_id": 9999, "book_id": make_book()["id"]})
        assert response.status_code == 404

    def test_missing_book_returns_404(self, client, make_member):
        response = client.post("/loans", json={"member_id": make_member()["id"], "book_id": 9999})
        assert response.status_code == 404

    @pytest.mark.parametrize("tier", ["apprentice", "adept"])
    def test_restricted_book_below_master_returns_403(self, client, make_member, make_book, tier):
        book = make_book(restricted=True)
        assert borrow(client, make_member(tier=tier), book).status_code == 403
        assert stock_of(client, book) == 10

    @pytest.mark.parametrize("tier", ["master", "supreme"])
    def test_restricted_book_allowed_for_master_and_above(self, client, make_member, make_book, tier):
        book = make_book(restricted=True)
        assert borrow(client, make_member(tier=tier), book).status_code == 201

    def test_out_of_stock_returns_409(self, client, make_member, make_book):
        book = make_book(stock=0)
        assert borrow(client, make_member(), book).status_code == 409

    def test_last_copy_borrowed_by_someone_else_returns_409(self, client, make_member, make_book):
        book = make_book(stock=1)
        assert borrow(client, make_member(), book).status_code == 201
        assert borrow(client, make_member(), book).status_code == 409

    def test_same_book_twice_returns_409(self, client, make_member, make_book):
        member = make_member(tier="supreme")
        book = make_book(stock=10)
        assert borrow(client, member, book).status_code == 201
        assert borrow(client, member, book).status_code == 409
        assert stock_of(client, book) == 9

    def test_same_book_can_be_borrowed_again_after_return(self, client, make_member, make_book):
        member = make_member(tier="supreme")
        book = make_book()
        loan = borrow(client, member, book).json()
        return_loan(client, loan)
        assert borrow(client, member, book).status_code == 201

    def test_overdue_loan_blocks_borrowing(self, client, clock, make_member, make_book):
        member = make_member(tier="supreme")
        borrow(client, member, make_book())
        clock.advance(days=14, seconds=1)
        assert borrow(client, member, make_book()).status_code == 409

    def test_loan_due_right_now_does_not_block_borrowing(self, client, clock, make_member, make_book):
        member = make_member(tier="supreme")
        borrow(client, member, make_book())
        clock.advance(days=14)
        assert borrow(client, member, make_book()).status_code == 201

    def test_returned_overdue_loan_no_longer_blocks(self, client, clock, make_member, make_book):
        member = make_member(tier="supreme")
        loan = borrow(client, member, make_book()).json()
        clock.advance(days=20)
        return_loan(client, loan)
        assert borrow(client, member, make_book()).status_code == 201

    def test_403_checked_before_overdue(self, client, clock, make_member, make_book):
        member = make_member(tier="adept")
        borrow(client, member, make_book())
        clock.advance(days=15)
        assert borrow(client, member, make_book(restricted=True)).status_code == 403


class TestLoanLimits:
    @pytest.mark.parametrize("tier, limit", [("apprentice", 1), ("adept", 3), ("master", 5)])
    def test_tier_limit(self, client, make_member, make_book, tier, limit):
        member = make_member(tier=tier)
        for _ in range(limit):
            assert borrow(client, member, make_book()).status_code == 201
        extra = make_book()
        assert borrow(client, member, extra).status_code == 409
        assert stock_of(client, extra) == 10

    def test_supreme_has_no_limit(self, client, make_member, make_book):
        member = make_member(tier="supreme")
        for _ in range(8):
            assert borrow(client, member, make_book()).status_code == 201

    def test_returned_loans_do_not_count_toward_limit(self, client, make_member, make_book):
        member = make_member(tier="apprentice")
        loan = borrow(client, member, make_book()).json()
        return_loan(client, loan)
        assert borrow(client, member, make_book()).status_code == 201


class TestReturnLoan:
    def test_return_sets_returned_at_and_status(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        clock.advance(days=3)
        response = return_loan(client, loan)
        assert response.status_code == 200
        body = response.json()
        assert datetime.fromisoformat(body["returned_at"]) == clock.current
        assert body["status"] == "returned"
        assert body["late_fee_cents"] == 0

    def test_return_restores_stock(self, client, make_member, make_book):
        book = make_book(stock=1)
        loan = borrow(client, make_member(), book).json()
        return_loan(client, loan)
        assert stock_of(client, book) == 1

    def test_return_twice_returns_409(self, client, make_member, make_book):
        book = make_book(stock=5)
        loan = borrow(client, make_member(), book).json()
        return_loan(client, loan)
        assert return_loan(client, loan).status_code == 409
        assert stock_of(client, book) == 5

    def test_return_missing_loan_returns_404(self, client):
        assert client.post("/loans/9999/return").status_code == 404

    @pytest.mark.parametrize(
        "elapsed, fee",
        [
            (timedelta(days=13), 0),  # early
            (timedelta(days=14), 0),  # exactly at due_at
            (timedelta(days=14, seconds=1), 25),  # 1 second late -> 1 day
            (timedelta(days=16), 50),  # exactly 2 days late
            (timedelta(days=17, hours=1), 100),  # 3 days + 1 hour late -> 4 days
        ],
    )
    def test_late_fee(self, client, clock, make_member, make_book, elapsed, fee):
        loan = borrow(client, make_member(), make_book(price_cents=10_000)).json()
        clock.advance(seconds=elapsed.total_seconds())
        body = return_loan(client, loan).json()
        assert body["late_fee_cents"] == fee

    def test_late_fee_is_capped_at_book_price(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book(price_cents=60)).json()
        clock.advance(days=24)  # 10 days late -> 250 uncapped
        assert return_loan(client, loan).json()["late_fee_cents"] == 60

    def test_late_fee_is_persisted(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        clock.advance(days=15)
        return_loan(client, loan)
        assert client.get(f"/loans/{loan['id']}").json()["late_fee_cents"] == 25


class TestLoanStatus:
    def test_status_is_active_until_due(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        clock.advance(days=14)
        assert client.get(f"/loans/{loan['id']}").json()["status"] == "active"

    def test_status_becomes_overdue_after_due(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        clock.advance(days=14, seconds=1)
        assert client.get(f"/loans/{loan['id']}").json()["status"] == "overdue"

    def test_returned_late_loan_stays_returned(self, client, clock, make_member, make_book):
        loan = borrow(client, make_member(), make_book()).json()
        clock.advance(days=20)
        return_loan(client, loan)
        clock.advance(days=30)
        assert client.get(f"/loans/{loan['id']}").json()["status"] == "returned"


class TestMemberLoans:
    @pytest.fixture
    def member_with_loans(self, client, clock, make_member, make_book):
        """Supreme member with one overdue, one returned and one active loan."""
        member = make_member(tier="supreme")
        overdue = borrow(client, member, make_book()).json()  # due START + 14d
        returned = borrow(client, member, make_book()).json()
        return_loan(client, returned)
        clock.advance(days=10)
        active = borrow(client, member, make_book()).json()  # due START + 24d
        clock.advance(days=5)  # now START + 15d
        return member, overdue, returned, active

    def test_lists_all_loans_by_id(self, client, member_with_loans):
        member, overdue, returned, active = member_with_loans
        response = client.get(f"/members/{member['id']}/loans")
        assert response.status_code == 200
        body = response.json()
        assert [loan["id"] for loan in body] == [overdue["id"], returned["id"], active["id"]]
        assert [loan["status"] for loan in body] == ["overdue", "returned", "active"]

    @pytest.mark.parametrize("status, index", [("overdue", 1), ("returned", 2), ("active", 3)])
    def test_status_filter(self, client, member_with_loans, status, index):
        member = member_with_loans[0]
        expected = member_with_loans[index]
        response = client.get(f"/members/{member['id']}/loans", params={"status": status})
        assert response.status_code == 200
        assert [loan["id"] for loan in response.json()] == [expected["id"]]

    def test_excludes_other_members_loans(self, client, make_member, make_book):
        member = make_member()
        borrow(client, make_member(), make_book())
        assert client.get(f"/members/{member['id']}/loans").json() == []

    def test_invalid_status_filter_returns_422(self, client, make_member):
        member = make_member()
        response = client.get(f"/members/{member['id']}/loans", params={"status": "late"})
        assert response.status_code == 422

    def test_missing_member_returns_404(self, client):
        assert client.get("/members/9999/loans").status_code == 404
