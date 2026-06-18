"""Sub-agents + supervisor (Tasks 3 & 4).

Decision (grill #3): prebuilt agents + `langgraph-supervisor` for routing. On
LangChain v1 the constructor is `langchain.agents.create_agent` (the old
`langgraph.prebuilt.create_react_agent` is deprecated). The music agent's
runtime preference injection (grill #10) is now done with the `dynamic_prompt`
middleware, which reads `loaded_memory` from the request state.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langgraph_supervisor import create_supervisor

from .catalog_tools import CATALOG_TOOLS
from .config import model
from .invoice_tools import INVOICE_TOOLS
from .state import AgentState, State


@dynamic_prompt
def _music_system_prompt(request) -> str:
    """Inject the customer's loaded preferences into the music agent's prompt."""
    prefs = request.state.get("loaded_memory") or "No saved preferences yet."
    return (
        "You are the Music Catalog agent for a digital music store. "
        "Answer questions about albums, tracks, and genres, and give "
        "recommendations, using ONLY your tools (never invent catalog data).\n"
        f"The customer's known music preferences: {prefs}\n"
        "When the customer asks for recommendations or 'songs that match my "
        "preferences', use these preferences to decide which artists or "
        "genres to look up."
    )


_INVOICE_PROMPT = (
    "You are the Invoice Information agent for a digital music store. "
    "Answer questions about the customer's past purchases, invoice details, and "
    "the support rep who handles their invoices, using ONLY your tools. "
    "The customer's identity is already verified and injected into the tools — "
    "never ask the customer for their customer ID, and never look up other "
    "customers."
)

_SUPERVISOR_PROMPT = (
    "You are a customer-support supervisor managing two agents:\n"
    "- music_catalog: music discovery, recommendations, and catalog search "
    "(albums, tracks, genres).\n"
    "- invoice_info: past purchases, invoice details, and the customer's support "
    "rep.\n\n"
    "A single request may need BOTH agents (e.g. 'how much was my last purchase "
    "and what albums do you have by X?'). In that case delegate to each relevant "
    "agent one at a time, then COMBINE their results into one clear final answer. "
    "Do not answer catalog or invoice questions yourself — always use the agents."
)


music_agent = create_agent(
    model,
    tools=CATALOG_TOOLS,
    middleware=[_music_system_prompt],
    state_schema=AgentState,
    name="music_catalog",
)

invoice_agent = create_agent(
    model,
    tools=INVOICE_TOOLS,
    system_prompt=_INVOICE_PROMPT,
    state_schema=AgentState,
    name="invoice_info",
)

# Supervisor graph — compiled and embedded as a node in the outer graph.
# output_mode="full_history" propagates the sub-agents' tool-call messages up to
# the outer state, so create_memory's "music engaged?" gate can see them.
supervisor = create_supervisor(
    agents=[music_agent, invoice_agent],
    model=model,
    prompt=_SUPERVISOR_PROMPT,
    state_schema=State,
    output_mode="full_history",
).compile()
