# 🔧 Đóng góp & Phát triển

## 🔧 Thêm tính năng mới

### Workflow Development
1. **Fork & Branch**
   ```bash
   git clone https://github.com/dungle03/rag-pdf.git
   cd rag-pdf
   git checkout -b feature/awesome-feature
   ```

2. **Setup Development Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   pip install -r requirements.txt
   pip install -e .  # Editable install
   ```

3. **Implement với Testing**
   ```bash
   # Tạo tests cho feature mới
   echo '{"q": "Test question?", "expected": ["keyword"]}' >> tests/eval_cases.json
   
   # Run tests
   python tests/simple_test.py
   python tests/run_eval.py
   ```

4. **Code Quality Checks**
   ```bash
   # Format code
   black app/ tests/
   
   # Type checking
   mypy app/
   
   # Linting
   flake8 app/ tests/
   ```

5. **Commit & Push**
   ```bash
   git add .
   git commit -m "feat: add awesome feature with tests"
   git push origin feature/awesome-feature
   ```

### 📝 Code Style Guidelines
- **Type Hints**: Bắt buộc cho tất cả functions và class methods
- **Docstrings**: Google style cho modules, classes và public functions
- **Error Handling**: Sử dụng custom exceptions và structured error responses
- **Logging**: Plaintext logging (timestamped, contextual fields)
- **Testing**: Unit tests + integration tests cho mọi feature mới

### 🧪 Testing Strategy
```bash
# Unit tests cho individual components
python -m pytest tests/unit/ -v

# Integration tests cho entire workflow  
python -m pytest tests/integration/ -v

# Performance benchmarks
python tests/benchmark.py

# Load testing với multiple sessions
python tests/load_test.py --sessions 10 --queries 100
```

## Roadmap tính năng

### ✅ Đã hoàn thành (Completed)
- [x] **Recency Boost**: Tự động ưu tiên tài liệu mới hơn với SimHash-based versioning
- [x] **Document Versioning**: Smart detection và status tracking (active/superseded/archived)
- [x] **Temporal Metadata**: Propagation từ document → chunks → retrieval → UI
- [x] **Three Decay Modes**: Exponential, Linear, Step với configurable parameters
- [x] **UI Enhancements**: Status badges (✨/📝/📦) và age info display

### Ngắn hạn
- [ ] Hỗ trợ nhiều định dạng file (DOCX, TXT, RTF)
- [ ] Cải thiện UI/UX với React frontend
- [ ] Export kết quả ra PDF/Word
- [ ] Multi-language support

### Dài hạn
- [ ] Vector database scaling (Qdrant, Weaviate)
- [ ] Fine-tuned embeddings cho tiếng Việt
- [ ] Multi-modal support (images, tables)
- [ ] Collaborative features (sharing, comments)
