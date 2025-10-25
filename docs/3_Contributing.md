# 🔧 Đóng góp & Phát triển

Chúng tôi hoan nghênh mọi sự đóng góp để cải thiện dự án. Dưới đây là hướng dẫn chi tiết để bạn bắt đầu.

## Cấu trúc dự án

```
rag-pdf/
├── app/                           # 🚀 Core Application
│   ├── main.py                   # FastAPI app initialization + CORS + static mounting
│   ├── routes.py                 # API endpoints với error handling
│   ├── rag/                      # 🧠 RAG Engine - Toàn bộ logic AI
│   └── utils/                    # 🛠️ Production Utilities
├── static/                       # 🎨 Frontend Assets
├── templates/                    # 📄 HTML Templates
├── tests/                        # 🧪 Test Suite
├── storage/                      # 💾 Runtime Data (auto-created)
├── uploads/                      # 📁 Session-based File Storage
├── logs/                         # 📁 Plaintext application logs
├── .venv/                        # 🐍 Python Virtual Environment
├── requirements.txt              # 📋 Python dependencies
├── .env.example                  # 📝 Environment configuration template
└── README.md                     # 📖 This documentation
```

## Workflow Phát triển

1.  **Fork & Branch**:
    ```bash
    git clone https://github.com/dungle03/rag-pdf.git
    cd rag-pdf
    git checkout -b feature/your-awesome-feature
    ```

2.  **Cài đặt môi trường**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    pip install -r requirements.txt
    ```

3.  **Lập trình & Kiểm thử**:
    - Thêm code cho tính năng mới.
    - Viết unit test hoặc integration test tương ứng trong thư mục `tests/`.
    - Chạy test để đảm bảo không có lỗi phát sinh:
      ```bash
      python tests/simple_test.py
      python tests/run_eval.py
      ```

4.  **Kiểm tra chất lượng code**:
    ```bash
    # Format code
    black app/ tests/
    
    # Type checking
    mypy app/
    
    # Linting
    flake8 app/ tests/
    ```

5.  **Commit & Push**:
    ```bash
    git add .
    git commit -m "feat: Add your awesome feature"
    git push origin feature/your-awesome-feature
    ```
    Sau đó, tạo một Pull Request trên GitHub.

## Hướng dẫn về Code Style

- **Type Hints**: Bắt buộc cho tất cả các hàm và phương thức.
- **Docstrings**: Theo Google style cho modules, classes và public functions.
- **Error Handling**: Sử dụng custom exceptions và trả về lỗi có cấu trúc.
- **Logging**: Ghi log dạng plaintext, có timestamp và ngữ cảnh.

## Chiến lược Testing

- **`tests/simple_test.py`**: Kiểm tra nhanh toàn bộ workflow (upload -> ingest -> ask).
- **`tests/run_eval.py`**: Chạy bộ đánh giá chi tiết dựa trên `tests/eval_cases.json` để đo lường accuracy.
- Thêm các test case mới vào `eval_cases.json` khi phát triển tính năng.

## Roadmap

#### Ngắn hạn
- [ ] Hỗ trợ nhiều định dạng file (DOCX, TXT, RTF)
- [ ] Cải thiện UI/UX với React frontend
- [ ] Export kết quả ra PDF/Word

#### Dài hạn
- [ ] Hỗ trợ các vector database khác (Qdrant, Weaviate)
- [ ] Fine-tuned embeddings cho tiếng Việt
- [ ] Hỗ trợ Multi-modal (hình ảnh, bảng biểu trong tài liệu)
