# Cloudway — Documentation Index

**Neuro-Symbolic Policy Compliance System**

Hala Alramli, University of Antwerp, 2026

Company: cloudway

---

## Documents

| File | Description |
|---|---|
| [architecture.md](architecture.md) | System architecture, multi-agent graph, component design |
| [evaluation_findings.md](evaluation_findings.md) | Baseline comparison results + failure analysis |
| [api_reference.md](api_reference.md) | Module reference, state schema, public functions |
| [deployment.md](deployment.md) | Setup, running the system, Docker, credentials |

---

## Quick Summary

Cloudway eliminates undetected LLM hallucinations in corporate policy queries
by combining RAG (retrieval) with ASP symbolic validation (Clingo).

```
User Query
    │
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

---

## Research Questions

| RQ | Question | Evidence |
|---|---|---|
| **RQ1** | Does ASP reduce hallucination rates? | 100% detection rate vs 0% baselines — see [evaluation_findings.md](evaluation_findings.md) |
| **RQ2** | What is the precision-recall of LLM fact extraction? | Fails on non-formalizable claims (ATOL) — see [evaluation_findings.md#rq2](evaluation_findings.md#rq2-fact-extraction-precision-recall) |
| **RQ3** | What fraction of policy clauses can be ASP-encoded? | Quantitative clauses (fees, dates) = fully encodable; qualitative = not — see [evaluation_findings.md#rq3](evaluation_findings.md#rq3-asp-formalizability) |
