from decimal import Decimal

import pytest

from app.catalog import Catalog, InsufficientStock, ProductNotFound, seeded_catalog


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    c.add("A", Decimal("10.00"), 5)
    c.add("B", Decimal("0.10"), 3)
    return c


def test_add_assigns_sequential_ids_and_normalises(catalog):
    p = catalog.add("  Pen  ", Decimal("1.5"), 0)
    assert p.id == 3
    assert p.name == "Pen"
    assert p.price == Decimal("1.50")


@pytest.mark.parametrize(
    "name,price,stock,msg",
    [
        ("   ", Decimal("1"), 1, "blank"),
        ("X", Decimal("0"), 1, "positive"),
        ("X", Decimal("-1"), 1, "positive"),
        ("X", Decimal("1"), -1, "negative"),
    ],
)
def test_add_rejects_invalid(catalog, name, price, stock, msg):
    with pytest.raises(ValueError, match=msg):
        catalog.add(name, price, stock)


def test_get_unknown_raises(catalog):
    with pytest.raises(ProductNotFound) as exc:
        catalog.get(99)
    assert exc.value.product_id == 99


def test_list_pagination(catalog):
    assert [p.id for p in catalog.list(limit=1, offset=1)] == [2]
    assert catalog.list(limit=10, offset=10) == []


@pytest.mark.parametrize("limit,offset", [(0, 0), (1, -1)])
def test_list_rejects_bad_paging(catalog, limit, offset):
    with pytest.raises(ValueError):
        catalog.list(limit=limit, offset=offset)


def test_checkout_decrements_stock_and_rounds_total(catalog):
    total = catalog.checkout({1: 2, 2: 3})
    assert total == Decimal("20.30")
    assert catalog.get(1).stock == 3
    assert catalog.get(2).stock == 0


def test_checkout_exact_stock_boundary(catalog):
    catalog.checkout({2: 3})
    with pytest.raises(InsufficientStock) as exc:
        catalog.checkout({2: 1})
    assert (exc.value.requested, exc.value.available) == (1, 0)


def test_checkout_is_atomic(catalog):
    with pytest.raises(InsufficientStock):
        catalog.checkout({1: 1, 2: 4})
    assert catalog.get(1).stock == 5  # first line was not applied


def test_checkout_unknown_product(catalog):
    with pytest.raises(ProductNotFound):
        catalog.checkout({1: 1, 42: 1})
    assert catalog.get(1).stock == 5


@pytest.mark.parametrize("items", [{}, {1: 0}, {1: -2}])
def test_checkout_rejects_invalid_cart(catalog, items):
    with pytest.raises(ValueError):
        catalog.checkout(items)


def test_seeded_catalog_has_products():
    assert len(seeded_catalog().list()) == 4
