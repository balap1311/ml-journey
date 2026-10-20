# fin-rag: build a production RAG system, step by step

**Goal:** ask a question like *"What was Infosys's consolidated basic EPS in FY2026?"*, have a RAG system find the right part of the annual report and answer with a value and a citation, then **score every answer against `data/ground_truth.csv`**.

**How we work:** each step follows the same order: **learn** the idea, **build** it yourself (Claude reviews), **measure** it against ground truth, **see what breaks**, and let that limitation lead to the next step. You start with the simplest RAG that works, measure how bad it is, and improve it one fix at a time. Every fix is justified by a number. That record is the story you tell in interviews.

**Stack (local, free):** Docling (parsing) · sentence-transformers + `bge-small-en-v1.5` (embeddings) · LanceDB (vector store) · `rank_bm25` (keyword search) · Ollama + `qwen2.5:7b-instruct` (LLM; your 16 GB GPU can also run 14b) · FastAPI (serving) · conda `py3127`.
No LangChain or LlamaIndex at first. You'll write each part yourself so you understand what those frameworks hide. You can switch to one later and compare.

---

## The mental model (read this first)

RAG has two pipelines:

```
INDEXING (offline, once per document)
  PDF ──► parse ──► chunks ──► embed each chunk ──► store vectors + text + metadata

QUERYING (online, every question)
  question ──► embed ──► find the k most similar chunks ──► put them in the prompt ──► LLM answers
```

- **Retrieval** decides *what the LLM gets to see*. If the right chunk isn't retrieved, no LLM can answer correctly.
- **Generation** decides *what the LLM does with it*. It can still misread, pick the wrong column, or make up a number.

**The most important skill in RAG is telling these two failures apart.** Every step below measures them separately.

---

## Step 0: Setup

- [x] Install Ollama for Windows (ollama.com), then `ollama pull qwen2.5:7b-instruct`. Test: `ollama run qwen2.5:7b-instruct "hello"`.
- [x] In `py3127`: `pip install sentence-transformers lancedb rank_bm25 ollama fastapi uvicorn`.
- [x] Optional but recommended: install the CUDA build of PyTorch so Docling and embeddings run on the GPU. Check that `torch.cuda.is_available()` returns `True`.

**Done when:** Python can call Ollama and get a reply, and can embed one sentence.

---

## Step 1: Evaluation first

**Learn:** you can't improve what you don't measure. In production RAG the evaluation set is built *before* the system.
**Build:**
- [ ] `eval/questions.jsonl`: turn each `ground_truth.csv` row into a question, e.g. `{"id": "q01", "question": "What was Infosys's consolidated revenue from operations in FY2026?", "expected": 178650, "unit": "INR crore", "page": 287}`. Write 2 versions of some questions (formal and casual: "Infosys top line FY26?").
- [ ] Add about 10 **unanswerable** questions ("Infosys FY2019 revenue", "Infosys market share"). The correct answer is "not found".
- [ ] `eval/score.py`: compare an answer to the expected value. Count it as correct if it's within 0.5% (to allow for rounding) and the unit is right.

**Done when:** `score.py` runs on a dummy answers file and prints accuracy.

---

## Step 2: Parse the documents

**Learn:** what a PDF really contains (text pieces at x,y positions), and how Docling rebuilds tables. You already traced this for one row in Phase 0.
**Build:**
- [ ] `ingest/parse.py`: run Docling on the pages that hold the statements (PDF pages 207–217 and 285–295) plus a few pages of text, e.g. the Board's report. Save the result as JSON so you only parse once.

**Limitation you'll see:** parsing mistakes carry through everything after it. A broken table here can't be fixed later.

---

## Step 3: Naive RAG, the baseline

**Learn:** chunking, embeddings (text → vector, where similar meaning gives a similar vector), cosine similarity, top-k search, prompt templates.
**Build:**
- [ ] `index/chunk.py`, version 1: export the document as plain text and split it into fixed chunks of about 500 characters with some overlap. Use this crude version on purpose.
- [ ] `index/build.py`: embed the chunks with `bge-small-en-v1.5` and store them in LanceDB with `page` metadata.
- [ ] `rag/answer.py`: embed the question, retrieve the top 5 chunks, prompt the LLM with *"Answer using only this context"*, and return the answer.
- [ ] Run all of `questions.jsonl` and score it.

