# 🏗️ Kiến trúc & Công nghệ

Phần này mô tả chi tiết về kiến trúc hệ thống, luồng xử lý RAG, và các công nghệ được sử dụng.

## Luồng xử lý RAG chi tiết

```mermaid
flowchart LR
    U["👤 Người dùng"] -- "Upload PDF" --> S["🚀 FastAPI /upload"]
    S --> L["📄 PDF Loader<br/>pypdfium2 + OCR"]
    L --> C["✂️ Chunking<br/>300-500 tokens<br/>10-15% overlap"]
    C --> E["🧠 Embeddings<br/>Gemini API"]
    E --> V["💾 Vector Store<br/>FAISS + MMR"]
    
    U -- "❓ Query" --> Q["🔍 FastAPI /ask"]
    Q --> R1["🔎 Hybrid Retrieve<br/>BM25 + Vector"]
    R1 --> R2["🎯 Rerank<br/>BGE CrossEncoder"]
    R2 --> G["✨ Gemini 2.0 Flash<br/>RAG prompts"]
    G --> A["📋 Answer + Citations<br/>[doc:page] format"]
    A --> U
    
    E -.-> EC["💰 Embed Cache<br/>SQLite"]
    G -.-> AC["💾 Answer Cache<br/>Query cache"]
    S -.-> FS["📁 File Storage<br/>Session-based"]
```

## Kiến trúc tổng thể hệ thống

```mermaid
graph TB
    subgraph Frontend["🌐 Frontend Layer"]
        UI["Web Interface<br/>Bootstrap 5 + JS"]
    end
    
    subgraph Gateway["🔌 API Gateway"]
        API["FastAPI Application<br/>ASGI + Uvicorn"]
        ROUTES["Routes Controller<br/>upload, ingest, ask"]
    end
    
    subgraph RAGEngine["🧠 RAG Processing Engine"]
        LOADER["📄 Document Loader<br/>pypdfium2 + OCR"]
        CHUNK["✂️ Smart Chunking<br/>tiktoken-based"]
        EMBED["🔗 Embedding Engine<br/>Gemini API + ThreadPool"]
        VECTOR["💾 Vector Database<br/>FAISS IndexFlatIP"]
        SEARCH["🔍 Hybrid Retrieval<br/>BM25 + Vector + MMR"]
        RERANK["🎯 Cross-Encoder<br/>BGE reranker"]
        GEN["✨ LLM Generator<br/>Gemini 2.0 Flash"]
    end
    
    subgraph Storage["💾 Storage & Cache"]
        FILES["📁 File System<br/>Session-based"]
        ECACHE["⚡ Embedding Cache<br/>SQLite + SHA1"]
        ACACHE["🗃️ Answer Cache<br/>Query + DocSet"]
        LOGS["📁 File Logs<br/>Plaintext"]
    end
    
    subgraph Security["🛡️ Security & Monitoring"]
        VALID["✅ Input Validation<br/>MIME + Size check"]
        RATE["⏱️ Rate Limiting<br/>Per-IP protection"]
        ERROR["🚨 Error Handling<br/>Exception management"]
    end
    
    UI --> API
    API --> ROUTES
    ROUTES --> VALID
    VALID --> LOADER
    LOADER --> CHUNK
    CHUNK --> EMBED
    EMBED --> VECTOR
    VECTOR --> SEARCH
    SEARCH --> RERANK
    RERANK --> GEN
    
    EMBED -.-> ECACHE
    GEN -.-> ACACHE
    LOADER -.-> FILES
    API -.-> RATE
    ROUTES -.-> ERROR
    GEN -.-> LOGS
```

## Công nghệ sử dụng

#### 🚀 Backend Framework
- **FastAPI**: High-performance async web framework.
- **Uvicorn**: ASGI server.
- **Pydantic**: Data validation.

#### 🤖 AI & Machine Learning Stack
- **Google Gemini API**: `text-embedding-004` & `gemini-2.0-flash-001`.
- **FAISS**: Vector database for similarity search.
- **BGE Reranker**: Cross-encoder for re-ranking.
- **BM25**: Sparse retrieval algorithm.
- **MMR**: Maximal Marginal Relevance for diversity.

#### 📄 Document Processing Pipeline
- **pypdfium2** & **pymupdf**: PDF text extraction.
- **Tesseract OCR**: Optical Character Recognition.
- **tiktoken**: Tokenizer for accurate chunking.

#### 🎨 Frontend Technology
- **Bootstrap 5**: Responsive UI framework.
- **Vanilla JavaScript**: Client-side logic.
- **Jinja2**: Server-side templating.

#### 💾 Storage & Performance
- **SQLite**: For embedding and answer cache.
- **File System**: Session-based file management.
- **Multi-threading**: Concurrent embedding generation.
