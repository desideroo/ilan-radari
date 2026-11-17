"""Kalıcı durum: görülen ilanlar, kaynak sağlığı, Telegram offset'i.

Dosya `state/state.json` olarak ayrı `state` branch'inde tutulur (workflow commit eder).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import config

DEFAULT = {
    "version": 1,
    "created": None,
    "seen": {},            # uid -> {t, title, company, url, status, score, msg}
    "dedupe": {},          # firma|başlık hash -> uid
    "sources": {},         # ad -> {last_run, fails, last_error, last_ok, alerted, ctx}
    "tg_offset": 0,
    "paused": False,
    "last_summary": "",
    "daily": {},           # "YYYY-MM-DD" -> {sent, dropped, candidates}
}


class State:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = {**DEFAULT, **json.loads(path.read_text(encoding="utf-8"))}
        else:
            self.data = json.loads(json.dumps(DEFAULT))
            self.data["created"] = time.time()

    @property
    def first_run(self) -> bool:
        return not self.data["seen"]

    def save(self) -> None:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def prune(self) -> None:
        cutoff = time.time() - config.SEEN_RETENTION_DAYS * 86400
        seen = self.data["seen"]
        for uid in [u for u, v in seen.items() if v.get("t", 0) < cutoff and v.get("status") not in ("saved", "applied", "irrelevant")]:
            del seen[uid]
        live = set(seen)
        self.data["dedupe"] = {k: v for k, v in self.data["dedupe"].items() if v in live}
        days = sorted(self.data["daily"])
        for d in days[:-30]:
            del self.data["daily"][d]

    def source(self, name: str) -> dict:
        return self.data["sources"].setdefault(name, {"last_run": 0, "fails": 0, "last_error": "",
                                                       "last_ok": 0, "alerted": False, "ctx": {}})

    def is_seen(self, uid: str, dedupe_key: str) -> bool:
        return uid in self.data["seen"] or dedupe_key in self.data["dedupe"]

    def mark(self, job, status: str = "sent", msg_id: int | None = None, score: int | None = None) -> None:
        self.data["seen"][job.uid] = {"t": time.time(), "title": job.title, "company": job.company,
                                      "url": job.url, "status": status, "score": score, "msg": msg_id}
        self.data["dedupe"][job.dedupe_key] = job.uid

    def day(self, key: str) -> dict:
        return self.data["daily"].setdefault(key, {"sent": 0, "dropped": 0, "candidates": 0,
                                                   "applied": 0, "saved": 0, "irrelevant": 0})
