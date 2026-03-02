import csv
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
import tldextract

UA = "Mozilla/5.0 (compatible; SchoolRegistryBot/1.0; +https://github.com/your/repo)"
TIMEOUT = 30
SLEEP_SEC = 0.6  # бережно к источникам

BLOCK_DOMAINS = {
    "vk.com", "t.me", "youtube.com", "instagram.com", "facebook.com", "ok.ru",
    "tiktok.com", "google.com", "yandex.ru", "yandex.com", "dzen.ru",
    "apple.com", "play.google.com",
}

def normalize_domain(url: str) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    ext = tldextract.extract(url)
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}".lower()

def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        out.append(urljoin(base_url, href))
    return out

def read_sources(path="sources.txt") -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

def main():
    sources = read_sources()
    seen = set()

    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True) as client:
        for src in sources:
            try:
                r = client.get(src)
                r.raise_for_status()
            except Exception:
                continue

            for link in extract_links(r.text, src):
                d = normalize_domain(link)
                if not d or d in BLOCK_DOMAINS:
                    continue
                # фильтр: отсекаем сами источники, оставляем “кандидаты школ”
                if d in {"tutortop.ru", "kurshub.ru", "sravni.ru", "edu.sravni.ru",
                         "choosecourse.ru", "okursah.ru", "courselist.ru", "coursator.online",
                         "katalog-kursov.ru", "getcourse.ru", "online-shkoly.com",
                         "career.hh.ru", "t-j.ru", "info-hit.ru"}:
                    continue
                seen.add(d)

            time.sleep(SLEEP_SEC)

    rows = [{"domain": d, "source": "sources.txt"} for d in sorted(seen)]
    with open("data/raw_domains.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["domain", "source"])
        w.writeheader()
        w.writerows(rows)

    print(f"Collected candidate domains: {len(rows)} -> data/raw_domains.csv")

if __name__ == "__main__":
    main()
