"""
Telemetry & Observability — OTel Decorator Pattern (doc 06)

Exports traces and metrics via OTLP to the local Grafana LGTM stack:
    docker run -p 3000:3000 -p 4317:4317 -p 4318:4318 --rm -it grafana/otel-lgtm

Usage in node functions:
    from src.telemetry import node, set_span_attrs, TRACER

    @node("rag_agent")
    def rag_agent_node(state): ...

Usage for graph-level tracing (do NOT use @node here):
    with TRACER.start_as_current_span("graph.run") as span:
        result = graph.invoke(...)

Decorator hierarchy (outer → inner):
    @traced       — opens the OTel span
      @counted    — increments the execution counter
        @timed    — records node latency (histogram)
          @track_errors — catches and records exceptions
"""

import functools
import os
import time
from typing import Callable

from dotenv import load_dotenv
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

load_dotenv()

# ── Resource ──────────────────────────────────────────────────────────────────

_RESOURCE = Resource.create({
    "service.name": "cloudway",
    "service.version": "1.0.0",
    "deployment.environment": os.getenv("LOG_LEVEL", "development"),
})

# ── OTLP endpoint ─────────────────────────────────────────────────────────────
# Grafana LGTM container listens on port 4317 (gRPC OTLP).
_OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")

# ── Tracer setup ──────────────────────────────────────────────────────────────

_trace_provider = TracerProvider(resource=_RESOURCE)
_trace_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=_OTLP_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(_trace_provider)

TRACER = trace.get_tracer("cloudway.pipeline")

# ── Meter setup ───────────────────────────────────────────────────────────────

_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=_OTLP_ENDPOINT, insecure=True),
    export_interval_millis=10_000,
)
_meter_provider = MeterProvider(resource=_RESOURCE, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)

METER = metrics.get_meter("cloudway.pipeline")

# ── Instruments ───────────────────────────────────────────────────────────────

_node_counter = METER.create_counter(
    name="cloudway.node.executions",
    description="Total number of times each LangGraph node has executed",
    unit="1",
)

_node_latency = METER.create_histogram(
    name="cloudway.node.latency_ms",
    description="Latency of each LangGraph node in milliseconds",
    unit="ms",
)

_error_counter = METER.create_counter(
    name="cloudway.node.errors",
    description="Total number of exceptions raised inside LangGraph nodes",
    unit="1",
)


# ── Span attribute helper ─────────────────────────────────────────────────────

def set_span_attrs(attrs: dict) -> None:
    """
    Attach key-value pairs to the current active span.

    Call this inside any node to record domain-specific data without
    holding a reference to the span object.

    Examples:
        set_span_attrs({"classifier.has_claims": True, "classifier.is_refusal": False})
        set_span_attrs({"asp.violations": 2, "asp.validation_passed": False})
        set_span_attrs({"llm.tokens_estimate": 450})
    """
    span = trace.get_current_span()
    if span.is_recording():
        for key, value in attrs.items():
            span.set_attribute(key, value)


# ── Individual decorators ─────────────────────────────────────────────────────

def traced(node_name: str) -> Callable:
    """Outermost decorator — opens the OTel span."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with TRACER.start_as_current_span(f"node.{node_name}") as span:
                span.set_attribute("node.name", node_name)
                return fn(*args, **kwargs)
        return wrapper
    return decorator


def counted(node_name: str) -> Callable:
    """Increments the execution counter inside an active span."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _node_counter.add(1, {"node": node_name})
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def timed(node_name: str) -> Callable:
    """Records node wall-clock latency in milliseconds."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                _node_latency.record(elapsed_ms, {"node": node_name})
                set_span_attrs({"node.latency_ms": round(elapsed_ms, 2)})
        return wrapper
    return decorator


def track_errors(node_name: str) -> Callable:
    """
    Innermost decorator — catches exceptions, records them on the span
    and the error counter, then re-raises.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                _error_counter.add(1, {"node": node_name})
                span = trace.get_current_span()
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(
                        trace.StatusCode.ERROR,
                        description=str(exc),
                    )
                raise
        return wrapper
    return decorator


# ── Composite @node decorator ─────────────────────────────────────────────────

def node(node_name: str) -> Callable:
    """
    Composite decorator that applies the full telemetry stack to a LangGraph
    node function. Apply this to EVERY node function (rag_agent, classifier,
    fact_extractor, asp_validator, decision).

    Do NOT use this on the graph-level runner — use a manual
    `with TRACER.start_as_current_span("graph.run")` block there instead.

    Hierarchy (outer → inner):
        @traced → @counted → @timed → @track_errors

    Example:
        @node("rag_agent")
        def rag_agent_node(state: GuardrailsState) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        # Apply from innermost to outermost so the call stack is
        # track_errors → timed → counted → traced (outermost runs first).
        fn = track_errors(node_name)(fn)
        fn = timed(node_name)(fn)
        fn = counted(node_name)(fn)
        fn = traced(node_name)(fn)
        return fn
    return decorator
