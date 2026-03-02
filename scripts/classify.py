import csv

def score_row(r: dict) -> tuple[int, str]:
    s = 0
    if r.get("email_general"): s += 20
    if r.get("phone_general"): s += 10
    if r.get("tg") or r.get("vk") or r.get("youtube"): s += 10
    if r.get("inn") or r.get("ogrn"): s += 10
    if r.get("lms_detected") and r["lms_detected"] != "unknown": s += 15
    if r.get("main_category") and r["main_category"] != "Other": s += 10

    pr = "A" if s >= 55 else ("B" if s >= 35 else "C")
    return s, pr

def main():
    with open("data/registry_enriched.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        s, pr = score_row(r)
        r["icp_score"] = str(s)
        r["priority"] = pr

    fields = list(rows[0].keys()) if rows else []
    with open("data/registry_final.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Final: {len(rows)} -> data/registry_final.csv")

if __name__ == "__main__":
    main()
