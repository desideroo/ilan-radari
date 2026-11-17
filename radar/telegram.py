"""Telegram Bot API: mesaj gönderme, butonlar ve komutlar.

Butonlara basma ve komutlar bir sonraki turda (en geç ~15 dk) işlenir;
sürekli açık bir sunucu gerekmesin diye webhook yerine getUpdates kullanılır.
"""

from __future__ import annotations

import html
import os
import time

import requests

from . import config
from .matching import suggested_cv
from .models import Job

SOURCE_LABEL = {"linkedin": "LinkedIn", "kariyernet": "Kariyer.net", "elemannet": "Eleman.net",
                "isbul": "isbul.net", "youthall": "Youthall"}


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.enabled = bool(self.token and self.chat_id)

    def _api(self, method: str, **params):
        if not self.enabled:
            return None
        err = "429"
        for attempt in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{self.token}/{method}", json=params, timeout=30)
            except requests.RequestException as e:
                # hata metninde token'lı URL olabilir: sadece tür adını raporla
                err = type(e).__name__
                time.sleep(2 * (attempt + 1))
                continue
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 429:
                time.sleep(int(data.get("parameters", {}).get("retry_after", 3)) + 1)
                continue
            if not data.get("ok"):
                raise RuntimeError(f"Telegram {method}: {data.get('description', r.status_code)}")
            return data["result"]
        raise RuntimeError(f"Telegram {method}: bağlantı hatası ({err})")

    def send(self, text: str, buttons: list[list[dict]] | None = None, silent: bool = False):
        params = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                  "link_preview_options": {"is_disabled": True}, "disable_notification": silent}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        res = self._api("sendMessage", **params)
        time.sleep(1.1)  # sohbet başına ~1 mesaj/sn sınırı
        return res

    def updates(self, offset: int) -> list[dict]:
        return self._api("getUpdates", offset=offset, timeout=0,
                         allowed_updates=["message", "callback_query"]) or []

    def answer_callback(self, cq_id: str, text: str):
        try:
            self._api("answerCallbackQuery", callback_query_id=cq_id, text=text)
        except RuntimeError:
            pass  # eski (süresi geçmiş) callback'ler cevaplanamaz, sorun değil

    def set_buttons(self, message_id: int, buttons: list[list[dict]]):
        try:
            self._api("editMessageReplyMarkup", chat_id=self.chat_id, message_id=message_id,
                      reply_markup={"inline_keyboard": buttons})
        except RuntimeError:
            pass

    def set_commands(self):
        self._api("setMyCommands", commands=[
            {"command": "durum", "description": "Sistem ve kaynak durumu"},
            {"command": "bugun", "description": "Bugünün özeti"},
            {"command": "kaydedilenler", "description": "'Sonra bak' dediğin ilanlar"},
            {"command": "duraklat", "description": "Bildirimleri durdur"},
            {"command": "devam", "description": "Bildirimleri yeniden başlat"},
            {"command": "yardim", "description": "Komutlar"},
        ])


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def score_icon(score: int) -> str:
    return "🟢" if score >= 70 else "🟡" if score >= 45 else "🟠"


def job_buttons(uid: str, status: str = "") -> list[list[dict]]:
    if status == "applied":
        return [[{"text": "✅ Başvuruldu", "callback_data": f"u:{uid}"}]]
    if status == "irrelevant":
        return [[{"text": "❌ İlgisiz olarak işaretlendi", "callback_data": f"u:{uid}"}]]
    row = [{"text": "✅ Başvurdum", "callback_data": f"a:{uid}"},
           {"text": "⭐ Sonra", "callback_data": f"s:{uid}"},
           {"text": "❌ İlgisiz", "callback_data": f"x:{uid}"}]
    if status == "saved":
        row[1] = {"text": "⭐ Kaydedildi", "callback_data": f"u:{uid}"}
    return [row]


def format_job(job: Job) -> str:
    sc = job.llm["score"] if job.llm else job.rule_score
    lines = [f"{score_icon(sc)} <b>{sc}/100</b> · <b>{esc(job.title)}</b>"]
    meta = [f"🏢 {esc(job.company or '?')}"]
    loc = job.location or ""
    if job.work_mode and job.work_mode.lower() not in loc.lower():
        loc = f"{loc} ({job.work_mode})" if loc else job.work_mode
    meta.append(f"📍 {esc(loc or '?')}")
    lines.append(" · ".join(meta))
    when = job.posted if job.posted and not job.posted[:4].isdigit() else ""
    if job.age_hours is not None:
        h = job.age_hours
        when = f"{int(h)} saat önce" if h < 24 else f"{int(h // 24)} gün önce"
    src = SOURCE_LABEL.get(job.source, job.source)
    lines.append(f"🕐 {esc(when or '-')} · {src}")
    labels = ", ".join(config.TRACKS[t]["label"] for t in job.tracks[:2])
    lines.append(f"🧭 {esc(labels)} · 📄 CV: <b>{esc(suggested_cv(job))}</b>")
    if job.llm:
        lines.append(f"📝 {esc(job.llm.get('summary', ''))}")
        if job.llm.get("why"):
            lines.append(f"👍 {esc(job.llm['why'])}")
        gaps = (job.llm.get("gaps") or "").strip()
        if gaps and gaps != "-":
            lines.append(f"🔸 Eksik: {esc(gaps)}")
    elif job.snippet or job.description:
        lines.append(f"📝 {esc((job.snippet or job.description)[:280])}…")
    warns = list(job.warnings)
    if job.llm and job.llm.get("military_required") and not any(w.startswith("Askerlik") for w in warns):
        warns.insert(0, "Askerlik: ilanda 'tamamlanmış' şartı var (sende tecilli, Ekim 2028)")
    if job.llm and (job.llm.get("min_years") or 0) >= 2 and not any(w.startswith("Deneyim") for w in warns):
        warns.append(f"Deneyim: ilanda {job.llm['min_years']}+ yıl isteniyor")
    for w in warns:
        lines.append(f"⚠️ {esc(w)}")
    lines.append(f'🔗 <a href="{html.escape(job.url)}">İlana git</a>')
    return "\n".join(lines)
