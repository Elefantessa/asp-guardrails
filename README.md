# Documentation Index

**Neuro-Symbolic Policy Compliance System**

Hala Alramli, University of Antwerp, 2026

---

## Documents

| File | Description |
|---|---|
| [architecture.md](./documentation/architecture.md) | System architecture, multi-agent graph, component design |
| [evaluation_findings.md](./documentation/evaluation_findings.md) | Baseline comparison results + failure analysis |
| [api_reference.md](./documentation/api_reference.md) | Module reference, state schema, public functions |
| [deployment.md](./documentation/deployment.md) | Setup, running the system, Docker, credentials |

---

## Quick Summary

Eliminates undetected LLM hallucinations in corporate policy queries
by combining RAG (retrieval) with ASP symbolic validation (Clingo).

```
User Query
    │
    ▼
Query Rewriter (Claude Haiku 4.5)
    │  normalises vocabulary, similarity fallback
    ▼
RAG Agent (Claude via Bedrock)
    │  CLAIM: / REFUSAL: / clarification
    ▼
Classifier (deterministic)
    │
    ├── clarification  →  pending_info
    ├── refusal        →  refused_out_of_scope
    └── final answer
            │
            ▼
    Fact Extractor (LLM → ASP atoms)
            │
            ▼
    ASP Validator (Clingo)
            │
            ├── valid    →  approved
            └── invalid  →  escalated (human review)
```

**Key result:** RAG+ASP detects 100% of injected hallucinations vs 0% for LLM-only and RAG-only baselines.

The system is also evaluated across two embedding backends (Bedrock Titan v2 vs HuggingFace
MiniLM): 100% (31/31) vs 96.8% (30/31) — see [evaluation_findings.md §7](evaluation_findings.md#7-embedding-backend-comparison-d4).
It ships as a 5-service Docker stack (API, 2× Streamlit UI, PostgreSQL, Grafana) — see
[deployment.md](deployment.md).

---

## Research Questions

| RQ | Question | Evidence |
|---|---|---|
| **RQ1** | Does ASP reduce hallucination rates? | 100% detection rate vs 0% baselines — see [evaluation_findings.md](evaluation_findings.md) |
| **RQ2** | What is the precision-recall of LLM fact extraction? | Fails on non-formalizable claims (ATOL) — see [evaluation_findings.md §3](evaluation_findings.md#3-rq2--fact-extraction-precision-recall) |
| **RQ3** | What fraction of policy clauses can be ASP-encoded? | Quantitative clauses (fees, dates) = fully encodable; qualitative = not — see [evaluation_findings.md §4](evaluation_findings.md#4-rq3--asp-formalizability) |
