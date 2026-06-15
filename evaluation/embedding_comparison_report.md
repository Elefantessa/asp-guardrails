# Embedding Comparison Report

_Generated: 2026-06-12T17:18:22.913864+00:00_

## Summary

| Metric | Bedrock (Titan v2) | HuggingFace (MiniLM) |
|---|---|---|
| Accuracy | 31/31 (100.0%) | 30/31 (96.8%) |
| Avg latency | 3864 ms | 3661 ms |
| Avg min similarity score | 1.0448 | 0.9141 |

## Per-Case Results

| ID | Category | Expected | Bedrock | HF | Agree | BD ms | HF ms | BD score | HF score |
|---|---|---|---|---|---|---|---|---|---|
| TC001 | identity_validatio | approved | ✅ approved | ✅ approved | ✓ | 6823 | 11637 | 1.0171 | 1.0241 |
| TC002 | identity_validatio | approved | ✅ approved | ✅ approved | ✓ | 5805 | 4602 | 1.0171 | 1.051 |
| TC003 | identity_validatio | approved | ✅ approved | ✅ approved | ✓ | 4662 | 3996 | 1.0775 | 1.1137 |
| TC004 | cancellation_fees | approved | ✅ approved | ✅ approved | ✓ | 5220 | 4860 | 0.9137 | 0.7831 |
| TC005 | cancellation_fees | escalated | ✅ escalated | ✅ escalated | ✓ | 2 | 2 | — | — |
| TC006 | amendment_fees | approved | ✅ approved | ✅ approved | ✓ | 6358 | 7117 | 0.9304 | 0.8406 |
| TC007 | amendment_restrict | approved | ✅ approved | ✅ approved | ✓ | 5850 | 5632 | 0.9543 | 0.8 |
| TC008 | payment_requiremen | approved | ✅ approved | ✅ approved | ✓ | 4900 | 3895 | 0.8022 | 0.6701 |
| TC009 | complaint_time_lim | approved | ✅ approved | ✅ approved | ✓ | 7375 | 4608 | 1.0348 | 0.7345 |
| TC010 | missing_informatio | pending_info | ✅ pending_info | ✅ pending_info | ✓ | 2445 | 2438 | 0.9379 | 0.7306 |
| TC011 | cancellation_fees_ | approved | ✅ approved | ✅ approved | ✓ | 4 | 5 | — | — |
| TC012 | cancellation_fees_ | approved | ✅ approved | ✅ approved | ✓ | 2 | 3 | — | — |
| TC013 | cancellation_fees_ | approved | ✅ approved | ✅ approved | ✓ | 2 | 3 | — | — |
| TC014 | cancellation_fees_ | escalated | ✅ escalated | ✅ escalated | ✓ | 3 | 3 | — | — |
| TC015 | cancellation_fees_ | approved | ✅ approved | ✅ approved | ✓ | 3 | 3 | — | — |
| TC016 | cancellation_fees | approved | ✅ approved | ✅ approved | ✓ | 5142 | 4304 | 0.9138 | 0.6713 |
| TC017 | out_of_scope | refused_out_of_sco | ✅ refused_out_ | ✅ refused_out_ | ✓ | 2174 | 1832 | 1.8789 | 1.5156 |
| TC018 | out_of_scope | refused_out_of_sco | ✅ refused_out_ | ✅ refused_out_ | ✓ | 2815 | 2456 | 1.6874 | 1.5533 |
| TC019 | out_of_scope | refused_out_of_sco | ✅ refused_out_ | ✅ refused_out_ | ✓ | 2770 | 2150 | 1.6584 | 1.5284 |
| TC020 | out_of_scope | refused_out_of_sco | ✅ refused_out_ | ✅ refused_out_ | ✓ | 2755 | 2040 | 1.0113 | 1.1308 |
| TC021 | missing_informatio | pending_info | ✅ pending_info | ✅ pending_info | ✓ | 4301 | 2634 | 0.8288 | 0.7386 |
| TC022 | missing_informatio | approved | ✅ approved | ✅ approved | ✓ | 7844 | 5888 | 0.9088 | 0.8052 |
| TC023 | financial_protecti | approved | ✅ approved | ❌ refused_out_ | **✗** | 7222 | 5891 | 0.8247 | 0.5914 |
| TC024 | amendment_fees | escalated | ✅ escalated | ✅ escalated | ✓ | 3 | 2 | — | — |
| TC025 | identity_validatio | escalated | ✅ escalated | ✅ escalated | ✓ | 3 | 1 | — | — |
| TC026 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 4901 | 6211 | 0.8065 | 0.6162 |
| TC027 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 8200 | 8635 | 1.042 | 0.8704 |
| TC028 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 5255 | 4944 | 0.9631 | 0.9423 |
| TC029 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 5596 | 6758 | 1.3232 | 1.0795 |
| TC030 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 5398 | 5223 | 0.5888 | 0.524 |
| TC031 | query_rewriter_voc | approved | ✅ approved | ✅ approved | ✓ | 5961 | 5726 | 0.9088 | 0.7103 |

## Backend Disagreements

Cases where Bedrock and HuggingFace reached different decisions:

| ID | Query | Expected | Bedrock | HuggingFace |
|---|---|---|---|---|
| TC023 | Is my holiday financially protected if TUI goes bust?… | approved | approved | refused_out_of_scope |