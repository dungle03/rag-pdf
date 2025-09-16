# app/rag/pdf_loader.py
from __future__ import annotations
from typing import List, Tuple
import os
import re

import pypdfium2 as pdfium
from PIL import Image

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    # ưu tiên biến môi trường trỏ tới tesseract.exe (Windows)
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")
except Exception:
    TESSERACT_AVAILABLE = False

TextPage = Tuple[int, str]  # (page_number, text)

_WS_RE = re.compile(r"\s+")
def _normalize_ws(s: str) -> str:
    return _WS_RE.sub(" ", s or "").strip()

def _detect_repeated(lines_per_page: list[list[str]], position: str, min_repeat: int = 3) -> set[str]:
    bag: dict[str, int] = {}
    for lines in lines_per_page:
        if not lines:
            continue
        pick = lines[0] if position == "head" else lines[-1]
        key = _normalize_ws(pick)[:120]
        if key:
            bag[key] = bag.get(key, 0) + 1
    return {k for k, c in bag.items() if c >= min_repeat}

def _extract_text_pdfium(doc: pdfium.PdfDocument) -> list[str]:
    out: list[str] = []
    for page in doc:
        tp = page.get_textpage()
        # pypdfium2 khuyến cáo dùng get_text_bounded cho default args
        txt = tp.get_text_bounded() or ""
        out.append(txt)
    return out

def _ocr_page(page: pdfium.PdfPage, scale: float = 2.0, lang: str = "vie+eng") -> str:
    if not TESSERACT_AVAILABLE:
        return ""
    # render bitmap rồi chuyển PIL để OCR
    bitmap = page.render(scale=scale).to_pil()
    if not isinstance(bitmap, Image.Image):
        bitmap = Image.fromarray(bitmap)
    text = pytesseract.image_to_string(bitmap, lang=lang)
    return text or ""

def load_pdf(path: str, ocr: bool = False, ocr_lang: str = "vie+eng") -> List[TextPage]:
    """
    Trả về danh sách (page_number, text) đã loại header/footer lặp.
    - Nếu `ocr=False`: chỉ trích text layer.
    - Nếu `ocr=True`: trang nào không có text sẽ OCR; hoặc OCR toàn bộ nếu muốn.
    """
    doc = pdfium.PdfDocument(path)

    # 1) lấy text layer trước
    raw_texts = _extract_text_pdfium(doc)

    # 2) OCR fallback (khi bật ocr=True hoặc trang rỗng)
    if ocr and not TESSERACT_AVAILABLE:
        # cảnh báo mềm (không raise để app tiếp tục chạy)
        print("⚠️  OCR được bật nhưng pytesseract/tesseract chưa sẵn sàng. Bỏ qua OCR.")

    if ocr or any(_normalize_ws(t) == "" for t in raw_texts):
        for i, page in enumerate(doc):
            if not ocr and _normalize_ws(raw_texts[i]) != "":
                continue  # đã có text, không OCR
            if TESSERACT_AVAILABLE:
                try:
                    ocr_txt = _ocr_page(page, scale=2.0, lang=ocr_lang)
                    raw_texts[i] = ocr_txt or raw_texts[i]
                except Exception as e:
                    # không chặn pipeline
                    print(f"⚠️  OCR lỗi ở trang {i+1}: {e}")

    # 3) loại header/footer lặp & normalize
    lines_per_page = [[ln for ln in (pg.splitlines() or []) if ln.strip()] for pg in raw_texts]
    heads = _detect_repeated(lines_per_page, "head")
    tails = _detect_repeated(lines_per_page, "tail")

    cleaned_pages: List[TextPage] = []
    for idx, lines in enumerate(lines_per_page, start=1):
        if not lines:
            cleaned_pages.append((idx, ""))
            continue
        if lines and _normalize_ws(lines[0])[:120] in heads:
            lines = lines[1:]
        if lines and _normalize_ws(lines[-1])[:120] in tails:
            lines = lines[:-1]
        text = _normalize_ws(" ".join(lines))
        cleaned_pages.append((idx, text))
    return cleaned_pages
