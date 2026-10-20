# Document Intake Triage

A small, readable project that turns messy case documents into a structured
**review queue** — built as a hands-on way to practise the Forward Deployed
AI Engineer (FDE) skill set.

The scenario: a public-benefits office receives a pile of unstructured
documents (applications, medical letters, ID proofs, income slips). Staff read
each one, pull out the key fields, notice what's missing, and decide what
happens next. This project does the first pass automatically, cites the policy
it applied, and hands a human a prioritised queue.

> **Why this shape?** FDE roles are consistently described as: embed with a
> customer, find the real workflow, prototype fast, **measure it with evals**,
> then take it to production. This repo has a piece of every one of those
> stages, and it runs offline with no API key so you can start immediately.

---

## Quickstart

```bash
pip install -r requirements.txt

python -m src.cli run data/samples     # process the sample documents
python -m src.cli eval                 # score against the labelled gold set
python -m src.cli tune                 # sweep the routing thresholds
python -m src.cli retrieve "income evidence"   # inspect the policy index
python -m pytest -q                    # run the tests

uvicorn src.api:app --reload           # then open http://127.0.0.1:8000
```

No API key is required. Everything runs with a built-in offline extractor.

### Containerised

```bash
docker compose up --build              # then open http://127.0.0.1:8000
```

---

## What happens to a document

```
file ─► ingest ─► extract ─► validate ─► retrieve ─► route
       (text)    (model →    (policy +   (cite the   (auto_route /
                  typed       confidence) policy)     human_review /
                  object)                             incomplete)
```

- **ingest** (`src/ingest.py`) — PDF/text → plain text.
- **extract** (`src/extract.py` + `src/llm.py`) — the model returns a JSON
  object; we coerce it into a typed `Extraction`. Every field carries a
  confidence.
- **validate** (`src/validate.py`) — two separate checks: *completeness*
  (are required fields present?) and *confidence* (do we trust the values?).
- **retrieve** (`src/retrieve.py`) — find the policy clause the decision
  relies on, so the rationale is citable.
- **route** (`src/schemas.py`) — three outcomes:
  - `auto_route` — complete and confident, straight through
  - `incomplete` — a required field is missing, goes back to the applicant
  - `human_review` — present but uncertain, a person decides

That split — *missing* vs *untrusted* — is the whole point. It is what lets a
system be useful without pretending to be certain.

---

## Retrieval (the RAG half)

A decision that says "missing income" is only useful if it can say *which rule*
it applied. `src/retrieve.py` indexes the office's policy corpus in
`data/policy/`, chunks it on headings so every passage keeps its clause id, and
attaches the top matches to each result:

```
- case_002_application.txt: Missing required field(s): monthly_income.
  Request from applicant. Applies 4.2(a) Requirement.
```

The embedder is swappable, exactly like the model. `HashingEmbedder` runs
offline with no network, so the project still starts with zero setup. It matches
on vocabulary, not meaning — swap in `OpenAIEmbedder` (or any real embedding
model) before you trust the ranking. Being honest about which one you're running
is part of the job.

```bash
python -m src.cli retrieve "identity document name mismatch"
```

### Vector store: Supabase (optional)

By default retrieval runs **in memory** and needs nothing but Python. For a real
vector store, the same interface is backed by Postgres + pgvector:

```bash
# 1. apply the schema (sql/001_triage_policy_passages.sql)
# 2. point the app at your database and load the corpus
export RETRIEVER_BACKEND=supabase
export SUPABASE_DB_URL=postgresql://...   # from the Supabase dashboard
python -m src.cli load-policy
python -m src.cli retrieve "income evidence"
```

The passages live in a dedicated `triage` schema — separate from any
application tables — with RLS on and no public policies. The corpus is chunked
on headings so every row keeps its clause id, and `triage.match_policy_passages`
does cosine search over an HNSW index.

The connection string is read from the environment and never written to the
repo. `RETRIEVER_BACKEND=memory` (the default) keeps the project fully offline,
so you can develop without a database and switch when you need one.

---

## Tuning

"Tuning" is three different jobs, kept apart in `src/tuning.py`:

