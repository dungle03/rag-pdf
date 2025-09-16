from __future__ import annotations
import os
from typing import List, Tuple
import google.generativeai as genai
from app.utils.schema import Chunk

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "gemini-1.5-flash")
TEMP = float(os.getenv("GEN_TEMPERATURE", "0.1"))
MAX_OUT = int(os.getenv("GEN_MAX_OUTPUT_TOKENS", "256"))

SYSTEM_PROMPT = (
"Bạn là trợ lý trích dẫn đáng tin cậy. "
"Chỉ trả lời dựa trên nội dung trích từ các tài liệu đã cung cấp. "
"Bắt buộc chèn trích dẫn theo dạng [doc:page] sau mỗi đoạn liên quan. "
"Nếu không tìm thấy thông tin, trả lời rõ: 'Không thấy thông tin trong tài liệu đã cung cấp.' "
"Trả lời ngắn gọn, chính xác, bằng tiếng Việt."
)

def _ensure_init():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")
    genai.configure(api_key=api_key)

def _build_context(passages: List[Chunk]) -> str:
    parts = []
    for p in passages:
        header = f"[{p.doc_name}:{p.page}]"
        text = p.text.replace("\n", " ")
        # hạn chế độ dài mỗi đoạn để giảm token:
        if len(text) > 1000: text = text[:1000] + "…"
        parts.append(f"{header} {text}")
    return "\n".join(parts)

def generate(query: str, passages: List[Chunk]) -> Tuple[str, float]:
    _ensure_init()
    context = _build_context(passages)
    prompt = f"{SYSTEM_PROMPT}\n\nNgữ cảnh:\n{context}\n\nCâu hỏi: {query}"
    model = genai.GenerativeModel(LLM_MODEL,
        generation_config={"temperature": TEMP, "max_output_tokens": MAX_OUT, "candidate_count": 1}
    )
    resp = model.generate_content(prompt)
    answer = (resp.text or "").strip() if hasattr(resp, "text") else str(resp)
    if passages:
        scores = [float(p.score or 0.0) for p in passages]
        conf = sum((s + 1) / 2 for s in scores) / len(scores)
    else:
        conf = 0.0
    return answer, float(conf)
