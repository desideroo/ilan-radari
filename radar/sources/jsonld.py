"""İlan detay sayfalarındaki schema.org JobPosting (JSON-LD) verisini okur.

Google for Jobs için çoğu ilan sitesi bunu yayınlar; site tasarımı değişse bile
genelde sabit kaldığı için detay okumada ilk tercih budur.
"""

from __future__ import annotations

import html as htmlmod
import json
import re

from bs4 import BeautifulSoup

from . import clean


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def job_posting(page_html: str) -> dict | None:
    soup = BeautifulSoup(page_html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            t = node.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                return node
    return None


def description_text(node: dict) -> str:
    raw = htmlmod.unescape(node.get("description") or "")
    text = BeautifulSoup(raw, "lxml").get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:6000]


def summary(node: dict) -> dict:
    org = node.get("hiringOrganization") or {}
    loc = node.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
    return {
        "description": description_text(node),
        "company": clean(org.get("name") if isinstance(org, dict) else ""),
        "city": clean(addr.get("addressLocality") or addr.get("addressRegion") or ""),
        "date_posted": node.get("datePosted", ""),
        "valid_through": node.get("validThrough", ""),
        "employment_type": node.get("employmentType", ""),
        "remote": node.get("jobLocationType") == "TELECOMMUTE",
        "experience": node.get("experienceRequirements", ""),
    }