**Expect:** low accuracy. **That's the point.** This number is your baseline.

---

## Step 4: Failure analysis

**Learn:** retrieval metrics. **Recall@k** asks: was the ground-truth page among the k retrieved chunks?
**Build:**
- [ ] `eval/retrieval.py`: recall@1, @5 and @10 using the `page` in `questions.jsonl`.
- [ ] Sort every wrong answer into one of these groups:
  - **retrieval miss**: the right page wasn't retrieved
  - **wrong column/scope**: the right table was retrieved, but the answer used standalone instead of consolidated, or 2025 instead of 2026
  - **misread number**: e.g. `29, 211` read as 29
  - **hallucination**: the number isn't in the context at all
  - **should have said "not found"**

**Limitations you'll see (written down before you've seen your own numbers):**
- Fixed-size chunks cut tables in half. The row "Basic 70.87 61.58" ends up with no header saying which column is 2026, and no parent saying it's EPS.
- Embeddings are poor at exact terms. "Basic EPS" and "Diluted EPS" give almost the same vector. So do standalone and consolidated.
- Standalone and consolidated tables use nearly the same words, so retrieval mixes them up.

**Done when:** you have a table of failures by group. Each later step targets one group.

---

## Step 5: Fix chunking with table-aware chunks

**Learn:** chunks should match how the document is organised. Each chunk needs enough context to make sense on its own.
**Build:**
- [ ] Version 2 of the chunker:
  - each **table** becomes one chunk, written as markdown, with its title on top (*"Consolidated Statement of Profit and Loss, In ₹ crore"*)
  - each **table row** also becomes a small chunk with its full context: *"Consolidated P&L, FY2026 | Earnings per equity share > Basic | 71.58 INR"*
  - **text sections** are split by heading, not by character count
- [ ] Store metadata on every chunk: `scope`, `statement`, `period`, `page`, `chunk_type`.
- [ ] Measure again: accuracy and recall@k.

**Limitation that remains:** semantic search still mixes up standalone and consolidated.

---

## Step 6: Better retrieval: hybrid search and metadata filters

**Learn:** BM25, which ranks by keyword matches. Reciprocal rank fusion, which combines two ranked lists. Filtering on metadata *before* searching.
**Build:**
- [ ] Add a BM25 index next to the vectors, and merge the two result lists with reciprocal rank fusion.
- [ ] Filter by metadata: if the question says "consolidated", only search chunks where `scope = consolidated`.
- [ ] Measure recall@k for vectors alone, BM25 alone, hybrid, and hybrid with filters.

**Limitation that remains:** the right chunk is often in the top 10 but not in the top 3. The LLM gets distracted by similar-looking chunks.

---

## Step 7: Reranking

**Learn:** bi-encoders vs cross-encoders. Retrieve broadly and cheaply first, then score the shortlist carefully.
**Build:**
- [ ] Retrieve 20 chunks, rerank them with `bge-reranker-base`, and keep the top 3–5.
- [ ] Measure the gain in accuracy and the extra time it adds.

---

## Step 8: Understand the query

**Learn:** users don't speak in metadata. "Infosys profit last year" needs to become `{company: Infosys, metric: PAT, period: FY2026, scope: consolidated (default)}`.
**Build:**
- [ ] `rag/query.py`: the LLM turns the question into JSON fields. Your code adds defaults (latest year, consolidated) and synonyms ("top line" → revenue).
- [ ] Use the fields as filters in retrieval, and say them explicitly in the prompt.
- [ ] Measure: casual questions should now score about as well as formal ones.

---

## Step 9: Reliable answers: structured output, citations, "not found"

**Learn:** LLMs give fluent answers that may be wrong. You check the output with code instead of trusting it.
**Build:**
- [ ] Make the LLM return JSON: `{value, unit, scope, period, chunk_id, quote}` or `{"not_found": true}`. Use temperature 0.
- [ ] `rag/validate.py`: reject the answer if the `quote` isn't in the cited chunk, or if the number doesn't appear in the quote. A rejected answer becomes "not found".
- [ ] Measure: hallucinations should drop to about 0, and "not found" accuracy on unanswerable questions should rise.

