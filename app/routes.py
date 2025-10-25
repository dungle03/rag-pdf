import os, uuid, json, time, shutil, math, re
import numpy as np
from typing import List
from fastapi import APIRouter, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.utils import security
from app.utils.logger import app_logger
from app.utils.schema import Chunk
from app.utils.config import get_int, get_float, get_bool
from app.rag.pdf_loader import load_pdf
from app.rag.chunking import chunk_pages
from app.rag.embeddings import embed_texts
from app.rag.vectorstore import get_store, drop_store
from app.rag.hybrid import hybrid_retrieve
from app.rag.rerank import rerank
from app.rag.generator import generate
from app.rag.answer_cache import get_cached, put_cached
from app.utils.ingest_jobs import (
    create_job,
    set_job_progress,
    set_job_done,
    set_job_failed,
)
from app.rag.chat_manager import (
    append_exchange,
    create_chat,
    delete_chat,
    list_chats,
    load_chat,
    rename_chat as rename_chat_entry,
)
from app.rag.document_tracker import SmartDocumentTracker  # ← NEW

load_dotenv()
router = APIRouter()
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MANIFEST_NAME = "manifest.json"


def _score_to_probability(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v >= 50:
        return 1.0
    if v <= -50:
        return 0.0
    if 0.0 <= v <= 1.0:
        return v
    if v > 1.0:
        return 1.0 / (1.0 + math.exp(-v))
    # assume [-1,1]
    return max(0.0, min(1.0, (v + 1.0) / 2.0))


def _chunk_probability(chunk: Chunk) -> float:
    meta = chunk.meta if isinstance(chunk.meta, dict) else {}
    for key in ("relevance", "hybrid_score", "dense_score", "dense_score_raw"):
        if key in meta:
            prob = _score_to_probability(meta.get(key))
            if prob > 0:
                return prob
    return _score_to_probability(getattr(chunk, "score", None))


_CITATION_RE = re.compile(r"\[([^\[\]]+?\.pdf)\s*:\s*([^\]]+?)\]")


def _extract_citation_pairs(answer: str) -> set[tuple[str, str | None]]:
    """Trích danh sách (tài liệu, trang) từ câu trả lời."""
    pairs: set[tuple[str, str | None]] = set()
    if not answer:
        return pairs

    for doc_name, raw_pages in _CITATION_RE.findall(answer):
        doc = (doc_name or "").strip()
        if not doc:
            continue
        raw = (raw_pages or "").strip()
        if not raw:
            pairs.add((doc, None))
            continue
        segments = [seg.strip() for seg in raw.split(",") if seg.strip()]
        if not segments:
            pairs.add((doc, None))
            continue
        for segment in segments:
            range_match = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", segment)
            if range_match:
                try:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2))
                    if start <= end:
                        for page_num in range(start, end + 1):
                            pairs.add((doc, str(page_num)))
                        continue
                except ValueError:
                    pass
                pairs.add((doc, range_match.group(1)))
                pairs.add((doc, range_match.group(2)))
            else:
                pairs.add((doc, segment))
    return pairs


def _session_summary(session_id: str) -> dict:
    folder = os.path.join(UPLOAD_DIR, session_id)
    manifest_path = os.path.join(folder, MANIFEST_NAME)
    manifest = {}
    docs_summary: list[dict] = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            docs_summary = manifest.get("docs", [])
        except Exception:
            manifest = {}
            docs_summary = []

    chats = list_chats(UPLOAD_DIR, session_id)
    primary_chat = chats[0] if chats else None

    title = "Phiên làm việc"
    if primary_chat and primary_chat.get("title"):
        title = primary_chat["title"]
    elif docs_summary:
        title = docs_summary[0].get("doc", "Phiên làm việc")
    else:
        title = f"Phiên {session_id[:6]}"

    return {
        "session_id": session_id,
        "title": title,
        "created_at": primary_chat.get("created_at") if primary_chat else None,
        "updated_at": primary_chat.get("updated_at") if primary_chat else None,
        "message_count": primary_chat.get("message_count") if primary_chat else 0,
        "chat_id": primary_chat.get("chat_id") if primary_chat else None,
        "doc_count": len(docs_summary),
        "docs": docs_summary,
    }


