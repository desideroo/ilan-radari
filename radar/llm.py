"""Gemini ile toplu ilan değerlendirmesi (ücretsiz katman).

Anahtar yoksa ya da kota/hata olursa None döner; sistem kural puanıyla devam eder.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

from .models import Job

# Boşsa: hesabın erişebildiği Flash modelleri otomatik bulunur (Google model adlarını sık değiştiriyor)
MODELS_ENV = [m.strip() for m in os.getenv("GEMINI_MODELS", "").split(",") if m.strip()]
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
_models_cache: list[str] | None = None


def _version(name: str) -> tuple:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return (float(m.group(1)) if m else 0.0,)


def available_models(key: str, log=print) -> list[str]:
    """generateContent destekleyen Flash modelleri: en yeni sürüm önce, aynı sürümde Flash, sonra Flash-Lite."""
    global _models_cache
    if _models_cache is not None:
        return _models_cache
    if MODELS_ENV:
        _models_cache = MODELS_ENV
        return _models_cache
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30)
        r.raise_for_status()
        names = []
        for m in r.json().get("models", []):
            n = m.get("name", "").removeprefix("models/")
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if not re.fullmatch(r"gemini-\d+(\.\d+)?-flash(-lite)?(-latest)?", n):
                continue  # preview/image/tts/live gibi varyantları atla
            names.append(n)
        names.sort(key=lambda n: (_version(n), "lite" not in n), reverse=True)
        _models_cache = names[:3] or FALLBACK_MODELS
    except Exception as e:  # noqa: BLE001
        log(f"LLM model listesi alınamadı ({type(e).__name__}), varsayılanlar kullanılıyor")
        _models_cache = FALLBACK_MODELS
    log(f"LLM modelleri: {', '.join(_models_cache)}")
    return _models_cache
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
            "work_mode": {"type": "STRING", "enum": ["remote", "hybrid", "onsite", "unknown"]},
        },
        "required": ["id", "score", "cv", "summary", "why", "gaps", "military_required", "min_years", "work_mode"],
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
- min_years: ilanda ŞART olarak istenen minimum iş deneyimi yılı. "Tercihen" yazanlar ve staj sayılmaz. Yoksa 0.
- work_mode: ilan metnine göre çalışma şekli: "remote" (tamamen uzaktan), "hybrid", "onsite" ya da yazmıyorsa "unknown"
Aday yeni mezun ve tam zamanlı iş deneyimi yok: 2 yıl ve üstü deneyim şartı olan ya da kıdemli/uzman seviye
(senior, lead, 3+ yıl) ilanlara en fazla 20 puan ver.
Uydurma bilgi yazma; sadece ilanda yazanı kullan.
{feedback}
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


def feedback_block(feedback: dict | None) -> str:
    """Kullanıcının Telegram butonlarıyla verdiği geri bildirimi istem metnine çevirir."""
    if not feedback or not (feedback.get("bad") or feedback.get("good")):
        return ""
    lines = ["", "KULLANICI GERİ BİLDİRİMİ (adayın kendi işaretlemeleri, puanlamayı buna göre ayarla):"]
    if feedback.get("bad"):
        lines.append("İlgisiz bulduğu ilanlar: bunlara benzeyen ilanlara (aynı tür rol, sektör ya da firma tipi) 30'un altında puan ver.")
        lines += [f"- {t}" for t in feedback["bad"]]
    if feedback.get("good"):
        lines.append("Başvurduğu ya da kaydettiği ilanlar: bunlara benzeyen ilanların puanını yükselt.")
        lines += [f"- {t}" for t in feedback["good"]]
    return "\n".join(lines) + "\n"


def evaluate(jobs: list[Job], log=print, feedback: dict | None = None) -> int:
    """Her işe job.llm atar. Başarıyla değerlendirilen ilan sayısını döndürür.
    feedback: {"bad": [...], "good": [...]} kullanıcının işaretlediği ilanların "başlık (firma)" listesi."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or not jobs:
        return 0
    done = 0
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        prompt = PROMPT.format(profile=PROFILE, jobs=_payload(chunk), feedback=feedback_block(feedback))
        result = None
        for model in available_models(key, log):
            for attempt in range(2):  # 503 (yoğunluk) için bir kez daha dene
                try:
                    result = _call(model, key, prompt)
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"LLM uyarı: {str(e)[:160]}")
                    if "HTTP 503" not in str(e):
                        break
                    time.sleep(8)
            if result is not None:
                break
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
