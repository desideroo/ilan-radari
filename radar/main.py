"""Tek tur: komutları işle, zamanı gelen kaynakları tara, uygun ilanları Telegram'a gönder."""

from __future__ import annotations

import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dataclasses import asdict

from . import config, llm, matching
from .models import Job
from .sources import elemannet, isbul, kariyernet, linkedin, youthall
from .state import State
from .telegram import SOURCE_LABEL, Telegram, esc, format_job, job_buttons

SOURCES = {m.NAME: m for m in (linkedin, kariyernet, elemannet, isbul, youthall)}
TZ = ZoneInfo(config.TIMEZONE)
MAX_SEND_PER_RUN = 60
PENDING_MAX_H = 12   # LLM bu süre içinde değerlendiremezse açıklama-eşleşmeli ilan düşürülür


_LOG: list[str] = []
SEED_ONLY = os.getenv("SEED_ONLY") == "1"


def log(msg: str) -> None:
    line = f"[{datetime.now(TZ):%H:%M:%S}] {msg}"
    _LOG.append(line)
    print(line, flush=True)


def write_summary() -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("```\n" + "\n".join(_LOG) + "\n```\n")


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- Telegram girdileri

HELP = (
    "<b>İlan Radarı</b> komutları:\n"
    "/durum: sistem ve kaynak durumu\n"
    "/bugun: bugünün özeti\n"
    "/kaydedilenler: ⭐ ile kaydettiğin ilanlar\n"
    "/duraklat, /devam: bildirimleri durdur/başlat\n\n"
    "İlanlardaki butonlar ve komutlar en geç ~15 dakika içinde işlenir."
)


def handle_updates(st: State, tg: Telegram) -> None:
    if not tg.enabled:
        return
    try:
        ups = tg.updates(st.data["tg_offset"])
    except RuntimeError as e:
        log(f"getUpdates hata: {e}")
        return
    for u in ups:
        st.data["tg_offset"] = u["update_id"] + 1
        if "callback_query" in u:
            cq = u["callback_query"]
            if str(cq.get("message", {}).get("chat", {}).get("id")) != tg.chat_id:
                continue
            handle_callback(st, tg, cq)
        elif "message" in u:
            m = u["message"]
            if str(m.get("chat", {}).get("id")) != tg.chat_id:
                continue  # sadece sahibine cevap ver
            handle_command(st, tg, (m.get("text") or "").strip().split("@")[0].lower())


def handle_callback(st: State, tg: Telegram, cq: dict) -> None:
    data = cq.get("data", "")
    action, _, uid = data.partition(":")
    rec = st.data["seen"].get(uid)
    if not rec or action == "u":
        tg.answer_callback(cq["id"], "Tamam")
        return
    status = {"a": "applied", "s": "saved", "x": "irrelevant"}.get(action)
    if not status:
        return
    rec["status"] = status
    st.day(today())[status] = st.day(today()).get(status, 0) + 1
    tg.answer_callback(cq["id"], {"applied": "Başvuru kaydedildi ✅", "saved": "Kaydedildi ⭐",
                                  "irrelevant": "İlgisiz olarak işaretlendi"}[status])
    tg.set_buttons(cq["message"]["message_id"], job_buttons(uid, status))


def status_text(st: State) -> str:
    lines = [f"<b>Durum:</b> {'⏸ duraklatıldı' if st.data['paused'] else '▶️ çalışıyor'}"]
    now = time.time()
    for name in SOURCES:
        s = st.source(name)
        ok = s.get("last_ok") or 0
        ago = f"{int((now - ok) / 60)} dk önce" if ok else "henüz yok"
        icon = "✅" if s.get("fails", 0) == 0 and ok else ("⚠️" if s.get("fails", 0) < 3 else "❌")
        extra = f" · {s['fails']} hata: {esc(s.get('last_error', '')[:80])}" if s.get("fails") else ""
        lines.append(f"{icon} {SOURCE_LABEL[name]}: son başarılı tarama {ago}{extra}")
    seen = st.data["seen"]
    lines.append(f"\nTakip edilen ilan: {len(seen)} · gönderilen: {sum(1 for v in seen.values() if v.get('status') in ('sent', 'saved', 'applied', 'irrelevant'))}")
    return "\n".join(lines)