def _session_snapshot(session_id: str) -> dict:
    folder = os.path.join(UPLOAD_DIR, session_id)
    manifest_path = os.path.join(folder, MANIFEST_NAME)

    if not os.path.isdir(folder):
        raise FileNotFoundError("Session không tồn tại")

    manifest: dict = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}

    manifest.setdefault("session_id", session_id)
    manifest.setdefault("docs", [])
    manifest.setdefault("total_chunks", 0)

    docs_summary = manifest.get("docs", [])
    docs_by_name = {doc.get("doc"): doc for doc in docs_summary if doc.get("doc")}

    existing_files = []
    pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    for fname in pdf_files:
        file_path = os.path.join(folder, fname)
        if not os.path.isfile(file_path):
            continue
        file_size = os.path.getsize(file_path)
        doc_meta = docs_by_name.get(fname)
        status = "ingested" if doc_meta else "uploaded"
        existing_files.append(
            {
                "name": fname,
                "orig_name": fname,
                "size": file_size,
                "pages": doc_meta.get("pages", 0) if doc_meta else 0,
                "chunks": doc_meta.get("chunks", 0) if doc_meta else 0,
                "status": status,
            }
        )

    has_vector_store = False
    try:
        store = get_store(session_id=session_id, dim=768)
        has_vector_store = store.size() > 0
    except Exception:
        has_vector_store = False

    chats = list_chats(UPLOAD_DIR, session_id)

    return {
        "session_found": True,
        "session_id": session_id,
        "files": existing_files,
        "manifest": manifest,
        "has_vector_store": has_vector_store,
        "can_ask": has_vector_store and len(existing_files) > 0,
        "chats": chats,
    }


def _normalize_session_id(raw: str | None) -> str | None:
    """Validate and normalize session_id. Return None if invalid."""
    if not raw:
        return None
    sid = raw.strip()
    # accept UUID hex (32 chars) or simple alphanumeric session ids; sanitize path chars
    if len(sid) == 32 and all(c in "0123456789abcdefABCDEF" for c in sid):
        return sid
    # fallback: allow shorter ids (used by UI) but reject path traversal
    if ".." in sid or "/" in sid or "\\" in sid:
        return None
    return sid


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
    normalized = _normalize_session_id(session_id)
    session_id = normalized or str(uuid.uuid4())
    folder = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(folder, exist_ok=True)

    saved = []
    errors: list[dict[str, str]] = []
    for f in files:
        if not security.is_pdf(f):
            errors.append({"file": f.filename or "", "error": "File không phải PDF"})
            continue
        # Stream to disk to avoid reading entire file into memory
        size_limit = security.MAX_FILE_MB * 1024 * 1024
        safe_name = security.sanitize_filename(f.filename or "")
        path = os.path.join(folder, safe_name)
        total = 0
        try:
            app_logger.info(
                "[upload] start filename='%s' content_type='%s' -> %s",
                f.filename,
                f.content_type,
                path,
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
            app_logger.info(
                "[upload] done filename='%s' size=%d bytes saved='%s'",
                f.filename,
                total,
                path,
            )
        except ValueError as e:
            # cleanup partial file
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            app_logger.warning(
                "[upload] error filename='%s' error='%s'", f.filename, str(e)
            )
            errors.append({"file": f.filename or safe_name, "error": str(e)})
            continue
        except Exception as e:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            app_logger.exception(
                "[upload] unexpected error filename='%s' error='%s'", f.filename, str(e)
            )
            errors.append(
                {"file": f.filename or safe_name, "error": "Không thể lưu file"}
            )
            continue
        saved.append(
            {
                "path": path,
                "name": os.path.basename(path),
                "orig_name": f.filename,
                "size": total,
            }
        )

    if not saved:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Không có PDF hợp lệ",
                "errors": errors,
            },
        )

    return {"session_id": session_id, "files": saved, "errors": errors}


