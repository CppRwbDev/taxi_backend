import logging
import logging.handlers
import os
from app.config import settings


def setup_logging():
    """
    Loglash tizimini sozlash:
    - Console ga chiqadi (har doim)
    - Faylga yoziladi (rotating, har 10 MB yangi fayl)
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Log papkasini yaratish
    log_dir = os.path.dirname(settings.LOG_FILE_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 1. Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. File handler (rotating — max 10 MB, 5 ta backup)
    file_handler = logging.handlers.RotatingFileHandler(
        settings.LOG_FILE_PATH,
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Uvicorn loglarini ham o'sha formatterga ulash
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
