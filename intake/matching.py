"""Match what the customer wrote to an item in the catalog.

Order of trust: an exact item code, then a code with a typo, then the
description. Descriptions are compared on normalised tokens; numbers in the
description must agree with the item (2,5 mm cable is not 1,5 mm cable).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .models import ExtractedLine
from .workspace import Item, Workspace

SURE = 90
PROBABLE = 75
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def code_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _stem(token: str) -> str:
    if any(c.isdigit() for c in token):
        return token
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    if len(token) > 4 and token[-1] in "aeio":
        token = token[:-1]
    return token


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)       # 2,5 -> 2.5
    text = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", "", text)  # 5w-30 -> 5w30
    text = re.sub(r"(\d)\s*(mm²|mm2|mmq)", r"\1 mm", text)
    text = re.sub(r"[^a-z0-9. ]+", " ", text)
    return " ".join(_stem(t) for t in text.split())


def numbers(text: str) -> set[str]:
    return {str(float(n)) for n in _NUMBER.findall(normalize(text))}


@dataclass
class Match:
    item: Item | None
    score: float
    via: str
    alternatives: list[tuple[Item, float]] = field(default_factory=list)

    @property
    def sure(self) -> bool:
        return self.item is not None and self.score >= SURE and not self.ambiguous

    @property
    def ambiguous(self) -> bool:
        if not self.alternatives or self.item is None:
            return False
        return self.score - self.alternatives[0][1] < 4


class Matcher:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.by_code = {code_key(code): item for code, item in workspace.items.items()}
        self.texts = [
            (item, [normalize(t) for t in (item.name, *item.aliases)])
            for item in workspace.items.values()
        ]

    def match(self, line: ExtractedLine, customer_id: str | None = None) -> Match:
        if line.code:
            key = code_key(line.code)
            if key in self.by_code:
                return Match(self.by_code[key], 100, "code")
            close = process.extractOne(key, list(self.by_code), scorer=fuzz.ratio, score_cutoff=80)
            if close:
                return Match(self.by_code[close[0]], 80, "code with a typo")

        bought = {p.code for p in self.workspace.purchases(customer_id)} if customer_id else set()
        wanted = normalize(line.description)
        wanted_numbers = numbers(line.description)

        scored: list[tuple[Item, float]] = []
        for item, texts in self.texts:
            best = 0.0
            for text in texts:
                score = fuzz.token_set_ratio(wanted, text)
                if wanted_numbers and not wanted_numbers <= numbers(text):
                    score -= 25
                best = max(best, score)
            if item.code in bought:
                best += 4
            scored.append((item, min(best, 100.0)))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        top, score = scored[0]
        if score < PROBABLE:
            return Match(None, score, "description", scored[:3])
        rivals = [(item, s) for item, s in scored[1:4] if s >= PROBABLE]
        return Match(top, score, "description", rivals)
