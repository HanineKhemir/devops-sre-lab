"""OpenTelemetry setup: traces (OTLP -> Tempo), metrics (Prometheus), JSON logs.

Every log record carries the active trace_id/span_id so Grafana can jump
from a Loki log line to the matching Tempo trace and back.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from opentelemetry import metrics, trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import Settings

# Explicit buckets: the latency SLO threshold (0.2 s) must be a bucket
# boundary, otherwise "% of requests under 200 ms" cannot be computed exactly.
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0)
REQUEST_DURATION = "http.server.request.duration"

_initialised = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        span_ctx = trace.get_current_span().get_span_context()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if span_ctx.is_valid:
            payload["trace_id"] = format(span_ctx.trace_id, "032x")
            payload["span_id"] = format(span_ctx.span_id, "016x")
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn's own access log duplicates ours and lacks trace ids.
    logging.getLogger("uvicorn.access").disabled = True


def init_telemetry(settings: Settings) -> None:
    """Install global tracer and meter providers once per process."""
    global _initialised
    if _initialised:
        return
    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": settings.service_version}
    )

    tracer_provider = TracerProvider(resource=resource)
    if settings.otlp_endpoint:  # pragma: no cover - needs a live collector
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True))
        )
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PrometheusMetricReader()],
        views=[
            View(
                instrument_name=REQUEST_DURATION,
                aggregation=ExplicitBucketHistogramAggregation(LATENCY_BUCKETS),
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)
    configure_logging()
    _initialised = True
