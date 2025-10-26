# ✨ Tính năng và Cấu hình Chi tiết

Tài liệu này mô tả chi tiết các tính năng cốt lõi của RAG PDF QA System, bao gồm nguyên lý hoạt động, use cases thực tế, và hướng dẫn tinh chỉnh tham số để tối ưu cho từng trường hợp sử dụng cụ thể.

---

## 🔍 Hệ thống Tìm kiếm Lai (Hybrid Search)

### Tổng quan

Hybrid Search kết hợp **hai phương pháp bổ trợ** để tìm kiếm thông tin chính xác hơn:
- **Vector Search (Dense Retrieval)**: Tìm kiếm theo **ngữ nghĩa**, hiểu được ý nghĩa câu hỏi ngay cả khi không có từ khóa chính xác.
- **Keyword Search (Sparse Retrieval)**: Tìm kiếm theo **từ khóa**, đảm bảo các thuật ngữ quan trọng được khớp chính xác.

### Cách hoạt động chi tiết

#### 1. Dense Retrieval (Vector Search)
**Nguyên lý:**
- Mỗi chunk text và câu hỏi được chuyển thành vector 768 chiều bằng `Gemini text-embedding-004`.
- Tính độ tương đồng cosine giữa vector câu hỏi và các vector chunks.
- Kết quả: Tìm được các chunks có **ngữ nghĩa gần** với câu hỏi.

**Ví dụ thực tế:**
```
Câu hỏi: "Nghỉ phép được bao nhiêu ngày?"
Chunk tìm được: "Nhân viên được hưởng 12 ngày nghỉ có lương hàng năm."
→ Không có từ "bao nhiêu" nhưng vẫn tìm được vì ngữ nghĩa phù hợp.
```

**Ưu điểm:**
- Hiểu được câu hỏi đặt theo nhiều cách khác nhau
- Tìm được thông tin liên quan ngay cả khi dùng từ đồng nghĩa
- Xử lý tốt câu hỏi tiếng Việt tự nhiên

**Nhược điểm:**
- Có thể bỏ sót thông tin nếu thuật ngữ chuyên ngành quan trọng không nằm trong ngữ cảnh training

#### 2. Sparse Retrieval (BM25 Keyword Search)
**Nguyên lý:**
- Sử dụng thuật toán **BM25** (Best Matching 25) - cải tiến của TF-IDF.
- Đánh giá tần suất xuất hiện của từ khóa trong chunk và độ hiếm của từ trong toàn bộ tài liệu.
- Kết quả: Tìm được các chunks có **từ khóa khớp chính xác**.

**Công thức BM25 (đơn giản hóa):**
```
score(chunk, query) = Σ IDF(term) × (TF(term) × (k+1)) / (TF(term) + k)
```
- `TF`: Term Frequency - tần suất từ trong chunk
- `IDF`: Inverse Document Frequency - độ hiếm của từ
- `k`: Tham số điều chỉnh (thường = 1.5)

**Ví dụ thực tế:**
```
Câu hỏi: "Quy định về ISO 9001 trong công ty?"
Chunk tìm được: "Công ty đã đạt chứng nhận ISO 9001:2015 vào năm 2023."
→ Tìm được vì khớp chính xác từ "ISO 9001"
```

**Ưu điểm:**
- Tìm chính xác các thuật ngữ kỹ thuật, mã số, tên riêng
- Không cần API embedding, xử lý nhanh
- Hoạt động tốt với từ khóa tiếng Anh trong văn bản tiếng Việt

**Nhược điểm:**
- Không hiểu ngữ nghĩa, chỉ khớp từ đúng chính tả
- Không tìm được thông tin nếu câu hỏi dùng từ đồng nghĩa

#### 3. Hybrid Fusion - Kết hợp hai phương pháp
**Công thức kết hợp:**
```python
hybrid_score = (1 - alpha) × vector_score + alpha × bm25_score
```

**Ví dụ cụ thể với alpha = 0.6:**
```
Chunk A: 
  - Vector score = 0.85 (ngữ nghĩa rất gần)
  - BM25 score = 0.30 (ít từ khóa khớp)
  - Hybrid = 0.4 × 0.85 + 0.6 × 0.30 = 0.34 + 0.18 = 0.52

Chunk B:
  - Vector score = 0.60 (ngữ nghĩa khá gần)
  - BM25 score = 0.90 (nhiều từ khóa khớp chính xác)
  - Hybrid = 0.4 × 0.60 + 0.6 × 0.90 = 0.24 + 0.54 = 0.78
  
→ Chunk B được ưu tiên vì cân bằng giữa ngữ nghĩa và từ khóa
```

#### 4. MMR (Maximal Marginal Relevance) - Đa dạng hóa kết quả
**Mục đích:** Tránh trả về nhiều chunks có nội dung trùng lặp.

**Công thức MMR:**
```python
MMR = λ × similarity(chunk, query) - (1-λ) × max_similarity(chunk, selected_chunks)
```

