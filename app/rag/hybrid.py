from __future__ import annotations
from typing import Iterable, List, Tuple
import regex as re
import numpy as np
from rank_bm25 import BM25Okapi
from app.utils.schema import Chunk

_WORD = re.compile(r"\p{L}+\p{M}*|\d+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    # tokenizer đơn giản cho TV: lấy chuỗi chữ (có dấu) & số → lower
    return [t.lower() for t in _WORD.findall(text or "")]


def _norm01(x: np.ndarray) -> np.ndarray:
    # chuẩn hoá về [0,1] an toàn
    if x.size == 0:
        return x
    mn, mx = float(x.min()), float(x.max())
    if mx - mn < 1e-12:
        return np.zeros_like(x)
    return (x - mn) / (mx - mn)


def hybrid_retrieve(
    query_vec: np.ndarray,
    query_text: str,
    store,
    docs: Iterable[str] | None,
    top_k: int = 10,
    alpha: float = 0.6,
    mmr_lambda: float = 0.5,
    recency_weight: float = 0.0,  # ← NEW: Weight cho recency boost
    recency_mode: str = "exponential",  # ← NEW: Decay mode
) -> List[Chunk]:
    """
    Kết hợp dense (cosine) + sparse (BM25) rồi MMR.
    - query_vec: (D,) đã L2-norm
    - store: FAISSStore hiện tại (có .items)
    - docs: danh sách tài liệu cho phép (None = tất cả)
    """
    allow = set(docs or [])
    # chọn candidates theo filter tài liệu
    cand_ids = [
        i
        for i, it in enumerate(store.items)
        if not allow or it.meta.get("doc") in allow
    ]
    if not cand_ids:
        return []

    # Check embedding dimension consistency
    if store.items and query_vec.shape[0] != store.items[0].vec.shape[0]:
        query_dim = query_vec.shape[0]
        store_dim = store.items[0].vec.shape[0]
        raise ValueError(
            f"Embedding dimension mismatch: query_dim={query_dim} != store_dim={store_dim}. "
            "This usually happens when the embedding model changed after documents were ingested. "
            "Please re-ingest the documents (or clear the vector store) so all embeddings share the same dimension."
        )

    # 1) Dense sims (cosine), đã L2 nên dot = cosine in [-1,1] → map về [0,1]
    dense_sims = np.array(
        [float(store.items[i].vec @ query_vec) for i in cand_ids], dtype=np.float32
    )
    dense01 = (dense_sims + 1.0) / 2.0

    # 2) BM25 sims
    corpus_tokens = [_tokenize(store.items[i].text) for i in cand_ids]
    bm25 = BM25Okapi(corpus_tokens)
    q_tokens = _tokenize(query_text)
    bm25_scores = np.array(bm25.get_scores(q_tokens), dtype=np.float32)
    bm2501 = _norm01(bm25_scores)

    # 3) Kết hợp dense + sparse thành điểm hybrid cơ bản
    combo = (1.0 - alpha) * dense01 + alpha * bm2501

    recency_scores: np.ndarray | None = None

    # 4) Áp dụng recency boost (nếu bật)
    if recency_weight > 0:
        # Import ở đây để tránh circular dependency
        from datetime import datetime

        current_time = datetime.now().timestamp()

        # Compute recency scores
        recency_scores = []
        for gid in cand_ids:
            item = store.items[gid]
            timestamp = item.meta.get("upload_timestamp", 0) if item.meta else 0

            if timestamp > 0:
                age_days = (current_time - timestamp) / 86400.0
                if recency_mode == "exponential":
                    half_life = 30.0
                    recency = np.exp(-age_days / half_life)
                elif recency_mode == "linear":
                    max_age = 90.0
                    recency = max(0.0, 1.0 - (age_days / max_age))
                elif recency_mode == "step":
                    if age_days <= 7:
                        recency = 1.0
                    elif age_days <= 30:
                        recency = 0.8
                    elif age_days <= 90:
                        recency = 0.5
                    else:
                        recency = 0.2
                else:
                    recency = 1.0
            else:
                recency = 0.5  # Default for unknown timestamp

            recency_scores.append(recency)

        recency_scores = np.array(recency_scores, dtype=np.float32)

        # Combine: (1 - recency_weight) * hybrid + recency_weight * recency
        combo = (1.0 - recency_weight) * combo + recency_weight * recency_scores

    # 5) Sort và lấy top candidates
    order = np.argsort(-combo)[: max(top_k * 3, top_k)]
    cand_top = [cand_ids[j] for j in order.tolist()]

    score_meta = {}
    for idx, gid in enumerate(cand_ids):
        meta_entry = {
            "dense_score_raw": float(dense_sims[idx]),
            "dense_score": float(dense01[idx]),
            "bm25_score_raw": float(bm25_scores[idx]),
            "bm25_score": float(bm2501[idx]),
            "hybrid_score": float(combo[idx]),
        }

        # Add recency info nếu có
        if (
            recency_weight > 0
            and recency_scores is not None
            and len(recency_scores) > idx
        ):
            meta_entry["recency_score"] = float(recency_scores[idx])

        score_meta[gid] = meta_entry

    # 6) MMR (trên vector dense) để đa dạng
    chosen: list[int] = []
    while len(chosen) < min(top_k, len(cand_top)):
        best_gid = None
        best_val = -1e9
        for gid in cand_top:
            if gid in chosen:
                continue
            sim_q = float(store.items[gid].vec @ query_vec)  # [-1,1]
            rep = 0.0
            for sel in chosen:
                rep = max(rep, float(store.items[gid].vec @ store.items[sel].vec))
            mmr = mmr_lambda * sim_q - (1 - mmr_lambda) * rep
            if mmr > best_val:
                best_val, best_gid = mmr, gid
        chosen.append(best_gid)

    # 7) Xuất dạng Chunk
    out: List[Chunk] = []
    for gid in chosen:
        it = store.items[gid]
        meta = dict(it.meta or {})
        meta.update(score_meta.get(gid, {}))

        # ✅ FIX: Extract enhanced metadata to top-level Chunk fields
        out.append(
            Chunk(
                doc_name=meta.get("doc", "unknown"),
                page=meta.get("page", 0),
                chunk_id=meta.get("chunk_id", 0),
                text=it.text,
                n_tokens=0,
                score=meta.get("hybrid_score", 0.0),
                meta=meta,
                # ✅ NEW: Pass enhanced metadata to top-level fields
                upload_timestamp=meta.get("upload_timestamp"),
                document_status=meta.get("document_status"),
                document_version=meta.get("document_version"),
                recency_score=meta.get("recency_score"),
            )
        )
    return out
