import json
import logging

import pytest

from tests.conftest import make_client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_products(client):
    r = client.get("/products")
    assert r.status_code == 200
    assert len(r.json()) == 4
    assert client.get("/products", params={"limit": 2, "offset": 3}).json()[0]["id"] == 4


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_list_products_bad_paging(client, params):
    assert client.get("/products", params=params).status_code == 422


def test_get_product(client):
    r = client.get("/products/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Keyboard"


def test_get_product_not_found(client):
    r = client.get("/products/999")
    assert r.status_code == 404
    assert "999" in r.json()["detail"]


def test_create_product(client):
    r = client.post("/products", json={"name": "Desk", "price": "120.50", "stock": 2})
    assert r.status_code == 201
    assert r.json()["id"] == 5
    assert client.get("/products/5").json()["price"] == "120.50"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "price": "1", "stock": 1},
        {"name": "X", "price": "0", "stock": 1},
        {"name": "X", "price": "1.001", "stock": 1},
        {"name": "X", "price": "1", "stock": -1},
        {"name": "X", "stock": 1},
    ],
)
def test_create_product_validation(client, body):
    assert client.post("/products", json=body).status_code == 422


def test_create_product_blank_name_after_strip(client):
    r = client.post("/products", json={"name": "   ", "price": "1", "stock": 1})
    assert r.status_code == 422
    assert "blank" in r.json()["detail"]


def test_checkout_success_merges_duplicate_lines(client):
    r = client.post(
        "/checkout",
        json={
            "items": [
                {"product_id": 2, "quantity": 1},
                {"product_id": 2, "quantity": 2},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paid"
    assert body["total"] == "59.97"
    assert body["processing_ms"] == 120.0  # midpoint of 20..220 with rng 0.5


def test_checkout_unknown_product(client):
    r = client.post("/checkout", json={"items": [{"product_id": 77, "quantity": 1}]})
    assert r.status_code == 404


def test_checkout_insufficient_stock():
    from app.catalog import Catalog
    from decimal import Decimal
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    from tests.conftest import FixedRandom, _no_sleep

    cat = Catalog()
    cat.add("Rare", Decimal("5"), 1)
    c = TestClient(create_app(Settings(), catalog=cat, rng=FixedRandom(0.5), sleep=_no_sleep))
    r = c.post("/checkout", json={"items": [{"product_id": 1, "quantity": 2}]})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {"items": [{"product_id": 1, "quantity": 0}]},
        {"items": [{"product_id": 0, "quantity": 1}]},
        {"items": [{"product_id": 1, "quantity": 1001}]},
        {},
    ],
)
def test_checkout_validation(client, body):
    assert client.post("/checkout", json=body).status_code == 422


@pytest.mark.parametrize(
    "rng_value,rate,expected",
    [
        (0.01, 0.05, 500),  # below rate -> failure
        (0.05, 0.05, 200),  # exactly at rate -> success (strict <)
        (0.99, 1.0, 500),  # rate 1 -> always fails
        (0.0, 0.0, 200),  # rate 0 -> never fails
    ],
)
def test_flaky(rng_value, rate, expected):
    c = make_client(flaky_rate=rate, rng_value=rng_value)
    assert c.get("/flaky").status_code == expected


def test_metrics_exposes_latency_histogram_with_slo_bucket(client):
    client.get("/products")
    text = client.get("/metrics").text
    assert "http_server_request_duration_seconds_bucket" in text
    assert 'le="0.2"' in text
    assert 'http_route="/products"' in text


def test_metrics_counts_checkouts(client):
    client.post("/checkout", json={"items": [{"product_id": 1, "quantity": 1}]})
    assert "catalog_checkouts" in client.get("/metrics").text


def test_unmatched_route_404(client):
    assert client.get("/nope").status_code == 404


def test_request_logs_are_json_with_trace_id(client, caplog):
    from app.telemetry import JsonFormatter

    with caplog.at_level(logging.INFO, logger="catalog"):
        client.get("/products/1")
    records = [r for r in caplog.records if r.getMessage() == "request completed"]
    assert records
    # Format inside a live span to check trace correlation fields.
    from opentelemetry import trace

    with trace.get_tracer("t").start_as_current_span("s"):
        line = json.loads(JsonFormatter().format(records[-1]))
    assert line["http_route"] == "/products/{product_id}"
    assert line["http_status"] == 200
    assert len(line["trace_id"]) == 32
    assert len(line["span_id"]) == 16


def test_json_formatter_without_span_and_with_exception():
    from app.telemetry import JsonFormatter

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    line = json.loads(JsonFormatter().format(rec))
    assert "trace_id" not in line
    assert "RuntimeError: boom" in line["exception"]
    assert line["level"] == "error"


def test_unhandled_exception_returns_500():
    from app.catalog import Catalog
    from app.main import create_app
    from app.config import Settings
    from fastapi.testclient import TestClient

    class Broken(Catalog):
        def list(self, limit=50, offset=0):
            raise RuntimeError("db down")

    c = TestClient(create_app(Settings(), catalog=Broken()), raise_server_exceptions=False)
    assert c.get("/products").status_code == 500
