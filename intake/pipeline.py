from __future__ import annotations

import re
import time
from typing import Callable

from rapidfuzz import fuzz

from . import rules
from .matching import Matcher, normalize
from .models import ExtractedOrder, Issue, Line, OrderResult
from .sources import Document
from .units import to_sale_units
from .workspace import Customer, Workspace

Extractor = Callable[[Document, str], ExtractedOrder]


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def find_customer(order: ExtractedOrder, workspace: Workspace) -> tuple[Customer | None, float]:
    """Fax number and email are exact; the name is matched loosely."""
    fax = _digits(order.customer_fax)
    email = (order.customer_email or "").lower()
    for customer in workspace.customers:
        if fax and customer.fax and _digits(customer.fax).endswith(fax[-8:]):
            return customer, 100
        if email and customer.email == email:
            return customer, 100

    if not order.customer_name:
        return None, 0
    wanted = normalize(order.customer_name)
    best, best_score = None, 0.0
    for customer in workspace.customers:
        for name in (customer.name, *customer.aliases):
            score = fuzz.token_set_ratio(wanted, normalize(name))
            if score > best_score:
                best, best_score = customer, score
    return (best, best_score) if best_score >= 85 else (None, best_score)


def process(doc: Document, workspace: Workspace, extract: Extractor) -> OrderResult:
    started = time.perf_counter()
    order = extract(doc, workspace.seller)
    customer, _ = find_customer(order, workspace)
    customer_id = customer.id if customer else None
    matcher = Matcher(workspace)

    lines = []
    for number, extracted in enumerate(order.lines, start=1):
        match = matcher.match(extracted, customer_id)
        issues = rules.run(rules.LineContext(workspace, customer_id, extracted, match))
        item = match.item
        qty = None
        if item and extracted.quantity is not None:
            qty, _ = to_sale_units(extracted.quantity, extracted.unit, item)
        lines.append(Line(
            number=number,
            extracted=extracted,
            code=item.code if item else None,
            name=item.name if item else None,
            match_score=round(match.score, 1),
            quantity=qty,
            unit=item.unit if item else extracted.unit,
            issues=issues,
        ))

    order_issues = []
    if customer is None:
        who = order.customer_name or "the sender"
        order_issues.append(Issue("unknown_customer", f"Could not match {who} to a customer account."))

    return OrderResult(
        source=doc.name,
        workspace=workspace.name,
        mode=getattr(extract, "mode", "custom"),
        order=order,
        customer_id=customer_id,
        customer_name=customer.name if customer else None,
        lines=lines,
        issues=order_issues,
        seconds=round(time.perf_counter() - started, 2),
    )
