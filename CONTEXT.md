# Music Store Customer Support

A multi-agent customer-support assistant for a digital music store (Chinook dataset). It verifies who the caller is, answers music-catalog and invoice questions through specialised sub-agents, and remembers each caller's music preferences across sessions.

## Language

**Customer**:
A person with a record in the store's database who can be identified by a customer ID, email, or phone number. Synonymous with **User** in this project — the person chatting and the verified database identity are the same entity.
_Avoid_: User, client, account, caller (use **Customer**)

**Verification**:
The act of resolving free-text caller input into a known `customer_id`. An LLM extracts a structured identifier (customer ID, email, or phone) from the message; a SQL lookup then maps email/phone to the canonical `customer_id`.

**Identifier**:
One of three values a Customer can present to be verified: customer ID, email, or phone number. Email and phone are non-canonical and must be mapped to a customer ID.

**Preference Profile**:
The long-term, per-Customer record of music tastes (e.g. favourite artists and genres) used to personalise recommendations. Stored as a structured object keyed by `customer_id`, read by `load_memory` and updated by `create_memory`. Survives across sessions; distinct from session memory, which only holds the running conversation and `customer_id` for one thread.

**Support Rep**:
The Employee assigned to a Customer (`Customer.SupportRepId → Employee`). This is what "the employee associated with an invoice" resolves to — Chinook has no direct Invoice→Employee link, so an invoice's employee is the support rep of the customer who owns it.

**Invoice**:
A record of one past purchase by a Customer (`Invoice.CustomerId`). Belongs to exactly one Customer; only the owning Customer may view it.

## Relationships

- A **Customer** is resolved through **Verification** into exactly one `customer_id`
- An **Identifier** (id / email / phone) belongs to exactly one **Customer**
- A **Customer** has exactly one **Preference Profile** (keyed by `customer_id`)
- A **Customer** has many **Invoices**; each **Invoice** belongs to exactly one **Customer**
- A **Customer** has one **Support Rep**; an **Invoice**'s employee is the owning Customer's **Support Rep**

## Flagged ambiguities

- "User" vs "Customer" — resolved: these are the **same** entity. Prefer **Customer** throughout.
- "Similar artists" (in `get_tracks_by_artist`) — resolved: means **fuzzy name matching** (`LIKE '%name%'`), not a genre/recommendation engine. Chinook has no artist-similarity data.
