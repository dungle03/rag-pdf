from __future__ import annotations
import os

def get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def get_bool(name: str, default: bool=False) -> bool:
    val = os.getenv(name, "")
    if not val:
        return default
    return val.strip().lower() in {"1","true","yes","on"}