@router.post("/ingest")
async def ingest(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    ocr: bool = Form(False),
    background: bool = Form(False),
):
    t0 = time.time()
    folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(folder):
        return JSONResponse(
            status_code=404, content={"error": "session_id không tồn tại"}
        )

    # đọc cấu hình chunk
    CHUNK_SIZE = get_int("CHUNK_SIZE", 380)
    CHUNK_OVERLAP = get_int("CHUNK_OVERLAP", 50)

    # Initialize document tracker ← NEW
    doc_tracker = SmartDocumentTracker(folder)

    manifest_path = os.path.join(folder, MANIFEST_NAME)
    existing_docs_map: dict[str, dict] = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_existing = json.load(f)
            for doc_info in manifest_existing.get("docs", []):
                name = doc_info.get("doc")
                if name:
                    existing_docs_map[name] = doc_info
        except Exception:
            existing_docs_map = {}

    docs_summary: list[dict] = []
    new_docs_summary: list[dict] = []
    total_chunks_new = 0
    all_chunks: List[Chunk] = []
    skipped_docs: list[str] = []

    for fname in sorted(os.listdir(folder)):
        if not fname.lower().endswith(".pdf"):
            continue
        fpath = os.path.join(folder, fname)

        if fname in existing_docs_map:
            docs_summary.append(existing_docs_map[fname])
            skipped_docs.append(fname)
            continue

        # 1) Load PDF (OCR nếu cần)
        with open(fpath, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        pages = load_pdf(pdf_bytes, ocr=bool(ocr), ocr_lang="vie+eng")

        # 1.5) Register document và detect version/duplicate ← NEW
        normalized_text = " ".join(text for _, text in pages)
        chunk_ids_placeholder = []  # Will be updated after chunking

        doc_status, doc_message, superseded_doc = doc_tracker.register_document(
            filename=fname,
            raw_content=pdf_bytes,
            normalized_text=normalized_text,
            pages=pages,
            chunk_ids=chunk_ids_placeholder,
        )

        doc_metadata = doc_tracker.get_document_metadata(fname)
        upload_timestamp = (
            doc_metadata.upload_timestamp if doc_metadata else time.time()
        )
        document_status = doc_metadata.status if doc_metadata else "active"
        document_version = doc_metadata.version if doc_metadata else 1

        app_logger.info(
            "[ingest] Document '%s': %s - %s", fname, doc_status, doc_message
        )

        # 2) Chunk token-aware với enhanced metadata ← UPDATED
        chunks = chunk_pages(
            pages,
            doc_name=fname,
            chunk_size=CHUNK_SIZE,
            overlap=CHUNK_OVERLAP,
            upload_timestamp=upload_timestamp,  # ← NEW
            document_status=document_status,  # ← NEW
            document_version=document_version,  # ← NEW
        )
        if len(chunks) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Không tạo được chunk nào cho tài liệu {fname}. Kiểm tra PDF / OCR."
                },
            )
        total_chunks_new += len(chunks)
        all_chunks.extend(chunks)
        doc_summary = {
            "doc": fname,
            "pages": len(pages),
            "chunks": len(chunks),
            "status": doc_status,  # ← NEW
            "message": doc_message,  # ← NEW
            "upload_timestamp": upload_timestamp,  # ← NEW
            "document_status": document_status,  # ← NEW
            "version": document_version,  # ← NEW
        }
        docs_summary.append(doc_summary)
        new_docs_summary.append(doc_summary)

    if total_chunks_new == 0:
        # Không có tài liệu mới để xử lý, trả về thông tin hiện có
        existing_docs = list(existing_docs_map.values())
        existing_docs.sort(key=lambda d: d.get("doc", ""))
        latency = int((time.time() - t0) * 1000)
        return {
            "ingested": [],
            "total_chunks": 0,
            "overall_chunks": sum(d.get("chunks", 0) for d in existing_docs),
            "docs": existing_docs,
            "skipped": skipped_docs,
            "message": "Không có tài liệu mới cần xử lý.",
            "latency_ms": latency,
        }

    # 3) Embed theo batch
    B = 64
    vecs_list = []
    for i in range(0, len(all_chunks), B):
        batch_texts = [c.text for c in all_chunks[i : i + B]]
        vecs = embed_texts(batch_texts)
        vecs_list.append(vecs)
    vectors = (np.vstack(vecs_list)).astype("float32")
    app_logger.info("Embed vectors: %s chunks: %d", vectors.shape, len(all_chunks))

    # 4) Upsert vào vector store
    store = get_store(session_id=session_id, dim=vectors.shape[1])
    store.add(vectors, all_chunks)

    # 5) Ghi manifest (kết hợp với tài liệu đã xử lý trước đó)
    docs_by_name: dict[str, dict] = {}
    for doc in docs_summary:
        name = doc.get("doc")
        if name:
            docs_by_name[name] = doc
    for name, doc in existing_docs_map.items():
        if name not in docs_by_name:
            docs_by_name[name] = doc
    combined_docs = sorted(docs_by_name.values(), key=lambda d: d.get("doc", ""))

    # Get document tracking statistics ← NEW
    doc_stats = doc_tracker.get_statistics()

    manifest = {
        "session_id": session_id,
        "docs": combined_docs,
        "total_chunks": sum(d.get("chunks", 0) for d in combined_docs),
        "ts": int(time.time()),
        "ocr": bool(ocr),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "document_stats": doc_stats,  # ← NEW
    }
    with open(manifest_path, "w", encoding="utf-8") as w:
        json.dump(manifest, w, ensure_ascii=False, indent=2)

    latency = int((time.time() - t0) * 1000)
    result = {
        "ingested": new_docs_summary,
        "total_chunks": total_chunks_new,
        "overall_chunks": manifest["total_chunks"],
        "docs": combined_docs,
        "skipped": skipped_docs,
        "latency_ms": latency,
        "document_stats": doc_stats,  # ← NEW
    }

    if background:
        # Create a job and perform ingestion in background
        job_id = create_job(session_id)

        def _bg_task(jid: str, sid: str, ocr_flag: bool):
            try:
                set_job_progress(jid, 10)
                # Re-run ingest steps (simplified): load files, chunk, embed, upsert
                # For PoC we mark done with the same result
                time.sleep(0.1)
                set_job_progress(jid, 90)
                set_job_done(jid, result)
            except Exception as e:
                set_job_failed(jid, str(e))

        background_tasks.add_task(_bg_task, job_id, session_id, bool(ocr))
        return {"job_id": job_id, "status": "queued"}

    return result


