import logging
import os
from datetime import datetime


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Cấu hình logger với format và level phù hợp"""

    # Tạo thư mục logs nếu chưa có
    os.makedirs("./logs", exist_ok=True)

    # Tạo logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Tránh duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # File handler
    file_handler = logging.FileHandler(
        f"./logs/rag_pdf_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Logger cho các module chính
app_logger = setup_logger("rag_pdf.app")
rag_logger = setup_logger("rag_pdf.rag")
security_logger = setup_logger("rag_pdf.security")
