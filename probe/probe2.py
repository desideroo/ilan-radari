"""Faz 0b: Kariyer.net arama URL'leri ve LinkedIn çalışma şekli/deneyim bilgisi."""

import json
import re
from pathlib import Path
from urllib.parse import quote_plus

from radar import http
from radar.sources import kariyernet, linkedin

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
res = {}

for path in ["/is-ilanlari/remote", "/is-ilanlari/remote?kw=sap", "/is-ilanlari/remote?kw=yaz%C4%B1l%C4%B1m",
             "/is-ilanlari/konya?kw=yaz%C4%B1l%C4%B1m", "/is-ilanlari/konya?kw=sap", "/is-ilanlari/konya?kw=bilgi%20i%C5%9Flem",
             "/is-ilanlari/remote?kw=sap&cp=2"]:
    try:
        jobs = kariyernet.parse_list(http.get("https://www.kariyer.net" + path, polite=4))
        res[path] = [f"{j.title} | {j.location} | {j.work_mode} | {j.posted}" for j in jobs[:15]] + [f"TOPLAM {len(jobs)}"]
    except Exception as e:  # noqa: BLE001
        res[path] = [f"HATA {e}"]

# LinkedIn: uzaktan filtresiyle gelen ilanların detayında çalışma şekli var mı
li = {}
for label, url in [
    ("remote_sap", linkedin.search_url("SAP", "Türkiye", remote=True, posted_within_s=7 * 86400)),
    ("remote_sap_fE23", linkedin.search_url("SAP", "Türkiye", remote=True, posted_within_s=7 * 86400) + "&f_E=2%2C3"),
    ("konya_fE23", linkedin.search_url("", "Konya, Türkiye", posted_within_s=7 * 86400) + "&f_E=2%2C3"),
]:
    html = http.get(url)
    jobs = linkedin.parse_search(html, remote="remote" in label)
    li[label] = {"count": len(jobs), "items": []}
    for j in jobs[:6]:
        d = http.get(linkedin.DETAIL.format(id=j.source_id))
        Path(OUT / f"li_{label}_{j.source_id}.html").write_text(d, encoding="utf-8")
        det = linkedin.parse_detail(d)
        low = d.lower()
        hints = sorted({w for w in ["remote", "uzaktan", "hybrid", "hibrit", "on-site", "iş yerinde", "workplace",
                                     "ofisten", "office"] if w in low})
        li[label]["items"].append({"title": j.title, "loc": j.location, "criteria": det["criteria"], "hints": hints})
    # kart HTML'sinde çalışma şekli var mı
    li[label]["card_has_workplace"] = bool(re.search(r"workplace|uzaktan|remote", html, re.I))

(OUT / "probe2.json").write_text(json.dumps({"kariyernet": res, "linkedin": li}, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({"kariyernet": res, "linkedin": li}, ensure_ascii=False, indent=1))
