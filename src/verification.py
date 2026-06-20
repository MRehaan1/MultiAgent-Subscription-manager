"""Customer verification node (Tasks 5 & 7).

Decision (grill #4 & #5): an LLM extracts a structured identifier (customer id /
email / phone) from free text; a deterministic SQL lookup maps email/phone to
the canonical customer_id. This is the single human-in-the-loop point — if no
valid customer_id can be produced, the node `interrupt()`s and loops until the
human supplies working credentials. It runs as an upstream GATE: nothing
sensitive runs until customer_id is set (ADR 0001).
"""

import re
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .config import model
from .database import run_query


class IdentifierExtraction(BaseModel):
    """Structured result of parsing a customer's message for an identifier."""

    identifier_type: Literal["customer_id", "email", "phone", "none"] = Field(
        description="Which kind of identifier the message contains, or 'none'."
    )
    value: str = Field(
        default="",
        description="The raw identifier value found in the message (empty if none).",
    )


_extractor = model.with_structured_output(IdentifierExtraction)

_EXTRACT_SYSTEM = (
    "You extract a customer identifier from a support message. "
    "Return the customer ID, email, or phone number if present, else 'none'. "
    "Do not invent values; only extract what is explicitly in the text."
)


def _extract_identifier(textval: str) -> IdentifierExtraction:
    return _extractor.invoke(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": textval or ""},
        ]
    )


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _lookup_customer_id(parsed: IdentifierExtraction) -> str | None:
    """Map an extracted identifier to a canonical customer_id, or None."""
    if parsed.identifier_type == "none" or not parsed.value.strip():
        return None

    if parsed.identifier_type == "customer_id":
        rows = run_query(
            "SELECT CustomerId FROM Customer WHERE CustomerId = :v",
            {"v": _digits(parsed.value)},
        )
        return str(rows[0]["CustomerId"]) if rows else None

    if parsed.identifier_type == "email":
        rows = run_query(
            "SELECT CustomerId FROM Customer WHERE LOWER(Email) = LOWER(:v)",
            {"v": parsed.value.strip()},
        )
        return str(rows[0]["CustomerId"]) if rows else None

    if parsed.identifier_type == "phone":
        target = _digits(parsed.value)
        if not target:
            return None
        # Phone formats vary wildly; compare digits-only in Python.
        rows = run_query(
            "SELECT CustomerId, Phone FROM Customer WHERE Phone IS NOT NULL"
        )
        for r in rows:
            stored = _digits(r["Phone"])
            if stored and (stored == target or stored.endswith(target[-8:])):
                return str(r["CustomerId"])
        return None

    return None


def _latest_user_text(messages: list) -> str:
    for msg in reversed(messages or []):
        role = getattr(msg, "type", None) or (
            msg.get("role") if isinstance(msg, dict) else None
        )
        if role in ("human", "user"):
            return getattr(msg, "content", None) or (
                msg.get("content") if isinstance(msg, dict) else ""
            )
    return ""


def verify_info(state: dict) -> dict:
    """Resolve the caller to a verified customer_id, interrupting if needed."""
    # Already verified earlier in the session (persisted by the checkpointer).
    if state.get("customer_id"):
        return {}

    text_to_parse = _latest_user_text(state.get("messages", []))
    resumed_inputs: list[str] = []
    while True:
        parsed = _extract_identifier(text_to_parse)
        customer_id = _lookup_customer_id(parsed)
        if customer_id is not None:
            update = {"customer_id": customer_id}
            # Surface whatever the human typed at the interrupt (it often
            # contains the actual question, not just credentials) so the
            # supervisor answers it instead of only seeing the first message.
            if resumed_inputs:
                update["messages"] = [HumanMessage(content=t) for t in resumed_inputs]
            return update
        # HITL: pause and ask the human; their reply resumes here.
        # First contact gets a greeting; only retries say "couldn't verify".
        if not resumed_inputs:
            prompt = (
                "Hi! Welcome to Music Store support. Before I can help, I need to "
                "verify your account — please share your customer ID, email, or "
                "phone number."
            )
        else:
            prompt = (
                "I couldn't verify your identity. Please provide your "
                "customer ID, email, or phone number."
            )
        text_to_parse = interrupt(prompt)
        resumed_inputs.append(text_to_parse)