**Ví dụ:**
```
Query: "Chính sách làm việc từ xa"

Không có MMR (λ = 1.0):
  1. "Chính sách WFH: Nhân viên được làm việc từ xa 2 ngày/tuần"
  2. "WFH policy: Employees work from home 2 days per week" (bản tiếng Anh)
  3. "Làm việc từ xa: Tối đa 2 ngày mỗi tuần"
  → Ba chunks gần như giống nhau!

Có MMR (λ = 0.7):
  1. "Chính sách WFH: Nhân viên được làm việc từ xa 2 ngày/tuần"
  2. "Thiết bị hỗ trợ WFH: Công ty cấp laptop và màn hình"
  3. "Quy trình đăng ký WFH qua hệ thống nội bộ"
  → Thông tin đa dạng hơn, bao quát nhiều khía cạnh!
```

**Khuyến nghị `MMR_LAMBDA`:**
- `0.9-1.0`: Ưu tiên relevance tuyệt đối (ít đa dạng)
- `0.7` (default): Cân bằng giữa relevance và đa dạng
- `0.3-0.5`: Rất đa dạng (có thể giảm độ chính xác)

#### 5. Cross-Encoder Reranking
**Nguyên lý:**
- Sau khi có top-K candidates từ hybrid search, dùng model `BGE reranker-base` để đánh giá lại.
- Cross-encoder xem xét **cả câu hỏi và chunk cùng lúc**, cho điểm chính xác hơn bi-encoder (vector search).

**So sánh Bi-encoder vs Cross-encoder:**
```
Bi-encoder (Vector Search):
  embed(query) → [v1]
  embed(chunk) → [v2]
  score = cosine(v1, v2)
  → Nhanh nhưng không xem xét tương tác giữa query và chunk

Cross-encoder (Reranker):
  model([query, chunk]) → score
  → Chậm hơn nhưng chính xác hơn vì xem xét toàn bộ ngữ cảnh
```

**Trade-off:**
- **Bật reranker** (`RERANK_ON=true`): Tăng accuracy 5-15%, tăng latency ~500ms
- **Tắt reranker** (`RERANK_ON=false`): Phản hồi nhanh hơn, accuracy giảm nhẹ

### Bảng cấu hình Hybrid Search

| Biến | Mô tả chi tiết | Giá trị mặc định | Khuyến nghị |
|---|---|---|---|
| `HYBRID_ON` | Bật/tắt Hybrid Search.<br/>• `true`: Kết hợp Vector + BM25<br/>• `false`: Chỉ dùng Vector Search | `true` | Luôn bật cho độ chính xác cao nhất |
| `HYBRID_ALPHA` | Trọng số BM25 trong công thức hybrid.<br/>• `0.0`: Chỉ dùng Vector Search<br/>• `0.5`: Cân bằng 50-50<br/>• `1.0`: Chỉ dùng BM25 | `0.6` | • `0.6-0.7` cho văn bản kỹ thuật (nhiều thuật ngữ)<br/>• `0.3-0.4` cho văn bản tự nhiên |
| `RETRIEVE_TOP_K` | Số chunks ban đầu lấy từ hybrid search.<br/>Số này phải **lớn hơn** `CONTEXT_K` để có không gian cho MMR và reranking. | `12` | • `10-15` cho dataset nhỏ (<100 pages)<br/>• `20-30` cho dataset lớn (>500 pages) |
| `CONTEXT_K` | Số chunks cuối cùng gửi đến LLM.<br/>Quyết định **độ dài context window**. | `10` | • `6-8` cho câu hỏi đơn giản<br/>• `10-12` cho câu hỏi phức tạp cần nhiều ngữ cảnh |
| `MMR_LAMBDA` | Hệ số đa dạng hóa.<br/>• `1.0`: Không đa dạng, chỉ relevance<br/>• `0.5`: Cân bằng<br/>• `0.0`: Đa dạng tối đa (có thể mất relevance) | `0.7` | • `0.8-0.9` cho câu hỏi cần độ chính xác cao<br/>• `0.5-0.6` cho câu hỏi khám phá |
| `RERANK_ON` | Bật/tắt Cross-encoder Reranking.<br/>**Trade-off:** Accuracy +10% nhưng latency +500ms | `true` | • `true` cho production (độ chính xác quan trọng)<br/>• `false` cho development (tốc độ ưu tiên) |

### Use Cases và Tuning Tips

#### Use Case 1: Tài liệu kỹ thuật với nhiều thuật ngữ
**Đặc điểm:** Chứa mã số, thuật ngữ tiếng Anh, ký hiệu kỹ thuật.

**Cấu hình khuyến nghị:**
```ini
HYBRID_ON=true
HYBRID_ALPHA=0.7          # Ưu tiên BM25 để khớp thuật ngữ chính xác
RETRIEVE_TOP_K=15
CONTEXT_K=8
MMR_LAMBDA=0.8            # Ít đa dạng, ưu tiên relevance cao
RERANK_ON=true
```

**Ví dụ:** Tài liệu về API, database schema, quy chuẩn ISO.

#### Use Case 2: Văn bản tự nhiên, câu hỏi mở
**Đặc điểm:** Ngôn ngữ tự nhiên, ít thuật ngữ, cần hiểu ngữ cảnh.

