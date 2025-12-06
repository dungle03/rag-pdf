# CHƯƠNG 3: CÀI ĐẶT VÀ TRIỂN KHAI

## 3.1. Cấu trúc dự án

Dự án được tổ chức theo cấu trúc module rõ ràng, phân tách giữa logic xử lý (RAG core), giao diện (frontend) và API:

```text
rag-pdf/
├── app/
│   ├── main.py              # Entry point - FastAPI app
│   ├── routes.py            # API endpoints & Router
│   ├── rag/                 # Core RAG modules
│   │   ├── pdf_loader.py    # Xử lý PDF & OCR
│   │   ├── chunking.py      # Chia nhỏ văn bản
│   │   ├── embeddings.py    # Tạo vector từ văn bản
│   │   ├── vectorstore.py   # Quản lý FAISS vector DB
│   │   ├── hybrid.py        # Tìm kiếm kết hợp (Hybrid Search)
│   │   ├── rerank.py        # Đánh giá lại kết quả (Reranking)
│   │   ├── generator.py     # Sinh câu trả lời (LLM)
│   │   ├── document_tracker.py # Quản lý phiên bản & trùng lặp
│   │   ├── chat_manager.py  # Quản lý lịch sử chat
│   │   ├── cache.py         # Caching cho embeddings (SQLite)
│   │   └── answer_cache.py  # Caching cho câu trả lời
│   └── utils/               # Các tiện ích (Logger, Security, Config...)
├── templates/               # HTML templates (Jinja2)
├── static/                  # CSS, JavaScript
├── requirements.txt         # Các thư viện phụ thuộc
└── uploads/                 # Lưu trữ dữ liệu session & file upload
```

**Design Patterns:**
- **Modular Architecture:** Chia nhỏ các chức năng thành các module độc lập.
- **Dependency Injection:** Sử dụng qua cơ chế của FastAPI.

---

## 3.2. Module xử lý PDF

**File:** `app/rag/pdf_loader.py`

**Chức năng chính:**
- Trích xuất văn bản từ file PDF sử dụng thư viện **pypdfium2** (hiệu năng cao).
- Tích hợp **Tesseract OCR** để xử lý các tài liệu dạng ảnh (scanned PDF) khi không trích xuất được text.
- Tự động phát hiện và loại bỏ HEADER/FOOTER lặp lại để làm sạch dữ liệu.

**Quy trình:**
1. Load file PDF (bytes hoặc path).
2. Trích xuất text layer cơ bản.
3. Nếu text rỗng hoặc chế độ `ocr=True` được bật: sử dụng `pytesseract` để nhận dạng ký tự quang học.
4. Phân tích tần xuất các dòng đầu/cuối trang để loại bỏ header/footer dư thừa.
5. Chuẩn hóa khoảng trắng và trả về danh sách `(page_number, text)`.

---

## 3.3. Module Embeddings và Vector Store

### Embedding Service (`app/rag/embeddings.py`)

**Model:** Google Gemini `text-embedding-004`
- **Dimension:** 768 chiều.
- **Cơ chế:** Gọi API Google GenAI để lấy vector biểu diễn văn bản.
- **Normalization:** Áp dụng L2 normalization để chuẩn hóa vector (phục vụ tính Cosine Similarity).

**Caching:**
- Sử dụng **SQLite** (`app/rag/cache.py`) để lưu trữ persistent cache các vector đã tính toán.
- Key = SHA1 hash của đoạn text.
- Giảm thiểu chi phí gọi API và tăng tốc độ xử lý khi gặp lại các đoạn văn bản cũ.

### Vector Store (`app/rag/vectorstore.py`)

**FAISS Index:**
- Sử dụng `faiss.IndexFlatIP` (Inner Product) tương đương Cosine Similarity với vector đã chuẩn hóa.
- Lưu trữ index dưới dạng file binary `faiss_index.bin` trong thư mục session.

**Metadata Storage:**
- File `items.jsonl` lưu trữ metadata chi tiết (text gốc, tên file, số trang, chunk_id...) tương ứng với từng vector trong index.
- Đồng bộ 1-1 giữa index của FAISS và dòng trong file JSONL.

---

## 3.4. Module Hybrid Search

**File:** `app/rag/hybrid.py`

**Nguyên lý:** Kết hợp sức mạnh của **Vector Search** (tìm kiếm ngữ nghĩa) và **BM25** (tìm kiếm từ khóa chính xác).

