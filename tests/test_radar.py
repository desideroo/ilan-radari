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
    jobs = linkedin.parse_search(fx("linkedin_tr_sap"), remote=True)
    assert all(j.is_remote for j in jobs)


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
])
def test_title_excluded(title):
    assert matching.title_excluded(job(title))


def test_management_trainee_not_excluded():
    assert not matching.title_excluded(job("Management Trainee - IT"))


def test_location_rules():
    assert matching.location_ok(job("x", "Konya, Türkiye"))
    assert matching.location_ok(job("x", "Karaman - Merkez"))
    assert matching.location_ok(job("x", "İstanbul", mode="Uzaktan / Remote"))
    assert not matching.location_ok(job("x", "İstanbul, Türkiye"))
    assert not matching.location_ok(job("x", "Ankara", mode="Hibrit"))


def test_irrelevant_not_candidate():
    assert not matching.classify(job("Garson", desc="Restoranımızda çalışacak garson arıyoruz."))


def test_description_strong_term():
    j = job("Satın Alma Uzmanı", desc="SAP MM modülünü aktif kullanabilen")
    assert matching.classify(j) and j.tracks == ["erp"]
    assert j.extra["track_from"] == "description"


def test_warnings():
    d = ("En az 3 yıl deneyimli, askerlik hizmetini tamamlamış, ileri düzeyde İngilizce bilen")
    w = matching.warnings_for(job("Yazılım Geliştirici", desc=d))
    assert any(x.startswith("Askerlik") for x in w)
    assert any("3+ yıl" in x for x in w)
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
