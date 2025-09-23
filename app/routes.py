import os, uuid, json, time
import numpy as np
from typing import List
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.utils import security
from app.utils.schema import Chunk
from app.utils.config import get_int, get_float, get_bool
from app.rag.pdf_loader import load_pdf
from app.rag.chunking import chunk_pages
from app.rag.embeddings import embed_texts
from app.rag.vectorstore import get_store
from app.rag.hybrid import hybrid_retrieve
from app.rag.rerank import rerank
from app.rag.generator import generate
from app.rag.answer_cache import get_cached, put_cached

load_dotenv()
router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MANIFEST_NAME = "manifest.json"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/upload")
async def upload(
    files: List[UploadFile] = File(...),
    session_id: str | None = Form(None),
):
    if len(files) == 0:
        return JSONResponse(
            status_code=400, content={"error": "Không có file nào được chọn"}
        )
    if len(files) > security.MAX_FILES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Tối đa {security.MAX_FILES} file / lần"},
        )

    # Reuse provided session_id if valid; else create new
    session_id = session_id or str(uuid.uuid4())
    folder = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(folder, exist_ok=True)

    saved = []
    for f in files:
        if not security.is_pdf(f):
            continue
        # Stream to disk to avoid reading entire file into memory
        size_limit = security.MAX_FILE_MB * 1024 * 1024
        path = os.path.join(folder, security.sanitize_filename(f.filename))
        total = 0
        try:
            print(
                f"[upload] start filename='{f.filename}' content_type='{f.content_type}' -> {path}"
            )
            first_chunk = True
            with open(path, "wb") as w:
                while True:
                    chunk = await f.read(1024 * 1024)
                    if not chunk:
                        break
                    if first_chunk:
                        # Kiểm tra chữ ký PDF trên chunk đầu
                        if not security.looks_like_pdf_bytes(chunk):
                            raise ValueError(
                                "Tệp không phải PDF hợp lệ (thiếu chữ ký %PDF)"
                            )
                        first_chunk = False
                    total += len(chunk)
                    if total > size_limit:
                        raise ValueError(f"File vượt quá {security.MAX_FILE_MB} MB")
                    w.write(chunk)
            print(
                f"[upload] done filename='{f.filename}' size={total} bytes saved='{path}'"
            )
        except ValueError as e:
            # cleanup partial file
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            print(f"[upload] error filename='{f.filename}' error='{e}'")
            return JSONResponse(
                status_code=400, content={"error": str(e), "file": f.filename}
            )
        saved.append(
            {
                "path": path,
                "name": os.path.basename(path),
                "orig_name": f.filename,
                "size": total,
            }
        )

    if not saved:
        return JSONResponse(status_code=400, content={"error": "Không có PDF hợp lệ"})

    return {"session_id": session_id, "files": saved}


