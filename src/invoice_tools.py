"""Invoice Information tools (Task 3).

SECURITY (decision: grill #8 + ADR 0001): `customer_id` is injected from the
verified graph State via `InjectedState` — it is hidden from the model's tool
schema, so the LLM cannot set or override it. Every query is also scoped with
`WHERE CustomerId = :verified_id`, so a verified customer can only ever read
their own data (no snooping by guessing invoice ids or asking for another id).
"""

from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .database import run_query


@tool
def get_invoices_by_customer_sorted_by_date(
    customer_id: Annotated[str, InjectedState("customer_id")],
) -> str:
    """Retrieve the verified customer's invoices, most recent first.

    Use this for questions like "how much was my most recent purchase?".
    """
    rows = run_query(
        """
        SELECT InvoiceId, InvoiceDate, Total
        FROM Invoice
        WHERE CustomerId = :c
        ORDER BY InvoiceDate DESC
        """,
        {"c": customer_id},
    )
    if not rows:
        return "No invoices found for your account."
    lines = [
        f"- Invoice #{r['InvoiceId']}: {r['InvoiceDate']} — total ${r['Total']:.2f}"
        for r in rows
    ]
    return "Your invoices (most recent first):\n" + "\n".join(lines)


@tool
def get_invoices_sorted_by_unit_price(
    customer_id: Annotated[str, InjectedState("customer_id")],
) -> str:
    """Retrieve the verified customer's invoices, highest amount first.

    ("Unit price" is interpreted as the invoice total — the meaningful price
    ordering for whole invoices.)
    """
    rows = run_query(
        """
        SELECT InvoiceId, InvoiceDate, Total
        FROM Invoice
        WHERE CustomerId = :c
        ORDER BY Total DESC
        """,
        {"c": customer_id},
    )
    if not rows:
        return "No invoices found for your account."
    lines = [
        f"- Invoice #{r['InvoiceId']}: ${r['Total']:.2f} ({r['InvoiceDate']})"
        for r in rows
    ]
    return "Your invoices (highest amount first):\n" + "\n".join(lines)


@tool
def get_employee_by_invoice_and_customer(
    invoice_id: str,
    customer_id: Annotated[str, InjectedState("customer_id")],
) -> str:
    """Retrieve the support rep (employee) associated with one of the customer's invoices.

    Chinook has no direct invoice->employee link, so this resolves to the
    support rep assigned to the customer who owns the invoice
    (Invoice -> Customer.SupportRepId -> Employee). Returns nothing if the
    invoice does not belong to the verified customer.
    """
    rows = run_query(
        """
        SELECT e.FirstName, e.LastName, e.Title, e.Email, e.Phone
        FROM Invoice i
        JOIN Customer c ON i.CustomerId = c.CustomerId
        JOIN Employee e ON c.SupportRepId = e.EmployeeId
        WHERE i.InvoiceId = :inv AND i.CustomerId = :c
        """,
        {"inv": invoice_id, "c": customer_id},
    )
    if not rows:
        return f"No invoice #{invoice_id} found on your account."
    e = rows[0]
    return (
        f"Invoice #{invoice_id} is handled by your support rep "
        f"{e['FirstName']} {e['LastName']} ({e['Title']}), "
        f"email {e['Email']}, phone {e['Phone']}."
    )


INVOICE_TOOLS = [
    get_invoices_by_customer_sorted_by_date,
    get_invoices_sorted_by_unit_price,
    get_employee_by_invoice_and_customer,
]
