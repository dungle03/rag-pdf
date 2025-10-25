# ✨ Tính năng và Cấu hình

Phần này mô tả chi tiết các tính năng cốt lõi của hệ thống và cách tinh chỉnh chúng qua các biến môi trường trong file `.env`.

---

## 🔍 Hệ thống tìm kiếm lai (Hybrid Search)

Kết hợp hai phương pháp tìm kiếm để tăng độ chính xác: **Vector Search** (tìm theo ngữ nghĩa) và **Keyword Search** (tìm theo từ khóa).

- **Dense Retrieval (Vector Search)**: Sử dụng `Gemini embeddings` để hiểu ý nghĩa câu hỏi.
- **Sparse Retrieval (Keyword Search)**: Dùng thuật toán `BM25` để khớp từ khóa chính xác.
- **Hybrid Fusion**: Trộn kết quả của hai phương pháp trên.
- **MMR (Maximal Marginal Relevance)**: Tăng tính đa dạng cho kết quả, tránh các đoạn văn bản trùng lặp.
- **Cross-Encoder Reranking**: Một lớp xếp hạng lại để chọn ra những ngữ cảnh (chunks) phù hợp nhất trước khi đưa vào LLM.

### Cấu hình (`.env`)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `HYBRID_ON` | Bật/tắt Hybrid Search. Nếu `false`, chỉ dùng Vector Search. | `true` |
| `HYBRID_ALPHA` | Trọng số của Keyword Search (BM25). Giá trị từ `0` (chỉ vector) đến `1` (chỉ keyword). | `0.6` |
| `RETRIEVE_TOP_K` | Số lượng chunks ban đầu được lấy ra để chuẩn bị cho bước rerank. | `12` |
| `CONTEXT_K` | Số lượng chunks cuối cùng được gửi đến LLM làm ngữ cảnh. | `10` |
| `MMR_LAMBDA` | Hệ số đa dạng hóa kết quả (`0`: ít đa dạng, `1`: rất đa dạng). | `0.7` |
| `RERANK_ON` | Bật/tắt lớp Cross-encoder Reranking. | `true` |

---

## 🆕 Tính năng Recency Boost - Ưu tiên thông tin mới

Tự động ưu tiên thông tin từ các tài liệu được tải lên gần đây. Khi có file mới, các chunks từ file đó sẽ được tăng điểm, đảm bảo câu trả lời luôn cập nhật.

### Cấu hình (`.env`)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `RECENCY_WEIGHT` | Trọng số của điểm "mới". `0.0` là tắt, `0.5` là ưu tiên tối đa. | `0.3` |
| `RECENCY_MODE` | Cách tính điểm giảm dần theo thời gian: `exponential` (giảm nhanh), `linear` (giảm đều), `step` (giảm theo bậc). | `exponential` |

---

## 🧠 Sinh câu trả lời thông minh (Generative AI)

Sử dụng model `Gemini 2.0 Flash` để tạo ra câu trả lời dựa trên ngữ cảnh đã tìm kiếm, kèm theo các cơ chế bảo vệ để tăng độ tin cậy.

- **Context-aware Generation**: Prompt được thiết kế để bám sát ngữ cảnh.
- **Trích dẫn bắt buộc**: Yêu cầu model trả lời kèm nguồn `[doc:page]`.
- **Guardrails**: Ngưỡng an toàn để từ chối trả lời nếu ngữ cảnh không liên quan, tránh "ảo giác" (hallucination).

### Cấu hình (`.env`)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `RAG_LLM_MODEL` | Model Gemini dùng để sinh câu trả lời. | `gemini-2.0-flash-001` |
| `GENERATE_MIN_SIM` | Ngưỡng tương đồng tối thiểu giữa câu hỏi và ngữ cảnh. Nếu thấp hơn, hệ thống từ chối trả lời. | `0.25` |
| `ANSWER_MIN_CONTEXT_PROB` | Ngưỡng tin cậy tối thiểu mà câu trả lời phải dựa trên ngữ cảnh được cung cấp. | `0.35` |
| `ANSWER_MIN_DIRECT_PROB` | Ngưỡng tin cậy tối thiểu cho các câu trả lời trực tiếp (không cần suy luận phức tạp). | `0.25` |
| `GEN_TEMPERATURE` | Độ "sáng tạo" của model. `0.0` cho câu trả lời xác định, cao hơn sẽ đa dạng hơn. | `0.08` |
| `GEN_MAX_OUTPUT_TOKENS` | Số lượng token tối đa cho một câu trả lời. | `1024` |

---

## 📤 Quản lý và xử lý tài liệu

Hệ thống được tối ưu để xử lý file PDF, bao gồm cả tài liệu scan.

- **Upload đa file**: Hỗ trợ tải lên nhiều file PDF cùng lúc.
- **OCR tích hợp**: Tự động dùng `Tesseract OCR` để trích xuất chữ từ file ảnh/scan.
- **Chunking thông minh**: Chia nhỏ văn bản để tối ưu cho việc tìm kiếm.
- **Session Isolation**: Mỗi phiên chat có một không gian tài liệu riêng.

### Cấu hình (`.env`)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `MAX_FILES` | Số lượng file tối đa cho một lần upload. | `5` |
| `MAX_FILE_MB` | Dung lượng tối đa cho mỗi file (tính bằng MB). | `10` |
| `TESSERACT_CMD` | Đường dẫn đến file thực thi của Tesseract OCR. | `C:\ Program Files\Tesseract-OCR\tesseract.exe` |
| `OCR_LANG` | Ngôn ngữ ưu tiên cho OCR (ví dụ: `vie` cho tiếng Việt, `eng` cho tiếng Anh). | `vie` |

---

## ⚡ Tối ưu hiệu năng & Cache

Tích hợp nhiều lớp cache để giảm độ trễ và tiết kiệm chi phí gọi API.

- **Embedding Cache**: Lưu embedding của các chunk đã xử lý vào SQLite. Giảm gọi API khi ingest lại cùng một tài liệu.
- **Answer Cache**: Lưu lại các cặp câu hỏi-trả lời đã được xử lý trên cùng một bộ tài liệu.

### Cấu hình (`.env`)

| Biến | Mô tả | Giá trị mặc định |
|---|---|---|
| `ENABLE_EMBED_CACHE` | Bật/tắt cache cho embeddings. | `true` |
| `EMBED_CACHE_DIR` | Thư mục lưu trữ database cache của embedding. | `./storage/emb_cache` |
| `ENABLE_ANSWER_CACHE` | Bật/tắt cache cho câu trả lời. | `true` |
| `ANSWER_CACHE_DB` | Đường dẫn đến file SQLite chứa cache câu trả lời. | `./storage/answer_cache.sqlite` |

---

## 💬 Quản lý hội thoại và Giao diện

- **Session độc lập**: Mỗi cuộc trò chuyện có UUID riêng, cô lập tài liệu và lịch sử.
- **Giao diện quản lý**: Sidebar cho phép chuyển đổi, đổi tên, hoặc xóa các phiên chat.
- **Tự động khôi phục**: Mở lại phiên làm việc gần nhất khi truy cập lại.