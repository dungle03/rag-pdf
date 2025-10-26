"""
Quick Fix Script - Update timestamps for testing Recency Boost
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Config
DAYS_AGO_V1 = 30  # v1 = 30 days ago
DAYS_AGO_V2 = 0  # v2 = today


def get_timestamp(days_ago):
    """Calculate timestamp"""
    return (datetime.now() - timedelta(days=days_ago)).timestamp()


def find_sessions():
    """Find all sessions"""
    upload_dir = Path("uploads")
    if not upload_dir.exists():
        return []
    return [d for d in upload_dir.iterdir() if d.is_dir()]


def process_session(session_path):
    """Process one session"""
    manifest_file = session_path / "manifest.json"
    items_file = session_path / "items.jsonl"

    print(f"\n📁 Session: {session_path.name}")

    if not manifest_file.exists():
        print(f"  ❌ No manifest.json")
        return

    # Fix manifest
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    updated = 0
    for doc in manifest.get("docs", []):
        name = doc["doc"]
        if "v1" in name.lower() or "2024" in name:
            doc["upload_timestamp"] = get_timestamp(DAYS_AGO_V1)
            print(f"  ✅ {name}: {DAYS_AGO_V1} ngày trước")
            updated += 1
        elif "v2" in name.lower() or "2025" in name:
            doc["upload_timestamp"] = get_timestamp(DAYS_AGO_V2)
            print(f"  ✅ {name}: hôm nay")
            updated += 1

    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"  💾 Updated manifest.json ({updated} docs)")

    # Fix items.jsonl if exists
    if items_file.exists():
        items = []
        with open(items_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))

        items_updated = 0
        for item in items:
            # Get filename from metadata
            meta = item.get("meta", {})
            name = meta.get("filename", meta.get("doc", ""))

            if "v1" in name.lower() or "2024" in name:
                if "meta" in item:
                    item["meta"]["upload_timestamp"] = get_timestamp(DAYS_AGO_V1)
                    items_updated += 1
            elif "v2" in name.lower() or "2025" in name:
                if "meta" in item:
                    item["meta"]["upload_timestamp"] = get_timestamp(DAYS_AGO_V2)
                    items_updated += 1

        with open(items_file, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        print(f"  💾 Updated items.jsonl ({items_updated} items)")


def main():
    print("=" * 60)
    print("🔧 TIMESTAMP FIXER")
    print("=" * 60)

    sessions = find_sessions()

    if not sessions:
        print("\n❌ No sessions found in uploads/")
        sys.exit(1)

    print(f"\n✅ Found {len(sessions)} session(s)")

    for session_path in sessions:
        process_session(session_path)

    print("\n" + "=" * 60)
    print("✅ DONE!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Restart server")
    print("2. Hard refresh browser (Ctrl+Shift+R)")
    print("3. Query để test recency scores")


if __name__ == "__main__":
    main()
