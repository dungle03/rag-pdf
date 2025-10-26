from __future__ import annotations
import os
import math
from typing import List, Tuple
import google.generativeai as genai
from app.utils.schema import Chunk
from app.utils.logger import rag_logger

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "gemini-2.0-flash-001")
TEMP = float(os.getenv("GEN_TEMPERATURE", "0.3"))
MAX_OUT = int(
    os.getenv("GEN_MAX_OUTPUT_TOKENS", "1024")
)  # Tăng để hỗ trợ suy luận chi tiết hơn

SYSTEM_PROMPT = (
    "Bạn là trợ lý RAG thông minh, trả lời bằng tiếng Việt dựa 100% trên NỘI DUNG TÀI LIỆU. "
    "Luôn suy luận LOGIC và THÔNG MINH dựa trên dẫn chứng từ tài liệu.\n"
    "📋 QUY TRÌNH SUY LUẬN:\n"
    "1. 🔍 Phân tích câu hỏi: Xác định ý chính, loại câu hỏi (thực tế, so sánh, quy trình, định nghĩa).\n"
    "2. 🕵️‍♂️ Tìm kiếm dẫn chứng: So khớp thông tin từ tài liệu với câu hỏi.\n"
    "3. 🧠 Suy luận logic: Kết nối thông tin, so sánh nếu cần, loại bỏ mâu thuẫn.\n"
    "4. 🎯 Kết luận: Trả lời trực tiếp, rõ ràng, CHI TIẾT và CỤ THỂ.\n"
    "📌 QUY TẮC:\n"
    "• Không bịa đặt; nếu thiếu dữ liệu, trả lời: 'Xin lỗi, không tìm thấy thông tin phù hợp trong tài liệu hiện có.'\n"
    "• Chỉ dùng thông tin từ tài liệu; không thêm kiến thức ngoài.\n"
    "• Khi trích dẫn, ghi đúng tên file và số trang, ví dụ [tb741.pdf:3].\n"
    "• Suy luận từng bước nếu câu hỏi phức tạp, nhưng giữ ngắn gọn.\n"
    "• Trình bày bằng markdown rõ ràng, chuyên nghiệp và thân thiện.\n"
    "• **LUÔN TRẢ LỜI CHI TIẾT VÀ CỤ THỂ**: Cung cấp đầy đủ thông tin, ví dụ thực tế, số liệu chính xác, bước thực hiện rõ ràng."
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

        # ✅ FIX: Ưu tiên "filename" từ metadata, fallback về doc_name
        filename = p.doc_name  # Default
        if isinstance(getattr(p, "meta", None), dict):
            filename = p.meta.get("filename", p.meta.get("doc", p.doc_name))

        header = f"[{idx}] {filename}:{p.page} (độ phù hợp ≈ {relevance:.2f})"
        text = p.text.replace("\n", " ").strip()
        if len(text) > 1200:
            text = text[:1200] + "…"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def _detect_question_type(query: str) -> str:
    """Detect the type of question for adaptive reasoning."""
    query_lower = query.lower()

    # Comparison questions
    if any(
        word in query_lower
        for word in ["so sánh", "khác nhau", "khác biệt", "so với", "thế nào"]
    ):
        return "comparison"

    # Causal questions
    if any(
        word in query_lower
        for word in ["tại sao", "vì sao", "nguyên nhân", "do", "bởi"]
    ):
        return "causal"

    # Procedural questions
    if any(
        word in query_lower
        for word in ["cách", "bước", "quy trình", "làm thế nào", "thực hiện"]
    ):
        return "procedural"

    # Definitional questions
    if any(
        word in query_lower
        for word in ["là gì", "định nghĩa", "giải thích", "có nghĩa là"]
    ):
        return "definitional"

    # Quantitative questions
    if any(
        word in query_lower for word in ["bao nhiêu", "mấy", "số lượng", "phần trăm"]
    ):
        return "quantitative"

    return "general"


def _get_reasoning_guide(question_type: str) -> str:
    """Get adaptive reasoning guide based on question type."""
    guides = {
        "comparison": """Hãy suy luận để so sánh CHI TIẾT:
1. **Xác định đối tượng**: Liệt kê các thực thể cần so sánh với mô tả đầy đủ.
2. **Tìm điểm tương đồng**: Tìm và giải thích các đặc điểm chung một cách cụ thể.
3. **Tìm điểm khác biệt**: Xác định và phân tích sự khác nhau về đặc điểm, ưu/nhược điểm chi tiết.
4. **Kết luận**: Tổng hợp so sánh một cách logic với ví dụ cụ thể.""",
        "causal": """Hãy suy luận về nguyên nhân CHI TIẾT:
1. **Xác định hiện tượng**: Mô tả vấn đề hoặc kết quả với đầy đủ chi tiết.
2. **Tìm nguyên nhân trực tiếp**: Tìm và giải thích các yếu tố gây ra trực tiếp với ví dụ.
3. **Tìm nguyên nhân gián tiếp**: Xem xét và phân tích các yếu tố nền tảng chi tiết.
4. **Kết luận**: Giải thích mối quan hệ nhân quả với bằng chứng cụ thể.""",
        "procedural": """Hãy suy luận về quy trình CHI TIẾT:
1. **Xác định mục tiêu**: Mô tả kết quả mong muốn với đầy đủ chi tiết.
2. **Liệt kê bước thực hiện**: Tìm và mô tả các bước theo thứ tự logic với hướng dẫn cụ thể.
3. **Xác định điều kiện**: Lưu ý chi tiết các yêu cầu hoặc điều kiện tiên quyết.
4. **Kết luận**: Tóm tắt quy trình một cách có hệ thống với ví dụ thực tế.""",
        "definitional": """Hãy suy luận về định nghĩa CHI TIẾT:
1. **Xác định khái niệm**: Mô tả đối tượng cần định nghĩa với ngữ cảnh đầy đủ.
2. **Tìm đặc điểm chính**: Liệt kê và giải thích các thuộc tính quan trọng chi tiết.
3. **Tìm ví dụ**: Tìm và mô tả minh họa thực tế cụ thể.
4. **Kết luận**: Đưa ra định nghĩa rõ ràng, đầy đủ với các khía cạnh khác nhau.""",
        "quantitative": """Hãy suy luận về số lượng CHI TIẾT:
1. **Xác định chỉ số**: Mô tả dữ liệu cần tìm với ngữ cảnh đầy đủ.
2. **Tìm số liệu cụ thể**: Trích xuất và phân tích các con số từ tài liệu chi tiết.
3. **Xác minh tính chính xác**: Kiểm tra nguồn và ngữ cảnh với giải thích cụ thể.
4. **Kết luận**: Trình bày số liệu với đơn vị, ngữ cảnh và phân tích chi tiết.""",
        "general": """Hãy suy luận từng bước để trả lời CHI TIẾT và THÔNG MINH:
1. **Phân tích câu hỏi**: Xác định loại câu hỏi và thông tin cần thiết với phân tích sâu.
2. **Tìm kiếm dẫn chứng**: Trích xuất và phân tích thông tin liên quan từ tài liệu chi tiết.
3. **Suy luận logic**: Kết nối thông tin, so sánh nếu có nhiều nguồn, loại bỏ thông tin không liên quan với giải thích.
4. **Kết luận**: Trả lời trực tiếp, rõ ràng với đầy đủ chi tiết và bằng chứng.""",
    }

    return guides.get(question_type, guides["general"])


def generate(query: str, passages: List[Chunk]) -> Tuple[str, float]:
    _ensure_init()
    context = _build_context(passages)

    # Adjust max output for summary queries
    is_summary = any(
        word in query.lower()
        for word in ["tóm tắt", "tổng kết", "summary", "summarize", "tóm tắt nội dung"]
    )
    max_out = MAX_OUT * 2 if is_summary else MAX_OUT  # Double for summaries

    question_type = _detect_question_type(query)
    reasoning_guide = _get_reasoning_guide(question_type)

    # Enhanced prompt: yêu cầu không lặp lại citation giống nhau liên tục
    citation_note = (
        "\n\n**Lưu ý về trích dẫn:**\n"
        "- Chỉ chèn trích dẫn [tên_file.pdf:trang] ở cuối đoạn hoặc bullet lớn nhất, không lặp lại cùng một trích dẫn nhiều lần liên tiếp trong cùng một đoạn hoặc danh sách.\n"
        "- Nếu nhiều ý trong cùng đoạn/bullet cùng nguồn, chỉ cần citation ở cuối đoạn/bullet đó.\n"
        "- Không chèn citation sau từng câu nhỏ nếu cùng nguồn.\n"
    )
    if is_summary:
        prompt = f"""{SYSTEM_PROMPT}

=== THÔNG TIN TỪ TÀI LIỆU ===
{context}

=== CÂU HỎI ===
{query}

=== HƯỚNG DẪN SUY LUẬN ===
Hãy suy luận thông minh để tóm tắt:
1. **Phân tích tổng thể**: Xác định chủ đề chính và mối liên hệ giữa các tài liệu.
2. **Trích xuất thông tin**: Lấy điểm chính, số liệu, quy trình từ mỗi nguồn.
3. **So sánh và tổng hợp**: Đối chiếu thông tin, loại bỏ trùng lặp, tạo bản đồ logic.
4. **Kết luận**: Tóm tắt cô đọng nhưng đầy đủ.

=== YÊU CẦU TRÌNH BÀY ===
- **Tóm tắt tổng quát**: Nội dung chính của từng file với CHI TIẾT đầy đủ.
- **Điểm quan trọng**: Liệt kê các điểm chính, số liệu, quy trình CỤ THỂ và chi tiết.
- **So sánh nếu có**: Đối chiếu nội dung liên quan giữa các file một cách CHI TIẾT.
- **Kết luận**: Tóm tắt chung với logic rõ ràng và đầy đủ thông tin.
Sử dụng markdown, trích dẫn chính xác [tên_file.pdf:trang], đảm bảo logic và đầy đủ.
{citation_note}"""
    else:
        prompt = f"""{SYSTEM_PROMPT}

=== THÔNG TIN TỪ TÀI LIỆU ===
{context}

=== CÂU HỎI ===
{query}

=== HƯỚNG DẪN SUY LUẬN ===
{reasoning_guide}

=== YÊU CẦU TRÌNH BÀY ===
- **Kết luận**: Câu trả lời trực tiếp, CHI TIẾT và CỤ THỂ (2-5 câu).
- **Dẫn chứng**: 2-4 điểm chính từ tài liệu với giải thích đầy đủ, kèm [tên_file.pdf:trang].
- **Phân tích** (nếu cần): Giải thích logic chi tiết, so sánh nếu có nhiều thông tin.
- **Khuyến nghị** (nếu phù hợp): Hành động tiếp theo hoặc lưu ý CỤ THỂ.
Sử dụng markdown, trích dẫn chính xác, đảm bảo logic và đầy đủ.
{citation_note}"""

    model = genai.GenerativeModel(
        LLM_MODEL,
        generation_config={
            "temperature": TEMP,
            "max_output_tokens": max_out,
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

    conf = 0.0
    if passages:
        chunk_scores: list[float] = []
        for p in passages:
            meta = getattr(p, "meta", {}) or {}
            candidates: list[float] = []
            for key in ("relevance", "hybrid_score", "dense_score", "bm25_score"):
                val = meta.get(key)
                if val is None:
                    continue
                try:
                    candidates.append(float(val))
                except (TypeError, ValueError):
                    continue
            if not candidates and getattr(p, "score", None) is not None:
                candidates.append(_sigmoid(p.score))
            if not candidates:
                continue
            best = max(candidates)
            chunk_scores.append(max(0.0, min(1.0, best)))

        if chunk_scores:
            chunk_scores.sort(reverse=True)
            primary = chunk_scores[0]
            support_vals = chunk_scores[1:3]
            support = sum(support_vals) / len(support_vals) if support_vals else primary
            high_quality = len([s for s in chunk_scores if s >= 0.6])
            coverage_ratio = min(1.0, high_quality / max(1, len(chunk_scores)))
            consistency = 1.0 - min(1.0, abs(primary - support))

            blended = (
                0.6 * primary
                + 0.25 * support
                + 0.1 * coverage_ratio
                + 0.05 * consistency
            )

            if primary >= 0.85:
                blended = max(blended, 0.92)
            elif primary >= 0.75:
                blended = max(blended, 0.84)
            elif primary >= 0.65:
                blended = max(blended, 0.76)

            conf = min(0.99, max(primary * 0.9, blended))

    return answer, float(conf)
