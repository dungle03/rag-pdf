from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict
import numpy as np
import faiss

from app.utils.schema import Chunk

@dataclass
class VSItem:
    vec: np.ndarray  # (d,)
    meta: Dict
    text: str

class FAISSStore:
    def __init__(self, dim: int):
        # dùng inner product (đã chuẩn hoá = cosine)
        self.index = faiss.IndexFlatIP(dim)
        self.items: List[VSItem] = []
        self.docs_set = set()

    @property
    def dim(self) -> int:
        return self.index.d
    
    def size(self) -> int:
        return int(self.index.ntotal)

    def add(self, vectors: np.ndarray, chunks: List[Chunk]):
        assert vectors.shape[0] == len(chunks)
        self.index.add(vectors)
        for i, c in enumerate(chunks):
            self.items.append(
                VSItem(
                    vec=vectors[i],
                    meta={"doc": c.doc_name, "page": c.page, "chunk_id": c.chunk_id},
                    text=c.text,
                )
            )
            self.docs_set.add(c.doc_name)

    def _mmr(self, query_vec: np.ndarray, cand_ix: np.ndarray, k: int, lambda_: float = 0.5) -> List[int]:
        """Maximal Marginal Relevance để đa dạng hoá kết quả."""
        chosen: List[int] = []
        cand = list(cand_ix)
        cand_sims = [float(np.dot(self.items[i].vec, query_vec)) for i in cand]

        while cand and len(chosen) < k:
            # lợi ích = lambda * sim(q, i) - (1-lambda) * max_j sim(i, j) với j đã chọn
            best_i = None
            best_score = -1e9
            for idx, i in enumerate(cand):
                rep = 0.0
                if chosen:
                    rep = max(
                        float(np.dot(self.items[i].vec, self.items[j].vec))
                        for j in chosen
                    )
                score = lambda_ * cand_sims[idx] - (1 - lambda_) * rep
                if score > best_score:
                    best_score, best_i = score, i
            chosen.append(best_i)
            cand.remove(best_i)
        return chosen

    def search(self, query_vec: np.ndarray, top_k: int = 8, mmr_lambda: float = 0.5) -> List[Chunk]:
        if self.index.ntotal == 0:
            return []
        D, I = self.index.search(query_vec.reshape(1, -1).astype("float32"), max(top_k * 3, top_k))
        cand_ix = [int(i) for i in I[0] if i >= 0]
        if not cand_ix:
            return []

        picked = self._mmr(query_vec, cand_ix, k=top_k, lambda_=mmr_lambda)
        out: List[Chunk] = []
        for i in picked:
            it = self.items[i]
            out.append(
                Chunk(
                    doc_name=it.meta["doc"],
                    page=it.meta["page"],
                    chunk_id=it.meta["chunk_id"],
                    text=it.text,
                    n_tokens=0,
                    score=float(np.dot(it.vec, query_vec)),
                    meta=it.meta,
                )
            )
        return out

    def list_docs(self):
        return sorted(self.docs_set)

    def clear(self):
        self.index.reset()
        self.items.clear()
        self.docs_set = set()

# Singleton store (khởi tạo lazy sau khi biết dim)
_store: FAISSStore | None = None

def get_store(dim: int | None = None) -> FAISSStore:
    global _store
    if _store is None:
        if dim is None:
            raise RuntimeError("Vector store chưa khởi tạo. Hãy gọi get_store(dim) lần đầu.")
        _store = FAISSStore(dim=dim)
    return _store
