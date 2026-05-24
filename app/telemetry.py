"""OpenTelemetry setup: OTLP HTTP exporter -> Jaeger.

Initialized once at app startup. Provides a module-level tracer for agent spans.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

_initialized = False


def init_tracing(service_name: str = "portfolio-pulse") -> None:
    """Idempotent: configure global tracer provider once."""
    global _initialized
    if _initialized:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer(name: str = "portfolio-pulse") -> trace.Tracer:
    return trace.get_tracer(name)
