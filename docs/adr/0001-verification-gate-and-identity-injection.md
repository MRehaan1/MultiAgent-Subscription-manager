# 1. Verification as an upstream gate + tool-level identity injection

Date: 2026-06-18

## Status

Accepted

## Context

The system answers two kinds of questions for a music-store Customer: public
music-catalog queries, and **sensitive** account queries (past purchases,
invoice totals, the assigned Support Rep). Sensitive queries must only ever
reveal data belonging to the Customer actually making the request.

The whole system is a chat interface backed by an LLM. The LLM is helpful and
obedient by nature, so if it is trusted to decide *whose* data to fetch, a
Customer can simply ask for someone else's — "show me the invoices for customer
50", "who handled invoice #200?" (an invoice they don't own), or even
"ignore previous instructions and...". This is the snooping threat: a verified
Customer fishing for *another* Customer's private data.

We needed to decide where identity is established and how the verified identity
reaches the data-access tools.

## Decision

Two coupled decisions:

1. **Verification is an upstream gate, not an agent capability.** The graph runs
   a dedicated `verify_info` node **before** the supervisor. It extracts an
   identifier (customer ID / email / phone) via a structured-output LLM call,
   maps it to the canonical `customer_id` via a parameterized SQL lookup, and
   writes `customer_id` into `State`. If it cannot produce a valid `customer_id`
   it fires a single `interrupt()` (human-in-the-loop) and loops until verified.
   The supervisor and sub-agents therefore only ever run *after* a verified
   `customer_id` exists.

2. **Sensitive tools receive `customer_id` by injection, never from the LLM.**
   The invoice tools take `customer_id` via LangGraph's `InjectedState`, so the
   parameter is filled from verified `State` and hidden from the model's tool
   schema. The model cannot set or override it. Sensitive queries are
   additionally scoped in SQL (`WHERE ... AND CustomerId = :verified_id`) so an
   invoice that does not belong to the verified Customer returns zero rows.

The trust boundary lives in code (the gate + SQL scoping + injection), not in
the model's judgement.

## Consequences

**Positive**
- A verified Customer structurally cannot reach another Customer's data,
  regardless of how the chat message is phrased (prompt injection included).
- Identity resolution is deterministic and testable in isolation.
- Removes a class of LLM mistakes (passing the wrong / a hallucinated ID).

**Negative / costs**
- The graph topology is fixed around the gate; reordering it later (e.g. lazy
  verification only when a sensitive tool is hit) is a structural change, not a
  config tweak.
- The agent cannot handle identity "conversationally" (e.g. acting on behalf of
  another account) — by design.
- The brief's tool signatures still show `customer_id: str`, but the parameter
  is injected rather than LLM-supplied; this divergence must be explained to a
  reader.

## Alternatives considered

- **Let the LLM pass `customer_id` as a normal tool argument.** Simplest, and
  matches the brief's signatures literally. Rejected: it makes snooping trivial —
  the model will pass whatever ID the conversation suggests.
- **Verification as a tool the supervisor calls on demand.** More flexible, lets
  the agent decide when identity is needed. Rejected: it allows a sensitive tool
  to run before identity is established, and relies on the model to *choose* to
  verify — not a guarantee.
