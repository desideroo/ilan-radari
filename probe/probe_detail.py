"""Detay sayfaları erişilebilir mi, JSON-LD var mı?"""

import json
from pathlib import Path

from radar import http
from radar.sources import elemannet, isbul, jsonld, kariyernet, youthall

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
res = []
for name, mod, url in [
    ("kariyernet", kariyernet, "https://www.kariyer.net/is-ilanlari/konya"),
    ("elemannet", elemannet, "https://www.eleman.net/is-ilanlari/konya"),
    ("isbul", isbul, "https://isbul.net/is-ilanlari/konya"),
    ("youthall", youthall, "https://www.youthall.com/tr/jobs/"),
]:
    try:
        jobs = mod.parse_list(http.get(url))
    except Exception as e:  # noqa: BLE001
        res.append({"source": name, "list_error": str(e)})
        continue
    for j in jobs[:3]:
        rec = {"source": name, "url": j.url}
        try:
            page = http.get(j.url, polite=3)
            node = jsonld.job_posting(page)
            rec.update(ok=True, bytes=len(page), jsonld=bool(node),
                       desc_len=len(jsonld.description_text(node)) if node else 0,
                       keys=sorted(node)[:20] if node else [])
            if not node:
                (OUT / f"detail_{name}.html").write_text(page[:600_000], encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rec.update(ok=False, error=str(e)[:200])
        res.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
(OUT / "results_detail.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