1. **Routing-policy tuning** — choosing the confidence thresholds. This is a
   business decision: how much risk of a wrong auto-route will the customer
   accept? `python -m src.cli tune` grid-searches the thresholds against the
   gold set and reports decision accuracy alongside auto-route precision,
   because the two trade off.
2. **Prompt / few-shot tuning** — `PROMPT_VARIANTS` holds candidate templates.
   Score them with the eval harness; keep the winner.
3. **Fine-tuning** — `python -m src.cli export-ft` writes a labelled training
   file in provider chat format. It **does not launch a job**: that needs
   credentials and spends money, so it stays a deliberate manual step.

One honest note: under `provider=mock` the extractor ignores the prompt, so a
prompt sweep scores identically for every variant. That is the lesson, not a
bug — you cannot tune a model that does not read your prompt.

---

## Project layout

```
doc-intake-triage/
├── src/
│   ├── config.py      # env-driven settings, safe defaults
│   ├── schemas.py     # the output contract + the office's policy table
│   ├── llm.py         # provider-agnostic client: mock | openai | anthropic
│   ├── ingest.py      # file -> text (pdf/txt/md)
│   ├── extract.py     # model output -> validated Extraction
│   ├── validate.py    # completeness + confidence -> decision
│   ├── retrieve.py    # policy index + retrieval (memory or Supabase/pgvector)
│   ├── load_policy.py # embed the corpus into the Supabase vector store
│   ├── pipeline.py    # orchestration
│   ├── evals.py       # the evaluation harness
│   ├── tuning.py      # threshold sweep, prompt variants, fine-tune export
│   ├── cli.py         # run / eval / tune / export-ft / retrieve
│   └── api.py         # FastAPI service
├── app/index.html     # one-page review-queue UI
├── data/
│   ├── samples/       # 6 synthetic case documents
│   ├── policy/        # the office's policy corpus (retrieval source)
│   └── labels.jsonl   # the gold set the evals score against
├── sql/               # the pgvector schema (triage.policy_passages)
├── tests/             # routing, retrieval, and end-to-end tests
├── Dockerfile         # container image
├── docker-compose.yml # local run
├── .github/workflows/ # CI: tests + eval gate
└── PROJECT_PLAN.md    # the engagement plan this code implements
```

---

## Swapping in a real model

The model is a component, not the system. Set two env vars and the same
pipeline calls a real provider:

```bash
cp .env.example .env
# set DOC_TRIAGE_PROVIDER=openai and OPENAI_API_KEY=...
python -m src.cli run data/samples
```

`src/llm.py` defines one interface (`extract_document`) with three
implementations: `MockLLM` (offline, regex), `OpenAILLM`, `AnthropicLLM`.
Adding a fourth provider is one small class.

The **mock** is a stand-in, not a replacement. Your evals run green against it
because the gold set was written to match the sample documents — that proves
the *harness* works, not that the system is accurate on real data. Point it at
a real model, or at messier documents, and the scorecard will move. Watching it
move is the exercise.

---

## Where to take it next (your FDE reps)

Roughly in order of learning value:

1. **Add hard documents.** Photos of forms, multi-page PDFs, two applicants on
   one page. Watch the scorecard drop, then fix it. This is the real job.
2. **Fuzzy field matching.** Right now evals compare strings exactly. Add
   normalisation for dates and currency so "INR 18,500" == "18,500".
3. **Real embeddings.** Swap `HashingEmbedder` for a semantic embedder and
   measure whether retrieval actually improves the cited clause.
4. **Human-in-the-loop feedback.** Let a reviewer correct a field in the UI and
   append the correction to the gold set. Now the system improves with use.
5. **Batch + queue persistence.** Store results in SQLite; add a status per
   case (new / reviewed / sent back).
6. **Cost & latency.** Log tokens and ms per document; add a cheap-model-first
   fallback for easy documents.
7. **Policy config, not code.** Move `REQUIRED_FIELDS` into a YAML file the
   customer can edit without a deploy.

Each of these maps to a line you can say in an interview: *"the customer
needed X, so I changed Y, and the eval went from A to B."*

---

## Notes

- All sample data is **synthetic** — no real personal or health information.
- If you adapt this to real records, handle them as sensitive from the start:
  data minimisation, access control, and no secrets in the repo.
- Built to be read. If a file is confusing, that is a bug — open it and fix it.
