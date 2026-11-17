"""Faz 0, ikinci tur: HTTP ile engellenen siteleri gerçek tarayıcıyla (Playwright) dene."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("probe_out")
(OUT / "html").mkdir(parents=True, exist_ok=True)

TARGETS = {
    "kariyernet_search": "https://www.kariyer.net/is-ilanlari?kw=sap",
    "kariyernet_konya": "https://www.kariyer.net/is-ilanlari/konya",
    "yenibiris": "https://www.yenibiris.com/is-ilanlari?q=yaz%C4%B1l%C4%B1m",
    "secretcv": "https://www.secretcv.com/is-ilanlari/konya",
    "youthall_jobs": "https://www.youthall.com/tr/jobs/",
    "indeed_tr": "https://tr.indeed.com/jobs?q=sap&l=Konya",
}

MARKERS = ["just a moment", "cf-chl", "captcha", "access denied", "verify you are human"]

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        locale="tr-TR",
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        viewport={"width": 1366, "height": 900},
    )
    for name, url in TARGETS.items():
        page = ctx.new_page()
        api_hits = []
        page.on("response", lambda r, acc=api_hits: acc.append((r.status, r.url))
                if r.request.resource_type in ("xhr", "fetch") else None)
        rec = {"source": name, "client": "playwright"}
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(8000)
            html = page.content()
            rec.update(status=resp.status if resp else None, bytes=len(html), title=page.title()[:120],
                       block_markers=[m for m in MARKERS if m in html.lower()],
                       xhr=[f"{s} {u[:160]}" for s, u in api_hits][:40])
            (OUT / "html" / f"{name}__playwright.html").write_text(html[:600_000], encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        page.close()
    browser.close()

(OUT / "results_browser.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