**Cấu hình khuyến nghị:**
```ini
HYBRID_ON=true
HYBRID_ALPHA=0.4          # Ưu tiên Vector Search để hiểu ngữ nghĩa
RETRIEVE_TOP_K=12
CONTEXT_K=10              # Cần nhiều context để hiểu toàn cảnh
MMR_LAMBDA=0.6            # Đa dạng vừa phải
RERANK_ON=true
```

**Ví dụ:** Sách giáo khoa, tài liệu đào tạo, policy văn bản.

#### Use Case 3: Dataset nhỏ, cần phản hồi nhanh
**Đặc điểm:** <50 pages, ít chunks, cần tốc độ.

**Cấu hình khuyến nghị:**
```ini
HYBRID_ON=true
HYBRID_ALPHA=0.5
RETRIEVE_TOP_K=8          # Ít candidates vì dataset nhỏ
CONTEXT_K=5
MMR_LAMBDA=0.7
RERANK_ON=false           # Tắt để giảm latency
```

---

## 🆕 Tính năng Recency Boost - Ưu tiên Thông tin Mới

### Tổng quan

**Recency Boost** tự động phát hiện và ưu tiên chunks từ tài liệu mới hơn khi ranking kết quả. Tính năng này cực kỳ hữu ích khi:
- Có nhiều phiên bản của cùng một tài liệu (policy v1, v2, v3...)
- Thông tin được cập nhật thường xuyên (news, blog, quy định)
- Cần đảm bảo câu trả lời luôn dựa trên thông tin mới nhất

### Cách hoạt động chi tiết

#### Bước 1: Document Registration (Đăng ký tài liệu)
Khi upload một file PDF mới:

```python
# 1. Tính SimHash fingerprint (128-bit)
fingerprint = compute_simhash(full_document_text)

# 2. So sánh với các document đã có
for existing_doc in database:
    hamming_dist = count_different_bits(fingerprint, existing_doc.fingerprint)
    
    if hamming_dist < 20:  # Threshold = 20 bits
        # Đây là phiên bản mới của document cũ!
        existing_doc.status = "superseded"  # Đánh dấu cũ
        new_doc.status = "active"           # Đánh dấu mới
        new_doc.version = existing_doc.version + 1
```

**Ví dụ thực tế:**
```
Ngày 1/1/2024: Upload "hr_policy_2024.pdf"
  → status = "active", version = 1

Ngày 1/7/2024: Upload "hr_policy_2024_updated.pdf"
  → SimHash phát hiện 90% tương đồng với file cũ
  → File cũ: status = "superseded"
  → File mới: status = "active", version = 2
```

#### Bước 2: Temporal Metadata Propagation
Mỗi chunk kế thừa thông tin temporal từ document:

```python
chunk = {
    "text": "Nhân viên được nghỉ 12 ngày/năm",
    "upload_timestamp": 1704067200,  # Unix timestamp
    "document_status": "active",      # active/superseded/archived
    "document_version": 2
}
```

#### Bước 3: Recency Scoring trong Retrieval
Khi query, mỗi chunk được tính recency score dựa trên 3 modes:

##### Mode 1: Exponential Decay (Mặc định - Khuyến nghị)
**Công thức:**
```python
age_days = (current_time - upload_timestamp) / 86400
half_life = 30.0  # Ngày
recency_score = exp(-age_days / half_life)
```

**Đặc điểm:**
- Giảm **mượt mà và tự nhiên** theo thời gian
- Document 30 ngày tuổi = 50% score
- Document 90 ngày tuổi = 12.5% score
- Không bao giờ về 0 (luôn còn một chút giá trị)

**Biểu đồ:**
```
Score
1.0 |●
    |  ●
0.8 |    ●
    |      ●
0.6 |        ●●
    |           ●●
0.4 |              ●●●
    |                  ●●●●
0.2 |                       ●●●●●●
0.0 |_________________________________
    0   15  30  45  60  75  90  days
```

**Phù hợp cho:** Policy updates, documentation, general content.

##### Mode 2: Linear Decay
**Công thức:**
```python
max_age = 90.0  # Ngày
recency_score = max(0, 1.0 - (age_days / max_age))
```

**Đặc điểm:**
- Giảm **đều đặn** theo thời gian
- Document 45 ngày tuổi = 50% score
- Document > 90 ngày = 0% score (bị loại hoàn toàn)

**Biểu đồ:**
```
Score
1.0 |●
    |  ●●
0.8 |     ●●
    |        ●●
0.6 |           ●●
    |              ●●
0.4 |                 ●●
    |                    ●●
0.2 |                       ●●
0.0 |___________________________●●●●
    0   15  30  45  60  75  90  days
```

**Phù hợp cho:** Content có "shelf life" rõ ràng (quarterly reports, seasonal content).

##### Mode 3: Step Function
**Công thức:**
```python
if age_days < 7:
    recency_score = 1.0      # Rất mới: 100%
elif age_days < 30:
    recency_score = 0.7      # Gần đây: 70%
elif age_days < 90:
    recency_score = 0.4      # Cũ: 40%
else:
    recency_score = 0.1      # Rất cũ: 10%
```

**Đặc điểm:**
- **Discrete levels**, không smooth
- Thresholds rõ ràng tại 7/30/90 ngày
- Dễ giải thích và debug

