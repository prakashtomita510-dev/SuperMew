from __future__ import annotations

import math
from statistics import mean
from typing import Iterable, Sequence


def recall_at_k(predicted: Sequence[str], relevant: set[str], k: int) -> int:
    return int(bool(relevant.intersection(predicted[:k])))


def mrr_at_k(predicted: Sequence[str], relevant: set[str], k: int) -> float:
    for index, doc_id in enumerate(predicted[:k], start=1):
        if doc_id in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(predicted: Sequence[str], relevant: set[str], k: int) -> float:
    dcg = 0.0
    for index, doc_id in enumerate(predicted[:k], start=1):
        if doc_id in relevant:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def exact_match(prediction: str, gold: str) -> int:
    return int(prediction.strip() == gold.strip())


def token_f1(prediction: str, gold: str) -> float:
    pred_tokens = prediction.strip().split()
    gold_tokens = gold.strip().split()
    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    pred_counts = {}
    gold_counts = {}
    for token in pred_tokens:
        pred_counts[token] = pred_counts.get(token, 0) + 1
    for token in gold_tokens:
        gold_counts[token] = gold_counts.get(token, 0) + 1

    overlap = 0
    for token, count in pred_counts.items():
        overlap += min(count, gold_counts.get(token, 0))

    if overlap == 0:
        return 0.0

    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def safe_mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return float(mean(items)) if items else None

