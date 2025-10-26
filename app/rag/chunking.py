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
    upload_timestamp: float = None,
    document_status: str = "active",
    document_version: int = 1,
) -> List[Chunk]:
    """Nhận (page, text) -> trả về danh sách Chunk token-aware với semantic enhancement."""
    out: List[Chunk] = []
    cid = 0
    for page_no, text in pages:
        ids = _tokens(text)
        n = len(ids)
        if n == 0:
            continue

        # Semantic chunking: ưu tiên cắt tại các điểm logic
        chunks = _semantic_split(text, chunk_size, overlap)

        for chunk_text in chunks:
            chunk_ids = _tokens(chunk_text)
            if not chunk_ids:
                continue

            out.append(
                Chunk(
                    doc_name=doc_name,
                    page=page_no,
                    chunk_id=cid,
                    text=chunk_text,
                    n_tokens=len(chunk_ids),
                    upload_timestamp=upload_timestamp,
                    document_status=document_status,
                    document_version=document_version,
                    meta={
                        "doc": doc_name,
                        "filename": doc_name,  # ✅ FIX: Thêm filename để citation hiển thị đúng
                        "page": page_no,
                        "start_token": 0,  # Có thể cải tiến sau
                        "end_token": len(chunk_ids),
                        "semantic_chunk": True,
                        "upload_timestamp": upload_timestamp,
                        "document_status": document_status,
                        "document_version": document_version,
                    },
                )
            )
            cid += 1
    return out


def _semantic_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Chia text thành chunks với semantic awareness."""
    ids = _tokens(text)
    n = len(ids)

    if n <= chunk_size:
        return [_detokenize(ids)]

    chunks = []
    start = 0

    while start < n:
        # Tìm điểm kết thúc semantic
        end = min(start + chunk_size, n)

        # Ưu tiên cắt tại câu hoàn chỉnh
        if end < n:
            # Tìm dấu chấm, chấm hỏi, chấm than gần nhất
            search_end = min(end + 50, n)  # Tìm trong phạm vi rộng hơn
            text_segment = _detokenize(ids[start:search_end])

            # Tìm vị trí cắt semantic
            semantic_breaks = [". ", "! ", "? ", "\n\n", "\n"]
            best_break = end

            for break_marker in semantic_breaks:
                pos = text_segment.find(break_marker)
                if pos != -1:
                    token_pos = start + len(
                        _tokens(text_segment[: pos + len(break_marker)])
                    )
                    if token_pos > start + chunk_size * 0.7 and token_pos < search_end:
                        best_break = token_pos
                        break

            end = min(best_break, n)

        # Tạo chunk
        chunk_ids = ids[start:end]
        chunk_text = _detokenize(chunk_ids)
        chunks.append(chunk_text)

        # Tính overlap
        if end == n:
            break
        start = max(0, end - overlap)

    return chunks
