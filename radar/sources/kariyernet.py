"""Kariyer.net arama sayfaları (sunucu tarafında render edilen HTML).

Site gerçek tarayıcıları bot korumasıyla (PerimeterX) engelliyor ama düz HTTP
isteklerine şimdilik cevap veriyor. Bu yüzden istekler az ve seyrek tutulur.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from .. import config, http
from ..models import Job
from . import age_from_text, clean, jsonld

BASE = "https://www.kariyer.net"
NAME = "kariyernet"


def parse_list(page_html: str) -> list[Job]:
    soup = BeautifulSoup(page_html, "lxml")
    jobs = []
    for card in soup.select('div[data-test="ad-card"]'):
        a = card.select_one("a[href*='/is-ilani/']")
        if not a:
            continue
        href = a["href"]
        m = re.search(r"-(\d+)/?$", href.split("?")[0])
        if not m:
            continue
        title_el = card.select_one('[data-test="ad-card-title"]')
        comp_el = card.select_one('[data-test="subtitle"]')
        loc_el = card.select_one('[data-test="location"]')
        when = card.get("time", "")
        jobs.append(Job(
            source=NAME, source_id=m.group(1),
            title=clean(title_el.get_text() if title_el else card.get("positionname", "")),
            company=clean(comp_el.get_text() if comp_el else ""),
            location=clean(loc_el.get_text() if loc_el else card.get("cityname", "")),
            url=urljoin(BASE, href.split("?")[0]),
            work_mode=clean(card.get("workmodeltext", "")),
            posted=when, age_hours=age_from_text(when),
            extra={"sponsored": card.get("sponsor") == "true",
                   "work_type": card.get("worktypetext", ""),
                   "sector": card.get("sectorname", "")},
        ))
    return jobs


def fetch(ctx: dict) -> list[Job]:
    jobs: list[Job] = []
    for path in config.KARIYERNET_CITY_PATHS:
        jobs += parse_list(http.get(BASE + path, polite=3))
    kws = config.KARIYERNET_REMOTE_KEYWORDS
    first = ctx.get("first_run", False)
    cursor = ctx.setdefault("cursor", 0)
    chosen = kws if first else [kws[(cursor + i) % len(kws)] for i in range(config.KARIYERNET_REMOTE_PER_RUN)]
    ctx["cursor"] = (cursor + config.KARIYERNET_REMOTE_PER_RUN) % len(kws)
    for kw in chosen:
        found = parse_list(http.get(f"{BASE}/is-ilanlari?kw={quote_plus(kw)}", polite=3))
        jobs += [j for j in found if "uzaktan" in j.work_mode.lower() or "remote" in j.work_mode.lower()]
    return jobs


def parse_detail(page_html: str) -> str:
    """İlan metni + 'Aday Kriterleri' (tecrübe, eğitim, askerlik) tek metin olarak."""
    soup = BeautifulSoup(page_html, "lxml")
    q = soup.select_one('[data-test="qualifications-and-job-description"]')
    text = q.get_text("\n", strip=True) if q else ""
    body = soup.select_one(".job-detail-body")
    if body:
        lines = body.get_text("\n", strip=True).split("\n")
        if "Aday Kriterleri" in lines:
            crit, i = [], lines.index("Aday Kriterleri") + 1
            while i < len(lines) - 1 and len(crit) < 8:
                if lines[i] == "•":
                    crit.append(f"{lines[i + 1]}: {lines[i + 2] if i + 2 < len(lines) else ''}")
                    i += 3
                else:
                    break
            if crit:
                text += "\n\nAday Kriterleri: " + "; ".join(crit)
    if not text:
        node = jsonld.job_posting(page_html)
        text = jsonld.summary(node)["description"] if node else ""
    return text[:6000]


def enrich(job: Job) -> None:
    job.description = parse_detail(http.get(job.url, polite=3))
