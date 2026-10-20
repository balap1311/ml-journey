"""Score RAG answers against the eval set.

Usage:
    python eval/score.py <answers.jsonl> [--out eval/results.jsonl]

answers.jsonl has one line per question: {"id": "q001", "answer": "<raw LLM text>"}

Rules (these are measurement choices, change them on purpose, not by accident):
- A refusal phrase ("not found", "not available", ...) counts as "the system said not found".
- From an answer, take the FIRST number that has a unit or currency next to it;
  if none has one, take the first number that isn't a year or a date.
- Convert that number to the question's unit (crore for INR crore, as-is for INR).
- Correct if within 0.5% of expected. If expected is 0, it must be exactly 0
  (or the answer says "no borrowings", "nil", "zero", ...).
"""
import argparse, json, re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
QUESTION_FILES = [HERE / "questions.jsonl", HERE / "questions_manual.jsonl"]
TOLERANCE = 0.005  # 0.5%

REFUSAL_PHRASES = [
    "not found", "not available", "not mentioned", "not provided", "not disclosed",
    "not reported", "not present", "no information", "does not contain", "doesn't contain",
    "cannot find", "can't find", "could not find", "unable to find", "cannot be determined",
    "cannot answer", "can't answer", "i don't know",
]
ZERO_PHRASES = ["no borrowings", "no debt", "debt-free", "debt free", "nil", "zero", "none"]

# How many crore one of each unit is worth
TO_CRORE = {
    "lakh crore": 100_000, "lakh crores": 100_000, "lac crore": 100_000,
    "crore": 1, "crores": 1, "cr": 1,
    "billion": 100, "bn": 100,
    "million": 0.1, "mn": 0.1,
    "lakh": 0.01, "lakhs": 0.01,
}
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

# A number: Indian (1,78,650) or Western (178,650) grouping, or plain digits, optional decimals.
# Longer unit names come first so "lakh crore" wins over "lakh".
NUMBER_RE = re.compile(
    r"(?P<currency>₹|rs\.?|inr)?\s*"
    r"(?P<num>(?<![\w.])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?)"
    r"(?:\s*(?P<unit>lakh crores?|lac crore|crores?|cr\b|billion|bn\b|million|mn\b|lakhs?))?",
    re.IGNORECASE,
)


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def is_refusal(text):
    t = text.lower()
    return any(p in t for p in REFUSAL_PHRASES)


def is_year_or_date(text, m):
    """True for numbers like 2026 in 'FY2026', '2025-26', 'March 31, 2026'."""
    num = m.group("num")
    before = text[max(0, m.start("num") - 12):m.start("num")].lower()
    after = text[m.end("num"):m.end("num") + 3]
    if re.search(r"(fy|fiscal\s*)$", before):            # FY2026, fiscal 2026
        return True
    if re.search(MONTHS + r"\s*$", before):               # March 31
        return True
    if re.fullmatch(r"(19|20)\d\d", num) and not m.group("currency") and not m.group("unit"):
        return True                                        # a bare year like 2026
    if re.match(r"-\d\d", after):                          # 2025-26
        return True
    return False


def extract_number(text):
    """'₹1,78,650 crore' -> (178650.0, 'crore'). Returns None if no usable number."""
    candidates = [m for m in NUMBER_RE.finditer(text) if not is_year_or_date(text, m)]
    if not candidates:
        return None
    with_unit = [m for m in candidates if m.group("unit") or m.group("currency")]
    m = (with_unit or candidates)[0]
    value = float(m.group("num").replace(",", ""))
    unit = (m.group("unit") or "").lower()
    return value, unit


def to_expected_unit(value, unit, expected_unit):
    """Convert to the question's unit. INR crore questions accept lakh crore, million, etc."""
    if expected_unit == "INR crore" and unit:
        return value * TO_CRORE[re.sub(r"\s+", " ", unit)]
    return value  # no unit given, or a per-share value in INR


def is_correct(got, expected, tol=TOLERANCE):
    if expected == 0:
        return got == 0  # relative error divides by zero, so require an exact 0
    return abs(got - expected) / abs(expected) <= tol


def score_one(q, answer):
    """Returns (outcome, got). Outcomes:
    correct / wrong / no_number / wrong_refusal / missing        (answerable questions)
    correct_refusal / should_have_refused / missing              (unanswerable questions)
    """
    if answer is None:
        return "missing", None
    if is_refusal(answer):
        return ("correct_refusal" if not q["answerable"] else "wrong_refusal"), None
    if not q["answerable"]:
        return "should_have_refused", None

    found = extract_number(answer)
    if found is None:
        if q["expected"] == 0 and any(p in answer.lower() for p in ZERO_PHRASES):
            return "correct", 0.0
        return "no_number", None
    got = round(to_expected_unit(*found, q["unit"]), 4)  # round away float noise (14881.900000000001)
    return ("correct" if is_correct(got, q["expected"]) else "wrong"), got


def pct(n, d):
    return f"{n:>3} / {d:<3} = {100 * n / d:5.1f}%" if d else f"{n:>3} / {d:<3} =   n/a"


def main():
    parser = argparse.ArgumentParser(description="Score RAG answers against the eval set.")
    parser.add_argument("answers", help="answers.jsonl with {id, answer} per line")
    parser.add_argument("--out", default=str(HERE / "results.jsonl"))
    args = parser.parse_args()

    questions = [q for path in QUESTION_FILES for q in load_jsonl(path)]
    answers = {a["id"]: a["answer"] for a in load_jsonl(args.answers)}

    results = []
    for q in questions:
        outcome, got = score_one(q, answers.get(q["id"]))
        results.append({
            "id": q["id"], "style": q["style"], "metric": q["metric"], "scope": q["scope"],
            "period": q["period"], "page": q["page"], "expected": q["expected"], "got": got,
            "outcome": outcome, "answer": answers.get(q["id"]),
        })

    with open(args.out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    answerable = [r for r in results if r["style"] != "unanswerable"]
    unanswerable = [r for r in results if r["style"] == "unanswerable"]
    counts = Counter(r["outcome"] for r in results)

    print(f"Scored {len(answers)} answers against {len(questions)} questions\n")
    print(f"Answerable accuracy:            {pct(counts['correct'], len(answerable))}")
    print(f"Unanswerable correctly refused: {pct(counts['correct_refusal'], len(unanswerable))}")
    print(f"Answerable wrongly refused:     {pct(counts['wrong_refusal'], len(answerable))}")

    by_style = defaultdict(list)
    for r in answerable:
        by_style[r["style"]].append(r)
    print("\nAccuracy by style:")
    for style, rs in by_style.items():
        print(f"  {style:<8} {pct(sum(r['outcome'] == 'correct' for r in rs), len(rs))}")

    print("\nOutcomes:", dict(counts))
    print(f"Per-question results written to {args.out}")


if __name__ == "__main__":
    main()
