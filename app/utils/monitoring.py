import functools
import traceback
from typing import Callable, Any
from fastapi import HTTPException
from app.utils.logger import app_logger


def handle_exceptions(func: Callable) -> Callable:
    """Decorator để handle exceptions một cách nhất quán"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Re-raise HTTPException (đã được handle)
            raise
        except ValueError as e:
            app_logger.error(f"Validation error in {func.__name__}: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError as e:
            app_logger.error(f"File not found in {func.__name__}: {str(e)}")
            raise HTTPException(status_code=404, detail="Requested resource not found")
        except PermissionError as e:
            app_logger.error(f"Permission error in {func.__name__}: {str(e)}")
            raise HTTPException(status_code=403, detail="Permission denied")
        except Exception as e:
            app_logger.error(
                f"Unexpected error in {func.__name__}: {str(e)}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            raise HTTPException(
                status_code=500, detail="Internal server error. Please try again later."
            )

    return wrapper


class MetricsCollector:
    """Thu thập metrics đơn giản"""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.response_times = []

    def record_request(self, endpoint: str, response_time: float, success: bool = True):
        self.request_count += 1
        self.response_times.append(response_time)

        if not success:
            self.error_count += 1

        app_logger.info(
            f"Request: {endpoint} | "
            f"Response time: {response_time:.2f}ms | "
            f"Success: {success}"
        )

    def get_stats(self) -> dict:
        if not self.response_times:
            return {"request_count": 0, "error_count": 0, "avg_response_time": 0}

        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / self.request_count,
            "avg_response_time": sum(self.response_times) / len(self.response_times),
            "max_response_time": max(self.response_times),
            "min_response_time": min(self.response_times),
        }


# Singleton metrics collector
metrics = MetricsCollector()
