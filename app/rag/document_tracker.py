# app/rag/document_tracker.py
"""
Smart Document Tracking với SimHash-based duplicate detection.
Phát hiện documents mới/cũ/updated và tự động quản lý versions.
"""

from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class DocumentFingerprint:
    """Lightweight representation của document để track versions"""

    filename: str
    file_hash: str  # SHA256 của raw file
    content_hash: str  # SHA256 của normalized text
    semantic_hash: str  # SimHash cho fuzzy matching
    upload_timestamp: float
    page_count: int
    chunk_count: int
    chunk_ids: List[str]  # IDs của chunks thuộc doc này
    status: str = "active"  # "active" | "superseded" | "archived"
    version: int = 1
    supersedes: List[str] = None  # List of doc_ids bị thay thế
    superseded_by: Optional[str] = None

    def __post_init__(self):
        if self.supersedes is None:
            self.supersedes = []

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> DocumentFingerprint:
        return cls(**data)


class SmartDocumentTracker:
    """
    Intelligent document tracking với:
    - O(n) duplicate detection
    - SimHash-based fuzzy matching
    - Automatic version management
    """

    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        self.fingerprints_path = os.path.join(session_dir, "document_fingerprints.json")
        # {doc_id: [DocumentFingerprint, ...]} - Multiple versions per filename
        self.fingerprints: Dict[str, List[DocumentFingerprint]] = {}
        self._load_fingerprints()

    def _load_fingerprints(self):
        """Load fingerprints từ disk"""
        if not os.path.exists(self.fingerprints_path):
            self.fingerprints = {}
            return

        try:
            with open(self.fingerprints_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.fingerprints = {}
            for doc_id, fp_list in data.items():
                self.fingerprints[doc_id] = [
                    DocumentFingerprint.from_dict(fp) for fp in fp_list
                ]
        except Exception as e:
            print(f"⚠️  Lỗi load fingerprints: {e}")
            self.fingerprints = {}

    def _save_fingerprints(self):
        """Save fingerprints ra disk"""
        try:
            os.makedirs(self.session_dir, exist_ok=True)

            data = {}
            for doc_id, fp_list in self.fingerprints.items():
                data[doc_id] = [fp.to_dict() for fp in fp_list]

            with open(self.fingerprints_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  Lỗi save fingerprints: {e}")

    def compute_semantic_hash(self, text: str, hash_bits: int = 128) -> str:
        """
        SimHash algorithm - cho phép fuzzy matching.
        Documents tương tự 90%+ sẽ có hash gần giống nhau.

        Args:
            text: Full document text
            hash_bits: Number of bits (default 128)

        Returns:
            Hex string representation of SimHash
        """
        # Normalize text
        text = text.lower().strip()
        if not text:
            return "0" * 32

        # Tokenize
        tokens = text.split()
        if not tokens:
            return "0" * 32

        # Initialize vector
        vector = np.zeros(hash_bits, dtype=np.float32)

        # Hash each token and accumulate
        for token in tokens:
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)

            # Convert to binary vector
            for i in range(hash_bits):
                if token_hash & (1 << i):
                    vector[i] += 1.0
                else:
                    vector[i] -= 1.0

        # Convert to binary hash
        simhash = 0
        for i in range(hash_bits):
            if vector[i] > 0:
                simhash |= 1 << i

        # Return as hex string (32 chars for 128 bits)
        return format(simhash, "032x")

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """Tính khoảng cách Hamming giữa 2 SimHash"""
        try:
            x = int(hash1, 16) ^ int(hash2, 16)
            return bin(x).count("1")
        except:
            return 128  # Max distance

    def find_similar_document(
        self,
        semantic_hash: str,
        threshold: int = 10,  # Hamming distance threshold (out of 128 bits)
    ) -> Tuple[Optional[DocumentFingerprint], float]:
        """
        Tìm document tương tự nhất trong O(n) time.

        Args:
            semantic_hash: SimHash của document cần tìm
            threshold: Max Hamming distance để coi là similar

        Returns:
            (matched_fingerprint, similarity_score)
            similarity_score: 0.0-1.0, where 1.0 = identical
        """
        best_match = None
        best_distance = float("inf")

        for versions in self.fingerprints.values():
            for fp in versions:
                distance = self.hamming_distance(semantic_hash, fp.semantic_hash)
                if distance < best_distance:
                    best_distance = distance
                    best_match = fp

        if best_distance <= threshold:
            similarity = 1.0 - (best_distance / 128.0)  # Normalize to [0,1]
            return best_match, similarity

        return None, 0.0

    def register_document(
        self,
        filename: str,
        raw_content: bytes,
        normalized_text: str,
        pages: List[Tuple[int, str]],
        chunk_ids: List[str],
    ) -> Tuple[str, str, Optional[DocumentFingerprint]]:
        """
        Đăng ký document mới và detect duplicates/updates.

        Args:
            filename: Tên file PDF
            raw_content: Raw bytes của file
            normalized_text: Full text sau khi normalize
            pages: List of (page_num, text)
            chunk_ids: List of chunk IDs

        Returns:
            (status, message, superseded_doc)

            status: "new" | "duplicate" | "updated" | "version"
            message: Human-readable description
            superseded_doc: Document cũ bị thay thế (if any)
        """
        # Compute hashes
        file_hash = hashlib.sha256(raw_content).hexdigest()
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        semantic_hash = self.compute_semantic_hash(normalized_text)

        # Generate doc_id: filename without extension
        base_name = os.path.splitext(filename)[0]
        doc_id = base_name

        # Check exact duplicate (same file hash)
        if doc_id in self.fingerprints:
            for fp in self.fingerprints[doc_id]:
                if fp.file_hash == file_hash:
                    return (
                        "duplicate",
                        f"File '{filename}' đã tồn tại với nội dung giống hệt",
                        fp,
                    )

        # Check semantic similarity
        similar_doc, similarity = self.find_similar_document(semantic_hash)

        # Create new fingerprint
        upload_timestamp = datetime.now().timestamp()
        version = len(self.fingerprints.get(doc_id, [])) + 1

        new_fp = DocumentFingerprint(
            filename=filename,
            file_hash=file_hash,
            content_hash=content_hash,
            semantic_hash=semantic_hash,
            upload_timestamp=upload_timestamp,
            page_count=len(pages),
            chunk_count=len(chunk_ids),
            chunk_ids=chunk_ids,
            status="active",
            version=version,
            supersedes=[],
            superseded_by=None,
        )

        # Determine status based on similarity
        status = "new"
        message = f"Document hoàn toàn mới: {filename}"
        superseded_doc = None

        if similar_doc and similarity > 0.95:
            # Rất giống → có thể là version mới
            if (
                similar_doc.filename == filename
                or os.path.splitext(similar_doc.filename)[0]
                == os.path.splitext(filename)[0]
            ):
                status = "version"
                message = f"Phát hiện version mới của '{filename}' (similarity: {similarity:.1%})"
                superseded_doc = similar_doc

                # Mark old version as superseded
                similar_doc.status = "superseded"
                similar_doc.superseded_by = doc_id
                new_fp.supersedes = [similar_doc.filename]
            else:
                status = "duplicate"
                message = (
                    f"Nội dung tương tự '{similar_doc.filename}' ({similarity:.1%})"
                )

        elif similar_doc and similarity > 0.80:
            # Tương đối giống → có thay đổi
            status = "updated"
            message = (
                f"Nội dung được cập nhật từ '{similar_doc.filename}' ({similarity:.1%})"
            )
            superseded_doc = similar_doc

            # Mark old version as superseded
            similar_doc.status = "superseded"
            similar_doc.superseded_by = doc_id
            new_fp.supersedes = [similar_doc.filename]

        # Save fingerprint
        if doc_id not in self.fingerprints:
            self.fingerprints[doc_id] = []
        self.fingerprints[doc_id].append(new_fp)

        self._save_fingerprints()

        return status, message, superseded_doc

    def get_document_metadata(self, filename: str) -> Optional[DocumentFingerprint]:
        """Lấy metadata của document (active version)"""
        doc_id = os.path.splitext(filename)[0]
        if doc_id not in self.fingerprints:
            return None

        # Return newest active version
        for fp in reversed(self.fingerprints[doc_id]):
            if fp.status == "active":
                return fp

        # Fallback: return newest regardless of status
        return self.fingerprints[doc_id][-1] if self.fingerprints[doc_id] else None

    def get_all_documents(self) -> List[DocumentFingerprint]:
        """Lấy tất cả documents (all versions)"""
        all_docs = []
        for versions in self.fingerprints.values():
            all_docs.extend(versions)
        return all_docs

    def get_active_documents(self) -> List[DocumentFingerprint]:
        """Chỉ lấy documents có status='active'"""
        active = []
        for versions in self.fingerprints.values():
            for fp in versions:
                if fp.status == "active":
                    active.append(fp)
        return active

    def compute_recency_score(
        self, timestamp: float, mode: str = "exponential", half_life_days: float = 30.0
    ) -> float:
        """
        Compute recency score dựa trên upload timestamp.

        Args:
            timestamp: Upload timestamp (Unix seconds)
            mode: "exponential" | "linear" | "step"
            half_life_days: Số ngày để score giảm còn 50% (cho exponential mode)

        Returns:
            Score từ 0.0-1.0 (1.0 = very recent)
        """
        now = datetime.now().timestamp()
        age_days = (now - timestamp) / 86400.0

        if mode == "exponential":
            # Exponential decay: score = e^(-age/τ)
            decay = np.exp(-age_days / half_life_days)
            return float(np.clip(decay, 0.0, 1.0))

        elif mode == "linear":
            # Linear decay over max_age_days
            max_age = half_life_days * 3  # 90 days default
            if age_days >= max_age:
                return 0.0
            return float(1.0 - (age_days / max_age))

        elif mode == "step":
            # Step function với thresholds
            if age_days <= 7:
                return 1.0
            elif age_days <= 30:
                return 0.8
            elif age_days <= 90:
                return 0.5
            elif age_days <= 365:
                return 0.2
            else:
                return 0.05

        else:
            return 1.0  # No decay

    def get_statistics(self) -> Dict:
        """Lấy thống kê về documents"""
        all_docs = self.get_all_documents()
        active_docs = self.get_active_documents()

        return {
            "total_documents": len(all_docs),
            "active_documents": len(active_docs),
            "superseded_documents": len(
                [d for d in all_docs if d.status == "superseded"]
            ),
            "archived_documents": len([d for d in all_docs if d.status == "archived"]),
            "total_chunks": sum(d.chunk_count for d in active_docs),
            "unique_filenames": len(self.fingerprints),
        }
