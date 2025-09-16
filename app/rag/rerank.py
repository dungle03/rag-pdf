# app/rag/rerank.py
from __future__ import annotations
from typing import List
from app.utils.schema import Chunk

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
    import numpy as np

    scores = _MODEL.predict(pairs, convert_to_numpy=True).tolist()
    # sắp xếp giảm dần
    idx = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)[:top_k]
    out = []
    for i in idx:
        p = passages[i].copy(update={"score": float(scores[i])})
        out.append(p)
    return out
