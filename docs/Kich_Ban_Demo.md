# GIỚI THIỆU VÀ KỊCH BẢN DEMO PROJECT RAG-PDF

## 1. Giới thiệu dự án (Pitch 30 giây)

"Thưa thầy/cô, đây là hệ thống **RAG-PDF Intelligent Q&A** - giải pháp hỏi đáp tài liệu thông minh sử dụng **Google Gemini** và kỹ thuật **Hybrid Search** (kết hợp tìm kiếm ngữ nghĩa và từ khóa).

Điểm khác biệt của dự án là tính năng **'Recency Boost'** giúp hệ thống tự động ưu tiên thông tin từ các tài liệu mới nhất, giải quyết bài toán thông tin lỗi thời. Bên cạnh đó, hệ thống tích hợp **Smart Document Tracking** để quản lý phiên bản, phát hiện trùng lặp và trích dẫn nguồn (citation) chính xác đến từng trang tài liệu, tất cả được vận hành trên nền tảng **FastAPI** hiệu năng cao."

---

## 2. Kịch bản Demo (Step-by-step)

### Giai đoạn 1: Khởi động & Upload (Chứng minh khả năng xử lý dữ liệu)

1.  **Mở trang chủ**: Giới thiệu giao diện sạch, tập trung vào Chat & Upload.
2.  **Upload File 1 (Cũ)**:
    *   *Hành động*: Kéo thả file `Chinh_Sach_Nhan_Su_2023.pdf`.
    *   *Kết quả*: Hệ thống xử lý nhanh, hiện thông báo thành công.
3.  **Upload File 1 (Lại lần nữa)**:
    *   *Hành động*: Upload lại chính file vừa rồi.
    *   *Kết quả*: Hệ thống báo lỗi **"Duplicate document"** (Chứng minh tính năng SimHash Fingerprint - không tốn tài nguyên xử lý lại).

### Giai đoạn 2: Hỏi đáp cơ bản (Chứng minh RAG & Citation)

1.  **Câu hỏi 1**: "Chính sách nghỉ phép năm như thế nào?"
2.  **Quan sát**:
    *   Câu trả lời được sinh ra tự nhiên.
    *   **Quan trọng**: Chỉ vào **Trích dẫn [Chinh_Sach_Nhan_Su_2023.pdf:trang X]** ở cuối câu. Click vào trích dẫn để show (nếu UI hỗ trợ highlight).

### Giai đoạn 3: Tính năng Recency Boost (Điểm đắt giá nhất)

1.  **Upload File 2 (Mới)**:
    *   *Hành động*: Upload file `Chinh_Sach_Nhan_Su_2024.pdf` (Nội dung sửa đổi: "Nghỉ phép tăng lên 14 ngày" thay vì 12 ngày cũ).
    *   *Kết quả*: Hệ thống nhận diện đây là **"Updated Version"** (do tên hoặc nội dung tương đồng cao) và đánh dấu file cũ là **"Superseded"**.
2.  **Hỏi lại câu cũ**: "Chính sách nghỉ phép năm hiện tại là bao nhiêu?"
3.  **Kết quả mong đợi**:
    *   Hệ thống trả lời theo số liệu mới (14 ngày).
    *   Giải thích: "Hệ thống tự động ưu tiên tài liệu 2024 do thuật toán Recency Decay, dù tài liệu 2023 vẫn nằm trong kho dữ liệu."

### Giai đoạn 4: Hybrid Search (Tìm kiếm chính xác)

1.  **Hỏi câu chứa mã số/từ khóa đặc thù**: "Mã quy trình QT-099 quy định gì?" (Giả sử QT-099 chỉ xuất hiện 1 lần).
2.  **Kết quả**: Hệ thống tìm chính xác đoạn chứa "QT-099" nhờ **BM25**, trong khi Vector Search thuần túy có thể bị trôi nghĩa.

### Giai đoạn 5: Quản lý Session

1.  *Hành động*: Bấm nút "New Chat" hoặc "Tạo Session mới".
2.  *Kết quả*: Môi trường làm việc mới hoàn toàn, không bị lẫn lộn dữ liệu với bài demo trước (Tính năng Multi-session).

---

## 3. Chuẩn bị file test

Để demo mượt mà, bạn nên chuẩn bị sẵn 2 file PDF giả lập:
1.  `Quy_Dinh_A_v1.pdf`: Chứa thông tin cũ (VD: Lương cơ bản 10 triệu).
2.  `Quy_Dinh_A_v2.pdf`: Chứa thông tin mới (VD: Lương cơ bản 15 triệu).
