from __future__ import annotations

import csv
import io
from dataclasses import asdict

from .models import OrderResult

CSV_COLUMNS = ["customer_id", "customer_reference", "line", "code", "description",
               "quantity", "unit", "status", "issues"]


def to_dict(result: OrderResult) -> dict:
    return {
        "source": result.source,
        "workspace": result.workspace,
        "mode": result.mode,
        "seconds": result.seconds,
        "customer_id": result.customer_id,
        "customer_name": result.customer_name,
        "order": result.order.model_dump(),
        "issues": [asdict(i) for i in result.issues],
        "lines": [
            {
                "number": line.number,
                "status": line.status,
                "code": line.code,
                "name": line.name,
                "match_score": line.match_score,
                "quantity": line.quantity,
                "unit": line.unit,
                "extracted": line.extracted.model_dump(),
                "issues": [asdict(i) for i in line.issues],
            }
            for line in result.lines
        ],
    }


def to_csv(result: OrderResult) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for line in result.lines:
        writer.writerow({
            "customer_id": result.customer_id or "",
            "customer_reference": result.order.customer_reference or "",
            "line": line.number,
            "code": line.code or "",
            "description": line.name or line.extracted.description,
            "quantity": "" if line.quantity is None else f"{line.quantity:g}",
            "unit": line.unit or "",
            "status": line.status,
            "issues": " | ".join(i.message for i in line.issues),
        })
    return out.getvalue()
