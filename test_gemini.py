# test_gemini.py
import os, google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("Missing GEMINI_API_KEY env var")

genai.configure(api_key=API_KEY)

# 1) Test embeddings
emb = genai.embed_content(
    model="text-embedding-004",
    content="Xin chào, đây là bài test embeddings."
)
vec = emb["embedding"]
print(f"[Embeddings] OK. Vector dim = {len(vec)} (ví dụ 768/1024 tùy model).")

# 2) Test LLM generate
model = genai.GenerativeModel("gemini-1.5-flash")
resp = model.generate_content("Hãy trả lời một câu bất kỳ bằng tiếng Việt, tối đa 15 từ.")
print("[LLM] OK. Mẫu phản hồi:", (resp.text or "").strip()[:120])
