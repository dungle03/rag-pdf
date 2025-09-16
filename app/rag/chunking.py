from __future__ import annotations
from typing import List, Tuple
from app.utils.schema import Chunk

# tiktoken có thể không có sẵn tokenizer "cl100k_base" trên 1 số máy rất cũ,
# nhưng đa số môi trường Python hiện đại đều OK.
import tiktoken
ENC = tiktoken.get_encoding("cl100k_base")

def _tokens(text: str) -> list[int]:
    return ENC.encode(text or "")

def _detokenize(ids: list[int]) -> str:
    return ENC.decode(ids)

def chunk_pages(
    pages: List[Tuple[int, str]],
    doc_name: str,
    chunk_size: int = 400,
    overlap: int = 50,
) -> List[Chunk]:
    """Nhận (page, text) -> trả về danh sách Chunk token-aware."""
    out: List[Chunk] = []
    cid = 0
    for page_no, text in pages:
        ids = _tokens(text)
        n = len(ids)
        if n == 0:
            continue
        start = 0
        while start < n:
            end = min(start + chunk_size, n)
            segment = _detokenize(ids[start:end])
            out.append(
                Chunk(
                    doc_name=doc_name,
                    page=page_no,
                    chunk_id=cid,
                    text=segment,
                    n_tokens=end - start,
                    meta={"doc": doc_name, "page": page_no, "start_token": start, "end_token": end},
                )
            )
            cid += 1
            if end == n:
                break
            start = max(0, end - overlap)
    return out
