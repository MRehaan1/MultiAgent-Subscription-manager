"""Long-term preference memory (Task 6).

- Stored in an InMemoryStore, namespaced by ("memory_profile", customer_id),
  key "user_memory" (decision: grill #6) — per-customer isolation.
- `load_memory` reads the profile and flattens it into `loaded_memory` (a str,
  per the brief's State schema); the music agent injects this into its prompt.
- `create_memory` is GATED (decision: grill #7, Option B): it only runs when the
  music_catalog agent was engaged, and uses a PII-excluding prompt + merge
  semantics so financial data never leaks into the profile.
"""

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from .catalog_tools import CATALOG_TOOL_NAMES
from .config import model

_NAMESPACE_PREFIX = "memory_profile"
_KEY = "user_memory"


class PreferenceProfile(BaseModel):
    """A customer's long-term music tastes."""

    favorite_artists: list[str] = Field(default_factory=list)
    favorite_genres: list[str] = Field(default_factory=list)
    notes: str = ""


_memory_extractor = model.with_structured_output(PreferenceProfile)

_MEMORY_SYSTEM = (
    "You maintain a customer's MUSIC preference profile. "
    "Given the existing profile and the latest conversation, return the UPDATED "
    "full profile, MERGING new musical tastes (artists, genres) with the existing "
    "ones — never drop existing entries. "
    "Record ONLY musical taste. NEVER record purchase amounts, invoice details, "
    "dates, phone numbers, emails, or any financial or personal data."
)


def _namespace(customer_id: str) -> tuple[str, str]:
    return (_NAMESPACE_PREFIX, str(customer_id))


def _profile_to_text(profile: PreferenceProfile) -> str:
    parts = []
    if profile.favorite_artists:
        parts.append("Favorite artists: " + ", ".join(profile.favorite_artists))
    if profile.favorite_genres:
        parts.append("Favorite genres: " + ", ".join(profile.favorite_genres))
    if profile.notes:
        parts.append("Notes: " + profile.notes)
    return " | ".join(parts) if parts else "No saved preferences yet."


def _music_engaged(messages: list) -> bool:
    """True if any music_catalog tool was called in the conversation."""
    for msg in messages or []:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name in CATALOG_TOOL_NAMES:
                return True
    return False


def _conversation_text(messages: list) -> str:
    out = []
    for msg in messages or []:
        role = getattr(msg, "type", "") or ""
        content = getattr(msg, "content", "") or ""
        if role in ("human", "ai") and content:
            out.append(f"{role}: {content}")
    return "\n".join(out)


def load_memory(state: dict, *, store: BaseStore) -> dict:
    """Read the customer's preference profile into `loaded_memory`."""
    customer_id = state.get("customer_id")
    if not customer_id:
        return {"loaded_memory": ""}
    item = store.get(_namespace(customer_id), _KEY)
    if item is None:
        return {"loaded_memory": "No saved preferences yet."}
    profile = PreferenceProfile(**item.value)
    return {"loaded_memory": _profile_to_text(profile)}


def create_memory(state: dict, *, store: BaseStore) -> dict:
    """Update the preference profile — only on music-engaged turns (gated)."""
    customer_id = state.get("customer_id")
    messages = state.get("messages", [])
    if not customer_id or not _music_engaged(messages):
        return {}

    ns = _namespace(customer_id)
    existing_item = store.get(ns, _KEY)
    existing = (
        PreferenceProfile(**existing_item.value)
        if existing_item is not None
        else PreferenceProfile()
    )

    updated = _memory_extractor.invoke(
        [
            {"role": "system", "content": _MEMORY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Existing profile: {existing.model_dump()}\n\n"
                    f"Conversation:\n{_conversation_text(messages)}"
                ),
            },
        ]
    )
    store.put(ns, _KEY, updated.model_dump())
    return {}
