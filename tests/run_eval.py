import os, json, time, requests, re, unicodedata

URL = os.getenv("APP_URL", "http://127.0.0.1:8000/ask")

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "M")  # bỏ dấu
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

with open("tests/eval_cases.json", encoding="utf-8") as f:
    cases = json.load(f)

results = []
for case in cases:
    q = case["q"]
    t0 = time.time()
    r = requests.post(URL, data={"query": q}, timeout=120)
    elapsed = (time.time()-t0)*1000
    if r.status_code != 200:
        print(f"[HTTP {r.status_code}] {r.text}")
        continue
    data = r.json()
    answer = data.get("answer","")
    ans_n = normalize(answer)

    # --- chấm điểm ---
    groups = case.get("expect_groups") or []
    ok = True
    for g in groups:
        g_match = any(normalize(kw) in ans_n for kw in g)
        if not g_match:
            ok = False
            break

    results.append({"q": q, "answer": answer, "latency": elapsed, "ok": ok})

if results:
    acc = sum(1 for r in results if r["ok"])/len(results)
    print(f"\n=== Evaluation Report ===\nAccuracy: {acc*100:.1f}%")
    print(f"Avg latency: {sum(r['latency'] for r in results)/len(results):.1f} ms")
    for r in results:
        print(f"- Q: {r['q']} | OK={r['ok']} | {r['latency']:.1f} ms\n  Ans: {r['answer'][:120]}...")
else:
    print("Không có test nào thành công (HTTP != 200).")