@router.delete("/session/{session_id}/file/{doc_name}")
async def delete_uploaded_file(session_id: str, doc_name: str):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )

    folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(folder):
        return JSONResponse(status_code=404, content={"error": "Session không tồn tại"})

    safe_name = security.sanitize_filename(doc_name)
    file_path = os.path.join(folder, safe_name)
    if not os.path.isfile(file_path):
        return JSONResponse(
            status_code=404, content={"error": "Tài liệu không tồn tại"}
        )

    try:
        os.remove(file_path)
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Không thể xoá file: {str(e)}"}
        )

    store = get_store(session_id)
    removed_vectors = store.remove_doc(safe_name)

    manifest_path = os.path.join(folder, MANIFEST_NAME)
    manifest: dict = {
        "session_id": session_id,
        "docs": [],
        "total_chunks": 0,
        "ts": int(time.time()),
        "ocr": False,
        "chunk_size": get_int("CHUNK_SIZE", 380),
        "chunk_overlap": get_int("CHUNK_OVERLAP", 50),
    }
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            manifest.update(existing)
        except Exception:
            pass

    docs_before = manifest.get("docs", []) or []
    docs_after = [doc for doc in docs_before if doc.get("doc") != safe_name]
    manifest["docs"] = docs_after
    manifest["total_chunks"] = sum(d.get("chunks", 0) for d in docs_after)
    manifest["ts"] = int(time.time())

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    try:
        snapshot = _session_snapshot(session_id)
    except FileNotFoundError:
        snapshot = {
            "session_found": False,
            "session_id": session_id,
            "files": [],
            "manifest": manifest,
            "has_vector_store": False,
            "can_ask": False,
            "chats": [],
        }

    return {
        "deleted": True,
        "doc": safe_name,
        "removed_vectors": removed_vectors,
        "session": snapshot,
    }


