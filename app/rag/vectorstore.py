from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict
import numpy as np
import faiss
import os
import json

from app.utils.schema import Chunk


@dataclass
class VSItem:
    vec: np.ndarray  # (d,)
    meta: Dict
    text: str


class FAISSStore:
    def __init__(self, db_path: str, dim: int):
        self.db_path = db_path
        # dùng inner product (đã chuẩn hoá = cosine)
        self.index = faiss.IndexFlatIP(dim)
        self.items: List[VSItem] = []
        self.docs_set = set()

        if os.path.exists(db_path):
            print(f"Tải index từ {db_path}")
            self.index = faiss.read_index(db_path)
            # cố gắng tải metadata items nếu có
            self._try_load_items_from_disk()

    def _items_file_path(self) -> str:
        folder = os.path.dirname(self.db_path)
        return os.path.join(folder, "items.jsonl")

    def _try_load_items_from_disk(self):
        items_path = self._items_file_path()
        if not os.path.exists(items_path):
            return
        try:
            loaded = []
            with open(items_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    vec = None
                    try:
                        vec = self.index.reconstruct(i)
                    except Exception:
                        # nếu không reconstruct được (lệch số lượng), bỏ qua
                        break
                    loaded.append(
                        VSItem(
                            vec=np.array(vec, dtype=np.float32),
                            meta=rec.get("meta", {}),
                            text=rec.get("text", ""),
                        )
                    )
            if loaded:
                self.items = loaded
                self.docs_set = {
                    it.meta.get("doc") for it in self.items if it.meta.get("doc")
                }
                print(f"Tải metadata {len(self.items)} items từ {items_path}")
        except Exception as e:
            print(f"Lỗi tải items metadata: {e}")

    @property
    def dim(self) -> int:
        return self.index.d

    def size(self) -> int:
        return int(self.index.ntotal)

    def add(self, vectors: np.ndarray, chunks: List[Chunk]):
        assert vectors.shape[0] == len(chunks)
        # guard: rebuild index if empty and dim mismatches
        if vectors.shape[1] != self.index.d:
            if self.index.ntotal == 0:
                print(
                    f"Dim mismatch: rebuilding index {self.index.d} -> {vectors.shape[1]}"
                )
                self.index = faiss.IndexFlatIP(int(vectors.shape[1]))
            else:
                raise ValueError(
                    f"Embedding dim {vectors.shape[1]} != index dim {self.index.d}. Cannot add to non-empty index."
                )
        self.index.add(vectors)
        faiss.write_index(self.index, self.db_path)  # Lưu index sau khi thêm
        print(f"Đã lưu index vào {self.db_path}")

        for i, c in enumerate(chunks):
            self.items.append(
                VSItem(
                    vec=vectors[i],
                    meta={"doc": c.doc_name, "page": c.page, "chunk_id": c.chunk_id},
                    text=c.text,
                )
            )
            self.docs_set.add(c.doc_name)

        # persist items metadata to disk for future runs
        items_path = self._items_file_path()
        try:
            with open(items_path, "w", encoding="utf-8") as w:
                for it in self.items:
                    rec = {"meta": it.meta, "text": it.text}
                    w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"Đã lưu metadata items vào {items_path}")
        except Exception as e:
            print(f"Lỗi lưu items metadata: {e}")

    def _mmr(
        self, query_vec: np.ndarray, cand_ix: np.ndarray, k: int, lambda_: float = 0.5
    ) -> List[int]:
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

    def search(
        self, query_vec: np.ndarray, top_k: int = 8, mmr_lambda: float = 0.5
    ) -> List[Chunk]:
        if self.index.ntotal == 0:
            return []
        if query_vec.shape[0] != self.index.d:
            print(
                f"Bỏ qua search: query dim {query_vec.shape[0]} != index dim {self.index.d}"
            )
            return []
        # đảm bảo có items metadata; nếu thiếu, thử tải từ disk
        if not self.items or len(self.items) < int(self.index.ntotal):
            self._try_load_items_from_disk()
            if not self.items or len(self.items) < int(self.index.ntotal):
                # không đủ metadata → trả rỗng để tránh lỗi
                print("Thiếu metadata items so với index; bỏ qua kết quả để tránh lỗi.")
                return []
        D, I = self.index.search(
            query_vec.reshape(1, -1).astype("float32"), max(top_k * 3, top_k)
        )
        cand_ix = [int(i) for i in I[0] if i >= 0]
        if not cand_ix:
            return []

        picked = self._mmr(query_vec, cand_ix, k=top_k, lambda_=mmr_lambda)
        out: List[Chunk] = []
        for i in picked:
            it = self.items[i]
            cos = float(np.dot(it.vec, query_vec))
            score_norm = (cos + 1.0) / 2.0
            meta = dict(it.meta or {})
            meta.update(
                {
                    "dense_score_raw": cos,
                    "dense_score": score_norm,
                }
            )
            out.append(
                Chunk(
                    doc_name=meta["doc"],
                    page=meta["page"],
                    chunk_id=meta["chunk_id"],
                    text=it.text,
                    n_tokens=0,
                    score=score_norm,
                    meta=meta,
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
_stores: Dict[str, FAISSStore] = {}


def _uploads_dir() -> str:
    return os.getenv("UPLOAD_DIR", "./uploads")


def _store_paths(session_id: str) -> tuple[str, str, str]:
    base = _uploads_dir()
    folder = os.path.join(base, session_id)
    return (
        folder,
        os.path.join(folder, "faiss_index.bin"),
        os.path.join(folder, "items.jsonl"),
    )


def get_store(session_id: str, dim: int = 768) -> FAISSStore:
    """Lấy/tạo vector store cho session cụ thể."""
    if session_id in _stores:
        return _stores[session_id]

    # Nếu chưa có trong cache, tạo mới từ file hoặc tạo rỗng
    folder, index_path, _ = _store_paths(session_id)
    os.makedirs(folder, exist_ok=True)

    store = FAISSStore(db_path=index_path, dim=dim)
    _stores[session_id] = store
    return store


def drop_store(session_id: str) -> None:
    """Loại bỏ store đã được cache của session (nếu có)."""
    store = _stores.pop(session_id, None)
    if store:
        try:
            store.clear()
        except Exception:
            pass

    folder, index_path, items_path = _store_paths(session_id)
    for path in (index_path, items_path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    # nếu folder trống sau khi xoá index, giữ nguyên (PDFs vẫn dùng)
