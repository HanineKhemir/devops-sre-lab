"""Runtime configuration, read from environment variables."""

import os
from dataclasses import dataclass


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    service_name: str = "catalog-api"
    service_version: str = "0.1.0"
    # Probability (0..1) that /flaky returns a 500.
    flaky_error_rate: float = 0.05
    # /checkout simulated processing time, uniform in [min, max] milliseconds.
    checkout_delay_min_ms: float = 20.0
    checkout_delay_max_ms: float = 220.0
    # OTLP gRPC endpoint (e.g. http://tempo:4317). Empty disables trace export.
    otlp_endpoint: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.flaky_error_rate <= 1.0:
            raise ValueError("FLAKY_ERROR_RATE must be within [0, 1]")
        if (
            self.checkout_delay_min_ms < 0
            or self.checkout_delay_max_ms < self.checkout_delay_min_ms
        ):
            raise ValueError("checkout delay bounds must satisfy 0 <= min <= max")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", cls.service_name),
            service_version=os.getenv("SERVICE_VERSION", cls.service_version),
            flaky_error_rate=_float("FLAKY_ERROR_RATE", cls.flaky_error_rate),
            checkout_delay_min_ms=_float("CHECKOUT_DELAY_MIN_MS", cls.checkout_delay_min_ms),
            checkout_delay_max_ms=_float("CHECKOUT_DELAY_MAX_MS", cls.checkout_delay_max_ms),
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        )
