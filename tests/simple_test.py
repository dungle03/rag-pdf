#!/usr/bin/env python3
"""
Simple test script cho RAG PDF system
"""

import os
import sys
import json
import time
import uuid
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"

def simple_test():
    """Chạy test đơn giản"""
    
    print("=== RAG PDF Simple Test ===")
    
    # 1. Health check
    try:
        response = requests.get(f"{BASE_URL}/healthz", timeout=5)
        if response.status_code != 200:
            print("❌ Server không chạy! Start server trước:")
            print("   uvicorn app.main:app --reload")
            return False
    except:
        print("❌ Không thể kết nối server!")
        return False
    
    print("✅ Server đang chạy")
    
    # 2. Upload file test
    test_file = Path("uploads/viettelpay_guide.pdf")
    if not test_file.exists():
        print(f"❌ Không tìm thấy file test: {test_file}")
        print("Hãy copy file PDF vào thư mục uploads/")
        return False
    
    session_id = "test-" + str(uuid.uuid4())[:8]
    
    try:
        with open(test_file, 'rb') as f:
            files = {'files': f}
            data = {'session_id': session_id}
            response = requests.post(f"{BASE_URL}/upload", files=files, data=data, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Upload failed: {response.text}")
            return False
        
        print("✅ Upload thành công")
        
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return False
    
    # 3. Ingest
    try:
        data = {'session_id': session_id, 'ocr': 'false'}
        response = requests.post(f"{BASE_URL}/ingest", data=data, timeout=300)
        
        if response.status_code != 200:
            print(f"❌ Ingest failed: {response.text}")
            return False
        
        result = response.json()
        print(f"✅ Ingest thành công: {result['total_chunks']} chunks")
        
    except Exception as e:
        print(f"❌ Ingest error: {e}")
        return False
    
    # 4. Test queries từ eval_cases.json
    cases_file = Path("tests/eval_cases.json")
    if not cases_file.exists():
        print("❌ Không tìm thấy file test cases")
        return False
    
    with open(cases_file, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
    
    print(f"\n=== Testing {len(test_cases)} queries ===")
    
    passed = 0
    total_time = 0
    
    for i, case in enumerate(test_cases, 1):
        query = case['q']
        expected_keywords = case['expected']
        
        print(f"\n[{i}/{len(test_cases)}] {query}")
        
        try:
            data = {'query': query, 'session_id': session_id}
            start_time = time.time()
            response = requests.post(f"{BASE_URL}/ask", data=data, timeout=60)
            elapsed = (time.time() - start_time) * 1000
            total_time += elapsed
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('answer', '').lower()
                confidence = result.get('confidence', 0)
                
                # Check if any expected keyword is in answer
                found = any(keyword.lower() in answer for keyword in expected_keywords)
                
                if found:
                    print(f"✅ PASS ({elapsed:.1f}ms) - Confidence: {confidence:.3f}")
                    passed += 1
                else:
                    print(f"❌ FAIL ({elapsed:.1f}ms) - Không tìm thấy từ khóa mong đợi")
                    print(f"   Answer: {answer[:100]}...")
            else:
                print(f"❌ Query failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Query error: {e}")
    
    # 5. Kết quả
    accuracy = (passed / len(test_cases)) * 100
    avg_time = total_time / len(test_cases)
    
    print(f"\n=== KẾT QUẢ TEST ===")
    print(f"Accuracy: {accuracy:.1f}% ({passed}/{len(test_cases)})")
    print(f"Avg Latency: {avg_time:.1f}ms")
    print(f"Session: {session_id}")
    
    if accuracy >= 60:
        print("🎉 TEST PASS!")
        return True
    else:
        print("❌ TEST FAIL - Cần cải thiện accuracy")
        return False

if __name__ == "__main__":
    success = simple_test()
    sys.exit(0 if success else 1)
