import csv
import re

RULES = [
    ("IT", re.compile(r"\bpython|java|qa|frontend|backend|devops|аналитик данных|data science|программи", re.I)),
    ("Languages", re.compile(r"\bанглийск|испанск|немецк|французск|language|ielts|toefl", re.I)),
    ("Exams", re.compile(r"\bегэ|огэ|впр|ент|экзамен|подготовка к егэ", re.I)),
    ("Kids", re.compile(r"\bдет|школьник|1-11 класс|робототехник|ментальная арифметика", re.I)),
    ("Business", re.compile(r"\bmba|управлен|продаж|маркетинг|бизнес", re.I)),
    ("ProfEdu", re.compile(r"\bпрофпереподготов|повышение квалификац|dpo|дпо", re.I)),
]

def guess_category(text: str) -> str:
    t = (text or "").strip()
    for cat, rx in RULES:
        if rx.search(t):
            return cat
    return "Other"

def main():
    with open("data/registry.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        # пока классифицируем по домену/URL и наличию LMS как слабый сигнал
        text = f"{r.get('domain','')} {r.get('base_url','')} {r.get('lms_detected','')}"
        cat = guess_category(text)

        # простой скоринг
        score = 0
        if r.get("email_general"): score += 20
        if r.get("phone_general"): score += 10
        if r.get("lms_detected") and r["lms_detected"] != "unknown": score += 15
        if cat != "Other": score += 10

        priority = "A" if score >= 35 else ("B" if score >= 20 else "C")

        r["main_category"] = cat
        r["icp_score"] = str(score)
        r["priority"] = priority
        out.append(r)

    fields = list(out[0].keys()) if out else []
    with open("data/registry_classified.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"Classified: {len(out)} -> data/registry_classified.csv")

if __name__ == "__main__":
    main()