**Quy trình:**
1. **Vector Search:** Truy vấn FAISS để lấy danh sách chunks tương đồng ngữ nghĩa.
2. **BM25 Search:** Sử dụng thư viện `rank_bm25` để đánh giá độ khớp từ khóa trên tập documents.
3. **Score Fusion (RRF):** Kết hợp điểm số từ 2 nguồn và điểm số "tính mới" (Recency Boost).
   - Công thức kết hợp có trọng số: $\alpha$ (Vector), $\beta$ (BM25), $\gamma$ (Recency).
4. **Recency Boost:** Tăng điểm cho các tài liệu mới hơn dựa trên timestamp upload.

---

## 3.5. Module Reranking

**File:** `app/rag/rerank.py`

**Model:** Sử dụng Cross-Encoder `BAAI/bge-reranker-base` (hoặc tương đương).

**Chức năng:**
- Nhận danh sách candidates từ bước Hybrid Search.
- Đánh giá lại độ liên quan (relevance score) chi tiết giữa câu hỏi va từng đoạn văn bản.
- Sắp xếp lại và lọc ra những đoạn văn bản chất lượng nhất (Top-K) để gửi cho LLM.

---

## 3.6. Module Generation

**File:** `app/rag/generator.py`

**Model:** Google Gemini 2.0 Flash (`gemini-2.0-flash-001`).

**Chức năng:**
- Xây dựng prompt context từ các chunk văn bản đã rerank.
- Gửi yêu cầu sinh câu trả lời tới Gemini API.
- Prompt được tối ưu để yêu cầu model trích dẫn nguồn (citation) chính xác.

**Citation:**
- Hệ thống yêu cầu model trả về theo định dạng `[filename:page]`.
- Regex parsing để trích xuất và hiển thị link trích dẫn trên giao diện người dùng.

---

## 3.7. Module Document Tracker

**File:** `app/rag/document_tracker.py`

**Chức năng:** Theo dõi trạng thái tài liệu, phiên bản và tính toán điểm "tính mới".

**Cơ chế SimHash:**
- Tạo fingerprint (dấu vân tay) cho nội dung văn bản.
- Phát hiện tài liệu trùng lặp hoặc phiên bản mới của tài liệu cũ.
- Tự động đánh dấu tài liệu cũ là `superseded` (đã bị thay thế) và tài liệu mới là `active`.

**Recency Scoring:**
- Tính điểm ưu tiên dựa trên thời gian upload (`age_days`).
- Hỗ trợ các chế độ tính: Exponential decay, Linear decay, Step function.

---

## 3.8. Caching System

Hệ thống sử dụng nhiều lớp cache để tối ưu hiệu năng:

1.  **Embedding Cache (`app/rag/cache.py`):**
    - Backend: SQLite (`embed_cache.sqlite`).
    - Lưu trữ vĩnh viễn vector embeddings để không phải tính toán lại khi restart server.
    
2.  **Answer Cache (`app/rag/answer_cache.py`):**
    - Backend: SQLite (`answer_cache.sqlite`).
    - Cache câu trả lời cho các câu hỏi trùng lặp trong cùng ngữ cảnh tài liệu.
    - Key = Hash(Query + List of Document IDs).

---

## 3.9. Giao diện người dùng

**Công nghệ:** HTML5, CSS3, Vanilla JavaScript (không dùng framework nặng).

**Tương tác (`static/app.js`):**
- Quản lý State: Session ID, danh sách file, lịch sử chat.
- Gọi API không đồng bộ (Async/Await) tới Backend.
- Hiển thị Markdown rendering, highlight code, và tương tác với trích dẫn (click to highlight source).

---

## 3.10. API Endpoints

Hệ thống cung cấp các RESTful API endpoints chính (định nghĩa trong `app/routes.py`):

### Session Management
- `POST /session`: Tạo phiên làm việc mới.
- `GET /session/{session_id}`: Lấy thông tin chi tiết phiên làm việc (file, chat history).
- `GET /sessions`: Lấy danh sách các phiên làm việc.
- `DELETE /session/{session_id}`: Xóa phiên làm việc.

### Document Operations
- `POST /upload`: Tải file PDF lên server (lưu trữ tạm).
- `POST /ingest`: Xử lý file PDF (Chunking, Embedding, Indexing) vào hệ thống RAG.
- `DELETE /session/{session_id}/file/{doc_name}`: Xóa file khỏi phiên làm việc.

### Chat & Query
- `POST /ask`: Gửi câu hỏi và nhận câu trả lời.
  - Body: `query`, `session_id`, `chat_id`, ...
- `POST /chat/start`: Bắt đầu cuộc hội thoại mới trong session.
- `GET /chat/{chat_id}`: Lấy nội dung cuộc hội thoại.

### Utilities
- `GET /`: Trang chủ (Home UI).
- `GET /health`: Health check endpoint.
