import pytest

from app.config import Settings


def test_defaults_from_empty_env(monkeypatch):
    for var in (
        "FLAKY_ERROR_RATE",
        "CHECKOUT_DELAY_MIN_MS",
        "CHECKOUT_DELAY_MAX_MS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_NAME",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.flaky_error_rate == 0.05
    assert s.service_name == "catalog-api"
    assert s.otlp_endpoint == ""


def test_reads_env(monkeypatch):
    monkeypatch.setenv("FLAKY_ERROR_RATE", "0.5")
    monkeypatch.setenv("CHECKOUT_DELAY_MIN_MS", "")
    monkeypatch.setenv("CHECKOUT_DELAY_MAX_MS", "900")
    s = Settings.from_env()
    assert s.flaky_error_rate == 0.5
    assert s.checkout_delay_min_ms == 20.0
    assert s.checkout_delay_max_ms == 900.0


def test_non_numeric_env_rejected(monkeypatch):
    monkeypatch.setenv("FLAKY_ERROR_RATE", "lots")
    with pytest.raises(ValueError, match="FLAKY_ERROR_RATE"):
        Settings.from_env()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"flaky_error_rate": -0.1},
        {"flaky_error_rate": 1.1},
        {"checkout_delay_min_ms": -1},
        {"checkout_delay_min_ms": 300, "checkout_delay_max_ms": 100},
    ],
)
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


@pytest.mark.parametrize("rate", [0.0, 1.0])
def test_rate_boundaries_accepted(rate):
    assert Settings(flaky_error_rate=rate).flaky_error_rate == rate
