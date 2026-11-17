from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field


def norm(text: str) -> str:
    """Küçük harf, Türkçe karakterleri sadeleştir, fazla boşlukları at."""
    text = (text or "").replace("İ", "i").replace("I", "ı").lower()
    text = text.translate(str.maketrans("ığüşöçâîû", "igusocaiu"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    location: str
    url: str
    work_mode: str = ""          # "Uzaktan", "Hibrit", "İş Yerinde" ya da boş
    posted: str = ""             # "2026-11-12" ya da "4 saat" gibi ham metin
    age_hours: float | None = None
    snippet: str = ""
    description: str = ""
    extra: dict = field(default_factory=dict)

    # eşleştirme sonuçları
    tracks: list[str] = field(default_factory=list)
    rule_score: int = 0
    llm: dict | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def dedupe_key(self) -> str:
        raw = norm(self.company) + "|" + norm(self.title)
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    @property
    def is_remote(self) -> bool:
        blob = norm(f"{self.work_mode} {self.location}")
        return "uzaktan" in blob or "remote" in blob

    def text_blob(self) -> str:
        return norm(" ".join([self.title, self.company, self.snippet, self.description]))
