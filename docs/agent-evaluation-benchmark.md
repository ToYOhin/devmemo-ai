# Agent Evaluation Synthetic Baseline

## Method

R6-I5 executes all 64 cases in `agent-evaluation-corpus-v1` through the actual
in-memory `RetrievalService` and `EvidenceAnswerAgent` core. Each case receives
a fresh deterministic embedding store populated only with generated synthetic
records whose IDs are already allowlisted by that case. The deterministic
Provider is used, so no network, real Memo, identity, credential, prompt dump,
Qdrant, Docker, or external model participates.

The harness emits only `agent-evaluation-result-v1` objects and evaluates them
with the predeclared `agent-evaluation-thresholds-v1`. Tests use a fixed-step
clock so the report is reproducible; its latency value is contract evidence,
not runtime performance evidence. Delegation/authentication and durable storage
are outside this core-only baseline and remain covered by their separate tests.

## Result

After R6-I5C, the baseline executes 64 cases with no failed case. The versioned
metrics are:

| Metric | Value | Gate |
| --- | ---: | --- |
| Retrieval Recall@5 | 1.0 | pass |
| Retrieval MRR | 1.0 | pass |
| Citation precision | 1.0 | pass |
| Groundedness | 1.0 | pass |
| Refusal accuracy | 1.0 | pass |
| Scope leak count | 0 | pass |
| Synthetic fixed-step p95 latency | 1 ms | pass |

The fixed pre-retrieval policy refuses all eight protected-intent cases without
calling retrieval or a Provider. The content-free report contains no failed
case or failed threshold. Regression tests preserve normal retrieval, citation,
visibility, no-context, and error behavior.

## Limitations

This is a sanitized offline product-core baseline, not evidence for real model
quality, Provider latency/cost, Qdrant ranking, lifecycle convergence, Docker,
authenticated browser behavior, restart recovery, CI on a clean checkout, or a
release. Those claims require their own authorization and evidence.
