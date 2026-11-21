"""Parser ve eşleştirme testleri: GitHub Actions sunucusundan alınmış gerçek sayfa örnekleriyle."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from radar import config, main, matching
from radar.models import Job, norm
from radar.sources import age_from_text, elemannet, isbul, kariyernet, linkedin, youthall
from radar.state import State
from radar.telegram import format_job

FX = Path(__file__).parent / "fixtures"


def fx(name: str) -> str:
    return gzip.decompress((FX / f"{name}.html.gz").read_bytes()).decode("utf-8")


def job(title, location="Konya", desc="", mode="", source="kariyernet", sid="1", company="Firma"):
    return Job(source=source, source_id=sid, title=title, company=company, location=location,
               url="https://example.com/x", work_mode=mode, description=desc)


# ------------------------------------------------------------------ parser'lar

def test_linkedin_search():
    jobs = linkedin.parse_search(fx("linkedin_tr_sap"))
    assert len(jobs) == 10
    j = jobs[0]
    assert j.title == "SAP ABAP Geliştirme Uzmanı"
    assert j.source_id.isdigit() and j.url.endswith(f"/jobs/view/{j.source_id}/")
    assert j.location.endswith("Türkiye") and j.age_hours is not None


def test_linkedin_remote_flag():
    # LinkedIn uzaktan filtresini yok saydığı için kart "uzaktan" sayılmaz, sadece doğrulama için işaretlenir
    jobs = linkedin.parse_search(fx("linkedin_tr_sap"), remote=True)
    assert all(j.extra.get("remote_query") and not j.is_remote for j in jobs)


def test_linkedin_detail():
    d = linkedin.parse_detail(fx("linkedin_detail"))
    assert len(d["description"]) > 100
    assert d["criteria"]


def test_kariyernet_list():
    jobs = kariyernet.parse_list(fx("kariyernet_konya"))
    assert len(jobs) >= 40
    assert all(j.source_id.isdigit() for j in jobs)
    assert all(j.url.startswith("https://www.kariyer.net/is-ilani/") for j in jobs)
    assert {j.work_mode for j in jobs} <= {"İş Yerinde", "Hibrit", "Uzaktan / Remote", ""}
    assert sum(1 for j in jobs if "Konya" in j.location) > 30
    assert all(j.title and j.company for j in jobs)


def test_kariyernet_detail():
    d = kariyernet.parse_detail(fx("kariyernet_detail"))
    assert len(d) > 300
    assert d.startswith("Aday Kriterleri: Tecrübe: En az 5 yıl tecrübeli")
    w = matching.warnings_for(job("Bakım Ustası", desc=d))
    assert any(x.startswith("Askerlik") for x in w) and any("5 yıl" in x for x in w)


def test_elemannet_list():
    jobs = elemannet.parse_list(fx("eleman_net"))
    assert len(jobs) >= 20
    assert all(j.title and j.url.startswith("https://www.eleman.net/is-ilani/") for j in jobs)
    assert sum(1 for j in jobs if "Konya" in j.location) > 15


def test_isbul_list():
    jobs = isbul.parse_list(fx("isbul"))
    assert len(jobs) >= 15
    assert any(j.work_mode == "Uzaktan" for j in jobs)
    assert all(j.url.startswith("https://isbul.net/is-ilani/") for j in jobs)


def test_youthall_list():
    jobs = youthall.parse_list(fx("youthall_jobs"))
    assert len(jobs) >= 5
    assert all("youthall.com/tr/" in j.url and j.title for j in jobs)


@pytest.mark.parametrize("text,hours", [("4 saat", 4), ("1 gün", 24), ("5 gün önce", 120),
                                        ("2 hafta önce", 336), ("Bugün", 6), ("30 dakika", 0.5)])
def test_age(text, hours):
    assert age_from_text(text) == pytest.approx(hours)


# ------------------------------------------------------------------ eşleştirme

def test_norm_turkish():
    assert norm("İŞ ANALİSTİ Yazılım Geliştirici") == "is analisti yazilim gelistirici"


@pytest.mark.parametrize("title,track", [
    ("SAP ABAP Geliştirme Uzmanı", "erp"),
    ("SAP FI/CO Danışmanı", "erp"),
    ("Odoo ERP Uygulama Uzmanı", "erp"),
    ("İş Analisti", "erp"),
    ("Full Stack Developer", "fullstack"),
    (".NET Yazılım Geliştirici", "fullstack"),
    ("Veri Analisti", "data"),
    ("Power BI Raporlama Uzmanı", "data"),
    ("Yapay Zeka Mühendisi", "ai"),
    ("Yazılım Test Uzmanı", "test"),
    ("Sistem Yöneticisi", "network"),
    ("Bilgi İşlem Personeli", "network"),
])
def test_tracks(title, track):
    j = job(title)
    assert matching.classify(j)
    assert j.tracks[0] == track


@pytest.mark.parametrize("title", [
    "Senior SAP Specialist", "Kıdemli Yazılım Geliştirici", "Bilgi İşlem Müdürü",
    "Satış Temsilcisi", "Kalite Kontrol Uzmanı", "IT Infrastructure Internship", "Team Lead - Backend",
    "SAP Public Cloud Geliştirme ve Proje Lideri", "Veri Bilimcisi - İleri Analitik Yöneticisi",
    "Middle Software Engineer - Backend", "İnsan Kaynakları Stajyeri", "Proje Yönetim Stajyeri",
])
def test_title_excluded(title):
    assert matching.title_excluded(job(title))


def test_system_admin_not_excluded():
    assert not matching.title_excluded(job("Sistem Yöneticisi"))


@pytest.mark.parametrize("title", [
    "Software Engineer - Open To People With Disabilities (All Roles and Experience Levels)",
    "Software Engineer - Open To People With Disabilities",
    "Engelli Kadrosu - Yazılım Uzmanı",
    "Bilgi İşlem Personeli (EKPSS)",
])
def test_disability_quota_titles_excluded(title):
    assert matching.title_excluded(job(title))


def test_inclusive_statement_in_description_not_excluded():
    j = job("Yazılım Geliştirici", desc="We welcome applications from people with disabilities.")
    assert not matching.title_excluded(j) and matching.classify(j)


def test_company_exclude():
    assert matching.title_excluded(job("Yazılım Mühendisi", company="Omuz Omuza Engelsiz İnsan Kaynakları"))


def test_management_trainee_not_excluded():
    assert not matching.title_excluded(job("Management Trainee - IT"))


def test_location_rules():
    assert matching.location_ok(job("x", "Konya, Türkiye"))
    assert matching.location_ok(job("x", "Karaman - Merkez"))
    assert matching.location_ok(job("x", "İstanbul", mode="Uzaktan / Remote"))
    assert not matching.location_ok(job("x", "İstanbul, Türkiye"))
    assert not matching.location_ok(job("x", "Ankara", mode="Hibrit"))


def li_remote(title, desc, **kw):
    j = job(title, location="İstanbul, Türkiye", desc=desc, source="linkedin", **kw)
    j.extra["remote_query"] = True
    return j


def test_linkedin_remote_needs_evidence():
    assert matching.location_ok(li_remote("Yazılım Geliştirici", ""))
    assert not matching.classify(li_remote("Yazılım Geliştirici", "İstanbul ofisimizde çalışacak"))
    assert not matching.classify(li_remote("Yazılım Geliştirici", "Hibrit çalışma modeli, tamamen uzaktan değil"))
    ok = li_remote("Yazılım Geliştirici", "Bu pozisyon tamamen uzaktan çalışma modelindedir.")
    assert matching.classify(ok) and ok.work_mode == "Uzaktan"
    assert matching.classify(li_remote("Backend Developer", "This is a fully remote position."))


def test_site_remote_field_trusted():
    j = job("Yazılım Test Mühendisi", location="Adana", mode="Uzaktan / Remote")
    assert matching.classify(j)


def test_experience_rejected():
    j = job("Yazılım Geliştirici", desc="En az 3 yıl yazılım geliştirme deneyimi")
    assert not matching.classify(j) and "3+ yıl" in j.extra["reject"]
    j = job("SAP Uzmanı", source="linkedin")
    j.extra["seniority"] = "Orta-Üst Düzey Yönetici"
    assert not matching.classify(j) and j.extra["reject"].startswith("kıdem")


def test_one_year_allowed_with_warning():
    j = job("Yazılım Geliştirici", desc="En az 1 yıl deneyimli")
    assert matching.classify(j)


def test_entry_level_kept():
    j = job("Ağ Sistemleri Uzmanı", source="linkedin")
    j.extra["seniority"] = "Başlangıç Seviye"
    assert matching.classify(j)


def test_irrelevant_not_candidate():
    assert not matching.classify(job("Garson", desc="Restoranımızda çalışacak garson arıyoruz."))


def test_description_strong_term():
    j = job("Sistem Destek Elemanı", desc="SAP kullanıcı desteği verecek")
    assert matching.classify(j)
    j = job("Kurumsal Uygulamalar Uzmanı", desc="SAP MM modülünü aktif kullanabilen")
    assert matching.classify(j) and j.tracks == ["erp"]
    assert j.extra["track_from"] == "description"


@pytest.mark.parametrize("title", ["Endüstri Mühendisi", "Satın Alma Uzmanı", "Bordro Uzmanı",
                                   "Matematik Öğretmeni", "İnsan Kaynakları Uzmanı", "Satış Uzmanı"])
def test_non_it_title_rejected_even_with_sap(title):
    j = job(title, desc="SAP ve ERP sistemlerini kullanabilen, yapay zeka araçlarına hakim")
    assert not matching.classify(j) and j.extra["reject"] == "alan dışı meslek"


def test_it_title_with_business_word_kept():
    assert matching.classify(job("SAP Satın Alma Danışmanı"))
    assert matching.classify(job("Üretim Planlama ERP Uzmanı"))


def test_warnings():
    d = ("En az 3 yıl deneyimli, askerlik hizmetini tamamlamış, ileri düzeyde İngilizce bilen")
    w = matching.warnings_for(job("Yazılım Geliştirici", desc=d))
    assert any(x.startswith("Askerlik") for x in w)
    assert any("3 yıl" in x for x in w)
    assert any(x.startswith("Dil") for x in w)


def test_junior_scores_higher():
    a, b = job("Yazılım Geliştirici", desc="yeni mezun"), job("Yazılım Geliştirici", desc="5 yıl deneyimli")
    matching.classify(a), matching.classify(b)
    assert a.rule_score > b.rule_score


def test_erp_priority_over_general():
    a, b = job("SAP Uzmanı"), job("Yazılım Uzmanı")
    matching.classify(a), matching.classify(b)
    assert a.rule_score > b.rule_score


def test_format_job_escapes_and_warns():
    j = job("SAP <ABAP> & Fiori", desc="askerliğini tamamlamış")
    matching.classify(j)
    msg = format_job(j)
    assert "&lt;ABAP&gt; &amp; Fiori" in msg
    assert "⚠️ Askerlik" in msg and "05_ERP_SAP" in msg


# ------------------------------------------------------------------ uçtan uca (ağ yok)

def test_end_to_end_offline(tmp_path, monkeypatch, capsys):
    pages = {
        "seeMoreJobPostings": fx("linkedin_konya"),
        "jobPosting/": fx("linkedin_detail"),
        "kariyer.net/is-ilanlari": fx("kariyernet_konya"),
        "eleman.net/is-ilanlari": fx("eleman_net"),
        "isbul.net/is-ilanlari": fx("isbul"),
        "youthall.com/tr/jobs": fx("youthall_jobs"),
    }

    def fake_get(url, **kw):
        for k, v in pages.items():
            if k in url:
                return v
        return "<html></html>"  # detay sayfaları: JSON-LD yok

    monkeypatch.setattr("radar.http.get", fake_get)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    main.main()
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["seen"], "ilanlar işaretlenmeli"
    assert all(s["last_ok"] for s in data["sources"].values())
    # ikinci tur: aynı ilanlar tekrar gönderilmez
    sent_before = sum(1 for v in data["seen"].values() if v["status"] == "sent")
    monkeypatch.setenv("FORCE_ALL", "1")
    main.main()
    data2 = json.loads((tmp_path / "state.json").read_text())
    assert sum(1 for v in data2["seen"].values() if v["status"] == "sent") == sent_before


def test_state_prune(tmp_path):
    st = State(tmp_path / "s.json")
    old, keep = job("a", sid="1"), job("b", sid="2")
    st.mark(old, "skip"), st.mark(keep, "saved")
    for v in st.data["seen"].values():
        v["t"] = 0
    st.save()
    assert list(st.data["seen"]) == [keep.uid]
    assert config.SEEN_RETENTION_DAYS > 0


def test_pending_when_llm_down(tmp_path, monkeypatch):
    """LLM çalışmazsa: başlıktan eşleşen gönderilir, sadece açıklamadan eşleşen bekletilir."""
    from radar import llm
    st = State(tmp_path / "s.json")
    st.mark(job("eski", sid="0", company="eski"), "skip")   # ilk çalışma değil
    a = job("SAP ABAP Uzmanı", sid="1")
    b = job("Kurumsal Uygulamalar Uzmanı", desc="SAP MM bilen", sid="2", company="Başka")
    sent = []

    class FakeTg:
        enabled = True
        def send(self, text, buttons=None, silent=False):
            sent.append(text)
            return {"message_id": 1}

    for j in (a, b):
        assert matching.classify(j)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm, "evaluate", lambda jobs, log=print, feedback=None: 0)
    monkeypatch.setattr(main, "SOURCES", {"fake": type("M", (), {"fetch": staticmethod(lambda ctx: [a, b]),
                                                                  "enrich": staticmethod(lambda j: None)})})
    monkeypatch.setitem(config.SOURCE_INTERVAL_MIN, "fake", 15)
    monkeypatch.setitem(main.SOURCE_LABEL, "fake", "Fake")
    main.scan(st, FakeTg())
    assert len(sent) == 1 and "SAP ABAP" in sent[0]
    assert b.uid in st.data["pending"] and st.data["seen"][b.uid]["status"] == "pending"

    # sonraki tur: LLM düzeldi, bekleyen ilan değerlendirilip gönderilir
    def ok(jobs, log=print, feedback=None):
        for j in jobs:
            j.llm = {"score": 55, "cv": "05_ERP_SAP", "summary": "s", "why": "w", "gaps": "-",
                     "military_required": False, "min_years": 0}
        return len(jobs)
    monkeypatch.setattr(llm, "evaluate", ok)
    st.source("fake")["last_run"] = 0
    main.scan(st, FakeTg())
    assert len(sent) == 2 and "Kurumsal Uygulamalar" in sent[1]
    assert not st.data["pending"]


def test_model_discovery(monkeypatch):
    from radar import llm

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"models": [
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
            ]}
    monkeypatch.setattr(llm, "_models_cache", None)
    monkeypatch.setattr(llm, "MODELS_ENV", [])
    monkeypatch.setattr(llm.requests, "get", lambda *a, **k: R())
    assert llm.available_models("k", log=lambda m: None) == ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"]


def test_feedback_reaches_prompt(tmp_path, monkeypatch):
    from radar import llm
    st = State(tmp_path / "s.json")
    bad, good = job("Çağrı Merkezi Destek", sid="9", company="X"), job("SAP ABAP Uzmanı", sid="8", company="Y")
    st.mark(bad), st.mark(good)
    for j, action in ((bad, "x"), (good, "a")):
        cq = {"id": "1", "data": f"{action}:{j.uid}", "message": {"message_id": 5, "chat": {"id": 1}}}
        main.handle_callback(st, type("T", (), {"answer_callback": lambda *a: None,
                                                "set_buttons": lambda *a: None})(), cq)
    fb = main.feedback_examples(st)
    assert fb == {"bad": ["Çağrı Merkezi Destek (X)"], "good": ["SAP ABAP Uzmanı (Y)"]}

    captured = {}
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(llm, "available_models", lambda key, log=print: ["m"])
    def fake_call(model, key, prompt):
        captured["p"] = prompt
        return []
    monkeypatch.setattr(llm, "_call", fake_call)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    llm.evaluate([job("Yeni İlan")], log=lambda m: None, feedback=fb)
    assert "İlgisiz bulduğu ilanlar" in captured["p"] and "Çağrı Merkezi Destek (X)" in captured["p"]
    assert "SAP ABAP Uzmanı (Y)" in captured["p"]

    # işaretli ilanlar eski olsa da silinmez (örnek olarak kalır)
    for v in st.data["seen"].values():
        v["t"] = 0
    st.prune()
    assert bad.uid in st.data["seen"]


def test_details_stored_for_review(tmp_path):
    st = State(tmp_path / "s.json")
    j = job("SAP ABAP Uzmanı", desc="Uzun açıklama " * 50, sid="5")
    matching.classify(j)
    j.llm = {"score": 70, "cv": "05_ERP_SAP", "summary": "özet", "why": "w", "gaps": "-",
             "military_required": False, "min_years": 0, "work_mode": "onsite"}
    st.mark(j, "sent", score=70)
    d = st.data["details"][j.uid]
    assert d["llm"]["summary"] == "özet" and d["location"] == "Konya" and d["tracks"] == ["erp"]
    assert 0 < len(d["description"]) <= 2500
    irrelevant = job("Garson", sid="6")
    st.mark(irrelevant, "skip")
    assert irrelevant.uid not in st.data["details"]          # alakasız atlamalar saklanmaz
    rej = job("Yazılım Geliştirici", desc="En az 5 yıl deneyim", sid="7")
    assert not matching.classify(rej)
    st.mark(rej, "skip")
    assert st.data["details"][rej.uid]["reject"].startswith("5+")   # gerekçeli elemeler saklanır
    st.save()
    assert State(tmp_path / "s.json").data["details"][j.uid]["llm"]["cv"] == "05_ERP_SAP"


def test_reset_seen_keeps_feedback(tmp_path):
    st = State(tmp_path / "s.json")
    a, b = job("SAP Uzmanı", sid="1"), job("Veri Analisti", sid="2")
    st.mark(a), st.mark(b)
    st.data["seen"][b.uid].update(status="irrelevant", fb_t=1.0)
    st.source("linkedin")["last_run"] = 123
    assert not st.first_run
    assert st.reset_seen() == 1
    assert a.uid not in st.data["seen"] and b.uid in st.data["seen"]
    assert st.first_run and st.source("linkedin")["last_run"] == 0
    assert not st.is_seen(a.uid, a.dedupe_key)


@pytest.mark.parametrize("text,years", [
    ("Aday Kriterleri: Tecrübe: 1-15 yıl tecrübeli", 1),
    ("Tecrübe: En az 1 yıl, en fazla 15 yıl tecrübeli", 1),
    ("Tecrübe: En az 5 yıl tecrübeli", 5),
    ("0-2 yıl deneyimli adaylar", None),
    ("en az 3 yıl deneyim, en fazla 10 yıl", 3),
    ("3-5 years of experience", 3),
    ("Tecrübe: Tecrübesiz", None),
])
def test_required_years_ranges(text, years):
    assert matching.required_years(text) == years


def test_migration_reopens_experience_rejections(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"version": 1, "seen": {
        "kariyernet:1": {"t": 1e12, "title": "Bilgi İşlem Uzmanı", "status": "skip", "why": "15+ yıl deneyim"},
        "kariyernet:2": {"t": 1e12, "title": "Garson", "status": "skip"}},
        "dedupe": {"a": "kariyernet:1", "b": "kariyernet:2"}}), encoding="utf-8")
    st = State(p)
    assert "kariyernet:1" not in st.data["seen"] and "kariyernet:2" in st.data["seen"]
    assert st.data["dedupe"] == {"b": "kariyernet:2"} and st.data["version"] == 2


def test_kariyernet_partial_block_tolerated(monkeypatch):
    from radar import http as h
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        if "karaman" in url:
            raise h.FetchError(f"{url} -> HTTP 403")
        return fx("kariyernet_konya")
    monkeypatch.setattr("radar.http.get", fake_get)
    ctx = {}
    jobs = kariyernet.fetch(ctx)
    assert jobs and len(calls) == 1 + 2 * config.KARIYERNET_KW_PER_RUN
    assert ctx["partial_errors"] and "403" in ctx["partial_errors"][0]


def test_kariyernet_all_blocked_raises(monkeypatch):
    from radar import http as h
    monkeypatch.setattr("radar.http.get", lambda url, **kw: (_ for _ in ()).throw(h.FetchError("403")))
    with pytest.raises(h.FetchError):
        kariyernet.fetch({})


def test_remote_reject_only_counts_relevant():
    j = job("Garson", location="İstanbul, Türkiye", source="linkedin")
    j.extra["remote_query"] = True
    assert not matching.classify(j) and "reject" not in j.extra


def test_dedupe_ignores_parenthetical():
    a = job("Software Engineer - Open To X (All Roles and Experience Levels)", sid="1", company="EPAM")
    b = job("Software Engineer - Open To X", sid="2", company="EPAM")
    assert a.dedupe_key == b.dedupe_key
