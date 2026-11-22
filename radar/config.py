"""Arama kriterleri. Filtreyi değiştirmek için sadece bu dosyayı düzenlemek yeterli.

Anahtar kelimeler `models.norm` ile sadeleştirilmiş metinde aranır (küçük harf,
Türkçe karakterler ASCII). Bu yüzden burada da ASCII ve küçük harf yazılır.
Kelime sınırı gereken kısa terimler `\\b` ile regex olarak yazılır.
"""

# --- Konum ---------------------------------------------------------------
CITIES = ["konya", "karaman"]          # bu illerdeki ilanlar + uzaktan ilanlar kabul

# --- Alanlar ve CV eşlemesi ---------------------------------------------
# Sıra önceliktir: bir ilan birden çok alana uyarsa ilk eşleşen "ana alan" olur.
TRACKS = {
    "erp": {
        "label": "ERP / SAP",
        "cv": "05_ERP_SAP",
        "priority": 3,
        "patterns": [
            r"\bsap\b", r"\babap\b", r"\bfi ?/ ?co\b", r"\bfico\b", r"s/?4 ?hana", r"\bhana\b",
            r"\berp\b", r"\bodoo\b", r"\bnetsis\b", r"logo tiger", r"logo j-?platform", r"\bmikro yazilim",
            r"dynamics 365", r"microsoft dynamics", r"\bcrm\b", r"is analisti", r"business analyst",
            r"surec analisti", r"surec gelistirme", r"uygulama danismani", r"cozum danismani",
            r"functional consultant", r"technical consultant", r"\bmrp\b",
        ],
    },
    "fullstack": {
        "label": "Yazılım / Full Stack",
        "cv": "03_Full_Stack",
        "priority": 2,
        "patterns": [
            r"full ?stack", r"back ?-?end", r"front ?-?end", r"\.net\b", r"\bc#", r"asp\.net",
            r"python (developer|gelistirici|engineer|muhendis)", r"\breact\b", r"\bflutter\b",
            r"\bandroid\b", r"\bkotlin\b", r"mobil (uygulama|gelistirici|developer)",
            r"web (developer|gelistirici|yazilim)", r"yazilim (gelistirici|gelistirme|uzmani|muhendisi|developer)",
            r"software (developer|engineer|development)", r"\bdeveloper\b", r"\bgelistirici\b",
            r"\bfastapi\b", r"\bapi\b",
        ],
    },
    "data": {
        "label": "Veri Bilimi / Analitiği",
        "cv": "04_Veri_Bilimi",
        "priority": 2,
        "patterns": [
            r"veri analist", r"data analyst", r"data scien", r"veri bilim", r"veri muhendis",
            r"data engineer", r"\bbi\b", r"business intelligence", r"is zekasi", r"power ?bi",
            r"\btableau\b", r"raporlama (uzmani|analisti|sorumlusu)", r"reporting", r"\betl\b",
            r"\bsql\b", r"veri tabani", r"database",
        ],
    },
    "ai": {
        "label": "Yapay Zeka / ML",
        "cv": "02_Yapay_Zeka",
        "priority": 2,
        "patterns": [
            r"yapay zeka", r"\bai\b", r"artificial intelligence", r"machine learning", r"makine ogren",
            r"deep learning", r"derin ogren", r"\bllm\b", r"\bgenai\b", r"generative ai",
            r"computer vision", r"goruntu isleme", r"\bnlp\b", r"\bmlops\b", r"\bml\b",
        ],
    },
    "test": {
        "label": "Yazılım Test / QA",
        "cv": "06_Genel",
        "priority": 1,
        "patterns": [
            r"yazilim test", r"software test", r"test (muhendisi|uzmani|engineer|analisti|otomasyon)",
            r"\bqa\b", r"quality assurance", r"test automation",
        ],
    },
    "network": {
        "label": "Ağ / Sistem / BT Destek",
        "cv": "01_Ag_Altyapi",
        "priority": 1,
        "patterns": [
            r"\bnetwork\b", r"\bag (uzmani|muhendisi|yoneticisi|teknisyeni|sorumlusu|sistemleri|altyapi|guvenligi)", r"ag ve sistem", r"sistem (yoneticisi|uzmani|destek|muhendisi)",
            r"system admin", r"sysadmin", r"bt destek", r"it support", r"it specialist", r"help ?desk",
            r"bilgi islem", r"\bbt (uzmani|sorumlusu|personeli|teknisyeni)", r"\bcisco\b", r"\bdevops\b",
            r"siber guvenlik", r"cyber security", r"teknik destek uzmani",
            r"yardim masasi", r"end user support", r"desktop support", r"son kullanici destek",
            r"(system|technical) support (specialist|engineer|technician|analyst)", r"sistem analisti", r"hosting destek",
        ],
    },
    "general": {
        "label": "Bilişim Sistemleri (Genel)",
        "cv": "06_Genel",
        "priority": 1,
        "patterns": [
            r"bilisim sistemleri", r"bilgi sistemleri", r"information systems", r"\bbilisim\b",
            r"\byazilim\b", r"\bsoftware\b", r"bilgi teknolojileri", r"\bbt\b",
        ],
    },
}

