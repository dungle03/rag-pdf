"""Simple metrics collector (PoC) - prints cache DB stats and counts.
Usage: python scripts/collect_metrics.py
"""

import sqlite3
import os

ANSWER_DB = os.getenv("ANSWER_CACHE_DB", "./storage/answer_cache.sqlite")
EMBED_DB = os.getenv("EMBED_CACHE_DB", "./storage/embed_cache.sqlite")


def print_answer_cache_stats(path):
    if not os.path.exists(path):
        print("Answer cache DB not found:", path)
        return
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM answers")
            total = cur.fetchone()[0]
            print(f"Answer cache entries: {total}")
    except Exception as e:
        print("Error reading answer cache:", e)


def print_embed_cache_stats(path):
    if not os.path.exists(path):
        print("Embed cache DB not found:", path)
        return
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM embeddings")
            total = cur.fetchone()[0]
            print(f"Embed cache entries: {total}")
    except Exception as e:
        print("Error reading embed cache:", e)


if __name__ == "__main__":
    print("Metrics PoC")
    print_answer_cache_stats(ANSWER_DB)
    print_embed_cache_stats(EMBED_DB)
