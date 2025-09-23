import time
from collections import defaultdict
from typing import Dict
from fastapi import HTTPException
from app.utils.logger import security_logger


class RateLimiter:
    """Rate limiter đơn giản dựa trên IP và endpoint"""

    def __init__(self):
        self.requests: Dict[str, list] = defaultdict(list)
        self.limits = {
            "/upload": (5, 60),  # 5 requests per minute
            "/ingest": (3, 300),  # 3 requests per 5 minutes
            "/ask": (30, 60),  # 30 requests per minute
        }

    def check_rate_limit(self, client_ip: str, endpoint: str) -> bool:
        """Kiểm tra rate limit cho IP và endpoint"""
        if endpoint not in self.limits:
            return True

        max_requests, window_seconds = self.limits[endpoint]
        key = f"{client_ip}:{endpoint}"
        now = time.time()

        # Xóa requests cũ
        self.requests[key] = [
            req_time
            for req_time in self.requests[key]
            if now - req_time < window_seconds
        ]

        # Kiểm tra limit
        if len(self.requests[key]) >= max_requests:
            security_logger.warning(
                f"Rate limit exceeded for {client_ip} on {endpoint}: "
                f"{len(self.requests[key])}/{max_requests} requests in {window_seconds}s"
            )
            return False

        # Thêm request hiện tại
        self.requests[key].append(now)
        return True


# Singleton instance
rate_limiter = RateLimiter()


def check_rate_limit(client_ip: str, endpoint: str):
    """Middleware function để check rate limit"""
    if not rate_limiter.check_rate_limit(client_ip, endpoint):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {endpoint}. Please try again later.",
        )