# Başlıkta alan kelimesi yoksa, açıklamada bu güçlü terimlerden biri geçerse yine aday sayılır
# (örnek: "Satın Alma Uzmanı" ilanında "SAP MM bilen" şartı). Son kararı LLM puanı verir.
DESCRIPTION_STRONG = {
    "erp": [r"\bsap\b", r"\babap\b", r"\bodoo\b", r"s/?4 ?hana", r"\berp\b"],
    "ai": [r"yapay zeka", r"machine learning", r"makine ogrenmesi", r"\bllm\b"],
    "data": [r"power ?bi", r"\btableau\b", r"veri analizi", r"data analysis"],
    "fullstack": [r"\bpython\b", r"\bc#", r"\.net\b", r"\breact\b", r"\bflutter\b"],
}

# Yeni mezun / giriş seviyesi sinyalleri (puanı artırır)
JUNIOR_PATTERNS = [
    r"yeni mezun", r"\bjunior\b", r"\bjr\b", r"giris seviye", r"entry ?level", r"graduate",
    r"management trainee", r"\bmt\b", r"genc yetenek", r"young talent", r"kariyerine yeni",
    r"tecrubesiz", r"deneyimsiz", r"0-2 yil", r"0-1 yil", r"uzman yardimcisi", r"\bassociate\b",
    r"yetistirilmek uzere",
]

# Başlıkta bunlar varsa ilan elenir (kıdemli / yönetici / alakasız)
TITLE_EXCLUDE = [
    r"\bsenior\b", r"\bsr\b", r"kidemli", r"\blead\b", r"\blider",
    r"(?<!sistem )(?<!ag )(?<!veritabani )(?<!network )yoneticisi\b", r"\bmiddle\b", r"\bmid-?level\b", r"team lead", r"mudur", r"\bmanager\b",
    r"\bhead\b", r"direktor", r"director", r"principal", r"\barchitect\b", r"\bmimar\b", r"\bsef\b", r"chief",
    r"\bstajyer", r"\bintern\b", r"\binternship", r"\bstaj\b", r"\bstaji\b",
    r"satis temsilcisi", r"satis danismani", r"sales representative", r"cagri merkezi", r"call center",
    r"musteri temsilcisi", r"pazarlama", r"marketing", r"kalite kontrol", r"\bsofor\b", r"\bdepo\b", r"\bmuhasebe elemani\b",
]
# Başlıkta alan kelimesi yoksa (sadece açıklamadan eşleşiyorsa) ve başlık bu mesleklerden biriyse ilan elenir.
# Başlıkta IT terimi de geçen ilanlar (ör. "SAP Satın Alma Danışmanı") bundan etkilenmez.
NON_IT_TITLES = [
    r"(endustri|makine|makina|insaat|elektrik|elektronik|kimya|gida|harita|cevre|maden|metalurji|tekstil|ziraat|otomotiv|uretim|kalite|proje) muhendis",
    r"ogretmen", r"egitmen", r"insan kaynaklari", r"\bik\b", r"\bhr\b", r"muhasebe", r"finans", r"bordro",
    r"satin ?alma", r"satinalma", r"lojistik", r"\bdepo", r"uretim", r"planlama uzmani", r"teknik ressam",
    r"\bsatis\b", r"pazarlama", r"\bhemsire", r"\bdoktor", r"\beczaci", r"avukat", r"\bhukuk",
    r"operator", r"teknisyen(?!.*(bilgi|bt|it|ag|network))", r"\busta", r"\bmimar", r"tasarim", r"\bgrafik",
]

# Firma adında ya da başlıkta bunlar geçen ilanlar elenir (engelli kadrosu ilanları gibi)
COMPANY_OR_TITLE_EXCLUDE = [
    r"engelli", r"engelsiz", r"ekpss", r"ozel politika", r"disabilit", r"disabled", r"handicap",
]

# "management trainee" içindeki "manager" yanlış elemesin diye bu ifadeler muaf
TITLE_EXCLUDE_EXCEPT = [r"management trainee", r"yonetici adayi", r"manager trainee"]

# Açıklamada bu şartlar uyarı olarak işaretlenir
MILITARY_PATTERNS = [
    r"askerli[kg]\w*[^.\n]{0,40}(tamamla|yapmis|yapilmis|bitir|ilisig|muaf)",
    r"askerlik (hizmetini|gorevini) (tamamla|yapmis|bitir)",
    r"askerlik durumu[: ]+(yapildi|tamamlandi|muaf)",
    r"military service[^.\n]{0,30}(complet|exempt|fulfil)",
]

