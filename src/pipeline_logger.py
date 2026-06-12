"""
Pipeline console logger — prints every stage to terminal in real time.

Usage: imported automatically by each agent when LOG_PIPELINE=true in .env

Output format:
  [RAG]       Query: "..." | Retrieved 5 chunks
  [RAG]       Answer (227 chars): "Based on the policy..."
  [CLASSIFY]  → CLAIM (final answer)
  [EXTRACT]   Claims: 2 | Facts: 2
               - days_until_holiday("b1", 65).
               - llm_claims_cancellation_fee("c1", "b1", 30).
  [ASP]       ✅ PASS | 0 violations | 3 derived atoms
  [DECISION]  approved
  ─────────────────────────────────────────────────────────
"""

import os, logging, textwrap

# Controlled by LOG_PIPELINE env var (default: true)
_ENABLED = os.getenv("LOG_PIPELINE", "true").lower() != "false"

# ANSI colours
_C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[36m",
    "green":  "\033[32m",
    "yellow": "\033[33m",
    "red":    "\033[31m",
    "blue":   "\033[34m",
    "grey":   "\033[90m",
    "magenta":"\033[35m",
}

_LOG = logging.getLogger("cloudway.pipeline")
if not _LOG.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _LOG.addHandler(_h)
_LOG.setLevel(logging.DEBUG)
_LOG.propagate = False


def _col(text: str, *colours: str) -> str:
    return "".join(_C[c] for c in colours) + text + _C["reset"]


def _tag(name: str, colour: str = "cyan") -> str:
    return _col(f"[{name:<9}]", colour, "bold")


def _sep():
    if _ENABLED:
        _LOG.info(_col("─" * 60, "grey"))


def log_rag(query: str, n_chunks: int, answer: str):
    if not _ENABLED:
        return
    _sep()
    _LOG.info(f"{_tag('RAG')} {_col('Query:', 'bold')} {query!r}")
    _LOG.info(f"{_tag('RAG')} Retrieved {_col(str(n_chunks), 'green')} chunks")
    preview = answer[:200].replace("\n", " ")
    _LOG.info(f"{_tag('RAG')} Answer ({len(answer)} chars): {_col(preview + ('…' if len(answer) > 200 else ''), 'grey')}")


def log_classifier(is_clarification: bool, is_refusal: bool, error: bool):
    if not _ENABLED:
        return
    if error:
        label = _col("FORMAT ERROR → escalated", "red", "bold")
    elif is_clarification:
        label = _col("CLARIFICATION (pending_info)", "yellow")
    elif is_refusal:
        label = _col("REFUSAL (refused_out_of_scope)", "grey")
    else:
        label = _col("CLAIM → proceeding to ASP", "green")
    _LOG.info(f"{_tag('CLASSIFY', 'blue')} → {label}")


def log_extractor(claims: list[str], facts: list[str]):
    if not _ENABLED:
        return
    _LOG.info(
        f"{_tag('EXTRACT', 'magenta')} Claims: {_col(str(len(claims)), 'green')} | "
        f"Valid ASP facts: {_col(str(len(facts)), 'green')}"
    )
    for f in facts:
        _LOG.info(f"  {_col('├─', 'grey')} {_col(f, 'cyan')}")
    if not facts and claims:
        _LOG.info(f"  {_col('└─ No mappable facts (claims cannot be encoded as ASP)', 'yellow')}")


def log_asp(passed: bool, violations: list[str], derived: list[str]):
    if not _ENABLED:
        return
    if passed:
        _LOG.info(
            f"{_tag('ASP')} {_col('✅ PASS', 'green', 'bold')} | "
            f"0 violations | {len(derived)} derived atoms"
        )
    else:
        _LOG.info(
            f"{_tag('ASP')} {_col('❌ FAIL', 'red', 'bold')} | "
            f"{len(violations)} violation(s)"
        )
        for v in violations:
            _LOG.info(f"  {_col('├─', 'grey')} {_col(v, 'red')}")


def log_decision(decision: str, latency_ms: int = 0):
    if not _ENABLED:
        return
    colours = {
        "approved": "green",
        "escalated": "red",
        "pending_info": "yellow",
        "refused_out_of_scope": "grey",
        "error": "red",
    }
    col = colours.get(decision, "reset")
    lat = f"  {_col(f'({latency_ms} ms)', 'grey')}" if latency_ms else ""
    _LOG.info(f"{_tag('DECISION')} {_col(decision.upper(), col, 'bold')}{lat}")
    _sep()
