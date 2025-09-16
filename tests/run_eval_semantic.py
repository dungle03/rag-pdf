import os, json, time, requests, re, unicodedata
from typing import List
from rapidfuzz.fuzz import token_set_ratio
from sentence_transformers import SentenceTransformer, util

URL = os.getenv("APP_URL", "http://127.0.0.1:8000/ask")
THRESH = float(os.getenv("EVAL_THRESH", "0.62"))  # ngưỡng pass cho mỗi nhóm

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "M")  # bỏ dấu
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

# --- load cases ---
with open("tests/eval_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

# --- load model (1 lần) ---
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def score_pair(ans: str, cand: str) -> float:
    """Trả điểm 0..1 giữa câu trả lời và 1 từ/nhóm kỳ vọng."""
    # 1) fuzzy lexical (ổn định khi cụm ngắn)
    fuzzy = token_set_ratio(ans, cand) / 100.0
    # 2) semantic cosine
    e1 = model.encode(ans, normalize_embeddings=True)
    e2 = model.encode(cand, normalize_embeddings=True)
    cos = float(util.cos_sim(e1, e2).item())  # [-1,1]
    cos01 = (cos + 1) / 2  # về [0,1]
    return max(fuzzy, cos01)

def group_pass(ans: str, group: List[str]) -> float:
    """Một nhóm OR pass nếu có ít nhất 1 phần tử đạt điểm >= THRESH.
    Trả về best score của nhóm (để log)."""
    scores = [score_pair(ans, c) for c in group]
    best = max(scores) if scores else 0.0
    return best

# --- run ---
results = []
for case in cases:
    q = case["q"]
    t0 = time.time()
    r = requests.post(URL, data={"query": q}, timeout=120)
    dt = (time.time() - t0) * 1000
    if r.status_code != 200:
        print(f"[HTTP {r.status_code}] {r.text}")
        continue
    data = r.json()
    answer = (data.get("answer") or "").strip()
    ans_n = normalize(answer)

    groups = case.get("expect_groups") or []
    group_scores = [group_pass(ans_n, [normalize(x) for x in g]) for g in groups]
    ok = all(s >= THRESH for s in group_scores)

    results.append({
        "q": q,
        "answer": answer,
        "latency": dt,
        "ok": ok,
        "scores": [round(s,3) for s in group_scores]
    })

# --- report ---
if results:
    acc = sum(1 for r in results if r["ok"]) / len(results)
    avg_lat = sum(r["latency"] for r in results) / len(results)
    print(f"\n=== Semantic Evaluation Report ===")
    print(f"Accuracy: {acc*100:.1f}% | Avg latency: {avg_lat:.1f} ms | THRESH={THRESH}")
    for r in results:
        print(f"- Q: {r['q']} | OK={r['ok']} | scores={r['scores']} | {r['latency']:.1f} ms")
        print(f"  Ans: {r['answer'][:140]}...")
else:
    print("Không có test nào (HTTP != 200).")
