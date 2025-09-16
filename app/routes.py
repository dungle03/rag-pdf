import os, uuid, json, time
import numpy as np
from typing import List
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.utils import security
from app.utils.schema import Chunk
from app.utils.config import get_int, get_float, get_bool
from app.rag.pdf_loader import load_pdf
from app.rag.chunking import chunk_pages
from app.rag.embeddings import embed_texts
from app.rag.vectorstore import get_store
from app.rag.rerank import rerank
from app.rag.generator import generate
from app.rag.hybrid import hybrid_retrieve

load_dotenv()
router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MANIFEST_NAME = "manifest.json"

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    if len(files) == 0:
        return JSONResponse(status_code=400, content={"error": "Không có file nào được chọn"})
    if len(files) > security.MAX_FILES:
        return JSONResponse(status_code=400, content={"error": f"Tối đa {security.MAX_FILES} file / lần"})

    session_id = str(uuid.uuid4())
    folder = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(folder, exist_ok=True)

    saved = []
    for f in files:
        if not security.is_pdf(f):
            continue
        try:
            data = await security.read_and_check_size(f)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"error": str(e), "file": f.filename})
        path = os.path.join(folder, security.sanitize_filename(f.filename))
        with open(path, "wb") as w:
            w.write(data)
        saved.append({"path": path, "name": os.path.basename(path)})

    if not saved:
        return JSONResponse(status_code=400, content={"error": "Không có PDF hợp lệ"})

    return {"session_id": session_id, "files": saved}

@router.post("/ingest")
async def ingest(
    session_id: str = Form(...),
    ocr: bool = Form(False)
):
    t0 = time.time()
    folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(folder):
        return JSONResponse(status_code=404, content={"error": "session_id không tồn tại"})

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
        chunks = chunk_pages(pages, doc_name=fname, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        total_chunks += len(chunks)
        all_chunks.extend(chunks)
        docs_summary.append({"doc": fname, "pages": len(pages), "chunks": len(chunks)})

    if total_chunks == 0:
        return JSONResponse(status_code=400, content={"error": "Không tạo được chunk nào. Kiểm tra PDF/ OCR."})

    # 3) Embed theo batch
    B = 64
    vecs_list = []
    for i in range(0, len(all_chunks), B):
        batch_texts = [c.text for c in all_chunks[i:i+B]]
        vecs = embed_texts(batch_texts)
        vecs_list.append(vecs)
    vectors = (np.vstack(vecs_list)).astype("float32")
    print("Embed vectors:", vectors.shape, "chunks:", len(all_chunks))


    # 4) Upsert vào vector store
    store = get_store(dim=vectors.shape[1])
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
    return {"ingested": docs_summary, "total_chunks": total_chunks, "latency_ms": latency}

@router.post("/ask")
async def ask(query: str = Form(...)):
    t0 = time.time()

    # === cấu hình truy vấn ===
    TOP_K = get_int("RETRIEVE_TOP_K", 10)
    CONTEXT_K = get_int("CONTEXT_K", 6)
    MMR_LAMBDA = get_float("MMR_LAMBDA", 0.5)
    RERANK_ON = get_bool("RERANK_ON", False)

    # 1) Embed query
    qvec = embed_texts([query])[0]   # dùng embed_texts cho đồng nhất

    # 2) Retrieve + MMR
    store = get_store()
    retrieved = store.search(qvec, top_k=TOP_K, mmr_lambda=MMR_LAMBDA)

    # 3) (optional) Rerank bằng cross-encoder nếu bật
    passages = rerank(retrieved, query, top_k=min(CONTEXT_K, TOP_K)) if RERANK_ON else retrieved[:CONTEXT_K]

    # 4) Generate
    answer, confidence = generate(query, passages)

    citations = [
        {
            "doc": p.doc_name,
            "page": p.page,
            "score": float(p.score or 0.0),
            "text_span": (p.text[:300] + "…") if len(p.text) > 320 else p.text,
        } for p in passages
    ]

    latency = int((time.time() - t0) * 1000)
    return {
        "answer": answer,
        "confidence": float(confidence),
        "citations": citations,
        "latency_ms": latency
    }

# API liệt kê tài liệu (không đụng /docs mặc định của Swagger)
@router.get("/rag-docs")
async def rag_docs():
    try:
        store = get_store()
        return {"docs": store.list_docs(), "vectors": store.size()}
    except Exception:
        return {"docs": [], "vectors": 0}

@router.get("/healthz")
async def healthz():
    return {"status": "ok"}
