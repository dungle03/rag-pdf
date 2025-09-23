from __future__ import annotations
import os, re
from fastapi import UploadFile

MAX_FILES = int(os.getenv("MAX_FILES", 5))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", 10))


def is_pdf(file: UploadFile) -> bool:
    # Một số trình duyệt gửi 'application/pdf', số khác có thể là 'application/octet-stream'.
    # Nới lỏng: nếu content-type chứa 'pdf' hoặc tên file .pdf.
    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    return ("pdf" in ct) or name.endswith(".pdf")


_SAFE = re.compile(r"[^a-zA-Z0-9_\-\.]+")


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name)
    return _SAFE.sub("_", base)


async def read_and_check_size(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise ValueError(f"File vượt quá {MAX_FILE_MB} MB")
    return data


def looks_like_pdf_bytes(b: bytes) -> bool:
    """Kiểm tra nhanh chữ ký PDF trong vài KB đầu (tìm '%PDF')."""
    if not b:
        return False
    head = b[:4096]
    # Cho phép BOM/whitespace trước ký hiệu
    return b"%PDF" in head
