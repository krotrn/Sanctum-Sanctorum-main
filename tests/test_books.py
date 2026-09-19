import pytest

from tests.conftest import isbn13


def book_payload(**overrides) -> dict:
    payload = {
        "title": "The Book of Vishanti",
        "author": "Anonymous",
        "isbn": isbn13(500),
        "price_cents": 2500,
        "stock": 3,
    }
    payload.update(overrides)
    return payload


def hyphenate(isbn: str) -> str:
    return f"{isbn[:3]}-{isbn[3]}-{isbn[4:8]}-{isbn[8:12]}-{isbn[12]}"


def ids(response) -> list:
    return [book["id"] for book in response.json()["items"]]


class TestCreateBook:
    def test_create_returns_201_with_book(self, client):
        response = client.post("/books", json=book_payload())
        assert response.status_code == 201
        body = response.json()
        assert isinstance(body["id"], int)
        assert body["title"] == "The Book of Vishanti"
        assert body["author"] == "Anonymous"
        assert body["isbn"] == isbn13(500)
        assert body["price_cents"] == 2500
        assert body["stock"] == 3

    def test_restricted_defaults_to_false(self, client):
        response = client.post("/books", json=book_payload())
        assert response.json()["restricted"] is False

    def test_restricted_can_be_set(self, client):
        response = client.post("/books", json=book_payload(restricted=True))
        assert response.status_code == 201
        assert response.json()["restricted"] is True

    def test_title_and_author_are_stripped(self, client):
        response = client.post("/books", json=book_payload(title="  Tome  ", author=" Wong   "))
        assert response.status_code == 201
        assert response.json()["title"] == "Tome"
        assert response.json()["author"] == "Wong"

    def test_zero_price_and_zero_stock_are_allowed(self, client):
        response = client.post("/books", json=book_payload(price_cents=0, stock=0))
        assert response.status_code == 201

    def test_title_of_200_chars_is_allowed(self, client):
        response = client.post("/books", json=book_payload(title="a" * 200))
        assert response.status_code == 201

    def test_length_limit_applies_after_stripping(self, client):
        response = client.post("/books", json=book_payload(title="   " + "a" * 200 + "   "))
        assert response.status_code == 201
        assert response.json()["title"] == "a" * 200

    @pytest.mark.parametrize(
        "overrides",
        [
            {"title": ""},
            {"title": "   "},
            {"title": "a" * 201},
            {"author": ""},
            {"author": "   "},
            {"author": "a" * 201},
            {"price_cents": -1},
            {"stock": -1},
        ],
    )
    def test_invalid_fields_return_422(self, client, overrides):
        response = client.post("/books", json=book_payload(**overrides))
        assert response.status_code == 422

    def test_isbn_hyphens_are_removed(self, client):
        response = client.post("/books", json=book_payload(isbn=hyphenate(isbn13(500))))
        assert response.status_code == 201
        assert response.json()["isbn"] == isbn13(500)

    def test_isbn_spaces_are_removed(self, client):
        spaced = hyphenate(isbn13(500)).replace("-", " ")
        response = client.post("/books", json=book_payload(isbn=spaced))
        assert response.status_code == 201
        assert response.json()["isbn"] == isbn13(500)

    def test_isbn_with_bad_checksum_returns_422(self, client):
        valid = isbn13(500)
        wrong_check_digit = str((int(valid[12]) + 1) % 10)
        response = client.post("/books", json=book_payload(isbn=valid[:12] + wrong_check_digit))
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "isbn",
        [
            isbn13(500)[:12],  # 12 digits
            isbn13(500) + "0",  # 14 digits
            "97800000005AB",  # 13 chars, not all digits
            "",
        ],
    )
    def test_isbn_with_wrong_shape_returns_422(self, client, isbn):
        response = client.post("/books", json=book_payload(isbn=isbn))
        assert response.status_code == 422

    def test_duplicate_isbn_returns_409(self, client):
        assert client.post("/books", json=book_payload()).status_code == 201
        response = client.post("/books", json=book_payload(title="Another"))
        assert response.status_code == 409

    def test_duplicate_isbn_detected_after_normalization(self, client):
        assert client.post("/books", json=book_payload()).status_code == 201
        response = client.post("/books", json=book_payload(isbn=hyphenate(isbn13(500))))
        assert response.status_code == 409


