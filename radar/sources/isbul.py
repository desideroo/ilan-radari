from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import config, http
from ..models import Job
from . import clean, jsonld

BASE = "https://isbul.net"
NAME = "isbul"


def parse_list(page_html: str) -> list[Job]:
    soup = BeautifulSoup(page_html, "lxml")
    jobs, seen = [], set()
    for a in soup.select("a[href^='/is-ilani/'][aria-label]"):
        href = a["href"].split("?")[0]
        m = re.search(r"-(\d+)$", href)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        title = clean(a.get("title") or a.get_text())
        # aria-label: "Başlık, Firma, Konum"
        label = [clean(p) for p in a["aria-label"].split(",")]
        company = label[1] if len(label) > 1 else ""
        location = ", ".join(label[2:]) if len(label) > 2 else ""
        card = a.find_parent("article") or a.parent.parent.parent.parent
        chips = [clean(s.get("title", "")) for s in card.select("span[data-chip][title]")] if card else []
        mode = next((c for c in chips if c.lower() in ("uzaktan", "hibrit", "iş yerinde", "işyerinde")), "")
        jobs.append(Job(source=NAME, source_id=m.group(1), title=title, company=company,
                        location=location, url=urljoin(BASE, href), work_mode=mode,
                        extra={"chips": chips}))
    return jobs


def fetch(ctx: dict) -> list[Job]:
    jobs: list[Job] = []
    for path in config.ISBUL_PATHS:
        jobs += parse_list(http.get(BASE + path))
    return jobs


def enrich(job: Job) -> None:
    node = jsonld.job_posting(http.get(job.url))
    if node:
        s = jsonld.summary(node)
        job.description = s["description"]
        if s["date_posted"]:
            job.posted = s["date_posted"][:10]
        if s["remote"] and not job.work_mode:
            job.work_mode = "Uzaktan"