def day_text(st: State, key: str, title: str) -> str:
    d = st.day(key)
    lines = [f"<b>{title}</b>",
             f"📨 Gönderilen ilan: {d['sent']}",
             f"✅ Başvuru: {d.get('applied', 0)} · ⭐ Kaydedilen: {d.get('saved', 0)} · ❌ İlgisiz: {d.get('irrelevant', 0)}",
             f"🔎 Aday ilan: {d['candidates']} (LLM'in alakasız bulduğu {d['dropped']} ilan gönderilmedi)"]
    start = datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=TZ).timestamp()
    sent = sorted([v for v in st.data["seen"].values()
                   if v.get("t", 0) >= start and v.get("status") in ("sent", "saved", "applied")],
                  key=lambda v: -(v.get("score") or 0))[:10]
    if sent:
        lines.append("\nEn yüksek puanlılar:")
        for v in sent:
            lines.append(f"• {v.get('score') or '-'} · <a href=\"{esc(v['url'])}\">{esc(v['title'])}</a> · {esc(v['company'])}")
    return "\n".join(lines)


def handle_command(st: State, tg: Telegram, cmd: str) -> None:
    if cmd in ("/start", "/yardim", "/help"):
        tg.send(HELP)
    elif cmd == "/durum":
        tg.send(status_text(st))
    elif cmd == "/bugun":
        tg.send(day_text(st, today(), "Bugün"))
    elif cmd == "/kaydedilenler":
        items = [v for v in st.data["seen"].values() if v.get("status") == "saved"]
        if not items:
            tg.send("Kaydedilmiş ilan yok.")
        else:
            tg.send("<b>⭐ Kaydedilenler</b>\n" + "\n".join(
                f"• <a href=\"{esc(v['url'])}\">{esc(v['title'])}</a> · {esc(v['company'])}" for v in items[-30:]))
    elif cmd == "/duraklat":
        st.data["paused"] = True
        tg.send("⏸ Bildirimler durduruldu. Tekrar başlatmak için /devam")
    elif cmd == "/devam":
        st.data["paused"] = False
        tg.send("▶️ Bildirimler yeniden başladı.")


# ---------------------------------------------------------------- tarama

def due(st: State, name: str) -> bool:
    if os.getenv("FORCE_ALL") == "1":
        return True
    s = st.source(name)
    return time.time() - s.get("last_run", 0) >= config.SOURCE_INTERVAL_MIN[name] * 60 - 90


def health(st: State, tg: Telegram, name: str, ok: bool, err: str = "") -> None:
    s = st.source(name)
    s["last_run"] = time.time()
    if ok:
        if s.get("alerted"):
            tg.send(f"✅ {SOURCE_LABEL[name]} yeniden çalışıyor.", silent=True)
        s.update(fails=0, last_error="", last_ok=time.time(), alerted=False)
    else:
        s["fails"] = s.get("fails", 0) + 1
        s["last_error"] = err
        if s["fails"] >= 3 and not s.get("alerted"):
            tg.send(f"⚠️ {SOURCE_LABEL[name]} {s['fails']} turdur taranamıyor: {esc(err[:200])}\n"
                    "Diğer kaynaklar çalışmaya devam ediyor.")
            s["alerted"] = True


