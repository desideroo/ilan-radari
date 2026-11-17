"""Kural tabanlı ön filtre ve puan. LLM yoksa ya da kotası bittiyse tek başına karar verir."""

from __future__ import annotations

import re

from . import config
from .models import Job, norm

_C = {k: [re.compile(p) for p in v["patterns"]] for k, v in config.TRACKS.items()}
_DESC = {k: [re.compile(p) for p in v] for k, v in config.DESCRIPTION_STRONG.items()}
_JUNIOR = [re.compile(p) for p in config.JUNIOR_PATTERNS]
_EXCL = [re.compile(p) for p in config.TITLE_EXCLUDE]
_EXCL_OK = [re.compile(p) for p in config.TITLE_EXCLUDE_EXCEPT]
_MIL = [re.compile(p) for p in config.MILITARY_PATTERNS]
_EXP = re.compile(r"(?:en az|minimum|min\.?|at least)?\s*(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*(?:yil|years?)\b[^.\n]{0,40}(?:deneyim|tecrube|experience|is tecrubesi)")
_EXP2 = re.compile(r"(?:deneyim|tecrube|experience)[^.\n]{0,25}?(\d{1,2})\s*\+?\s*(?:yil|years?)")


def location_ok(job: Job) -> bool:
    if job.is_remote:
        return True
    loc = norm(job.location)
    return any(c in loc for c in config.CITIES)


def title_excluded(job: Job) -> bool:
    t = norm(job.title)
    if any(p.search(t) for p in _EXCL_OK):
        return False
    return any(p.search(t) for p in _EXCL)


def title_tracks(job: Job) -> list[str]:
    t = norm(job.title)
    return [k for k, pats in _C.items() if any(p.search(t) for p in pats)]


def description_tracks(job: Job) -> list[str]:
    d = norm(job.description + " " + job.snippet)
    return [k for k, pats in _DESC.items() if any(p.search(d) for p in pats)]


def required_years(text: str) -> int | None:
    t = norm(text)
    vals = [int(m.group(1)) for m in _EXP.finditer(t)] + [int(m.group(1)) for m in _EXP2.finditer(t)]
    vals = [v for v in vals if 0 < v <= 20]
    return max(vals) if vals else None


def warnings_for(job: Job) -> list[str]:
    w = []
    blob = norm(job.description + " " + job.snippet)
    if any(p.search(blob) for p in _MIL):
        w.append("Askerlik: ilanda 'tamamlanmış' şartı var (sende tecilli, Ekim 2028)")
    yrs = required_years(job.description + " " + job.snippet)
    if yrs and yrs >= 2:
        w.append(f"Deneyim: ilanda {yrs}+ yıl isteniyor")
    if re.search(r"(ileri|akici|fluent|advanced|c1|native)[^.\n]{0,20}(ingilizce|english)|(ingilizce|english)[^.\n]{0,20}(ileri|akici|fluent|advanced|c1)", blob):
        w.append("Dil: ileri/akıcı İngilizce isteniyor (sende B2)")
    if re.search(r"almanca|german", blob):
        w.append("Dil: Almanca geçiyor (sende A2)")
    return w


def score(job: Job) -> int:
    """0-100 arası kaba uygunluk puanı (LLM yoksa kullanılır)."""
    if not job.tracks:
        return 0
    pri = max(config.TRACKS[t]["priority"] for t in job.tracks)
    s = {3: 60, 2: 50, 1: 40}[pri]
    if job.extra.get("track_from") == "title":
        s += 10
    blob = norm(job.title + " " + job.description + " " + job.snippet)
    if any(p.search(blob) for p in _JUNIOR):
        s += 15
    if any(c in norm(job.location) for c in config.CITIES):
        s += 5
    yrs = required_years(job.description)
    if yrs:
        s -= 5 * max(yrs - 1, 0)
    return max(0, min(100, s))


def prefilter(job: Job) -> bool:
    """Detay sayfası çekilmeden önceki ucuz eleme."""
    return location_ok(job) and not title_excluded(job)


def classify(job: Job) -> bool:
    """Detay okunduktan sonra: aday mı? Aday ise alan, puan ve uyarıları doldurur."""
    tr = title_tracks(job)
    job.extra["track_from"] = "title"
    if not tr:
        tr = description_tracks(job)
        job.extra["track_from"] = "description"
    if not tr:
        return False
    # "general" sadece başka alan yoksa kalsın
    if len(tr) > 1 and "general" in tr:
        tr.remove("general")
    tr.sort(key=lambda k: -config.TRACKS[k]["priority"])
    job.tracks = tr
    job.warnings = warnings_for(job)
    job.rule_score = score(job)
    return True


def suggested_cv(job: Job) -> str:
    if job.llm and job.llm.get("cv") in {v["cv"] for v in config.TRACKS.values()}:
        return job.llm["cv"]
    return config.TRACKS[job.tracks[0]]["cv"] if job.tracks else "06_Genel"
