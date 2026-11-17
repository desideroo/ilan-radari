"""Faz 0: kaynak fizibilite testi.

GitHub Actions sunucusundan her ilan kaynağına birkaç istek atar ve
sonucu probe_out/ altına yazar: HTTP durumu, sayfa boyutu, bot koruması
izleri ve ilan sayısı tahmini. Ham HTML örnekleri de saklanır ki
parser'lar gerçek çıktıya göre yazılabilsin.

İki istemci denenir:
  - requests  (sade HTTP)
  - curl_cffi (gerçek Chrome TLS parmak izi taklidi)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from curl_cffi import requests as creq

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
(OUT / "html").mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

BLOCK_MARKERS = [
    "just a moment",
    "cf-chl",
    "challenge-platform",
    "captcha",
    "access denied",
    "attention required",
    "px-captcha",
    "datadome",
    "verify you are human",
    "robot",
]

kw = "yazılım"
TARGETS: dict[str, str] = {
    # LinkedIn guest API (giriş gerektirmeyen ilan uç noktası)
    "linkedin_konya": (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=&location=Konya%2C%20T%C3%BCrkiye&f_TPR=r604800&start=0"
    ),
    "linkedin_tr_remote_sap": (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=SAP&location=T%C3%BCrkiye&f_WT=2&f_TPR=r604800&start=0"
    ),
    "linkedin_tr_sap": (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=SAP%20ABAP&location=T%C3%BCrkiye&f_TPR=r604800&start=0"
    ),
    # Kariyer.net
    "kariyernet_search": f"https://www.kariyer.net/is-ilanlari?kw={quote_plus('sap')}",
    "kariyernet_konya": "https://www.kariyer.net/is-ilanlari/konya",
    # Diğer Türk siteleri
    "yenibiris": f"https://www.yenibiris.com/is-ilanlari?q={quote_plus(kw)}",
    "eleman_net": "https://www.eleman.net/is-ilanlari/konya",
    "secretcv": "https://www.secretcv.com/is-ilanlari/konya",
    "isbul": "https://isbul.net/is-ilanlari/konya",
    "youthall_jobs": "https://www.youthall.com/tr/jobs/",
    "toptalent": "https://toptalent.co/is-ilanlari",
    "kariyerkapisi": "https://kariyerkapisi.cbiko.gov.tr/",
    "ilan_gov_tr": "https://www.ilan.gov.tr/ilan/kategori/9/is-ilanlari",
    "indeed_tr": "https://tr.indeed.com/jobs?q=sap&l=Konya",
    "glassdoor_tr": "https://www.glassdoor.com.tr/Is/konya-is-ilanlari-SRCH_IL.0,5_IC2828063.htm",
}


def classify(status: int, text: str) -> list[str]:
    low = text[:200_000].lower()
    hits = [m for m in BLOCK_MARKERS if m in low]
    return hits


def count_jobs(name: str, text: str) -> int:
    if name.startswith("linkedin"):
        return len(re.findall(r"base-search-card", text)) or len(
            re.findall(r"/jobs/view/", text)
        )
    # Kaba tahmin: ilan detay linki benzeri href sayısı
    pats = [r"/is-ilani/", r"/ilan/", r"/jobs/", r"/is-ilanlari/[^\"'?]+-\d+", r"jobId"]
    return max(len(re.findall(p, text)) for p in pats)


def fetch(client: str, url: str):
    t0 = time.time()
    try:
        if client == "requests":
            r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        else:
            r = creq.get(url, headers={"Accept-Language": HEADERS["Accept-Language"]},
                         impersonate="chrome", timeout=25, allow_redirects=True)
        return r.status_code, r.text, r.url, round(time.time() - t0, 2), None
    except Exception as e:  # noqa: BLE001
        return None, "", url, round(time.time() - t0, 2), repr(e)[:300]


def main() -> None:
    results = []
    for name, url in TARGETS.items():
        for client in ("requests", "curl_cffi"):
            status, text, final_url, secs, err = fetch(client, url)
            rec = {
                "source": name,
                "client": client,
                "status": status,
                "final_url": final_url,
                "bytes": len(text),
                "seconds": secs,
                "block_markers": classify(status or 0, text),
                "job_like_count": count_jobs(name, text) if text else 0,
                "title": (re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I).group(1).strip()[:120]
                          if re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I) else ""),
                "error": err,
            }
            results.append(rec)
            if text:
                (OUT / "html" / f"{name}__{client}.html").write_text(text[:600_000], encoding="utf-8")
            print(json.dumps(rec, ensure_ascii=False))
            time.sleep(2)

    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # LinkedIn detay uç noktası (ilan içeriği) testi
    m = None
    for f in (OUT / "html").glob("linkedin_*__requests.html"):
        m = re.search(r"urn:li:jobPosting:(\d+)", f.read_text(encoding="utf-8"))
        if m:
            break
    if m:
        jid = m.group(1)
        st, tx, _, secs, err = fetch("requests", f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")
        (OUT / "html" / "linkedin_detail.html").write_text(tx[:600_000], encoding="utf-8")
        print(json.dumps({"source": "linkedin_detail", "status": st, "bytes": len(tx), "err": err}))


if __name__ == "__main__":
    main()
