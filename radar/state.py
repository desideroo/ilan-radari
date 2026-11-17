"""Kalıcı durum: görülen ilanlar, kaynak sağlığı, Telegram offset'i.

Dosya `state/state.json` olarak ayrı `state` branch'inde tutulur (workflow commit eder).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import config

DETAILS_RETENTION_DAYS = 14

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
    "details": {},         # uid -> ilanın tam resmi (açıklama, konum, LLM değerlendirmesi); 14 gün tutulur
}


class State:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = {**json.loads(json.dumps(DEFAULT)), **json.loads(path.read_text(encoding="utf-8"))}
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
        dcut = time.time() - DETAILS_RETENTION_DAYS * 86400
        details = self.data.setdefault("details", {})
        for uid in [u for u, v in details.items() if v.get("t", 0) < dcut or u not in seen]:
            if seen.get(uid, {}).get("status") in ("saved", "applied", "irrelevant"):
                details[uid].pop("description", None)   # işaretlilerin özeti kalsın, uzun metin gitsin
            else:
                del details[uid]
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
        reason = (getattr(job, "extra", None) or {}).get("reject", "")
        if status != "skip" or reason:
            # günlük değerlendirme için ilanın tam resmi (sadece ilgili ilanlar; açıklama kısaltılır)
            cap = 600 if status == "skip" else 2500
            llm = job.llm or {}
            self.data["details"][job.uid] = {
                "t": time.time(), "source": job.source, "title": job.title, "company": job.company,
                "location": job.location, "work_mode": job.work_mode, "posted": job.posted,
                "tracks": job.tracks, "rule_score": job.rule_score, "reject": reason,
                "warnings": job.warnings, "seniority": job.extra.get("seniority", ""),
                "track_from": job.extra.get("track_from", ""),
                "llm": {k: llm.get(k) for k in ("score", "cv", "summary", "why", "gaps",
                                                 "military_required", "min_years", "work_mode") if k in llm},
                "description": (job.description or job.snippet or "")[:cap],
            }

    def day(self, key: str) -> dict:
        return self.data["daily"].setdefault(key, {"sent": 0, "dropped": 0, "candidates": 0,
                                                   "applied": 0, "saved": 0, "irrelevant": 0})
