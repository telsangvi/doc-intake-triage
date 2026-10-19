# Document Intake Triage

A small, readable project that turns messy case documents into a structured
**review queue** — built as a hands-on way to practise the Forward Deployed
AI Engineer (FDE) skill set.

The scenario: a public-benefits office receives a pile of unstructured
documents (applications, medical letters, ID proofs, income slips). Staff read
each one, pull out the key fields, notice what's missing, and decide what
happens next. This project does the first pass automatically and hands a human
a prioritised queue.

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
python -m pytest -q                    # run the tests

uvicorn src.api:app --reload           # then open http://127.0.0.1:8000
```

No API key is required. Everything runs with a built-in offline extractor.

---

## What happens to a document

```
file ──► ingest ──► extract ──► validate ──► route
        (text)     (model →    (policy +    (auto_route /
                    typed       confidence)  human_review /
                    object)                  incomplete)
```

- **ingest** (`src/ingest.py`) — PDF/text → plain text.
- **extract** (`src/extract.py` + `src/llm.py`) — the model returns a JSON
  object; we coerce it into a typed `Extraction`. Every field carries a
  confidence.
- **validate** (`src/validate.py`) — two separate checks: *completeness*
  (are required fields present?) and *confidence* (do we trust the values?).
- **route** (`src/schemas.py`) — three outcomes:
  - `auto_route` — complete and confident, straight through
  - `incomplete` — a required field is missing, goes back to the applicant
  - `human_review` — present but uncertain, a person decides

That split — *missing* vs *untrusted* — is the whole point. It is what lets a
system be useful without pretending to be certain.

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
│   ├── pipeline.py    # orchestration
│   ├── evals.py       # the evaluation harness
│   ├── cli.py         # run / eval commands
│   └── api.py         # FastAPI service
├── app/index.html     # one-page review-queue UI
├── data/
│   ├── samples/       # 6 synthetic case documents
│   └── labels.jsonl   # the gold set the evals score against
├── tests/             # routing + end-to-end tests
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

## The eval harness

`python -m src.cli eval` prints a scorecard:

```
doc-type accuracy: 100%
decision accuracy: 100%
field accuracy   : 100%
```

Three numbers, because there are three different things to get right:
classification, extraction, and routing. Field-level misses are printed by name
— they are your next prompt or rule iteration.

---

## Where to take it next (your FDE reps)

Roughly in order of learning value:

1. **Add hard documents.** Photos of forms, multi-page PDFs, two applicants on
   one page. Watch the scorecard drop, then fix it. This is the real job.
2. **Fuzzy field matching.** Right now evals compare strings exactly. Add
   normalisation for dates and currency so "INR 18,500" == "18,500".
3. **Human-in-the-loop feedback.** Let a reviewer correct a field in the UI and
   append the correction to the gold set. Now the system improves with use.
4. **Batch + queue persistence.** Store results in SQLite; add a status per
   case (new / reviewed / sent back).
5. **Cost & latency.** Log tokens and ms per document; add a cheap-model-first
   fallback for easy documents.
6. **Policy config, not code.** Move `REQUIRED_FIELDS` into a YAML file the
   customer can edit without a deploy.
7. **Deploy it.** Containerise the API, add a health check and structured
   logs, and run it somewhere real.

Each of these maps to a line you can say in an interview: *"the customer
needed X, so I changed Y, and the eval went from A to B."*

---

## Notes

- All sample data is **synthetic** — no real personal or health information.
- If you adapt this to real records, handle them as sensitive from the start:
  data minimisation, access control, and no secrets in the repo.
- Built to be read. If a file is confusing, that is a bug — open it and fix it.
