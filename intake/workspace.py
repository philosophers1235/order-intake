"""A workspace is one distributor: its catalog, customers and order history.

Everything is plain CSV so it can be exported from any ERP without code.
"""
from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Item:
    code: str
    name: str
    aliases: tuple[str, ...]
    unit: str
    content_qty: float | None
    content_unit: str | None
    price: float | None
    previous_price: float | None
    status: str
    replaced_by: str | None

    @property
    def discontinued(self) -> bool:
        return self.status == "discontinued"


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    aliases: tuple[str, ...]
    email: str | None
    fax: str | None


@dataclass(frozen=True)
class Purchase:
    day: date
    customer_id: str
    code: str
    qty: float


def _split(value: str | None) -> tuple[str, ...]:
    return tuple(v.strip() for v in (value or "").split("|") if v.strip())


def _number(value: str | None) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Workspace:
    def __init__(self, path: Path, seller: str, currency: str,
                 items: list[Item], customers: list[Customer], history: list[Purchase]):
        self.path = path
        self.seller = seller
        self.currency = currency
        self.items = {item.code: item for item in items}
        self.customers = customers
        self.history = sorted(history, key=lambda p: p.day)

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def load(cls, path: str | Path) -> Workspace:
        path = Path(path)
        meta = json.loads((path / "workspace.json").read_text(encoding="utf-8"))
        items = [
            Item(
                code=r["code"].strip(),
                name=r["name"].strip(),
                aliases=_split(r.get("aliases")),
                unit=r["unit"].strip(),
                content_qty=_number(r.get("content_qty")),
                content_unit=(r.get("content_unit") or "").strip() or None,
                price=_number(r.get("price")),
                previous_price=_number(r.get("previous_price")),
                status=(r.get("status") or "active").strip(),
                replaced_by=(r.get("replaced_by") or "").strip() or None,
            )
            for r in _rows(path / "catalog.csv")
        ]
        customers = [
            Customer(
                id=r["id"].strip(),
                name=r["name"].strip(),
                aliases=_split(r.get("aliases")),
                email=(r.get("email") or "").strip().lower() or None,
                fax=(r.get("fax") or "").strip() or None,
            )
            for r in _rows(path / "customers.csv")
        ]
        history = [
            Purchase(date.fromisoformat(r["date"]), r["customer_id"].strip(), r["code"].strip(), float(r["qty"]))
            for r in _rows(path / "history.csv")
        ]
        return cls(path, meta["seller"], meta.get("currency", "EUR"), items, customers, history)

    def purchases(self, customer_id: str, code: str | None = None) -> list[Purchase]:
        return [p for p in self.history
                if p.customer_id == customer_id and (code is None or p.code == code)]

    def usual_quantity(self, customer_id: str, code: str, last: int = 3) -> tuple[float | None, list[Purchase]]:
        recent = self.purchases(customer_id, code)[-last:]
        if not recent:
            return None, []
        return statistics.median(p.qty for p in recent), recent
