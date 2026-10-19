# Project Plan — Document Intake Triage

This is the *engagement* behind the code: how a forward-deployed engineer would
frame, scope, and deliver this piece of work. It is written as if for a real
customer, because that is the muscle the role trains.

---

## 1. The customer and the problem

**Customer:** a state benefits office (a good stand-in for any public-sector or
healthcare back office). They process benefit applications and the documents
that support them.

**The workflow today.** An application arrives with attachments — a form, an ID
proof, sometimes a medical letter, sometimes an income slip. A caseworker opens
each document, reads it, retypes the key fields into a case system, checks
whether anything required is missing, and either moves the case forward or
writes back to the applicant asking for what's absent.

**Where it hurts.**
- It is slow and repetitive, and the backlog grows in bursts.
- The most common cause of a stalled case is a *missing field* nobody noticed
  until later — so the applicant waits, and the office pays for the round trip.
- Scanned and handwritten documents are the worst: low quality means low
  confidence, and a caseworker has no signal about which fields to trust.

**What we are NOT doing.** We are not deciding who gets benefits. The system
does not approve, deny, or score people. It extracts, checks completeness, and
routes. Humans keep every decision that matters. Saying this clearly, early, is
part of the job.

---

## 2. What "done" looks like (success metrics)

Written with the customer before building, because "it works" is not a metric.

| Metric | Baseline (manual) | Target |
| --- | --- | --- |
| Time to first-pass triage per document | ~4 min | < 20 sec |
| Missing-field cases caught before caseworker review | ~60% | > 95% |
| Field extraction accuracy on required fields | n/a | > 90% |
| Documents needing a human | 100% | < 40% |
| Documents auto-routed correctly | n/a | > 98% precision |

The last row matters most: an auto-route that is *wrong* is worse than no
automation. We optimise for precision on auto-routes and accept a larger
human-review bucket.

---

## 3. Solution architecture

```
                    ┌──────────────────────────────────────────┐
  documents  ─────► │  ingest: pdf / txt / image → text         │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  extract: LLM → JSON → typed Extraction   │
                    │  (provider-agnostic; mock offline)        │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  validate: policy (completeness)          │
                    │          + confidence thresholds          │
                    └───────────────────┬──────────────────────┘
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  retrieve: policy clause the decision     │
                    │  relies on (RAG over data/policy)         │
                    └───────────────────┬──────────────────────┘
                                        ▼
              ┌─────────────────┬───────────────┬─────────────────┐
              ▼                 ▼               ▼
        auto_route        human_review      incomplete
        (straight          (review          (back to
         through)           queue)           applicant)
```

Two design choices carry the weight:

- **Structured output as a contract.** The model must return a fixed JSON
  shape. That shape is what the customer's case system consumes, and it is what
  the evals score. The model is swappable; the contract is not.
- **Confidence is a first-class field.** Every value carries a score, so the
  system can say "I found it, but I'm not sure" instead of guessing.
- **Every decision is grounded and citable.** The routing decision retrieves the
  policy clause it applied from the office's own corpus and records it. A
  decision that cannot name its rule is not auditable, and Policy 2.0(d)
  requires that it can be explained later.

---

## 4. Data, privacy, and safety

Public-sector and healthcare documents are sensitive by default.

- **Data minimisation.** Extract only the fields the workflow needs.
- **No training on customer data.** Use providers with a no-training
  guarantee, or a self-hosted model for the most sensitive deployments.
- **Human-in-the-loop for anything uncertain.** The system never silently
  overwrites a caseworker's judgement.
- **Auditability.** Every routing decision stores the fields, confidences, and
  a plain-language rationale, so a decision can be explained later.
- **No secrets in the repo.** Keys come from the environment, never the code.

---

## 5. Delivery plan (roughly 3 weeks of focused work)

**Week 1 — discovery and a working prototype.**
Sit with two caseworkers, watch them triage 20 real documents, and write down
the required fields and the reasons cases stall. Build the thinnest end-to-end
path: one document type, extract, route, print. Demo it on day 4.

**Week 2 — evals and the hard documents.**
Write the gold set *before* tuning anything. Measure classification, field
extraction, and routing separately. Add the documents that break it — scans,
handwriting, multi-page. Iterate prompt and rules against the scorecard. Add the
policy corpus and wire retrieval into the rationale, so every decision names the
clause it applied.

**Week 3 — review queue, tuning, and rollout.**
Ship the review-queue UI. Sweep the routing thresholds against the customer's
risk appetite: how much auto-route precision will they accept, and how much
human review will they staff? Add reviewer corrections feeding the gold set.
Containerise the service, put the API behind a health check and logs, and add a
CI gate so the eval score cannot silently regress. Run it alongside the manual
process on a real batch, compare, and tune.

Throughout: a running one-page log of decisions and their reasons — the
artifact that turns a deployment into reusable patterns.

---

## 6. Evaluation plan

- **Gold set:** documents with human-verified fields, classifications, and
  expected routing.
- **Three metrics, tracked per change:** doc-type accuracy, field accuracy,
  decision accuracy.
- **Regression gate:** a change that lowers field accuracy on the gold set
  does not ship, no matter how good the demo looks.
- **Field-level error review:** the scorecard names each miss; those drive the
  next iteration.
- **Threshold sweep:** routing thresholds are tuned against the gold set, and
  the sweep reports auto-route precision next to decision accuracy, because the
  two trade off. The chosen setting is a customer decision, recorded with its
  reasoning.
- **Retrieval quality:** whether the cited clause is the right one is checked
  the same way as extraction — against a labelled expectation, not by eye.
- **Real-data drift:** re-score monthly on a sample of live documents, because
  the distribution of documents changes over time.

---

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Model confidently invents a value | Low-confidence routing + human review + evals that catch it |
| Poor scans defeat extraction | Route low-confidence to humans; add OCR; flag document quality |
| Auto-route sends a bad case through | Optimise for precision; conservative thresholds; audit trail |
| Scope creep into "decide eligibility" | Written boundary: extract and route only, never adjudicate |
| Customer can't maintain it | Policy in config, not code; a playbook and a handover session |

---

## 8. Demo script (2 minutes)

1. **Frame it.** "A benefits office triages documents by hand. Here's the
   backlog problem and the one metric we're moving."
2. **Drop three documents** into the UI — a clean application, one missing its
   income, and a bad scan.
3. **Show the queue.** One auto-routes, one goes back for a missing field, one
   is flagged for a human because the scan is unclear.
4. **Open the scorecard.** "Here's accuracy on the gold set, and here's what we
   do when it drops."
5. **Close on the loop.** "The reviewer's corrections feed the gold set, so it
   gets better with use. That's the part that makes it a deployment, not a
   demo."

---

## 9. How to talk about this in an interview

Lead with the customer and the outcome, not the tech:

- *"A benefits office was losing time to manual triage and missed fields. I
  built a pipeline that extracts and routes, and cut time-to-triage from
  minutes to seconds."*
- *"The key decision was separating 'missing' from 'uncertain' — one goes back
  to the applicant, the other to a human. That's what made it trustworthy."*
- *"I wrote the eval before I tuned anything. Every change had to hold field
  accuracy or it didn't ship."*
- *"It runs offline with a mock model so the customer can see it in a meeting
  without a data-processing agreement in place."*

Then be ready for the follow-ups: how you'd handle a bad scan, how you'd price
it, what you'd do if the model disagreed with the caseworker, and how you'd
scale it from one office to fifty.
