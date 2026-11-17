"""All tunable settings in one place: what counts as an "IT tender" and how it is tagged.

Prozorro matches the ``cpv`` filter by *exact* 10-character code ("72260000-5"),
not by prefix. So we list concrete codes of the CPV classes we care about and
let the API do an OR over them in a single query.

Why these codes
---------------
* ``72*`` IT services: software development, web/internet services, hosting,
  support, consulting, networks. This is the core of the radar.
* ``48*`` software packages and information systems: licences, ERP/CRM,
  security software.
* ``30200000`` computer equipment (hardware) is deliberately NOT included: the
  radar is about software and services work an IT company can bid for, and a
  hardware-delivery tender is a different business (resellers).
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Prozorro -------------------------------------------------------------
API_BASE = "https://prozorro.gov.ua/api"
SITE_BASE = "https://prozorro.gov.ua/uk"
USER_AGENT = "tender-radar/0.1 (open-source portfolio project; daily batch)"
PAGE_SIZE = 20  # fixed by the API

# Tenders that still accept proposals.
ACTIVE_STATUSES = ["active.enquiries", "active.tendering"]

# CPV code -> human label. Order matters only for display.
CPV_CODES: dict[str, str] = {
    # 72: IT services
    "72210000-0": "Software package programming services",
    "72211000-7": "Systems and user software programming",
    "72212000-4": "Application software programming",
    "72220000-3": "Systems and technical consultancy",
    "72230000-6": "Custom software development",
    "72231000-3": "Military software development",
    "72240000-9": "Systems analysis and programming",
    "72250000-2": "System and support services",
    "72260000-5": "Software-related services",
    "72261000-2": "Software support services",
    "72262000-9": "Software development services",
    "72263000-6": "Software implementation services",
    "72267000-4": "Software maintenance and repair",
    "72268000-1": "Software supply services",
    "72300000-8": "Data services",
    "72310000-1": "Data-processing services",
    "72320000-4": "Database services",
    "72400000-4": "Internet services",
    "72410000-7": "Provider services",
    "72413000-8": "WWW site design services",
    "72415000-2": "WWW host operation services",
    "72416000-9": "Application service providers",
    "72420000-0": "Internet development services",
    "72421000-7": "Internet or intranet client application development",
    "72422000-4": "Internet or intranet server application development",
    "72500000-0": "Computer-related services",
    "72510000-3": "Computer-related management services",
    "72590000-7": "Computer-related professional services",
    "72600000-6": "Computer support and consultancy services",
    "72610000-9": "Computer support services",
    "72611000-6": "Technical computer support services",
    "72700000-7": "Computer network services",
    "72800000-8": "Computer audit and testing services",
    "72900000-0": "Computer backup and catalogue conversion services",
    # 48: software packages and information systems
    "48000000-8": "Software package and information systems",
    "48100000-9": "Industry-specific software package",
    "48200000-0": "Networking, Internet and intranet software package",
    "48400000-2": "Business transaction and personal business software package",
    "48500000-3": "Communication and multimedia software package",
    "48600000-4": "Database and operating software package",
    "48700000-5": "Software package utilities",
    "48730000-4": "Security software package",
    "48760000-3": "Antivirus software package",
    "48800000-6": "Information systems and servers",
    "48810000-9": "Information systems",
    "48900000-7": "Miscellaneous software package and computer systems",
}

# Extra free-text queries (Prozorro search is morphological), for tenders filed
# under a "wrong" CPV. A text hit is kept only if it also scores on keywords.
TEXT_QUERIES: list[str] = ["CRM", "ERP", "кібербезпека", "хостинг", "веб-сайт"]
TEXT_ONLY_MIN_SCORE = 30  # a text hit needs two distinct keywords, one stray word is noise


# --- Categories and keywords ---------------------------------------------
@dataclass(frozen=True)
class Category:
    """A tag shown in the UI plus the terms that trigger it.

    Terms are Ukrainian words (stemmed by ``textmatch``) or English terms.
    Upper-case terms of up to 6 letters (CRM, ERP, API) match exactly.
    """

    name: str
    terms: tuple[str, ...]
    cpv_prefixes: tuple[str, ...] = ()  # CPV prefixes that imply this tag


CATEGORIES: tuple[Category, ...] = (
    Category(
        "Software dev",
        ("програмне забезпечення", "програмного забезпечення", "розробка програм", "розробка програмного",
         "розробка застосунків", "мобільний застосунок", "software", "API", "програмування"),
        ("7221", "7222", "7223", "7224", "72262", "72263"),
    ),
    Category(
        "Web",
        ("веб-сайт", "вебсайт", "сайт", "веб-портал", "веб-застосунок", "веб-додаток", "інтернет-портал", "website"),
        ("72413", "7242"),
    ),
    Category(
        "Information systems",
        ("інформаційна система", "інформаційно-комунікаційна система", "автоматизована система",
         "інформаційний ресурс", "електронний реєстр", "CRM", "ERP", "електронний документообіг", "база даних"),
        ("488", "48000", "72320", "72300"),
    ),
    Category(
        "Cloud & hosting",
        ("хмарний", "хмарні послуги", "хостинг", "дата-центр", "центр обробки даних", "cloud", "hosting", "SaaS"),
        ("72415", "72416", "72310", "72400", "72410"),
    ),
    Category(
        "Security",
        ("кібербезпека", "кіберзахист", "захист інформації", "комплексна система захисту інформації", "КСЗІ",
         "антивірус", "пентест", "SIEM", "cybersecurity"),
        ("48730", "48760"),
    ),
    Category(
        "Support & licences",
        ("технічна підтримка", "супровід програмного", "супровід", "ліцензія", "ліцензії", "оновлення програмного",
         "підтримка програмного", "технічний супровід", "ІТ-аутсорсинг", "license"),
        ("72250", "72261", "72267", "72268", "726", "72590", "725"),
    ),
)

FALLBACK_CATEGORY = "Other IT"  # used when nothing else matches

# --- Pipeline limits ------------------------------------------------------
REQUESTS_PER_MINUTE = 55  # the API allows 60; keep a safety margin
REQUEST_TIMEOUT = 20.0  # seconds, per request
MAX_RETRIES = 4
BACKOFF_BASE = 1.5  # seconds; doubles each retry
DETAIL_CONCURRENCY = 4
MAX_PAGES_PER_QUERY = 15  # 300 tenders per query is far above today's volume
EXPIRY_GRACE_DAYS = 2  # keep a tender this many days after its deadline
