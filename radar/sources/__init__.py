from __future__ import annotations

import re
from datetime import date, datetime, timezone

from ..models import norm


def age_from_text(text: str) -> float | None:
    """'4 saat', '2 gün önce', '1 hafta', 'Bugün', '30 dakika' -> saat cinsinden yaş."""
    t = norm(text)
    if not t:
        return None
    if "bugun" in t or "yeni" in t or "just now" in t:
        return 6.0
    if "dun" in t or "yesterday" in t:
        return 30.0
    m = re.search(r"(\d+)\s*\+?\s*(dakika|dk|minute|saat|hour|gun|day|hafta|week|ay|month)", t)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    mult = {"dakika": 1 / 60, "dk": 1 / 60, "minute": 1 / 60, "saat": 1, "hour": 1,
            "gun": 24, "day": 24, "hafta": 168, "week": 168, "ay": 720, "month": 720}[unit]
    return n * mult


def age_from_date(iso: str) -> float | None:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    then = datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)
    return max((now - then).total_seconds() / 3600, 0.0)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