# --- Deneyim ve çalışma şekli ---------------------------------------------
# İlanda istenen deneyim bu yıl veya üstündeyse ilan gönderilmez (yeni mezun).
MAX_REQUIRED_YEARS = 2          # 2+ yıl isteyen elenir, 1 yıl isteyen uyarıyla gelir
# LinkedIn "Kıdem düzeyi" alanında bunlar varsa elenir
SENIORITY_EXCLUDE = ["orta-ust duzey", "mid-senior", "direktor", "director", "yonetici", "executive"]

# Konya/Karaman dışındaki bir ilanın "uzaktan" sayılması için açıklamada açık ifade gerekir
REMOTE_EVIDENCE = [
    r"(tamamen|%100|tam zamanli|full|fully|100%)\s*(uzaktan|remote)", r"\bremote (position|role|job|work|opportunity|first)",
    r"uzaktan (calisma (modeli|imkani|sekli)|calisacak|calisabilecek)", r"work from home", r"evden calis",
    r"home ?office", r"\b(is|calisma) (modeli|sekli)[: ]+uzaktan", r"remote[- ]only", r"\bwork(ing)? remotely\b",
]
# Bunlardan biri varsa (uzaktan ifadesi olsa bile) Konya/Karaman dışı ilan elenir
ONSITE_EVIDENCE = [
    r"\bhibrit\b", r"\bhybrid\b", r"\bon-?site\b", r"is yerinde calis", r"ofisten calis", r"ofisimizde",
    r"haftanin \d gunu ofis", r"days? (a week )?in the office",
]

# --- Kaynaklar -----------------------------------------------------------
# Her kaynak en az bu kadar dakikada bir çalışır (workflow 15 dk'da bir tetiklenir).
SOURCE_INTERVAL_MIN = {
    "linkedin": 15,
    "kariyernet": 30,
    "elemannet": 60,
    "isbul": 60,
    "youthall": 120,
}

# LinkedIn: Konya/Karaman'da tüm ilanlar + Türkiye genelinde uzaktan ilanlar (alan anahtar kelimeleriyle)
LINKEDIN_CITY_QUERIES = [
    {"keywords": "", "location": "Konya, Türkiye"},
    {"keywords": "", "location": "Karaman, Türkiye"},
]
LINKEDIN_REMOTE_KEYWORDS = [
    "SAP", "ABAP", "ERP", "Odoo",
    "yazılım geliştirici", "software developer", "full stack", "backend", ".NET", "Python",
    "veri analisti", "data analyst", "data scientist", "business intelligence",
    "yapay zeka", "machine learning",
    "test engineer", "QA",
    "network", "sistem yöneticisi",
]
LINKEDIN_PAGES_CITY = 2        # sayfa başına 10 ilan
LINKEDIN_REMOTE_PER_RUN = 6    # her turda uzaktan anahtar kelimelerden kaç tanesi dönsün (sırayla)
# Not: LinkedIn'in giriş gerektirmeyen araması "uzaktan" (f_WT) ve "deneyim" (f_E) filtrelerini yok sayıyor.
# Bu yüzden Türkiye geneli aramalardan gelen ilanlar ancak açıklamada açıkça uzaktan yazıyorsa kabul edilir.

# Kariyer.net: genel listeler sponsorlu ilanlara göre sıralandığı için anahtar kelimeyle aranır.
KARIYERNET_KEYWORDS = ["yazılım", "bilgi işlem", "sap", "erp", "veri", "yapay zeka", "bilişim",
                       "developer", "analist", "network", "test", "sistem"]
KARIYERNET_CITY_SLUGS = ["konya"]          # anahtar kelimeyle aranır (her turda birkaç kelime, sırayla)
KARIYERNET_FULL_LIST_SLUGS = ["karaman"]   # küçük il: tüm liste
KARIYERNET_KW_PER_RUN = 4                  # her turda kaç kelime (konya + remote için ayrı ayrı)

ELEMANNET_PATHS = ["/is-ilanlari/konya", "/is-ilanlari/karaman"]
ISBUL_PATHS = ["/is-ilanlari/konya", "/is-ilanlari/karaman"]

# --- Bildirim -----------------------------------------------------------
# LLM bir ilanı açıkça alakasız bulursa (bu puanın altı) gönderilmez, günlük özette sayılır.
LLM_DROP_BELOW = 40
FIRST_RUN_MAX_AGE_HOURS = 72    # ilk çalışmada sadece son 3 günün ilanları gönderilir
DAILY_SUMMARY_HOUR = 21         # Türkiye saati
TIMEZONE = "Europe/Istanbul"
SEEN_RETENTION_DAYS = 60
