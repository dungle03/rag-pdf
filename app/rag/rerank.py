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
    """Trả về danh sách đã rerank với logic suy luận nâng cao."""
    _lazy_load()
    if not _AVAILABLE or not passages:
        return passages[:top_k]

    pairs = [(query, p.text) for p in passages]

    scores = _MODEL.predict(pairs, convert_to_numpy=True).tolist()

    # Thêm logic suy luận: ưu tiên chunks có tính kết nối và logic
    enhanced_scores = []
    for i, score in enumerate(scores):
        chunk = passages[i]
        text = chunk.text.lower()

        # Bonus cho chunks có tính logic và kết nối
        logic_bonus = 0.0

        # Ưu tiên chunks có từ khóa suy luận
        reasoning_keywords = [
            "vì",
            "do",
            "nên",
            "kết quả",
            "nguyên nhân",
            "tại sao",
            "do đó",
            "vậy",
            "thế nên",
            "dẫn đến",
            "gây ra",
            "theo đó",
            "từ đó",
            "xuất phát từ",
            "dựa trên",
        ]
        if any(keyword in text for keyword in reasoning_keywords):
            logic_bonus += 0.1

        # Ưu tiên chunks có số liệu hoặc dữ kiện cụ thể
        if any(char.isdigit() for char in text):
            logic_bonus += 0.05

        # Ưu tiên chunks có cấu trúc logic (danh sách, bước)
        if any(marker in text for marker in ["1.", "2.", "3.", "-", "•", "bước"]):
            logic_bonus += 0.05

        enhanced_score = score + logic_bonus
        enhanced_scores.append(enhanced_score)

    # Sắp xếp theo điểm số nâng cao
    idx = sorted(range(len(passages)), key=lambda i: enhanced_scores[i], reverse=True)[
        :top_k
    ]
    out = []
    for i in idx:
        chunk = passages[i]
        score = float(enhanced_scores[i])
        chunk.score = score
        if isinstance(chunk.meta, dict):
            meta = dict(chunk.meta)
            meta["relevance"] = _sigmoid(score)
            meta["logic_bonus"] = enhanced_scores[i] - scores[i]  # Ghi lại bonus
            chunk.meta = meta
        out.append(chunk)
    return out
