from __future__ import annotations
import os, sqlite3, json, time
from typing import Optional

def _conn(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.execute("""
      CREATE TABLE IF NOT EXISTS answer_cache(
        k TEXT PRIMARY KEY,
        answer TEXT NOT NULL,
        confidence REAL,
        citations TEXT,
        ts INTEGER
      )
    """)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def _key(question: str, docset: list[str]) -> str:
    norm_q = " ".join(question.strip().split()).lower()
    norm_docs = ",".join(sorted(set(docset)))
    return f"{norm_q}||{norm_docs}"

def get_cached(db_path: str, question: str, docset: list[str]) -> Optional[dict]:
    con = _conn(db_path)
    k = _key(question, docset)
    cur = con.execute("SELECT answer, confidence, citations, ts FROM answer_cache WHERE k=?", (k,))
    row = cur.fetchone()
    con.close()
    if not row: return None
    answer, conf, cites_json, ts = row
    return {"answer": answer, "confidence": conf, "citations": json.loads(cites_json or "[]"), "ts": ts}

def put_cached(db_path: str, question: str, docset: list[str], answer: str, confidence: float, citations: list[dict]) -> None:
    con = _conn(db_path)
    k = _key(question, docset)
    con.execute(
      "INSERT OR REPLACE INTO answer_cache(k, answer, confidence, citations, ts) VALUES (?,?,?,?,?)",
      (k, answer, confidence, json.dumps(citations, ensure_ascii=False), int(time.time()))
    )
    con.commit(); con.close()
