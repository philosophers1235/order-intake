"""Checks that decide whether a line can go straight to the ERP.

Each check looks at one line and returns an Issue or None. A line with no
issues is ready; anything else goes to a person, with a suggested fix when
the catalog or the customer's history gives us one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .matching import SURE, Match
from .models import ExtractedLine, Issue, Suggestion
from .units import to_sale_units
from .workspace import Workspace


@dataclass
class LineContext:
    workspace: Workspace
    customer_id: str | None
    line: ExtractedLine
    match: Match


def _money(value: float, currency: str) -> str:
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency + " ")
    return f"{symbol}{value:,.2f}"


def check_match(ctx: LineContext) -> Issue | None:
    m = ctx.match
    if m.item is None:
        close = [item for item, score in m.alternatives[:1] if score >= 50]
        if close:
            return Issue("unknown_item", f"Not in the catalog. Closest is {close[0].code} {close[0].name}.")
        return Issue("unknown_item", "Not in the catalog.")
    if m.via == "code with a typo":
        return Issue("code_typo", f"Code {ctx.line.code} does not exist; looks like {m.item.code}.",
                     Suggestion("closest existing code", code=m.item.code))
    if m.ambiguous:
        options = " or ".join(f"{item.code}" for item, _ in [(m.item, m.score), *m.alternatives[:2]])
        return Issue("ambiguous_item", f"\"{ctx.line.description}\" could be {options}.")
    if m.score < SURE:
        return Issue("uncertain_match", f"Matched to {m.item.code} {m.item.name}, but the description differs.",
                     Suggestion("best match in the catalog", code=m.item.code))
    return None


def check_discontinued(ctx: LineContext) -> Issue | None:
    item = ctx.match.item
    if item is None or not item.discontinued:
        return None
    replacement = item.replaced_by and ctx.workspace.items.get(item.replaced_by)
    if not replacement:
        return Issue("discontinued", f"{item.code} is discontinued and has no replacement in the catalog.")
    reason = f"{replacement.code} replaces it in the catalog"
    if ctx.customer_id:
        bought = ctx.workspace.purchases(ctx.customer_id, replacement.code)
        if bought:
            last = bought[-1]
            reason = f"{replacement.code} replaces it, and this customer ordered it on {last.day:%d %b %Y}"
    return Issue("discontinued", f"{item.code} is no longer sold. Use {replacement.code} {replacement.name}?",
                 Suggestion(reason, code=replacement.code, quantity=ctx.line.quantity))


def check_quantity(ctx: LineContext) -> Issue | None:
    item = ctx.match.item
    if item is None:
        return None
    if ctx.line.quantity is None:
        if ctx.customer_id:
            usual, recent = ctx.workspace.usual_quantity(ctx.customer_id, item.code)
            if usual is not None:
                history = ", ".join(f"{p.qty:g}" for p in recent)
                return Issue("missing_quantity", "No quantity written.",
                             Suggestion(f"usual quantity for this customer (last orders: {history})", quantity=usual))
        return Issue("missing_quantity", "No quantity written and no order history to suggest one.")

    qty, problem = to_sale_units(ctx.line.quantity, ctx.line.unit, item)
    if problem:
        suggestion = Suggestion("round up to whole units", quantity=float(-(-qty // 1))) if qty else None
        return Issue("unit", problem, suggestion)

    if ctx.customer_id:
        usual, recent = ctx.workspace.usual_quantity(ctx.customer_id, item.code, last=5)
        if usual and len(recent) >= 3 and qty > 3 * usual:
            return Issue("unusual_quantity",
                         f"{qty:g} is {qty / usual:.0f}× what this customer usually orders ({usual:g}).",
                         Suggestion("usual quantity", quantity=usual))
    return None


def check_price(ctx: LineContext) -> Issue | None:
    item, written = ctx.match.item, ctx.line.unit_price
    if item is None or written is None or item.price is None:
        return None
    if abs(written - item.price) / item.price <= 0.02:
        return None
    cur = ctx.workspace.currency
    message = f"Order says {_money(written, cur)}, list price is {_money(item.price, cur)}."
    if item.previous_price and abs(written - item.previous_price) < 0.005:
        message += " That was the price before the last list update."
    return Issue("price", message)


def check_legibility(ctx: LineContext) -> Issue | None:
    if ctx.line.confidence == "low":
        return Issue("hard_to_read", "Hard to read in the original. Check it against the document.")
    return None


CHECKS = [check_match, check_discontinued, check_quantity, check_price, check_legibility]


def run(ctx: LineContext) -> list[Issue]:
    issues = []
    for check in CHECKS:
        issue = check(ctx)
        if issue:
            issues.append(issue)
            if issue.kind in {"unknown_item", "ambiguous_item"}:
                break  # nothing else is meaningful without an item
    return issues

