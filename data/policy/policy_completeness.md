# Policy 2.0 — Completeness and Routing

## 2.0(a) Complete cases
A case with all required fields present, and all fields extracted with high
confidence, may be routed automatically.

## 2.0(b) Incomplete cases
A case missing any required field must be returned to the applicant with a
request for the missing information. Missing fields are not grounds for
rejection.

## 2.0(c) Uncertain cases
A case whose fields are present but not reliably read — low confidence, poor
scan quality, or placeholder text — must be routed to a human reviewer.

## 2.0(d) Auditability
Every routing decision must record the fields used, their confidences, and the
policy clause applied, so the decision can be explained later.
