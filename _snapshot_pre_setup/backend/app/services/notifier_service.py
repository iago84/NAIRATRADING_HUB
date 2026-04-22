from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from ..core.logger import get_logger
from ..core.metrics import metrics_singleton


@dataclass(frozen=True)
class NotifierConfig:
    telegram_bot_token: str
    telegram_chat_id: str
    webhook_urls: List[str]


def load_notifier_config() -> NotifierConfig:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    urls = os.getenv("WEBHOOK_URLS", "").strip()
    webhook_urls = [u.strip() for u in urls.split(",") if u.strip()]
    return NotifierConfig(telegram_bot_token=token, telegram_chat_id=chat, webhook_urls=webhook_urls)


class NotifierService:
    def __init__(self):
        self.logger = get_logger("notifier")
        self.cfg = load_notifier_config()
        self.client = httpx.Client(timeout=5.0)

    def reload(self) -> None:
        self.cfg = load_notifier_config()

    def notify(self, event_type: str, payload: Dict[str, Any]) -> None:
        metrics_singleton.rolling["notify_10m"].add()
        if self.cfg.telegram_bot_token and self.cfg.telegram_chat_id:
            try:
                self._send_telegram(event_type, payload)
            except Exception:
                metrics_singleton.rolling["errors_10m"].add()
        for url in list(self.cfg.webhook_urls):
            try:
                self.client.post(url, json={"type": event_type, "payload": payload})
            except Exception:
                metrics_singleton.rolling["errors_10m"].add()

    def _send_telegram(self, event_type: str, payload: Dict[str, Any]) -> None:
        text = self._format(event_type, payload)
        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        self.client.post(url, data={"chat_id": self.cfg.telegram_chat_id, "text": text})

    def _format(self, event_type: str, payload: Dict[str, Any]) -> str:
        if event_type == "alert":
            sym = payload.get("symbol")
            typ = payload.get("type")
            conf = payload.get("confidence")
            score = payload.get("score")
            return f"NAIRA ALERT {typ}\n{sym}\nconf={conf} score={score}"
        if event_type == "signal":
            sym = payload.get("symbol")
            d = payload.get("direction")
            conf = payload.get("confidence")
            price = payload.get("price")
            return f"NAIRA SIGNAL\n{sym} {d}\nconf={conf} price={price}"
        return f"NAIRA {event_type}\n{payload}"


notifier_singleton = NotifierService()
