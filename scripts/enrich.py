import csv
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; RegistryBot/1.0; +https://github.com/your/repo)"
TIMEOUT = 25

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(\+7|8)\s*\(?\d{3}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")

SOCIAL_PATTERNS = {
    "tg": re.compile(r"t\.me/([A-Za-z0-9_]{3,})", re.I),
    "vk": re.compile(r"vk\.com/([A-Za-z0-9_.]{3,})", re.I),
    "yt": re.compile(r"youtube\.com/", re.I),
}

def guess_lms(html: str) -> str:
    h = html.lower()
    if "getcourse" in h or "gc-user" in h or "getcourse.ru" in h:
        return "getcourse"
    if "moodle" in h:
        return "moodle"
    if "teachbase" in h:
        return "teachbase"
    return "unknown"

def find_contact_page(soup: BeautifulSoup, base: str) -> str | None:
    # ищем "Контакты"
    for a in soup.select("a[href]"):
        txt = (a.get_text() or "").strip().lower()
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if "контакт" in txt or "contacts" in href.lower():
            return urljoin(base, href)
    return None

def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def extract_emails(text: str) -> str | None:
    m = EMAIL_RE.findall(text or "")
    if not m:
        return None
    # фильтр от мусора
    m = [e for e in m if not e.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))]
    return sorted(set(m))[0] if m else None

def extract_phone(text: str) -> str | None:
    m = PHONE_RE.search(text or "")
    return m.group(0) if m else None

def extract_social(text: str):
    out = {"tg": None, "vk": None, "yt": None}
    for k, rx in SOCIAL_PATTERNS.items():
        if rx.search(text or ""):
            out[k] = k
    return out

def main():
    # читаем raw.csv
    with open("data/raw.csv", newline="", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))

    rows = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True) as client:
        for item in raw:
            domain = item["domain"]
            base = f"https://{domain}"

            html = fetch(client, base)
            if not html:
                # fallback на http
                base = f"http://{domain}"
                html = fetch(client, base)
            if not html:
                continue

            soup = BeautifulSoup(html, "lxml")
            contact_url = find_contact_page(soup, base)

            contact_html = fetch(client, contact_url) if contact_url else None
            combined = (html or "") + "\n" + (contact_html or "")

            email = extract_emails(combined)
            phone = extract_phone(combined)
            lms = guess_lms(combined)

            rows.append({
                "domain": domain,
                "base_url": base,
                "contact_url": contact_url or "",
                "email_general": email or "",
                "phone_general": phone or "",
                "lms_detected": lms,
                "last_crawled": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "source": item.get("source", ""),
            })

    # пишем registry.csv (черновой реестр)
    with open("data/registry.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "domain","base_url","contact_url","email_general","phone_general","lms_detected","last_crawled","source"
        ])
        w.writeheader()
        w.writerows(rows)

    print(f"Enriched: {len(rows)} -> data/registry.csv")

if __name__ == "__main__":
    main()
