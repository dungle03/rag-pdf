from __future__ import annotations
import hashlib

def sha1_text(text: str) -> str:
    if text is None:
        text = ""
    h = hashlib.sha1()
    h.update(text.encode("utf-8", errors="ignore"))
    return h.hexdigest()