@router.post("/ingest")
async def ingest(session_id: str = Form(...), ocr: bool = Form(False)):
    t0 = time.time()
    folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(folder):
        return JSONResponse(
            status_code=404, content={"error": "session_id không tồn tại"}
        )

    # đọc cấu hình chunk
    CHUNK_SIZE = get_int("CHUNK_SIZE", 380)
    CHUNK_OVERLAP = get_int("CHUNK_OVERLAP", 50)

    docs_summary = []
    total_chunks = 0
    all_chunks: List[Chunk] = []

    for fname in sorted(os.listdir(folder)):
        if not fname.lower().endswith(".pdf"):
            continue
        fpath = os.path.join(folder, fname)

        # 1) Load PDF (OCR nếu cần)
        pages = load_pdf(fpath, ocr=bool(ocr), ocr_lang="vie+eng")

        # 2) Chunk token-aware
        chunks = chunk_pages(
            pages, doc_name=fname, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP
        )
        total_chunks += len(chunks)
        all_chunks.extend(chunks)
        docs_summary.append({"doc": fname, "pages": len(pages), "chunks": len(chunks)})

    if total_chunks == 0:
        return JSONResponse(
            status_code=400,
            content={"error": "Không tạo được chunk nào. Kiểm tra PDF/ OCR."},
        )

    # 3) Embed theo batch
    B = 64
    vecs_list = []
    for i in range(0, len(all_chunks), B):
        batch_texts = [c.text for c in all_chunks[i : i + B]]
        vecs = embed_texts(batch_texts)
        vecs_list.append(vecs)
    vectors = (np.vstack(vecs_list)).astype("float32")
    print("Embed vectors:", vectors.shape, "chunks:", len(all_chunks))

    # 4) Upsert vào vector store
    store = get_store(session_id=session_id, dim=vectors.shape[1])
    store.add(vectors, all_chunks)

    # 5) Ghi manifest
    manifest = {
        "session_id": session_id,
        "docs": docs_summary,
        "total_chunks": total_chunks,
        "ts": int(time.time()),
        "ocr": bool(ocr),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
    with open(os.path.join(folder, MANIFEST_NAME), "w", encoding="utf-8") as w:
        json.dump(manifest, w, ensure_ascii=False, indent=2)

    latency = int((time.time() - t0) * 1000)
    return {
        "ingested": docs_summary,
        "total_chunks": total_chunks,
        "latency_ms": latency,
    }


@router.post("/ask")
async def ask(
    query: str = Form(...),
    session_id: str = Form(...),
    selected_docs: str | None = Form(None),
):
    # Validation đầu vào
    if not query or not query.strip():
        return JSONResponse(
            status_code=400, content={"error": "Query không được để trống"}
        )

    if len(query.strip()) > 1000:
        return JSONResponse(
            status_code=400, content={"error": "Query quá dài (tối đa 1000 ký tự)"}
        )

    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )

    try:
        print(f"Received query: {query.strip()[:100]}... for session: {session_id}")
        t0 = time.time()

        # === cấu hình truy vấn cân bằng chất lượng vs chi phí ===
        TOP_K = get_int("RETRIEVE_TOP_K", 10)  # Sử dụng giá trị từ .env
        CONTEXT_K = get_int("CONTEXT_K", 6)  # Sử dụng giá trị từ .env
        MMR_LAMBDA = get_float("MMR_LAMBDA", 0.6)  # Diversity cao hơn cho chất lượng
        RERANK_ON = get_bool("RERANK_ON", True)  # Bật rerank để chọn chunks tốt nhất
        ENABLE_ANSWER_CACHE = get_bool("ENABLE_ANSWER_CACHE", True)
        HYBRID_ON = get_bool("HYBRID_ON", True)
        HYBRID_ALPHA = get_float("HYBRID_ALPHA", 0.5)

        # Chuẩn bị thông tin cho cache
        store = get_store(session_id=session_id)
        available_docs = store.list_docs()

        # 0) Kiểm tra answer cache trước
        if ENABLE_ANSWER_CACHE:
            cache_db = os.getenv("ANSWER_CACHE_DB", "./storage/answer_cache.sqlite")
            cached_result = get_cached(cache_db, query.strip(), available_docs)
            if cached_result:
                print(f"Cache hit for query: {query.strip()[:50]}...")
                latency = int((time.time() - t0) * 1000)
                return {
                    "answer": cached_result["answer"],
                    "confidence": cached_result["confidence"],
                    "sources": cached_result["citations"],
                    "latency_ms": latency,
                    "cached": True,
                }

        # 1) Embed query
        print("Embedding query...")
        qvec = embed_texts([query])[0]

        # 2) Parse selected docs once
        allow_docs = None
        if selected_docs:
            try:
                allow_docs = set(json.loads(selected_docs) or [])
            except Exception:
                allow_docs = set(
                    [s.strip() for s in selected_docs.split(",") if s.strip()]
                )

        # 3) Retrieve (hybrid hoặc vector-only)
        print("Retrieving relevant passages...")
        if HYBRID_ON:
            print("Using hybrid search (BM25 + Vector)...")
            retrieved = hybrid_retrieve(
                query_vec=qvec,
                query_text=query.strip(),
                store=store,
                docs=list(allow_docs) if allow_docs else None,
                top_k=TOP_K,
                alpha=HYBRID_ALPHA,
                mmr_lambda=MMR_LAMBDA,
            )
        else:
            print("Using vector search only...")
            retrieved = store.search(qvec, top_k=TOP_K, mmr_lambda=MMR_LAMBDA)
        # Filter theo docs được chọn (chỉ khi không dùng hybrid)
        if allow_docs and not HYBRID_ON:
            retrieved = [c for c in retrieved if c.doc_name in allow_docs]

        # 4) (optional) Rerank
        print("Reranking...")
        passages = (
            rerank(retrieved, query, top_k=min(CONTEXT_K, TOP_K))
            if RERANK_ON
            else retrieved[:CONTEXT_K]
        )

        # 5) Generate
        print("Generating answer...")
        answer, confidence = generate(query, passages)

        sources = [
            {
                "filename": p.doc_name,
                "page": p.page,
                "score": float(p.score or 0.0),
                "content": (p.text[:300] + "…") if len(p.text) > 320 else p.text,
            }
            for p in passages
        ]

        latency = int((time.time() - t0) * 1000)
        print(f"Query completed in {latency}ms")

        # Lưu vào cache nếu bật
        if ENABLE_ANSWER_CACHE:
            put_cached(
                cache_db, query.strip(), available_docs, answer, confidence, sources
            )

        return {
            "answer": answer,
            "confidence": float(confidence),
            "sources": sources,
            "latency_ms": latency,
        }
    except Exception as e:
        print(f"Error in /ask endpoint: {str(e)}")
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500, content={"error": f"Internal server error: {str(e)}"}
        )


# API liệt kê tài liệu (không đụng /docs mặc định của Swagger)
@router.get("/docs")
async def docs():
    all_sessions = []
    for session_id in os.listdir(UPLOAD_DIR):
        manifest_path = os.path.join(UPLOAD_DIR, session_id, MANIFEST_NAME)
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                all_sessions.append(json.load(f))
    return {"sessions": all_sessions}


@router.get("/health")
async def health():
    return {"status": "ok"}


# Alias để khớp tài liệu
@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """Lấy thông tin session để restore sau khi refresh trang"""
    folder = os.path.join(UPLOAD_DIR, session_id)
    manifest_path = os.path.join(folder, MANIFEST_NAME)

    if not os.path.exists(manifest_path):
        return JSONResponse(
            status_code=404,
            content={"error": "Session không tồn tại", "session_found": False},
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Kiểm tra xem files còn tồn tại không
        existing_files = []
        for doc_info in manifest.get("docs", []):
            file_path = os.path.join(folder, doc_info["doc"])
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                existing_files.append(
                    {
                        "name": doc_info["doc"],
                        "orig_name": doc_info["doc"],
                        "size": file_size,
                        "pages": doc_info.get("pages", 0),
                        "chunks": doc_info.get("chunks", 0),
                        "status": "ingested",  # Đã được xử lý
                    }
                )

        # Kiểm tra vector store có tồn tại không
        has_vector_store = False
        try:
            store = get_store(session_id=session_id, dim=768)
            has_vector_store = store.size() > 0
        except Exception:
            has_vector_store = False

        return {
            "session_found": True,
            "session_id": session_id,
            "files": existing_files,
            "manifest": manifest,
            "has_vector_store": has_vector_store,
            "can_ask": has_vector_store and len(existing_files) > 0,
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Lỗi đọc session: {str(e)}", "session_found": False},
        )
