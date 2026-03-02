import os
import csv
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; SchoolRegistryBot/1.0; +https://github.com/your/repo)"
TIMEOUT = 25
SLEEP_SEC = 0.4

# --- Regexes ---
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(\+7|8)\s*\(?\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")

# Реквизиты (ищем только опубликованные на сайте)
INN_RE = re.compile(r"\b(?:ИНН|INN)\s*[:№]?\s*(\d{10}|\d{12})\b", re.I)
OGRN_RE = re.compile(r"\b(?:ОГРН|OGRN)\s*[:№]?\s*(\d{13})\b", re.I)
KPP_RE = re.compile(r"\b(?:КПП|KPP)\s*[:№]?\s*(\d{9})\b", re.I)

# Соцсети
SOCIAL_RX = {
    "tg": re.compile(r"https?://t\.me/[A-Za-z0-9_]{3,}", re.I),
    "vk": re.compile(r"https?://vk\.com/[A-Za-z0-9_.]{3,}", re.I),
    "yt": re.compile(r"https?://(www\.)?youtube\.com/|https?://youtu\.be/", re.I),
    "ig": re.compile(r"https?://(www\.)?instagram\.com/", re.I),
}

# Подсказки для поиска страниц
ANCHOR_HINTS = (
    "контак", "о нас", "о компании", "реквизит", "документ", "оферт", "политик",
    "лиценз", "правов", "сведения", "about", "contacts", "contact", "docs", "oferta", "privacy",
)

# Категоризация (MVP эвристики)
CATEGORY_RULES = [
    ("IT", re.compile(r"\bpython|java|qa|frontend|backend|devops|data science|аналитик данных|программир", re.I)),
    ("Languages", re.compile(r"\bанглийск|испанск|немецк|французск|ielts|toefl|language", re.I)),
    ("Exams", re.compile(r"\bегэ|огэ|впр|экзамен|подготовка к егэ|подготовка к огэ", re.I)),
    ("Kids", re.compile(r"\bдет(и|ям|ский)|школьник|начальная школа|1-11 класс|робототехник", re.I)),
    ("Business", re.compile(r"\bmba|управлен|продаж|маркетинг|бизнес", re.I)),
    ("ProfEdu", re.compile(r"\bпрофпереподготов|повышение квалификац|дпо|dpo", re.I)),
    ("Psychology", re.compile(r"\bпсихолог|психотерап|коуч|therapy", re.I)),
]

# Блок-лист доменов (на всякий случай)
BLOCK_NETLOCS = {"vk.com", "t.me", "youtube.com", "youtu.be", "instagram.com", "facebook.com", "ok.ru"}


def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def is_same_domain(url: str, base_domain: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
        if not netloc:
            return True
        # допускаем поддомены
        return netloc == base_domain or netloc.endswith("." + base_domain)
    except Exception:
        return False


def extract_links_candidates(html: str, base_url: str, base_domain: str) -> list[str]:
    """
    Ищем ссылки на страницы "контакты/о нас/реквизиты/документы/оферта/политика/лицензия".
    Берём только внутренние ссылки.
    """
    soup = BeautifulSoup(html, "lxml")
    pages = set()

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        text = (a.get_text() or "").strip().lower()
        href_low = href.lower()

        if any(h in text for h in ANCHOR_HINTS) or any(h in href_low for h in ANCHOR_HINTS):
            full = urljoin(base_url, href)
            if not is_same_domain(full, base_domain):
                continue
            pages.add(full)

    # добавим типовые пути (часто работают)
    for path in ["/contacts", "/contact", "/about", "/company", "/rekvizity", "/docs", "/license", "/oferta", "/privacy"]:
        full = urljoin(base_url, path)
        if is_same_domain(full, base_domain):
            pages.add(full)

    # ограничим количество, чтобы не долбить сайт
    return list(pages)[:10]


def extract_first_email(text: str) -> str:
    emails = EMAIL_RE.findall(text or "")
    emails = [e for e in emails if not e.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))]
    return sorted(set(emails))[0] if emails else ""