**Biểu đồ:**
```
Score
1.0 |●●●●●●●
    |        
0.7 |        ●●●●●●●●●●●●●●●●●●●●●●●
    |
0.4 |                                  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
    |
0.1 |                                                                  ●●●●●●●●
0.0 |___________________________________________________________________________
    0     7           30                              90              days
```

**Phù hợp cho:** News, alerts, time-critical content.

#### Bước 4: Kết hợp với Hybrid Score
**Công thức cuối cùng:**
```python
final_score = (1 - recency_weight) × hybrid_score + recency_weight × recency_score
```

**Ví dụ tính toán cụ thể:**

Giả sử `RECENCY_WEIGHT=0.3`, `RECENCY_MODE=exponential`:

```
Chunk A (từ document 60 ngày tuổi):
  - hybrid_score = 0.85 (rất relevant)
  - age_days = 60
  - recency_score = exp(-60/30) = 0.135
  - final_score = 0.7 × 0.85 + 0.3 × 0.135 = 0.595 + 0.041 = 0.636

Chunk B (từ document 3 ngày tuổi):
  - hybrid_score = 0.70 (khá relevant)
  - age_days = 3
  - recency_score = exp(-3/30) = 0.905
  - final_score = 0.7 × 0.70 + 0.3 × 0.905 = 0.490 + 0.272 = 0.762
  
→ Chunk B được ưu tiên dù hybrid_score thấp hơn vì rất mới!
```

### Bảng cấu hình Recency Boost

### Bảng cấu hình Recency Boost

| Biến | Mô tả chi tiết | Giá trị mặc định | Range | Khuyến nghị |
|---|---|---|---|---|
| `RECENCY_WEIGHT` | Trọng số của recency trong công thức final score.<br/>• `0.0`: Tắt hoàn toàn (chỉ dùng relevance)<br/>• `0.3`: Default - cân bằng<br/>• `0.5`: Maximum - ưu tiên mạnh content mới | `0.3` | `0.0 - 0.5` | • `0.0` cho textbooks, historical content<br/>• `0.2-0.3` cho documentation<br/>• `0.4-0.5` cho news, policy updates |
| `RECENCY_MODE` | Chế độ time decay:<br/>• `exponential`: Smooth, natural decay<br/>• `linear`: Uniform decrease<br/>• `step`: Discrete thresholds | `exponential` | 3 modes | • `exponential` cho general use<br/>• `linear` cho content có shelf life<br/>• `step` cho time-critical (news) |

### Ma trận Use Cases cho Recency Boost

| Use Case | Scenario | RECENCY_WEIGHT | MODE | Lý do |
|---|---|---|---|---|
| **Policy/HR Updates** | Công ty cập nhật quy định hàng quý/năm | `0.4-0.5` | `exponential` | Phiên bản mới luôn ưu tiên, cũ giảm dần |
| **News/Blog** | Tin tức công nghệ, blog hàng tuần | `0.5` | `step` | Content > 1 tuần = outdated |
| **Technical Docs** | API docs, user guides có updates | `0.3` | `exponential` | Cân bằng giữa relevance và recency |
| **Legal/Compliance** | Văn bản pháp luật, compliance docs | `0.4` | `exponential` | Luật mới thay thế luật cũ |
| **Research Papers** | Bài báo khoa học, literature review | `0.2` | `linear` | Paper gốc vẫn quan trọng dù cũ |
| **Historical Archives** | Sách lịch sử, tài liệu lưu trữ | `0.0` | (any) | Thông tin không phụ thuộc thời gian |
| **Product Catalog** | Danh mục sản phẩm, price list | `0.4` | `linear` | Giá cũ không còn valid sau 90 ngày |

### Workflow thực tế: Policy Update Scenario

**Tình huống:** Công ty có policy nghỉ phép được cập nhật hàng năm.

**Timeline:**
```
📅 01/01/2024: Upload hr_policy_2024.pdf
  ├─ Status: active
  ├─ Version: 1
  └─ Nội dung: "Nhân viên được nghỉ 12 ngày/năm"

📅 15/06/2024: Nhân viên hỏi: "Tôi được nghỉ bao nhiêu ngày?"
  └─ Trả lời: "12 ngày/năm" [hr_policy_2024.pdf:5] ✨ Mới

📅 01/01/2025: Upload hr_policy_2025.pdf
  ├─ SimHash detect: 85% similar to 2024 version
  ├─ Action: Mark 2024 as "superseded"
  ├─ New document:
  │   ├─ Status: active
  │   ├─ Version: 2
  │   └─ Nội dung: "Nhân viên được nghỉ 15 ngày/năm" (tăng lên!)

📅 02/01/2025: Nhân viên hỏi lại câu cũ: "Tôi được nghỉ bao nhiêu ngày?"
  └─ Hệ thống tự động ưu tiên version 2025:
      - Chunk from 2024: recency_score = 0.37 (1 năm tuổi)
      - Chunk from 2025: recency_score = 1.0 (1 ngày tuổi)
  └─ Trả lời: "15 ngày/năm" [hr_policy_2025.pdf:5] ✨ Mới
```