@router.post("/ask")
async def ask(
    query: str = Form(...),
    session_id: str = Form(...),
    selected_docs: str | None = Form(None),
    chat_id: str | None = Form(None),
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

    # Normalize session id
    normalized = _normalize_session_id(session_id)
    if not normalized:
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    session_id = normalized

    try:
        app_logger.info(
            "Received query: %s... for session: %s", query.strip()[:100], session_id
        )
        t0 = time.time()

        # Ensure session folder exists
        session_folder = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_folder, exist_ok=True)

        # chuẩn bị chat
        chat_id_value = (chat_id or "").strip()
        chat_meta: dict | None = None
        if not chat_id_value:
            existing = list_chats(UPLOAD_DIR, session_id)
            if existing:
                chat_id_value = existing[0]["chat_id"]
            else:
                chat_meta = create_chat(UPLOAD_DIR, session_id)
                chat_id_value = chat_meta["chat_id"]
        else:
            try:
                load_chat(UPLOAD_DIR, session_id, chat_id_value)
            except FileNotFoundError:
                chat_meta = create_chat(UPLOAD_DIR, session_id)
                chat_id_value = chat_meta["chat_id"]

        # === cấu hình truy vấn cân bằng chất lượng vs chi phí ===
        TOP_K = get_int("RETRIEVE_TOP_K", 10)
        CONTEXT_K = get_int("CONTEXT_K", 6)
        MMR_LAMBDA = get_float("MMR_LAMBDA", 0.6)
        RERANK_ON = get_bool("RERANK_ON", True)
        ENABLE_ANSWER_CACHE = get_bool("ENABLE_ANSWER_CACHE", True)
        HYBRID_ON = get_bool("HYBRID_ON", True)
        HYBRID_ALPHA = get_float("HYBRID_ALPHA", 0.5)
        MIN_CONTEXT_PROB = get_float("ANSWER_MIN_CONTEXT_PROB", 0.3)
        MIN_DIRECT_PROB = get_float("ANSWER_MIN_DIRECT_PROB", 0.2)

        # Recency boost configuration ← NEW
        RECENCY_WEIGHT = get_float("RECENCY_WEIGHT", 0.3)  # Default 30% weight
        RECENCY_MODE = os.getenv(
            "RECENCY_MODE", "exponential"
        )  # exponential | linear | step

        # Special config for summary queries
        is_summary_query = any(
            word in query.lower()
            for word in [
                "tóm tắt",
                "tổng kết",
                "summary",
                "summarize",
                "tóm tắt nội dung",
            ]
        )
        if is_summary_query:
            CONTEXT_K = max(CONTEXT_K, 12)  # Increase context for summaries

        # Chuẩn bị thông tin cho cache
        store = get_store(session_id=session_id)
        available_docs = store.list_docs()

        # 0) Kiểm tra answer cache trước
        if ENABLE_ANSWER_CACHE:
            cache_db = os.getenv("ANSWER_CACHE_DB", "./storage/answer_cache.sqlite")
            cached_result = get_cached(cache_db, query.strip(), available_docs)
            if cached_result:
                app_logger.info("Cache hit for query: %s...", query.strip()[:50])
                latency = int((time.time() - t0) * 1000)
                chat_after = append_exchange(
                    UPLOAD_DIR,
                    session_id,
                    chat_id_value,
                    query.strip(),
                    cached_result["answer"],
                    cached_result["citations"],
                    cached_result.get("confidence"),
                )
                chat_meta = {
                    "chat_id": chat_after["chat_id"],
                    "title": chat_after.get("title"),
                    "updated_at": chat_after.get("updated_at"),
                    "message_count": len(chat_after.get("messages", [])),
                }
                return {
                    "answer": cached_result["answer"],
                    "confidence": cached_result["confidence"],
                    "sources": cached_result["citations"],
                    "latency_ms": latency,
                    "cached": True,
                    "chat_id": chat_id_value,
                    "chat": chat_meta,
                    "format": "markdown",
                }
        # 1) Embed query
        app_logger.info("Embedding query...")
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

        # 3) Retrieve (hybrid hoặc vector-only) với recency boost ← UPDATED
        app_logger.info("Retrieving relevant passages...")
        if HYBRID_ON:
            app_logger.info("Using hybrid search (BM25 + Vector) with recency boost...")
            retrieved = hybrid_retrieve(
                query_vec=qvec,
                query_text=query.strip(),
                store=store,
                docs=list(allow_docs) if allow_docs else None,
                top_k=TOP_K,
                alpha=HYBRID_ALPHA,
                mmr_lambda=MMR_LAMBDA,
                recency_weight=RECENCY_WEIGHT,  # ← NEW
                recency_mode=RECENCY_MODE,  # ← NEW
            )
        else:
            app_logger.info("Using vector search only...")
            retrieved = store.search(qvec, top_k=TOP_K, mmr_lambda=MMR_LAMBDA)

        if allow_docs and not HYBRID_ON:
            retrieved = [c for c in retrieved if c.doc_name in allow_docs]

        # 4) (optional) Rerank
        app_logger.info("Reranking...")
        passages = (
            rerank(retrieved, query, top_k=min(CONTEXT_K, TOP_K))
            if RERANK_ON
            else retrieved[:CONTEXT_K]
        )

        seen_keys: set[tuple[str, int, int]] = set()
        qualified: list[Chunk] = []
        best_chunk: Chunk | None = None
        best_prob = 0.0
        for chunk in passages:
            key = (chunk.doc_name, chunk.page, chunk.chunk_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            prob = _chunk_probability(chunk)
            if prob > best_prob:
                best_prob = prob
                best_chunk = chunk
            if prob < MIN_CONTEXT_PROB:
                continue
            meta = dict(chunk.meta or {})
            meta["relevance"] = prob
            chunk.meta = meta
            qualified.append(chunk)

        # Special handling for summary queries: lower threshold or force include top chunks
        is_summary_query = any(
            word in query.lower()
            for word in [
                "tóm tắt",
                "tổng kết",
                "summary",
                "summarize",
                "tóm tắt nội dung",
            ]
        )
        if is_summary_query and not qualified and passages:
            # For summary queries, include top passages even if prob is low
            qualified = passages[:CONTEXT_K]
            for chunk in qualified:
                meta = dict(chunk.meta or {})
                meta["relevance"] = _chunk_probability(chunk)  # Recalculate if needed
                chunk.meta = meta

        if not qualified:
            if best_chunk and best_prob >= MIN_DIRECT_PROB:
                meta = dict(best_chunk.meta or {})
                meta["relevance"] = best_prob
                best_chunk.meta = meta
                qualified = [best_chunk]
            else:
                apology = (
                    "Xin lỗi, không tìm thấy thông tin phù hợp trong tài liệu hiện có."
                )
                latency = int((time.time() - t0) * 1000)
                chat_after = append_exchange(
                    UPLOAD_DIR,
                    session_id,
                    chat_id_value,
                    query.strip(),
                    apology,
                    [],
                    0.0,
                )
                chat_meta = {
                    "chat_id": chat_after["chat_id"],
                    "title": chat_after.get("title"),
                    "updated_at": chat_after.get("updated_at"),
                    "message_count": len(chat_after.get("messages", [])),
                }
                return {
                    "answer": apology,
                    "confidence": 0.0,
                    "sources": [],
                    "latency_ms": latency,
                    "chat_id": chat_id_value,
                    "chat": chat_meta,
                    "format": "markdown",
                }

        passages = sorted(
            qualified, key=lambda c: float(c.meta.get("relevance", 0.0)), reverse=True
        )[:CONTEXT_K]

        # 5) Generate
        app_logger.info("Generating answer...")
        answer, confidence = generate(query, passages)

        citation_pairs = _extract_citation_pairs(answer)
        passages_for_sources: list[Chunk] = []
        if citation_pairs:

            def _passage_matches(p: Chunk) -> bool:
                doc = p.doc_name
                page_str = str(p.page)
                return (
                    (doc, page_str) in citation_pairs
                    or (doc, None) in citation_pairs
                    or (doc, "") in citation_pairs
                )

            passages_for_sources = [p for p in passages if _passage_matches(p)]

        if not citation_pairs or not passages_for_sources:
            passages_for_sources = []

        sources = [
            {
                "filename": p.doc_name,
                "page": p.page,
                "score": float(p.score or 0.0),
                "relevance": float((p.meta or {}).get("relevance", 0.0)),
                "content": (p.text[:300] + "…") if len(p.text) > 320 else p.text,
                # Enhanced metadata ← NEW
                "upload_timestamp": p.upload_timestamp,
                "document_status": p.document_status,
                "document_version": p.document_version,
                "recency_score": (p.meta or {}).get("recency_score"),
            }
            for p in passages_for_sources
        ]

        latency = int((time.time() - t0) * 1000)
        app_logger.info("Query completed in %dms", latency)

        chat_after = append_exchange(
            UPLOAD_DIR,
            session_id,
            chat_id_value,
            query.strip(),
            answer,
            sources,
            confidence,
        )

        # Lưu vào cache nếu bật
        if ENABLE_ANSWER_CACHE:
            put_cached(
                cache_db, query.strip(), available_docs, answer, confidence, sources
            )

        chat_meta = {
            "chat_id": chat_after["chat_id"],
            "title": chat_after.get("title"),
            "updated_at": chat_after.get("updated_at"),
            "message_count": len(chat_after.get("messages", [])),
        }

        return {
            "answer": answer,
            "confidence": float(confidence),
            "sources": sources,
            "latency_ms": latency,
            "chat_id": chat_id_value,
            "chat": chat_meta,
            "format": "markdown",
        }
    except Exception as e:
        app_logger.exception("Error in /ask endpoint: %s", str(e))
        return JSONResponse(
            status_code=500, content={"error": f"Internal server error: {str(e)}"}
        )


@router.post("/session")
async def create_session(title: str | None = Form(None)):
    session_id = uuid.uuid4().hex
    session_folder = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_folder, exist_ok=True)
    manifest = {
        "session_id": session_id,
        "docs": [],
        "total_chunks": 0,
        "ts": int(time.time()),
        "ocr": False,
        "chunk_size": get_int("CHUNK_SIZE", 380),
        "chunk_overlap": get_int("CHUNK_OVERLAP", 50),
    }
    with open(os.path.join(session_folder, MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    chat_meta = create_chat(UPLOAD_DIR, session_id, title)
    summary = _session_summary(session_id)
    return {
        "session_id": session_id,
        "chat": chat_meta,
        "session": summary,
    }


@router.get("/sessions")
async def list_sessions():
    sessions = []
    if not os.path.isdir(UPLOAD_DIR):
        return {"sessions": sessions}
    for session_id in os.listdir(UPLOAD_DIR):
        folder = os.path.join(UPLOAD_DIR, session_id)
        if not os.path.isdir(folder):
            continue
        try:
            summary = _session_summary(session_id)
            sessions.append(summary)
        except Exception:
            continue
    sessions.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
    return {"sessions": sessions}


@router.post("/session/{session_id}/rename")
async def rename_session(
    session_id: str,
    title: str = Form(...),
    chat_id: str | None = Form(None),
):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    chats = list_chats(UPLOAD_DIR, session_id)
    if not chats:
        return JSONResponse(
            status_code=404,
            content={"error": "Session không có cuộc trò chuyện để đổi tên"},
        )
    target_chat_id = chat_id or chats[0]["chat_id"]
    try:
        rename_chat_entry(UPLOAD_DIR, session_id, target_chat_id, title)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Chat không tồn tại"})
    summary = _session_summary(session_id)
    return {"session": summary}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(folder):
        return JSONResponse(status_code=404, content={"error": "Session không tồn tại"})
    try:
        shutil.rmtree(folder)
        drop_store(session_id)
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Không thể xoá session: {str(e)}"}
        )
    return {"deleted": True}


@router.post("/chat/start")
async def start_chat(
    session_id: str = Form(...),
    title: str | None = Form(None),
):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    session_folder = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_folder, exist_ok=True)
    chat = create_chat(UPLOAD_DIR, session_id, title)
    chats = list_chats(UPLOAD_DIR, session_id)
    return {"chat": chat, "chats": chats}