def extract_first_phone(text: str) -> str:
    m = PHONE_RE.search(text or "")
    return m.group(0) if m else ""


def extract_socials(text: str) -> dict:
    out = {"tg": "", "vk": "", "yt": "", "ig": ""}
    for k, rx in SOCIAL_RX.items():
        m = rx.search(text or "")
        if m:
            # пробуем вытащить именно URL вокруг совпадения
            chunk = (text or "")[max(0, m.start() - 50): m.start() + 250]
            url_m = re.search(r"https?://[^\s\"'>)]+", chunk)
            out[k] = url_m.group(0) if url_m else m.group(0)
    return out


def extract_requisites(text: str) -> dict:
    inn = ""
    ogrn = ""
    kpp = ""
    m = INN_RE.search(text or "")
    if m:
        inn = m.group(1)
    m = OGRN_RE.search(text or "")
    if m:
        ogrn = m.group(1)
    m = KPP_RE.search(text or "")
    if m:
        kpp = m.group(1)
    return {"inn": inn, "ogrn": ogrn, "kpp": kpp}


def guess_lms(html: str) -> str:
    h = (html or "").lower()
    if "getcourse" in h or "gc-user" in h or "getcourse.ru" in h:
        return "getcourse"
    if "moodle" in h:
        return "moodle"
    if "teachbase" in h:
        return "teachbase"
    if "tilda" in h:
        return "tilda_site"
    return "unknown"


def guess_category(text: str) -> str:
    for cat, rx in CATEGORY_RULES:
        if rx.search(text or ""):
            return cat
    return "Other"


def main():
    os.makedirs("data", exist_ok=True)

    # читаем домены
    with open("data/raw_domains.csv", newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))

    rows = []

    with httpx.Client(
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        for item in raw:
            domain = (item.get("domain") or "").strip().lower()
            if not domain:
                continue

            # пробуем https, потом http
            base_https = f"https://{domain}"
            base_http = f"http://{domain}"

            html = fetch(client, base_https)
            base_url = base_https

            if not html:
                html = fetch(client, base_http)
                base_url = base_http

            if not html:
                continue

            # защитимся от того, что домен на самом деле соцсеть/платформа
            try:
                netloc = urlparse(base_url).netloc.lower()
                if netloc in BLOCK_NETLOCS:
                    continue
            except Exception:
                pass

            soup = BeautifulSoup(html, "lxml")
            pages = extract_links_candidates(html, base_url, domain)

            texts = [html]
            fetched_pages = []

            for p in pages:
                ph = fetch(client, p)
                if ph:
                    texts.append(ph)
                    fetched_pages.append(p)
                time.sleep(0.15)

            combined = "\n".join(texts)

            email = extract_first_email(combined)
            phone = extract_first_phone(combined)
            socials = extract_socials(combined)
            req = extract_requisites(combined)

            lms = guess_lms(combined)
            category = guess_category(combined[:30000])  # достаточно для MVP

            rows.append({
                "domain": domain,
                "base_url": base_url,
                "email_general": email,
                "phone_general": phone,
                "tg": socials["tg"],
                "vk": socials["vk"],
                "youtube": socials["yt"],
                "instagram": socials["ig"],
                "inn": req["inn"],
                "ogrn": req["ogrn"],
                "kpp": req["kpp"],
                "lms_detected": lms,
                "main_category": category,
                "about_pages": ";".join(fetched_pages),
                "last_crawled_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "source": item.get("source", ""),
            })

            time.sleep(SLEEP_SEC)

    out_path = "data/registry_enriched.csv"
    fields = [
        "domain", "base_url", "email_general", "phone_general",
        "tg", "vk", "youtube", "instagram",
        "inn", "ogrn", "kpp",
        "lms_detected", "main_category",
        "about_pages", "last_crawled_utc", "source",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Enriched: {len(rows)} -> {out_path}")


if __name__ == "__main__":
    main()
