"""Youthall: yeni mezun programları ve genç yetenek ilanları."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .. import http
from ..models import Job
from . import clean, jsonld

URL = "https://www.youthall.com/tr/jobs/"
NAME = "youthall"


def parse_list(page_html: str) -> list[Job]:
    soup = BeautifulSoup(page_html, "lxml")
    jobs = []
    for box in soup.select("div.jobs"):
        a = box.select_one("a[href*='youthall.com/tr/']")
        if not a:
            continue
        href = a["href"].split("?")[0]
        m = re.search(r"youthall\.com/tr/([^/]+)/([^/]+?)_(\d+)/?$", href)
        if not m:
            continue
        title = clean(box.select_one(".jobs-content-title").get_text() if box.select_one(".jobs-content-title") else "")
        logo = box.select_one(".jobs-content-logo")
        company = clean(logo.get("alt", "").removesuffix(" logo")) if logo else m.group(1)
        tags = [clean(t.get_text()) for t in box.select(".jobs-tag")]
        desc = box.select_one(".jobs-content-desc")
        jobs.append(Job(
            source=NAME, source_id=f"{m.group(1)}-{m.group(3)}", title=title, company=company,
            location=tags[2] if len(tags) > 2 else "",
            url=href, snippet=clean(desc.get_text() if desc else ""),
            work_mode=next((t for t in tags if t.lower() in ("uzaktan", "remote", "hibrit", "hybrid")), ""),
            extra={"type": tags[0] if tags else "", "deadline": tags[1] if len(tags) > 1 else ""},
        ))
    return jobs


def fetch(ctx: dict) -> list[Job]:
    jobs = parse_list(http.get(URL))
    # stajları ele (mezun olduğu için)
    return [j for j in jobs if "staj" not in j.extra.get("type", "").lower()]


def enrich(job: Job) -> None:
    node = jsonld.job_posting(http.get(job.url))
    if node:
        job.description = jsonld.summary(node)["description"]