**UI hiển thị:**
```
📄 Sources:
[1] hr_policy_2025.pdf:5 | ✨ Mới | 📅 1 ngày trước | Recency: 100%
    "Nhân viên được nghỉ 15 ngày/năm..."
    
[2] hr_policy_2024.pdf:5 | 📝 Cũ | 📅 1 năm trước | Recency: 37%
    "Nhân viên được nghỉ 12 ngày/năm..."
```

### Troubleshooting Recency Boost

#### Problem 1: Document mới không được ưu tiên
**Triệu chứng:** Chunk từ file mới có recency_score = 1.0 nhưng vẫn rank thấp.

**Nguyên nhân có thể:**
1. `RECENCY_WEIGHT` quá thấp (ví dụ 0.1)
2. Hybrid score của chunk cũ quá cao (0.95+)

**Giải pháp:**
```ini
# Tăng RECENCY_WEIGHT lên
RECENCY_WEIGHT=0.4  # hoặc 0.5

# Hoặc kiểm tra lại relevance của câu hỏi
# Có thể chunk cũ thực sự relevant hơn với câu hỏi cụ thể
```

**Cách debug:**
```python
# Kiểm tra scores trong response
{
  "sources": [
    {
      "doc": "new_doc.pdf",
      "hybrid_score": 0.65,      # Relevance thấp
      "recency_score": 1.0,       # Rất mới
      "final_score": 0.755        # = 0.7*0.65 + 0.3*1.0
    },
    {
      "doc": "old_doc.pdf",
      "hybrid_score": 0.92,       # Relevance cao!
      "recency_score": 0.37,      # Cũ
      "final_score": 0.755        # = 0.7*0.92 + 0.3*0.37
    }
  ]
}
# → Cả hai bằng nhau! Cần tăng RECENCY_WEIGHT
```

#### Problem 2: Document cũ bị ignore hoàn toàn
**Triệu chứng:** Chunk từ file cũ có hybrid_score = 0.95 nhưng không được chọn.

**Nguyên nhân:** `RECENCY_WEIGHT` quá cao hoặc dùng `step` mode với threshold quá strict.

**Giải pháp:**
```ini
# Giảm RECENCY_WEIGHT
RECENCY_WEIGHT=0.2

# Hoặc chuyển sang exponential mode
RECENCY_MODE=exponential
```

#### Problem 3: Version detection sai
**Triệu chứng:** File mới hoàn toàn khác nhưng bị mark là "superseded" của file cũ.

**Nguyên nhân:** SimHash threshold quá cao (>30 bits).

**Giải pháp:** Cần điều chỉnh threshold trong code `document_tracker.py`:
```python
# Default: 20 bits
if hamming_distance < 20:  # Giảm xuống 15 để strict hơn
    mark_as_superseded()
```

---

## 🧠 Sinh câu trả lời thông minh (Generative AI)

### Tổng quan

Sử dụng **Gemini 2.0 Flash** để tạo câu trả lời dựa trên ngữ cảnh đã retrieval, với các cơ chế bảo vệ (guardrails) để tăng độ tin cậy và giảm hallucination.

### Pipeline Generation chi tiết

#### Bước 1: Context Assembly
Sau khi retrieval, hệ thống ghép các chunks thành context:

```python
context = ""
for i, chunk in enumerate(top_chunks):
    context += f"[{i+1}] ({chunk.doc}:page {chunk.page})\n"
    context += f"{chunk.text}\n\n"
```

**Ví dụ context:**
```
[1] (hr_policy.pdf:page 5)
Nhân viên chính thức được hưởng 15 ngày nghỉ phép có lương hàng năm.
Nhân viên thử việc được hưởng 7 ngày nghỉ phép.

[2] (hr_policy.pdf:page 6)
Nghỉ phép cần đăng ký trước tối thiểu 3 ngày làm việc.
Trường hợp khẩn cấp, thông báo cho quản lý trực tiếp.
```

#### Bước 2: Prompt Engineering
Hệ thống tạo prompt với 3 phần chính:

**1. System Instruction:**
```
Bạn là trợ lý AI chuyên trả lời câu hỏi dựa trên tài liệu được cung cấp.
QUAN TRỌNG:
- CHỈ trả lời dựa trên ngữ cảnh được cung cấp
- BẮT BUỘC trích dẫn nguồn [doc:page]
- NẾU không có thông tin: nói "Tôi không tìm thấy..."
```

**2. Context:**
```
=== NGỮ CẢNH ===
[1] (hr_policy.pdf:page 5)
...
```

**3. User Query:**
```
=== CÂU HỎI ===
Nhân viên thử việc được nghỉ bao nhiêu ngày?
```

#### Bước 3: LLM Generation
Gọi Gemini API với parameters:

```python
response = gemini.generate_content(
    prompt,
    temperature=0.08,           # Rất thấp để deterministic
    max_output_tokens=1024,     # Đủ cho câu trả lời chi tiết
    top_p=0.95,                 # Nucleus sampling
    top_k=40                    # Top-K sampling
)
```

