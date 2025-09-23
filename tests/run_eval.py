#!/usr/bin/env python3
"""
Simple evaluation script for RAG PDF
"""

import os
import sys
import json
import time
import uuid
import requests
from pathlib import Path


def run_evaluation():
    """Run simple evaluation"""

    BASE_URL = "http://127.0.0.1:8000"
    session_id = os.getenv("TEST_SESSION_ID", f"test-{uuid.uuid4().hex[:8]}")

    print(f"Starting evaluation with session: {session_id}")

    # Load test cases
    cases_file = Path("tests/eval_cases.json")
    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    passed = 0

    for i, case in enumerate(cases, 1):
        query = case["q"]
        expected = case["expected"]

        print(f"[{i}/{len(cases)}] Testing: {query[:50]}...")

        try:
            data = {"query": query, "session_id": session_id}
            start = time.time()
            response = requests.post(f"{BASE_URL}/ask", data=data, timeout=60)
            elapsed = (time.time() - start) * 1000

            if response.status_code == 200:
                result = response.json()
                answer = result.get("answer", "").lower()
                confidence = result.get("confidence", 0)

                # Simple keyword matching
                found = any(kw.lower() in answer for kw in expected)

                if found:
                    print(f"✅ PASS | {elapsed:.1f}ms | Confidence: {confidence:.3f}")
                    passed += 1
                    status = "PASS"
                else:
                    print(f"❌ FAIL | {elapsed:.1f}ms | No expected keywords found")
                    status = "FAIL"

                results.append(
                    {
                        "query": query,
                        "answer": answer,
                        "confidence": confidence,
                        "latency_ms": elapsed,
                        "status": status,
                        "expected": expected,
                    }
                )
            else:
                print(f"❌ API Error: {response.status_code}")

        except Exception as e:
            print(f"❌ Error: {e}")

    # Report
    accuracy = (passed / len(cases)) * 100
    avg_latency = sum(r["latency_ms"] for r in results) / len(results) if results else 0

    print(f"\n=== EVALUATION REPORT ===")
    print(f"Session: {session_id}")
    print(f"Accuracy: {accuracy:.1f}% ({passed}/{len(cases)})")
    print(f"Avg Latency: {avg_latency:.1f}ms")

    if accuracy >= 60:
        print("🎉 EVALUATION PASS")
    else:
        print("❌ EVALUATION FAIL")

    return {
        "session_id": session_id,
        "accuracy": accuracy,
        "passed": passed,
        "total": len(cases),
        "avg_latency_ms": avg_latency,
        "results": results,
    }


if __name__ == "__main__":
    eval_data = run_evaluation()
    sys.exit(0 if eval_data["accuracy"] >= 60 else 1)
