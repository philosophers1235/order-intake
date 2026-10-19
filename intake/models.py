from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


# What the model returns. Values stay as the customer wrote them;
# everything that needs judgement happens later, in plain code.

class ExtractedLine(BaseModel):
    raw: str = Field(description="The whole line exactly as written, including quantity and unit.")
    description: str = Field(description="Item description as written, without quantity and unit.")
    code: str | None = Field(None, description="Item code exactly as written, if the customer gave one.")
    quantity: float | None = Field(None, description="Quantity as a number. Null if it is not stated.")
    unit: str | None = Field(None, description="Unit as written, for example 'pz', 'm', 'box', 'sets'.")
    unit_price: float | None = Field(None, description="Unit price if the customer wrote one.")
    confidence: Confidence = Field("high", description="'low' when handwriting or print quality makes a value uncertain.")
    note: str | None = Field(None, description="Anything a person should know about this line.")


class ExtractedOrder(BaseModel):
    customer_name: str | None = Field(None, description="The business placing the order, not the supplier.")
    customer_contact: str | None = Field(None, description="Person who signed or sent the order.")
    customer_email: str | None = None
    customer_fax: str | None = None
    customer_reference: str | None = Field(None, description="The customer's own order or PO number.")
    order_date: str | None = Field(None, description="ISO date if the year is clear, otherwise as written.")
    delivery: str | None = Field(None, description="Requested delivery date or instructions, as written.")
    notes: str | None = None
    lines: list[ExtractedLine]


# What the pipeline produces after checking the extraction against the workspace.

@dataclass
class Suggestion:
    reason: str
    code: str | None = None
    quantity: float | None = None


@dataclass
class Issue:
    kind: str
    message: str
    suggestion: Suggestion | None = None


@dataclass
class Line:
    number: int
    extracted: ExtractedLine
    code: str | None
    name: str | None
    match_score: float
    quantity: float | None
    unit: str | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "review" if self.issues else "ok"


@dataclass
class OrderResult:
    source: str
    workspace: str
    mode: str
    order: ExtractedOrder
    customer_id: str | None
    customer_name: str | None
    lines: list[Line]
    issues: list[Issue] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def needs_review(self) -> int:
        return sum(1 for line in self.lines if line.status == "review") + len(self.issues)