**Temperature impact:**
```
Temperature = 0.0 (Deterministic):
  "Nhân viên thử việc được hưởng 7 ngày nghỉ phép. [hr_policy.pdf:5]"
  → Câu trả lời giống nhau mọi lần

Temperature = 0.08 (Default):
  "Theo chính sách, nhân viên thử việc được hưởng 7 ngày nghỉ phép có lương. [hr_policy.pdf:5]"
  → Có variation nhẹ nhưng vẫn chính xác

Temperature = 0.5 (Cao):
  "Nhân viên đang trong thời gian thử việc sẽ được nghỉ 7 ngày trong năm, ít hơn so với nhân viên chính thức. [hr_policy.pdf:5]"
  → Thêm suy luận, có thể hallucinate
```

#### Bước 4: Guardrails - Kiểm tra chất lượng

**Guardrail 1: Minimum Similarity Check**
```python
if max_similarity < GENERATE_MIN_SIM:  # Default: 0.25
    return "Tôi không tìm thấy thông tin liên quan đến câu hỏi của bạn."
```

**Ví dụ:**
```
Query: "Công thức tính tốc độ ánh sáng?"
Top chunk similarity: 0.15 (về policy công ty, không liên quan)
→ HỆ THỐNG TỪ CHỐI TRẢ LỜI thay vì hallucinate
```

**Guardrail 2: Answer Confidence Check**
Sau khi có câu trả lời, hệ thống đánh giá confidence:

```python
confidence_prompt = f"""
Context: {context}
Question: {query}
Answer: {answer}

On a scale 0-1, how confident are you that this answer is:
1. Based on the provided context (context_prob)
2. Directly answering the question (direct_prob)
"""

if context_prob < ANSWER_MIN_CONTEXT_PROB:  # 0.35
    return "Thông tin không đủ tin cậy..."
    
if direct_prob < ANSWER_MIN_DIRECT_PROB:  # 0.25
    return "Câu trả lời không trực tiếp..."
```

**Guardrail 3: Citation Validation**
Kiểm tra câu trả lời có trích dẫn nguồn không:

```python
import re
citations = re.findall(r'\[([^\]]+):(\d+)\]', answer)
if not citations:
    logger.warning("Answer missing citations!")
    # Có thể reject hoặc warn user
```

### Bảng cấu hình Generation

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

## ⚡ Tối ưu Hiệu năng & Cache

### Tổng quan

Hệ thống tích hợp **hai lớp cache** để:
- Giảm latency (thời gian phản hồi)
- Tiết kiệm chi phí API calls
- Tăng throughput (số request/giây)

### Cache Layer 1: Embedding Cache

#### Mục đích
Lưu trữ embeddings đã tính toán để tránh gọi Gemini API lại cho cùng một đoạn text.

#### Cách hoạt động

```python
def get_or_compute_embedding(text: str) -> np.ndarray:
    # 1. Tính hash của text
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    
    # 2. Kiểm tra cache
    cached = cache_db.get(text_hash)
    if cached:
        logger.info("✅ Cache hit!")
        return np.frombuffer(cached, dtype=np.float32)
    
    # 3. Nếu miss, gọi API
    logger.info("❌ Cache miss, calling Gemini API...")
    embedding = gemini.embed_content(text)
    
    # 4. Lưu vào cache
    cache_db.set(text_hash, embedding.tobytes())
    
    return embedding
```

#### Performance Impact

**Scenario: Re-ingest document sau khi chỉnh sửa nhỏ**

Không có cache:
```
Document: 100 pages, 350 chunks
API calls: 350 requests
Time: 350 × 0.3s = 105 seconds
Cost: 350 × $0.00001 = $0.0035
```

Có cache (90% chunks không đổi):
```
Cache hits: 315 chunks (90%)
API calls: 35 requests (10% new/modified)
Time: 35 × 0.3s + 315 × 0.001s = 10.8 seconds  ← 10x faster!
Cost: 35 × $0.00001 = $0.00035  ← 10x cheaper!
```

#### Cache Storage

**Schema SQLite:**
```sql
CREATE TABLE embedding_cache (
    text_hash TEXT PRIMARY KEY,
    embedding BLOB,           -- 768 × 4 bytes = 3KB per entry
    model_name TEXT,
    created_at TIMESTAMP,
    access_count INTEGER
);

CREATE INDEX idx_created ON embedding_cache(created_at);
```

**Capacity estimate:**
```
Average chunk: 300 tokens ≈ 225 words
Embedding size: 768 floats × 4 bytes = 3KB
1000 chunks = 3 MB
10,000 chunks = 30 MB
100,000 chunks = 300 MB ← Very manageable!
```

#### Cache Invalidation Strategy

**Khi nào cần clear cache:**
1. **Model upgrade:** `text-embedding-004` → `text-embedding-005`
2. **Dimension change:** 768 → 1024 dims
3. **Disk space issue:** Cache DB > 1GB

**Commands:**
```bash
# Clear toàn bộ cache
rm ./storage/emb_cache/*.sqlite

# Clear cache cũ hơn 30 ngày
python scripts/clean_old_cache.py --days 30

# Check cache stats
python -c "
from app.rag.cache import EmbeddingCache
cache = EmbeddingCache()
print(f'Entries: {cache.count()}')
print(f'Hit rate: {cache.hit_rate():.1%}')
print(f'Size: {cache.size_mb():.1f} MB')
"
```

### Cache Layer 2: Answer Cache

#### Mục đích
Lưu câu trả lời đã generate cho cùng một cặp (query, document_set).

