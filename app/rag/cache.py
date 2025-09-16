from __future__ import annotations
import os, sqlite3
from typing import Iterable, Dict, Tuple, List, Optional

import numpy as np

def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    con.execute("""
        CREATE TABLE IF NOT EXISTS embed_cache (
            k TEXT PRIMARY KEY,
            dim INTEGER NOT NULL,
            vec BLOB NOT NULL
        )
    """)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con

def fetch_many(db_path: str, keys: Iterable[str]) -> Dict[str, np.ndarray]:
    if not keys:
        return {}
    con = _connect(db_path)
    qmarks = ",".join("?" for _ in keys)
    cur = con.execute(f"SELECT k, dim, vec FROM embed_cache WHERE k IN ({qmarks})", list(keys))
    out: Dict[str, np.ndarray] = {}
    for k, dim, blob in cur.fetchall():
        arr = np.frombuffer(blob, dtype=np.float32)
        out[k] = arr.reshape(dim)
    con.close()
    return out

def upsert_many(db_path: str, items: List[Tuple[str, np.ndarray]]) -> None:
    if not items:
        return
    con = _connect(db_path)
    cur = con.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO embed_cache(k, dim, vec) VALUES (?,?,?)",
        [(k, v.shape[0], v.astype("float32").tobytes()) for k, v in items]
    )
    con.commit()
    con.close()
