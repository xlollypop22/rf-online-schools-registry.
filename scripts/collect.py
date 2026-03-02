import re
import csv
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
import tldextract

SOURCES = [
    # TODO: вставь сюда 3–10 страниц рейтингов/каталогов онлайн-школ
    "https://example.com/list-1",
    "https://example.com/list-2",
]

UA = "Mozilla/5.0 (compatible; RegistryBot/1.0; +https://github.com/your/repo)"
TIMEOUT = 30

def normalize_domain(url: str) -> str | None:
    try:
        if not url.startswith("http"):
            return None
        ext = tldextract.extract(url)
        if not ext.domain or not ext.suffix:
            return None
        return f"{ext.domain}.{ext.suffix}".lower()
    except Exception:
        return None

def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        links.append(full)
    return links

def main():
    seen_domains = set()

    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True) as client:
        for src in SOURCES:
            try:
                r = client.get(src)
                r.raise_for_status()
            except Exception:
                continue

            links = extract_links(r.text, src)
            for link in links:
                d = normalize_domain(link)
                if not d:
                    continue
                # грубый фильтр: выкинем соцсети/маркетплейсы/общие домены
                if d in {"vk.com", "t.me", "youtube.com", "instagram.com", "facebook.com", "ok.ru"}:
                    continue
                seen_domains.add(d)

    # Пишем raw.csv: source, domain
    rows = [{"source": "mvp_sources", "domain": d} for d in sorted(seen_domains)]
    with open("data/raw.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "domain"])
        w.writeheader()
        w.writerows(rows)

    print(f"Collected domains: {len(rows)} -> data/raw.csv")

if __name__ == "__main__":
    main()
