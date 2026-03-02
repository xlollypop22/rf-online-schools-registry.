import csv
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; SchoolRegistryBot/1.0; +https://github.com/your/repo)"
TIMEOUT = 25
SLEEP_SEC = 0.5

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(\+7|8)\s*\(?\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
INN_RE = re.compile(r"\b(ИНН|INN)\s*[:№]?\s*(\d{10}|\d{12})\b", re.I)
OGRN_RE = re.compile(r"\b(ОГРН|OGRN)\s*[:№]?\s*(\d{13})\b", re.I)
KPP_RE = re.compile(r"\b(КПП|KPP)\s*[:№]?\s*(\d{9})\b", re.I)

SOCIAL_RX = {
    "tg": re.compile(r"https?://t\.me/[A-Za-z0-9_]{3,}", re.I),
    "vk": re.compile(r"https?://vk\.com/[A-Za-z0-9_.]{3,}", re.I),
    "yt": re.compile(r"https?://(www\.)?youtube\.com/|https?://youtu\.be/", re.I),
    "ig": re.compile(r"https?://(www\.)?instagram\.com/", re.I),
}

ABOUT_HINTS = ("о компании", "о нас", "about", "реквизит", "документ", "правов", "лиценз", "контакт", "contacts")

CATEGORY_RULES = [
    ("IT", re.compile(r"\bpython|java|qa|frontend|backend|devops|data science|аналитик данных|программир", re.I)),
    ("Languages", re.compile(r"\bанглийск|испанск|немецк|французск|ielts|toefl|language", re.I)),
    ("Exams", re.compile(r"\bегэ|огэ|впр|экзамен|подготовка к егэ|подготовка к огэ", re.I)),
    ("Kids", re.compile(r"\bдет(и|ям|ский)|школьник|начальная школа|1-11 класс|робототехник", re.I)),
    ("Business", re.compile(r"\bmba|управлен|продаж|маркетинг|бизнес", re.I)),
    ("ProfEdu", re.compile(r"\bпрофпереподготов|повышение квалификац|дпо|dpo", re.I)),
    ("Psychology", re.compile(r"\bпсихолог|психотерап|коуч|therapy", re.I)),
]

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

def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def find_candidate_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    pages = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        text = (a.get_text() or "").strip().lower()
        low = (href or "").lower()
        if any(k in text for k in ABOUT_HINTS) or any(k in low for k in ("about", "contacts", "contact", "rekviz", "license", "doc")):
            pages.add(urljoin(base_url, href))
    return list(pages)[:8]

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
            # вытащим первую ссылку целиком
            link_m = re.search(r"https?://[^\s\"'>]+", text[m.start(): m.start()+200])
            out[k] = link_m.group(0) if link_m else ""
    return out

def extract_requisites(text: str) -> dict:
    inn = ""
    ogrn = ""
    kpp = ""
    m = INN_RE.search(text or "")
    if m: inn = m.group(2)
    m = OGRN_RE.search(text or "")
    if m: ogrn = m.group(2)
    m = KPP_RE.search(text or "")
    if m: kpp = m.group(2)
    return {"inn": inn, "ogrn": ogrn, "kpp": kpp}

def main():
    with open("data/raw_domains.csv", newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))

    rows = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True) as client:
        for item in raw:
            domain = item["domain"].strip().lower()
            base_https = f"https://{domain}"
            base_http = f"http://{domain}"

            html = fetch(client, base_https) or fetch(client, base_http)
            base_url = base_https if html and "https://" in (client.get(base_https).url.__str__() if False else base_https) else (base_https if html else base_http)
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")
            extra_pages = find_candidate_pages(soup, base_url)

            texts = [html]
            for p in extra_pages:
                page_html = fetch(client, p)
                if page_html:
                    texts.append(page_html)
                time.sleep(0.2)

            combined = "\n".join(texts)

            email = extract_first_email(combined)
            phone = extract_first_phone(combined)
            socials = extract_socials(combined)
            req = extract_requisites(combined)
            lms = guess_lms(combined)
            category = guess_category(combined[:20000])  # достаточно, чтобы быстро

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
                "about_pages": ";".join(extra_pages),
                "last_crawled_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            })

            time.sleep(SLEEP_SEC)

    with open("data/registry_enriched.csv", "w", newline="", encoding="utf-8") as f:
        fields = [
            "domain","base_url","email_general","phone_general","tg","vk","youtube","instagram",
            "inn","ogrn","kpp","lms_detected","main_category","about_pages","last_crawled_utc"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Enriched: {len(rows)} -> data/registry_enriched.csv")

if __name__ == "__main__":
    main()
