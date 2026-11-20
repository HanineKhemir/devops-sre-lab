"""Product catalog REST API."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import NoOpMeterProvider
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from pydantic import BaseModel, Field

from app.catalog import Catalog, InsufficientStock, ProductNotFound, seeded_catalog
from app.config import Settings
from app.telemetry import REQUEST_DURATION, init_telemetry

logger = logging.getLogger("catalog")


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0)


class ProductOut(BaseModel):
    id: int
    name: str
    price: Decimal
    stock: int


class CartItem(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1000)


class CheckoutIn(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)


class CheckoutOut(BaseModel):
    status: str
    total: Decimal
    processing_ms: float


def create_app(
    settings: Settings | None = None,
    catalog: Catalog | None = None,
    rng: random.Random | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> FastAPI:
    settings = settings or Settings.from_env()
    catalog = catalog or seeded_catalog()
    rng = rng or random.Random()
    init_telemetry(settings)

    meter = metrics.get_meter("catalog-api")
    duration = meter.create_histogram(
        REQUEST_DURATION, unit="s", description="HTTP server request duration"
    )
    checkouts = meter.create_counter(
        "catalog.checkouts", unit="1", description="Completed checkouts"
    )
    tracer = trace.get_tracer("catalog-api")

    app = FastAPI(title="Catalog API", version=settings.service_version)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            if path != "/metrics":
                duration.record(
                    elapsed,
                    {
                        "http.route": path,
                        "http.request.method": request.method,
                        "http.response.status_code": status,
                    },
                )
            logger.info(
                "request completed",
                extra={
                    "fields": {
                        "http_method": request.method,
                        "http_route": path,
                        "http_status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                },
            )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.get("/products", response_model=list[ProductOut])
    async def list_products(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return [p.__dict__ for p in catalog.list(limit=limit, offset=offset)]

    @app.get("/products/{product_id}", response_model=ProductOut)
    async def get_product(product_id: int):
        try:
            return catalog.get(product_id).__dict__
        except ProductNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/products", response_model=ProductOut, status_code=201)
    async def create_product(body: ProductIn):
        try:
            product = catalog.add(body.name, body.price, body.stock)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.info("product created", extra={"fields": {"product_id": product.id}})
        return product.__dict__

    @app.post("/checkout", response_model=CheckoutOut)
    async def checkout(body: CheckoutIn):
        items: dict[int, int] = {}
        for item in body.items:
            items[item.product_id] = items.get(item.product_id, 0) + item.quantity
        delay_ms = rng.uniform(settings.checkout_delay_min_ms, settings.checkout_delay_max_ms)
        with tracer.start_as_current_span("payment.authorize") as span:
            span.set_attribute("payment.simulated_delay_ms", delay_ms)
            await sleep(delay_ms / 1000)
        try:
            total = catalog.checkout(items)
        except ProductNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InsufficientStock as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        checkouts.add(1)
        logger.info(
            "checkout completed",
            extra={"fields": {"order_total": str(total), "line_count": len(items)}},
        )
        return CheckoutOut(status="paid", total=total, processing_ms=round(delay_ms, 2))

    @app.get("/flaky")
    async def flaky():
        if rng.random() < settings.flaky_error_rate:
            logger.error("simulated downstream failure", extra={"fields": {"endpoint": "/flaky"}})
            raise HTTPException(status_code=500, detail="simulated intermittent failure")
        return {"status": "ok"}

    # Traces only: our own histogram above has low-cardinality labels and SLO buckets.
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="metrics,health", meter_provider=NoOpMeterProvider()
    )
    return app


app = create_app()
