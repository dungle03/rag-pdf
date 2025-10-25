# 📚 RAG PDF QA System

> **Hệ thống hỏi đáp tài liệu PDF thông minh** sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)** với **FastAPI + Google Gemini AI + FAISS**.

Ứng dụng web hiện đại cho phép tải lên tài liệu PDF và đặt câu hỏi bằng tiếng Việt, nhận câu trả lời chính xác kèm trích dẫn nguồn chi tiết.

---

## ✨ Tính năng chính

- **Giao diện trực quan**: Upload, quản lý và hỏi đáp tài liệu trên một giao diện web duy nhất.
- **Tìm kiếm lai (Hybrid Search)**: Kết hợp `Vector Search` và `BM25` để tăng độ chính xác.
- **Tối ưu với Reranking**: Dùng Cross-Encoder để xếp hạng lại các kết quả, chọn ra ngữ cảnh phù hợp nhất.
- **Sinh câu trả lời thông minh**: Sử dụng **Gemini 2.0 Flash** với trích dẫn nguồn `[doc:page]` rõ ràng.
- **Hỗ trợ OCR**: Tự động nhận dạng văn bản từ file PDF dạng ảnh/scan.
- **Ưu tiên thông tin mới (Recency Boost)**: Tự động ưu tiên các tài liệu mới được tải lên.
- **Quản lý đa phiên**: Mỗi cuộc trò chuyện có không gian làm việc, lịch sử và tài liệu riêng biệt.
- **Hiệu năng cao**: Tích hợp Cache cho embeddings và câu trả lời, xử lý đồng thời để tăng tốc độ.

## 🚀 Bắt đầu nhanh

### 1. Yêu cầu

- **Python** 3.10 - 3.12
- **Google Gemini API Key**: Lấy từ [Google AI Studio](https://aistudio.google.com/)
- (Tùy chọn) **Tesseract OCR**: Cài đặt để xử lý file PDF scan.

### 2. Cài đặt

```bash
# 1. Clone repository
git clone https://github.com/dungle03/rag-pdf.git
cd rag-pdf

# 2. Tạo và kích hoạt môi trường ảo
python -m venv .venv
# Trên Windows
.\.venv\Scripts\Activate.ps1
# Trên macOS/Linux
source .venv/bin/activate

# 3. Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 3. Cấu hình

```bash
# Tạo file .env từ file mẫu
cp .env.example .env
```

Mở file `.env` và điền `GEMINI_API_KEY` của bạn vào.

### 4. Chạy ứng dụng

```bash
# Chạy ở chế độ development (tự động reload khi có thay đổi)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Bây giờ, hãy mở trình duyệt và truy cập `http://127.0.0.1:8000`.

---

## 📖 Tài liệu chi tiết

Để hiểu sâu hơn về dự án, vui lòng tham khảo các tài liệu sau trong thư mục `docs/`:

- **[Kiến trúc & Công nghệ](docs/1_Architecture.md)**: Sơ đồ và giải thích chi tiết về kiến trúc hệ thống.
- **[Mô tả các tính năng](docs/2_Features.md)**: Giải thích chi tiết về các tính năng cốt lõi của hệ thống.
- **[Đóng góp & Phát triển](docs/3_Contributing.md)**: Hướng dẫn về cách đóng góp, cấu trúc code và roadmap dự án.

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng xem hướng dẫn chi tiết tại **[CONTRIBUTING.md](docs/3_Contributing.md)**.

## 📄 Giấy phép

Dự án được phát triển cho mục đích **học tập và nghiên cứu**. Vui lòng trích dẫn nguồn khi sử dụng.

---
**Thông tin tác giả**
- **Sinh viên**: Lê Đình Dũng - 211240089
- **GitHub**: [@dungle03](https://github.com/dungle03)
- **Giảng viên**: Thầy Bùi Ngọc Dũng