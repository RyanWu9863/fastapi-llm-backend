import json
import logging


class JsonFormatter(logging.Formatter):
    """每筆 log 輸出成一行 JSON：log 收集系統（ELK、CloudWatch 等）可以直接依欄位搜尋、統計。"""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            # 呼叫端用 logger.info("事件", extra={"fields": {...}}) 帶入結構化欄位
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup_logging() -> None:
    """設定 "app" logger；app.xxx 模組用 logging.getLogger(__name__) 都會套用這個格式。"""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app")
    logger.handlers = [handler]  # 重複呼叫也不會疊加 handler
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 不再往上傳給 root logger，避免同一筆印兩次