#### Cách hoạt động

```python
def get_or_generate_answer(query: str, doc_ids: List[str]) -> str:
    # 1. Tính cache key
    cache_key = hashlib.md5(
        f"{query}:{sorted(doc_ids)}".encode()
    ).hexdigest()
    
    # 2. Check cache
    cached_answer = answer_cache.get(cache_key)
    if cached_answer and not is_expired(cached_answer, max_age=3600):
        logger.info("✅ Answer cache hit!")
        return cached_answer['answer']
    
    # 3. Generate new answer
    answer = generate_with_llm(query, contexts)
    
    # 4. Cache with metadata
    answer_cache.set(cache_key, {
        'answer': answer,
        'query': query,
        'doc_ids': doc_ids,
        'timestamp': time.time(),
        'confidence': confidence_score
    })
    
    return answer
```

#### Cache Hit Scenarios

**Scenario 1: Repeated questions**
```
User A (10:00): "Quy định nghỉ phép?"
  → Generate answer, cache it

User B (10:05): "Quy định nghỉ phép?"  ← Exact same query!
  → Cache hit! Return instantly
  
Time saved: ~2 seconds per query
```

**Scenario 2: Similar questions (advanced)**
```python
# With fuzzy matching (optional)
def find_similar_cached_query(new_query: str, threshold=0.95):
    for cached in answer_cache.all():
        similarity = cosine_sim(
            embed(new_query),
            embed(cached['query'])
        )
        if similarity > threshold:
            return cached['answer']
    return None
```

#### Cache Expiration Policy

**TTL (Time To Live) strategy:**
```ini
# .env configuration
ANSWER_CACHE_TTL=3600  # 1 hour default

# Dynamic TTL based on content:
if document_status == "active":
    ttl = 3600  # 1 hour
elif document_status == "superseded":
    ttl = 0     # Don't cache old content
```

**Invalidation triggers:**
1. **New document uploaded** → Clear cache for that session
2. **Document deleted** → Clear related cache entries
3. **Manual clear** → User action via API

### Bảng cấu hình Performance & Cache

| Biến | Mô tả chi tiết | Giá trị mặc định | Khuyến nghị |
|---|---|---|---|
| `ENABLE_EMBED_CACHE` | Bật/tắt Embedding Cache.<br/>**Highly recommended** luôn bật! | `true` | Luôn `true` trừ khi debugging |
| `EMBED_CACHE_DB` | Đường dẫn SQLite database cho embedding cache | `./storage/embed_cache.sqlite` | SSD path để nhanh hơn |
| `ENABLE_ANSWER_CACHE` | Bật/tắt Answer Cache.<br/>Tắt nếu cần câu trả lời luôn mới | `true` | • `true` cho production<br/>• `false` nếu content thay đổi liên tục |
| `ANSWER_CACHE_DB` | Đường dẫn SQLite database cho answer cache | `./storage/answer_cache.sqlite` | SSD path để nhanh hơn |
| `ANSWER_CACHE_TTL` | Time-to-live cho cached answers (giây) | `3600` | • `3600` (1h) cho general<br/>• `600` (10m) cho content động<br/>• `86400` (24h) cho static content |
| `EMBED_CONCURRENCY` | Số threads parallel cho embedding generation | `4` | • `2-4` cho máy yếu<br/>• `8-16` cho server mạnh |
| `EMBED_SLEEP_MS` | Delay giữa các API calls (tránh rate limit) | `0` | • `0` nếu có quota cao<br/>• `100-200` nếu bị rate limit |

### Performance Tuning Matrix

| Scenario | Cache Config | Expected Performance |
|---|---|---|
| **Development** | Both caches ON | • Initial ingest: 100s<br/>• Re-ingest: 10s (10x faster)<br/>• Query: 1.5s avg |
| **Production - High Traffic** | Both caches ON, TTL=3600 | • Cache hit rate: 60-80%<br/>• Avg latency: 0.8s<br/>• API cost: -70% |
| **Production - Low Traffic** | Embed cache ON, Answer cache OFF | • Fresh answers always<br/>• Moderate API usage |
| **Testing/Debug** | Both caches OFF | • Clean state every run<br/>• Higher latency & cost |

### Monitoring Cache Performance

**Metrics to track:**

```python
# app/utils/monitoring.py
class CacheMetrics:
    def __init__(self):
        self.embed_hits = 0
        self.embed_misses = 0
        self.answer_hits = 0
        self.answer_misses = 0
    
    @property
    def embed_hit_rate(self):
        total = self.embed_hits + self.embed_misses
        return self.embed_hits / total if total > 0 else 0
    
    @property
    def answer_hit_rate(self):
        total = self.answer_hits + self.answer_misses
        return self.answer_hits / total if total > 0 else 0
```

**Dashboard example:**
```
=== Cache Performance (Last 24h) ===
Embedding Cache:
  Hits: 15,234 | Misses: 3,456 | Hit Rate: 81.5%
  API Calls Saved: 15,234
  Cost Saved: $0.15

Answer Cache:
  Hits: 892 | Misses: 1,108 | Hit Rate: 44.6%
  Avg Response Time: 0.7s (vs 2.1s without cache)
  
Total Savings: $0.17/day ≈ $5.10/month
```

