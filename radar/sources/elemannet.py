from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import config, http
from ..models import Job
from . import clean, jsonld

BASE = "https://www.eleman.net"
NAME = "elemannet"


def parse_list(page_html: str) -> list[Job]:
    soup = BeautifulSoup(page_html, "lxml")
    jobs = []
    for box in soup.select("div.ilan_listeleme_bol"):
        a = box.select_one("a[href*='/is-ilani/']")
        if not a:
            continue
        m = re.search(r"-i(\d+)", a["href"])
        if not m:
            continue
        h3 = a.select_one("h3")
        title = clean(h3.find(string=True, recursive=False) if h3 else a.get("title", ""))
        if not title and h3:
            title = clean(h3.get_text())
        sub = a.select_one(".c-showcase-box__subtitle")
        company, location = "", ""
        if sub:
            parts = [clean(p) for p in sub.get_text("|").split("|") if clean(p)]
            if parts:
                company = parts[0]
            if len(parts) > 1:
                location = " ".join(parts[1:])
        snip = a.select_one(".c-showcase-box__text")
        jobs.append(Job(
            source=NAME, source_id=m.group(1), title=title, company=company,
            location=re.sub(r"\s*-\s*", " - ", location).strip(" -"),
            url=a["href"].split("?")[0],
            snippet=clean(snip.get_text() if snip else ""),
        ))
    return jobs


def fetch(ctx: dict) -> list[Job]:
    jobs: list[Job] = []
    for path in config.ELEMANNET_PATHS:
        jobs += parse_list(http.get(BASE + path))
    return jobs


def enrich(job: Job) -> None:
    node = jsonld.job_posting(http.get(job.url))
    if node:
        s = jsonld.summary(node)
        job.description = s["description"]
        if s["date_posted"]:
            job.posted = s["date_posted"][:10]
