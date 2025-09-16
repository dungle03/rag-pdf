from app.rag.pdf_loader import load_pdf
from app.rag.chunking import chunk_pages

pdf_path = r".\uploads\tb741.pdf"  # đổi đường dẫn PDF
pages = load_pdf(pdf_path, ocr=True, ocr_lang="vie+eng")
print(f"Pages: {len(pages)}")

chunks = chunk_pages(pages, doc_name="tb741.pdf", chunk_size=400, overlap=50)
print(f"Chunks: {len(chunks)}")

if chunks:
    print("Example chunk:", chunks[0].dict() | {"text": chunks[0].text[:120] + "..."})
else:
    print("⚠️ Không trích được text dù đã OCR. Hãy kiểm tra Tesseract đã cài và ngôn ngữ 'vie' có sẵn chưa.")
