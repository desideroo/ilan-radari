"""Gemini ile toplu ilan değerlendirmesi (ücretsiz katman).

Anahtar yoksa ya da kota/hata olursa None döner; sistem kural puanıyla devam eder.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from .models import Job

MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROFILE = (Path(__file__).parent / "profile.md").read_text(encoding="utf-8")
BATCH = 6

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "score": {"type": "INTEGER"},
            "cv": {"type": "STRING"},
            "summary": {"type": "STRING"},
            "why": {"type": "STRING"},
            "gaps": {"type": "STRING"},
            "military_required": {"type": "BOOLEAN"},
            "min_years": {"type": "INTEGER"},
        },
        "required": ["id", "score", "cv", "summary", "why", "gaps", "military_required", "min_years"],
    },
}

PROMPT = """Sen deneyimli bir İK uzmanısın. Aşağıdaki aday profiline göre her iş ilanını değerlendir.

{profile}

Her ilan için JSON döndür:
- id: ilanın id'si (aynen)
- score: 0-100 uygunluk. Ölçüt: adayın alanı ve yetkinlikleriyle örtüşme, yeni mezun için gerçekçilik (kıdem, yıl şartı),
  konum (Konya/Karaman ya da uzaktan). SAP/ERP rolleri öncelikli. Alanla ilgisiz ilan (satış, üretim, muhasebe elemanı vb.) 0-20.
- cv: önerilen CV kodu (yukarıdaki listeden tam olarak biri)
- summary: ilanın 2 cümlelik Türkçe özeti (ne iş, hangi teknolojiler)
- why: adayın neden uygun olduğu, 1 cümle
- gaps: adayda eksik kalan şartlar, kısa (yoksa "-")
- military_required: ilanda "askerliğini tamamlamış/muaf" şartı varsa true
- min_years: istenen minimum deneyim yılı (yoksa 0)
Uydurma bilgi yazma; sadece ilanda yazanı kullan.

İLANLAR:
{jobs}
"""


def _payload(jobs: list[Job]) -> str:
    items = []
    for j in jobs:
        items.append({
            "id": j.uid, "baslik": j.title, "firma": j.company, "konum": j.location,
            "calisma_sekli": j.work_mode, "aciklama": (j.description or j.snippet)[:3500],
        })
    return json.dumps(items, ensure_ascii=False)


def _call(model: str, key: str, prompt: str) -> list[dict]:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA,
                             "temperature": 0.2},
    }
    # anahtar URL'de değil başlıkta: hata mesajlarında/loglarda görünmesin
    r = requests.post(API.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def evaluate(jobs: list[Job], log=print) -> int:
    """Her işe job.llm atar. Başarıyla değerlendirilen ilan sayısını döndürür."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or not jobs:
        return 0
    done = 0
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        prompt = PROMPT.format(profile=PROFILE, jobs=_payload(chunk))
        result = None
        for model in MODELS:
            try:
                result = _call(model, key, prompt)
                break
            except Exception as e:  # noqa: BLE001
                log(f"LLM uyarı: {e}")
                time.sleep(3)
        if result is None:
            break  # kota/hata: kalanlar kural puanıyla gider
        by_id = {r.get("id"): r for r in result if isinstance(r, dict)}
        for j in chunk:
            r = by_id.get(j.uid)
            if r:
                r["score"] = max(0, min(100, int(r.get("score", 0))))
                j.llm = r
                done += 1
        time.sleep(4)  # ücretsiz katman dakika sınırı için
    return done
