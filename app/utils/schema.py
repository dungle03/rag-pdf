from pydantic import BaseModel
from typing import Optional, Dict


class Chunk(BaseModel):
    doc_name: str
    page: int
    chunk_id: int
    text: str
    n_tokens: int
    score: Optional[float] = None
    meta: Optional[Dict] = None

    # Extended metadata cho document versioning
    upload_timestamp: Optional[float] = None
    document_status: Optional[str] = None  # "active" | "superseded" | "archived"
    document_version: Optional[int] = None
    recency_score: Optional[float] = None
