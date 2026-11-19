"""Vault Zeta Retrieval Evaluation & Benchmarking Suite.

Provides measurable, falsifiable verification of retrieval precision, recall,
mean reciprocal rank (MRR), and conflict/stale-memory leakage prevention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .store import VaultZetaStore


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    query: str
    expected_ids: Sequence[str]
    forbidden_ids: Sequence[str] = field(default_factory=tuple)
    scope: str | None = None
    kinds: Sequence[str] | None = None


@dataclass(frozen=True, slots=True)
class RetrievalEvalResult:
    case: RetrievalEvalCase
    hit_ids: list[str]
    reciprocal_rank: float
    precision_at_k: float
    recall_at_k: float
    forbidden_leakage_count: int


@dataclass(frozen=True, slots=True)
class RetrievalEvalSummary:
    total_cases: int
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    mean_recall_at_k: float
    total_forbidden_leakages: int
    success: bool


def evaluate_retrieval(
    store: VaultZetaStore,
    cases: Sequence[RetrievalEvalCase],
    *,
    k: int = 5,
    include_stale: bool = False,
    include_superseded: bool = False,
) -> RetrievalEvalSummary:
    """Run retrieval evaluation across test cases and compute precision, recall, and MRR."""
    if not cases:
        return RetrievalEvalSummary(0, 0.0, 0.0, 0.0, 0, True)

    results: list[RetrievalEvalResult] = []

    for case in cases:
        hits = store.search(
            case.query,
            scope=case.scope,
            kinds=case.kinds,
            include_stale=include_stale,
            include_superseded=include_superseded,
            limit=k,
        )
        hit_ids = [h.id for h in hits]

        # 1. Reciprocal Rank
        rr = 0.0
        for rank, hid in enumerate(hit_ids, start=1):
            if hid in case.expected_ids:
                rr = 1.0 / rank
                break

        # 2. Precision & Recall @ K
        expected_set = set(case.expected_ids)
        hits_in_expected = sum(1 for hid in hit_ids if hid in expected_set)
        prec = hits_in_expected / max(1, len(hit_ids))
        rec = hits_in_expected / max(1, len(expected_set))

        # 3. Forbidden (stale/superseded/conflicting) leakage
        forbidden_set = set(case.forbidden_ids)
        leakages = sum(1 for hid in hit_ids if hid in forbidden_set)

        results.append(
            RetrievalEvalResult(
                case=case,
                hit_ids=hit_ids,
                reciprocal_rank=rr,
                precision_at_k=prec,
                recall_at_k=rec,
                forbidden_leakage_count=leakages,
            )
        )

    mrr = sum(r.reciprocal_rank for r in results) / len(results)
    mean_prec = sum(r.precision_at_k for r in results) / len(results)
    mean_rec = sum(r.recall_at_k for r in results) / len(results)
    total_leakages = sum(r.forbidden_leakage_count for r in results)

    # Success criteria: MRR >= 0.8, no forbidden leakage
    success = (mrr >= 0.8) and (total_leakages == 0)

    return RetrievalEvalSummary(
        total_cases=len(cases),
        mean_reciprocal_rank=round(mrr, 4),
        mean_precision_at_k=round(mean_prec, 4),
        mean_recall_at_k=round(mean_rec, 4),
        total_forbidden_leakages=total_leakages,
        success=success,
    )
