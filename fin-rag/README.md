# fin-rag

Extract key financial metrics (revenue, net income, EPS, cash flow, P/E, ROE, D/E) from company annual reports into a flat file, and serve them through structured lookups in under 50 ms.

Fully local, free tools only: Docling for parsing, rules plus a local LLM (Ollama) for extraction, Parquet/SQLite for storage, FastAPI for lookups.

---

## Status

| Phase | What | State |
|---|---|---|
| 0 | Parse one report, find revenue candidates | Done |
| 1 | Clean extraction for 4 core metrics + accuracy test | **Next** |
| 2 | Retrieval-augmented extraction (BM25 + embeddings + Ollama) for misses | Planned |
| 3 | Storage + `GET /metrics` API + latency test | Planned |
| 4 | README results: accuracy, latency, architecture | Planned |

**First result:** Infosys FY2026 consolidated revenue from operations = ₹1,78,650 crore, extracted from page 1, table 0 of the Board's Report.

---

## Setup (Windows / PowerShell)

```powershell
git clone https://github.com/balap1311/fin-rag.git
cd fin-rag
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install docling pypdf pandas

# optional: hide Hugging Face symlink warnings
$env:HF_HUB_DISABLE_SYMLINKS_WARNING=1
```

The first run downloads Docling's layout and OCR models (a few hundred MB).

### Test data

PDFs are not committed (`data/raw/` is gitignored). Download into `data/raw/`:

| File | Source |
|---|---|
| `infosys_boards_report_fy26.pdf` | https://www.infosys.com/investors/reports-filings/annual-report/annual/documents/2025-26/boards-report.pdf |
| `infosys_additional_info_fy26.pdf` | https://www.infosys.com/investors/reports-filings/documents/additional-information-2025-26.pdf |
| TCS FY2026 Integrated Annual Report | tcs.com, Investor Relations section |

If `Invoke-WebRequest` or `curl.exe` gets blocked, download in the browser instead.

---

## Usage

```powershell
python phase0.py data\raw\infosys_boards_report_fy26.pdf            # whole file
python phase0.py data\raw\some_annual_report.pdf 180 200            # only pages 180-200
```

Output: prints each table found, then writes revenue candidate rows to `metrics.csv`.

### How `phase0.py` works

1. Reads arguments: the PDF path, plus an optional start and end page.
2. `slice_pdf()` copies only the selected pages to a smaller PDF (pypdf), so parsing is faster.
3. `DocumentConverter().convert()`: Docling's layout model and OCR find text blocks and tables.
4. Loops over `doc.tables`. Each table becomes a pandas DataFrame, with its page number taken from `table.prov`.
5. Label matching: lowercases the first column and checks it against `REVENUE_KEYWORDS`.
6. Writes the matches to `metrics.csv`.

Steps 1–4 are parsing and already work. Steps 5–6 are extraction, which is what gets improved next.

---

## Known issues (from the Phase 0 run)

- **Noise rows:** the substring "revenue" also matches `profit before tax (% of revenue)`. Prefer exact labels and exclude rows containing `%`, "of revenue" or "growth".
- **Column choice:** each row holds standalone 2026/2025/YoY and consolidated 2026/2025/YoY values. Docling keeps the headers (e.g. `Consolidated.For the year ended March 31,.2026`), so choose the column by its header, not by position.
- **Number format:** values are strings in Indian format (`1,78,650`). Parse them to float and store the unit (`crore`) separately.
- **Chart junk:** tables 2–4 on page 5 are chart labels (the `` ` `` is a misread ₹ symbol). Skip tables whose first column isn't line-item text.

---

## Next steps

### Phase 1: clean extraction (one session at a time)

- [ ] Read steps 4–5 of `phase0.py`. Run it and note where the label and values sit in each row.
- [ ] Create `ground_truth.csv` (`company, period, scope, metric, value, unit`) using the values below.
- [ ] Fix revenue: exact label match, `%` exclusion, column chosen by header (consolidated, latest year).
- [ ] Add PAT, total assets and total equity (tables 0 and 1), each with its own keywords and exclusions.
- [ ] Output clean records: `company, period, scope, metric, value, unit, source_doc, page, table`.
- [ ] Write `test_accuracy.py`: compare output to `ground_truth.csv` and print hits and misses per metric.
- [ ] Compute ROE (PAT / equity) and D/E from the extracted line items.

### Phase 2: retrieval-augmented extraction
- [ ] Chunk the parsed output (keep each table as one chunk with page/section metadata).
- [ ] Hybrid retrieval: BM25 (`rank_bm25`) + embeddings (`bge-small-en-v1.5`) in LanceDB.
- [ ] For metrics the rules miss: retrieve top-k chunks, then have Ollama (Qwen2.5 3B/7B) extract the value with a required chunk citation.
- [ ] Measure retrieval recall@k and check that each cited chunk actually contains the number.

### Phase 3: serve and measure
- [ ] Store results in Parquet (flat file) and SQLite/DuckDB.
- [ ] FastAPI `GET /metrics?company=&period=&metric=` served from an in-memory dict.
- [ ] Latency test: p50/p95/p99, target p95 < 50 ms.

### Phase 4: write-up
- [ ] README: architecture diagram, accuracy per metric, lookup latency, known limitations.

### Later (v0.2, not now)
OCR-only scanned PDFs, PPT/Excel inputs, `/ask` endpoint for MD&A questions, reranker, semantic cache, Docker Compose, GitHub Actions CI, and a P/E price source.

---

## Ground truth (₹ crore, FY2026, checked against the PDFs)

| Company | Metric | Standalone | Consolidated |
|---|---|---|---|
| Infosys | Revenue from operations | 1,48,819 | 1,78,650 |
| Infosys | Profit after tax | 29,211 | 29,474 |
| Infosys | Profit attributable to owners | 29,211 | 29,440 |
| Infosys | Total assets | 1,26,691 | 1,55,967 |
| Infosys | Basic EPS (₹) | n/a | 71.58 |
| TCS | Revenue from operations | 2,20,938 | 2,67,021 |

---

## Working rules

- Build the smallest runnable slice first, then widen it. No new planning until the current slice runs.
- Commit and push after every working session.
- Out-of-scope ideas go into "Later (v0.2)", not into the current phase.
