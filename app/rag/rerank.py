# app/rag/rerank.py
from __future__ import annotations
from typing import List
import math
from app.utils.schema import Chunk


def _sigmoid(value: float) -> float:
    if value >= 50:
        return 1.0
    if value <= -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


_MODEL = None
_AVAILABLE = False


def _lazy_load():
    global _MODEL, _AVAILABLE
    if _MODEL is not None:
        return
    try:
        from sentence_transformers import CrossEncoder

        _MODEL = CrossEncoder("BAAI/bge-reranker-base")  # CPU ok
        _AVAILABLE = True
    except Exception:
        _MODEL = None
        _AVAILABLE = False


def rerank(passages: List[Chunk], query: str, top_k: int = 6) -> List[Chunk]:
    """Trả về danh sách đã rerank. Nếu không có model thì trả về đầu vào (cắt top_k)."""
    _lazy_load()
    if not _AVAILABLE or not passages:
        return passages[:top_k]
    pairs = [(query, p.text) for p in passages]

    scores = _MODEL.predict(pairs, convert_to_numpy=True).tolist()
    # sắp xếp giảm dần
    idx = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)[:top_k]
    out = []
    for i in idx:
        chunk = passages[i]
        score = float(scores[i])
        chunk.score = score
        if isinstance(chunk.meta, dict):
            meta = dict(chunk.meta)
            meta["relevance"] = _sigmoid(score)
            chunk.meta = meta
        out.append(chunk)
    return out
