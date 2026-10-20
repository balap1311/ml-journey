import csv, json
from pathlib import Path

# 1. Paths: build them from this file's location, so the script
#    works no matter which folder you run it from
HERE = Path(__file__).parent          # .../fin-rag/eval
CSV_PATH = HERE.parent / "data" / "ground_truth.csv"
OUT_PATH = HERE / "questions.jsonl"

# 2. Metric code -> words a human would use (wording close to the PDF's labels)
METRIC_PHRASES = {
    "revenue_from_operations": "revenue from operations",
    "profit_after_tax": "profit after tax",
    "net_income_owners": "net profit attributable to owners of the company",
    "eps_basic": "basic earnings per share",
    "eps_diluted": "diluted earnings per share",
    "operating_cash_flow": "net cash generated from operating activities",
    "capex": "capital expenditure",
    "total_assets": "total assets",
    "total_equity": "total equity",
    "equity_owners": "equity attributable to owners of the company",
    "total_borrowings": "total borrowings",
    "lease_liabilities": "lease liabilities",
}

# Balances are a snapshot on one date; everything else is a flow over the year
BALANCE_METRICS = {"total_assets", "total_equity", "equity_owners",
                   "total_borrowings", "lease_liabilities"}

def period_end(period):
    # "FY2026" -> "March 31, 2026" (Indian financial year ends on March 31)
    return f"March 31, {period.removeprefix('FY')}"

# 3. One CSV row -> one question record
def make_question(row, qid):
    company, scope, period, metric = row["company"], row["scope"], row["period"], row["metric"]
    phrase = METRIC_PHRASES[metric]

    if metric in BALANCE_METRICS:
        question = f"What did {company} report as its {scope} {phrase} as of {period_end(period)}?"
    else:
        question = f"What was {company}'s {scope} {phrase} in {period}?"

    return {
        "id": qid,
        "question": question,
        "expected": float(row["value"]),   # "178650" (text) -> 178650.0 (number)
        "unit": row["unit"],
        "page": int(row["page"]),          # PDF page, NOT printed_page
        "company": company,
        "scope": scope,
        "period": period,
        "metric": metric,
        "style": "formal",
        "answerable": True,
    }

# 4. Read CSV -> build records -> write one JSON object per line
def main():
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for i, row in enumerate(rows, start=1):
            record = make_question(row, f"q{i:03d}")        # q001, q002, ...
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} questions to {OUT_PATH}")

if __name__ == "__main__":
    main()
