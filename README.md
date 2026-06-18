# Music Store Customer Support — Multi-Agent System

A customer-support assistant for a digital music store (Chinook dataset), built
with **LangGraph**, **langgraph-supervisor**, and **Gemini** (`gemini-2.0-flash`).
It verifies the customer, routes questions to specialised sub-agents, and
remembers each customer's music preferences across sessions.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your free Gemini API key
```

Get a free Gemini key at https://aistudio.google.com/apikey.

## Run

```bash
python -m src.main            # run from the project root
```

`:new` starts a fresh session (for Test Case 2); `:quit` exits.

## Architecture

```
START -> verify_info -> load_memory -> supervisor -> create_memory -> END
              │                            ├─ music_catalog (sub-agent)
              └─ interrupt() (HITL)        └─ invoice_info  (sub-agent)
```

| Module | Responsibility |
|---|---|
| `config.py` | Gemini model (temperature=0, max_retries=3) |
| `database.py` | Chinook in-memory SQLite + parameterized `run_query` |
| `catalog_tools.py` | 4 music tools — fuzzy `LIKE` matching |
| `invoice_tools.py` | 3 invoice tools — `customer_id` injected from verified state |
| `verification.py` | structured-extraction + SQL lookup + the single HITL interrupt |
| `memory.py` | `PreferenceProfile`, `load_memory`, gated `create_memory` |
| `agents.py` | sub-agents (`create_react_agent`) + supervisor |
| `graph.py` | outer `StateGraph`, compiled with checkpointer + store |
| `main.py` | interactive REPL |

## Key design decisions

See `CONTEXT.md` (domain language) and `docs/adr/0001-*.md` (the verification
gate + identity-injection security model). Highlights:

- **Verification is an upstream gate** — sensitive queries cannot run before a
  `customer_id` is established.
- **`customer_id` is injected** into invoice tools from verified state (via
  `InjectedState`), never supplied by the LLM — prevents cross-customer snooping.
- **Two memories:** session (`InMemorySaver`) + long-term preferences
  (`InMemoryStore`, keyed by `customer_id`).
- **`create_memory` is gated** to music-engaged turns + uses a PII-excluding
  prompt, so financial data never enters the preference profile.

## Test scenarios

1. **Provide info (same session):**
   - `My phone number is +55 (12) 3923-5555. How much was my most recent purchase? What albums do you have by the Rolling Stones?`
   - then: `List some songs that match my preferences?` → Rolling Stones songs.
2. **Missing info (`:new` session):**
   - `How much was my most recent purchase? What albums do you have by the Rolling Stones?` → interrupts asking for credentials.
