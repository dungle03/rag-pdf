from __future__ import annotations
import os
import math
from typing import List, Tuple
import google.generativeai as genai
from app.utils.schema import Chunk
from app.utils.logger import rag_logger

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "gemini-1.5-flash")
TEMP = float(os.getenv("GEN_TEMPERATURE", "0.1"))
MAX_OUT = int(
    os.getenv("GEN_MAX_OUTPUT_TOKENS", "768")
)  # Cân bằng: 768 tokens đủ chi tiết nhưng tiết kiệm hơn 1024

SYSTEM_PROMPT = (
    "Bạn là trợ lý RAG, trả lời bằng tiếng Việt dựa 100% trên NỘI DUNG TÀI LIỆU. "
    "Luôn so sánh câu hỏi với ngữ cảnh và chỉ sử dụng thông tin liên quan.\n"
    "📋 BỐ CỤC TRẢ LỜI:\n"
    "1. 🎯 Kết luận: 1–3 câu trả lời trực tiếp, có [tên_file.pdf:trang].\n"
    "2. 📚 Dẫn chứng: 1–3 bullet dẫn chứng quan trọng, mỗi bullet kèm [tên_file.pdf:trang].\n"
    # "3. 📝 Phân tích: Giải thích ngắn gọn hơn nếu cần, chỉ thông tin sát câu hỏi.\n"
    "3. ⚠️ Lưu ý/Khuyến nghị: Nêu hạn chế hoặc gợi ý hành động tiếp theo (nếu có).\n"
    "📌 QUY TẮC:\n"
    "• Không bịa đặt; nếu thiếu dữ liệu, trả lời: 'Xin lỗi, không tìm thấy thông tin phù hợp trong tài liệu hiện có.'\n"
    "• Chỉ dùng thông tin từ tài liệu; không thêm kiến thức ngoài.\n"
    "• Khi trích dẫn, ghi đúng tên file và số trang, ví dụ [tb741.pdf:3].\n"
    "• Không lặp lại câu hỏi, không xin lỗi nhiều lần.\n"
    "• Trình bày bằng markdown rõ ràng, ngắn gọn, chuyên nghiệp và thân thiện."
)


def _sigmoid(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v >= 50:
        return 1.0
    if v <= -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-v))


def _ensure_init():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")
    genai.configure(api_key=api_key)


def _build_context(passages: List[Chunk]) -> str:
    parts = []
    for idx, p in enumerate(passages, start=1):
        relevance = 0.0
        if isinstance(getattr(p, "meta", None), dict):
            relevance = float(p.meta.get("relevance", 0.0) or 0.0)
        elif getattr(p, "score", None) is not None:
            relevance = _sigmoid(p.score)
        header = f"[{idx}] {p.doc_name}:{p.page} (độ phù hợp ≈ {relevance:.2f})"
        text = p.text.replace("\n", " ").strip()
        if len(text) > 1200:
            text = text[:1200] + "…"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def generate(query: str, passages: List[Chunk]) -> Tuple[str, float]:
    _ensure_init()
    context = _build_context(passages)

    # Prompt tối ưu cho format đẹp và câu trả lời đầy đủ
    prompt = f"""{SYSTEM_PROMPT}

=== THÔNG TIN TỪ TÀI LIỆU ===
{context}

=== CÂU HỎI ===
{query}

=== YÊU CẦU ===
Hãy trả lời THEO ĐÚNG CẤU TRÚC trên với:
- Xuống dòng rõ ràng giữa các phần
- Sử dụng **bold** cho tiêu đề 
- Bullet points cho danh sách
- Trả lời ĐẦY ĐỦ, không được cắt giữa chừng
- TRÍCH DẪN: Sử dụng tên file CHÍNH XÁC từ context ở trên, ví dụ [tb741.pdf:2] chứ KHÔNG PHẢI [doc:1]"""

    model = genai.GenerativeModel(
        LLM_MODEL,
        generation_config={
            "temperature": TEMP,
            "max_output_tokens": MAX_OUT,
            "candidate_count": 1,
        },
    )
    resp = model.generate_content(prompt)

    feedback = getattr(resp, "prompt_feedback", None)
    if feedback and getattr(feedback, "block_reason", None):
        raise RuntimeError(f"Yêu cầu bị từ chối: {feedback.block_reason}")

    answer = ""
    resp_text_error: str | None = None
    # resp.text accessor may raise ValueError if the response doesn't contain Part objects
    try:
        if hasattr(resp, "text") and resp.text:
            answer = resp.text.strip()
    except ValueError as e:
        # keep the error message for debugging / fallback behavior
        resp_text_error = str(e)

    # Fallback: try to extract from candidates (older or alternate response shape)
    if not answer and getattr(resp, "candidates", None):
        for candidate in resp.candidates:
            parts = getattr(getattr(candidate, "content", None), "parts", [])
            texts = [p.text for p in parts if getattr(p, "text", None)]
            if texts:
                answer = "\n".join(texts).strip()
                if answer:
                    break

    # If still empty, handle gracefully (do not raise unhandled exception)
    if not answer:
        feedback = getattr(resp, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None) if feedback else None
        # Log details for debugging (do not expose internals to end user)
        if resp_text_error:
            rag_logger.warning(
                "GenAI response parsing error: %s; prompt_block=%s",
                resp_text_error,
                bool(block_reason),
            )
        if block_reason:
            rag_logger.info("GenAI blocked request: %s", block_reason)
            answer = (
                "Xin lỗi, yêu cầu của bạn bị mô hình từ chối do chính sách nội dung. "
                "Vui lòng thử diễn đạt lại câu hỏi hoặc giảm bớt nội dung nhạy cảm."
            )
        else:
            answer = (
                "Xin lỗi, mô hình không trả về nội dung hợp lệ. Vui lòng thử lại sau hoặc "
                "chỉnh sửa câu hỏi."
            )

    if passages:
        scores = [_sigmoid(p.score) for p in passages]
        conf = sum(scores) / len(scores)
    else:
        conf = 0.0
    return answer, float(conf)
