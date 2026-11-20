"""In-memory product catalog and checkout domain logic."""

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock


class CatalogError(Exception):
    """Base class for domain errors."""


class ProductNotFound(CatalogError):
    def __init__(self, product_id: int) -> None:
        super().__init__(f"product {product_id} not found")
        self.product_id = product_id


class InsufficientStock(CatalogError):
    def __init__(self, product_id: int, requested: int, available: int) -> None:
        super().__init__(f"product {product_id}: requested {requested}, only {available} in stock")
        self.product_id = product_id
        self.requested = requested
        self.available = available


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price: Decimal
    stock: int


CENT = Decimal("0.01")


class Catalog:
    """Thread-safe in-memory store. Checkout is all-or-nothing."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._products: dict[int, Product] = {}
        self._next_id = 1

    def add(self, name: str, price: Decimal, stock: int) -> Product:
        if not name.strip():
            raise ValueError("name must not be blank")
        if price <= 0:
            raise ValueError("price must be positive")
        if stock < 0:
            raise ValueError("stock must not be negative")
        with self._lock:
            product = Product(self._next_id, name.strip(), price.quantize(CENT), stock)
            self._products[product.id] = product
            self._next_id += 1
            return product

    def get(self, product_id: int) -> Product:
        with self._lock:
            try:
                return self._products[product_id]
            except KeyError:
                raise ProductNotFound(product_id) from None

    def list(self, limit: int = 50, offset: int = 0) -> list[Product]:
        if limit < 1 or offset < 0:
            raise ValueError("limit must be >= 1 and offset >= 0")
        with self._lock:
            ordered = sorted(self._products.values(), key=lambda p: p.id)
        return ordered[offset : offset + limit]

    def checkout(self, items: dict[int, int]) -> Decimal:
        """Reserve stock for every item and return the order total.

        Validates the whole cart before mutating anything, so a failure on
        one line leaves all stock untouched.
        """
        if not items:
            raise ValueError("cart must not be empty")
        if any(qty <= 0 for qty in items.values()):
            raise ValueError("quantities must be positive")
        with self._lock:
            for pid, qty in items.items():
                product = self._products.get(pid)
                if product is None:
                    raise ProductNotFound(pid)
                if product.stock < qty:
                    raise InsufficientStock(pid, qty, product.stock)
            total = Decimal("0")
            for pid, qty in items.items():
                product = self._products[pid]
                self._products[pid] = replace(product, stock=product.stock - qty)
                total += product.price * qty
        return total.quantize(CENT, rounding=ROUND_HALF_UP)


def seeded_catalog() -> Catalog:
    catalog = Catalog()
    catalog.add("Keyboard", Decimal("49.90"), 1_000_000)
    catalog.add("Mouse", Decimal("19.99"), 1_000_000)
    catalog.add("Monitor", Decimal("229.00"), 1_000_000)
    catalog.add("USB-C Cable", Decimal("9.50"), 1_000_000)
    return catalog
