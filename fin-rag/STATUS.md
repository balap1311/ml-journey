# fin-rag status

**Last updated:** 2026-10-20

```
Progress  [██░░░░░░░░░░░░]  2 / 14 steps done (14%)
```

| # | Step | Status |
|---|---|---|
| 0 | Setup (Ollama, embeddings, GPU) | ✅ done |
| 1 | Evaluation first (questions + scorer) | ✅ done |
| 2 | Parse the documents (Docling) | 👉 **next** |
| 3 | Naive RAG baseline | ⬜ |
| 4 | Failure analysis (recall@k, error groups) | ⬜ |
| 5 | Table-aware chunks | ⬜ |
| 6 | Hybrid search (BM25) + metadata filters | ⬜ |
| 7 | Reranking | ⬜ |
| 8 | Query understanding | ⬜ |
| 9 | Structured output, citations, "not found" | ⬜ |
| 10 | Derived metrics (calculate in code) | ⬜ |
| 11 | Generalise (add TCS / Wipro) | ⬜ |
| 12 | Production (FastAPI, Docker, CI) | ⬜ |
| 13 | Write-up | ⬜ |

Full details for every step: [PLAN.md](PLAN.md).

### What Step 0 confirmed
- Python env: `D:\condaenvs\fin-rag\python.exe`. CUDA works (RTX 3080 Ti).
- Ollama `qwen2.5:7b-instruct` replies from Python.
- `BAAI/bge-small-en-v1.5` embeds a sentence on the GPU (384 dimensions).

### What Step 1 built
- `eval/questions.jsonl`: 48 formal questions, generated from `ground_truth.csv` by `eval/make_questions.py`.
- `eval/questions_manual.jsonl`: 13 casual and 10 unanswerable questions. Each unanswerable one was checked against the PDF.
- `eval/score.py`: grades raw-text answers. Run it with `python eval\score.py <answers.jsonl>`.
- `eval/dummy_answers.jsonl`: 14 trap answers. All outcomes matched the predictions (7 / 61 correct).
- Known limitations: when an answer gives both years, the scorer takes the first number (Step 9 fixes this), and "29, 211" (a number split by a space) is read as 211. That split comes from bad parsing, so it is left counted as a failure.
- Learning notes: [RAG Evaluation: Learning Notes](https://claude.ai/code/artifact/c074f9f3-ca35-4180-8dfa-8eb8b04615e5).

---

## ▶ Next session: Step 2, Parse the documents

**Goal:** turn the statement pages of the annual report into structured JSON (headings, paragraphs, tables), and check that the tables came out right. You parse once and reuse the result, because parsing is slow.

**Why:** a PDF only holds text pieces at x,y positions. Docling rebuilds the tables from them. Every later step works on this output, so a broken table here can't be fixed later.

Do these in order. Tick each one off as you finish it.

### Task 1: learn what you're parsing
- [ ] Open `data/raw/infosys-ar-26.pdf` at PDF page 209 (the standalone P&L) and page 287 (the consolidated P&L). Look at how the tables are laid out: the columns, the notes column, and the rows with sub-items.
- [ ] Find a few pages of plain text (for example the Board's report) to parse as well. Note their PDF page numbers.

### Task 2: try Docling on one page
- [ ] In a Python shell, convert only page 209 and print it as markdown:
  ```python
  from docling.document_converter import DocumentConverter
  result = DocumentConverter().convert("data/raw/infosys-ar-26.pdf", page_range=(209, 209))
  print(result.document.export_to_markdown())
  ```
- [ ] Compare the table with the PDF. Is "Revenue from operations" there with 148,819 and 136,592 in the right columns?

### Task 3: `ingest/parse.py`
- [ ] Make the folder `fin-rag/ingest/`.
- [ ] Parse PDF pages **207–217** (standalone statements), **285–295** (consolidated statements) and your text pages.
- [ ] Save each result as JSON in `data/parsed/` (use `result.document.export_to_dict()`), plus a markdown copy so it's easy to read.
- [ ] Record how long parsing takes.

### Task 4: check the output against ground truth
- [ ] For pages 207–210 and 285–288, check 5–10 values from `ground_truth.csv` in the parsed tables.
- [ ] Write down every problem you find (merged columns, split numbers like "29, 211", missing headers) in `notes/parsing_issues.md`. These are the "parsing errors carry through" limitation, and you'll come back to them in Step 4.

### Finish
- [ ] Ask Claude to review `parse.py` and your parsing notes.
- [ ] Decide whether `data/parsed/` goes in git (it's generated, so probably not).
- [ ] Commit, and update this file to 3 / 14.

**Run commands with:** open a **new** terminal, then
```
conda activate fin-rag
cd D:\Projects\ml-journey\fin-rag
python ingest\parse.py
```
(If activation ever fails, use the full path instead: `D:\condaenvs\fin-rag\python.exe ingest\parse.py`)
