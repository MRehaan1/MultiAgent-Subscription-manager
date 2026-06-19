"""Optional Langfuse tracing.

If LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set, every LLM / agent / tool
call is traced. If they're blank (or langfuse isn't installed), tracing is
silently disabled and the app runs normally.

We read LANGFUSE_BASE_URL for the host (falling back to LANGFUSE_HOST, then
Langfuse cloud), so the .env can use either name.
"""

import os

_DEFAULT_HOST = "https://cloud.langfuse.com"


def get_langfuse_handler():
    """Return a Langfuse LangChain CallbackHandler, or None if not configured."""
    public = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret = os.getenv("LANGFUSE_SECRET_KEY")
    if not (public and secret):
        return None  # tracing disabled

    host = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or _DEFAULT_HOST
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler
    except ImportError:
        return None

    # Configure the singleton client; the CallbackHandler picks it up.
    Langfuse(public_key=public, secret_key=secret, host=host)
    return CallbackHandler()


def flush_langfuse() -> None:
    """Flush pending traces (Langfuse batches in the background)."""
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        pass