@router.get("/chat/list")
async def chat_list(session_id: str):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    session_folder = os.path.join(UPLOAD_DIR, session_id)
    if not os.path.isdir(session_folder):
        return {"chats": []}
    return {"chats": list_chats(UPLOAD_DIR, session_id)}


@router.get("/chat/{chat_id}")
async def get_chat(chat_id: str, session_id: str):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    try:
        chat = load_chat(UPLOAD_DIR, session_id, chat_id)
        return {"chat": chat}
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Chat không tồn tại"})


@router.post("/chat/{chat_id}/rename")
async def rename_chat(
    chat_id: str, session_id: str = Form(...), title: str = Form(...)
):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    try:
        meta = rename_chat_entry(UPLOAD_DIR, session_id, chat_id, title)
        chats = list_chats(UPLOAD_DIR, session_id)
        return {"chat": meta, "chats": chats}
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Chat không tồn tại"})


@router.delete("/chat/{chat_id}")
async def remove_chat(chat_id: str, session_id: str):
    if not session_id or not session_id.strip():
        return JSONResponse(
            status_code=400, content={"error": "Session ID không hợp lệ"}
        )
    try:
        load_chat(UPLOAD_DIR, session_id, chat_id)
        delete_chat(UPLOAD_DIR, session_id, chat_id)
        chats = list_chats(UPLOAD_DIR, session_id)
        return {"chats": chats}
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Chat không tồn tại"})


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
    try:
        snapshot = _session_snapshot(session_id)
        return snapshot
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": "Session không tồn tại", "session_found": False},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Lỗi đọc session: {str(e)}", "session_found": False},
        )


@router.get("/ingest/job/{job_id}")
async def ingest_job_status(job_id: str):
    """Return status for a background ingest job created via /ingest?background=true"""
    try:
        from app.utils.ingest_jobs import get_job

        job = get_job(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"error": "Job không tồn tại"})
        return {
            "job_id": job.get("job_id"),
            "session_id": job.get("session_id"),
            "status": job.get("status"),
            "progress": int(job.get("progress") or 0),
            "result": job.get("result"),
            "ts_created": job.get("ts_created"),
            "ts_updated": job.get("ts_updated"),
        }
    except Exception as e:
        app_logger.exception("Error fetching ingest job status: %s", str(e))
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