---

## 💬 Quản lý Hội thoại và Giao diện

### Session Management

**Features:**
- **Multi-session support**: Mỗi user có thể có nhiều chat sessions
- **Session persistence**: Lưu trữ session metadata và chat history
- **Easy navigation**: Sidebar để chuyển đổi giữa các sessions
- **Auto-restore**: Tự động mở lại session gần nhất khi quay lại

### UI Components

#### 1. Sidebar - Session List
```javascript
// Display all sessions
sessions.forEach(session => {
    renderSessionCard({
        title: session.title || "Chat mới",
        message_count: session.message_count,
        last_active: session.last_active,
        status: session.status  // active/superseded/archived
    });
});
```

#### 2. Chat Interface
**Features:**
- Real-time typing indicator
- Message streaming (nếu supported)
- Citation highlighting
- Document source badges (✨ Mới, 📝 Cũ, 📦 Archive)

#### 3. File Management Panel
```
┌─────────────────────────────────────┐
│ 📄 Uploaded Documents               │
├─────────────────────────────────────┤
│ ✅ hr_policy_2025.pdf  (24 KB)     │
│    ✨ Mới | 1 ngày trước            │
│    [View] [Delete]                  │
│                                      │
│ ✅ company_handbook.pdf (156 KB)   │
│    📝 Cũ | 3 tháng trước            │
│    [View] [Delete]                  │
└─────────────────────────────────────┘
```

### Best Practices

**For End Users:**
1. **Organize by topic**: Tạo session riêng cho mỗi chủ đề (HR, Technical, Finance)
2. **Regular cleanup**: Xóa sessions cũ không dùng để tiết kiệm storage
3. **Descriptive titles**: Đặt tên session rõ ràng ("HR Policy Q&A", "API Documentation")

**For Admins:**
```bash
# Cleanup old sessions (>30 days inactive)
python scripts/cleanup_sessions.py --days 30

# Export session data
python scripts/export_session.py --session_id xxx --format json

# Backup all sessions
tar -czf sessions_backup_$(date +%Y%m%d).tar.gz ./uploads/
```

---

## 📊 Summary: Configuration Quick Reference

### Must-Have Settings (Tối thiểu)

```ini
# === Core AI ===
GEMINI_API_KEY=your_actual_key
RAG_EMBED_MODEL=text-embedding-004
RAG_LLM_MODEL=gemini-2.0-flash-001

# === Essential Performance ===
ENABLE_EMBED_CACHE=true
ENABLE_ANSWER_CACHE=true

# === Balanced Retrieval ===
HYBRID_ON=true
HYBRID_ALPHA=0.6
CONTEXT_K=10
```

### Recommended Production Settings

```ini
# === Optimized for Accuracy ===
HYBRID_ALPHA=0.6
RETRIEVE_TOP_K=12
CONTEXT_K=10
MMR_LAMBDA=0.7
RERANK_ON=true

# === Optimized for Recency ===
RECENCY_WEIGHT=0.3
RECENCY_MODE=exponential

# === Optimized for Safety ===
GENERATE_MIN_SIM=0.25
ANSWER_MIN_CONTEXT_PROB=0.35
GEN_TEMPERATURE=0.08

# === Optimized for Performance ===
ENABLE_EMBED_CACHE=true
ENABLE_ANSWER_CACHE=true
EMBED_CONCURRENCY=4
```

### Emergency "Fix It" Configs

**Problem: Too many hallucinations**
```ini
GEN_TEMPERATURE=0.05         # More deterministic
GENERATE_MIN_SIM=0.30        # Stricter threshold
ANSWER_MIN_CONTEXT_PROB=0.40
```

**Problem: Too slow**
```ini
RERANK_ON=false              # Disable reranker
CONTEXT_K=6                  # Less context
RETRIEVE_TOP_K=8
GEN_MAX_OUTPUT_TOKENS=512
```

**Problem: Over-rejecting questions**
```ini
GENERATE_MIN_SIM=0.20        # Lower threshold
ANSWER_MIN_CONTEXT_PROB=0.30
HYBRID_ALPHA=0.5             # More semantic search
```

---

## 🎓 Learning Path: From Beginner to Expert

### Level 1: Basic Usage (Người dùng cơ bản)
✅ Upload PDF và đặt câu hỏi  
✅ Hiểu cách đọc trích dẫn `[doc:page]`  
✅ Biết khi nào nên dùng OCR

### Level 2: Configuration Tuning (Người dùng nâng cao)
✅ Điều chỉnh `HYBRID_ALPHA` theo loại tài liệu  
✅ Tuning `RECENCY_WEIGHT` cho use case cụ thể  
✅ Hiểu trade-off giữa accuracy và speed

### Level 3: Advanced Optimization (Power User)
✅ Monitoring cache hit rates  
✅ Custom chunking strategies  
✅ A/B testing different configurations

### Level 4: System Administration (Admin/DevOps)
✅ Performance profiling với metrics  
✅ Database optimization và backup  
✅ Multi-user deployment và scaling

---

**Tài liệu này sẽ được cập nhật liên tục. Hãy check lại thường xuyên để có thông tin mới nhất! 🚀**