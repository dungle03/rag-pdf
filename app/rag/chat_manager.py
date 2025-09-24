from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict, List, Optional

CHAT_DIR_NAME = "chats"


def _session_dir(base_upload_dir: str, session_id: str) -> str:
    return os.path.join(base_upload_dir, session_id)


def _chat_dir(base_upload_dir: str, session_id: str) -> str:
    folder = os.path.join(_session_dir(base_upload_dir, session_id), CHAT_DIR_NAME)
    os.makedirs(folder, exist_ok=True)
    return folder


def _chat_path(base_upload_dir: str, session_id: str, chat_id: str) -> str:
    return os.path.join(_chat_dir(base_upload_dir, session_id), f"{chat_id}.json")


def _default_title(index: int) -> str:
    return f"Cuộc trò chuyện {index}"


def create_chat(
    base_upload_dir: str, session_id: str, title: Optional[str] = None
) -> Dict:
    chats = list_chats(base_upload_dir, session_id)
    chat_id = uuid.uuid4().hex
    now = int(time.time())
    chat_title = title.strip() if title else _default_title(len(chats) + 1)

    data = {
        "chat_id": chat_id,
        "title": chat_title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }

    path = _chat_path(base_upload_dir, session_id, chat_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "chat_id": chat_id,
        "title": chat_title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


def list_chats(base_upload_dir: str, session_id: str) -> List[Dict]:
    folder = _chat_dir(base_upload_dir, session_id)
    chats: List[Dict] = []
    for fname in os.listdir(folder):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(folder, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chats.append(
                {
                    "chat_id": data.get("chat_id") or fname.split(".")[0],
                    "title": data.get("title", "Cuộc trò chuyện"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": len(data.get("messages", [])),
                }
            )
        except Exception:
            continue
    chats.sort(key=lambda c: c.get("updated_at") or 0, reverse=True)
    return chats


def load_chat(base_upload_dir: str, session_id: str, chat_id: str) -> Dict:
    path = _chat_path(base_upload_dir, session_id, chat_id)
    if not os.path.exists(path):
        raise FileNotFoundError("Chat không tồn tại")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # bảo đảm các field chính có mặt
    data.setdefault("chat_id", chat_id)
    data.setdefault("title", "Cuộc trò chuyện")
    data.setdefault("created_at", int(time.time()))
    data.setdefault("updated_at", int(time.time()))
    data.setdefault("messages", [])
    return data


def save_chat(base_upload_dir: str, session_id: str, chat: Dict) -> None:
    path = _chat_path(base_upload_dir, session_id, chat["chat_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chat, f, ensure_ascii=False, indent=2)


def append_exchange(
    base_upload_dir: str,
    session_id: str,
    chat_id: str,
    question: str,
    answer: str,
    sources: Optional[List[Dict]] = None,
    confidence: Optional[float] = None,
) -> Dict:
    chat = load_chat(base_upload_dir, session_id, chat_id)
    now = int(time.time())
    chat["messages"].append(
        {
            "role": "user",
            "content": question,
            "timestamp": now,
        }
    )
    chat["messages"].append(
        {
            "role": "assistant",
            "content": answer,
            "timestamp": now,
            "sources": sources or [],
            "confidence": confidence,
        }
    )
    if len(chat["messages"]) == 2 and question.strip():
        # cập nhật title bằng câu hỏi đầu tiên nếu title còn mặc định
        current_title = (chat.get("title") or "").strip().lower()
        if current_title.startswith("cuộc trò chuyện"):
            remainder = current_title[len("cuộc trò chuyện") :].strip()
            if remainder == "" or remainder.isdigit():
                chat["title"] = question.strip()[:60]
    chat["updated_at"] = now
    save_chat(base_upload_dir, session_id, chat)
    return chat


def rename_chat(
    base_upload_dir: str, session_id: str, chat_id: str, title: str
) -> Dict:
    chat = load_chat(base_upload_dir, session_id, chat_id)
    chat["title"] = title.strip() or chat.get("title") or "Cuộc trò chuyện"
    chat["updated_at"] = int(time.time())
    save_chat(base_upload_dir, session_id, chat)
    return {
        "chat_id": chat["chat_id"],
        "title": chat["title"],
        "updated_at": chat["updated_at"],
        "message_count": len(chat.get("messages", [])),
    }


def delete_chat(base_upload_dir: str, session_id: str, chat_id: str) -> None:
    path = _chat_path(base_upload_dir, session_id, chat_id)
    if os.path.exists(path):
        os.remove(path)
