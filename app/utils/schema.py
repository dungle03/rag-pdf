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
