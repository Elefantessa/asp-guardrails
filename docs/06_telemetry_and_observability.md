# Telemetry & Observability (OpenTelemetry + LGTM)

## 1. Goal
Implement comprehensive observability across the LangGraph pipeline using OpenTelemetry (OTel). The telemetry data must be exported via OTLP to a local Grafana LGTM stack container (`grafana/otel-lgtm`).

## 2. Why OTel for Cloudway?
[cite_start]In a LangGraph app, the LLM decides what runs. OTel is critical because:
* [cite_start]It identifies exactly which node is causing a slowdown (e.g., ChromaDB retrieval, Claude generation, or Clingo validation).
* [cite_start]It tracks how often conditional edges execute and what the decisions are.
* [cite_start]Traces let you reconstruct exactly what happened in any past run, while metrics answer questions across thousands of runs.

## 3. Infrastructure & Dependencies
* **Backend:** The user will run the Grafana LGTM container locally using:
  `docker run -p 3000:3000 -p 4317:4317 -p 4318:4318 --rm -it grafana/otel-lgtm`
* **Python Packages:** Add the following to `requirements.txt`:
  `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation`.

## 4. Implementation Strategy: The Decorator Pattern
Do not bloat the node logic with telemetry boilerplate. [cite_start]Instead, create a dedicated `telemetry.py` utility module that defines a decorator hierarchy. 

Implement a composite `@node` decorator that wraps LangGraph node functions. [cite_start]The hierarchy must be exactly as follows:
* [cite_start]`@traced`: Outermost — opens the trace span first.
* [cite_start]`@counted`: Increments the execution counter inside the span.
* [cite_start]`@timed`: Records node latency.
* [cite_start]`@track_errors`: Innermost — catches exceptions and records them while the span is still open.

### Node Attributes to Track
[cite_start]Use a helper function (e.g., `set_span_attrs()`) to attach data to the span without holding a reference to it. Track the following:
* Intent classification results (CLAIM vs REFUSAL).
* Token usage estimates for the LLM.
* Clingo ASP validation results (Valid vs Contradiction).
* Output lengths.

## 5. Graph-Level Tracing
The overall graph execution (e.g., the `run_pipeline` function) should NOT use the `@node` decorator. Instead, use a manual `with TRACER.start_as_current_span("graph.run")` block because it acts as the container span that wraps the entire pipeline execution.