---

## Step 10: Derived metrics, where pure RAG breaks

**Learn:** LLMs are unreliable at arithmetic. ROE needs PAT ÷ the average of two equity values. RAG retrieves facts. It doesn't calculate.
**Build:**
- [ ] For ROE, D/E and free cash flow: retrieve each input with RAG, then **calculate in Python**. This is a simple form of tool use: the LLM plans and fetches, code does the maths.
- [ ] Measure the derived metrics against values calculated from ground truth.

---

## Step 11: Generalise

**Learn:** whether the system only works on the document you tuned it for.
**Build:**
- [ ] Add TCS (and Wipro) reports and their ground truth. Run the same evaluation **without changing anything**.
- [ ] Look at what breaks: different labels, layouts, units. Fix it in general terms, not with company-specific rules.

---

## Step 12: Production

**Learn:** what turns a script into a service.
**Build:**
- [ ] FastAPI: `POST /query`, `POST /ingest`, `GET /health`, with Pydantic request and response models.
- [ ] Load the model and index once at startup. Cache answers to repeated questions. Measure p50 and p95 latency per stage (retrieve / rerank / LLM).
- [ ] Logging: one JSON log line per query, with question, fields, chunk IDs, answer, validation result and latency per stage. Optional: tracing with Langfuse (self-hosted) or LangSmith.
- [ ] Configuration in `config.yaml` (models, k, chunker version) so each experiment can be reproduced.
- [ ] Index versioning: re-indexing creates a new version, and the evaluation records which version it ran on.
- [ ] Tests, plus a GitHub Actions check that runs a small evaluation and **fails the build if accuracy drops**.
- [ ] Dockerfile and `docker-compose.yml` (API + Ollama).

**Done when:** on a clean machine, `docker compose up` then one `curl` returns a cited answer.

---

## Step 13: Write-up

- [ ] README: architecture diagram, **the experiment table below**, limitations, next steps.
- [ ] `docs/design.md`: the key decisions and the alternatives you rejected.

---

## Experiment log (add one row after every step)

| Step | Change | Recall@5 | Accuracy (answerable) | "Not found" correct | Hallucinations | p95 latency |
|---|---|---|---|---|---|---|
| 3 | Naive RAG baseline | | | | | |
| 5 | Table-aware chunks | | | | | |
| 6 | Hybrid + filters | | | | | |
| 7 | Reranker | | | | | |
| 8 | Query understanding | | | | | |
| 9 | Structured output + validation | | | | | |
| 10 | Calculated metrics | | | | | |
| 11 | + TCS (no tuning) | | | | | |

The final README is built from this table: *"Started at X%, ended at Y%. Here is what each change contributed and why."*

---

## RAG limitations reference

| Limitation | Where you'll see it | Fixed in |
|---|---|---|
| Parsing errors carry through | Step 2 | better parsing, checks |
| Chunks lose context (table headers, parent rows) | Step 3–4 | Step 5 |
| Embeddings blur exact terms and numbers | Step 4 | Step 6 (BM25) |
| Similar sections get confused (standalone vs consolidated) | Step 4 | Step 6 (filters), Step 8 |
| Right chunk ranked too low, LLM distracted | Step 6 | Step 7 |
| Casual questions don't match document wording | Step 1 eval | Step 8 |
| Hallucinated or misread numbers | Step 4 | Step 9 |
| Answers when it shouldn't | unanswerable set | Step 9 |
| Arithmetic | Step 10 | calculate in code / tool use |
| Overfitting to one document | Step 11 | general fixes |
| Latency, stale index, no visibility into runs | Step 12 | caching, versioning, logs |

## Rules
- One step at a time. Don't start the next step until this one has a number in the experiment log.
- Commit after each step with its result in the commit message.
- New ideas go into a **Later** list: agents (LangGraph), GraphRAG, fine-tuning embeddings, scanned PDFs.