class TestGetBook:
    def test_get_existing_book(self, client, make_book):
        book = make_book()
        response = client.get(f"/books/{book['id']}")
        assert response.status_code == 200
        assert response.json() == book

    def test_get_missing_book_returns_404(self, client):
        assert client.get("/books/9999").status_code == 404


class TestPatchBook:
    def test_partial_update_changes_only_given_fields(self, client, make_book):
        book = make_book(price_cents=1000, stock=4)
        response = client.patch(f"/books/{book['id']}", json={"price_cents": 1500})
        assert response.status_code == 200
        assert response.json() == {**book, "price_cents": 1500}

    def test_update_all_patchable_fields(self, client, make_book):
        book = make_book()
        changes = {
            "title": "New Title",
            "author": "New Author",
            "price_cents": 0,
            "stock": 0,
            "restricted": True,
        }
        response = client.patch(f"/books/{book['id']}", json=changes)
        assert response.status_code == 200
        assert response.json() == {**book, **changes}

    def test_update_is_persisted(self, client, make_book):
        book = make_book()
        client.patch(f"/books/{book['id']}", json={"stock": 42})
        assert client.get(f"/books/{book['id']}").json()["stock"] == 42

    def test_title_is_stripped_on_update(self, client, make_book):
        book = make_book()
        response = client.patch(f"/books/{book['id']}", json={"title": "  Trimmed  "})
        assert response.json()["title"] == "Trimmed"

    def test_isbn_is_ignored(self, client, make_book):
        book = make_book()
        response = client.patch(f"/books/{book['id']}", json={"isbn": isbn13(777), "stock": 1})
        assert response.status_code == 200
        assert response.json()["isbn"] == book["isbn"]
        assert response.json()["stock"] == 1

    @pytest.mark.parametrize(
        "changes",
        [
            {"title": "   "},
            {"title": "a" * 201},
            {"author": ""},
            {"price_cents": -1},
            {"stock": -5},
        ],
    )
    def test_invalid_update_returns_422_and_changes_nothing(self, client, make_book, changes):
        book = make_book()
        response = client.patch(f"/books/{book['id']}", json=changes)
        assert response.status_code == 422
        assert client.get(f"/books/{book['id']}").json() == book

    def test_patch_missing_book_returns_404(self, client):
        assert client.patch("/books/9999", json={"stock": 1}).status_code == 404


