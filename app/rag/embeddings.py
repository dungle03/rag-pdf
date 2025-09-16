from __future__ import annotations
import os, time
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import google.generativeai as genai

from app.utils.hash import sha1_text
from app.rag.cache import fetch_many, upsert_many

EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "text-embedding-004")

def _ensure_init():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    genai.configure(api_key=api_key)

def _l2_normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return (x / n).astype("float32")

def _embed_single(text: str) -> np.ndarray:
    r = genai.embed_content(model=EMBED_MODEL, content=text, task_type="retrieval_document")
    v = None
    if isinstance(r, dict):
        v = r.get("embedding") or r.get("values")
    if v is None and hasattr(r, "embedding"):
        v = r.embedding
    if v is None:
        raise RuntimeError(f"Unexpected embedding response: {type(r)} -> {r}")
    return np.array(v, dtype=np.float32)

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Trả về (N, D) embeddings (L2-normalized).
    Sử dụng cache SQLite theo SHA1(text) + gọi Gemini song song cho các miss.
    """
    _ensure_init()

    if not texts:
        return np.zeros((0, 768), dtype=np.float32)

    # 1) Tính key SHA1
    keys = [sha1_text(t) for t in texts]

    # 2) Hit cache
    db_path = os.getenv("EMBED_CACHE_DB", "./storage/embed_cache.sqlite")
    cached: Dict[str, np.ndarray] = fetch_many(db_path, keys)

    # 3) Chuẩn bị indices cho miss
    miss_indices = [i for i, k in enumerate(keys) if k not in cached]
    hits = len(keys) - len(miss_indices)

    # 4) Gọi song song cho miss
    conc = max(1, int(os.getenv("EMBED_CONCURRENCY", "4")))
    sleep_ms = max(0, int(os.getenv("EMBED_SLEEP_MS", "0")))
    results: Dict[int, np.ndarray] = {}

    if miss_indices:
        with ThreadPoolExecutor(max_workers=conc) as ex:
            fut2idx = {
                ex.submit(_embed_single, texts[i]): i
                for i in miss_indices
            }
            for fut in as_completed(fut2idx):
                i = fut2idx[fut]
                vec = fut.result()
                results[i] = vec
                if sleep_ms:
                    time.sleep(sleep_ms / 1000.0)

        # 5) Ghi cache cho miss
        upsert_many(
            db_path,
            [(keys[i], results[i]) for i in miss_indices]
        )

    # 6) Lắp mảng theo thứ tự gốc
    dim = (next(iter(cached.values())).shape[0]
           if cached else (next(iter(results.values())).shape[0] if results else 768))
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, k in enumerate(keys):
        if k in cached:
            out[i] = cached[k]
        else:
            out[i] = results[i]

    return _l2_normalize(out)

def embed_query(q: str) -> np.ndarray:
    return embed_texts([q])
