from __future__ import annotations
import os
from typing import List, Tuple
import google.generativeai as genai
from app.utils.schema import Chunk

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "gemini-1.5-flash")
TEMP = float(os.getenv("GEN_TEMPERATURE", "0.1"))
MAX_OUT = int(
    os.getenv("GEN_MAX_OUTPUT_TOKENS", "768")
)  # Cân bằng: 768 tokens đủ chi tiết nhưng tiết kiệm hơn 1024

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI chuyên nghiệp, trả lời câu hỏi dựa trên tài liệu với format rõ ràng và dễ đọc.\n\n"
    
    "📋 **CẤU TRÚC TRẢ LỜI BẮT BUỘC:**\n\n"
    
    "**[Câu mở đầu thân thiện]**\n\n"
    
    "**🔍 Thông tin chính:**\n"
    "• Điểm 1 [doc:page]\n"
    "• Điểm 2 [doc:page]\n"
    "• Điểm 3 [doc:page]\n\n"
    
    "**� Chi tiết cụ thể:**\n"
    "[Giải thích chi tiết với ví dụ]\n\n"
    
    "**⚠️ Lưu ý quan trọng:**\n"
    "• Điều cần chú ý 1\n"
    "• Điều cần chú ý 2\n\n"
    
    "**💡 Tóm tắt:**\n"
    "[Kết luận ngắn gọn]\n\n"
    
    "🚨 **QUY TẮC QUAN TRỌNG:**\n"
    "• LUÔN xuống dòng giữa các phần\n"
    "• Sử dụng ** ** để in đậm tiêu đề\n"
    "• Dùng bullet points (•) cho danh sách\n"
    "• LUÔN chèn [doc:page] sau thông tin quan trọng\n"
    "• Viết đầy đủ, không cắt giữa chừng\n"
    "• Nếu không có thông tin: 'Xin lỗi, không tìm thấy thông tin này trong tài liệu.'"
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
        text = p.text.replace("\n", " ").strip()
        # Cân bằng: giảm từ 1500 xuống 1200 để tiết kiệm token nhưng vẫn đủ thông tin
        if len(text) > 1200:
            text = text[:1200] + "…"
        parts.append(f"{header} {text}")
    return "\n\n".join(parts)  # Thêm khoảng cách giữa các đoạn


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
- Luôn có trích dẫn [doc:page]"""

    model = genai.GenerativeModel(
        LLM_MODEL,
        generation_config={
            "temperature": 0.1,  # Giảm để đảm bảo tuân thủ format
            "max_output_tokens": MAX_OUT,
            "candidate_count": 1,
        },
    )
    resp = model.generate_content(prompt)
    answer = (resp.text or "").strip() if hasattr(resp, "text") else str(resp)

    if passages:
        scores = [float(p.score or 0.0) for p in passages]
        conf = sum((s + 1) / 2 for s in scores) / len(scores)
    else:
        conf = 0.0
    return answer, float(conf)