class TestListBooks:
    def test_empty_store(self, client):
        response = client.get("/books")
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}

    def test_default_order_is_id_ascending(self, client, make_book):
        created = [make_book(title=t)["id"] for t in ["Charlie", "Alpha", "Bravo"]]
        assert ids(client.get("/books")) == created

    def test_items_are_full_book_objects(self, client, make_book):
        book = make_book()
        assert client.get("/books").json()["items"] == [book]

    def test_q_matches_title_case_insensitively(self, client, make_book):
        match = make_book(title="The Darkhold")
        make_book(title="Book of Cagliostro")
        assert ids(client.get("/books", params={"q": "DARKHOLD"})) == [match["id"]]

    def test_q_matches_author_case_insensitively(self, client, make_book):
        make_book(author="Cagliostro")
        match = make_book(author="Wong the Librarian")
        assert ids(client.get("/books", params={"q": "librar"})) == [match["id"]]

    def test_q_matches_title_or_author(self, client, make_book):
        by_title = make_book(title="Astral Projection", author="Someone")
        by_author = make_book(title="Untitled", author="Astral Scholar")
        make_book(title="Other", author="Nobody")
        response = client.get("/books", params={"q": "astral"})
        assert ids(response) == [by_title["id"], by_author["id"]]
        assert response.json()["total"] == 2

    def test_restricted_filter_true(self, client, make_book):
        make_book(restricted=False)
        secret = make_book(restricted=True)
        assert ids(client.get("/books", params={"restricted": "true"})) == [secret["id"]]

    def test_restricted_filter_false(self, client, make_book):
        public = make_book(restricted=False)
        make_book(restricted=True)
        assert ids(client.get("/books", params={"restricted": "false"})) == [public["id"]]

    def test_price_range_is_inclusive(self, client, make_book):
        books = [make_book(price_cents=p) for p in [100, 200, 300, 400]]
        response = client.get("/books", params={"min_price": 200, "max_price": 300})
        assert ids(response) == [books[1]["id"], books[2]["id"]]

    def test_min_price_only(self, client, make_book):
        books = [make_book(price_cents=p) for p in [100, 200, 300]]
        response = client.get("/books", params={"min_price": 200})
        assert ids(response) == [books[1]["id"], books[2]["id"]]

    def test_max_price_only(self, client, make_book):
        books = [make_book(price_cents=p) for p in [100, 200, 300]]
        response = client.get("/books", params={"max_price": 200})
        assert ids(response) == [books[0]["id"], books[1]["id"]]

    def test_filters_combine(self, client, make_book):
        make_book(title="Magic A", price_cents=100, restricted=True)
        match = make_book(title="Magic B", price_cents=500, restricted=True)
        make_book(title="Magic C", price_cents=500, restricted=False)
        make_book(title="Mundane", price_cents=500, restricted=True)
        params = {"q": "magic", "restricted": "true", "min_price": 200}
        assert ids(client.get("/books", params=params)) == [match["id"]]

    def test_sort_by_title_with_id_tie_break(self, client, make_book):
        bravo = make_book(title="Bravo")
        alpha1 = make_book(title="Alpha")
        charlie = make_book(title="Charlie")
        alpha2 = make_book(title="Alpha")
        response = client.get("/books", params={"sort": "title"})
        assert ids(response) == [alpha1["id"], alpha2["id"], bravo["id"], charlie["id"]]

    def test_sort_by_title_descending_with_id_tie_break(self, client, make_book):
        bravo = make_book(title="Bravo")
        alpha1 = make_book(title="Alpha")
        charlie = make_book(title="Charlie")
        alpha2 = make_book(title="Alpha")
        response = client.get("/books", params={"sort": "-title"})
        assert ids(response) == [charlie["id"], bravo["id"], alpha1["id"], alpha2["id"]]

    def test_sort_by_price_with_id_tie_break(self, client, make_book):
        mid = make_book(price_cents=200)
        cheap1 = make_book(price_cents=100)
        expensive = make_book(price_cents=300)
        cheap2 = make_book(price_cents=100)
        response = client.get("/books", params={"sort": "price"})
        assert ids(response) == [cheap1["id"], cheap2["id"], mid["id"], expensive["id"]]

    def test_sort_by_price_descending_with_id_tie_break(self, client, make_book):
        mid = make_book(price_cents=200)
        cheap = make_book(price_cents=100)
        expensive1 = make_book(price_cents=300)
        expensive2 = make_book(price_cents=300)
        response = client.get("/books", params={"sort": "-price"})
        assert ids(response) == [expensive1["id"], expensive2["id"], mid["id"], cheap["id"]]

    @pytest.mark.parametrize("sort", ["id", "author", "+price", "price_desc"])
    def test_invalid_sort_returns_422(self, client, sort):
        assert client.get("/books", params={"sort": sort}).status_code == 422

    def test_pagination_with_limit_and_offset(self, client, make_book):
        books = [make_book() for _ in range(5)]
        response = client.get("/books", params={"limit": 2, "offset": 2})
        assert response.status_code == 200
        body = response.json()
        assert [b["id"] for b in body["items"]] == [books[2]["id"], books[3]["id"]]
        assert body["total"] == 5
        assert body["limit"] == 2
        assert body["offset"] == 2

    def test_default_limit_is_20(self, client, make_book):
        for _ in range(21):
            make_book()
        body = client.get("/books").json()
        assert len(body["items"]) == 20
        assert body["total"] == 21

    def test_offset_past_end_returns_no_items_but_total(self, client, make_book):
        make_book()
        make_book()
        body = client.get("/books", params={"offset": 10}).json()
        assert body["items"] == []
        assert body["total"] == 2

    def test_total_counts_filtered_results_before_pagination(self, client, make_book):
        for _ in range(3):
            make_book(restricted=True)
        make_book(restricted=False)
        body = client.get("/books", params={"restricted": "true", "limit": 1}).json()
        assert len(body["items"]) == 1
        assert body["total"] == 3

    def test_sort_applies_before_pagination(self, client, make_book):
        make_book(price_cents=300)
        cheapest = make_book(price_cents=100)
        make_book(price_cents=200)
        response = client.get("/books", params={"sort": "price", "limit": 1})
        assert ids(response) == [cheapest["id"]]

    @pytest.mark.parametrize("limit", [1, 100])
    def test_limit_bounds_are_accepted(self, client, limit):
        assert client.get("/books", params={"limit": limit}).status_code == 200

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
    def test_out_of_range_pagination_returns_422(self, client, params):
        assert client.get("/books", params=params).status_code == 422