def scan(st: State, tg: Telegram) -> None:
    first = st.first_run
    if first:
        log("İlk çalışma: son 3 günün ilanları gönderilecek.")
    candidates = []
    for name, mod in SOURCES.items():
        if not due(st, name):
            continue
        s = st.source(name)
        ctx = s.setdefault("ctx", {})
        ctx["first_run"] = first
        t0 = time.time()
        try:
            listing = mod.fetch(ctx)
        except Exception as e:  # noqa: BLE001
            log(f"{name}: HATA {e}")
            health(st, tg, name, False, str(e))
            continue
        ctx.pop("first_run", None)
        if not listing and name != "youthall":
            health(st, tg, name, False, "0 ilan döndü (sayfa yapısı değişmiş olabilir)")
            continue
        health(st, tg, name, True)

        new = []
        for j in listing:
            if st.is_seen(j.uid, j.dedupe_key) or any(j.uid == c.uid for c in new):
                continue
            if not matching.prefilter(j):
                st.mark(j, "skip")
                continue
            if first and j.age_hours is not None and j.age_hours > config.FIRST_RUN_MAX_AGE_HOURS:
                st.mark(j, "skip")
                continue
            new.append(j)
        log(f"{name}: {len(listing)} ilan, {len(new)} yeni aday (ön filtre sonrası), {time.time() - t0:.0f} sn")

        enriched = 0
        for j in new:
            if first and not matching.title_tracks(j):
                st.mark(j, "skip")      # ilk turda başlığı alakasızların detayına bakma
                continue
            if enriched < (60 if first else 30):
                try:
                    mod.enrich(j)
                    enriched += 1
                except Exception as e:  # noqa: BLE001
                    log(f"{name}: detay alınamadı {j.url}: {e}")
            if matching.classify(j):
                candidates.append(j)
            else:
                st.mark(j, "skip")

    # LLM'in değerlendiremediği, sadece açıklamadan eşleşen ilanlar bekletilir ve sonraki turlarda tekrar denenir
    pending = st.data.setdefault("pending", {})
    n_new = len(candidates)
    now = time.time()
    for uid, rec in list(pending.items()):
        if now - rec["t"] > PENDING_MAX_H * 3600:
            del pending[uid]
            st.data["seen"].get(uid, {})["status"] = "dropped"
            st.day(today())["dropped"] += 1
        elif not SEED_ONLY:
            candidates.append(Job(**rec["job"]))
    if not candidates:
        return
    if SEED_ONLY:
        for j in candidates:
            st.mark(j, "sent", score=j.rule_score)
        log(f"Tohumlama: {len(candidates)} aday gönderilmeden işaretlendi")
        return
    st.day(today())["candidates"] += n_new
    n = llm.evaluate(candidates, log=log)
    log(f"LLM ile değerlendirilen: {n}/{len(candidates)}")

    candidates.sort(key=lambda j: -(j.llm["score"] if j.llm else j.rule_score))
    sent = 0
    llm_on = bool(os.getenv("GEMINI_API_KEY", "").strip())
    for j in candidates:
        if not j.llm and llm_on and j.extra.get("track_from") == "description":
            if j.uid not in pending:
                pending[j.uid] = {"t": time.time(), "job": asdict(j)}
                st.mark(j, "pending", score=j.rule_score)
            continue
        pending.pop(j.uid, None)
        sc = j.llm["score"] if j.llm else j.rule_score
        if j.llm and sc < config.LLM_DROP_BELOW:
            st.mark(j, "dropped", score=sc)
            st.day(today())["dropped"] += 1
            continue
        if sent >= MAX_SEND_PER_RUN:
            break  # işaretlenmedi: sonraki turda tekrar gelir
        try:
            res = tg.send(format_job(j), job_buttons(j.uid)) if tg.enabled else None
        except RuntimeError as e:
            log(f"Gönderilemedi: {e}")
            continue
        if not tg.enabled:
            print("----\n" + format_job(j))
        st.mark(j, "sent", msg_id=(res or {}).get("message_id"), score=sc)
        st.day(today())["sent"] += 1
        sent += 1
    log(f"Gönderilen: {sent}")


def daily_summary(st: State, tg: Telegram) -> None:
    now = datetime.now(TZ)
    key = now.strftime("%Y-%m-%d")
    if now.hour >= config.DAILY_SUMMARY_HOUR and st.data["last_summary"] != key:
        tg.send(day_text(st, key, f"🗓 Günlük özet ({now:%d.%m.%Y})"), silent=True)
        st.data["last_summary"] = key


def main() -> None:
    state_path = Path(os.getenv("STATE_PATH", "state/state.json"))
    st = State(state_path)
    tg = Telegram()
    if not tg.enabled:
        if os.getenv("GITHUB_ACTIONS") == "true":
            # Secrets girilmeden ilanları "görüldü" sayarsak sonra hiç gönderilmezler
            log("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID secret'ları yok: tarama atlandı.")
            return
        log("Telegram ayarlı değil: ilanlar sadece loga yazılacak.")
    first = st.first_run
    try:
        if first and tg.enabled and not SEED_ONLY:
            tg.set_commands()
            tg.send("👋 <b>İlan Radarı</b> kuruldu. İlk taramada son 3 günün uygun ilanlarını gönderiyorum, "
                    "sonrasında yeni ilanlar geldikçe haber vereceğim.\n\n" + HELP)
        handle_updates(st, tg)
        if not st.data["paused"]:
            scan(st, tg)
        handle_updates(st, tg)
        daily_summary(st, tg)
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        raise
    finally:
        st.save()
        write_summary()


if __name__ == "__main__":
    main()
