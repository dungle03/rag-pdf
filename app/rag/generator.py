from __future__ import annotations
import os
import math
from typing import List, Tuple
import google.generativeai as genai
from app.utils.schema import Chunk

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "gemini-1.5-flash")
TEMP = float(os.getenv("GEN_TEMPERATURE", "0.1"))
MAX_OUT = int(
    os.getenv("GEN_MAX_OUTPUT_TOKENS", "768")
)  # Cân bằng: 768 tokens đủ chi tiết nhưng tiết kiệm hơn 1024

SYSTEM_PROMPT = (
    "Bạn là trợ lý RAG, trả lời bằng tiếng Việt dựa 100% trên THÔNG TIN TỪ TÀI LIỆU."
    " Luôn so sánh câu hỏi với ngữ cảnh trước khi trả lời và chỉ sử dụng nội dung phù hợp.\n\n"
    "📋 **BỐ CỤC CÂU TRẢ LỜI**\n"
    "1. **🎯 Kết luận nhanh:** 1-3 câu trả lời trực tiếp câu hỏi, có [tên_file.pdf:số_trang].\n"
    "2. **📚 Bằng chứng chính:** Bullet tóm tắt dẫn chứng quan trọng (1-3 bullet), mỗi bullet kèm [tên_file.pdf:số_trang].\n"
    "3. **📝 Phân tích chi tiết:** Giải thích sâu hơn nếu cần, dùng đoạn văn ngắn, chỉ đưa thông tin liên quan.\n"
    "4. **⚠️ Lưu ý / Khuyến nghị:** Nêu lưu ý, hạn chế hoặc đề xuất hành động tiếp theo (nếu có).\n\n"
    "� **QUY TẮC BẮT BUỘC**\n"
    "• Tuyệt đối không bịa thông tin; nếu dữ liệu không đủ, trả lời: 'Xin lỗi, không tìm thấy thông tin phù hợp trong tài liệu hiện có.'\n"
    "• Không trích dẫn thông tin ngoài ngữ cảnh đã cung cấp.\n"
    "• QUAN TRỌNG: Khi trích dẫn, phải dùng CHÍNH XÁC tên file từ context, VD: [tb741.pdf:3] hoặc [guide.pdf:12]\n"
    "• Không lặp lại câu hỏi, không xin lỗi nhiều lần.\n"
    "• Luôn sử dụng định dạng markdown rõ ràng, mỗi phần cách nhau bằng dòng trống.\n"
    "• Giữ giọng văn chuyên nghiệp nhưng thân thiện, ưu tiên ngắn gọn và sát câu hỏi."
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
    if hasattr(resp, "text") and resp.text:
        answer = resp.text.strip()
    elif getattr(resp, "candidates", None):
        for candidate in resp.candidates:
            parts = getattr(getattr(candidate, "content", None), "parts", [])
            texts = [p.text for p in parts if getattr(p, "text", None)]
            if texts:
                answer = "\n".join(texts).strip()
                if answer:
                    break
    if not answer:
        raise RuntimeError("Không nhận được phản hồi từ mô hình.")

    if passages:
        scores = [_sigmoid(p.score) for p in passages]
        conf = sum(scores) / len(scores)
    else:
        conf = 0.0
    return answer, float(conf)
