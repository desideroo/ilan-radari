"""LinkedIn'in giriş gerektirmeyen (guest) iş ilanı uç noktaları.

Hiçbir hesap, çerez ya da oturum kullanılmaz.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .. import config, http
from ..models import Job
from . import age_from_date, age_from_text, clean

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
NAME = "linkedin"


def search_url(keywords: str, location: str, *, remote: bool = False, start: int = 0,
               posted_within_s: int = 86400) -> str:
    params = {"keywords": keywords, "location": location, "f_TPR": f"r{posted_within_s}",
              "sortBy": "DD", "start": start}
    if remote:
        params["f_WT"] = "2"   # LinkedIn guest araması bunu yok sayıyor; uzaktan olduğu açıklamadan doğrulanır
    return f"{SEARCH}?{urlencode(params)}"


def parse_search(html: str, *, remote: bool = False) -> list[Job]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    for card in soup.select("div.base-search-card"):
        urn = card.get("data-entity-urn", "")
        m = re.search(r"(\d+)$", urn)
        if not m:
            continue
        jid = m.group(1)
        title = clean(card.select_one(".base-search-card__title").get_text() if card.select_one(".base-search-card__title") else "")
        comp_el = card.select_one(".base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location")
        time_el = card.select_one("time")
        posted = time_el.get("datetime", "") if time_el else ""
        age = age_from_text(clean(time_el.get_text())) if time_el else None
        if age is None and posted:
            age = age_from_date(posted)
        jobs.append(Job(
            source=NAME, source_id=jid, title=title,
            company=clean(comp_el.get_text() if comp_el else ""),
            location=clean(loc_el.get_text() if loc_el else ""),
            url=f"https://www.linkedin.com/jobs/view/{jid}/",
            posted=posted, age_hours=age,
            extra={"remote_query": True} if remote else {},
        ))
    return jobs


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    desc_el = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
    desc = desc_el.get_text("\n", strip=True) if desc_el else ""
    criteria = {}
    for li in soup.select(".description__job-criteria-item"):
        k = li.select_one(".description__job-criteria-subheader")
        v = li.select_one(".description__job-criteria-text")
        if k and v:
            criteria[clean(k.get_text())] = clean(v.get_text())
    applicants = soup.select_one(".num-applicants__caption")
    return {"description": desc[:6000], "criteria": criteria,
            "applicants": clean(applicants.get_text()) if applicants else ""}


def fetch(ctx: dict) -> list[Job]:
    jobs: list[Job] = []
    first = ctx.get("first_run", False)
    window = 7 * 86400 if first else 86400
    for q in config.LINKEDIN_CITY_QUERIES:
        for page in range(config.LINKEDIN_PAGES_CITY):
            html = http.get(search_url(q["keywords"], q["location"], start=page * 10, posted_within_s=window))
            batch = parse_search(html)
            jobs += batch
            if len(batch) < 10:
                break
    # Uzaktan anahtar kelimeler: her turda sırayla bir dilim
    kws = config.LINKEDIN_REMOTE_KEYWORDS
    if first:
        chosen = kws
    else:
        cursor = ctx.setdefault("cursor", 0)
        chosen = [kws[(cursor + i) % len(kws)] for i in range(config.LINKEDIN_REMOTE_PER_RUN)]
        ctx["cursor"] = (cursor + config.LINKEDIN_REMOTE_PER_RUN) % len(kws)
    for kw in chosen:
        html = http.get(search_url(kw, "Türkiye", remote=True, posted_within_s=window if first else 3 * 86400))
        jobs += parse_search(html, remote=True)
    return jobs


def enrich(job: Job) -> None:
    d = parse_detail(http.get(DETAIL.format(id=job.source_id)))
    job.description = d["description"]
    job.extra.update(criteria=d["criteria"], applicants=d["applicants"])
    seniority = d["criteria"].get("Kıdem düzeyi") or d["criteria"].get("Seniority level") or ""
    if seniority:
        job.extra["seniority"] = seniority
